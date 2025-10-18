"""
Unit tests for manager modules (contact, channel, room).

Tests cover contact management, channel operations, and room server handling.
"""

import pytest
from unittest.mock import Mock, AsyncMock
from meshtui.contact import ContactManager
from meshtui.channel import ChannelManager
from meshtui.room import RoomManager


class TestContactManager:
    """Tests for ContactManager class."""

    def test_initialization(self, mock_meshcore):
        """Test ContactManager initialization."""
        manager = ContactManager(mock_meshcore)
        assert manager.meshcore == mock_meshcore
        assert manager.contacts == []

    @pytest.mark.asyncio
    async def test_refresh_contacts(self, mock_meshcore, sample_contacts):
        """Test refreshing contacts from device."""
        manager = ContactManager(mock_meshcore)

        # Build contacts dict by pubkey
        contacts_dict = {
            "abc123": {"name": "Alice", "type": 0, "last_seen": 1234567890},
            "def456": {"name": "Bob", "type": 0, "last_seen": 1234567900},
            "ghi789": {"name": "Room1", "type": 3, "last_seen": 1234567800},
        }

        mock_result = Mock()
        mock_result.type = Mock()
        mock_result.payload = contacts_dict
        mock_meshcore.commands.get_contacts.return_value = mock_result

        await manager.refresh()

        assert len(manager.contacts) == 3
        # Check that public_key was added
        assert any(c.get("public_key") == "abc123" for c in manager.contacts)

    def test_get_all_contacts(self, mock_meshcore, sample_contacts):
        """Test retrieving all contacts."""
        manager = ContactManager(mock_meshcore)
        manager.contacts = sample_contacts

        all_contacts = manager.get_all()

        assert len(all_contacts) == 3
        assert all_contacts[0]["name"] == "Alice"

    def test_get_by_name(self, mock_meshcore, sample_contacts):
        """Test retrieving contact by name."""
        manager = ContactManager(mock_meshcore)
        # Update contacts to include public_key field
        contacts_with_pubkey = []
        for c in sample_contacts:
            contact = c.copy()
            contact['public_key'] = contact.pop('pubkey')
            contacts_with_pubkey.append(contact)
        manager.contacts = contacts_with_pubkey

        contact = manager.get_by_name("Bob")

        assert contact is not None
        assert contact["public_key"] == "def456"

    def test_get_by_name_not_found(self, mock_meshcore, sample_contacts):
        """Test retrieving non-existent contact."""
        manager = ContactManager(mock_meshcore)
        contacts_with_pubkey = []
        for c in sample_contacts:
            contact = c.copy()
            contact['public_key'] = contact.pop('pubkey')
            contacts_with_pubkey.append(contact)
        manager.contacts = contacts_with_pubkey

        contact = manager.get_by_name("Charlie")

        assert contact is None

    def test_get_by_key(self, mock_meshcore, sample_contacts):
        """Test retrieving contact by public key."""
        manager = ContactManager(mock_meshcore)
        contacts_with_pubkey = []
        for c in sample_contacts:
            contact = c.copy()
            contact['public_key'] = contact.pop('pubkey')
            contacts_with_pubkey.append(contact)
        manager.contacts = contacts_with_pubkey

        contact = manager.get_by_key("abc123")

        assert contact is not None
        assert contact["name"] == "Alice"

    def test_get_by_key_prefix_match(self, mock_meshcore, sample_contacts):
        """Test retrieving contact by partial public key."""
        manager = ContactManager(mock_meshcore)
        contacts_with_pubkey = []
        for c in sample_contacts:
            contact = c.copy()
            contact['public_key'] = contact.pop('pubkey')
            contacts_with_pubkey.append(contact)
        manager.contacts = contacts_with_pubkey

        contact = manager.get_by_key("abc")  # Partial key

        assert contact is not None
        assert contact["name"] == "Alice"

    def test_is_room_server(self, mock_meshcore, sample_contacts):
        """Test identifying room server contacts."""
        manager = ContactManager(mock_meshcore)

        # Room server (type 3)
        room_contact = sample_contacts[2]
        assert manager.is_room_server(room_contact) is True

        # Regular contact (type 0)
        regular_contact = sample_contacts[0]
        assert manager.is_room_server(regular_contact) is False

    def test_is_repeater(self, mock_meshcore):
        """Test identifying repeater contacts."""
        manager = ContactManager(mock_meshcore)

        # Repeater is type 2, not type 1
        repeater_contact = {"type": 2}
        assert manager.is_repeater(repeater_contact) is True

        regular_contact = {"type": 0}
        assert manager.is_repeater(regular_contact) is False

    @pytest.mark.asyncio
    async def test_send_message(self, mock_meshcore):
        """Test sending a message to a contact."""
        manager = ContactManager(mock_meshcore)

        # Set up contact lookup
        manager.contacts = [{"name": "Alice", "public_key": "abc123", "type": 0}]

        mock_result = Mock()
        mock_result.type = Mock()  # Not ERROR type
        mock_meshcore.commands.send_msg.return_value = mock_result

        result = await manager.send_message("Alice", "Hello!")

        mock_meshcore.commands.send_msg.assert_called_once_with("abc123", "Hello!")
        assert result is not None
        assert result['status'] == 'sent'


class TestChannelManager:
    """Tests for ChannelManager class."""

    def test_initialization(self, mock_meshcore):
        """Test ChannelManager initialization."""
        manager = ChannelManager(mock_meshcore)
        assert manager.meshcore == mock_meshcore

    @pytest.mark.asyncio
    async def test_get_channels(self, mock_meshcore):
        """Test getting channels from device."""
        manager = ChannelManager(mock_meshcore)

        # Mock channel_info_list
        mock_meshcore.channel_info_list = [
            {"channel_idx": 0, "channel_name": "Public"},
            {"channel_idx": 1, "channel_name": "Private"},
        ]

        channels = await manager.get_channels()

        assert len(channels) == 2
        assert channels[0]["name"] == "Public"
        assert channels[0]["id"] == 0

    @pytest.mark.asyncio
    async def test_send_channel_message_by_index(self, mock_meshcore):
        """Test sending a channel message by index."""
        manager = ChannelManager(mock_meshcore)

        mock_result = Mock()
        mock_result.type = Mock()  # Not ERROR type
        mock_meshcore.commands.send_chan_msg.return_value = mock_result

        result = await manager.send_message(0, "Hello channel!")

        mock_meshcore.commands.send_chan_msg.assert_called_once_with(0, "Hello channel!")
        assert result is True

    @pytest.mark.asyncio
    async def test_send_channel_message_by_name(self, mock_meshcore):
        """Test sending a channel message by name."""
        manager = ChannelManager(mock_meshcore)

        # Mock get_channels to return channel list
        mock_meshcore.channel_info_list = [
            {"channel_idx": 0, "channel_name": "Public"},
        ]

        mock_result = Mock()
        mock_result.type = Mock()  # Not ERROR type
        mock_meshcore.commands.send_chan_msg.return_value = mock_result

        result = await manager.send_message("Public", "Hello!")

        mock_meshcore.commands.send_chan_msg.assert_called_once_with(0, "Hello!")
        assert result is True

    @pytest.mark.asyncio
    async def test_join_channel(self, mock_meshcore):
        """Test joining a channel."""
        manager = ChannelManager(mock_meshcore)

        # Mock existing channels
        mock_meshcore.channel_info_list = [
            {"channel_idx": 0, "channel_name": "Public"},
        ]

        mock_result = Mock()
        mock_result.type = Mock()  # Not ERROR type
        mock_meshcore.commands.set_channel.return_value = mock_result

        result = await manager.join_channel("Test Channel", "secretkey")

        # Should use slot 1 (since 0 is taken)
        mock_meshcore.commands.set_channel.assert_called_once()
        assert result is True


class TestRoomManager:
    """Tests for RoomManager class."""

    def test_initialization(self, mock_meshcore):
        """Test RoomManager initialization."""
        messages = []
        manager = RoomManager(mock_meshcore, messages)

        assert manager.meshcore == mock_meshcore
        assert manager.message_store == messages
        assert manager.logged_in_rooms == {}

    @pytest.mark.asyncio
    async def test_login_timeout(self, mock_meshcore):
        """Test logging into a room server with timeout."""
        manager = RoomManager(mock_meshcore, [])

        room_contact = {
            "name": "Room1",
            "public_key": "room123",
            "type": 3,
        }

        mock_result = Mock()
        mock_result.type = Mock()  # Not ERROR type
        mock_meshcore.commands.send_login.return_value = mock_result

        # This will timeout waiting for login event
        success = await manager.login("Room1", room_contact, "password123")

        # Should timeout and return False
        assert success is False

    @pytest.mark.asyncio
    async def test_logout(self, mock_meshcore):
        """Test logging out of a room server."""
        manager = RoomManager(mock_meshcore, [])

        # Set up logged in room
        manager.logged_in_rooms["Room1"] = True
        manager.room_pubkeys["Room1"] = "room123"

        mock_result = Mock()
        mock_result.type = Mock()  # Not ERROR type
        mock_meshcore.commands.send_logout.return_value = mock_result

        success = await manager.logout("Room1", "room123")

        mock_meshcore.commands.send_logout.assert_called_once_with("room123")
        assert success is True
        assert manager.logged_in_rooms["Room1"] is False

    def test_is_logged_in(self, mock_meshcore):
        """Test checking if logged into a room."""
        manager = RoomManager(mock_meshcore, [])

        manager.logged_in_rooms["Room1"] = True

        assert manager.is_logged_in("Room1") is True
        assert manager.is_logged_in("Room2") is False

    def test_is_admin(self, mock_meshcore):
        """Test checking admin status in a room."""
        manager = RoomManager(mock_meshcore, [])

        manager.room_admin_status["Room1"] = True
        manager.room_admin_status["Room2"] = False

        assert manager.is_admin("Room1") is True
        assert manager.is_admin("Room2") is False

    def test_get_room_by_pubkey(self, mock_meshcore):
        """Test retrieving room name by public key."""
        manager = RoomManager(mock_meshcore, [])

        manager.pubkey_to_room["room123"] = "Room1"

        room_name = manager.get_room_by_pubkey("room123")

        assert room_name == "Room1"

    def test_get_room_by_pubkey_not_found(self, mock_meshcore):
        """Test retrieving non-existent room."""
        manager = RoomManager(mock_meshcore, [])

        room_name = manager.get_room_by_pubkey("nonexistent")

        assert room_name is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
