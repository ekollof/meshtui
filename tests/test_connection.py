"""Tests for MeshConnection reconnection behavior."""

from unittest.mock import AsyncMock, patch

import pytest

from meshtui.connection import MeshConnection
from meshtui.transport import ConnectionType


@pytest.fixture
def connection():
    """Provide a MeshConnection without opening any real transport."""
    return MeshConnection()


@pytest.mark.asyncio
async def test_reconnect_without_previous_attempt(connection):
    """Reconnect is a no-op when no connection has been attempted yet."""
    assert await connection.reconnect() is False


@pytest.mark.asyncio
async def test_reconnect_serial_without_previous_attempt(connection):
    """Serial reconnect is a no-op when no serial connection was attempted."""
    assert await connection.reconnect_serial() is False


@pytest.mark.asyncio
async def test_reconnect_retries_last_serial_attempt(connection):
    """Reconnect retries the last serial port and baudrate."""
    connection.last_connection = {
        "type": ConnectionType.SERIAL,
        "port": "/dev/ttyUSB0",
        "baudrate": 9600,
    }

    with patch.object(
        connection, "connect_serial", new=AsyncMock(return_value=True)
    ) as connect_serial:
        result = await connection.reconnect()

    assert result is True
    connect_serial.assert_awaited_once_with(
        port="/dev/ttyUSB0", baudrate=9600, verify_meshcore=False
    )


@pytest.mark.asyncio
async def test_reconnect_serial_uses_last_serial_after_ble_fallback(connection):
    """Serial reconnect keeps the serial port even if BLE was tried last."""
    connection.last_serial_connection = {
        "type": ConnectionType.SERIAL,
        "port": "/dev/ttyUSB0",
        "baudrate": 115200,
    }
    connection.last_connection = {
        "type": ConnectionType.BLE,
        "address": "AA:BB:CC:DD:EE:FF",
        "pin": None,
    }

    with patch.object(
        connection, "connect_serial", new=AsyncMock(return_value=True)
    ) as connect_serial:
        assert await connection.reconnect_serial() is True

    connect_serial.assert_awaited_once_with(
        port="/dev/ttyUSB0", baudrate=115200, verify_meshcore=False
    )


@pytest.mark.asyncio
async def test_reconnect_retries_last_ble_attempt(connection):
    """Reconnect retries the last BLE address and PIN."""
    connection.last_connection = {
        "type": ConnectionType.BLE,
        "address": "AA:BB:CC:DD:EE:FF",
        "pin": "123456",
    }

    with patch.object(
        connection, "connect_ble", new=AsyncMock(return_value=True)
    ) as connect_ble:
        result = await connection.reconnect()

    assert result is True
    connect_ble.assert_awaited_once_with(
        address="AA:BB:CC:DD:EE:FF", pin="123456"
    )


@pytest.mark.asyncio
async def test_reconnect_retries_last_tcp_attempt(connection):
    """Reconnect retries the last TCP endpoint."""
    connection.last_connection = {
        "type": ConnectionType.TCP,
        "hostname": "192.168.1.100",
        "port": 5000,
    }

    with patch.object(
        connection, "connect_tcp", new=AsyncMock(return_value=True)
    ) as connect_tcp:
        result = await connection.reconnect()

    assert result is True
    connect_tcp.assert_awaited_once_with(hostname="192.168.1.100", port=5000)


@pytest.mark.asyncio
async def test_reconnect_drops_half_open_connection(connection):
    """Reconnect disconnects a half-open MeshCore instance before retrying."""
    connection.meshcore = object()
    connection.last_connection = {
        "type": ConnectionType.SERIAL,
        "port": "/dev/ttyACM0",
        "baudrate": 115200,
    }

    with (
        patch.object(connection, "disconnect", new=AsyncMock()) as disconnect,
        patch.object(
            connection, "connect_serial", new=AsyncMock(return_value=True)
        ) as connect_serial,
    ):
        result = await connection.reconnect()

    assert result is True
    disconnect.assert_awaited_once()
    connect_serial.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_serial_connect_can_be_retried(connection):
    """A failed initial serial connect can be retried with reconnect()."""
    with patch(
        "meshtui.connection.MeshCore.create_serial",
        side_effect=OSError("port not available"),
    ):
        assert (
            await connection.connect_serial(
                "/dev/ttyUSB0", baudrate=9600, verify_meshcore=False
            )
            is False
        )

    with patch.object(
        connection, "connect_serial", new=AsyncMock(return_value=True)
    ) as connect_serial:
        assert await connection.reconnect() is True

    connect_serial.assert_awaited_once_with(
        port="/dev/ttyUSB0", baudrate=9600, verify_meshcore=False
    )


@pytest.mark.asyncio
async def test_failed_serial_connect_records_retry_parameters(connection):
    """A failed serial attempt is remembered so the UI can retry it."""
    with patch(
        "meshtui.connection.MeshCore.create_serial",
        side_effect=OSError("port not available"),
    ):
        result = await connection.connect_serial(
            "/dev/ttyUSB0", baudrate=9600, verify_meshcore=False
        )

    assert result is False
    assert connection.last_connection == {
        "type": ConnectionType.SERIAL,
        "port": "/dev/ttyUSB0",
        "baudrate": 9600,
    }
    assert connection.last_serial_connection == connection.last_connection
