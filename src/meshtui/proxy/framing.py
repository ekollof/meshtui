"""MeshCore companion framing used by the TCP proxy.

Host → device frames are marked 0x3C ('<'). Device → host frames are
marked 0x3E ('>'). That is the same convention MeshCore uses on serial,
BLE, and native WiFi TCP. The Python client (`meshcore.tcp_cx`) looks
for 0x3E on receive and writes 0x3C on send.
"""

from __future__ import annotations

from typing import Optional, Tuple

HOST_TO_DEVICE = 0x3C
DEVICE_TO_HOST = 0x3E
FRAME_MARKERS = (DEVICE_TO_HOST, HOST_TO_DEVICE)
MAX_FRAME_SIZE = 300


def encode_frame(payload: bytes, marker: int = DEVICE_TO_HOST) -> bytes:
    """Wrap a payload in a MeshCore companion frame."""
    return bytes([marker]) + len(payload).to_bytes(2, "little") + payload


def find_frame_start(data: bytes) -> int:
    """Return the index of the first valid start marker, or -1."""
    pos_device = data.find(bytes([DEVICE_TO_HOST]))
    pos_host = data.find(bytes([HOST_TO_DEVICE]))
    candidates = [p for p in (pos_device, pos_host) if p >= 0]
    return min(candidates) if candidates else -1


def parse_frames(buffer: bytes) -> Tuple[list[bytes], bytes]:
    """Extract complete payloads from a byte buffer.

    Returns (payloads, leftover). Leftover is any incomplete trailing
    frame (or unparsed prefix with no start marker).
    """
    payloads: list[bytes] = []
    data = buffer

    while data:
        start = find_frame_start(data)
        if start < 0:
            return payloads, b""
        data = data[start:]
        if len(data) < 3:
            return payloads, data
        size = int.from_bytes(data[1:3], "little")
        if size > MAX_FRAME_SIZE:
            data = data[1:]
            continue
        if len(data) < 3 + size:
            return payloads, data
        payloads.append(data[3 : 3 + size])
        data = data[3 + size :]

    return payloads, b""


def header_size(header: bytes) -> Optional[int]:
    """Parse payload length from a 3-byte header, or None if invalid."""
    if len(header) != 3 or header[0] not in FRAME_MARKERS:
        return None
    size = int.from_bytes(header[1:3], "little")
    if size > MAX_FRAME_SIZE:
        return None
    return size
