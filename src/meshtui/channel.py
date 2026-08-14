#!/usr/bin/env python3
"""
Channel management for MeshTUI.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Union
from meshcore import EventType


def parse_channel_secret(key: str) -> Optional[bytes]:
    """Parse a user-supplied channel secret into exactly 16 bytes.

    Accepts a 32-character hex string (optional ``0x`` prefix, colons,
    spaces, or dashes) or a 16-character / 16-byte UTF-8 string.

    Args:
        key: Secret as entered by the user

    Returns:
        16-byte secret, or None if key is empty

    Raises:
        ValueError: If the key is present but not a valid 16-byte secret
    """
    if key is None:
        return None

    cleaned = key.strip()
    if not cleaned:
        return None

    hex_candidate = cleaned
    if hex_candidate.lower().startswith("0x"):
        hex_candidate = hex_candidate[2:]
    hex_candidate = (
        hex_candidate.replace(":", "").replace(" ", "").replace("-", "")
    )
    try:
        secret = bytes.fromhex(hex_candidate)
        if len(secret) == 16:
            return secret
    except ValueError:
        pass

    raw = cleaned.encode("utf-8")
    if len(raw) == 16:
        return raw

    raise ValueError(
        "Channel secret must be 16 bytes (32 hex characters or a 16-character string)"
    )


class ChannelManager:
    """Manages channel operations and message handling."""

    def __init__(self, meshcore):
        """Initialize channel manager.

        Args:
            meshcore: MeshCore instance
        """
        self.meshcore = meshcore
        self.logger = logging.getLogger("meshtui.channel")
        self._channels: List[Dict[str, Any]] = []
        self.low_power = False

    async def send_message(self, channel: Union[str, int], message: str) -> bool:
        """Send a message to a channel.

        Args:
            channel: Channel index (int) or channel name (str)
            message: Message text to send

        Returns:
            Dict with status info if successful, False otherwise
        """
        if not self.meshcore:
            return False

        try:
            # If channel is a string name, try to find its index
            if isinstance(channel, str):
                # Look up channel index by name
                channels = await self.get_channels()
                channel_idx = None
                for ch_info in channels:
                    if ch_info.get("name") == channel:
                        channel_idx = ch_info.get("id", 0)
                        break

                if channel_idx is None:
                    self.logger.error(f"Channel '{channel}' not found")
                    return False

                channel = channel_idx

            self.logger.info(f"Sending message to channel {channel}")
            result = await self.meshcore.commands.send_chan_msg(channel, message)

            if result.type == EventType.ERROR:
                self.logger.error(f"Failed to send channel message: {result}")
                return False

            # Extract expected_ack if present in payload
            payload = result.payload if hasattr(result, "payload") else {}
            self.logger.debug(f"Channel send result payload: {payload}")
            expected_ack = (
                payload.get("expected_ack") if isinstance(payload, dict) else None
            )

            # Return status information including expected_ack for tracking
            status_info = {
                "status": "sent",
                "result": payload,
                "expected_ack": expected_ack,
            }
            self.logger.debug(f"Channel message sent, result: {result.type}")
            return status_info

        except Exception as e:
            self.logger.error(f"Error sending channel message: {e}")
            return False

    def _normalize_channel(self, channel_id: int, channel_info: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a channel payload into the dict the UI expects."""
        channel_idx = channel_info.get("channel_idx", channel_id)
        name = channel_info.get("channel_name") or channel_info.get("name") or ""
        return {
            "id": channel_idx,
            "channel_idx": channel_idx,
            "name": name,
            **channel_info,
        }

    async def refresh(self) -> None:
        """Refresh the channels list by querying all channel slots."""
        if not self.meshcore:
            return

        try:
            self.logger.debug("Refreshing channels list")
            channels: List[Dict[str, Any]] = []
            slot_timeout = 1.0 if self.low_power else 3.0
            # Query channels 0-7 (typical range for most devices)
            for idx in range(8):
                try:
                    result = await asyncio.wait_for(
                        self.meshcore.commands.get_channel(idx), timeout=slot_timeout
                    )
                    if result.type != EventType.ERROR:
                        channel_info = result.payload or {}
                        self.logger.debug(f"Channel {idx} info: {channel_info}")
                        normalized = self._normalize_channel(idx, channel_info)
                        if normalized.get("name"):
                            channels.append(normalized)
                except asyncio.TimeoutError:
                    self.logger.debug(f"Timeout querying channel slot {idx}")
                except Exception as e:
                    self.logger.debug(f"Channel {idx} not available: {e}")
            self._channels = channels
            self.logger.info(f"Refreshed {len(channels)} named channel slots")
        except Exception as e:
            self.logger.error(f"Error refreshing channels: {e}")

    async def get_channels(self) -> List[Dict[str, Any]]:
        """Get list of available channels.

        Returns:
            List of channel information dictionaries
        """
        if not self.meshcore:
            return []

        try:
            # Prefer a previously queried cache so the UI does not
            # re-probe every slot on every refresh.
            if self._channels:
                self.logger.debug(
                    f"Returning {len(self._channels)} cached channels"
                )
                return list(self._channels)

            # MeshCore itself does not populate channel_info_list;
            # MeshConnection stores events on its own instance. Still
            # honor the attribute if a caller or test set it.
            if getattr(self.meshcore, "channel_info_list", None):
                channels = []
                for ch_info in self.meshcore.channel_info_list:
                    channel_idx = ch_info.get("channel_idx", 0)
                    normalized = self._normalize_channel(channel_idx, ch_info)
                    if normalized.get("name"):
                        channels.append(normalized)
                if channels:
                    self._channels = channels
                    self.logger.info(f"Found {len(channels)} channels")
                    return list(channels)

            await self.refresh()
            self.logger.info(f"Found {len(self._channels)} channels")
            return list(self._channels)

        except Exception as e:
            self.logger.error(f"Error getting channels: {e}")
            return []

    async def join_channel(self, channel_name: str, key: str = "") -> bool:
        """Join a channel by name and optional key.

        Args:
            channel_name: Name of the channel
            key: Optional encryption key

        Returns:
            True if joined successfully, False otherwise
        """
        if not self.meshcore:
            return False

        try:
            # Find an available channel slot (0-7)
            channels = await self.get_channels()
            used_slots = [ch.get("id", -1) for ch in channels]

            available_slot = None
            for slot in range(8):
                if slot not in used_slots:
                    available_slot = slot
                    break

            if available_slot is None:
                self.logger.error("No available channel slots")
                return False

            # Set the channel
            secret = parse_channel_secret(key) if key else b"\x00" * 16
            result = await self.meshcore.commands.set_channel(
                available_slot, channel_name, secret
            )

            if result.type == EventType.ERROR:
                self.logger.error(f"Failed to join channel: {result}")
                return False

            self._channels = []
            self.logger.info(
                f"Successfully joined channel '{channel_name}' in slot {available_slot}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Error joining channel: {e}")
            return False
