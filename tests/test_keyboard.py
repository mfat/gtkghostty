# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2026 mFat <newmfat@gmail.com> and the gtkghostty contributors
"""Real key events (xdotool on an X server) through GTK's input method.

Skipped without an X display or xdotool: synthetic GdkEvents cannot be made
from Python, and the bug these pin lived exactly in GTK's routing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time

import gi
import pytest

gi.require_version("Gtk", "4.0")
gi.require_version("GtkGhostty", "1")
from gi.repository import GLib, Gtk, GtkGhostty  # noqa: E402

pytestmark = pytest.mark.skipif(
    not os.environ.get("DISPLAY") or shutil.which("xdotool") is None
    or os.environ.get("GDK_BACKEND") != "x11",
    reason="needs X11 and xdotool",
)


def _pump(seconds):
    context = GLib.MainContext.default()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        context.iteration(False)


_DEAD_KEY_MAPPED = False


def _map_dead_acute():
    """Give dead_acute a real keycode before any window exists.

    xdotool otherwise remaps a spare key on the fly, after GTK loaded the
    keymap, so the key arrives as keyval 0 and nothing composes."""
    global _DEAD_KEY_MAPPED
    if not _DEAD_KEY_MAPPED and shutil.which("xmodmap"):
        subprocess.run(["xmodmap", "-e", "keycode 135 = dead_acute"], check=False)
        _DEAD_KEY_MAPPED = True


@pytest.fixture()
def focused_terminal():
    _map_dead_acute()
    term = GtkGhostty.Terminal()
    window = Gtk.Window(title="gtkghostty-keyboard-test")
    window.set_default_size(400, 200)
    window.set_child(term)
    window.present()
    _pump(1.0)
    term.grab_focus()
    sent = []
    term.connect("input", lambda _t, data: sent.append(data.get_data()))
    yield term, sent
    window.destroy()


def _keys(*names):
    subprocess.run(["xdotool", "key", "--delay", "60", *names], check=True)
    _pump(0.6)


def test_kitty_keyboard_encodes_text_keys_and_reports_releases(focused_terminal):
    term, sent = focused_terminal
    term.feed_data(b"\x1b[>11u")  # disambiguate + event types + all keys as escapes
    _keys("a", "Up")
    data = b"".join(sent)
    assert data.startswith(b"\x1b[97u"), data          # not a raw "a"
    assert b"\x1b[97;1:3u" in data, data                # release of a
    assert b"\x1b[1;1:3A" in data, data                 # release of Up


def test_legacy_keyboard_still_types_text_and_sends_no_releases(focused_terminal):
    _term, sent = focused_terminal
    _keys("a", "shift+b", "Up")
    assert b"".join(sent) == b"aB\x1b[A"


def test_a_dead_key_composition_goes_out_as_text(focused_terminal):
    term, sent = focused_terminal
    _keys("dead_acute")
    assert sent == []  # composing: nothing reaches the program yet
    _keys("e", "ctrl+c")
    assert b"".join(sent) == "é".encode() + b"\x03"


def test_a_composition_is_text_even_under_kitty(focused_terminal):
    term, sent = focused_terminal
    term.feed_data(b"\x1b[>11u")
    _keys("dead_acute", "e")
    presses = [chunk for chunk in sent if not chunk.endswith(b":3u")]
    assert "é".encode() in b"".join(presses), sent


def test_a_wheel_notch_scrolls_the_set_number_of_lines():
    term = GtkGhostty.Terminal()
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_child(term)
    window = Gtk.Window(title="gtkghostty-wheel-test")
    window.set_default_size(400, 200)
    window.set_child(scrolled)
    window.present()
    _pump(1.0)
    term.feed_data(b"".join(b"line%d\r\n" % n for n in range(200)))
    _pump(0.3)
    adjustment = scrolled.get_vadjustment()
    subprocess.run(["xdotool", "search", "--name", "gtkghostty-wheel-test", "windowfocus", "--sync"], check=False)
    subprocess.run(["xdotool", "search", "--name", "gtkghostty-wheel-test",
                    "mousemove", "--window", "%1", "100", "80"], check=True)
    moved = []
    for lines in (3, 7):
        term.props.wheel_scroll_lines = lines
        before = adjustment.get_value()
        subprocess.run(["xdotool", "click", "4"], check=True)  # one notch up
        _pump(0.5)
        moved.append(before - adjustment.get_value())
    window.destroy()
    assert moved == [3, 7], moved


def test_ctrl_alt_space_is_escape_nul(focused_terminal):
    # Midnight Commander and Emacs bind it; it is not an AltGr character.
    term, sent = focused_terminal
    _keys("ctrl+space", "ctrl+alt+space")
    assert b"".join(sent) == b"\x00\x1b\x00"
