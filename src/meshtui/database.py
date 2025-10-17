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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    sender_pubkey TEXT,
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
                    received_at INTEGER NOT NULL
                )
            """)
            
            # Contacts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS contacts (
                    pubkey TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    adv_name TEXT,
                    type INTEGER,
                    is_me INTEGER DEFAULT 0,
                    last_seen INTEGER NOT NULL,
                    first_seen INTEGER NOT NULL,
                    raw_data TEXT
                )
            """)
            
            # Last read tracking table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS last_read (
                    contact_or_channel TEXT PRIMARY KEY,
                    last_read_timestamp INTEGER NOT NULL
                )
            """)
            
            # Create indexes for efficient queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_sender 
                ON messages(sender)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_timestamp 
                ON messages(timestamp DESC)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_type 
                ON messages(type)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_channel 
                ON messages(channel)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_contacts_name 
                ON contacts(name)
            """)
            
            self.conn.commit()
            self.logger.info("Database initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            raise
    
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
            msg_type = msg_data.get('type', 'contact')
            sender = msg_data.get('sender', 'Unknown')
            sender_pubkey = msg_data.get('sender_pubkey', '')
            actual_sender = msg_data.get('actual_sender')
            actual_sender_pubkey = msg_data.get('actual_sender_pubkey')
            text = msg_data.get('text', '')
            timestamp = msg_data.get('timestamp', 0)
            channel = msg_data.get('channel')
            snr = msg_data.get('snr')
            path_len = msg_data.get('path_len')
            txt_type = msg_data.get('txt_type')
            signature = msg_data.get('signature')
            received_at = int(datetime.now().timestamp())
            
            # Store full raw data as JSON
            raw_data = json.dumps(msg_data)
            
            cursor.execute("""
                INSERT INTO messages (
                    type, sender, sender_pubkey, actual_sender, actual_sender_pubkey,
                    text, timestamp, channel, snr, path_len, txt_type, signature,
                    raw_data, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                msg_type, sender, sender_pubkey, actual_sender, actual_sender_pubkey,
                text, timestamp, channel, snr, path_len, txt_type, signature,
                raw_data, received_at
            ))
            
            self.conn.commit()
            msg_id = cursor.lastrowid
            self.logger.debug(f"Stored message {msg_id} from {sender}")
            return msg_id
            
        except Exception as e:
            self.logger.error(f"Failed to store message: {e}")
            return -1
    
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
            
            pubkey = contact_data.get('public_key') or contact_data.get('pubkey', '')
            if not pubkey:
                self.logger.warning("Contact has no pubkey, skipping storage")
                return False
            
            name = contact_data.get('name', 'Unknown')
            adv_name = contact_data.get('adv_name', name)
            contact_type = contact_data.get('type', 0)
            now = int(datetime.now().timestamp())
            raw_data = json.dumps(contact_data)
            is_me_int = 1 if is_me else 0
            
            # Insert or update (upsert)
            cursor.execute("""
                INSERT INTO contacts (pubkey, name, adv_name, type, is_me, last_seen, first_seen, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pubkey) DO UPDATE SET
                    name = excluded.name,
                    adv_name = excluded.adv_name,
                    type = excluded.type,
                    is_me = excluded.is_me,
                    last_seen = excluded.last_seen,
                    raw_data = excluded.raw_data
            """, (pubkey, name, adv_name, contact_type, is_me_int, now, now, raw_data))
            
            self.conn.commit()
            self.logger.debug(f"Stored/updated contact {name} ({pubkey[:12]}) is_me={is_me}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to store contact: {e}")
            return False
    
    def get_messages_for_contact(self, contact_name: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get messages for a specific contact or room.
        
        Args:
            contact_name: Name of contact or room
            limit: Maximum number of messages to return
            
        Returns:
            List of message dictionaries
        """
        try:
            cursor = self.conn.cursor()
            # Get both sent and received messages for this contact
            cursor.execute("""
                SELECT * FROM messages 
                WHERE (sender = ? OR json_extract(raw_data, '$.recipient') = ?) 
                  AND type IN ('contact', 'room')
                ORDER BY timestamp ASC, received_at ASC
                LIMIT ?
            """, (contact_name, contact_name, limit))
            
            return [dict(row) for row in cursor.fetchall()]
            
        except Exception as e:
            self.logger.error(f"Failed to get messages for contact: {e}")
            return []
    
    def get_messages_for_channel(self, channel: int, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get messages for a specific channel.
        
        Args:
            channel: Channel index (0 for public)
            limit: Maximum number of messages to return
            
        Returns:
            List of message dictionaries
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM messages 
                WHERE channel = ? AND type = 'channel'
                ORDER BY timestamp ASC, received_at ASC
                LIMIT ?
            """, (channel, limit))
            
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
            cursor.execute("""
                SELECT * FROM contacts WHERE pubkey = ?
            """, (pubkey,))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
            
            # Try prefix match
            cursor.execute("""
                SELECT * FROM contacts WHERE pubkey LIKE ? || '%'
                ORDER BY last_seen DESC
                LIMIT 1
            """, (pubkey,))
            
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
            cursor.execute("""
                SELECT * FROM contacts 
                WHERE name = ? OR adv_name = ?
                ORDER BY last_seen DESC
                LIMIT 1
            """, (name, name))
            
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
            cursor.execute("""
                SELECT * FROM contacts 
                ORDER BY last_seen DESC
            """)
            
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
            cursor.execute("""
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
            """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
            
        except Exception as e:
            self.logger.error(f"Failed to get recent conversations: {e}")
            return []
    
    def mark_as_read(self, contact_or_channel: str, timestamp: Optional[int] = None):
        """Mark messages as read up to a timestamp.
        
        Args:
            contact_or_channel: Name of contact, room, or channel
            timestamp: Unix timestamp to mark as read up to (default: now)
        """
        try:
            if timestamp is None:
                timestamp = int(datetime.now().timestamp())
            
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO last_read (contact_or_channel, last_read_timestamp)
                VALUES (?, ?)
                ON CONFLICT(contact_or_channel) DO UPDATE SET
                    last_read_timestamp = excluded.last_read_timestamp
            """, (contact_or_channel, timestamp))
            
            self.conn.commit()
            self.logger.debug(f"Marked {contact_or_channel} as read up to {timestamp}")
            
        except Exception as e:
            self.logger.error(f"Failed to mark as read: {e}")
    
    def get_unread_count(self, contact_or_channel: str) -> int:
        """Get count of unread messages for a contact/channel.
        
        Args:
            contact_or_channel: Name of contact, room, or channel
            
        Returns:
            Number of unread messages
        """
        try:
            cursor = self.conn.cursor()
            
            # Get last read timestamp
            cursor.execute("""
                SELECT last_read_timestamp FROM last_read
                WHERE contact_or_channel = ?
            """, (contact_or_channel,))
            
            row = cursor.fetchone()
            last_read = row[0] if row else 0
            
            # Count messages after last read (exclude sent messages)
            cursor.execute("""
                SELECT COUNT(*) FROM messages
                WHERE (sender = ? OR json_extract(raw_data, '$.recipient') = ?)
                  AND received_at > ?
                  AND sender != 'Me'
            """, (contact_or_channel, contact_or_channel, last_read))
            
            count = cursor.fetchone()[0]
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
            cursor.execute("""
                SELECT DISTINCT sender FROM messages WHERE sender != 'Me'
                UNION
                SELECT DISTINCT json_extract(raw_data, '$.recipient') FROM messages
                WHERE json_extract(raw_data, '$.recipient') IS NOT NULL
            """)
            
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
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.logger.info("Database connection closed")
