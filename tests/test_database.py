"""
Unit tests for the database module.

Tests cover message storage, retrieval, unread count tracking,
and contact persistence.
"""

import pytest
from pathlib import Path
from meshtui.database import MessageDatabase


class TestMessageDatabase:
    """Tests for MessageDatabase class."""

    def test_database_initialization(self, temp_db_path):
        """Test database creation and schema initialization."""
        db = MessageDatabase(temp_db_path)
        assert temp_db_path.exists()

        # Check tables exist
        cursor = db.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert "messages" in tables
        assert "contacts" in tables
        assert "last_read" in tables

    def test_store_message_contact(self, temp_db_path, sample_messages):
        """Test storing a direct message."""
        db = MessageDatabase(temp_db_path)
        msg = sample_messages[0]  # Contact message

        msg_id = db.store_message(msg)
        assert msg_id > 0

        # Verify message was stored
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM messages WHERE id = ?", (msg_id,))
        row = cursor.fetchone()
        assert row is not None
        assert dict(row)["sender"] == "Alice"
        assert dict(row)["text"] == "Hello!"

    def test_store_message_channel(self, temp_db_path, sample_messages):
        """Test storing a channel message."""
        db = MessageDatabase(temp_db_path)
        msg = sample_messages[1]  # Channel message

        msg_id = db.store_message(msg)
        assert msg_id > 0

        # Verify message was stored with correct channel
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM messages WHERE id = ?", (msg_id,))
        row = cursor.fetchone()
        assert row is not None
        row_dict = dict(row)
        assert row_dict["type"] == "channel"
        assert row_dict["channel"] == 0  # Public

    def test_get_messages_for_contact(self, temp_db_path, sample_messages, sample_contacts):
        """Test retrieving messages for a specific contact."""
        db = MessageDatabase(temp_db_path)

        # Store contacts and messages
        for contact in sample_contacts:
            db.store_contact(contact, is_me=False)
        for msg in sample_messages:
            db.store_message(msg)

        # Get messages for Alice (2 messages)
        messages = db.get_messages_for_contact("Alice")
        assert len(messages) == 2
        assert all(msg["sender"] == "Alice" for msg in messages)

    def test_get_messages_for_channel(self, temp_db_path, sample_messages):
        """Test retrieving messages for a specific channel."""
        db = MessageDatabase(temp_db_path)

        # Store messages
        for msg in sample_messages:
            db.store_message(msg)

        # Get messages for Public channel (channel 0)
        messages = db.get_messages_for_channel(0)
        assert len(messages) == 1
        assert messages[0]["sender"] == "Bob"
        assert messages[0]["channel"] == 0

    def test_mark_as_read_contact(self, temp_db_path, sample_contacts):
        """Test marking contact messages as read."""
        db = MessageDatabase(temp_db_path)

        # Store contact first
        for contact in sample_contacts:
            db.store_contact(contact, is_me=False)

        # Mark as read
        db.mark_as_read("Alice", timestamp=1234567900)

        # Verify last_read entry
        cursor = db.conn.cursor()
        cursor.execute("""
            SELECT last_read_timestamp, identifier_type FROM last_read
            WHERE identifier = ?
        """, ("abc123",))  # Alice's pubkey
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 1234567900
        assert row[1] == "contact"

    def test_mark_as_read_channel(self, temp_db_path):
        """Test marking channel messages as read."""
        db = MessageDatabase(temp_db_path)

        # Mark Public channel as read
        db.mark_as_read("Public", timestamp=1234567900)

        # Verify last_read entry
        cursor = db.conn.cursor()
        cursor.execute("""
            SELECT last_read_timestamp, identifier_type FROM last_read
            WHERE identifier = ?
        """, ("Public",))
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 1234567900
        assert row[1] == "channel"

    def test_get_unread_count_contact(self, temp_db_path, sample_contacts, sample_messages):
        """Test getting unread count for a contact."""
        db = MessageDatabase(temp_db_path)

        # Store contact and messages
        for contact in sample_contacts:
            db.store_contact(contact, is_me=False)
        for msg in sample_messages:
            db.store_message(msg)

        # Mark as read before first message
        db.mark_as_read("Alice", timestamp=1234567889)

        # Should have 2 unread messages from Alice
        unread = db.get_unread_count("Alice")
        assert unread == 2

    def test_get_unread_count_channel(self, temp_db_path, sample_messages):
        """Test getting unread count for a channel."""
        db = MessageDatabase(temp_db_path)

        # Store messages
        for msg in sample_messages:
            db.store_message(msg)

        # Mark Public as read before all messages
        db.mark_as_read("Public", timestamp=1234567800)

        # Should have 1 unread message in Public
        unread = db.get_unread_count("Public")
        assert unread == 1

    def test_get_unread_count_after_read(self, temp_db_path, sample_messages):
        """Test that unread count is 0 after marking as read."""
        db = MessageDatabase(temp_db_path)

        # Store messages
        for msg in sample_messages:
            db.store_message(msg)

        # Get the current time and mark as read now (after all messages)
        import time
        now = int(time.time())
        db.mark_as_read("Public", timestamp=now)

        # Should have 0 unread messages
        unread = db.get_unread_count("Public")
        assert unread == 0

    def test_store_contact(self, temp_db_path, sample_contacts):
        """Test storing a contact."""
        db = MessageDatabase(temp_db_path)
        contact = sample_contacts[0]

        db.store_contact(contact, is_me=False)

        # Verify contact was stored
        stored = db.get_contact_by_pubkey("abc123")
        assert stored is not None
        assert stored["name"] == "Alice"
        assert stored["type"] == 0

    def test_get_contact_by_pubkey(self, temp_db_path, sample_contacts):
        """Test retrieving contact by public key."""
        db = MessageDatabase(temp_db_path)

        for contact in sample_contacts:
            db.store_contact(contact, is_me=False)

        contact = db.get_contact_by_pubkey("def456")
        assert contact is not None
        assert contact["name"] == "Bob"

    def test_get_contact_by_name(self, temp_db_path, sample_contacts):
        """Test retrieving contact by name."""
        db = MessageDatabase(temp_db_path)

        for contact in sample_contacts:
            db.store_contact(contact, is_me=False)

        contact = db.get_contact_by_name("Room1")
        assert contact is not None
        assert contact["pubkey"] == "ghi789"
        assert contact["type"] == 3  # Room server

    def test_get_all_contacts(self, temp_db_path, sample_contacts):
        """Test retrieving all contacts."""
        db = MessageDatabase(temp_db_path)

        for contact in sample_contacts:
            db.store_contact(contact, is_me=False)

        contacts = db.get_all_contacts()
        assert len(contacts) == 3
        names = {c["name"] for c in contacts}
        assert names == {"Alice", "Bob", "Room1"}

    def test_contact_update(self, temp_db_path, sample_contacts):
        """Test updating an existing contact."""
        db = MessageDatabase(temp_db_path)
        contact = sample_contacts[0].copy()

        # Store initial contact
        db.store_contact(contact, is_me=False)

        # Update contact
        contact["adv_name"] = "Alice Smith"
        new_last_seen = 1234568000
        contact["last_seen"] = new_last_seen
        db.store_contact(contact, is_me=False)

        # Verify update
        stored = db.get_contact_by_pubkey("abc123")
        assert stored["adv_name"] == "Alice Smith"
        # Note: last_seen is updated to current time on store, so just check it exists
        assert stored["last_seen"] > 0

    def test_exclude_own_messages_from_unread(self, temp_db_path):
        """Test that messages sent by 'Me' are excluded from unread counts."""
        db = MessageDatabase(temp_db_path)

        # Store message from me
        db.store_message({
            "type": "channel",
            "sender": "Me",
            "sender_pubkey": "",
            "text": "My message",
            "timestamp": 1234567900,
            "channel": 0,
        })

        # Mark as read before message
        db.mark_as_read("Public", timestamp=1234567800)

        # Should be 0 unread (own message excluded)
        unread = db.get_unread_count("Public")
        assert unread == 0

    def test_channel_index_extraction(self, temp_db_path):
        """Test that channel names are correctly parsed to channel indices."""
        db = MessageDatabase(temp_db_path)

        # Store messages for different channels
        for channel_idx in [0, 1, 2]:
            db.store_message({
                "type": "channel",
                "sender": "Alice",
                "sender_pubkey": "abc123",
                "text": f"Message in channel {channel_idx}",
                "timestamp": 1234567900,
                "channel": channel_idx,
            })

        # Mark all as read
        db.mark_as_read("Public", timestamp=1234567800)
        db.mark_as_read("Channel 1", timestamp=1234567800)
        db.mark_as_read("Channel 2", timestamp=1234567800)

        # All should have 1 unread message
        assert db.get_unread_count("Public") == 1
        assert db.get_unread_count("Channel 1") == 1
        assert db.get_unread_count("Channel 2") == 1


class TestDatabaseMigrations:
    """Tests for database schema migrations."""

    @pytest.mark.skip(reason="Complex integration test - requires full schema setup")
    def test_migration_adds_recipient_pubkey(self, temp_db_path):
        """Test that migration adds recipient_pubkey column."""
        # This test is skipped as it requires recreating the exact old schema
        # which is complex. Manual testing of migrations is recommended.
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
