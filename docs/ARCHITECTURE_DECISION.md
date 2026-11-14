# ADR 0002 — A native C/GObject widget on the public libghostty-vt 1.0 API

- **Status:** Accepted. Supersedes the ordering in [ADR 0001](ADR-0001-extraction-first.md) (extract
  Ghostty's GTK widget first); ADR 0001's analysis stays valid background.
- **Date:** 2026-11-14
- **Evidence:** [UPSTREAM_FEATURE_AUDIT.md](UPSTREAM_FEATURE_AUDIT.md), and SSH Pilot's libghostty-vt
  engine (`sshpilot` `a77f8bd4`, `46a14db5`), which runs the same release on Windows.

## Decision

Build `gtkghostty` as a **C/GObject GTK4 widget library** whose terminal core is the stable
**libghostty-vt 1.0** C ABI, drawn with GTK's own snapshot/Pango, and introspectable from Python via GIR.

- Terminal state, parsing, encoders, selection, search, paste, formatter and effects: **libghostty-vt**.
- Drawing and input glue: **ported from tilix2** (WTFPL), adapted to C and `GtkSnapshot`.
- The widget never owns a process. A byte stream goes in (`feed`), input and replies come out as signals.
  POSIX PTY and ConPTY are optional adapters in the same repository.

## Options considered

| Option | Verdict | Deciding evidence |
|---|---|---|
| A. Extract Ghostty's `GhosttySurface` / `GhosttyRenderSurface` | Rejected | App-internal Zig classes tied to `Application.default()`, `CoreSurface` and a DMA-BUF render path that is Linux-only; Ghostty on macOS is not GTK; a downstream of fast-moving internals (Blueshell's sync tooling shows the recurring cost) |
| B. Build on PrettyMux's `GhosttyTerminal` | Rejected | Needs a Ghostty **fork** (`patcito/ghostty@bd604e89`, frame API not upstream), the internal `libghostty.so` with its own GL context and shell, a global `ghostty_app_t`; GPL-3.0-only |
| C. Python widget on pyghostty (tilix2 as is) | Rejected for the library, kept as reference | pyghostty bundles a pre-1.0 library and has no Windows wheel; per-cell work in Python: a Python full-screen GTK redraw measured 116 ms on Linux and 144 ms on Windows (snapshot build), of which Pango itself is 10–13 ms |
| **D. C widget on libghostty-vt 1.0** | **Chosen** | Stable, versioned ABI (`GHOSTTY_VT_1.0` symbol versions); builds offline for Linux and cross-builds for Windows from one host (verified); no global state; licence MIT; the parts we must write are the GTK glue tilix2 already demonstrates |

## Consequences and rules

1. **No protocol code in gtkghostty.** If libghostty-vt has an API for it, call it. Exceptions: plain-text
   URL detection and regex search (libghostty search is literal).
2. **Keyboard on ConPTY.** A `legacy-keyboard` property makes the widget ignore kitty keyboard flags:
   ConPTY forwards a program's kitty request but cannot parse kitty-encoded keys (verified). Embedders on
   ConPTY set it; Linux and macOS PTYs leave it off.
3. **Rendering.** Start with one Pango layout per run, cached per row id and rebuilt only for dirty rows
   (tilix2's scheme). This is required, not an optimisation, on Windows: mixed-script relayout of a
   200×60 screen costs ~59 ms there. Draw with `GtkSnapshot` rather than Cairo so GSK can use the GPU;
   compare against tilix2's Cairo path on Linux before committing to either. A glyph atlas waits for
   measurements that demand it.
4. **Resize and history.** Expose `pull-history-on-grow` (`OPT_RESIZE_PULL_SCROLLBACK`); ConPTY
   embedders turn it off.
5. **Licence.** LGPL-2.1-or-later (decided 2026-11-15), as GTK and VTE: any application can link
   the widget, and changes to the widget stay free. MIT (libghostty-vt, Roost), WTFPL (tilix2) and
   Apache-2.0 (pyghostty) code may be ported with attribution in `NOTICE`; GPL/AGPL projects
   (PrettyMux, TildaZ) and Kwi's LGPL-only-v2.1/v3 modules stay design references. SSH Pilot code is
   relicensed by its author for gtkghostty under LGPL-2.1-or-later (see `NOTICE`).
6. **SSH Pilot integration** comes after the widget passes its parity checks on Windows; SSH Pilot keeps
   its current engines as fallbacks until then. SSH Pilot is the first consumer, not a dependency.

## First milestone

A shared library and GIR typelib with one widget, `GtkGhosttyTerminal`:

- `feed(GBytes)`, signals `input` (keys, paste, mouse, focus) and `reply` (`WRITE_PTY`), `size-changed`
  (cols, rows, cell pixels), `title-changed`, `bell`;
- render-state drawing with dirty-row layout caching, box drawing on the grid, wide cells, cursor,
  selection colours;
- keys through `ghostty_key_encoder` (with `legacy-keyboard`), text through `GtkIMMulticontext`;
- a Python demo that imports it through `gi.repository`, feeds a recorded VT fixture without a shell,
  and a second demo with the POSIX PTY adapter.

**Exit criteria:** the fixture renders identically to the SSH Pilot libghostty engine's text output;
vim, less and htop work through the PTY demo on Linux; the same build runs the fixture on Windows.

## Open questions

- Snapshot or Cairo: decide by measurement on Linux and on real Windows hardware (the test VM has no GPU).
- Preedit drawing and `GtkAccessibleText`: no reference covers them; design needed.
