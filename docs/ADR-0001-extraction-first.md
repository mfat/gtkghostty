# ADR 0001 — Investigate extracting Ghostty's existing GTK4 widget first

- **Status:** Accepted for the *research/prototype sequence*, not a verdict that extraction will succeed.
- **Date:** 2026-11-07
- **Scope:** Standalone gtkghostty project. No changes to SSH Pilot yet.

## Context

The first plan assumed we needed to implement a native GTK renderer around `libghostty-vt 1.0`. We subsequently confirmed the full Ghostty Linux application has an existing `GhosttySurface` GObject widget with input handling and a companion `GhosttyRenderSurface` drawing widget.

These are not part of the stable `libghostty-vt` distribution. They are application-internal Zig classes intertwined with `CoreSurface`, Ghostty's own application singleton, configuration, renderer, terminal I/O and GTK platform setup. The current compositor path uses DMA-BUF textures; `Gtk.GLArea` is a *historical* implementation, not the current default.

## Decision

**Prioritize a limited, measurable extraction spike before writing replacement rendering or input code.** Preserve the previous libghostty-vt-only architecture as a documented fallback.

Do not conflate: (a) extracting the full Ghostty `GhosttySurface` + core, and (b) building a GTK frontend over the standalone `libghostty-vt` ABI. Both may be valid, but they have different dependency, packaging and maintenance profiles.

### Path A: extraction

Try an independent GTK4 demonstration that instantiates the actual widget without the original Ghostty application window. Inventory and isolate dependencies; add an adapter for caller-managed byte streams; introduce a stable GObject boundary and GI bindings if possible.

**Go only if:** it can ship as a separate library, preserve correct input/renderer behavior, avoid a hidden global application requirement, provide explicit input/output/session ownership, and offer a credible Linux/Windows/macOS strategy at sustainable maintenance cost. Prove each gate by build/tests, not assumption.

### Path B: independent libghostty-vt frontend

If Path A fails, build a narrow GTK4/GObject library over `libghostty-vt 1.0.0`. Start with a CPU/Pango or GSK renderer, using Forgetty and Kwi as engineering references. This requires replicating visual, accessibility and input integration but avoids coupling to Ghostty's internal application runtime.

## Non-goals for the extraction spike

- Shipping a production library, claiming GObject Introspection compatibility, or replacing SSH Pilot backends.
- Porting the Linux-specific DMA-BUF presentation wholesale to Windows or macOS without a validated backend.
- Treating Ghostty upstream internal API as stable, or vendoring third-party code without license and provenance reviews.

## Decision evidence

- [GhosttySurface source](https://github.com/ghostty-org/ghostty/blob/main/src/apprt/gtk/class/surface.zig): `adw.Bin`/`gtk.Scrollable` GObject; constructor and init depend on `Application.default()`; `CoreSurface` reference.
- [RenderSurface source](https://github.com/ghostty-org/ghostty/blob/main/src/apprt/gtk/class/render_surface.zig): GTK widget using DMA-BUF-backed frame presentation and internal renderer/core state.
- [Ghostty core](https://github.com/ghostty-org/ghostty/blob/main/src/Surface.zig).
- [libghostty-vt 1.0](https://mitchellh.com/writing/libghostty-1-0): stable VT engine *not* an embeddable GTK widget.

## Revisit

After the documented Linux extraction experiment and platform smoke checks, record measured build size, transitive dependencies, global-state assumptions, complexity, CI results and licensing obligations. Mark Path A GO/NO-GO before committing to the full product implementation.
