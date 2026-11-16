#!/usr/bin/env python3
"""Desktop notifications over the freedesktop.org D-Bus service.

Uses jeepney, a pure-Python D-Bus client, so MeshTUI does not need
``notify-send``, ``notify2``, ``dbus-python``, or native build dependencies.
Notifications are Linux/BSD-only; other platforms simply report them as
unavailable.
"""

import logging
import threading
from typing import Optional

try:
    from jeepney import DBusAddress, new_method_call
    from jeepney.io.blocking import open_dbus_connection, unwrap_msg

    JEEPNEY_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised when the dependency is absent
    JEEPNEY_AVAILABLE = False

APP_NAME = "MeshTUI"
DEFAULT_ICON = "network-wireless"

# org.freedesktop.Notifications
NOTIFICATIONS_BUS_NAME = "org.freedesktop.Notifications"
NOTIFICATIONS_PATH = "/org/freedesktop/Notifications"
NOTIFICATIONS_INTERFACE = "org.freedesktop.Notifications"

_URGENCY = {"low": 0, "normal": 1, "critical": 2}


class DesktopNotifier:
    """Send freedesktop.org desktop notifications over the session bus."""

    def __init__(
        self,
        app_name: str = APP_NAME,
        icon: str = DEFAULT_ICON,
        timeout: float = 2.0,
    ):
        self.logger = logging.getLogger("meshtui.notifications")
        self.app_name = app_name
        self.icon = icon
        self.timeout = timeout
        self.available = False
        self._connection = None
        self._lock = threading.RLock()

    def connect(self) -> bool:
        """Open the session bus and verify a notification daemon is present.

        Returns:
            True if notifications can be sent, False otherwise.
        """
        if not JEEPNEY_AVAILABLE:
            self.logger.info("jeepney is not installed, desktop notifications disabled")
            return False

        with self._lock:
            self._close_connection()
            connection = None
            try:
                address = DBusAddress(
                    NOTIFICATIONS_PATH,
                    bus_name=NOTIFICATIONS_BUS_NAME,
                    interface=NOTIFICATIONS_INTERFACE,
                )
                connection = open_dbus_connection(bus="SESSION", auth_timeout=1.0)
                unwrap_msg(
                    connection.send_and_get_reply(
                        new_method_call(address, "GetServerInformation"),
                        timeout=self.timeout,
                    )
                )
            except Exception as e:
                self.logger.info("Desktop notifications unavailable: %s", e)
                if connection is not None:
                    try:
                        connection.close()
                    except Exception:
                        pass
                self.available = False
                self._connection = None
                return False

            self._connection = connection
            self.available = True
            self.logger.info("Desktop notifications enabled via jeepney")
            return True

    def close(self) -> None:
        """Close the D-Bus connection, if one is open."""
        with self._lock:
            self._close_connection()
            self.available = False

    def _close_connection(self) -> None:
        """Close and forget the current connection. Caller holds the lock."""
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception as e:
                self.logger.debug("Error closing notification connection: %s", e)
            self._connection = None

    def send(
        self,
        title: str,
        message: str,
        urgency: str = "normal",
    ) -> bool:
        """Send a notification.

        Args:
            title: Notification summary.
            message: Notification body.
            urgency: One of ``low``, ``normal``, or ``critical``.

        Returns:
            True if the notification was accepted by the daemon.
        """
        if not self.available:
            return False

        with self._lock:
            if self._connection is None:
                # The bus may have restarted since the last notification.
                if not self.connect():
                    return False

            try:
                address = DBusAddress(
                    NOTIFICATIONS_PATH,
                    bus_name=NOTIFICATIONS_BUS_NAME,
                    interface=NOTIFICATIONS_INTERFACE,
                )
                call = new_method_call(
                    address,
                    "Notify",
                    "susssasa{sv}i",
                    (
                        self.app_name,
                        0,  # replaces_id: always create a new notification
                        self.icon,
                        title,
                        message,
                        [],  # actions
                        {
                            "urgency": ("y", _URGENCY.get(urgency, 1)),
                            "desktop-entry": ("s", "meshtui"),
                        },
                        5000,  # expire_timeout (ms)
                    ),
                )
                unwrap_msg(
                    self._connection.send_and_get_reply(call, timeout=self.timeout)
                )
                return True
            except Exception as e:
                self.logger.warning("Failed to send desktop notification: %s", e)
                # Drop the broken connection; the next send will reconnect.
                self._close_connection()
                return False

    def get_server_information(self) -> Optional[dict]:
        """Return notification server details, or None when unavailable.

        This is primarily useful for diagnostics and tests.
        """
        if not self.available:
            return None

        with self._lock:
            if self._connection is None:
                return None
            try:
                address = DBusAddress(
                    NOTIFICATIONS_PATH,
                    bus_name=NOTIFICATIONS_BUS_NAME,
                    interface=NOTIFICATIONS_INTERFACE,
                )
                body = unwrap_msg(
                    self._connection.send_and_get_reply(
                        new_method_call(address, "GetServerInformation"),
                        timeout=self.timeout,
                    )
                )
                return {
                    "name": body[0],
                    "vendor": body[1],
                    "version": body[2],
                    "spec_version": body[3],
                }
            except Exception as e:
                self.logger.debug(
                    "Failed to query notification server information: %s", e
                )
                return None
