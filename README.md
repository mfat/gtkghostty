# gtkghostty — reusable GTK4 terminal widget

**Status: feasibility study and project documentation. No widget has yet been extracted, compiled, or tested.**

Goal: an independent GTK4 terminal component usable from native GObject applications and PyGObject, including SSH Pilot. Target platforms are Linux, Windows, and macOS. The widget must support a caller-provided terminal byte stream; launching or owning a process must remain optional.

## Why extraction first?

**Ghostty already ships a mature GTK4 widget, `GhosttySurface`.** Reimplementing its renderer and input layer before examining extraction would duplicate existing work. However, Ghostty does *not* distribute that widget as an independently supported library: it depends on Ghostty's internal `CoreSurface`, `GhosttyApplication`, renderer and configuration. The current GTK rendering path is a dedicated `GhosttyRenderSurface` that presents DMA-BUF textures, not the older `Gtk.GLArea` path.

**Our first milestone is an extraction feasibility experiment, not a new renderer.** See [EXTRACTION_FEASIBILITY.md](docs/EXTRACTION_FEASIBILITY.md) and [ADR 0001](docs/ADR-0001-extraction-first.md).

## Decision tree

1. **Path A — reuse/extract Ghostty's GTK frontend (preferred to investigate):** build an isolated GTK host that instantiates `GhosttySurface`, characterize its transitive dependencies, decouple global application assumptions and test an external byte-stream contract.
2. **Decision gate:** proceed with extraction only if the resulting component can be independently packaged, embedded, introspected, maintained, and made cross-platform without effectively carrying an entire Ghostty app fork.
3. **Path B — build a native GTK/GObject widget on libghostty-vt 1.0 (fallback):** if Path A fails the gate, adopt the original render-state design from the archived research with references to Forgetty, Kwi and Ghostling. This duplicates rendering work but gives us a narrow, stable library boundary.
4. **SSH Pilot integration is a later, separate task:** retain its existing terminal backends until parity tests pass.

## Current documentation

- [Extraction feasibility: audited upstream files and concrete spike](docs/EXTRACTION_FEASIBILITY.md)
- [ADR 0001: extraction-first decision](docs/ADR-0001-extraction-first.md)
- [Architecture and public API](docs/ARCHITECTURE.md)
- [Implementation plan and gates](docs/IMPLEMENTATION_PLAN.md)
- [Source map](docs/SOURCE_MAP.md)
- [Bootstrap and dependency collection](docs/BOOTSTRAP.md)
- [Test plan](docs/TEST_PLAN.md)
- [Security and licensing](docs/SECURITY_AND_LICENSING.md)
- [Pinned upstream references](sources.lock.json)
- [Original consolidated research snapshot (historical)](docs/PROJECT_BLUEPRINT.md)

## Verified upstream entry points

- [Ghostty GTK `GhosttySurface`](https://github.com/ghostty-org/ghostty/blob/main/src/apprt/gtk/class/surface.zig)
- [Ghostty GTK `GhosttyRenderSurface`](https://github.com/ghostty-org/ghostty/blob/main/src/apprt/gtk/class/render_surface.zig)
- [Ghostty core `Surface.zig`](https://github.com/ghostty-org/ghostty/blob/main/src/Surface.zig)
- [Ghostty GTK `Application`](https://github.com/ghostty-org/ghostty/blob/main/src/apprt/gtk/class/application.zig)
- [Official libghostty-vt](https://lib.ghostty.org/vt/)

This is a source-level assessment only. No extraction proof, binary builds or three-platform GUI tests have been completed.
