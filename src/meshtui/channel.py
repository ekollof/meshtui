#!/usr/bin/env python3
"""
Channel management for MeshTUI.
"""

import asyncio
import logging
from typing import List, Dict, Any, Union
from meshcore import EventType


class ChannelManager:
    """Manages channel operations and message handling."""

    def __init__(self, meshcore):
        """Initialize channel manager.

        Args:
            meshcore: MeshCore instance
        """
        self.meshcore = meshcore
        self.logger = logging.getLogger("meshtui.channel")

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

    async def refresh(self) -> None:
        """Refresh the channels list by querying all channel slots."""
        if not self.meshcore:
            return

        try:
            self.logger.debug("Refreshing channels list")
            # Query channels 0-7 (typical range for most devices)
            for idx in range(8):
                try:
                    result = await self.meshcore.commands.get_channel(idx)
                    if result.type != EventType.ERROR:
                        self.logger.debug(f"Channel {idx} info: {result.payload}")
                except Exception as e:
                    self.logger.debug(f"Channel {idx} not available: {e}")
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
            # Use stored channel info from events if available
            if (
                hasattr(self.meshcore, "channel_info_list")
                and self.meshcore.channel_info_list
            ):
                channels = []
                for ch_info in self.meshcore.channel_info_list:
                    ch_name = ch_info.get("channel_name", "")
                    if ch_name:  # Only include channels with names
                        channels.append(
                            {
                                "id": ch_info.get("channel_idx", 0),
                                "name": ch_name,
                                **ch_info,
                            }
                        )
                self.logger.info(f"Found {len(channels)} channels")
                return channels

            # Fallback: try to get channel information via commands
            channels = []
            for channel_id in range(8):  # MeshCore supports up to 8 channels
                try:
                    channel_result = await asyncio.wait_for(
                        self.meshcore.commands.get_channel(channel_id), timeout=2.0
                    )
                    if channel_result.type != EventType.ERROR:
                        channel_info = channel_result.payload
                        if channel_info and channel_info.get("channel_name"):
                            channels.append(
                                {
                                    "id": channel_id,
                                    "name": channel_info.get("channel_name", "Unknown"),
                                    **channel_info,
                                }
                            )
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    continue

            self.logger.info(f"Found {len(channels)} channels")
            return channels

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
            secret = key.encode("utf-8") if key else b"\x00" * 16
            result = await self.meshcore.commands.set_channel(
                available_slot, channel_name, secret[:16].ljust(16, b"\x00")
            )

            if result.type == EventType.ERROR:
                self.logger.error(f"Failed to join channel: {result}")
                return False

            self.logger.info(
                f"Successfully joined channel '{channel_name}' in slot {available_slot}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Error joining channel: {e}")
            return False
