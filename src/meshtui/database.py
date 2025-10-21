"""Database layer for persistent message and contact storage."""

import sqlite3
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime


class MessageDatabase:
    """SQLite database for storing messages and contacts."""

    def __init__(self, db_path: Path):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.logger = logging.getLogger("meshtui.database")
        self.conn = None
        self._init_database()

    def _init_database(self):
        """Initialize database schema."""
        try:
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self.conn.row_factory = sqlite3.Row  # Return rows as dicts

            cursor = self.conn.cursor()

            # Messages table
            # Uses public_key-based lookups for robustness against name changes
            # Note: sender_pubkey and recipient_pubkey store public keys from meshcore API
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    sender_pubkey TEXT,
                    recipient_pubkey TEXT,
                    actual_sender TEXT,
                    actual_sender_pubkey TEXT,
                    text TEXT NOT NULL,
                    timestamp INTEGER,
                    channel INTEGER,
                    snr REAL,
                    path_len INTEGER,
                    txt_type INTEGER,
                    signature TEXT,
                    raw_data TEXT,
                    received_at INTEGER NOT NULL,
                    ack_code TEXT,
                    delivery_status TEXT DEFAULT 'sent',
                    repeat_count INTEGER DEFAULT 0,
                    last_ack_time INTEGER
                )
            """
            )

            # Contacts table
            # Field naming convention: "public_key" matches meshcore API (reader.py line 81)
            # This is the canonical identifier for contacts throughout the codebase
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS contacts (
                    public_key TEXT PRIMARY KEY,  -- Canonical field name from meshcore API
                    name TEXT NOT NULL,           -- Display name
                    adv_name TEXT,                -- Advertised name
                    type INTEGER,                 -- Node type: 0=Companion, 1=Companion, 2=Repeater, 3=Room Server, 4=Sensor
                    is_me INTEGER DEFAULT 0,      -- 1 if this is the current user's contact
                    last_seen INTEGER NOT NULL,   -- Unix timestamp
                    first_seen INTEGER NOT NULL,  -- Unix timestamp
                    raw_data TEXT,                -- JSON of full contact data
                    notes TEXT DEFAULT ''         -- User notes for this contact
                )
            """
            )

            # Last read tracking table - uses public_key for contacts, name for channels
            # identifier: contact public_key OR channel name (e.g., "Public", "Channel 1")
            # identifier_type: "contact" or "channel"
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS last_read (
                    identifier TEXT PRIMARY KEY,
                    identifier_type TEXT NOT NULL,
                    last_read_timestamp INTEGER NOT NULL
                )
            """
            )

            # Create indexes for efficient queries
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_sender_pubkey 
                ON messages(sender_pubkey)
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_actual_sender_pubkey 
                ON messages(actual_sender_pubkey)
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_signature 
                ON messages(signature)
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_type 
                ON messages(type)
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_last_read_identifier 
                ON last_read(identifier, identifier_type)
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_timestamp 
                ON messages(timestamp DESC)
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_type 
                ON messages(type)
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_channel 
                ON messages(channel)
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_contacts_name 
                ON contacts(name)
            """
            )

            # Apply migrations for existing databases
            self._apply_migrations(cursor)

            self.conn.commit()
            self.logger.info(f"Database initialized at {self.db_path}")

        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            raise

    def _apply_migrations(self, cursor):
        """Apply schema migrations for existing databases."""
        try:
            # Check if recipient_pubkey column exists
            cursor.execute("PRAGMA table_info(messages)")
            columns = [row[1] for row in cursor.fetchall()]

            if "recipient_pubkey" not in columns:
                self.logger.info("Migrating database: adding recipient_pubkey column")
                cursor.execute("ALTER TABLE messages ADD COLUMN recipient_pubkey TEXT")
                self.conn.commit()
                self.logger.info("Migration complete: recipient_pubkey column added")

            # Check if contacts table still uses old "pubkey" column name
            cursor.execute("PRAGMA table_info(contacts)")
            contact_columns = [row[1] for row in cursor.fetchall()]

            if "pubkey" in contact_columns and "public_key" not in contact_columns:
                self.logger.info("Migrating database: renaming pubkey column to public_key")
                # SQLite doesn't support column rename in older versions, so we need to recreate
                # Create new table with correct schema
                cursor.execute(
                    """
                    CREATE TABLE contacts_new (
                        public_key TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        adv_name TEXT,
                        type INTEGER,
                        is_me INTEGER DEFAULT 0,
                        last_seen INTEGER NOT NULL,
                        first_seen INTEGER NOT NULL,
                        raw_data TEXT,
                        notes TEXT DEFAULT ''
                    )
                """
                )
                # Copy data from old table
                cursor.execute(
                    """
                    INSERT INTO contacts_new
                    SELECT pubkey, name, adv_name, type, is_me, last_seen, first_seen, raw_data,
                           COALESCE(notes, '') as notes
                    FROM contacts
                """
                )
                # Drop old table and rename new one
                cursor.execute("DROP TABLE contacts")
                cursor.execute("ALTER TABLE contacts_new RENAME TO contacts")
                # Recreate index
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_contacts_name
                    ON contacts(name)
                """
                )
                self.conn.commit()
                self.logger.info("Migration complete: pubkey renamed to public_key")

            # Check if contacts table has notes column (for databases that already have public_key)
            cursor.execute("PRAGMA table_info(contacts)")
            contact_columns = [row[1] for row in cursor.fetchall()]

            if "notes" not in contact_columns:
                self.logger.info("Migrating database: adding notes column to contacts")
                cursor.execute("ALTER TABLE contacts ADD COLUMN notes TEXT DEFAULT ''")
                self.conn.commit()
                self.logger.info("Migration complete: notes column added to contacts")

            # Check if last_read has new schema
            cursor.execute("PRAGMA table_info(last_read)")
            columns = [row[1] for row in cursor.fetchall()]

            if "identifier_type" not in columns:
                self.logger.info(
                    "Migrating database: recreating last_read table with new schema"
                )
                # Save old data
                cursor.execute(
                    "SELECT contact_or_channel, last_read_timestamp FROM last_read"
                )
                old_data = cursor.fetchall()

                # Drop and recreate
                cursor.execute("DROP TABLE last_read")
                cursor.execute(
                    """
                    CREATE TABLE last_read (
                        identifier TEXT PRIMARY KEY,
                        identifier_type TEXT NOT NULL,
                        last_read_timestamp INTEGER NOT NULL
                    )
                """
                )

                # Migrate old data (assume all were channels/names, not contacts)
                for row in old_data:
                    cursor.execute(
                        """
                        INSERT INTO last_read (identifier, identifier_type, last_read_timestamp)
                        VALUES (?, 'channel', ?)
                    """,
                        (row[0], row[1]),
                    )

                self.conn.commit()
                self.logger.info("Migration complete: last_read table updated")

        except Exception as e:
            self.logger.error(f"Migration failed: {e}")
            # Don't raise - allow app to continue with what it has

    def store_message(self, msg_data: Dict[str, Any]) -> int:
        """Store a message in the database.

        Args:
            msg_data: Message dictionary with fields like type, sender, text, etc.

        Returns:
            ID of inserted message
        """
        try:
            cursor = self.conn.cursor()

            # Extract fields
            msg_type = msg_data.get("type", "contact")
            sender = msg_data.get("sender", "Unknown")
            sender_pubkey = msg_data.get("sender_pubkey", "")
            recipient_pubkey = msg_data.get("recipient_pubkey", "")
            actual_sender = msg_data.get("actual_sender")
            actual_sender_pubkey = msg_data.get("actual_sender_pubkey")
            text = msg_data.get("text", "")
            timestamp = msg_data.get("timestamp", 0)
            channel = msg_data.get("channel")
            snr = msg_data.get("snr")
            path_len = msg_data.get("path_len")
            txt_type = msg_data.get("txt_type")
            signature = msg_data.get("signature")
            received_at = int(datetime.now().timestamp())

            # Delivery tracking fields
            ack_code = msg_data.get("ack_code")
            delivery_status = msg_data.get("delivery_status", "sent")
            repeat_count = msg_data.get("repeat_count", 0)
            last_ack_time = msg_data.get("last_ack_time")

            # Store full raw data as JSON
            raw_data = json.dumps(msg_data)

            cursor.execute(
                """
                INSERT INTO messages (
                    type, sender, sender_pubkey, recipient_pubkey, actual_sender, actual_sender_pubkey,
                    text, timestamp, channel, snr, path_len, txt_type, signature,
                    raw_data, received_at, ack_code, delivery_status, repeat_count, last_ack_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    msg_type,
                    sender,
                    sender_pubkey,
                    recipient_pubkey,
                    actual_sender,
                    actual_sender_pubkey,
                    text,
                    timestamp,
                    channel,
                    snr,
                    path_len,
                    txt_type,
                    signature,
                    raw_data,
                    received_at,
                    ack_code,
                    delivery_status,
                    repeat_count,
                    last_ack_time,
                ),
            )

            self.conn.commit()
            msg_id = cursor.lastrowid
            self.logger.debug(f"Stored message {msg_id} from {sender}")
            return msg_id

        except Exception as e:
            self.logger.error(f"Failed to store message: {e}")
            return -1

    def update_message_delivery_status(self, ack_code: str, repeat_count: int) -> bool:
        """Update delivery status of a message when ACK is received.

        Args:
            ack_code: The ACK code from the repeater
            repeat_count: Number of repeaters that have acknowledged

        Returns:
            True if message was found and updated
        """
        try:
            cursor = self.conn.cursor()
            import time

            cursor.execute(
                """
                UPDATE messages 
                SET repeat_count = ?, 
                    delivery_status = 'repeated',
                    last_ack_time = ?
                WHERE ack_code = ?
            """,
                (repeat_count, int(time.time()), ack_code),
            )

            self.conn.commit()

            if cursor.rowcount > 0:
                self.logger.debug(
                    f"Updated delivery status for ACK {ack_code}: {repeat_count} repeats"
                )
                return True
            else:
                self.logger.debug(f"No message found with ACK code {ack_code}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to update message delivery status: {e}")
            return False

    def store_contact(self, contact_data: Dict[str, Any], is_me: bool = False) -> bool:
        """Store or update a contact in the database.

        Args:
            contact_data: Contact dictionary with pubkey, name, type, etc.
            is_me: Whether this contact represents the current user

        Returns:
            True if successful
        """
        try:
            cursor = self.conn.cursor()

            pubkey = contact_data.get("public_key", "")
            if not pubkey:
                self.logger.warning("Contact has no public_key, skipping storage")
                return False

            name = contact_data.get("name", "Unknown")
            adv_name = contact_data.get("adv_name", name)
            contact_type = contact_data.get("type", 0)
            now = int(datetime.now().timestamp())
            raw_data = json.dumps(contact_data)
            is_me_int = 1 if is_me else 0

            # Insert or update (upsert)
            cursor.execute(
                """
                INSERT INTO contacts (public_key, name, adv_name, type, is_me, last_seen, first_seen, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(public_key) DO UPDATE SET
                    name = excluded.name,
                    adv_name = excluded.adv_name,
                    type = excluded.type,
                    is_me = excluded.is_me,
                    last_seen = excluded.last_seen,
                    raw_data = excluded.raw_data
            """,
                (pubkey, name, adv_name, contact_type, is_me_int, now, now, raw_data),
            )

            self.conn.commit()
            self.logger.debug(
                f"Stored/updated contact {name} ({pubkey[:12]}) is_me={is_me}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to store contact: {e}")
            return False

    def delete_contact(self, pubkey: str) -> bool:
        """Delete a contact from the database.

        Args:
            pubkey: The public key of the contact to delete

        Returns:
            True if successful
        """
        try:
            cursor = self.conn.cursor()

            # Delete the contact
            cursor.execute("DELETE FROM contacts WHERE public_key = ?", (pubkey,))

            # Also delete all messages associated with this contact
            cursor.execute(
                """
                DELETE FROM messages 
                WHERE sender_pubkey = ? OR recipient_pubkey = ?
            """,
                (pubkey, pubkey),
            )

            self.conn.commit()

            deleted_contacts = cursor.execute("SELECT changes()").fetchone()[0]
            self.logger.info(
                f"Deleted contact with pubkey {pubkey[:12]}... ({deleted_contacts} rows)"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to delete contact: {e}")
            return False

    def get_messages_for_contact(
        self, contact_name_or_pubkey: str, limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Get messages for a specific contact by pubkey or name.

        Args:
            contact_name_or_pubkey: Contact public key (preferred) or name (fallback)
            limit: Maximum number of messages to return

        Returns:
            List of message dictionaries
        """
        try:
            cursor = self.conn.cursor()

            # Try to find contact by pubkey first (handles prefixes)
            contact = self.get_contact_by_pubkey(contact_name_or_pubkey)
            if not contact:
                # Fallback: try by name
                cursor.execute(
                    "SELECT * FROM contacts WHERE name = ? OR adv_name = ?",
                    (contact_name_or_pubkey, contact_name_or_pubkey),
                )
                row = cursor.fetchone()
                contact = dict(row) if row else None

            if not contact:
                self.logger.warning(f"Contact not found: {contact_name_or_pubkey}")
                return []

            pubkey = contact["public_key"]
            is_room = contact.get("type") == 3

            # Get "me" contact to identify our own messages
            cursor.execute("SELECT public_key FROM contacts WHERE is_me = 1")
            me_row = cursor.fetchone()
            _ = me_row[0] if me_row else None  # my_pubkey for future use

            if is_room:
                # For room servers: get ALL messages to/from the room
                # This includes messages we sent TO the room, and ALL messages FROM the room
                cursor.execute(
                    """
                    SELECT * FROM messages
                    WHERE (sender_pubkey = ? OR ? LIKE sender_pubkey || '%'
                        OR recipient_pubkey = ? OR ? LIKE recipient_pubkey || '%')
                    AND type IN ('contact', 'room')
                    ORDER BY timestamp ASC, received_at ASC
                    LIMIT ?
                """,
                    (pubkey, pubkey, pubkey, pubkey, limit),
                )
            else:
                # For regular contacts: get messages to/from this contact
                # Note: Messages may have short pubkey prefixes, so we check both directions:
                # - sender_pubkey matches full pubkey OR
                # - full pubkey starts with sender_pubkey (prefix match)
                # DO NOT match actual_sender_pubkey or signature - those are for room messages
                cursor.execute(
                    """
                    SELECT * FROM messages 
                    WHERE (sender_pubkey = ? 
                        OR ? LIKE sender_pubkey || '%'
                        OR recipient_pubkey = ?
                        OR ? LIKE recipient_pubkey || '%'
                        OR json_extract(raw_data, '$.recipient') = ?
                        OR json_extract(raw_data, '$.recipient_pubkey') = ?
                        OR ? LIKE json_extract(raw_data, '$.recipient_pubkey') || '%')
                      AND type = 'contact'
                    ORDER BY timestamp ASC, received_at ASC
                    LIMIT ?
                """,
                    (pubkey, pubkey, pubkey, pubkey, pubkey, pubkey, pubkey, limit),
                )

            return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Failed to get messages for contact: {e}")
            return []

    def get_contact_by_me(self) -> Optional[Dict[str, Any]]:
        """Get the contact marked as 'me' (is_me = 1).

        Returns:
            Contact dictionary for current user, or None if not found
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM contacts WHERE is_me = 1 LIMIT 1")
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            self.logger.error(f"Failed to get 'me' contact: {e}")
            return None

    def get_messages_for_channel(
        self, channel: int, limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Get messages for a specific channel.

        Args:
            channel: Channel index (0 for public)
            limit: Maximum number of messages to return

        Returns:
            List of message dictionaries
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT * FROM messages 
                WHERE channel = ? AND type = 'channel'
                ORDER BY timestamp ASC, received_at ASC
                LIMIT ?
            """,
                (channel, limit),
            )

            return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Failed to get messages for channel: {e}")
            return []

    def get_contact_by_pubkey(self, pubkey: str) -> Optional[Dict[str, Any]]:
        """Get contact by public key or prefix.

        Args:
            pubkey: Full public key or prefix

        Returns:
            Contact dictionary or None
        """
        try:
            cursor = self.conn.cursor()

            # Try exact match first
            cursor.execute(
                """
                SELECT * FROM contacts WHERE public_key = ?
            """,
                (pubkey,),
            )

            row = cursor.fetchone()
            if row:
                return dict(row)

            # Try prefix match
            cursor.execute(
                """
                SELECT * FROM contacts WHERE public_key LIKE ? || '%'
                ORDER BY last_seen DESC
                LIMIT 1
            """,
                (pubkey,),
            )

            row = cursor.fetchone()
            return dict(row) if row else None

        except Exception as e:
            self.logger.error(f"Failed to get contact by pubkey: {e}")
            return None

    def get_contact_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get contact by name.

        Args:
            name: Contact name

        Returns:
            Contact dictionary or None
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT * FROM contacts 
                WHERE name = ? OR adv_name = ?
                ORDER BY last_seen DESC
                LIMIT 1
            """,
                (name, name),
            )

            row = cursor.fetchone()
            return dict(row) if row else None

        except Exception as e:
            self.logger.error(f"Failed to get contact by name: {e}")
            return None

    def get_all_contacts(self) -> List[Dict[str, Any]]:
        """Get all contacts.

        Returns:
            List of contact dictionaries
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT * FROM contacts 
                ORDER BY last_seen DESC
            """
            )

            return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Failed to get all contacts: {e}")
            return []

    def get_recent_conversations(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get list of recent contacts/rooms/channels with message counts.

        Args:
            limit: Maximum number of conversations to return

        Returns:
            List of conversation summaries
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT 
                    sender,
                    type,
                    channel,
                    COUNT(*) as message_count,
                    MAX(timestamp) as last_message_time,
                    MAX(received_at) as last_received_at
                FROM messages
                GROUP BY sender, type, channel
                ORDER BY last_received_at DESC
                LIMIT ?
            """,
                (limit,),
            )

            return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Failed to get recent conversations: {e}")
            return []

    def mark_as_read(
        self, contact_name_or_pubkey: str, timestamp: Optional[int] = None
    ):
        """Mark messages as read up to a timestamp.

        Args:
            contact_name_or_pubkey: Contact pubkey (preferred), name, or channel name
            timestamp: Unix timestamp to mark as read up to (default: now)
        """
        try:
            if timestamp is None:
                timestamp = int(datetime.now().timestamp())

            # Determine identifier and type
            identifier_type = "channel"  # Default for Public, etc.
            identifier = contact_name_or_pubkey

            # Try to find contact by pubkey or name
            contact = self.get_contact_by_pubkey(contact_name_or_pubkey)
            if not contact:
                cursor = self.conn.cursor()
                cursor.execute(
                    "SELECT * FROM contacts WHERE name = ? OR adv_name = ?",
                    (contact_name_or_pubkey, contact_name_or_pubkey),
                )
                row = cursor.fetchone()
                contact = dict(row) if row else None

            if contact:
                identifier = contact["public_key"]
                identifier_type = "contact"
            else:
                # For channels, keep the name as-is (e.g., "Public", "Channel 1")
                # The identifier stays as the channel name
                identifier_type = "channel"

            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO last_read (identifier, identifier_type, last_read_timestamp)
                VALUES (?, ?, ?)
                ON CONFLICT(identifier) DO UPDATE SET
                    last_read_timestamp = excluded.last_read_timestamp
            """,
                (identifier, identifier_type, timestamp),
            )

            self.conn.commit()
            self.logger.debug(
                f"Marked {identifier} ({identifier_type}) as read up to {timestamp}"
            )

        except Exception as e:
            self.logger.error(f"Failed to mark as read: {e}")

    def get_unread_count(self, contact_name_or_pubkey: str) -> int:
        """Get count of unread messages for a contact/channel.

        Args:
            contact_name_or_pubkey: Contact pubkey (preferred), name, or channel name

        Returns:
            Number of unread messages
        """
        try:
            cursor = self.conn.cursor()

            # Determine identifier
            identifier = contact_name_or_pubkey
            pubkey = None
            contact = self.get_contact_by_pubkey(contact_name_or_pubkey)
            if not contact:
                cursor.execute(
                    "SELECT * FROM contacts WHERE name = ? OR adv_name = ?",
                    (contact_name_or_pubkey, contact_name_or_pubkey),
                )
                row = cursor.fetchone()
                contact = dict(row) if row else None

            if contact:
                identifier = contact["public_key"]
                pubkey = identifier

            # Get last read timestamp
            cursor.execute(
                """
                SELECT last_read_timestamp FROM last_read
                WHERE identifier = ?
            """,
                (identifier,),
            )

            row = cursor.fetchone()
            last_read = row[0] if row else 0

            # Count messages after last read (exclude sent messages)
            if contact:
                # For contacts/rooms, use pubkey-based lookup
                # Note: sender_pubkey in messages table may be truncated (12 chars)
                # so we need to check if the full pubkey STARTS WITH the stored prefix
                pubkey_prefix = pubkey[:12]  # First 12 chars to match truncated keys
                self.logger.debug(
                    f"🔍 Unread query: pubkey={pubkey}, prefix={pubkey_prefix}, last_read={last_read}"
                )
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM messages
                    WHERE ((sender_pubkey IS NOT NULL AND sender_pubkey != '' AND ? LIKE sender_pubkey || '%')
                        OR (actual_sender_pubkey IS NOT NULL AND actual_sender_pubkey != '' AND ? LIKE actual_sender_pubkey || '%')
                        OR (signature IS NOT NULL AND signature != '' AND ? LIKE signature || '%'))
                      AND received_at > ?
                      AND sender != 'Me'
                """,
                    (pubkey, pubkey, pubkey, last_read),
                )
            else:
                # For channels, extract channel index from name and use channel field
                # Names are like "Public" (channel 0) or "Channel 1" (channel 1)
                channel_idx = 0
                if identifier == "Public":
                    channel_idx = 0
                elif identifier.startswith("Channel "):
                    try:
                        channel_idx = int(identifier.split(" ")[1])
                    except (IndexError, ValueError):
                        channel_idx = 0

                self.logger.debug(
                    f"🔍 Unread query: channel={identifier} (idx={channel_idx}), last_read={last_read}"
                )
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM messages
                    WHERE type = 'channel'
                      AND channel = ?
                      AND received_at > ?
                      AND sender != 'Me'
                """,
                    (channel_idx, last_read),
                )

            count = cursor.fetchone()[0]
            self.logger.debug(f"🔍 Unread count for {contact_name_or_pubkey}: {count}")
            return count

        except Exception as e:
            self.logger.error(f"Failed to get unread count: {e}")
            return 0

    def get_all_unread_counts(self) -> Dict[str, int]:
        """Get unread counts for all contacts/channels with unread messages.

        Returns:
            Dictionary mapping contact/channel names to unread counts
        """
        try:
            cursor = self.conn.cursor()

            # Get all unique senders and recipients
            cursor.execute(
                """
                SELECT DISTINCT sender FROM messages WHERE sender != 'Me'
                UNION
                SELECT DISTINCT json_extract(raw_data, '$.recipient') FROM messages
                WHERE json_extract(raw_data, '$.recipient') IS NOT NULL
            """
            )

            all_contacts = [row[0] for row in cursor.fetchall() if row[0]]

            # Get unread count for each
            unread_counts = {}
            for contact in all_contacts:
                count = self.get_unread_count(contact)
                if count > 0:
                    unread_counts[contact] = count

            return unread_counts

        except Exception as e:
            self.logger.error(f"Failed to get all unread counts: {e}")
            return {}

    def get_contact(self, pubkey: str) -> Optional[Dict[str, Any]]:
        """Get a contact by public key.

        Args:
            pubkey: Public key of the contact

        Returns:
            Contact dictionary or None if not found
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT * FROM contacts WHERE public_key = ?
            """,
                (pubkey,),
            )

            row = cursor.fetchone()
            return dict(row) if row else None

        except Exception as e:
            self.logger.error(f"Failed to get contact: {e}")
            return None

    def get_contact_notes(self, pubkey: str) -> str:
        """Get notes for a contact.

        Args:
            pubkey: Public key of the contact

        Returns:
            Notes string (empty string if none)
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT notes FROM contacts WHERE public_key = ?
            """,
                (pubkey,),
            )

            row = cursor.fetchone()
            return row[0] if row and row[0] else ""

        except Exception as e:
            self.logger.error(f"Failed to get contact notes: {e}")
            return ""

    def set_contact_notes(self, pubkey: str, notes: str) -> bool:
        """Set notes for a contact.

        Args:
            pubkey: Public key of the contact
            notes: Notes text to save

        Returns:
            True if successful, False otherwise
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                UPDATE contacts SET notes = ? WHERE public_key = ?
            """,
                (notes, pubkey),
            )
            self.conn.commit()
            self.logger.debug(f"Updated notes for contact {pubkey}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to set contact notes: {e}")
            return False

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.logger.info("Database connection closed")
