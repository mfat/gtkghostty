# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2026 mFat <newmfat@gmail.com> and the gtkghostty contributors
"""GtkGhosttyTerminal from Python through GObject Introspection.

Run from a build directory (see tests/run.sh): needs the typelib on
GI_TYPELIB_PATH, the library on LD_LIBRARY_PATH and a display (Xvfb is fine).
"""

from __future__ import annotations

import base64

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkGhostty", "1")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GLib, Gtk, GtkGhostty, Pango  # noqa: E402

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


def test_an_empty_screen_reads_as_empty_text():
    term = make()
    assert term.get_text() == ""


def test_size_version_and_colour_scheme_queries_are_answered():
    term = make(40, 10)
    replies = []
    term.connect("reply", lambda _t, data: replies.append(data.get_data()))
    term.feed_data(b"\x1b[18t")  # text area in characters
    term.feed_data(b"\x1b[>q")   # XTVERSION
    term.feed_data(b"\x1b[?996n")  # colour scheme
    assert replies[0] == b"\x1b[8;10;40t"
    assert replies[1].startswith(b"\x1bP>|gtkghostty ") and replies[1].endswith(b"\x1b\\")
    assert replies[2] == b"\x1b[?997;1n"  # dark: the default background is black
    term.feed_data(b"\x1b]11;#ffffff\x1b\\\x1b[?996n")
    assert replies[-1] == b"\x1b[?997;2n"  # light once the program sets a white background


def _osc_colour(term, number):
    replies = []
    handler = term.connect("reply", lambda _t, data: replies.append(data.get_data()))
    term.feed_data(b"\x1b]%d;?\x1b\\" % number)
    term.disconnect(handler)
    return replies[-1] if replies else None


def _rgba(spec):
    colour = Gdk.RGBA()
    assert colour.parse(spec)
    return colour


def test_theme_colours_are_the_defaults_programs_see():
    term = make()
    palette = [_rgba("#%02x0000" % n) for n in range(16)]
    term.set_colors(_rgba("#112233"), _rgba("#fafafa"), _rgba("#ff0000"), palette)
    assert _osc_colour(term, 10).startswith(b"\x1b]10;rgb:1111/2222/3333")
    assert _osc_colour(term, 11).startswith(b"\x1b]11;rgb:fafa/fafa/fafa")
    replies = []
    term.connect("reply", lambda _t, data: replies.append(data.get_data()))
    term.feed_data(b"\x1b]4;3;?\x1b\\\x1b]4;100;?\x1b\\")
    answer = b"".join(replies)  # replies to one write come out together
    assert answer.startswith(b"\x1b]4;3;rgb:0303/0000/0000")
    assert b"\x1b]4;100;rgb:" in answer
    assert b"\x1b]4;100;rgb:0000/0000/0000" not in answer  # 256-colour cube kept
    term.feed_data(b"\x1b[?996n")
    assert replies[-1] == b"\x1b[?997;2n"  # a light theme reads as light
    term.set_colors(None, None, None, None)
    assert _osc_colour(term, 11).startswith(b"\x1b]11;rgb:0000/0000/0000")


def test_cursor_scrollback_and_font_scale_settings():
    term = make(20, 4)
    term.set_cursor_shape(GtkGhostty.CursorShape.IBEAM)
    term.set_cursor_blink(True)
    assert term.get_cursor_shape() == GtkGhostty.CursorShape.IBEAM
    term.set_font_scale(1.5)
    assert term.get_font_scale() == 1.5
    term.set_font_scale(100)
    assert term.get_font_scale() == 4.0
    term.set_scrollback_lines(50)
    term.feed_data(b"".join(b"line%d\r\n" % n for n in range(5000)))
    kept = len(lines(term))
    assert 50 <= kept < 2000, kept  # pruned by whole pages, so about 50


def _selected_after_find(term, backwards=False):
    assert term.search_find(backwards)
    return term.get_selected_text()


def test_plain_search_walks_history_with_libghostty():
    term = make(30, 4)
    term.feed_data(b"".join(b"row%02d %s\r\n" % (n, b"ERROR" if n % 10 == 3 else b"ok") for n in range(40)))
    selected = []
    term.connect("selection-changed", lambda _t: selected.append(True))
    assert term.search_set_pattern("error", False, False)
    assert _selected_after_find(term, backwards=True) == "ERROR"  # newest first
    assert term.search_find(True) and term.search_find(True)
    assert selected
    assert term.search_set_pattern(None, False, False)
    assert not term.search_find(False)


def test_regex_and_case_sensitive_search_select_the_match():
    term = make(30, 4)
    term.feed_data(b"".join(b"row%02d %s\r\n" % (n, b"Error 42" if n == 7 else b"error 1") for n in range(30)))
    assert term.search_set_pattern("Error", False, True)
    assert _selected_after_find(term) == "Error"
    assert term.search_set_pattern(r"Error \d+", True, False)
    assert _selected_after_find(term) in ("error 1", "Error 42")
    assert not term.search_set_pattern("(unclosed", True, False)  # searched as text instead
    assert not term.search_find(False)


def test_links_and_line_text_under_the_pointer():
    term = make(40, 4)
    term.feed_data(b"see \x1b]8;;https://example.org/x\x1b\\here\x1b]8;;\x1b\\ and https://plain.example\r\n")
    contents = []
    term.connect("contents-changed", lambda _t: contents.append(True))
    term.feed_data(b"\x1b[s\x1b[u")
    assert contents
    # Cell metrics come from the font: find the link by scanning the row.
    found = None
    for x in range(0, 400, 2):
        found = term.hyperlink_at(x, 2)
        if found:
            break
    assert found == "https://example.org/x"
    text, column = term.get_line_at(1, 2)
    assert text.startswith("see here and https://plain.example") and column == 0


def test_a_new_terminal_answers_colour_queries():
    term = make()
    for number in (10, 11):
        assert _osc_colour(term, number).startswith(b"\x1b]%d;rgb:" % number)
    term.feed_data(b"\x1bc")  # a full reset keeps the defaults
    assert _osc_colour(term, 11).startswith(b"\x1b]11;rgb:")


def test_a_search_hit_in_history_scrolls_into_view():
    for regex in (False, True):
        term = make(20, 5)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(term)
        term.set_grid_size(20, 5)
        term.feed_data(b"needle at the top\r\n" + b"".join(b"line%d\r\n" % n for n in range(100)))
        adjustment = scrolled.get_vadjustment()
        bottom = adjustment.get_value()
        assert term.search_set_pattern("needle", regex, False)
        assert term.search_find(True)
        assert term.get_selected_text() == "needle"
        assert adjustment.get_value() < bottom - 50, (regex, adjustment.get_value())


def test_a_cursor_change_waits_for_an_unfinished_sequence():
    # Issue #1: changing the cursor injected bytes into a half-received OSC.
    term = make()
    term.feed_data(b"\x1b]2;hello")
    term.set_cursor_shape(GtkGhostty.CursorShape.UNDERLINE)
    term.set_cursor_blink(True)
    term.feed_data(b" world\x07")
    assert term.get_title() == "hello world"
    assert term.get_text() == ""
    assert term.get_cursor_shape() == GtkGhostty.CursorShape.UNDERLINE


def test_annotations_match_what_the_code_accepts():
    # Issue #2: the title can be NULL and a NULL font restores the default.
    term = make()
    assert term.get_title() is None and term.props.title is None
    default = term.get_font_desc().to_string()
    term.set_font_desc(Pango.FontDescription.from_string("Serif 20"))
    assert term.get_font_desc().to_string() != default
    term.set_font_desc(None)
    assert term.get_font_desc().to_string() == default
    text, column = term.get_line_at(1, 1)
    assert text == "" and column >= 0


def _clipboard_text(clipboard):
    result = []
    clipboard.read_text_async(None, lambda c, r: result.append(c.read_text_finish(r)))
    context = GLib.MainContext.default()
    deadline = GLib.get_monotonic_time() + 2_000_000
    while not result and GLib.get_monotonic_time() < deadline:
        context.iteration(False)
    return result[0] if result else None


def test_programs_can_set_but_never_read_the_clipboard():
    # OSC 52, as tmux and editors use to copy over SSH.
    term = make()
    replies = []
    term.connect("reply", lambda _t, data: replies.append(data.get_data()))
    clipboard, primary = term.get_clipboard(), term.get_primary_clipboard()
    term.feed_data(b"\x1b]52;c;" + base64.b64encode("copié over ssh".encode()) + b"\x1b\\")
    assert _clipboard_text(clipboard) == "copié over ssh"
    term.feed_data(b"\x1b]52;p;cHJpbWFyeQ==\x07")
    assert _clipboard_text(primary) == "primary"
    term.feed_data(b"\x1b]52;c;?\x1b\\")  # a read request
    assert all(b"copi" not in reply for reply in replies)
    assert not any(reply.startswith(b"\x1b]52") and len(reply) > 12 for reply in replies)
    term.props.allow_clipboard_write = False
    term.feed_data(b"\x1b]52;c;bm9wZQ==\x1b\\")
    assert _clipboard_text(clipboard) == "copié over ssh"
    assert term.get_text() == ""


def test_the_shell_reported_directory_is_a_property():
    term = make()
    seen = []
    term.connect("notify::current-directory-uri", lambda t, _p: seen.append(t.get_current_directory_uri()))
    assert term.get_current_directory_uri() is None
    term.feed_data(b"\x1b]7;file://myhost/home/me/src\x1b\\")
    assert term.props.current_directory_uri == "file://myhost/home/me/src"
    term.feed_data(b"\x1b]7;\x1b\\")  # cleared
    assert seen == ["file://myhost/home/me/src", None]


def test_the_selection_copies_as_html_with_its_colours():
    term = make(30, 3)
    term.feed_data(b"\x1b[31mred\x1b[0m plain")
    assert term.get_selected_html() is None
    term.select_all()
    html = term.get_selected_html()
    assert "red" in html and "plain" in html and "<" in html
    assert "color" in html.lower()


def test_the_line_under_the_pointer_follows_a_scrolled_back_view():
    term = make(30, 4)
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_child(term)
    term.set_grid_size(30, 4)
    term.feed_data(b"".join(b"line %d https://e.example/%d\r\n" % (n, n) for n in range(50)))
    term.scroll_lines(-20)
    text, _column = term.get_line_at(1, 1)
    assert text.startswith("line ") and text != "line 49 https://e.example/49"
    assert text.split()[1] in {str(n) for n in range(25, 35)}
