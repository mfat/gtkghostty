#!/usr/bin/env python3
"""GtkGhosttyTerminal with a program in a POSIX PTY (Linux, macOS).

The widget owns no process: this demo opens the PTY, feeds the program's
output to the widget and writes the widget's input and replies back.

    examples/pty_demo.py                 # $SHELL
    examples/pty_demo.py htop            # any command
    examples/pty_demo.py --fixture FILE  # just render recorded bytes, no process
"""

from __future__ import annotations

import os
import struct
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkGhostty", "1")
from gi.repository import GLib, Gtk, GtkGhostty  # noqa: E402


def run_fixture(term: GtkGhostty.Terminal, path: str) -> None:
    with open(path, "rb") as handle:
        term.feed_data(handle.read())


def run_program(term: GtkGhostty.Terminal, argv: list[str], app: Gtk.Application) -> None:
    import fcntl  # POSIX only; --fixture runs anywhere
    import pty
    import termios

    pid, master = pty.fork()
    if pid == 0:  # child
        os.environ["TERM"] = "xterm-256color"
        os.execvp(argv[0], argv)

    def write_all(data: bytes) -> None:
        view = memoryview(data)
        while view:
            try:
                written = os.write(master, view)
            except BlockingIOError:
                continue
            view = view[written:]

    term.connect("input", lambda _t, data: write_all(data.get_data()))
    term.connect("reply", lambda _t, data: write_all(data.get_data()))

    def resize(_t, columns, rows, cell_width, cell_height):
        size = struct.pack("HHHH", rows, columns, columns * cell_width, rows * cell_height)
        fcntl.ioctl(master, termios.TIOCSWINSZ, size)

    term.connect("size-changed", resize)
    resize(term, term.get_columns(), term.get_rows(), 0, 0)

    def readable(fd, condition):
        try:
            data = os.read(fd, 65536)
        except OSError:
            data = b""
        if not data:
            app.quit()
            return GLib.SOURCE_REMOVE
        term.feed_data(data)
        return GLib.SOURCE_CONTINUE

    GLib.unix_fd_add_full(GLib.PRIORITY_DEFAULT, master, GLib.IOCondition.IN | GLib.IOCondition.HUP, readable)
    term.connect("notify::title", lambda t, _p: term.get_root().set_title(t.get_title() or "gtkghostty"))


def main() -> None:
    args = sys.argv[1:]
    app = Gtk.Application(application_id=None)

    def activate(app):
        window = Gtk.ApplicationWindow(application=app, title="gtkghostty")
        window.set_default_size(900, 560)
        term = GtkGhostty.Terminal()
        window.set_child(term)
        window.present()
        term.grab_focus()
        if args[:1] == ["--fixture"]:
            run_fixture(term, args[1])
        else:
            run_program(term, args or [os.environ.get("SHELL", "/bin/sh")], app)

    app.connect("activate", activate)
    app.run([])


if __name__ == "__main__":
    main()
