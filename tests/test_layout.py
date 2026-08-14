"""Tests for compact / sidebar layout decisions."""

from meshtui.app import detect_low_power_host, resolve_layout


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


def test_pi_b_detected_as_low_power():
    assert detect_low_power_host(machine="armv6l", env={}) is True


def test_desktop_x86_not_low_power():
    assert (
        detect_low_power_host(
            machine="x86_64", cpu_count=4, mem_bytes=8 * 1024**3, env={}
        )
        is False
    )


def test_single_core_512mb_is_low_power():
    assert (
        detect_low_power_host(
            machine="armv7l", cpu_count=1, mem_bytes=512 * 1024 * 1024, env={}
        )
        is True
    )


def test_env_overrides_low_power_detection():
    assert detect_low_power_host(machine="x86_64", cpu_count=8, env={"MESHTUI_LOW_POWER": "1"})
    assert not detect_low_power_host(machine="armv6l", env={"MESHTUI_LOW_POWER": "0"})
