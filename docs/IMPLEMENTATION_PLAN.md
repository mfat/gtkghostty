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
