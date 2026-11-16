# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2026 mFat <newmfat@gmail.com> and the gtkghostty contributors
"""GtkGhosttyPty: real programs on a pseudo terminal, attached to the widget."""

from __future__ import annotations

import os
import sys

import gi
import pytest

gi.require_version("Gtk", "4.0")
gi.require_version("GtkGhostty", "1")
from gi.repository import GLib, Gtk, GtkGhostty  # noqa: E402

Gtk.init()
WINDOWS = sys.platform == "win32"


def pump_until(predicate, seconds=10.0):
    context = GLib.MainContext.default()
    deadline = GLib.get_monotonic_time() + int(seconds * 1_000_000)
    while not predicate() and GLib.get_monotonic_time() < deadline:
        context.iteration(False)
    return predicate()


def shell(script_posix, script_windows):
    if WINDOWS:
        return [os.environ.get("ComSpec", "cmd.exe"), "/d", "/q", "/c", script_windows]
    return ["/bin/sh", "-c", script_posix]


def attached(argv, columns=60, rows=10):
    term = GtkGhostty.Terminal()
    term.set_grid_size(columns, rows)
    pty = GtkGhostty.Pty.spawn(argv, None, None, columns, rows)
    exits = []
    pty.connect("exited", lambda _p, status: exits.append(status))
    pty.attach(term)
    return term, pty, exits


def test_output_reaches_the_terminal_and_exit_comes_last():
    outputs = []
    term, pty, exits = attached(shell("printf 'hello from sh\\n'; exit 3", "echo hello from cmd& exit /b 3"))
    pty.connect("output", lambda _p, data: outputs.append((len(exits), data.get_data())))
    assert pty.get_pid() > 0 and pty.is_running()
    assert pump_until(lambda: exits)
    assert exits == [3]
    assert all(seen_exit == 0 for seen_exit, _ in outputs)  # no output after "exited"
    assert "hello from" in term.get_text()
    assert not pty.is_running()


def test_typed_input_reaches_the_program():
    term, pty, exits = attached(shell("read line; echo got:$line", "set /p line=& call echo got:%line%"))
    term.paste_text("abc\n" if not WINDOWS else "abc\r")
    assert pump_until(lambda: exits)
    assert "got:abc" in term.get_text()


def test_the_environment_reaches_the_program():
    env = [f"{key}={value}" for key, value in os.environ.items()] + ["GG_PROBE=über-42"]
    term = GtkGhostty.Terminal()
    term.set_grid_size(60, 10)
    pty = GtkGhostty.Pty.spawn(shell("echo probe:$GG_PROBE", "echo probe:%GG_PROBE%"), env, None, 60, 10)
    exits = []
    pty.connect("exited", lambda _p, status: exits.append(status))
    pty.attach(term)
    assert pump_until(lambda: exits)
    assert "probe:über-42" in term.get_text()


@pytest.mark.skipif(WINDOWS, reason="stty is POSIX")
def test_the_starting_size_reaches_the_program():
    # macOS resets a terminal's size on its first open: lost unless the
    # terminal side is opened before the size is set.
    term, pty, exits = attached(["/bin/sh", "-c", "stty size"], 60, 10)
    assert pump_until(lambda: exits)
    assert "10 60" in term.get_text()


@pytest.mark.skipif(WINDOWS, reason="stty is POSIX")
def test_resize_reaches_the_program():
    term, pty, exits = attached(["/bin/sh", "-c", "sleep 0.3; stty size"], 60, 10)
    term.set_grid_size(77, 13)
    assert pump_until(lambda: exits)
    assert "13 77" in term.get_text()


@pytest.mark.skipif(WINDOWS, reason="SIGHUP status is POSIX")
def test_terminate_hangs_up_the_session():
    term, pty, exits = attached(["/bin/sh", "-c", "sleep 30"])
    pty.terminate()
    assert pump_until(lambda: exits, 5)
    assert exits == [128 + 1]  # SIGHUP


@pytest.mark.skipif(WINDOWS, reason="POSIX write queue")
def test_a_program_that_does_not_read_cannot_block_input():
    # Raw mode first: a line-mode TTY keeps only ~4 KB of an unfinished line.
    term, pty, exits = attached(["/bin/sh", "-c", "stty raw -echo; echo ready; sleep 1; head -c 300000 >/dev/null; echo drained"])
    assert pump_until(lambda: "ready" in term.get_text())
    start = GLib.get_monotonic_time()
    term.paste_text("x" * 300_000)  # far more than the PTY buffer
    assert GLib.get_monotonic_time() - start < 500_000  # returned at once
    assert pump_until(lambda: exits, 15)
    assert "drained" in term.get_text()


def test_missing_program_is_reported():
    if WINDOWS:
        with pytest.raises(GLib.Error):
            GtkGhostty.Pty.spawn(["no-such-program-xyz.exe"], None, None, 80, 24)
    else:
        exits = []
        pty = GtkGhostty.Pty.spawn(["no-such-program-xyz"], None, None, 80, 24)
        pty.connect("exited", lambda _p, status: exits.append(status))
        assert pump_until(lambda: exits)
        assert exits == [127]


@pytest.mark.skipif(sys.platform == "win32" or not os.path.exists("/proc"), reason="reads /proc")
def test_dropping_a_running_pty_leaves_no_zombie():
    # Issue #1: disposal hung up the child but nothing reaped it.
    pty = GtkGhostty.Pty.spawn(["sleep", "30"], None, None, 40, 10)
    pid = pty.get_pid()
    assert pid > 0
    del pty
    import gc

    gc.collect()

    def gone():
        try:
            with open(f"/proc/{pid}/stat") as stat:
                return stat.read().split(") ")[1][0] not in "RSDTZ"
        except FileNotFoundError:
            return True

    assert pump_until(gone, 5), "child still present (zombie?)"
