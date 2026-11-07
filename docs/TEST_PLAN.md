# Test plan — extraction-first changes

The existing functional terminal test matrix below remains applicable **after** selection of extraction (A) or independent renderer (B). Before either, test the actual source-level assumptions.

## Phase 0 extraction acceptance

| Experiment | Required proof | Not sufficient |
|---|---|---|
| E0 upstream baseline | Exact pinned Ghostty GTK version builds/runs with recorded toolchain and deps | README or prior screenshot |
| E1 standalone host | Real `GhosttySurface` instantiated outside Ghostty's original application entrypoint, drawing and accepting input | Widget class compiles in original Ghostty |
| E2 external transport | Feed raw output and receive input/replies/resize without the widget owning a shell; reliable teardown | Shell hard-coded in core |
| E3 public bindings | Independent GTK C host and `gi.repository` Python sample load usable widget | A Zig-only internal GObject definition |
| E4 platform plan | Linux Wayland/X11 smoke and tested Windows/macOS render/interoperability prototypes or documented blockers | Assuming DMA-BUF works across GDK backends |
| Maintainability | Count upstream files/patches, binary footprint and needed internal APIs | Licensing alone |

**Fail-fast rule:** no claims of a distributable library or cross-platform compatibility from a Linux-only internal widget demonstration. Document GO/NO-GO against [EXTRACTION_FEASIBILITY.md](EXTRACTION_FEASIBILITY.md) before writing a replacement renderer.

## Functional and quality tests (for both paths)
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
