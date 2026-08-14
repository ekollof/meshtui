"""Tests for MeshCore companion frame encoding used by the TCP proxy."""

import asyncio

import pytest

from meshtui.proxy.backends.serial import SerialBackend
from meshtui.proxy.framing import (
    DEVICE_TO_HOST,
    HOST_TO_DEVICE,
    encode_frame,
    find_frame_start,
    parse_frames,
)


def test_encode_host_to_device():
    payload = b"\x01\x03      mccli"
    frame = encode_frame(payload, HOST_TO_DEVICE)
    assert frame[0] == HOST_TO_DEVICE
    assert int.from_bytes(frame[1:3], "little") == len(payload)
    assert frame[3:] == payload


def test_encode_device_to_host():
    payload = b"\x05\x01" + b"x" * 77
    frame = encode_frame(payload, DEVICE_TO_HOST)
    assert frame[0] == DEVICE_TO_HOST
    assert len(frame) == 3 + 79


def test_parse_device_to_host_with_leading_junk():
    payload = b"\x05hello"
    raw = b"debug line\n" + encode_frame(payload, DEVICE_TO_HOST)
    frames, leftover = parse_frames(raw)
    assert frames == [payload]
    assert leftover == b""


def test_parse_legacy_0x3c_device_frame():
    payload = b"\x05legacy"
    frames, leftover = parse_frames(encode_frame(payload, HOST_TO_DEVICE))
    assert frames == [payload]
    assert leftover == b""


def test_find_frame_start_prefers_earliest_marker():
    data = b"xx" + bytes([HOST_TO_DEVICE]) + b"yy" + bytes([DEVICE_TO_HOST])
    assert find_frame_start(data) == 2


def test_tcp_broadcast_uses_device_to_host_marker():
    """Regression for #11: meshcore.tcp_cx looks for 0x3E on receive."""
    payload = b"\x05\x01" + b"self-info"
    pkt = encode_frame(payload, DEVICE_TO_HOST)
    assert pkt[0] == 0x3E
    assert pkt[0] != 0x3C


@pytest.mark.asyncio
async def test_serial_send_uses_host_to_device_marker():
    backend = SerialBackend("/dev/null")

    class _Transport:
        def __init__(self):
            self.written = b""

        def write(self, data):
            self.written = data

    backend.transport = _Transport()
    payload = b"\x01\x03      mccli"
    await backend.send_frame(payload)
    assert backend.transport.written[0] == HOST_TO_DEVICE
    assert backend.transport.written[3:] == payload


@pytest.mark.asyncio
async def test_serial_handle_rx_0x3e_and_legacy_0x3c():
    backend = SerialBackend("/dev/null")
    received = []

    async def _cb(frame):
        received.append(frame)

    backend.frame_callback = _cb
    payload_new = b"\x05new"
    payload_old = b"\x05old"
    backend.handle_rx(b"uart junk" + encode_frame(payload_new, DEVICE_TO_HOST))
    backend.handle_rx(encode_frame(payload_old, HOST_TO_DEVICE))
    await asyncio.sleep(0)
    assert received == [payload_new, payload_old]


@pytest.mark.asyncio
async def test_serial_handle_rx_split_across_chunks():
    backend = SerialBackend("/dev/null")
    received = []

    async def _cb(frame):
        received.append(frame)

    backend.frame_callback = _cb
    payload = b"\x05" + b"z" * 20
    raw = encode_frame(payload, DEVICE_TO_HOST)
    backend.handle_rx(raw[:2])
    backend.handle_rx(raw[2:8])
    backend.handle_rx(raw[8:])
    await asyncio.sleep(0)
    assert received == [payload]
