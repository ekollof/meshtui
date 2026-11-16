"""Tests for the jeepney-backed desktop notification helper."""

from unittest.mock import Mock, patch

import pytest

from meshtui import notifications
from meshtui.notifications import DesktopNotifier


class FakeConnection:
    """Minimal stand-in for a jeepney blocking DBusConnection."""

    def __init__(self, reply=None, error=None):
        self.reply = reply if reply is not None else object()
        self.error = error
        self.sent = []
        self.closed = False

    def send_and_get_reply(self, message, *, timeout=None):
        self.sent.append((message, timeout))
        if self.error:
            raise self.error
        return self.reply

    def close(self):
        self.closed = True


def test_connect_opens_session_bus_and_checks_daemon():
    notifier = DesktopNotifier()
    connection = FakeConnection()

    with (
        patch(
            "meshtui.notifications.open_dbus_connection",
            return_value=connection,
        ) as open_bus,
        patch("meshtui.notifications.unwrap_msg", return_value=("daemon",)),
    ):
        assert notifier.connect() is True

    open_bus.assert_called_once_with(bus="SESSION", auth_timeout=1.0)
    assert notifier.available is True
    assert notifier._connection is connection
    connection.sent[0][0].header.fields  # method call was built


def test_connect_returns_false_without_jeepney():
    notifier = DesktopNotifier()

    with patch.object(notifications, "JEEPNEY_AVAILABLE", False):
        assert notifier.connect() is False

    assert notifier.available is False


def test_connect_returns_false_when_bus_is_unavailable():
    notifier = DesktopNotifier()

    with patch(
        "meshtui.notifications.open_dbus_connection",
        side_effect=ConnectionError("no session bus"),
    ):
        assert notifier.connect() is False

    assert notifier.available is False
    assert notifier._connection is None


def test_send_builds_notify_call_with_urgency():
    notifier = DesktopNotifier()
    connection = FakeConnection()
    notifier.available = True
    notifier._connection = connection
    sentinel = object()

    with (
        patch("meshtui.notifications.new_method_call", return_value=sentinel) as call,
        patch("meshtui.notifications.unwrap_msg", return_value=(42,)),
    ):
        assert notifier.send("Title", "Body", urgency="critical") is True

    assert call.call_args.args[1] == "Notify"
    assert call.call_args.args[2] == "susssasa{sv}i"
    body = call.call_args.args[3]
    assert body[0] == "MeshTUI"
    assert body[1] == 0
    assert body[2] == "network-wireless"
    assert body[3] == "Title"
    assert body[4] == "Body"
    assert body[5] == []
    assert body[6]["urgency"] == ("y", 2)
    assert body[6]["desktop-entry"] == ("s", "meshtui")
    assert body[7] == 5000
    assert connection.sent == [(sentinel, notifier.timeout)]


@pytest.mark.parametrize(
    ("urgency", "expected"),
    [("low", 0), ("normal", 1), ("critical", 2), ("unknown", 1)],
)
def test_send_maps_urgency(urgency, expected):
    notifier = DesktopNotifier()
    notifier.available = True
    notifier._connection = FakeConnection()

    with (
        patch("meshtui.notifications.new_method_call") as call,
        patch("meshtui.notifications.unwrap_msg"),
    ):
        assert notifier.send("Title", "Body", urgency=urgency) is True

    assert call.call_args.args[3][6]["urgency"] == ("y", expected)


def test_send_reconnects_after_connection_loss():
    notifier = DesktopNotifier()
    connection = FakeConnection(error=RuntimeError("bus closed"))
    notifier.available = True
    notifier._connection = connection

    with (
        patch("meshtui.notifications.new_method_call"),
        patch("meshtui.notifications.unwrap_msg"),
    ):
        assert notifier.send("Title", "Body") is False

    assert connection.closed is True
    assert notifier._connection is None
    # A later send can open a fresh connection.
    assert notifier.available is True


def test_send_returns_false_when_not_connected():
    notifier = DesktopNotifier()

    with patch("meshtui.notifications.new_method_call") as call:
        assert notifier.send("Title", "Body") is False

    call.assert_not_called()


def test_send_reconnects_if_connection_was_dropped():
    notifier = DesktopNotifier()
    replacement = FakeConnection()
    notifier.available = True
    notifier._connection = None

    with (
        patch.object(notifier, "connect", return_value=True) as connect,
        patch("meshtui.notifications.new_method_call"),
        patch("meshtui.notifications.unwrap_msg"),
    ):
        # connect() normally installs a connection; emulate that side effect.
        def reconnect():
            notifier._connection = replacement
            return True

        connect.side_effect = reconnect
        assert notifier.send("Title", "Body") is True

    connect.assert_called_once()
    assert notifier._connection is replacement


def test_close_closes_connection():
    notifier = DesktopNotifier()
    connection = FakeConnection()
    notifier.available = True
    notifier._connection = connection

    notifier.close()

    assert connection.closed is True
    assert notifier._connection is None
    assert notifier.available is False


def test_get_server_information():
    notifier = DesktopNotifier()
    notifier.available = True
    notifier._connection = FakeConnection()

    with (
        patch("meshtui.notifications.new_method_call"),
        patch(
            "meshtui.notifications.unwrap_msg",
            return_value=("quickshell", "quickshell", "1.0", "1.2"),
        ),
    ):
        info = notifier.get_server_information()

    assert info == {
        "name": "quickshell",
        "vendor": "quickshell",
        "version": "1.0",
        "spec_version": "1.2",
    }


def test_app_send_desktop_notification_delegates_to_notifier():
    from meshtui.app import MeshTUI

    app = object.__new__(MeshTUI)
    app.notifications_enabled = True
    app.notifier = Mock()
    app.logger = Mock()

    app._send_desktop_notification("Title", "Body", urgency="critical")

    app.notifier.send.assert_called_once_with("Title", "Body", urgency="critical")


def test_app_send_desktop_notification_is_noop_when_disabled():
    from meshtui.app import MeshTUI

    app = object.__new__(MeshTUI)
    app.notifications_enabled = False
    app.notifier = Mock()
    app.logger = Mock()

    app._send_desktop_notification("Title", "Body")

    app.notifier.send.assert_not_called()
