# Upstream feature audit — who already owns each feature

**Date:** 2026-11-14. **Inputs:** the libghostty-vt 1.0.0 release (headers, guides, `ghostty_type_json`
manifest), the reference projects below at their pinned commits, and measurements from SSH Pilot's
libghostty-vt engine (`sshpilot` `a77f8bd4`, `46a14db5` on `dev`), which binds the same release from
Python and runs on Windows under ConPTY.

Each row names the implementation gtkghostty should **use or follow** before writing anything, and the
glue that is genuinely left. "Verified" means run and observed, not read; everything else is from source.

## Sources and status

| Source | Commit reviewed | Licence (checked in tree) | What it is | Run here? |
|---|---|---|---|---|
| libghostty-vt | release 1.0.0 tarball, sha256 `4a6ef758…` (SHA256SUMS minisign-verified) | MIT (+ bundled deps listed in `deps/libghostty-vt-third-party.json`) | Stable C ABI: parser, screens, scrollback, render state, encoders, selection, search, effects | **Yes**: built offline on Linux and cross-compiled for Windows with Zig 0.17.1; used by SSH Pilot on Windows |
| [tilix2](https://github.com/markuman/tilix2) | `65d775b` | WTFPL v2 | One-file GTK4 terminal (1471 lines) on pyghostty, Cairo/Pango | No (pyghostty's bundled library is an unverified binary; not loaded) |
| [pyghostty](https://pypi.org/project/pyghostty/) | 0.1.4 wheel | Apache-2.0 | cffi binding over a bundled `libghostty-vt` | Inspected only |
| [PrettyMux](https://github.com/patcito/prettymux) | `137915d` | GPL-3.0-only | C/GObject `GtkWidget` around Ghostty's internal `ghostty_surface_t` | No |
| [Roost](https://github.com/charliek/roost) | `e49d9d2d` | MIT | Rust/iced terminal, `roost-vt` wrapper over libghostty-vt | No |
| [Blueshell](https://github.com/tuna-os/blueshell) | `0234dde6e` (ptyxis-port) | MIT core, GPL agent | Fork of the Ghostty GTK application | No |

## Findings that change the plan

1. **pyghostty is not the binding to build on.** The 0.1.4 wheel bundles a pre-1.0 development build
   (`0.1.0-dev`, from a Ghostty git revision, Zig 0.16), not the stable 1.0 ABI; wheels exist for Linux
   and macOS only (no Windows); it adds cffi. Its own wrapper (`core.py`) is 177 lines over raw cffi.
2. **PrettyMux is not upstream Ghostty.** `ghostty_surface_take_frame()` / `ghostty_surface_frame_s`
   are not in upstream `include/ghostty.h`; its PKGBUILD builds `git+https://github.com/patcito/ghostty.git#commit=bd604e89…`.
   It links the full internal `libghostty.so`, which owns its own GL context and the shell, and every
   widget hangs off a global `ghostty_app_t`. GPL-3.0-only. **Reference for GObject lifecycle and
   controller wiring only; no code.**
3. **tilix2 has already solved most of the drawing glue** with the public render-state API, under a
   licence that allows reuse. Its renderer techniques are the starting point (table below), adapted
   from Python to C.
4. **ConPTY constrains the input path on Windows (verified).** ConPTY forwards a program's kitty keyboard
   request (`CSI > 1 u`) to the terminal, but does not parse kitty-encoded keys coming back:
   `CSI 99;5u` reached cmd.exe as literal text instead of Ctrl+C. A widget that uses libghostty's key
   encoder as-is will break Escape/Ctrl/Alt for programs that ask for kitty mode **whenever the transport
   is ConPTY**. The widget needs a "legacy keyboard only" property the embedder sets for such transports.
5. **OSC 8 survives ConPTY (verified):** a link printed by PowerShell under cmd.exe reads back from exactly
   the linked cells via `ghostty_grid_ref_hyperlink_uri`.

## Feature map

Legend — **Use**: call the libghostty-vt API, write no protocol code. **Port**: re-implement the cited
technique in C (licence permits, attribute it). **Study**: design reference only (licence or language).
**New**: nothing to reuse; justified in the last column.

### Terminal core

| Feature | Owner | API / file | Decision | Remaining glue |
|---|---|---|---|---|
| VT parsing, screens, alt screen, scrollback, reflow | libghostty-vt | `ghostty_terminal_vt_write`, `_resize` | **Use** | none |
| Scrollback limits | libghostty-vt | `OPT_SCROLLBACK_MAX_BYTES/LINES` | **Use** | Byte limit defaults to one page (~10 KB): set it, or history is tiny (verified). Pruning is by whole page (verified: a 50-line limit dropped history from 2211 rows to 1 at 20 columns) |
| ConPTY resize behaviour | libghostty-vt | `OPT_RESIZE_PULL_SCROLLBACK = false` | **Use** | Property on the widget; embedder sets it for ConPTY (verified against conhost repaints) |
| Replies (DA, DSR, mode reports) | libghostty-vt | `OPT_WRITE_PTY`; `OPT_DEVICE_ATTRIBUTES` returning false = library default | **Use** | Emit as a signal to the caller's transport; never write back from inside the callback |
| Title, bell, pwd, progress, notifications | libghostty-vt | `OPT_TITLE_CHANGED`, `OPT_BELL`, `OPT_PWD_CHANGED`, `OPT_PROGRESS_REPORT`, `OPT_DESKTOP_NOTIFICATION` | **Use** | GObject properties/signals |
| Full reset | libghostty-vt | `ghostty_terminal_reset` | **Use** | RIS **clears history** (verified); "reset keeping history" needs a sequence (SSH Pilot sends DECSTR + mode resets) |
| Modes (DECCKM, bracketed paste, focus, mouse) | libghostty-vt | `DATA_MODE` with `ghostty_mode_new(n, false)` | **Use** | `DATA_MOUSE_TRACKING` is a **bool**, not the mode (verified); read modes 9/1000/1002/1003 |
| Synchronized output (2026) | libghostty-vt | `OPT_RENDER_HOLD` | **Use** | Capture the frame when the hold starts; 1 s timeout (rendering guide) |
| Selection, word/line selection | libghostty-vt | `ghostty_terminal_select_*`, `OPT_SELECTION`, render-state row selection | **Use** | Gesture → selection calls; tilix2 `_press`/`_extend`/`select` |
| Search | libghostty-vt | `ghostty_search_*` | **Use** | Literal and ASCII case-insensitive only; regex needs our own pass over formatter text |
| Text out (copy, save, HTML) | libghostty-vt | `ghostty_formatter_*` (plain, VT, HTML) | **Use** | — |
| Paste safety, bracketed paste | libghostty-vt | `ghostty_paste_encode`, `ghostty_paste_is_safe` | **Use** | Confirmation UI belongs to the embedder |
| Hyperlinks (OSC 8) | libghostty-vt | `ghostty_grid_ref_hyperlink_uri` | **Use** | Pointer → screen point; scheme policy on activation |
| Plain-text URL detection | — | — | **New** | Small regex over row text (libghostty has none); SSH Pilot's `url_at` pattern |
| Kitty graphics | libghostty-vt | `ghostty_kitty_graphics_*`, placement render info | **Use** | Texture cache per image id + generation; tilix2 `_images` |
| Scroll counting for a pinned scrolled-back view | libghostty-vt | tracked grid ref at the active top | **Use** | Exact per write; lost (has_value false) when a single write prunes its page — then the viewed rows are gone too (verified) |

### Drawing (GTK)

| Feature | Owner | Where | Decision | Remaining glue |
|---|---|---|---|---|
| Frame snapshot, dirty rows, row ids | libghostty-vt | render state; `ROW_DATA_DIRTY`, `ROW_DATA_ID` | **Use** | Cache per row id; rows are all dirty after a viewport scroll |
| Bulk row read | libghostty-vt | `ROW_DATA_CELLS_RAW` + `ghostty_type_json` | **Use** (FFI callers) | In C, per-cell `ghostty_render_state_row_cells_get` is cheap; bulk read matters for Python (SSH Pilot) |
| Runs of same-styled cells | tilix2 `_build_row` | tilix2.py 854–920 | **Port** | Merge key = (fg, bold, italic, decorations) |
| Exact one-cell glyph advance | tilix2 `_grid_attrs` (set in `set_font`) | one Pango letter-spacing attribute = cell width − advance of `M` | **Port** | Prevents run drift |
| Wide cells (CJK, emoji) exactly two cells | tilix2 | scale factor per wide run | **Port** | — |
| Box drawing and block elements on the grid | tilix2 `draw_box` | procedural drawing, not the font | **Port** | Gap-free TUI borders |
| Pango layout cache, dirty rows only | tilix2 `_rowcache` | — | **Port** | **Required on Windows**: Pango with CJK/Greek/box text costs 59 ms per 200×60 relayout on Windows vs 13 ms ASCII (verified, PangoCairoWin32FontMap); Linux 10–13 ms |
| Background spans, selection inversion, cursor styles | tilix2 `_draw`, `_draw_cursor` | — | **Port** | — |
| Image layers (below bg / below text / above text) | tilix2 `_draw_images` | — | **Port** | — |
| Snapshot vs Cairo | — | — | **New** | tilix2 uses `Gtk.DrawingArea` + Cairo; a C widget should use `GtkWidget.snapshot` + `gtk_snapshot_append_layout`, so GSK can use the GPU. Measure before choosing; on a GPU-less VM GTK falls back to `CairoRenderer` |
| GPU glyph atlas | Kwi `GlyphAtlas.cpp` | LGPL, Qt | **Study** | Only if measurements demand it |

### Input

| Feature | Owner | Where | Decision | Remaining glue |
|---|---|---|---|---|
| Key encoding (legacy, kitty) | libghostty-vt | `ghostty_key_encoder_*`, `_setopt_from_terminal` | **Use** | Plus a **legacy-only** property for ConPTY transports (finding 4) |
| GDK keyval → `GhosttyKey` table | tilix2 `KEYMAP`, `base_keyval`, `ghostty_mods` | tilix2.py 43–90 | **Port** | Platform checks: Windows AltGr arrives as Ctrl+Alt (SSH Pilot handles it in `_on_key_pressed`) |
| IME, dead keys, compose | GTK `GtkIMMulticontext` | tilix2 `Win._im_commit`; PrettyMux (study) | **Port** (tilix2) | Preedit drawing at the cursor and cursor-location reporting are not in tilix2 |
| Mouse reporting | libghostty-vt | `ghostty_mouse_encoder_*` | **Use** | Gestures → events; Shift bypass for selection (tilix2 `_mouse_to_app`) |
| Focus reports | libghostty-vt | `ghostty_focus_encode` | **Use** | — |
| Wheel in alternate screen (mode 1007) | libghostty-vt mode + encoder | — | **Use** | — |

### Transport and process (outside the widget)

| Feature | Owner | Where | Decision | Remaining glue |
|---|---|---|---|---|
| Caller-owned byte stream | — | — | **New** | `feed(GBytes)` in, `input`/`reply` signals out: the core API |
| Write backpressure | tilix2 | `GLib.io_add_watch(IO_OUT)`, 488–503 | **Port** into the optional PTY adapter | — |
| POSIX PTY | tilix2 `_start_shell`; Roost `pty.rs` | — | **Port** (tilix2) | Optional adapter, not in the widget |
| Windows ConPTY | SSH Pilot `platform/windows/conpty.py` + `local_shell_pty.py` (verified); TildaZ (AGPL, study) | — | **Port** from SSH Pilot (relicensed, see note) | Optional adapter |

### Library, platform, maintenance

| Feature | Owner | Where | Decision | Remaining glue |
|---|---|---|---|---|
| GObject widget lifecycle, controllers | PrettyMux `ghostty_terminal.c` | GPL | **Study** | Original code |
| Wrapper decomposition (render state, encoders, selection, tracked refs) | Roost `crates/roost-vt` | MIT, Rust | **Study** | Mirror the module split in C |
| GIR / typelib | — | — | **New** | `gnome.generate_gir()` |
| Building libghostty-vt for Windows | SSH Pilot `packaging/windows/libghostty-vt/build.py` | pinned Zig + release, offline | **Port** (relicensed, see note) | Verified: 2.5 MB DLL importing only system DLLs, loads in python.org Python next to gvsbuild GTK |
| Upstream tracking | Blueshell `UPSTREAM_SYNC.md` | — | **Study** | Only needed if we ever patch Ghostty; the stable ABI avoids that |
| Accessibility | Ghostty GTK; Kwi `TerminalAccessible.cpp` (LGPL) | — | **Study** | `GtkAccessibleText` (GTK ≥ 4.14) from formatter text; not in tilix2 |

## Measured numbers carried forward

All on the same libghostty-vt 1.0.0 release; Windows numbers are a VirtualBox Windows 10 VM without a GPU.

| Measurement | Result |
|---|---|
| Build (Linux host) | 6.5 min native; 8.5 min cross-compiled for `x86_64-windows-gnu` |
| Raw parse through ctypes, Windows | 47.5 MB/s (libvterm model 3.6, pyte 0.2) |
| SSH Pilot engine, Windows, 1.5 MB fixtures | 30–65 MB/s plain/SGR vs libvterm 3–11 |
| Feed 4 KiB + read all rows, 120×40, Windows | median 3–6 ms, comparable to libvterm |
| Pango relayout of a full 200×60 screen | Linux 10–13 ms; Windows 13 ms ASCII, 59 ms mixed scripts |
| GTK on the VM | `CairoRenderer`, ~4 fps for a Python full-screen redraw: VM artefact, real Windows hardware untested |

**Licence note on SSH Pilot code.** SSH Pilot is GPL-3.0. On 2026-11-15 its author, who wrote every
commit to the files cited above, relicensed that code for gtkghostty under gtkghostty's licence,
LGPL-2.1-or-later (recorded in `NOTICE`). Rows marked "if relicensed" can therefore be ported.

## Gaps no reference covers

- Preedit (IME composition) drawn at the cursor and the IME cursor rectangle.
- `GtkAccessibleText` for a custom-drawn terminal.
- A ConPTY-safe keyboard mode (finding 4).
- GIR packaging and a byte-stream API independent of any PTY.
- Windows and macOS GTK verification on real hardware.
