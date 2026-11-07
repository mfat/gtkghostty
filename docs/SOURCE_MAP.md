# Source map — extraction-first references

**Current first priority:** upstream Ghostty's existing GTK widget, *not* a new libghostty-vt renderer. See [ADR 0001](ADR-0001-extraction-first.md) and [EXTRACTION_FEASIBILITY.md](EXTRACTION_FEASIBILITY.md). Live upstream links can change; `sources.lock.json` includes a pinned `ghostty-app` revision.

## Ghostty GTK widgets — first to evaluate (upstream application, MIT)

| File | What to inspect |
|---|---|
| [`src/apprt/gtk/class/surface.zig`](https://github.com/ghostty-org/ghostty/blob/main/src/apprt/gtk/class/surface.zig) | `GhosttySurface`, `adw.Bin`/`GtkScrollable` GObject, events/IME/clipboard, `CoreSurface` ownership, singleton assumptions |
| [`src/apprt/gtk/class/render_surface.zig`](https://github.com/ghostty-org/ghostty/blob/main/src/apprt/gtk/class/render_surface.zig) | `GhosttyRenderSurface` GTK snapshot widget, render thread, DMA-BUF presentation/GDK textures |
| [`src/apprt/gtk/class/application.zig`](https://github.com/ghostty-org/ghostty/blob/main/src/apprt/gtk/class/application.zig) | Default GTK app, config, actions, notifications and app-only dependencies |
| [`src/apprt/gtk/Surface.zig`](https://github.com/ghostty-org/ghostty/blob/main/src/apprt/gtk/Surface.zig) | Runtime adapter between core surface and GTK implementation |
| [`src/Surface.zig`](https://github.com/ghostty-org/ghostty/blob/main/src/Surface.zig) | `CoreSurface` and app core responsibilities |
| [`src/renderer.zig`](https://github.com/ghostty-org/ghostty/blob/main/src/renderer.zig) | Ghostty rendering subsystem boundary |
| [`src/renderer/Dmabuf.zig`](https://github.com/ghostty-org/ghostty/blob/main/src/renderer/Dmabuf.zig) | DMA-BUF abstraction imported by current GTK render surface |

**Observation:** the current Ghostty GTK renderer is *not* a `Gtk.GLArea` frontend. Its source explicitly says `Gtk.GLArea` was replaced by a custom widget consuming DMA-BUF render frames. That path is not proven portable to Windows/macOS GTK. **Neither `GhosttySurface` nor `GhosttyRenderSurface` is exported as part of the stable `libghostty-vt 1.0` library.** These are application internals; exporting an independent C/GObject API requires real engineering work.

## Existing independent solutions — use only as needed
Snapshot and commit pins: `../sources.lock.json` (retrieved from public GitHub branch API 2026-11-07). Paths below are verified in repository listings or fetched source. **Links show live branches**; use pinned SHAs to ensure the same code during development.

## libghostty-vt and official examples — Path B fallback

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

## Forgetty — GTK-specific Path B reference (MIT)

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
