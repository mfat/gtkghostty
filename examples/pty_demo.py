#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2026 mFat <newmfat@gmail.com> and the gtkghostty contributors
"""GtkGhosttyTerminal running a program through GtkGhosttyPty (Linux, macOS, Windows).

The widget owns no process; GtkGhosttyPty starts the program on a pseudo
terminal (a POSIX PTY or a Windows pseudo console) and attach() wires the two.

    examples/pty_demo.py                 # $SHELL, or %ComSpec% on Windows
    examples/pty_demo.py htop            # any command
    examples/pty_demo.py --fixture FILE  # just render recorded bytes, no process
"""

from __future__ import annotations

import os
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkGhostty", "1")
from gi.repository import Gtk, GtkGhostty  # noqa: E402


def run_fixture(term: GtkGhostty.Terminal, path: str) -> None:
    with open(path, "rb") as handle:
        term.feed_data(handle.read())


def default_command() -> list[str]:
    if sys.platform == "win32":
        return [os.environ.get("ComSpec", "cmd.exe")]
    return [os.environ.get("SHELL", "/bin/sh")]


def run_program(term: GtkGhostty.Terminal, argv: list[str], app: Gtk.Application) -> GtkGhostty.Pty:
    env = [f"{key}={value}" for key, value in os.environ.items() if key != "TERM"]
    env.append("TERM=xterm-256color")
    pty = GtkGhostty.Pty.spawn(argv, env, None, term.get_columns(), term.get_rows())
    pty.attach(term)
    pty.connect("exited", lambda _p, _status: app.quit())
    term.connect("notify::title", lambda t, _p: t.get_root().set_title(t.get_title() or "gtkghostty"))
    return pty


def main() -> None:
    args = sys.argv[1:]
    app = Gtk.Application(application_id=None)

    def activate(app):
        window = Gtk.ApplicationWindow(application=app, title="gtkghostty")
        window.set_default_size(900, 560)
        term = GtkGhostty.Terminal()
        scrolled = Gtk.ScrolledWindow()  # GtkScrollable: the scrollbar follows the history
        scrolled.set_child(term)
        window.set_child(scrolled)
        # The widget binds no shortcuts; an application picks its own.
        shortcuts = Gtk.ShortcutController(scope=Gtk.ShortcutScope.MANAGED)
        shortcuts.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        for accel, method in (("<Control><Shift>c", term.copy_clipboard),
                              ("<Control><Shift>v", term.paste_clipboard)):
            shortcuts.add_shortcut(Gtk.Shortcut.new(
                Gtk.ShortcutTrigger.parse_string(accel),
                Gtk.CallbackAction.new(lambda *_a, m=method: (m(), True)[1])))
        window.add_controller(shortcuts)
        window.present()
        term.grab_focus()
        if args[:1] == ["--fixture"]:
            run_fixture(term, args[1])
        else:
            app.pty = run_program(term, args or default_command(), app)  # keep it alive

    app.connect("activate", activate)
    app.run([])


if __name__ == "__main__":
    main()
