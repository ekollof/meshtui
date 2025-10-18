#!/usr/bin/env python3
"""
Room server handling for MeshTUI.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List
from meshcore import EventType


class RoomManager:
    """Manages room server connections and message handling."""

    def __init__(self, meshcore, message_store: List[Dict[str, Any]]):
        """Initialize room manager.
        
        Args:
            meshcore: MeshCore instance
            message_store: Shared message storage list
        """
        self.meshcore = meshcore
        self.message_store = message_store
        self.logged_in_rooms: Dict[str, bool] = {}  # room_name -> logged_in status
        self.room_admin_status: Dict[str, bool] = {}  # room_name -> is_admin status
        self.room_pubkeys: Dict[str, str] = {}  # Map room_name -> pubkey
        self.pubkey_to_room: Dict[str, str] = {}  # Map pubkey -> room_name
        self.logger = logging.getLogger("meshtui.room")
        
        # Subscribe to login events to capture admin status
        self.meshcore.subscribe(EventType.LOGIN_SUCCESS, self._handle_login_success)
        self.meshcore.subscribe(EventType.LOGIN_FAILED, self._handle_login_failed)

    async def _handle_login_success(self, event):
        """Handle LOGIN_SUCCESS event to capture admin status."""
        pubkey_prefix = event.payload.get('pubkey_prefix', '')
        is_admin = event.payload.get('is_admin', False)
        permissions = event.payload.get('permissions', 0)
        
        self.logger.info(f"Login success for {pubkey_prefix}: admin={is_admin}, permissions={permissions}")
        
        # Find which room this pubkey belongs to
        room_name = self.get_room_by_pubkey(pubkey_prefix)
        if room_name:
            self.room_admin_status[room_name] = is_admin
            self.logger.info(f"Room '{room_name}' admin status: {is_admin}")
    
    async def _handle_login_failed(self, event):
        """Handle LOGIN_FAILED event."""
        pubkey_prefix = event.payload.get('pubkey_prefix', '')
        self.logger.warning(f"Login failed for {pubkey_prefix}")
        
        # Clear admin status for this room
        room_name = self.get_room_by_pubkey(pubkey_prefix)
        if room_name:
            self.room_admin_status[room_name] = False
            self.logged_in_rooms[room_name] = False

    def is_logged_in(self, room_name: str) -> bool:
        """Check if we're logged into a room server.
        
        Args:
            room_name: Name of the room server
            
        Returns:
            True if logged in, False otherwise
        """
        return self.logged_in_rooms.get(room_name, False)
    
    def is_admin(self, room_name: str) -> bool:
        """Check if we have admin privileges in a room server.
        
        Args:
            room_name: Name of the room server
            
        Returns:
            True if admin, False otherwise
        """
        return self.room_admin_status.get(room_name, False)

    def get_room_by_pubkey(self, pubkey: str) -> Optional[str]:
        """Get the room name associated with a pubkey.
        
        Args:
            pubkey: Public key or prefix to look up
            
        Returns:
            Room name if found, None otherwise
        """
        # Try exact match first
        if pubkey in self.pubkey_to_room:
            return self.pubkey_to_room[pubkey]
        
        # Try prefix match (first 12 chars)
        pubkey_prefix = pubkey[:12] if len(pubkey) >= 12 else pubkey
        return self.pubkey_to_room.get(pubkey_prefix)

    async def login(self, room_name: str, contact: dict, password: str) -> bool:
        """Login to a room server.
        
        Args:
            room_name: Name of the room server contact
            contact: Contact dictionary for the room server
            password: Password for the room
            
        Returns:
            True if login successful, False otherwise
        """
        if not self.meshcore:
            return False

        try:
            self.logger.info(f"Attempting to login to room '{room_name}'")
            
            # Send login request with contact dict (not just key)
            result = await self.meshcore.commands.send_login(contact, password)
            
            if result.type == EventType.ERROR:
                self.logger.error(f"Failed to send login: {result}")
                return False
            
            # Wait for LOGIN_SUCCESS or LOGIN_FAILED event
            login_result = await asyncio.wait_for(
                self._wait_for_login_event(),
                timeout=5.0
            )
            
            if login_result and login_result == "success":
                self.logger.info(f"Successfully logged into room '{room_name}'")
                self.logged_in_rooms[room_name] = True
                
                # Store pubkey mappings for message routing
                room_key = contact.get('public_key') or contact.get('pubkey', '')
                self.room_pubkeys[room_name] = room_key
                pubkey_prefix = room_key[:12] if len(room_key) >= 12 else room_key
                self.pubkey_to_room[pubkey_prefix] = room_name
                self.logger.debug(f"Mapped pubkey {pubkey_prefix} to room {room_name}")
                
                # After successful login, retrieve queued messages
                self.logger.info(f"Fetching queued messages from room '{room_name}'")
                await self.fetch_messages(contact)
                
                return True
            else:
                self.logger.error(f"Login to room '{room_name}' failed")
                self.logged_in_rooms[room_name] = False
                return False
            
        except asyncio.TimeoutError:
            self.logger.error(f"Login to room '{room_name}' timed out")
            return False
        except Exception as e:
            self.logger.error(f"Error logging into room: {e}")
            import traceback
            self.logger.debug(f"Traceback: {traceback.format_exc()}")
            return False

    async def _wait_for_login_event(self) -> Optional[str]:
        """Wait for login success or failure event.
        
        Returns:
            "success" if LOGIN_SUCCESS, "failed" if LOGIN_FAILED, None on error
        """
        try:
            # Subscribe to login events temporarily
            login_success = asyncio.Future()
            
            async def on_login_success(event):
                if not login_success.done():
                    login_success.set_result("success")
            
            async def on_login_failed(event):
                if not login_success.done():
                    login_success.set_result("failed")
            
            sub1 = self.meshcore.subscribe(EventType.LOGIN_SUCCESS, on_login_success)
            sub2 = self.meshcore.subscribe(EventType.LOGIN_FAILED, on_login_failed)
            
            try:
                result = await asyncio.wait_for(login_success, timeout=5.0)
                return result
            finally:
                self.meshcore.unsubscribe(sub1)
                self.meshcore.unsubscribe(sub2)
                
        except Exception as e:
            self.logger.error(f"Error waiting for login event: {e}")
            return None

    async def fetch_messages(self, contact: dict) -> int:
        """Fetch queued messages from a room server after login.
        
        This purges the internal message queue by repeatedly calling get_msg()
        until we get NO_MORE_MSGS.
        
        Args:
            contact: Contact dictionary for the room server
            
        Returns:
            Number of messages fetched
        """
        if not self.meshcore:
            return 0
        
        try:
            message_count = 0
            max_messages = 100  # Safety limit
            
            self.logger.debug("Purging queued messages from MeshCore buffer...")
            
            # Keep calling get_msg() until NO_MORE_MSGS
            while message_count < max_messages:
                result = await asyncio.wait_for(
                    self.meshcore.commands.get_msg(),
                    timeout=1.0
                )
                
                if result.type == EventType.NO_MORE_MSGS:
                    self.logger.info(f"Retrieved {message_count} queued messages from room")
                    break
                elif result.type == EventType.CONTACT_MSG_RECV:
                    # Message will be handled by the event handler
                    message_count += 1
                    self.logger.debug(f"Received queued message {message_count}")
                elif result.type == EventType.ERROR:
                    self.logger.error(f"Error fetching room message: {result.payload}")
                    break
                else:
                    self.logger.debug(f"Got unexpected event while fetching: {result.type}")
                    
            self.logger.info(f"Fetched {message_count} queued messages from room")
            return message_count
                    
        except asyncio.TimeoutError:
            if message_count > 0:
                self.logger.info(f"Finished fetching {message_count} room messages (timeout)")
            else:
                self.logger.debug("No messages in queue")
            return message_count
        except Exception as e:
            self.logger.error(f"Error fetching room messages: {e}")
            import traceback
            self.logger.debug(f"Traceback: {traceback.format_exc()}")
            return 0

    async def logout(self, room_name: str, room_key: str) -> bool:
        """Logout from a room server.
        
        Args:
            room_name: Name of the room server
            room_key: Public key of the room server
            
        Returns:
            True if logout successful, False otherwise
        """
        if not self.meshcore:
            return False

        try:
            self.logger.info(f"Logging out from room '{room_name}'")
            
            result = await self.meshcore.commands.send_logout(room_key)
            
            if result.type == EventType.ERROR:
                self.logger.error(f"Failed to send logout: {result}")
                return False
            
            self.logged_in_rooms[room_name] = False
            self.logger.info(f"Successfully logged out from room '{room_name}'")
            return True
            
        except Exception as e:
            self.logger.error(f"Error logging out from room: {e}")
            return False
