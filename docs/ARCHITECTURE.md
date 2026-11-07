# Architecture and API design

## 1. Chosen baseline

- **Implementation**: C11 (or compatible C), GTK4, GLib/GObject, Pango/PangoCairo, GDK; Meson/Ninja.
- **VT core**: pinned `libghostty-vt 1.0.0` (C ABI stable from 1.0).
- **Bindings**: `gnome.generate_gir()` from the very first release, producing GIR and typelib so Python uses `gi.repository` without a handcrafted Python rendering loop.
- **Renderer v1**: native `GtkWidget` subclass with `snapshot`/GSK and Pango layout; optional Cairo-backed `GtkDrawingArea` permitted for a *throwaway* proof-of-concept. Avoid per-cell Python drawing and avoid GPU-specific APIs initially.
- **Session**: optional module with POSIX PTY + Windows ConPTY; public widget works with **arbitrary byte streams**.
- **Packaging**: prefer dynamically linking an installed libghostty-vt for distro builds, and reproducibly bundling a pinned native library for application builds. Verify ABI at startup.

Reasoning: Ghostty does the hard VT work; GTK handles OS graphics backends, font integration and event dispatch; C/GObject is the cleanest introspection boundary for a reusable GTK4 component.

## 2. Internal components and boundaries

```text
src/engine/         GtTerminalModel: libghostty-vt handles, effects, buffers, RenderState locking
src/widget/         GtTerminalView: GtkWidget, size allocation, paint, cursor/scrollbar
src/render/         Font metrics, row cache, Pango shaping, styles, images (later)
src/input/          Gdk key mapping, libghostty key encoder, GTK IM context, pointer events
src/a11y/           GtkAccessibleText + row/cell-to-offset mapping (requires GTK 4.14)
src/session/        optional launcher/I/O; pt_posix.c, pt_win32.c
include/gtktermkit/  stable public headers with gtk-doc/GIR annotations
examples/           C example, Python/PyGObject example, standalone session demo
tests/              core unit tests, fixture replay, GUI smoke, cross-platform test harness
```

**TerminalModel contract**
- `feed(bytes)`: serially pass bytes into `ghostty_terminal_vt_write()`, manage effects, request repaint.
- `snapshot_frame()`: call `ghostty_render_state_update()` then consume dirty rows and cursor, then `ghostty_render_state_clean()` after completed draw; guard producer/render-state access as documented.
- `encode_key/encode_mouse/encode_focus/encode_paste`: delegate to libghostty, not handwritten escape sequences.
- `resize(cols, rows)`: synchronize VT model and session adapter; send PTY window-size update to process and optionally pixel-size report.
- `scroll`, `select`, `search`: delegate to libghostty selection and viewport APIs.
- `process_effect`: copy borrowed callback buffers, never feed recursively, never block parser on UI dialogs. Reply requests go to transport.

**TerminalView contract**
- Owns a reference to model but **not** necessarily the session.
- Reports calculated cols/rows and cell pixel dimensions from allocation and Pango metrics.
- Renders only from stable snapshot-owned state; manages animations (cursor, graphics) on GTK main context.
- Emits byte events and signals rather than directly choosing a PTY or opening a URL.
- Supports `GtkScrollable` or public `GtkAdjustment` (decide in prototype) to be embeddable in `GtkScrolledWindow`.

**Session contract**
- Local processes use a real PTY: `forkpty`/`openpty` on POSIX; `CreatePseudoConsole`+`STARTUPINFOEX`+`PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE` on Windows.
- Bidirectional byte pipes and process lifecycle independent of the widget; no UI thread blocking.
- SSH Pilot may launch `ssh` through the adapter; the terminal handles the *local ssh process's* PTY, not the remote server's PTY directly. Confirm SSH allocation flags and signal semantics platform by platform.
- Detaching the view must not kill a session unless the owning app explicitly chooses that policy.

## 3. Draft C/GObject public surface (DESIGN, NOT IMPLEMENTED)

```c
/* Proposed names only; validate GIR annotations and ownership rules. */
GtTerminalView *gt_terminal_view_new(void);
void gt_terminal_view_feed(GtTerminalView *self,
                           const guint8 *data,
                           gsize n_bytes);
void gt_terminal_view_set_font_desc(GtTerminalView *self,
                                    const PangoFontDescription *font);
void gt_terminal_view_set_scrollback_limit(GtTerminalView *self, guint lines);
void gt_terminal_view_scroll_to_bottom(GtTerminalView *self);
char *gt_terminal_view_dup_selection_text(GtTerminalView *self);
/* signals: input-bytes(GBytes*), size-changed(uint cols,uint rows),
 * title-changed(string), bell(), request-open-uri(string),
 * clipboard-request(...), process-reply-bytes(GBytes*). */
```

`GBytes` is preferable to a NUL-terminated string for binary data in GObject signals; compare `GBytes` vs `(array length=)` GIR annotations before freezing the ABI. Avoid using non-introspectable callback types in public headers. Prefer explicit ownership transfer annotations.

## 4. Rendering plan

1. Use `GhosttyRenderState` as the sole source of frame information. Keep `GhosttyRenderStateRowIterator`, cells iterator and layout caches alive correctly; no reference to cell data across updates.
2. Build native row drawing primitives: background, selected range, glyph runs, underlines, cursor, overlays.
3. Use Pango to determine cell width/ascent/descent. Enforce monospace grid discipline; wide/zero-width clusters and font fallback require extensive tests.
4. Start with whole-view `queue_draw`, measure. Optimize by caching unchanged row display lists or textures keyed by row generation/version. Do not assume GTK4 provides an arbitrary rectangular invalidation API for a widget.
5. Support scale-factor changes, fractional scaling, font changes, dark/light theme, transparency (opt-in).
6. Advance later to GSK render nodes/texture atlas if CPU layout cost or frame times warrant it; never copy Qt Scene Graph shaders directly into GSK.

## 5. Input and IME plan

- `GtkEventControllerKey` plus `GtkIMContext`/`GtkIMMulticontext` composition; wire `preedit`/`commit` and cursor location.
- Read keyval, physical keycode, modifier side, keysym/layout and repeat status where available; map to libghostty key event enums. Note that Linux XKB, Windows and macOS need separate native validation.
- Route keypresses to terminal unless explicitly reserved by embedding app. Default Enter/Tab always reach terminal when focused; no global app interception except documented shortcuts.
- `GtkGestureClick`, `GtkGestureDrag`, `GtkEventControllerMotion`, `GtkEventControllerScroll` plus terminal mouse-report mode. Allow Shift or user-configured override for text selection when mouse-reporting TUIs are active.
- Distinguish keyboard text commit from protocol key event, to avoid duplicated IME input. Focus change may generate libghostty focus event if requested by app mode.

## 6. Accessibility and threading

- GTK >=4.14 for `GtkAccessibleText`; build row/cluster/offset mapping similar in concept to Kwi's `TerminalAccessible.cpp`. Test with Orca on Linux and platform-specific assistive technologies where available.
- Begin with **single main-context ownership of the VT and renderer** for correctness. Offload only PTY reads and enqueue drained batches into GTK main context (with size limits). If profiling proves inadequate, add native model worker + brief synchronized `begin_update()/end_update()` snapshots.
- Parser callbacks are synchronous and non-reentrant; never show a modal dialog or call `feed()` recursively in them.

## 7. Public packaging names (provisional)

Proposed namespace `GtkTermKit-1.0`, shared library `libgtktermkit-1`, headers `<gtktermkit/terminal-view.h>`, pkg-config `gtktermkit-1.0`, Python `gi.require_version('GtkTermKit', '1.0')`. Names are placeholders, not official libghostty affiliation.

## 8. Out of scope at first milestone

Full GPU atlas, animated Kitty image rendering, sixel, clickable file paths, recording/replay UI, shell integration scripts, split panes and tab manager. The first widget must render **one** stream correctly and support one local process without depending on SSH Pilot internals.

## Sources

- https://lib.ghostty.org/vt/first-terminal.html
- https://lib.ghostty.org/vt/guide-rendering.html
- https://lib.ghostty.org/vt/guide-effects.html
- https://docs.gtk.org/gtk4/class.DrawingArea.html
- https://docs.gtk.org/gtk4/class.EventControllerKey.html
- https://docs.gtk.org/gtk4/class.IMContext.html
- https://docs.gtk.org/gtk4/iface.AccessibleText.html
- https://developer.gnome.org/documentation/guidelines/programming/introspection.html
