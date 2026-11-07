# Cross-platform GTK4 terminal widget powered by libghostty-vt

**Engineering starter kit — research snapshot: 2026-11-07**

**Status:** architecture, source inventory, reproducible reference checkout tooling, risk assessment, and milestone plan. **Not** a compiled widget. This pack deliberately does not redistribute third-party project code or vendored libraries.

## Purpose

Build an independent, embeddable, native GTK4 terminal widget for Linux, Windows and macOS. Expose it through a stable C/GObject API and GObject Introspection for Python/PyGObject. Integrate with SSH Pilot only after a standalone component passes platform tests.

## Read in this order

1. [ARCHITECTURE.md](docs/ARCHITECTURE.md) — design decision and proposed API.
2. [SOURCE_MAP.md](docs/SOURCE_MAP.md) — exact existing pieces and which ones to reuse vs study.
3. [BOOTSTRAP.md](docs/BOOTSTRAP.md) — official libghostty 1.0.0 setup, OS prerequisites and research reference checkout.
4. [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) — phased work, acceptance gates and issue breakdown.
5. [TEST_PLAN.md](docs/TEST_PLAN.md) — cross-platform tests, regressions, benchmarks.
6. [SECURITY_AND_LICENSING.md](docs/SECURITY_AND_LICENSING.md) — terminal effects policy, I/O lifecycle, license guardrails.
7. [sources.lock.json](sources.lock.json) — repository SHA pins verified through the public GitHub API.

## Fundamental architecture

```text
App (SSH Pilot or any Gtk4 app) [Python, C, Rust, ...]
    | GObject Introspection (GtkTermKit-1.0.typelib)
    v
GtkTermKit.TerminalView : GtkWidget    <-- rendering, keyboard, IME, selection, accessibility
    |                                   <-- emits input-bytes; receives feed(output-bytes)
    v
GtkTermKit.TerminalModel / libghostty-vt 1.0.0  <-- VT parsing, screen, input encoding, selection, search, RenderState
    ^
    | independent bidirectional session adapter (optional)
    +--- POSIX PTY (Linux / macOS)
    +--- Windows ConPTY (Windows 10 1809+)
    +--- caller-provided input/output transport (SSH app integration)
```

**Design invariant:** the widget never unilaterally owns a shell or SSH process. Session lifecycle is an optional adapter with an explicit owner; it must not be required just to render and interact with a terminal stream.

## First green milestone

An isolated GTK4 demo runs on **Windows and Linux** with the same C widget, shows ANSI colors and Unicode from a real shell, sends input, handles resize, and is importable via `gi.repository` from Python. macOS runs before a beta release. Do not delete VTE or PyXtermJS in SSH Pilot until this passes an explicit parity suite.

## Upstream must-read

- [Libghostty 1.0 announcement (2026-11-06)](https://mitchellh.com/writing/libghostty-1-0)
- [Official libghostty-vt installation guide](https://lib.ghostty.org/vt/installing.html)
- [Official Your First Terminal](https://lib.ghostty.org/vt/first-terminal.html)
- [Official Rendering guide](https://lib.ghostty.org/vt/guide-rendering.html)
- [Official Effects guide](https://lib.ghostty.org/vt/guide-effects.html)
- [Official examples index](https://lib.ghostty.org/vt/example-programs.html)

Reference source commits are pinned separately; upstream may have changed since this snapshot.
