# Implementation plan — verify extraction before building a renderer

**Current priority: Path A extraction feasibility.** This supersedes the earlier implementation ordering. Refer to [ADR 0001](ADR-0001-extraction-first.md) and [EXTRACTION_FEASIBILITY.md](EXTRACTION_FEASIBILITY.md).

## Phase 0 — baseline and extraction spike (MUST finish first)

- [ ] Check out the pinned `ghostty-app` source commit and build the existing GTK frontend on supported Linux.
- [ ] Trace every `GhosttySurface` / `GhosttyRenderSurface` / `CoreSurface` dependency and runtime initialization path (Zig, GTK, libadwaita, GResources, renderer).
- [ ] Build a **minimal standalone GTK4 host** that embeds the actual `GhosttySurface` without Ghostty's original `Application`/`Window`.
- [ ] Demonstrate typing, rendering, resizing, exit and cleanup. Capture build artifacts, dependency graph and crash logs.
- [ ] Attempt caller-provided PTY byte transport; verify protocol responses and view-detach ownership.
- [ ] Try a small public C/GObject wrapper + GIR import from PyGObject (or document exactly why impossible).
- [ ] Profile portability blockers (DMA-BUF vs GDK backend on Windows/macOS); specify and smoke-test alternatives.
- [ ] Record upstream-sync cost, license obligations, dependency footprint and decision evidence.

**Gate:** written **GO/NO-GO** for extraction, supported by runnable Linux demo/build log and a credible cross-platform strategy. **Do not start writing a replacement renderer until this gate is resolved.**

## Phase 1A — if extraction is GO: isolate and stabilize

- [ ] Package only required Ghostty GTK/core/renderer subset with documented upstream pin and patch list.
- [ ] Remove hard requirements on global Ghostty application singleton and original window; separate config and lifetime.
- [ ] Expose widget as embeddable GObject with explicit feed/input/resize and optional session adapter.
- [ ] Build GIR/typelib and run standalone native and Python demos.
- [ ] Implement tested frame transport for GTK Linux and working Windows/macOS strategy; add fallback where necessary.
- [ ] Maintain safe callbacks, permissions, accessibility and regression tests against upstream Ghostty behavior.

**Gate:** no hidden original-app runtime; no unstable app-private symbols escape the public ABI; GUI works in an unrelated GTK process.

## Phase 1B — if extraction is NO-GO: use libghostty-vt only

- [ ] Choose independent C/GObject + GTK4/Meson baseline and `libghostty-vt 1.0.0`.
- [ ] Implement model ownership, effects/replies, render-state snapshots and GTK renderer.
- [ ] Use Pango/GSK initially, then optimize measured hotspots; follow Ghostling, Forgetty, Kwi.
- [ ] Expose GIR + native signal API; validate process-independent byte input/output and resize.
- [ ] Preserve evidence explaining why Path A failed and which code was intentionally not ported.

**Gate:** Linux+Windows native GtkWidget displays VT fixtures and a local shell with no Python rendering loop.

## Phase 2 — input, sessions and accessibility (either path)

- [ ] GTK key mapping (including Kitty protocol, modifier sides, AltGr, function keys) and IME preedit/commit.
- [ ] View selection, scrollback, search, clipboard with security policy, bracketed/multiline paste.
- [ ] Optional POSIX PTY and ConPTY adapters; error propagation, EOF, cancellation, shutdown, resize.
- [ ] Accessibility semantics with `GtkAccessibleText` where supported.
- [ ] Mouse tracking, hyperlinks, alternate-screen behavior and title/bell/notification events.

**Gate:** normal shells, SSH, `vim`, `less` and `tmux` work with real keyboards and paste on Linux and Windows.

## Phase 3 — portability and reliability

- [ ] Windows and macOS native GTK graphical smoke, renderer/backend interop, font and scale/IME tests.
- [ ] High-output performance, long scrollback, multiple widget instances and redraw throttling.
- [ ] Kitty graphics as supported by chosen engine, layering, limits and fallback.
- [ ] Reproducible builds, cross-platform CI, packaging and security review.

**Gate:** test matrix in `TEST_PLAN.md` passes or limitations are explicitly recorded.

## Phase 4 — public release and later SSH Pilot integration

- [ ] Versioned C/GObject API, pkg-config, headers, GIR, typelib, demos, licenses and security policy.
- [ ] Third-party GTK4 application embeds and drives the widget without SSH Pilot dependencies.
- [ ] Implement optional SSH Pilot backend behind feature flag. Compare with VTE/PyXtermJS and retain fallbacks until parity is demonstrated.

## Initial engineering issues

1. `research: pin and build upstream Ghostty GTK baseline`
2. `research: graph GhosttySurface and renderer dependencies`
3. `spike: instantiate GhosttySurface from minimal GTK host`
4. `spike: decouple Application.default, config and UI resources`
5. `spike: independent stream, resize and lifecycle contract`
6. `spike: GObject export and PyGObject introspection`
7. `spike: test Linux render path and Windows/macOS backend feasibility`
8. `decision: record Path A GO/NO-GO with evidence`
9. `fallback: build libghostty-vt GTK model/renderer only if NO-GO`
10. `quality: input, accessibility, security and cross-platform parity`

No implementation has been performed as part of this document update.
