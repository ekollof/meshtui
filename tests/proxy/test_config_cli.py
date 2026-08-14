"""CLI must not overwrite YAML listen_host/listen_port unless flags are passed."""

from argparse import Namespace

from meshtui.proxy.config import ProxyConfig
from meshtui.proxy.__main__ import apply_cli_overrides


def _args(**kwargs):
    defaults = {
        "serial": None,
        "baudrate": None,
        "ble": None,
        "host": None,
        "port": None,
        "debug": False,
        "log_file": None,
        "log_frames": False,
    }
    defaults.update(kwargs)
    return Namespace(**defaults)


def test_config_listen_port_kept_when_cli_omits_port():
    config = ProxyConfig(listen_host="127.0.0.1", listen_port=6000, serial_port="/dev/ttyUSB0")
    apply_cli_overrides(config, _args())
    assert config.listen_host == "127.0.0.1"
    assert config.listen_port == 6000


def test_cli_port_overrides_config():
    config = ProxyConfig(listen_port=6000, serial_port="/dev/ttyUSB0")
    apply_cli_overrides(config, _args(port=7000, host="127.0.0.1"))
    assert config.listen_port == 7000
    assert config.listen_host == "127.0.0.1"


def test_serial_flag_does_not_reset_listen_port():
    config = ProxyConfig(listen_port=6000, serial_port="/dev/from-config")
    apply_cli_overrides(config, _args(serial="/dev/ttyUSB0"))
    assert config.serial_port == "/dev/ttyUSB0"
    assert config.listen_port == 6000
    assert config.serial_baudrate == 115200
