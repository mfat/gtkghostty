# Feasibility assessment: extract GhosttySurface before rebuilding a widget

**Assessment date: 2026-11-07. Source inspection only; no extraction binary or runtime validation.**

## The finding

Ghostty already has **two relevant GTK4 GObject widgets** in the upstream *application* source:

| Component | Source | Observed responsibility |
|---|---|---|
| `GhosttySurface` | [`src/apprt/gtk/class/surface.zig`](https://github.com/ghostty-org/ghostty/blob/main/src/apprt/gtk/class/surface.zig) | `adw.Bin` and `GtkScrollable`-implementing terminal container, input/IME/events/clipboard integration and access to `CoreSurface` |
| `GhosttyRenderSurface` | [`src/apprt/gtk/class/render_surface.zig`](https://github.com/ghostty-org/ghostty/blob/main/src/apprt/gtk/class/render_surface.zig) | `GtkWidget` snapshot host receiving render frames/textures; current path consumes DMA-BUFs |
| `CoreSurface` | [`src/Surface.zig`](https://github.com/ghostty-org/ghostty/blob/main/src/Surface.zig) | Ghostty's application-integrated terminal core |
| GTK application singleton | [`src/apprt/gtk/class/application.zig`](https://github.com/ghostty-org/ghostty/blob/main/src/apprt/gtk/class/application.zig) | Application/global runtime/configuration/event orchestration |

**Do not mistake `GhosttySurface` for a widget provided by `libghostty-vt 1.0`.** That released library exposes a cross-platform VT engine and render state; it does not export Ghostty's full GTK frontend or GPU renderer.

## Source-level dependencies to audit

1. `GhosttySurface.new()` uses `Application.default().allocator()`; its GTK initialization falls back to `Application.default().getConfig()` when no config was supplied. Removing the application singleton requires a replacement for configuration, allocation, notifications and lifecycle.
2. `GhosttySurface` private state stores `CoreSurface` and the GTK runtime surface. Its renderer integration is not merely a call to the public `libghostty-vt` C API.
3. `GhosttyRenderSurface` imports Ghostty renderer internals, `CoreSurface`, `Dmabuf.zig` and GDK texture state.
4. The renderer source explicitly says it formerly used `Gtk.GLArea` and moved to a custom snapshot widget with a render thread/DMA-BUF queue. Proposals that assume current `Gtk.GLArea` rendering are outdated.
5. Ghostty GTK device setup handles Wayland/X11 EGL display paths. Do **not** infer that its Linux GPU sharing path works on GTK Windows/macOS.
6. A GObject type declaration alone does **not** make the widget a distributed shared library, public C ABI, GObject Introspection namespace or PyGObject package.

## Investigation experiments and evidence to record

### E0 — reproducible upstream baseline

- Check out the pinned `ghostty-app` commit from `sources.lock.json` into ignored `references/ghostty-app`.
- Build Ghostty's GTK frontend on a supported Linux environment with matching upstream toolchain and dependencies.
- Capture compiler/Zig version, build flags, platform, full transitive dependency list, artifact sizes and test output.
- **Exit:** baseline builds/runs independently; if not, stop and repair reproducibility before extraction.

### E1 — standalone GTK host (critical test)

- In a disposable branch/prototype outside the original app entrypoint, instantiate the real `GhosttySurface` in a minimal GTK4/libadwaita window.
- Enumerate required initialization symbols, global singletons, templates, GResource bundles, config and render-thread initialization.
- Classify each dependency as **essential reusable core**, **replaceable adapter**, **GUI-app-only**, or **platform-specific**.
- **Exit:** a real shell appears, accepts input, resizes and exits cleanly **without launching Ghostty's original Application/Window**. If not, record exact dependency blockers.

### E2 — detach process/transport from the widget

- Replace implicit process spawning with optional caller-owned session plumbing and a byte-stream interface.
- Ensure the widget receives output bytes and emits input/replies/resize requests with documented ownership, ordering and thread rules.
- Verify terminal protocol replies go back to transport; test attaching/detaching a view without terminating an external session.
- **Exit:** demo renders a scripted VT fixture without spawning a shell, plus one shell through a separate adapter.

### E3 — independent library and Python boundary

- Export a deliberately narrow C/GObject API with stable namespace, errors, signals, ownership rules and a deterministic shutdown path.
- Generate GIR/typelib and demonstrate `from gi.repository import ...` with a real embeddable instance.
- Validate public objects are not dependent on a default Ghostty application singleton; test multiple simultaneous instances.
- **Exit:** standalone GTK app and Python app can embed without importing or starting Ghostty application runtime.

### E4 — cross-platform feasibility (not presumed solved)

- Linux: Wayland and X11 behavior, DMA-BUF/GDK support and fallback behavior.
- Windows: assess GTK backend, texture interop/fallback, font, IME and ConPTY, *without assuming a direct DMA-BUF port*.
- macOS: assess GTK/GDK presentation, font/IME and POSIX PTY.
- **Exit:** minimal independent render/input demo on the target platform or a written, implementable backend plan with identified blockers.

## GO / NO-GO decision sheet

| Question | GO evidence | NO-GO evidence |
|---|---|---|
| Is extraction truly independent? | Small reusable core + no global application object required at runtime | Hidden, pervasive application-coupling or effective full-app fork |
| Can we expose safe public ABI/GIR? | Working independent native and PyGObject demos | Requires app-private Zig types in the public ABI |
| Can the renderer be portable? | Linux works; Windows/macOS backend designs have tested prototypes | Linux DMA-BUF presentation is inseparable from core |
| Can a third-party app control I/O? | Source/sink, resize and lifecycle independent | Core always owns launcher/session/window |
| Is ongoing maintenance sustainable? | Clear upstream sync strategy and limited patch surface | Constant cherry-picking of internal Ghostty files |
| Is licensing/distribution understood? | License audit, notices, dependencies, compatible link/build plan | Unresolved source provenance or binary distribution conditions |

If the initial extraction is demonstrably too expensive, *stop* and invoke Path B: libghostty-vt + independent GTK frontend. A no-go is a useful outcome, not project failure.

## Upstream files worth reading next

- [GTK surface](https://github.com/ghostty-org/ghostty/blob/main/src/apprt/gtk/class/surface.zig)
- [GTK render surface](https://github.com/ghostty-org/ghostty/blob/main/src/apprt/gtk/class/render_surface.zig)
- [Core surface](https://github.com/ghostty-org/ghostty/blob/main/src/Surface.zig)
- [GTK application](https://github.com/ghostty-org/ghostty/blob/main/src/apprt/gtk/class/application.zig)
- [GTK runtime surface adapter](https://github.com/ghostty-org/ghostty/blob/main/src/apprt/gtk/Surface.zig)
- [libghostty-vt docs](https://lib.ghostty.org/vt/) — fallback engine interface

**Caveat:** Source references above link to live upstream `main`; use the pinned `ghostty-app` SHA for reproducible development. This document contains design hypotheses that must be experimentally verified.
