# gtkghostty — reusable GTK4 terminal widget

**Status: design decided, no widget code yet.** The widget will be a C/GObject GTK4 library on the public **libghostty-vt 1.0** API ([ADR 0002](docs/ARCHITECTURE_DECISION.md)); which existing project owns each feature is mapped in the [upstream feature audit](docs/UPSTREAM_FEATURE_AUDIT.md). The engine side is already proven in SSH Pilot, which runs libghostty-vt 1.0 on Windows.

Goal: an independent GTK4 terminal component usable from native GObject applications and PyGObject, including SSH Pilot. Target platforms are Linux, Windows, and macOS. The widget must support a caller-provided terminal byte stream; launching or owning a process must remain optional.

## Earlier plan: why extraction was considered first (superseded by ADR 0002)

**Ghostty already ships a mature GTK4 widget, `GhosttySurface`.** Reimplementing its renderer and input layer before examining extraction would duplicate existing work. However, Ghostty does *not* distribute that widget as an independently supported library: it depends on Ghostty's internal `CoreSurface`, `GhosttyApplication`, renderer and configuration. The current GTK rendering path is a dedicated `GhosttyRenderSurface` that presents DMA-BUF textures, not the older `Gtk.GLArea` path.

**Our first milestone is an extraction feasibility experiment, not a new renderer.** See [EXTRACTION_FEASIBILITY.md](docs/EXTRACTION_FEASIBILITY.md) and [ADR 0001](docs/ADR-0001-extraction-first.md).

## Decision tree

1. **Path A — reuse/extract Ghostty's GTK frontend (preferred to investigate):** build an isolated GTK host that instantiates `GhosttySurface`, characterize its transitive dependencies, decouple global application assumptions and test an external byte-stream contract.
2. **Decision gate:** proceed with extraction only if the resulting component can be independently packaged, embedded, introspected, maintained, and made cross-platform without effectively carrying an entire Ghostty app fork.
3. **Path B — build a native GTK/GObject widget on libghostty-vt 1.0 (fallback):** if Path A fails the gate, adopt the original render-state design from the archived research with references to Forgetty, Kwi and Ghostling. This duplicates rendering work but gives us a narrow, stable library boundary.
4. **SSH Pilot integration is a later, separate task:** retain its existing terminal backends until parity tests pass.

## Building (first milestone)

Needs GTK ≥ 4.14, Meson, a C compiler, GObject Introspection and libghostty-vt 1.0
(build it from the official release with Zig 0.17, see [BOOTSTRAP.md](docs/BOOTSTRAP.md)).

```sh
PKG_CONFIG_PATH=/path/to/libghostty-vt/lib/pkgconfig meson setup _build
ninja -C _build
LIBGHOSTTY_VT_LIBDIR=/path/to/libghostty-vt/lib xvfb-run -a tests/run.sh _build
GI_TYPELIB_PATH=_build/src LD_LIBRARY_PATH=_build/src:/path/to/libghostty-vt/lib \
  python3 examples/pty_demo.py htop          # or --fixture tests/fixtures/showcase.vt
```

Windows (MSVC + gvsbuild GTK): see [docs/WINDOWS.md](docs/WINDOWS.md).

From Python: `gi.require_version("GtkGhostty", "1"); from gi.repository import GtkGhostty`.
The widget takes program output with `feed()` and emits `input`, `reply`, `size-changed`,
`bell` and `notify::title`; it never starts a process. It is a `GtkScrollable` (put it in a
`GtkScrolledWindow` for a scrollbar over the history), selects with libghostty's gesture rules
(drag, double-click word, triple-click line, edge autoscroll; the selection goes to the primary
selection, middle-click pastes it), reports the mouse to programs that ask (Shift selects
anyway) and offers `copy_clipboard()`/`paste_clipboard()` for the application's own shortcuts.

## Current documentation

- [ADR 0002: C widget on libghostty-vt 1.0 (current decision)](docs/ARCHITECTURE_DECISION.md)
- [Upstream feature audit: who already owns each feature](docs/UPSTREAM_FEATURE_AUDIT.md)
- [Extraction feasibility: audited upstream files and concrete spike](docs/EXTRACTION_FEASIBILITY.md)
- [ADR 0001: extraction-first decision (superseded)](docs/ADR-0001-extraction-first.md)
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
