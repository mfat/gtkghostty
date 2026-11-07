# Security, licensing and release obligations

## Remote terminal output is untrusted

The terminal can process malicious or accidental escape sequences from a remote server. libghostty-vt is fuzz-tested, but callbacks that perform side effects are **your application's responsibility**.

- The documented callbacks execute synchronously inside VT writes, are non-reentrant, and shouldn't block. Copy borrowed memory and enqueue any reply or UI request.
- Register the PTY reply callback explicitly so interactive programs receive device status reports. Ensure there is bounded buffering and proper cancellation.
- Off by default for remote sessions: OSC 52 clipboard **read**. For clipboard **write**, add explicit user preference/permission mechanism; never silently bridge remote server to local clipboard.
- Treat `title`, working directory, hyperlinks, notifications, file paths, and image/file-loading requests as untrusted. Sanitize and bound displayed values; require user action for opening URIs. Do not allow host filesystem access through a Kitty image request by default.
- Require confirmation for potentially dangerous multiline paste; support bracketed paste correctly.
- Limit memory/CPU for high-volume output, escape callbacks, scrollback and graphics. Cancel or detach sessions without leaking workers, handles or child processes.

Sources: https://lib.ghostty.org/vt/guide-effects.html and https://lib.ghostty.org/vt/first-terminal.html

## Licensing review before copying code

| Repo/component | License evidence as inspected | Safe use guideline |
|---|---|---|
| libghostty-vt 1.0.0 | MIT; official dependency manifest | Link/build against 1.0.0; retain required notices |
| Ghostling | MIT in repo | Reuse illustrative integration code subject to MIT notices |
| Forgetty | MIT in LICENSE | Candidate GTK implementation reference/code with attribution |
| Kwi lib modules | README and per-file headers: LGPL-2.1-only OR LGPL-3.0-only OR KDE accepted | Possible adaptation under compatible conditions; inspect original notices before using source |
| Kwi full application | GPL variants in top-level CMake project | Don't confuse top-level app license with LGPL sublibraries |
| TildaZ | AGPL-3.0-or-later in LICENSE | Architecture/documentation reference; do not copy/port AGPL code unless ready to satisfy license obligations |
| mightty | README states MIT; third-party notices | Verify file and third-party notices before borrowing |
| Phantty | No license established in repo metadata | Reference only; don't copy until permissions clarified |
| pyghostty | Apache-2.0 per GitHub metadata | Optional Python experimentation only; retain license notices if reused |
| GTK/Pango/GLib etc. | Individual upstream licenses | Track versions, notices and linking obligations separately |

License evidence is a **research snapshot, not legal advice**. Even MIT-licensed source code requires preservation of copyright notices. A source rewrite may still be derivative; do not assume changing languages makes a copyleft requirement disappear. Develop your own GTK design with MIT-compatible references if a permissive public widget is the goal.

## Release hygiene

- Record SPDX IDs, copyright notices and commit SHAs for any copied code.
- Include `THIRD_PARTY_NOTICES.md` and machine-readable build manifest.
- Sign/hash downloadable binaries and publish reproducible build instructions.
- Verify `libghostty-vt` ABI version and required features rather than assuming new library versions always include optional features.
- Publish a security contact/reporting workflow and support policy.
