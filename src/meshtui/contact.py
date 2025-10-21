#!/usr/bin/env python3
"""
Contact and node management for MeshTUI.
"""

import logging
from typing import Optional, List, Dict, Any
from meshcore import EventType


class ContactManager:
    """Manages contacts and direct messaging."""

    def __init__(self, meshcore):
        """Initialize contact manager.

        Args:
            meshcore: MeshCore instance
        """
        self.meshcore = meshcore
        self.contacts: List[Dict[str, Any]] = []
        self.logger = logging.getLogger("meshtui.contact")

    async def refresh(self) -> None:
        """Refresh the contacts list from the device."""
        if not self.meshcore:
            return

        try:
            result = await self.meshcore.commands.get_contacts()
            if result.type == EventType.ERROR:
                error_code = result.payload.get("error_code", "unknown")
                if error_code == 4:
                    self.logger.warning(
                        "Device busy, skipping contact refresh (error code 4)"
                    )
                else:
                    self.logger.error(f"Failed to get contacts: {result}")
                return

            # Convert contacts dict to list
            contacts_dict = result.payload
            self.contacts = []

            for public_key, contact_data in contacts_dict.items():
                contact_data["public_key"] = public_key
                # Normalize name field
                name = (
                    contact_data.get("name")
                    or contact_data.get("adv_name")
                    or contact_data.get("nick")
                    or contact_data.get("display_name")
                    or "Unknown"
                )
                contact_data["name"] = name
                self.contacts.append(contact_data)

            self.logger.info(f"Refreshed {len(self.contacts)} contacts")

        except Exception as e:
            self.logger.error(f"Error refreshing contacts: {e}")

    def get_all(self) -> List[Dict[str, Any]]:
        """Get all contacts.

        Returns:
            List of contact dictionaries
        """
        return self.contacts

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a contact by their name.

        Args:
            name: Contact name to search for

        Returns:
            Contact dictionary if found, None otherwise
        """
        # Try using MeshCore's built-in lookup first
        if self.meshcore and hasattr(self.meshcore, "get_contact_by_name"):
            contact = self.meshcore.get_contact_by_name(name)
            if contact:
                return contact

        # Fallback: manual search
        for contact in self.contacts:
            if contact.get("adv_name") == name or contact.get("name") == name:
                return contact
        return None

    def get_by_key(self, public_key: str) -> Optional[Dict[str, Any]]:
        """Get a contact by their public key or prefix.

        Args:
            public_key: Public key or prefix to search for

        Returns:
            Contact dictionary if found, None otherwise
        """
        # Try using MeshCore's built-in lookup first (handles prefixes)
        if self.meshcore and hasattr(self.meshcore, "get_contact_by_key_prefix"):
            contact = self.meshcore.get_contact_by_key_prefix(public_key)
            if contact:
                return contact

        # Fallback: manual search
        for contact in self.contacts:
            key = contact.get("public_key", "")
            # Match full key or prefix
            if key == public_key or key.startswith(public_key):
                return contact
        return None

    def is_room_server(self, contact: Dict[str, Any]) -> bool:
        """Check if a contact is a room server.

        Args:
            contact: Contact dictionary

        Returns:
            True if room server (type 3), False otherwise
        """
        return contact.get("type") == 3

    def is_repeater(self, contact: Dict[str, Any]) -> bool:
        """Check if a contact is a repeater.

        Args:
            contact: Contact dictionary

        Returns:
            True if repeater (type 2), False otherwise
        """
        return contact.get("type") == 2

    def is_sensor(self, contact: Dict[str, Any]) -> bool:
        """Check if a contact is a sensor node.

        Args:
            contact: Contact dictionary

        Returns:
            True if sensor (type 4), False otherwise
        """
        return contact.get("type") == 4

    def get_node_type_display(self, contact: Dict[str, Any]) -> str:
        """Get a display string for the node type.

        Args:
            contact: Contact dictionary

        Returns:
            Human-readable node type string
        """
        node_type = contact.get("type", 0)
        type_names = {
            0: "Companion",
            1: "Companion",
            2: "Repeater",
            3: "Room Server",
            4: "Sensor",
        }
        return type_names.get(node_type, "Unknown")

    async def send_message(
        self, recipient_name: str, message: str, use_retry: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Send a message to a contact.

        Uses send_msg_with_retry() by default for automatic retries and flood routing.
        For room servers/repeaters/sensors (type 2, 3, 4) uses send_cmd().

        Args:
            recipient_name: The display name of the contact
            message: The message text to send
            use_retry: Whether to use automatic retry with flood routing (default: True)

        Returns:
            Dict with status info if successful, None if failed
        """
        if not self.meshcore:
            return None

        try:
            # Look up the contact to get their pubkey/id
            contact = self.get_by_name(recipient_name)
            if not contact:
                self.logger.error(f"Contact '{recipient_name}' not found")
                return None

            # Try to get the recipient identifier
            recipient = contact.get("public_key")
            if not recipient:
                self.logger.error(
                    f"Contact '{recipient_name}' has no public_key/id field"
                )
                return None

            # Send message using send_msg_with_retry for automatic retries
            contact_type = contact.get("type", 1)
            self.logger.info(
                f"Sending message to {recipient_name} (type {contact_type}, key: {recipient[:16]}...)"
            )

            if use_retry:
                # Use retry logic with flood routing fallback
                result = await self.meshcore.commands.send_msg_with_retry(
                    recipient,
                    message,
                    max_attempts=3,
                    max_flood_attempts=2,
                    flood_after=2,
                    min_timeout=5,
                )
            else:
                # Simple send without retry
                result = await self.meshcore.commands.send_msg(recipient, message)

            if not result or result.type == EventType.ERROR:
                self.logger.error(f"Failed to send: {result}")
                return None

            # Extract expected_ack if present in payload
            payload = result.payload if hasattr(result, "payload") else {}
            expected_ack = (
                payload.get("expected_ack") if isinstance(payload, dict) else None
            )

            # Return status information including expected_ack for tracking
            status_info = {
                "status": "sent",
                "result": payload,
                "expected_ack": expected_ack,
            }
            self.logger.info(f"Message sent successfully (retry mode: {use_retry})")
            return status_info

        except Exception as e:
            self.logger.error(f"Error sending message: {e}")
            import traceback

            self.logger.debug(f"Traceback: {traceback.format_exc()}")
            return None
