"""Tests for compact / sidebar layout decisions."""

from meshtui.app import resolve_layout


def test_picocalc_size_hides_sidebar_and_compacts():
    compact, show_sidebar = resolve_layout(40, 24, None, None)
    assert compact is True
    assert show_sidebar is False


def test_normal_desktop_keeps_sidebar():
    compact, show_sidebar = resolve_layout(120, 40, None, None)
    assert compact is False
    assert show_sidebar is True


def test_user_can_force_sidebar_on_small_screen():
    compact, show_sidebar = resolve_layout(40, 24, True, None)
    assert compact is True
    assert show_sidebar is True


def test_user_can_force_compact_off():
    compact, show_sidebar = resolve_layout(40, 24, None, False)
    assert compact is False
    assert show_sidebar is False


def test_cli_compact_hides_sidebar():
    compact, show_sidebar = resolve_layout(120, 40, False, True)
    assert compact is True
    assert show_sidebar is False
