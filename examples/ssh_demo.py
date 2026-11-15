#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2026 mFat <newmfat@gmail.com> and the gtkghostty contributors
"""GtkGhosttyTerminal on a byte stream it does not own: an SSH channel.

The widget never needs a local process. Whatever carries the bytes (SSH, a
serial port, a socket, a container's attach stream) is wired the same way:

    stream output  -> terminal.feed_data()
    "input"        -> write to the stream (what the user types, pastes, clicks)
    "reply"        -> write to the stream (answers to the program's queries)
    "size-changed" -> tell the far end the new size

This uses paramiko (pip install paramiko). Authentication tries your SSH
agent and default keys, then asks for a password on the console. Host keys
come from ~/.ssh/known_hosts; an unknown host is refused, as ssh would.

    examples/ssh_demo.py user@host [-p PORT] [-i KEY]
"""

from __future__ import annotations

import argparse
import getpass
import os
import threading
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkGhostty", "1")
from gi.repository import GLib, Gtk, GtkGhostty  # noqa: E402

try:
    import paramiko
except ImportError:  # pragma: no cover - the example's only extra dependency
    raise SystemExit("this example needs paramiko: pip install paramiko") from None


def connect(target: str, port: int, key: str | None) -> paramiko.SSHClient:
    user, _, host = target.rpartition("@")
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    username = user or getpass.getuser()

    def login(password: str | None = None) -> None:
        client.connect(hostname=host, port=port, username=username, key_filename=key, password=password)

    try:
        login()
    except paramiko.AuthenticationException:  # (an SSHException too, so first)
        login(getpass.getpass(f"{username}@{host}'s password: "))
    except paramiko.BadHostKeyException as exc:
        raise SystemExit(f"host key for {host} changed: {exc}") from None
    except paramiko.SSHException as exc:
        if "known_hosts" not in str(exc):
            raise
        raise SystemExit(f"{host}:{port} is not in known_hosts; connect once with ssh to check its key") from None
    return client


def attach(term: GtkGhostty.Terminal, channel: paramiko.Channel,
           on_closed: Callable[[int], None]) -> None:
    """Wire the terminal to the channel in both directions."""

    def send(_term, data: GLib.Bytes) -> None:
        channel.sendall(data.get_data())

    term.connect("input", send)
    term.connect("reply", send)
    term.connect("size-changed", lambda _t, columns, rows, _w, _h: channel.resize_pty(columns, rows))

    def feed(chunk: bytes) -> bool:
        term.feed_data(chunk)
        return GLib.SOURCE_REMOVE

    def closed() -> bool:
        on_closed(channel.recv_exit_status())
        return GLib.SOURCE_REMOVE

    def reader() -> None:
        # paramiko blocks, so read on a thread and feed on the GTK thread.
        while True:
            data = channel.recv(65536)
            if not data:
                break
            GLib.idle_add(feed, data)
        GLib.idle_add(closed)

    threading.Thread(target=reader, daemon=True).start()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", help="[user@]host")
    parser.add_argument("-p", "--port", type=int, default=22)
    parser.add_argument("-i", "--identity", default=None)
    args = parser.parse_args()
    client = connect(args.target, args.port, args.identity)

    app = Gtk.Application(application_id=None)

    def activate(app):
        window = Gtk.ApplicationWindow(application=app, title=f"gtkghostty — {args.target}")
        window.set_default_size(900, 560)
        term = GtkGhostty.Terminal()
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(term)
        window.set_child(scrolled)
        window.present()
        term.grab_focus()
        channel = client.invoke_shell(
            term=os.environ.get("GTKGHOSTTY_TERM", "xterm-256color"),
            width=term.get_columns(), height=term.get_rows(),
        )
        attach(term, channel, lambda status: (print(f"remote shell exited ({status})"), app.quit()))
        term.connect("notify::title", lambda t, _p: window.set_title(t.get_title() or args.target))

    app.connect("activate", activate)
    try:
        app.run([])
    finally:
        client.close()


if __name__ == "__main__":
    main()
