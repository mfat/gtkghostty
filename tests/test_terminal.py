"""GtkGhosttyTerminal from Python through GObject Introspection.

Run from a build directory (see tests/run.sh): needs the typelib on
GI_TYPELIB_PATH, the library on LD_LIBRARY_PATH and a display (Xvfb is fine).
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkGhostty", "1")
from gi.repository import GLib, Gtk, GtkGhostty  # noqa: E402

Gtk.init()

FIXTURE = (
    "\x1b[31mRED\x1b[0m \x1b[38;2;10;200;30mtruecolor\x1b[0m wide: 漢字 emoji: 🧪 ok\r\n"
    "combining: é box: ┌─┐ ╭─╮ █▓░\r\n"
    + "\x1b[" + ";".join(["1"] * 40) + "mlong-CSI survived\x1b[0m\r\n"
    + "\x1b[?1049h\x1b[Halt screen\x1b[?1049l"
    + "back on main\r\n"
).encode()


def make(columns=60, rows=8):
    term = GtkGhostty.Terminal()
    term.set_grid_size(columns, rows)
    return term


def lines(term):
    return term.get_text().splitlines()


def test_fixture_byte_by_byte_without_a_shell():
    term = make()
    for index in range(len(FIXTURE)):  # split UTF-8 and split escape sequences
        term.feed(GLib.Bytes.new(FIXTURE[index:index + 1]))
    assert lines(term)[:4] == [
        "RED truecolor wide: 漢字 emoji: 🧪 ok",
        "combining: é box: ┌─┐ ╭─╮ █▓░",
        "long-CSI survived",
        "back on main",
    ]


def test_replies_come_out_after_the_write():
    term = make()
    replies = []
    term.connect("reply", lambda _t, data: replies.append(data.get_data()))
    term.feed_data(b"\x1b[5n\x1b[6n")
    assert b"".join(replies) == b"\x1b[0n\x1b[1;1R"


def test_title_and_bell():
    term = make()
    titles, bells = [], []
    term.connect("notify::title", lambda t, _p: titles.append(t.get_title()))
    term.connect("bell", lambda _t: bells.append(True))
    term.feed_data("\x1b]2;café\x07\x07".encode())
    assert titles == ["café"] and term.props.title == "café"
    assert bells == [True]


def test_paste_is_sanitised_and_bracketed_when_asked():
    term = make()
    sent = []
    term.connect("input", lambda _t, data: sent.append(data.get_data()))
    term.paste_text("echo hi\x1b[201~\n")
    term.feed_data(b"\x1b[?2004h")
    term.paste_text("ls\n")
    assert sent[0] == b"echo hi [201~\r"
    assert sent[1] == b"\x1b[200~ls\n\x1b[201~"
    assert not GtkGhostty.Terminal.paste_is_safe("rm -rf ~\n")
    assert GtkGhostty.Terminal.paste_is_safe("plain")


def test_resize_reports_the_grid_and_reflows():
    term = make(20, 4)
    sizes = []
    term.connect("size-changed", lambda _t, c, r, w, h: sizes.append((c, r, w > 0, h > 0)))
    term.feed_data(b"0123456789abcdefghij")
    term.set_grid_size(10, 4)
    assert sizes == [(10, 4, True, True)]
    assert (term.get_columns(), term.get_rows()) == (10, 4)
    assert lines(term)[:2] == ["0123456789", "abcdefghij"]


def test_properties():
    term = make()
    assert term.props.pull_history_on_grow and not term.props.legacy_keyboard
    term.props.legacy_keyboard = True
    term.props.pull_history_on_grow = False
    assert term.get_legacy_keyboard() and not term.get_pull_history_on_grow()


def test_renders_a_frame_in_a_window():
    term = GtkGhostty.Terminal()
    window = Gtk.Window()
    window.set_default_size(640, 300)
    window.set_child(term)
    window.present()
    term.feed_data(FIXTURE)
    context = GLib.MainContext.default()
    deadline = GLib.get_monotonic_time() + 3_000_000
    while term.get_columns() in (0, 80) and GLib.get_monotonic_time() < deadline:
        context.iteration(False)
    # The allocation decided the grid, not the 80x24 default.
    assert term.get_columns() != 80
    paintable = Gtk.WidgetPaintable.new(term)
    snapshot = Gtk.Snapshot()
    paintable.snapshot(snapshot, term.get_width(), term.get_height())
    node = snapshot.to_node()
    assert node is not None
    window.destroy()


def _pump(seconds=0.3):
    context = GLib.MainContext.default()
    deadline = GLib.get_monotonic_time() + int(seconds * 1_000_000)
    while GLib.get_monotonic_time() < deadline:
        context.iteration(False)


def test_scrollback_drives_the_scrolled_window_adjustment():
    term = make(20, 5)
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_child(term)
    term.set_grid_size(20, 5)
    term.feed_data(b"".join(b"line%d\r\n" % n for n in range(100)))
    adjustment = scrolled.get_vadjustment()
    assert adjustment.get_upper() >= 100
    assert adjustment.get_page_size() == 5
    bottom = adjustment.get_value()
    assert bottom == adjustment.get_upper() - adjustment.get_page_size()

    term.scroll_lines(-10)
    assert adjustment.get_value() == bottom - 10
    adjustment.set_value(0)  # dragging the scrollbar moves the viewport
    term.scroll_lines(1)
    assert adjustment.get_value() == 1

    term.paste_text("x")  # input jumps back to the prompt
    assert adjustment.get_value() == bottom


def test_output_keeps_a_scrolled_back_view_in_place():
    term = make(20, 5)
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_child(term)
    term.set_grid_size(20, 5)
    term.feed_data(b"".join(b"line%d\r\n" % n for n in range(50)))
    adjustment = scrolled.get_vadjustment()
    term.scroll_lines(-20)
    held = adjustment.get_value()
    term.feed_data(b"".join(b"more%d\r\n" % n for n in range(30)))
    assert adjustment.get_value() == held


def test_select_all_and_selected_text():
    term = make(20, 4)
    term.feed_data(b"alpha\r\nbeta  \r\n0123456789012345678901234")
    assert not term.has_selection() and term.get_selected_text() is None
    term.select_all()
    assert term.has_selection()
    # Soft-wrapped lines come out joined, trailing blanks trimmed.
    assert term.get_selected_text() == "alpha\nbeta\n0123456789012345678901234"
    term.unselect_all()
    assert not term.has_selection()
