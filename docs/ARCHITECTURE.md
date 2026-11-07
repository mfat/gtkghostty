# Architecture — extraction-first, fallback retained

**Status:** Proposed target architecture. The GTK widget is *not yet extracted or implemented*.

See [ADR 0001](ADR-0001-extraction-first.md) and [the extraction feasibility plan](EXTRACTION_FEASIBILITY.md) before implementing a new render layer.

## 1. Separate the three different Ghostty components

- `libghostty-vt 1.0.0`: stable C ABI; parser, terminal state, render state, encoding, effects. **Does not contain a GTK widget.**
- `GhosttySurface`: Ghostty **application-internal** libadwaita/GObject GTK widget implemented in Zig; includes input integration and links to `CoreSurface` / default GTK application.
- `GhosttyRenderSurface`: Ghostty **application-internal** `GtkWidget` drawing component that snapshots externally rendered DMA-BUF-backed textures; current upstream path, not the historical `Gtk.GLArea`.

## 2. Target public boundary (applies to either approach)

~~~text
GTK4 / libadwaita application (C, Python via GI, other GObject language)
                 |
    GtkGhostty.TerminalView (GtkWidget, documented ABI/GIR)
                 |   ^ signals: input, reply, resize, title, bell, permissions
                 |   |
        terminal model + native renderer
                 ^
                 | caller-provided byte transport
      +----------+----------+
      |          |          |
  POSIX PTY    ConPTY    other streams (SSH app/custom)
~~~

- The **view is not the process owner**. Spawning a shell is an optional adapter; the embedding app may own SSH CLI, a serial stream or a separate PTY.
- No hidden Ghostty default-application singleton is allowed in the public API.
- Feed and input payloads must be binary-safe (e.g. `GBytes`); specify ownership, ordering and dispatch to GTK main context.
- Multiple widgets/sessions must coexist in one application without global renderer/config clashes.
- Prefer an inspectable native GObject API with GIR and typelib for PyGObject. API names below are design candidates, not compiled symbols.

## 3. Path A — extracted Ghostty GTK

**First attempt:** preserve Ghostty's GTK widget and renderer while splitting it into minimal reusable layers:

~~~text
GtkGhostty.TerminalView (thin public GObject + gtk wrapper)
    -> extracted Ghostty GTK surface/input integration
    -> Ghostty CoreSurface + renderer subset
    -> caller-owned session adapter (or optional session launcher)
~~~

This can reduce duplicate font, rendering and input work but means maintaining a Zig/GTK/renderer integration layer. Carry an explicit inventory of upstream files and build dependencies. Keep any app-only functionality (window management, tabs, menus, notifications, shortcuts) outside library core.

**Critical risks:** Ghostty's `Application.default()` usage, deeply coupled `CoreSurface`, renderer thread lifecycle, GResource templates, direct DMA-BUF presentation (Linux-oriented), ABI/GIR compatibility, and upstream internal API churn.

**Don't** call Path A `libghostty-vt`-only: it uses more of Ghostty than the public ABI.

## 4. Path B — standalone libghostty-vt GTK frontend

Only after Path A is declared unviable by the documented gate:

~~~text
GtkGhostty.TerminalView (native GObject)
    -> GtkGhostty.TerminalModel (libghostty-vt 1.0 C ABI)
    -> GTK snapshot/Pango/GSK renderer + GTK IME/accessibility
    -> optional POSIX PTY / ConPTY or caller stream
~~~

Original C11/GObject + Meson design from the earlier research remains useful *here*. Delegate VT parsing, selection/search, keyboard encoding, render state and effects to libghostty. Do not implement a parser or force Python to paint cells.

The first fallback renderer can use Pango/Cairo in a measured prototype, then row caching or GSK/GPU after benchmark evidence. The fallback has a simpler library boundary but more UI engineering.

## 5. Portable graphics policy

Ghostty upstream has replaced its old `Gtk.GLArea` frame presentation with `GhosttyRenderSurface`, receiving DMA-BUF frames from the render thread via GDK textures. Do **not** assume Linux DMA-BUFs transfer directly to Windows/macOS GTK.

For an extracted renderer, preserve the renderer abstraction and implement/test alternate frame transport and fallback strategies per platform. Make capability detection and failure graceful. Characterize damage, scaling, font fallback, texture ownership and shutdown in each backend.

For Path B, GTK's standard snapshot/render nodes avoid depending on Ghostty's app-specific renderer but still require robust font shaping, effects, images and dirty-frame scheduling.

## 6. Public API sketch (provisional)

~~~c
/* Example signatures; not implemented. Validate GIR annotations and naming. */
GtkGhosttyTerminalView *gtk_ghostty_terminal_view_new(void);
void gtk_ghostty_terminal_view_feed(GtkGhosttyTerminalView *self,
                                   GBytes *output);
void gtk_ghostty_terminal_view_set_scrollback_limit(GtkGhosttyTerminalView *self,
                                                    guint lines);
/* Signals: "input-bytes" (GBytes*), "reply-bytes" (GBytes*),
   "grid-size-changed" (cols, rows, pixel_width, pixel_height),
   "title-changed" (UTF-8), "bell", "permission-request". */
~~~

Define synchronous vs queued calls, cancellation/EOF, resize ordering, clipboard permission ownership, thread constraints and per-session effects. Do not freeze API until extraction establishes a stable implementation.

## 7. Packaging and bindings

- If Path A wins: document Zig requirements, vendored/extracted Ghostty internals, native shared library exports, GI generation and platform renderer dependencies. `libghostty-vt 1.0` ABI alone does not stabilize those internals.
- If Path B wins: use Meson/C11, GTK4, Pango and pinned `libghostty-vt 1.0.0`, generate GIR with `gnome.generate_gir()`, package runtime and typelibs on each OS.
- In both cases: maintain LGPL/MIT/other attribution notices for reused sources, a reproducible upstream pin and native smoke tests.

## 8. Scope boundaries

No SSH Pilot backend changes, tab manager or bespoke network protocol in this library. Do not claim performance, cross-platform support, accessibility or keyboard correctness until tested. Do not replace VTE or PyXtermJS based on a Linux-only demonstration.
