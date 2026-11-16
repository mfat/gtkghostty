# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2026 mFat <newmfat@gmail.com> and the gtkghostty contributors
"""Real Option key presses on macOS (Quartz events through GTK's macOS backend).

The Option key is where macOS differs: GTK reports it as layout group 1, so
the key arrives already turned into the layout's Option character, and a
macOS build of libghostty-vt decides by option-as-alt whether it is text or
Alt. Skipped elsewhere, without PyObjC, or when the session will not take
posted events (no accessibility permission).
"""

from __future__ import annotations

import sys
import time

import pytest

if sys.platform != "darwin":
    pytest.skip("macOS only", allow_module_level=True)
Quartz = pytest.importorskip("Quartz", reason="needs pyobjc-framework-Quartz")
AppKit = pytest.importorskip("AppKit", reason="needs pyobjc-framework-Cocoa")

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("GtkGhostty", "1")
from gi.repository import GLib, Gtk, GtkGhostty  # noqa: E402

# kVK_ANSI_* virtual key codes (US/ABC positions).
KEY_A, KEY_B, KEY_L = 0, 11, 37
OPTION = Quartz.kCGEventFlagMaskAlternate


def _pump(seconds):
    context = GLib.MainContext.default()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        context.iteration(False)


def _press(keycode, flags=0):
    for down in (True, False):
        event = Quartz.CGEventCreateKeyboardEvent(None, keycode, down)
        Quartz.CGEventSetFlags(event, flags)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        _pump(0.05)
    _pump(0.4)


@pytest.fixture(scope="module")
def terminal():
    term = GtkGhostty.Terminal()
    window = Gtk.Window(title="gtkghostty-macos-keys")
    window.set_default_size(400, 200)
    window.set_child(term)
    window.present()
    AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    _pump(1.5)
    term.grab_focus()
    sent = []
    term.connect("input", lambda _t, data: sent.append(data.get_data()))
    _press(KEY_A)
    if b"a" not in b"".join(sent):
        window.destroy()
        pytest.skip("this session does not deliver posted key events (accessibility)")
    yield term, sent
    window.destroy()


def _typed(terminal, keycode, flags=OPTION):
    term, sent = terminal
    sent.clear()
    _press(keycode, flags)
    return b"".join(sent)


def test_option_types_the_layouts_character_by_default(terminal):
    term, _sent = terminal
    term.feed_data(b"\x1b[<u")  # legacy keyboard
    term.set_option_as_alt(GtkGhostty.OptionAsAlt.NEVER)
    assert _typed(terminal, KEY_L) == "¬".encode()  # issue mfat/sshpilot#737


def test_option_as_alt_sends_escape_and_the_plain_key(terminal):
    term, _sent = terminal
    term.feed_data(b"\x1b[<u")
    term.set_option_as_alt(GtkGhostty.OptionAsAlt.ALWAYS)
    try:
        assert _typed(terminal, KEY_B) == b"\x1bb"
    finally:
        term.set_option_as_alt(GtkGhostty.OptionAsAlt.NEVER)


def test_kitty_programs_get_option_characters_as_text(terminal):
    term, _sent = terminal
    term.feed_data(b"\x1b[>1u")  # kitty, disambiguate
    try:
        assert _typed(terminal, KEY_L) == "¬".encode()  # not CSI 172;3u
        term.set_option_as_alt(GtkGhostty.OptionAsAlt.ALWAYS)
        assert _typed(terminal, KEY_B) == b"\x1b[98;3u"
    finally:
        term.set_option_as_alt(GtkGhostty.OptionAsAlt.NEVER)
        term.feed_data(b"\x1b[<u")
