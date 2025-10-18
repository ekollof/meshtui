"""
Unit tests for the transport module.

Tests cover serial, BLE, and TCP transport layers with mocked
MeshCore connections.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
from meshtui.transport import SerialTransport, BLETransport, TCPTransport
from meshcore import EventType


class TestSerialTransport:
    """Tests for SerialTransport class."""

    @pytest.mark.asyncio
    async def test_identify_device_success(self, mock_meshcore):
        """Test successful device identification."""
        transport = SerialTransport()

        # Mock MeshCore creation and device query
        mock_result = Mock()
        mock_result.type = EventType.DEVICE_INFO
        mock_result.payload = {"model": "Heltec V3", "ver": "v1.9.0"}

        with patch("meshtui.transport.MeshCore.create_serial", return_value=mock_meshcore):
            mock_meshcore.commands.send_device_query.return_value = mock_result

            result = await transport.identify_device("/dev/ttyUSB0", timeout=5.0, retries=1)

        assert result is True
        mock_meshcore.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_identify_device_error_response(self, mock_meshcore):
        """Test device identification with error response."""
        transport = SerialTransport()

        mock_result = Mock()
        mock_result.type = EventType.ERROR

        with patch("meshtui.transport.MeshCore.create_serial", return_value=mock_meshcore):
            mock_meshcore.commands.send_device_query.return_value = mock_result

            result = await transport.identify_device("/dev/ttyUSB0", timeout=5.0, retries=2)

        assert result is False
        # Should have tried 2 times
        assert mock_meshcore.disconnect.call_count == 2

    @pytest.mark.asyncio
    async def test_identify_device_invalid_payload(self, mock_meshcore):
        """Test device identification with invalid payload."""
        transport = SerialTransport()

        mock_result = Mock()
        mock_result.type = EventType.DEVICE_INFO
        mock_result.payload = {}  # Missing 'model' field

        with patch("meshtui.transport.MeshCore.create_serial", return_value=mock_meshcore):
            mock_meshcore.commands.send_device_query.return_value = mock_result

            result = await transport.identify_device("/dev/ttyUSB0", timeout=5.0, retries=1)

        assert result is False

    @pytest.mark.asyncio
    async def test_identify_device_timeout(self, mock_meshcore):
        """Test device identification with timeout."""
        transport = SerialTransport()

        with patch("meshtui.transport.MeshCore.create_serial", return_value=mock_meshcore):
            import asyncio
            mock_meshcore.commands.send_device_query.side_effect = asyncio.TimeoutError()

            result = await transport.identify_device("/dev/ttyUSB0", timeout=0.1, retries=1)

        assert result is False

    @pytest.mark.asyncio
    async def test_identify_device_retries(self, mock_meshcore):
        """Test device identification with multiple retries."""
        transport = SerialTransport()

        # First attempt fails, second succeeds
        mock_error_result = Mock()
        mock_error_result.type = EventType.ERROR

        mock_success_result = Mock()
        mock_success_result.type = EventType.DEVICE_INFO
        mock_success_result.payload = {"model": "Test Device", "ver": "v1.0"}

        with patch("meshtui.transport.MeshCore.create_serial", return_value=mock_meshcore):
            mock_meshcore.commands.send_device_query.side_effect = [
                mock_error_result,
                mock_success_result
            ]

            result = await transport.identify_device("/dev/ttyUSB0", timeout=5.0, retries=2)

        assert result is True
        assert mock_meshcore.disconnect.call_count == 2  # Called after each attempt

    @pytest.mark.asyncio
    async def test_list_ports(self):
        """Test listing serial ports."""
        transport = SerialTransport()

        mock_port = Mock()
        mock_port.device = "/dev/ttyUSB0"
        mock_port.description = "USB Serial"
        mock_port.hwid = "USB VID:PID=1234:5678"

        with patch("meshtui.transport.serial.tools.list_ports.comports", return_value=[mock_port]):
            ports = await transport.list_ports()

        assert len(ports) == 1
        assert ports[0]["device"] == "/dev/ttyUSB0"
        assert ports[0]["description"] == "USB Serial"

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_meshcore):
        """Test successful serial connection."""
        transport = SerialTransport()

        mock_result = Mock()
        mock_result.type = EventType.DEVICE_INFO
        mock_result.payload = {"model": "Test Device"}

        with patch("meshtui.transport.MeshCore.create_serial", return_value=mock_meshcore):
            mock_meshcore.commands.send_device_query.return_value = mock_result

            meshcore = await transport.connect("/dev/ttyUSB0", baudrate=115200)

        assert meshcore is not None
        assert meshcore == mock_meshcore

    @pytest.mark.asyncio
    async def test_connect_failure(self, mock_meshcore):
        """Test failed serial connection."""
        transport = SerialTransport()

        with patch("meshtui.transport.MeshCore.create_serial", return_value=mock_meshcore):
            mock_meshcore.commands.send_device_query.side_effect = Exception("Connection failed")

            meshcore = await transport.connect("/dev/ttyUSB0")

        assert meshcore is None


class TestBLETransport:
    """Tests for BLETransport class."""

    @pytest.mark.asyncio
    async def test_scan_devices_success(self, temp_db_path):
        """Test successful BLE device scan."""
        transport = BLETransport(temp_db_path.parent)

        mock_device = Mock()
        mock_device.name = "MeshCore-ABC123"
        mock_device.address = "AA:BB:CC:DD:EE:FF"
        mock_device.rssi = -50

        with patch("meshtui.transport.BleakScanner.discover", return_value=[mock_device]):
            devices = await transport.scan_devices(timeout=1.0)

        assert len(devices) == 1
        assert devices[0]["name"] == "MeshCore-ABC123"
        assert devices[0]["address"] == "AA:BB:CC:DD:EE:FF"

    @pytest.mark.asyncio
    async def test_scan_devices_filters_non_meshcore(self, temp_db_path):
        """Test that BLE scan filters out non-MeshCore devices."""
        transport = BLETransport(temp_db_path.parent)

        mock_device1 = Mock()
        mock_device1.name = "MeshCore-ABC123"
        mock_device1.address = "AA:BB:CC:DD:EE:FF"
        mock_device1.rssi = -50

        mock_device2 = Mock()
        mock_device2.name = "Other Device"
        mock_device2.address = "11:22:33:44:55:66"
        mock_device2.rssi = -60

        with patch("meshtui.transport.BleakScanner.discover", return_value=[mock_device1, mock_device2]):
            devices = await transport.scan_devices()

        assert len(devices) == 1
        assert devices[0]["name"] == "MeshCore-ABC123"

    def test_save_and_get_address(self, temp_db_path):
        """Test saving and retrieving BLE address."""
        transport = BLETransport(temp_db_path.parent)

        transport.save_address("AA:BB:CC:DD:EE:FF")
        address = transport.get_saved_address()

        assert address == "AA:BB:CC:DD:EE:FF"

    @pytest.mark.asyncio
    async def test_connect_with_address(self, mock_meshcore, temp_db_path):
        """Test BLE connection with explicit address."""
        transport = BLETransport(temp_db_path.parent)

        mock_result = Mock()
        mock_result.type = EventType.DEVICE_INFO
        mock_result.payload = {"model": "Test Device"}

        with patch("meshtui.transport.MeshCore.create_ble", return_value=mock_meshcore):
            mock_meshcore.commands.send_device_query.return_value = mock_result

            meshcore = await transport.connect(address="AA:BB:CC:DD:EE:FF")

        assert meshcore is not None
        # Address should be saved
        assert transport.get_saved_address() == "AA:BB:CC:DD:EE:FF"

    @pytest.mark.asyncio
    async def test_connect_with_scan(self, mock_meshcore, temp_db_path):
        """Test BLE connection that requires scanning."""
        transport = BLETransport(temp_db_path.parent)

        mock_device = Mock()
        mock_device.name = "MeshCore-ABC123"
        mock_device.address = "AA:BB:CC:DD:EE:FF"
        mock_device.rssi = -50

        mock_result = Mock()
        mock_result.type = EventType.DEVICE_INFO
        mock_result.payload = {"model": "Test Device"}

        with patch("meshtui.transport.BleakScanner.discover", return_value=[mock_device]), \
             patch("meshtui.transport.MeshCore.create_ble", return_value=mock_meshcore):
            mock_meshcore.commands.send_device_query.return_value = mock_result

            meshcore = await transport.connect()

        assert meshcore is not None


class TestTCPTransport:
    """Tests for TCPTransport class."""

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_meshcore):
        """Test successful TCP connection."""
        transport = TCPTransport()

        mock_result = Mock()
        mock_result.type = EventType.DEVICE_INFO
        mock_result.payload = {"model": "Test Device"}

        with patch("meshtui.transport.MeshCore.create_tcp", return_value=mock_meshcore):
            mock_meshcore.commands.send_device_query.return_value = mock_result

            meshcore = await transport.connect("192.168.1.100", port=5000)

        assert meshcore is not None

    @pytest.mark.asyncio
    async def test_connect_failure(self, mock_meshcore):
        """Test failed TCP connection."""
        transport = TCPTransport()

        with patch("meshtui.transport.MeshCore.create_tcp", return_value=mock_meshcore):
            mock_meshcore.commands.send_device_query.side_effect = Exception("Connection failed")

            meshcore = await transport.connect("192.168.1.100")

        assert meshcore is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
