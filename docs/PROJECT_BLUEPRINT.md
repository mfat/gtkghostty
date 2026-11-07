# GTK4 + libghostty independent widget — collected project blueprint

Research snapshot: November 7, 2026. This is a collection of sources, architectural decisions, dependency instructions, and implementation gates—not working widget code.


---

# File: README.md

# Cross-platform GTK4 terminal widget powered by libghostty-vt

**Engineering starter kit — research snapshot: 2026-11-07**

**Status:** architecture, source inventory, reproducible reference checkout tooling, risk assessment, and milestone plan. **Not** a compiled widget. This pack deliberately does not redistribute third-party project code or vendored libraries.

## Purpose

Build an independent, embeddable, native GTK4 terminal widget for Linux, Windows and macOS. Expose it through a stable C/GObject API and GObject Introspection for Python/PyGObject. Integrate with SSH Pilot only after a standalone component passes platform tests.

## Read in this order

1. [ARCHITECTURE.md](docs/ARCHITECTURE.md) — design decision and proposed API.
2. [SOURCE_MAP.md](docs/SOURCE_MAP.md) — exact existing pieces and which ones to reuse vs study.
3. [BOOTSTRAP.md](docs/BOOTSTRAP.md) — official libghostty 1.0.0 setup, OS prerequisites and research reference checkout.
4. [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) — phased work, acceptance gates and issue breakdown.
5. [TEST_PLAN.md](docs/TEST_PLAN.md) — cross-platform tests, regressions, benchmarks.
6. [SECURITY_AND_LICENSING.md](docs/SECURITY_AND_LICENSING.md) — terminal effects policy, I/O lifecycle, license guardrails.
7. [sources.lock.json](sources.lock.json) — repository SHA pins verified through the public GitHub API.

## Fundamental architecture

```text
App (SSH Pilot or any Gtk4 app) [Python, C, Rust, ...]
    | GObject Introspection (GtkTermKit-1.0.typelib)
    v
GtkTermKit.TerminalView : GtkWidget    <-- rendering, keyboard, IME, selection, accessibility
    |                                   <-- emits input-bytes; receives feed(output-bytes)
    v
GtkTermKit.TerminalModel / libghostty-vt 1.0.0  <-- VT parsing, screen, input encoding, selection, search, RenderState
    ^
    | independent bidirectional session adapter (optional)
    +--- POSIX PTY (Linux / macOS)
    +--- Windows ConPTY (Windows 10 1809+)
    +--- caller-provided input/output transport (SSH app integration)
```

**Design invariant:** the widget never unilaterally owns a shell or SSH process. Session lifecycle is an optional adapter with an explicit owner; it must not be required just to render and interact with a terminal stream.

## First green milestone

An isolated GTK4 demo runs on **Windows and Linux** with the same C widget, shows ANSI colors and Unicode from a real shell, sends input, handles resize, and is importable via `gi.repository` from Python. macOS runs before a beta release. Do not delete VTE or PyXtermJS in SSH Pilot until this passes an explicit parity suite.

## Upstream must-read

- [Libghostty 1.0 announcement (2026-11-06)](https://mitchellh.com/writing/libghostty-1-0)
- [Official libghostty-vt installation guide](https://lib.ghostty.org/vt/installing.html)
- [Official Your First Terminal](https://lib.ghostty.org/vt/first-terminal.html)
- [Official Rendering guide](https://lib.ghostty.org/vt/guide-rendering.html)
- [Official Effects guide](https://lib.ghostty.org/vt/guide-effects.html)
- [Official examples index](https://lib.ghostty.org/vt/example-programs.html)

Reference source commits are pinned separately; upstream may have changed since this snapshot.


---

# File: docs/ARCHITECTURE.md

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


---

# File: docs/SOURCE_MAP.md

# Source map: actual reusable pieces

Snapshot and commit pins: `../sources.lock.json` (retrieved from public GitHub branch API 2026-11-07). Paths below are verified in repository listings or fetched source. **Links show live branches**; use pinned SHAs to ensure the same code during development.

## Library and official examples — integrate

| Source | Exact reference | Why |
|---|---|---|
| libghostty-vt 1.0.0 | https://lib.ghostty.org/vt/installing.html | Stable parser/renderer-state engine and C ABI; official build artifacts |
| Your First Terminal | https://lib.ghostty.org/vt/first-terminal.html | Native API initialization and update/clean lifecycle |
| Rendering guide | https://lib.ghostty.org/vt/guide-rendering.html | Dirty rows, colors, cursor, selection, two-phase locking |
| Effects guide | https://lib.ghostty.org/vt/guide-effects.html | PTY replies, title, clipboard, notifications, synchronous callback rules |
| C example index | https://lib.ghostty.org/vt/example-programs.html | 29 maintained C programs including input, selection, Kitty images, effects |
| Ghostling | https://github.com/ghostty-org/ghostling/blob/main/main.c | Minimal working terminal frontend showing integration (Raylib, not GTK) |
| Packaging guide | https://github.com/ghostty-org/ghostty/blob/main/PACKAGING-LIBGHOSTTY.md | Source/dependency tarballs, build/verification/install flags |

**Official examples to prioritize, in this order:** `c-vt-stream`, `c-vt-render`, `c-vt-effects`, `c-vt-encode-key`, `c-vt-encode-mouse`, `c-vt-encode-focus`, `c-vt-paste`, `c-vt-selection-gesture`, `c-vt-search`, `c-vt-kitty-graphics`, `c-vt-build-info`. Follow examples index links to their actual source locations.

## Forgetty — preferred GTK-specific reference (MIT)

- Repo: https://github.com/vikgmdev/forgetty
- GTK drawing, Pango, event loops, selection, cursor and terminal integration:
  - https://github.com/vikgmdev/forgetty/blob/main/crates/forgetty-gtk/src/terminal.rs
  - https://github.com/vikgmdev/forgetty/blob/main/crates/forgetty-gtk/src/input.rs
  - https://github.com/vikgmdev/forgetty/blob/main/crates/forgetty-gtk/src/clipboard.rs
- Reuse **concepts and potentially MIT-licensed code with required notices**; do not import its daemon/session infrastructure merely to get a widget. Linux-focus; no verified standalone GObject view or Windows/macOS GTK support.
- License: https://github.com/vikgmdev/forgetty/blob/main/LICENSE (MIT).

## Kwi — API/renderer/accessibility blueprint (LGPL sublibraries; GPL application)

- Repo: https://github.com/KDE/kwi
- Independent module design: `libs/ghostty-qt`, `libs/ghostty-qt-quick`, `libs/kwi-terminal`; README files explicitly describe their purposes.
- libghostty integration and frame representation:
  - https://github.com/KDE/kwi/blob/master/libs/ghostty-qt/src/Terminal.h
  - https://github.com/KDE/kwi/blob/master/libs/ghostty-qt/src/Terminal.cpp
  - https://github.com/KDE/kwi/blob/master/libs/ghostty-qt/src/Frame.h
- Text/layout/GPU:
  - https://github.com/KDE/kwi/blob/master/libs/ghostty-qt-quick/src/TerminalNode.cpp
  - https://github.com/KDE/kwi/blob/master/libs/ghostty-qt-quick/src/GlyphAtlas.cpp
  - https://github.com/KDE/kwi/blob/master/libs/ghostty-qt-quick/src/GridShaper.cpp
  - https://github.com/KDE/kwi/blob/master/libs/ghostty-qt-quick/src/PreeditLayout.cpp
- Input and UI:
  - https://github.com/KDE/kwi/blob/master/libs/ghostty-qt/src/QtInput.cpp
  - https://github.com/KDE/kwi/blob/master/libs/kwi-terminal/src/TerminalView.cpp
  - https://github.com/KDE/kwi/blob/master/libs/kwi-terminal/src/TerminalView.h
  - https://github.com/KDE/kwi/blob/master/libs/kwi-terminal/src/TerminalAccessible.cpp
  - https://github.com/KDE/kwi/blob/master/libs/kwi-terminal/src/Session.cpp
  - https://github.com/KDE/kwi/blob/master/libs/kwi-terminal/src/process/PtyProcess.cpp
- Kwi `ghostty-qt*` and `kwi-terminal` README files declare `LGPL-2.1-only OR LGPL-3.0-only OR LicenseRef-KDE-Accepted-LGPL`; inspect per-file SPDX and compatibility before adapting source. Its main executable uses GPL. It uses Qt Quick/GPU and `KPtyDevice` rather than GTK/ConPTY. Thus **study algorithms and interfaces, don't treat its code as GTK plug-and-play**.

## Windows and platform implementations — study for correctness

**mightty** — https://github.com/frixaco/mightty
- `src/shell/windows.rs` (ConPTY), `src/shell/unix.rs`, `src/widget/input.rs`, `src/widget/text_input.rs`, `src/widget/pty.rs`, `src/widget/render.rs`, `src/widget/graphics.rs`.
- Repo says code is MIT in README, but confirm file-level notices and dependencies before copying. It uses Rust/GPUI, not GTK. Its README currently pins an older Ghostty submodule/Zig 0.16, so **do not copy its build instructions** for the independent libghostty-vt 1.0.0 release.

**TildaZ** — https://github.com/ensky0/tildaz
- Architecture: https://github.com/ensky0/tildaz/blob/main/ARCHITECTURE.md
- `src/terminal/windows/pty.zig`, `src/terminal/posix/pty.zig`, `src/session_core.zig`, `src/terminal_interaction.zig`, platform font and IME handling.
- **AGPL-3.0-or-later**: https://github.com/ensky0/tildaz/blob/main/LICENSE. Use documentation to understand platform design; **do not copy/translate implementation into a permissively licensed widget without legal assessment and complying with AGPL requirements**.

**Phantty** — https://github.com/arya-s/phantty
- `src/directwrite.zig`, `src/font/`, `src/pty.zig`, `src/Renderer.zig`, `src/input.zig`.
- Windows-only font discovery, fallback and renderer reference. Repository metadata did **not identify a license** on inspection; **reference only until terms are established**.

## Python and alternative transports

- Python CFFI bindings for experimental work: https://github.com/AnswerDotAI/pyghostty (Apache-2.0 listed by GitHub). The final native widget should use GIR instead of depending on these bindings.
- Web fallback option: https://github.com/coder/ghostty-web . Useful for independent comparison but not the native GTK4 implementation.
- Windows official ConPTY: https://learn.microsoft.com/en-us/windows/console/createpseudoconsole
- GTK Windows/Python setup: https://pygobject.gnome.org/getting_started.html
- GTK accessibility: https://docs.gtk.org/gtk4/iface.AccessibleText.html (since GTK 4.14)
- GObject introspection: https://developer.gnome.org/documentation/guidelines/programming/introspection.html

## Other projects from the 1.0 announcement: why not critical for this widget

- JetBrains terminal, Neovim integration, Turborepo/devenv, Ghostel, cmux, herdr, OrbStack all demonstrate broader VT reuse, but are not closer GTK widget references than Forgetty.
- Awesome directory: https://github.com/Uzaaft/awesome-libghostty — watch for newly released GTK widgets rather than assuming a ready-made component exists.

## Provenance and confidence

Confirmed: official libghostty docs; listed paths and sample source; Forgetty/Kwi/TildaZ/mightty/Phantty repo files and license statements; GTK APIs; source HEAD SHAs. Not confirmed: building or running these source versions with GTK4 on all OSes; full upstream dependency auditing; GUI performance; shipping quality. This is a **source/architecture kit**, not a code validation report.


---

# File: docs/BOOTSTRAP.md

# Reproducible setup and dependency collection

## 0. Tools

- Native C compiler, Meson, Ninja, pkg-config, GTK4 development headers, GLib/GObject, Pango/PangoCairo, GObject Introspection (`g-ir-scanner`, `g-ir-compiler`), Python 3 and PyGObject for smoke tests.
- Zig **0.17** for libghostty-vt **1.0.0**, per official install guide. Don't assume another Zig minor works.
- Git to fetch pinned reference snapshots. Use `tools/fetch_reference_sources.py`.
- `curl`, `minisign`, `sha256sum` or Python hashlib for verifying signed source releases.

## 1. Pin official libghostty-vt 1.0.0

**Release root:** https://release.files.ghostty.org/libghostty-vt/1.0.0/

Download from that root:

- `libghostty-vt-1.0.0.tar.gz`
- `libghostty-vt-1.0.0-deps.tar.gz` (optional cache for offline build)
- `SHA256SUMS` and `SHA256SUMS.minisig`

Verify `SHA256SUMS` with the **official** public key from https://lib.ghostty.org/vt/installing.html, then verify the tarball hashes before extraction. The provided `tools/fetch_libghostty_vt.sh` automates verification on Linux/macOS/WSL/MSYS2 where `curl`, `minisign` and Python exist. It *downloads but does not compile* the library.

Build the official release source (Zig 0.17):

```sh
cd libghostty-vt-1.0.0
zig build -Doptimize=ReleaseFast --prefix "$HOME/.local"
export PKG_CONFIG_PATH="$HOME/.local/lib/pkgconfig:$PKG_CONFIG_PATH"
pkg-config --modversion libghostty-vt
```

For reproducible/offline builds, use the companion deps tarball and follow `PACKAGING-LIBGHOSTTY.md` for `--system`. Note `--prefix` installation location differs across machines; use `pkg-config` rather than hardcoding `lib/` vs `lib64/`.

**Do not** use GitHub's autogenerated source ZIP for the release: official docs state it is missing the libghostty build selection file. Don't use Ghostty app's main branch build defaults as if they were `libghostty-vt` release defaults. Libraries are independent.

## 2. Cross-platform toolchain

### Linux (Ubuntu/Debian, example)

```sh
sudo apt install build-essential meson ninja-build pkg-config libgtk-4-dev \
  libpango1.0-dev libgirepository-2.0-dev gobject-introspection \
  python3-gi python3-gi-cairo gir1.2-gtk-4.0
```

**Important:** Package names differ by distro/release. Install PTY headers from the C library/OS SDK as appropriate. Verify installed dependencies using Meson; this install recipe was not run in CI.

### Windows

Use MSYS2 UCRT64 per https://pygobject.gnome.org/getting_started.html. Install GTK4, Python, PyGObject, C compiler, Meson, Ninja, pkgconf, gobject-introspection, and GI typelibs in **one consistent UCRT64 prefix**. Avoid mixing MSYS and UCRT64 libraries or Python installations. Build libghostty-vt with Zig 0.17 and make its DLL/import library discoverable to the compiler and runtime. No official prebuilt Windows libghostty-vt binary is currently published.

Test Win10 1809+ / Win11 ConPTY. Don't make the library launch a shell just to display supplied bytes.

### macOS

Install GTK4, Pango, GLib, Meson/Ninja, GObject Introspection and PyGObject from a coherent package-manager prefix, build or install the libghostty-vt dynamic library with valid `@rpath`, and test Intel and Apple Silicon separately. Official XCFramework is an option for Apple builds but check whether it fits your C/Meson GTK linking workflow.

## 3. Retrieve reference source snapshots

```sh
python3 tools/fetch_reference_sources.py
```

This clones snapshots into an **ignored** `references/` directory and checks out the SHAs from `sources.lock.json`. It does not vendor those sources into your library, and requires network/Git when executed. Use `--list` to print locks without downloading; use `--only forgetty,kwi` to fetch selected repos.

## 4. Proposed Meson setup (specification, not tested build)

```meson
project('gtktermkit', 'c', version: '0.1.0', default_options: ['c_std=c11'])
gtk = dependency('gtk4', version: '>=4.14')
libghostty = dependency('libghostty-vt', version: '>=1.0.0')
# also use glib-2.0, gobject-2.0, pango, pangocairo, cairo
# shared_library('gtktermkit-1', sources, dependencies: [...], install: true)
# gnome.generate_gir(... namespace: 'GtkTermKit', nsversion: '1.0', ...)
```

Use `>=1.0.0` with a carefully reviewed ABI compatibility policy; maintain a tested-version matrix and reject missing required features at runtime if library returns `GHOSTTY_UNSUPPORTED`.

## 5. Cross-platform CI targets

- Linux: GCC/Clang; debug sanitizer build; headless parser tests; GTK integration tests with appropriate display backend; Pango and GIR import check.
- Windows: MSYS2 UCRT64 compile + native Windows GUI smoke + PyGObject import + ConPTY test; test the DLL load path.
- macOS: Intel and Apple Silicon build matrix where runners exist; `@rpath`/codesigning/notarization concerns for distributed apps.
- Dependency updates: lock Zig toolchain, source version, build features, reproducible package checksum; run ABI/feature smoke tests.

## Direct sources

- https://lib.ghostty.org/vt/installing.html
- https://github.com/ghostty-org/ghostty/blob/main/PACKAGING-LIBGHOSTTY.md
- https://pygobject.gnome.org/getting_started.html
- https://developer.gnome.org/documentation/guidelines/programming/introspection.html


---

# File: docs/IMPLEMENTATION_PLAN.md

# Implementation plan and work packages

Do **not** start with a full terminal emulator or packaging into SSH Pilot. Complete the sequence below as standalone, testable deliverables.

## Phase 0 — foundation / license gate

- [ ] Decide intended license **before copying other implementations**. For maximum flexibility start with original code + official MIT libghostty; treat Kwi LGPL and TildaZ AGPL source only as research until licensing decision.
- [ ] Verify official libghostty 1.0.0 tarballs/signatures and compiler/toolchain on Linux and Windows.
- [ ] Create minimal Meson C/GObject library and a GIR-annotated dummy `GtkWidget` subclass; import in `gi.repository` on Linux and Windows.
- [ ] Decide and document supported GTK minimum (recommended **4.14**, to implement `GtkAccessibleText`).
- [ ] Unit test shell-free `feed()` and frame snapshot via official C example.

**Gate:** CI builds C library + installed GIR/typelib on two OSes, Python can instantiate widget, and no copied code has unresolved license.

## Phase 1 — visible terminal on 2 OSes

- [ ] Own GhosttyTerminal/RenderState and lifecycle, parser effects, consistent error paths.
- [ ] Native GObject `TerminalView` with font metrics and whole-screen Pango/Cairo or GSK drawing.
- [ ] Render background/foreground/palette, styles, cursor, ANSI colors, wide glyphs.
- [ ] Correct grid resizing and clip; forward computed cols/rows and pixels to caller.
- [ ] Repaint only when needed; test sustained text throughput against VTE baseline.

**Gate:** same GTK source renders static tests and a live session on Linux and Windows, including Unicode and resizing.

## Phase 2 — full interactive local shell

- [ ] `GtkEventControllerKey`, libghostty key encoding and `GtkIMContext` preedit/commit.
- [ ] Optional POSIX PTY + Windows ConPTY process adapter with clean exit, status and signals.
- [ ] PTY replies via `WRITE_PTY` effect; never drop query replies.
- [ ] Focus, mouse protocols, scrollbar/scrollback, selection gestures and clipboard.
- [ ] Safe paste, bracketed paste and multi-line paste approval hook.
- [ ] Search and selection formatting; alternate screen and cursor styles.

**Gate:** run `vim`, `nano`, `less`, `htop`/`btop`, `ssh`, and a shell; arrow keys, IME, AltGr, resize and mouse all work on Linux and Windows.

## Phase 3 — portability, hardening, usability

- [ ] macOS GTK4 rendering, PTY, font and IME smoke tests on both CPU families where possible.
- [ ] Accessibility: GtkAccessibleText + Orca; carets, lines, text changes and selections.
- [ ] Security: title/URL sanitization; no unsolicited clipboard reads; OSC52 policy; limits on images and callbacks.
- [ ] Kitty images, cached textures, clipping, layering and animation; progress notifications.
- [ ] Cache unchanged rows and benchmark under high output; stress test 10+ widgets.
- [ ] Keyboard shortcut ownership contract, session detach/re-attach and graceful shutdown.

**Gate:** three-OS CI checks, platform GUI manual/automated suite, security policies documented, no regressions in input/graphics.

## Phase 4 — independent public library

- [ ] SemVer for the C/GObject public API and GIR namespace/version.
- [ ] pkg-config, Meson subproject option, headers, GIR/typelib and Python demo.
- [ ] Windows packaging (GTK native DLLs, Ghostty DLL), Linux distro/Flatpak packaging, macOS dylib/@rpath.
- [ ] Examples: shell-free byte-stream viewer, local shell, SSH CLI process, embedding into an existing libadwaita app.
- [ ] Release notes, security policy, library license notices, source-provenance manifest.

**Gate:** third-party GTK4 app can embed the widget without linking to any SSH Pilot code.

## Phase 5 — SSH Pilot integration (separate)

- [ ] Implement new `GtkTermKitBackend` satisfying the existing backend interface.
- [ ] Keep VTE on Linux and existing fallback elsewhere during comparison.
- [ ] Compare Pango/fonts, keyboard, dynamic resize, SFTP commands running in terminal, progress callbacks, SSH prompts, terminal reconnect behavior, split tabs.
- [ ] Feature flag backend; collect controlled bug reports; migrate only when parity gates pass.

## Suggested initial issues

1. `build: libghostty-vt 1.0.0 dependency + CI smoke test`
2. `gobject: first GtkWidget subclass with GIR import on Windows/Linux`
3. `core: terminal feed + RenderState update/clean + effects queue`
4. `render: palette, text runs, glyph metrics and cursor`
5. `resize: grid geometry and PTY window-size synchronization`
6. `input: GTK key->Ghostty key mapper + fixture suite`
7. `input: GTK IM context preedit and commit`
8. `session: POSIX PTY adapter with cleanup`
9. `session: Windows ConPTY adapter + Windows 10/11 tests`
10. `interaction: selection, clipboard, scrolling, search`
11. `a11y: GtkAccessibleText mapping and Orca acceptance`
12. `packaging: three-platform binaries and smoke apps`

## No-go criteria / contingency

- If Windows GTK4 native font/IME behavior cannot reach acceptable parity without large platform-specific changes, keep the widget core and renderer reusable but postpone Windows release; retain current SSH Pilot fallback.
- If main-thread rendering stalls under normal output, measure and implement row caching before adopting GPU APIs.
- If the desired minimal GTK version cannot support accessible text, decide to raise it or document a clear alternate accessibility strategy; do not silently ship an inaccessible renderer.


---

# File: docs/TEST_PLAN.md

# Test plan and acceptance matrix

## Test levels

**Unit / no GUI:** parser feed, model allocations/free, render snapshots, styles, palette, selection/search, input event encoding and effects callback queues. Use official libghostty C examples as correctness fixtures, not hand-rolled VT parsing.

**Widget integration / virtual display:** instantiate/destroy, focus, drawing, resize, font changing, GObject signal and GIR typing/ownership, dispose without use-after-free. Drive input with GTK event controllers; compare rendered image fixture for stable fonts on specific CI machines only.

**Native GUI smoke:** on real Windows/macOS/Linux, exercise IME, keyboard layouts, clipboard, screen readers, DPI/fractional scaling and process lifecycle. Headless success does not imply native GUI success.

**Stress/robustness:** thousands of full-screen redraws, throttled/fast PTY output, large scrollback, terminal resize storms, malicious OSC sequences, clipboard read/write attempts, session detach while output continues, many widgets in a window.

## Required fixtures

| Area | Cases | Pass criterion |
|---|---|---|
| UTF-8 | Split multibyte input across feed calls; combining marks; CJK wide chars; emoji/ZWJ | same grid as official libghostty API; no clipped cursor |
| Styling | SGR 8/16/256/RGB, bold, faint, underline kinds, inverse, OSC palette change | correct color/style snapshot |
| State | Alternate screen, scrollback reflow, rapid resize, cursor shape/blink | no missing rows or invalid handles |
| Input | AltGr, Ctrl+C, Backspace, Enter/Tab, arrows, F1–F12, keypad, Kitty keyboard | expected program input, no duplication |
| IME | Japanese, Chinese, Korean preedit + commit, dead keys, combining accents | no duplicate text; correct caret position |
| Pointer | SGR mouse mode, app consumes drag, selection override, double/triple click | compatible with terminal TUIs |
| Paste | UTF-8 paste, large paste, bracketed paste, multiline confirmation | safe policy and no data loss |
| Effects | DSR/DA replies, title, bell, OSC 52 clipboard read/write, untrusted URI | explicitly defined permission/policy |
| Rendering | Retina/HiDPI, fractional scale, font fallback, emoji/powerline/box drawing | readable fixed-width grid |
| Images (later) | Kitty placements, clipping, opacity, animation | correct state and bounded memory |
| Lifecycle | EOF, child crash, quick close, reattach view, cancellation mid-write | no deadlock or use-after-free |
| Accessibility | Orca reads contents/caret/selection and updates | documented success on supported GTK version |

## Manual smoke commands / apps

- `printf '\033[31mRED\033[0m wide: 漢字 emoji: 🧪\n'` (actual runtime interpreted by shell)
- `less`, `vim` or `nvim`, `nano`, `top` or `htop`, `btop`, `tmux` and an SSH login to a test machine.
- Repeatedly resize during a running TUI, paste multi-line shell commands, test AltGr and IME input.
- Powerline/Nerd Font glyphs only using fonts installed by user; don't redistribute proprietary fonts.
- Compare with VTE on Linux and Windows Terminal/ConPTY on Windows where appropriate.

## Performance targets (proposed gates, NOT measured)

- Normal shell input should feel instantaneous on all 3 OSes; instrument key-to-frame latency, don't assume libghostty parse speed guarantees renderer latency.
- Benchmark 1 MB and 10 MB VT fixtures; report CPU time, peak resident memory, dropped updates and p50/p95 frame time.
- Stress 10 simultaneous widgets and multi-minute output; verify bounded memory and responsive UI.
- Record baselines from VTE/Forgetty/Kwi where binaries are reproducible and comparable; do not claim cross-toolkit benchmark equivalence.

## CI suggestion

1. Linux x86_64: GCC + clang, ASAN/UBSAN and basic GUI smoke (Xvfb/Wayland test environment as available).
2. Windows x86_64: MSYS2 UCRT64 + GTK4/PyGObject + libghostty DLL + ConPTY smoke.
3. macOS x86_64/aarch64: compile and local GUI test where runner access allows.
4. Nightly: install/ABI smoke, parallel session stress, upstream test fixtures.

A virtual display test does not replace actual Wayland/Windows/macOS tests. Make bug reports include libghostty version, GTK version, font, scale factor, PTY adapter, OS and exact reproduction bytes.


---

# File: docs/SECURITY_AND_LICENSING.md

# Security, licensing and release obligations

## Remote terminal output is untrusted

The terminal can process malicious or accidental escape sequences from a remote server. libghostty-vt is fuzz-tested, but callbacks that perform side effects are **your application's responsibility**.

- The documented callbacks execute synchronously inside VT writes, are non-reentrant, and shouldn't block. Copy borrowed memory and enqueue any reply or UI request.
- Register the PTY reply callback explicitly so interactive programs receive device status reports. Ensure there is bounded buffering and proper cancellation.
- Off by default for remote sessions: OSC 52 clipboard **read**. For clipboard **write**, add explicit user preference/permission mechanism; never silently bridge remote server to local clipboard.
- Treat `title`, working directory, hyperlinks, notifications, file paths, and image/file-loading requests as untrusted. Sanitize and bound displayed values; require user action for opening URIs. Do not allow host filesystem access through a Kitty image request by default.
- Require confirmation for potentially dangerous multiline paste; support bracketed paste correctly.
- Limit memory/CPU for high-volume output, escape callbacks, scrollback and graphics. Cancel or detach sessions without leaking workers, handles or child processes.

Sources: https://lib.ghostty.org/vt/guide-effects.html and https://lib.ghostty.org/vt/first-terminal.html

## Licensing review before copying code

| Repo/component | License evidence as inspected | Safe use guideline |
|---|---|---|
| libghostty-vt 1.0.0 | MIT; official dependency manifest | Link/build against 1.0.0; retain required notices |
| Ghostling | MIT in repo | Reuse illustrative integration code subject to MIT notices |
| Forgetty | MIT in LICENSE | Candidate GTK implementation reference/code with attribution |
| Kwi lib modules | README and per-file headers: LGPL-2.1-only OR LGPL-3.0-only OR KDE accepted | Possible adaptation under compatible conditions; inspect original notices before using source |
| Kwi full application | GPL variants in top-level CMake project | Don't confuse top-level app license with LGPL sublibraries |
| TildaZ | AGPL-3.0-or-later in LICENSE | Architecture/documentation reference; do not copy/port AGPL code unless ready to satisfy license obligations |
| mightty | README states MIT; third-party notices | Verify file and third-party notices before borrowing |
| Phantty | No license established in repo metadata | Reference only; don't copy until permissions clarified |
| pyghostty | Apache-2.0 per GitHub metadata | Optional Python experimentation only; retain license notices if reused |
| GTK/Pango/GLib etc. | Individual upstream licenses | Track versions, notices and linking obligations separately |

License evidence is a **research snapshot, not legal advice**. Even MIT-licensed source code requires preservation of copyright notices. A source rewrite may still be derivative; do not assume changing languages makes a copyleft requirement disappear. Develop your own GTK design with MIT-compatible references if a permissive public widget is the goal.

## Release hygiene

- Record SPDX IDs, copyright notices and commit SHAs for any copied code.
- Include `THIRD_PARTY_NOTICES.md` and machine-readable build manifest.
- Sign/hash downloadable binaries and publish reproducible build instructions.
- Verify `libghostty-vt` ABI version and required features rather than assuming new library versions always include optional features.
- Publish a security contact/reporting workflow and support policy.

