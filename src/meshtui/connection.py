#!/usr/bin/env python3
"""
Connection manager for MeshCore devices.
Orchestrates transport, contacts, channels, and rooms.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
from enum import Enum

import serial.tools.list_ports
from bleak import BleakScanner
from meshcore import MeshCore, EventType

from .contact import ContactManager
from .channel import ChannelManager
from .room import RoomManager
from .transport import SerialTransport, BLETransport, TCPTransport, ConnectionType


class MeshConnection:
    """Manages connection to MeshCore devices."""

    def __init__(self):
        self.meshcore: Optional[MeshCore] = None
        self.connected = False
        self.connection_type: Optional[ConnectionType] = None
        self.device_info: Optional[Dict[str, Any]] = None
        self.messages: List[Dict[str, Any]] = []  # In-memory cache for quick access
        self.logger = logging.getLogger("meshtui.connection")
        
        # Managers (will be initialized after connection)
        self.contacts: Optional[ContactManager] = None
        self.channels: Optional[ChannelManager] = None
        self.rooms: Optional[RoomManager] = None
        
        # Flags to prevent spam
        self._refreshing_contacts = False
        
        # Callbacks for UI updates
        self._message_callback = None
        
        # Unread message tracking
        self.unread_counts: Dict[str, int] = {}  # contact_name -> unread count
        self.last_read_index: Dict[str, int] = {}  # contact_name -> last read message index
        self._messages_dirty = False  # Track if messages need saving
        self._save_task = None  # Background save task

        # Configuration
        self.config_dir = Path.home() / ".config" / "meshtui"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Database for persistent storage
        from .database import MessageDatabase
        self.db = MessageDatabase(self.config_dir / "meshtui.db")
        
        # Load recent messages into cache
        self._load_recent_messages()
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.address_file = self.config_dir / "default_address"
        
        # Transport layers
        self.serial_transport = SerialTransport()
        self.ble_transport = BLETransport(self.config_dir)
        self.tcp_transport = TCPTransport()

    async def identify_meshcore_device(
        self, device_path: str, timeout: float = 2.0
    ) -> bool:
        """Identify if a serial device is a MeshCore device by attempting to connect and query."""
        try:
            self.logger.debug(f"Testing if {device_path} is a MeshCore device...")
            # Create a temporary connection to test
            temp_mc = await MeshCore.create_serial(
                port=device_path, baudrate=115200, debug=False, only_error=True
            )

            # Try to query device info
            result = await temp_mc.commands.send_device_query()
            if result.type == EventType.ERROR:
                self.logger.debug(f"Device at {device_path} is not a MeshCore device")
                return False

            device_info = result.payload
            if device_info and "model" in device_info:
                self.logger.info(
                    f"Found MeshCore device at {device_path}: {device_info.get('model')} v{device_info.get('ver', 'unknown')}"
                )
                return True
            else:
                self.logger.debug(
                    f"Device at {device_path} responded but lacks MeshCore identification"
                )
                return False

        except Exception as e:
            self.logger.debug(f"Failed to identify device at {device_path}: {e}")
            return False

    async def scan_ble_devices(self, timeout: float = 2.0) -> List[Dict[str, Any]]:
        """Scan for available BLE MeshCore devices."""
        self.logger.info(f"Scanning for BLE devices (timeout: {timeout}s)...")
        try:
            devices = await BleakScanner.discover(timeout=timeout)
            meshcore_devices = []

            for device in devices:
                if device.name and device.name.startswith("MeshCore-"):
                    meshcore_devices.append(
                        {
                            "name": device.name,
                            "address": device.address,
                            "rssi": device.rssi,
                            "device": device,
                        }
                    )

            self.logger.info(f"Found {len(meshcore_devices)} BLE MeshCore devices")
            return meshcore_devices

        except Exception as e:
            self.logger.error(f"BLE scan failed: {e}")
            return []

    async def scan_serial_devices(self) -> List[Dict[str, Any]]:
        """Scan for available serial devices and identify MeshCore devices."""
        self.logger.info("Scanning for serial devices...")
        try:
            ports = serial.tools.list_ports.comports()
            serial_devices = []

            for port in ports:
                device_info = {
                    "device": port.device,
                    "name": port.name or "Unknown",
                    "description": port.description or "",
                    "manufacturer": port.manufacturer or "",
                    "serial_number": port.serial_number or "",
                }

                # Test if this is a MeshCore device
                if await self.identify_meshcore_device(port.device):
                    device_info["is_meshcore"] = True
                    self.logger.info(f"✓ MeshCore device found at {port.device}")
                else:
                    device_info["is_meshcore"] = False

                serial_devices.append(device_info)

            meshcore_count = sum(
                1 for d in serial_devices if d.get("is_meshcore", False)
            )
            self.logger.info(
                f"Found {len(serial_devices)} serial devices, {meshcore_count} are MeshCore devices"
            )
            return serial_devices

        except Exception as e:
            self.logger.error(f"Serial scan failed: {e}")
            return []

    async def connect_ble(
        self, address: Optional[str] = None, device=None, timeout: float = 2.0
    ) -> bool:
        """Connect to a MeshCore device via BLE."""
        try:
            if not address and not device:
                # Try to load saved address
                if self.address_file.exists():
                    with open(self.address_file, "r", encoding="utf-8") as f:
                        address = f.read().strip()

                # If no saved address, scan for devices
                if not address:
                    devices = await self.scan_ble_devices(timeout)
                    if devices:
                        device = devices[0]["device"]
                        address = devices[0]["address"]
                    else:
                        self.logger.error("No MeshCore devices found")
                        return False

            self.logger.info(f"Connecting to BLE device: {address}")
            self.meshcore = await MeshCore.create_ble(
                address=address, device=device, debug=False, only_error=False
            )

            # Test connection
            result = await self.meshcore.commands.send_device_query()
            if result.type == EventType.ERROR:
                self.logger.error(f"Device query failed: {result}")
                return False

            self.connected = True
            self.connection_type = ConnectionType.BLE
            self.device_info = result.payload

            # Save address for future use
            with open(self.address_file, "w", encoding="utf-8") as f:
                f.write(address or device.address)

            # Setup event handlers
            await self._setup_event_handlers()
            
            # Initialize managers
            self._initialize_managers()

            self.logger.info(f"Connected to {self.device_info.get('name', 'Unknown')}")
            return True

        except Exception as e:
            self.logger.error(f"BLE connection failed: {e}")
            return False

    async def connect_tcp(self, hostname: str, port: int = 5000) -> bool:
        """Connect to a MeshCore device via TCP."""
        try:
            self.logger.info(f"Connecting to TCP device: {hostname}:{port}")
            self.meshcore = await MeshCore.create_tcp(
                host=hostname, port=port, debug=False, only_error=False
            )

            # Test connection
            result = await self.meshcore.commands.send_device_query()
            if result.type == EventType.ERROR:
                self.logger.error(f"Device query failed: {result}")
                return False

            self.connected = True
            self.connection_type = ConnectionType.TCP
            self.device_info = result.payload

            # Setup event handlers
            await self._setup_event_handlers()

            self.logger.info(
                f"Connected to {self.device_info.get('name', 'Unknown')} via TCP"
            )
            return True

        except Exception as e:
            self.logger.error(f"TCP connection failed: {e}")
            return False

    async def connect_serial(self, port: str, baudrate: int = 115200) -> bool:
        """Connect to a MeshCore device via serial."""
        try:
            self.logger.info(f"Connecting to serial device: {port}@{baudrate}")
            self.meshcore = await MeshCore.create_serial(
                port=port, baudrate=baudrate, debug=False, only_error=False
            )

            # Test connection
            self.logger.debug("Sending device query to test connection...")
            result = await self.meshcore.commands.send_device_query()
            if result.type == EventType.ERROR:
                self.logger.error(f"Device query failed: {result}")
                return False

            self.connected = True
            self.connection_type = ConnectionType.SERIAL
            self.device_info = result.payload
            self.logger.info(
                f"Device query successful. Device info: {self.device_info}"
            )

            # Setup event handlers
            await self._setup_event_handlers()
            self.logger.debug("Event handlers set up")
            
            # Initialize managers
            self._initialize_managers()

            # Explicitly refresh contacts after connection
            self.logger.debug("Refreshing contacts after connection...")
            await self.refresh_contacts()

            contact_count = len(self.contacts.get_all()) if self.contacts else 0
            self.logger.info(
                f"Connected to {self.device_info.get('name', 'Unknown')} via serial. Found {contact_count} contacts."
            )
            return True

        except Exception as e:
            self.logger.error(f"Serial connection failed: {e}")
            return False

    def _initialize_managers(self):
        """Initialize the contact, channel, and room managers."""
        if not self.meshcore:
            return
        
        self.logger.debug("Initializing managers...")
        self.contacts = ContactManager(self.meshcore)
        self.channels = ChannelManager(self.meshcore)
        self.rooms = RoomManager(self.meshcore, self.messages)
        self.logger.debug("Managers initialized")

    async def _setup_event_handlers(self):
        """Setup event handlers for meshcore events."""
        if not self.meshcore:
            return
        self.logger.debug("Setting up event handlers...")

        # Enable auto-update of contacts if supported
        try:
            self.meshcore.auto_update_contacts = True
            self.logger.debug("Auto-update contacts enabled")
        except Exception:
            self.logger.debug("auto_update_contacts not available on this MeshCore instance")

        # Start auto message fetching if the API supports it (guarded)
        try:
            start_fetch = getattr(self.meshcore, "start_auto_message_fetching", None)
            if start_fetch:
                res = start_fetch()
                if asyncio.iscoroutine(res):
                    await res
                self.logger.debug("Auto message fetching started")
        except Exception as e:
            self.logger.debug(f"Auto message fetching not started: {e}")

        # Subscribe to events - meshcore handles async callbacks properly
        self.meshcore.subscribe(EventType.NEW_CONTACT, self._handle_new_contact)
        self.meshcore.subscribe(EventType.CONTACTS, self._handle_contacts_update)
        self.meshcore.subscribe(EventType.CONTACT_MSG_RECV, self._handle_contact_message)
        self.meshcore.subscribe(EventType.CHANNEL_MSG_RECV, self._handle_channel_message)
        self.meshcore.subscribe(EventType.ADVERTISEMENT, self._handle_advertisement)
        self.meshcore.subscribe(EventType.PATH_UPDATE, self._handle_path_update)
        self.meshcore.subscribe(EventType.CHANNEL_INFO, self._handle_channel_info)
        self.logger.debug("Event handlers subscribed")

    async def _handle_new_contact(self, event):
        """Handle new contact event - store immediately."""
        self.logger.info(f"📡 EVENT: New contact detected: {event.payload}")
        print(f"DEBUG: New contact event received: {event.payload}")
        
        # Store new contact immediately
        contact_data = event.payload or {}
        if contact_data.get('public_key') or contact_data.get('pubkey'):
            self.db.store_contact(contact_data, is_me=False)
            self.logger.info(f"Stored new contact: {contact_data.get('name', 'Unknown')}")
        
        # Update contacts list
        await self.refresh_contacts()

    async def _handle_advertisement(self, event):
        """Handle advertisement event - update contact when they broadcast."""
        self.logger.info(f"📡 EVENT: Advertisement received: {event.payload}")
        print(f"DEBUG: Advertisement event received: {event.payload}")
        
        # Extract contact info from advertisement
        adv_data = event.payload or {}
        pubkey = adv_data.get('pubkey') or adv_data.get('public_key')
        
        if pubkey and self.contacts:
            # Try to find this contact
            contact = self.contacts.get_by_key(pubkey)
            if contact:
                # Update their last_seen timestamp
                self.db.store_contact(contact, is_me=False)
                self.logger.debug(f"Updated contact {contact.get('name')} from advertisement")
            else:
                # New contact from advertisement - create minimal contact record
                contact_data = {
                    'public_key': pubkey,
                    'pubkey': pubkey,
                    'name': adv_data.get('name', pubkey[:12]),
                    'adv_name': adv_data.get('adv_name', adv_data.get('name', pubkey[:12])),
                    'type': adv_data.get('type', 0),
                }
                self.db.store_contact(contact_data, is_me=False)
                self.logger.info(f"Created new contact from advertisement: {contact_data.get('name')}")
                
                # Trigger contacts refresh to update UI
                if self._message_callback:
                    self._message_callback(None)

    async def _handle_path_update(self, event):
        """Handle path update event."""
        self.logger.info(f"📡 EVENT: Path update: {event.payload}")
        print(f"DEBUG: Path update event received: {event.payload}")

    async def _handle_contacts_update(self, event):
        """Handle contacts list update event."""
        # Prevent refresh loops
        if self._refreshing_contacts:
            self.logger.debug("Skipping contacts update event (already refreshing)")
            return
            
        self.logger.info(f"📡 EVENT: Contacts update received")
        print(f"DEBUG: Contacts update event received")
        # Refresh contacts through the manager
        await self.refresh_contacts()

    async def _handle_contact_message(self, event):
        """Handle direct contact message received event."""
        self.logger.info(f"📧 EVENT: Direct message received: {event.payload}")
        print(f"DEBUG: Direct message received: {event.payload}")
        
        # Store message in the messages list
        msg_data = event.payload or {}
        sender_key = msg_data.get('pubkey_prefix', msg_data.get('sender', 'Unknown'))
        
        # Try to identify if this is from a room server
        sender_name = sender_key
        is_room_message = False
        actual_sender_name = None
        signature = msg_data.get('signature', '')
        
        if self.rooms:
            room_name = self.rooms.get_room_by_pubkey(sender_key)
            if room_name:
                sender_name = room_name
                is_room_message = True
                self.logger.debug(f"Message identified as from room: {room_name}")
                
                # For room messages, try to identify the actual sender from signature
                if signature and self.contacts:
                    actual_sender = self.contacts.get_by_key(signature)
                    if actual_sender:
                        actual_sender_name = actual_sender.get('adv_name') or actual_sender.get('name', signature)
                        self.logger.debug(f"Room message sender: {actual_sender_name}")
                    else:
                        actual_sender_name = signature
                        self.logger.debug(f"Room message sender (unknown): {signature}")
        
        # If not a room, try to find contact name
        if not is_room_message and self.contacts:
            contact = self.contacts.get_by_key(sender_key)
            if contact:
                sender_name = contact.get('adv_name') or contact.get('name', sender_key)
        
        self.messages.append({
            'type': 'room' if is_room_message else 'contact',
            'sender': sender_name,
            'sender_pubkey': sender_key,
            'actual_sender': actual_sender_name,  # For room messages, this is the real sender
            'actual_sender_pubkey': signature if is_room_message else None,
            'text': msg_data.get('text', ''),
            'timestamp': msg_data.get('timestamp', msg_data.get('sender_timestamp', 0)),
            'channel': None,
            'snr': msg_data.get('SNR'),
            'path_len': msg_data.get('path_len'),
            'txt_type': msg_data.get('txt_type'),
            'signature': signature,
        })
        
        # Store in database
        self.db.store_message(self.messages[-1])
        
        # Update contact last_seen when receiving a message from them
        if self.contacts and sender_key:
            contact = self.contacts.get_by_key(sender_key)
            if contact:
                self.db.store_contact(contact, is_me=False)
        
        self.logger.info(f"Stored message from {sender_name}: {msg_data.get('text', '')[:50]}")
        
        # Trigger callback for UI notification
        if self._message_callback:
            try:
                msg_type = 'room' if is_room_message else 'contact'
                self._message_callback(sender_name, msg_data.get('text', ''), msg_type)
            except Exception as e:
                self.logger.error(f"Error in message callback: {e}")

    async def _handle_channel_message(self, event):
        """Handle channel message received event."""
        self.logger.info(f"📢 EVENT: Channel message received: {event.payload}")
        print(f"DEBUG: Channel message received: {event.payload}")
        
        # Store message in the messages list
        msg_data = event.payload or {}
        sender_key = msg_data.get('pubkey_prefix', msg_data.get('sender', ''))
        
        # Channel messages have sender name embedded in text like "SenderName: message"
        text = msg_data.get('text', '')
        sender_name = 'Unknown'
        
        # Try to extract sender from text prefix
        if ': ' in text:
            potential_sender, message_text = text.split(': ', 1)
            # Verify this looks like a sender name (not part of the message)
            if len(potential_sender) < 50 and not potential_sender.startswith(' '):
                sender_name = potential_sender
                text = message_text  # Use message without sender prefix
        
        # Try to find contact by name or key
        if self.contacts:
            if sender_key:
                contact = self.contacts.get_by_key(sender_key)
                if contact:
                    sender_name = contact.get('adv_name') or contact.get('name', sender_name)
            else:
                # Try to find by name we extracted
                contact = self.contacts.get_by_name(sender_name)
                if contact:
                    sender_key = contact.get('public_key') or contact.get('pubkey', '')
        
        channel_idx = msg_data.get('channel_idx', msg_data.get('channel', 0))
        channel_name = f"Channel {channel_idx}" if channel_idx != 0 else "Public"
        
        self.messages.append({
            'type': 'channel',
            'sender': sender_name,
            'sender_pubkey': sender_key,
            'text': text,
            'timestamp': msg_data.get('sender_timestamp', msg_data.get('timestamp', 0)),
            'channel': channel_idx,
            'snr': msg_data.get('SNR'),
            'path_len': msg_data.get('path_len'),
            'txt_type': msg_data.get('txt_type'),
        })
        
        # Store in database
        self.db.store_message(self.messages[-1])
        
        # Update contact last_seen when receiving a channel message from them
        if self.contacts and sender_key:
            contact = self.contacts.get_by_key(sender_key)
            if contact:
                self.db.store_contact(contact, is_me=False)
        elif self.contacts and sender_name != 'Unknown':
            contact = self.contacts.get_by_name(sender_name)
            if contact:
                self.db.store_contact(contact, is_me=False)
        
        self.logger.info(f"Stored channel message from {sender_name} on channel {channel_idx}")
        
        # Trigger callback for UI notification
        if self._message_callback:
            try:
                channel_name = f"Channel {channel_idx}" if channel_idx != 0 else "Public"
                self._message_callback(sender_name, msg_data.get('text', ''), 'channel', channel_name)
            except Exception as e:
                self.logger.error(f"Error in message callback: {e}")

    async def _handle_channel_info(self, event):
        """Handle channel information event."""
        self.logger.info(f"📻 EVENT: Channel info: {event.payload}")
        print(f"DEBUG: Channel info received: {event.payload}")
        
        # Store channel info
        if not hasattr(self, 'channel_info_list'):
            self.channel_info_list = []
        
        # Add or update channel info
        channel_data = event.payload
        if channel_data:
            # Update existing or append new
            channel_idx = channel_data.get('channel_idx')
            found = False
            for i, ch in enumerate(self.channel_info_list):
                if ch.get('channel_idx') == channel_idx:
                    self.channel_info_list[i] = channel_data
                    found = True
                    break
            if not found:
                self.channel_info_list.append(channel_data)

    async def refresh_contacts(self):
        """Refresh the contacts list."""
        if not self.meshcore:
            self.logger.warning("Cannot refresh contacts: no meshcore connection")
            print("DEBUG: Cannot refresh contacts - no meshcore connection")
            return

        # Prevent refresh loops
        if self._refreshing_contacts:
            self.logger.debug("Already refreshing contacts, skipping")
            return
            
        self._refreshing_contacts = True
        try:
            self.logger.debug("Refreshing contacts via ContactManager...")
            print("DEBUG: Refreshing contacts via ContactManager...")
            
            # Delegate to ContactManager
            if self.contacts:
                await self.contacts.refresh()
                contact_list = self.contacts.get_all()
                self.logger.info(f"Successfully refreshed {len(contact_list)} contacts")
                print(f"DEBUG: Successfully refreshed {len(contact_list)} contacts")
                
                # Store contacts in database
                for contact in contact_list:
                    self.db.store_contact(contact)
                
                if contact_list:
                    self.logger.debug(
                        f"Contact names: {[c.get('name', 'Unknown') for c in contact_list]}"
                    )
                    print(
                        f"DEBUG: Contact names: {[c.get('name', 'Unknown') for c in contact_list]}"
                    )
            else:
                self.logger.error("ContactManager not initialized")
                print("DEBUG: ContactManager not initialized")
                
        except asyncio.TimeoutError:
            self.logger.error("Timeout refreshing contacts")
            print("DEBUG: Timeout refreshing contacts")
        except Exception as e:
            self.logger.error(f"Failed to refresh contacts: {e}")
            print(f"DEBUG: Failed to refresh contacts: {e}")
            import traceback

            self.logger.debug(f"Traceback: {traceback.format_exc()}")
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
        finally:
            self._refreshing_contacts = False

    async def send_message(self, recipient_name: str, message: str) -> Optional[Dict[str, Any]]:
        """Send a direct message to a contact.
        
        Args:
            recipient_name: The display name of the contact
            message: The message text to send
            
        Returns:
            Dict with status info if successful, None if failed
        """
        if not self.meshcore:
            return None

        try:
            # Look up the contact to get their pubkey/id
            contact = self.get_contact_by_name(recipient_name)
            if not contact:
                self.logger.error(f"Contact '{recipient_name}' not found")
                return None
            
            # Try to get the recipient identifier (public_key is the standard field)
            recipient = contact.get("public_key") or contact.get("pubkey") or contact.get("id") or contact.get("pk")
            if not recipient:
                self.logger.error(f"Contact '{recipient_name}' has no public_key/id field")
                self.logger.debug(f"Contact fields: {list(contact.keys())}")
                return None
            
            self.logger.info(f"Sending message to {recipient_name} (key: {recipient[:16]}...)")
            result = await self.meshcore.commands.send_msg(recipient, message)
            
            if result.type == EventType.ERROR:
                self.logger.error(f"Failed to send message: {result}")
                return None
            
            # Store sent message in database
            import time
            sent_msg = {
                'type': 'contact',
                'sender': 'Me',  # Mark as sent by me
                'sender_pubkey': '',  # We don't have our own pubkey easily accessible
                'recipient': recipient_name,
                'recipient_pubkey': recipient,
                'text': message,
                'timestamp': int(time.time()),
                'channel': None,
                'sent': True,  # Flag to indicate this is outgoing
            }
            self.messages.append(sent_msg)
            self.db.store_message(sent_msg)
            
            # Return status information
            status_info = {
                'status': 'sent',
                'result': result.payload if hasattr(result, 'payload') else {},
            }
            self.logger.info(f"Message sent successfully: {status_info}")
            return status_info
            
        except Exception as e:
            self.logger.error(f"Error sending message: {e}")
            import traceback
            self.logger.debug(f"Traceback: {traceback.format_exc()}")
            return None

    def is_logged_into_room(self, room_name: str) -> bool:
        """Check if we're logged into a room server."""
        if self.rooms:
            return self.rooms.is_logged_in(room_name)
        return False

    async def login_to_room(self, room_name: str, password: str) -> bool:
        """Login to a room server.
        
        Args:
            room_name: Name of the room server contact
            password: Password for the room
            
        Returns:
            True if login successful, False otherwise
        """
        if not self.rooms or not self.contacts:
            return False

        try:
            # Look up the room contact
            contact = self.contacts.get_by_name(room_name)
            if not contact:
                self.logger.error(f"Room '{room_name}' not found")
                return False
            
            # Verify it's a room server (type 3)
            if not self.contacts.is_room_server(contact):
                self.logger.error(f"Contact '{room_name}' is not a room server")
                return False
            
            # Get the room's public key
            room_key = contact.get("public_key") or contact.get("pubkey")
            if not room_key:
                self.logger.error(f"Room '{room_name}' has no public_key")
                return False
            
            # Delegate to RoomManager (pass contact dict, not just key)
            return await self.rooms.login(room_name, contact, password)
            
        except Exception as e:
            self.logger.error(f"Error logging into room: {e}")
            return False

    async def _fetch_room_messages(self, room_key: str) -> None:
        """Fetch queued messages from a room server after login.
        
        Args:
            room_key: Public key of the room server
        """
        if not self.meshcore:
            return
        
        try:
            # Keep fetching messages until we get NO_MORE_MSGS
            message_count = 0
            max_messages = 100  # Safety limit
            
            while message_count < max_messages:
                # Get next message with timeout
                result = await asyncio.wait_for(
                    self.meshcore.commands.get_msg(),
                    timeout=3.0
                )
                
                if result.type == EventType.NO_MORE_MSGS:
                    self.logger.info(f"Retrieved {message_count} queued messages from room")
                    break
                elif result.type == EventType.CONTACT_MSG_RECV:
                    # Got a message - store it
                    msg_data = result.payload
                    self.messages.append({
                        'type': 'contact',
                        'sender': msg_data.get('pubkey_prefix', 'Unknown'),
                        'text': msg_data.get('text', ''),
                        'timestamp': msg_data.get('timestamp', 0),
                        'channel': None,
                    })
                    message_count += 1
                    self.logger.debug(f"Received room message {message_count}: {msg_data.get('text', '')[:50]}")
                elif result.type == EventType.ERROR:
                    self.logger.error(f"Error fetching room message: {result.payload}")
                    break
                else:
                    # Got some other event, skip it
                    self.logger.debug(f"Got unexpected event while fetching room messages: {result.type}")
                    
        except asyncio.TimeoutError:
            self.logger.info(f"Timeout fetching room messages after {message_count} messages")
        except Exception as e:
            self.logger.error(f"Error fetching room messages: {e}")
            import traceback
            self.logger.debug(f"Traceback: {traceback.format_exc()}")

    async def send_channel_message(self, channel: Union[str, int], message: str) -> bool:
        """Send a message to a channel.
        
        Args:
            channel: Channel index (int) or channel name (str)
            message: Message text to send
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
                    if ch_info.get('name') == channel:
                        channel_idx = ch_info.get('id', 0)
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
            
            # Store sent channel message
            import time
            sent_msg = {
                'type': 'channel',
                'sender': 'Me',
                'sender_pubkey': '',
                'text': message,
                'timestamp': int(time.time()),
                'channel': channel,
                'sent': True,
            }
            self.messages.append(sent_msg)
            self.db.store_message(sent_msg)
            
            return True
        except Exception as e:
            self.logger.error(f"Error sending channel message: {e}")
            return False

    async def get_messages(self) -> List[Dict[str, Any]]:
        """Get all messages (both received via events and polled)."""
        if not self.meshcore:
            return []

        try:
            messages = []
            
            # Get messages from event storage first
            if hasattr(self, 'received_messages'):
                messages.extend(self.received_messages)
                self.logger.debug(f"Found {len(self.received_messages)} messages from events")
            
            # Poll for additional messages that might not have triggered events
            max_poll_messages = 50
            message_count = 0
            
            try:
                while message_count < max_poll_messages:
                    msg_result = await asyncio.wait_for(
                        self.meshcore.commands.get_msg(), timeout=1.0
                    )
                    if msg_result.type == EventType.ERROR or msg_result.type == EventType.NO_MORE_MSGS:
                        break
                    
                    # Add timestamp and type info
                    message_data = {
                        'type': 'polled',
                        'timestamp': self.meshcore.time,
                        **msg_result.payload
                    }
                    messages.append(message_data)
                    self.logger.debug(f"Polled message: {msg_result.payload}")
                    message_count += 1
                    
            except asyncio.TimeoutError:
                self.logger.debug("Finished polling messages (timeout)")
            except Exception as e:
                self.logger.debug(f"Finished polling messages: {e}")

            # Sort messages by timestamp if available
            messages.sort(key=lambda x: x.get('timestamp', 0))
            
            if len(messages) > 0:
                self.logger.info(f"Retrieved {len(messages)} total messages")
            else:
                self.logger.debug("Retrieved 0 total messages")
            return messages
        except Exception as e:
            self.logger.error(f"Error getting messages: {e}")
            return []

    def set_message_callback(self, callback):
        """Set callback for new message notifications.
        
        Args:
            callback: Function to call when new message arrives.
                     Signature: callback(sender, text, msg_type, channel_name=None)
        """
        self._message_callback = callback

    async def disconnect(self):
        """Disconnect from the device.
        
        Note: You may see 'Task was destroyed but it is pending!' warnings
        from meshcore.events.EventDispatcher._process_events(). This is a
        known issue in the meshcore library and does not affect functionality.
        """
        if self.meshcore:
            try:
                self.logger.info("Disconnecting from device...")
                
                # MeshCore's EventDispatcher will be cleaned up when the object is deleted
                # Just clear our reference and let Python's garbage collector handle it
                meshcore_instance = self.meshcore
                self.meshcore = None
                
                # Give a moment for any pending events to complete
                await asyncio.sleep(0.2)
                
                # Now delete the instance (may produce EventDispatcher warnings from meshcore)
                del meshcore_instance
                
            except Exception as e:
                self.logger.error(f"Error during disconnect: {e}")

        self.connected = False
        self.connection_type = None
        self.device_info = None
        self.meshcore = None
        self.connected = False
        self.connection_type = None
        self.device_info = None
        self.contacts = None
        self.channels = None
        self.rooms = None
        self.logger.info("Disconnected")

    def get_device_info(self) -> Optional[Dict[str, Any]]:
        """Get current device information."""
        return self.device_info

    def get_contacts(self) -> List[Dict[str, Any]]:
        """Get current contacts list."""
        if self.contacts:
            return self.contacts.get_all()
        return []

    def get_contact_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a contact by their name."""
        if self.contacts:
            return self.contacts.get_by_name(name)
        return None

    def get_messages_for_contact(self, contact_name: str) -> List[Dict[str, Any]]:
        """Get messages for a specific contact or room from database.
        
        Args:
            contact_name: Name of contact or room
            
        Returns:
            List of message dictionaries
        """
        return self.db.get_messages_for_contact(contact_name, limit=1000)

    def get_messages_for_channel(self, channel_name: str) -> List[Dict[str, Any]]:
        """Get messages for a specific channel from database.
        
        Args:
            channel_name: "Public" or channel name
            
        Returns:
            List of message dictionaries
        """
        # Determine channel index
        if channel_name == "Public":
            channel_idx = 0
        else:
            # Try to extract channel index from name like "Channel 1"
            try:
                channel_idx = int(channel_name.split()[-1])
            except:
                channel_idx = 0
        
        return self.db.get_messages_for_channel(channel_idx, limit=1000)
    
    def mark_as_read(self, contact_or_channel: str):
        """Mark all messages from a contact/channel as read.
        
        Args:
            contact_or_channel: Name of contact, room, or channel
        """
        import time
        self.db.mark_as_read(contact_or_channel, int(time.time()))
        self.logger.debug(f"Marked {contact_or_channel} as read")
    
    def get_unread_count(self, contact_or_channel: str) -> int:
        """Get the number of unread messages for a contact/channel.
        
        Args:
            contact_or_channel: Name of contact, room, or channel
            
        Returns:
            Number of unread messages
        """
        return self.db.get_unread_count(contact_or_channel)
    
    def get_all_unread_counts(self) -> Dict[str, int]:
        """Get unread counts for all contacts/channels.
        
        Returns:
            Dictionary mapping contact/channel names to unread counts
        """
        return self.db.get_all_unread_counts()
    
    def _load_recent_messages(self):
        """Load recent messages from database into memory cache."""
        try:
            # Load recent conversations to initialize unread counts
            conversations = self.db.get_recent_conversations(limit=50)
            self.logger.info(f"Loaded {len(conversations)} recent conversations from database")
        except Exception as e:
            self.logger.error(f"Failed to load recent messages: {e}")
    
    def _save_messages(self):
        """Legacy method - now using database directly."""
        pass  # Database saves in real-time
    
    async def _periodic_save_messages(self):
        """Legacy method - no longer needed with database."""
        pass  # Database handles persistence

    def is_connected(self) -> bool:
        """Check if connected to a device."""
        try:
            return bool(self.connected and self.meshcore and getattr(self.meshcore, "is_connected", False))
        except Exception:
            return bool(self.connected)

    def test_logging(self):
        """Test method to verify logging is working."""
        self.logger.info("🧪 TEST: Logging system test message")
        self.logger.debug("🧪 TEST: Debug logging test")
        print("DEBUG: Direct print test from connection.py")
        return "Logging test completed"

    async def login_to_repeater(self, repeater_name: str, password: str) -> bool:
        """Log into a repeater node."""
        if not self.meshcore:
            return False

        try:
            result = await self.meshcore.commands.login(repeater_name, password)
            if result.type == EventType.ERROR:
                self.logger.error(
                    f"Failed to login to repeater {repeater_name}: {result}"
                )
                return False
            self.logger.info(f"Successfully logged into repeater {repeater_name}")
            return True
        except Exception as e:
            self.logger.error(f"Error logging into repeater {repeater_name}: {e}")
            return False

    async def logout_from_repeater(self, repeater_name: str) -> bool:
        """Log out from a repeater node."""
        if not self.meshcore:
            return False

        try:
            result = await self.meshcore.commands.logout(repeater_name)
            if result.type == EventType.ERROR:
                self.logger.error(
                    f"Failed to logout from repeater {repeater_name}: {result}"
                )
                return False
            self.logger.info(f"Successfully logged out from repeater {repeater_name}")
            return True
        except Exception as e:
            self.logger.error(f"Error logging out from repeater {repeater_name}: {e}")
            return False

    async def send_command_to_repeater(self, repeater_name: str, command: str) -> bool:
        """Send a command to a repeater node (no ack)."""
        if not self.meshcore:
            return False

        try:
            result = await self.meshcore.commands.send_command(repeater_name, command)
            if result.type == EventType.ERROR:
                self.logger.error(
                    f"Failed to send command to repeater {repeater_name}: {result}"
                )
                return False
            self.logger.info(f"Command sent to repeater {repeater_name}: {command}")
            return True
        except Exception as e:
            self.logger.error(f"Error sending command to repeater {repeater_name}: {e}")
            return False

    async def request_repeater_status(
        self, repeater_name: str
    ) -> Optional[Dict[str, Any]]:
        """Request status from a repeater node."""
        if not self.meshcore:
            return None

        try:
            result = await self.meshcore.commands.request_status(repeater_name)
            if result.type == EventType.ERROR:
                self.logger.error(
                    f"Failed to get status from repeater {repeater_name}: {result}"
                )
                return None
            self.logger.info(f"Received status from repeater {repeater_name}")
            return result.payload
        except Exception as e:
            self.logger.error(
                f"Error requesting status from repeater {repeater_name}: {e}"
            )
            return None

    async def wait_for_repeater_message(
        self, timeout: int = 8
    ) -> Optional[Dict[str, Any]]:
        """Wait for a message/reply from a repeater with timeout."""
        if not self.meshcore:
            return None

        try:
            result = await self.meshcore.commands.wait_message(timeout=timeout)
            if result.type == EventType.ERROR:
                self.logger.error(f"Error waiting for repeater message: {result}")
                return None
            if result.type == EventType.TIMEOUT:
                self.logger.info("Timeout waiting for repeater message")
                return None
            self.logger.info("Received message from repeater")
            return result.payload
        except Exception as e:
            self.logger.error(f"Error waiting for repeater message: {e}")
            return None

    async def get_available_nodes(self) -> List[Dict[str, Any]]:
        """Get list of available nodes (repeaters, room servers, etc.)."""
        if not self.meshcore:
            return []

        try:
            # This might need to be implemented based on meshcore API
            # For now, return contacts that might be nodes
            await self.refresh_contacts()
            contacts = self.get_contacts()

            # Filter for potential nodes (this is a heuristic)
            nodes = []
            for contact in contacts:
                # Look for contacts that might be repeaters or room servers
                # This would need refinement based on meshcore's node identification
                if contact.get("name", "").startswith(("REP", "ROOM", "NODE")):
                    nodes.append(contact)

            self.logger.info(f"Found {len(nodes)} potential nodes")
            return nodes
        except Exception as e:
            self.logger.error(f"Error getting available nodes: {e}")
            return []

    async def get_channels(self) -> List[Dict[str, Any]]:
        """Get list of available channels."""
        if not self.meshcore:
            return []

        try:
            # Use stored channel info from events if available
            if hasattr(self, 'channel_info_list') and self.channel_info_list:
                channels = []
                for ch_info in self.channel_info_list:
                    ch_name = ch_info.get('channel_name', '')
                    if ch_name:  # Only include channels with names
                        channels.append({
                            'id': ch_info.get('channel_idx', 0),
                            'name': ch_name,
                            **ch_info
                        })
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
                        if channel_info and channel_info.get('channel_name'):
                            channels.append({
                                'id': channel_id,
                                'name': channel_info.get('channel_name', 'Unknown'),
                                **channel_info
                            })
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
        """Join a channel by name and optional key."""
        if not self.meshcore:
            return False

        try:
            # Find an available channel slot (0-7)
            channels = await self.get_channels()
            used_slots = [ch.get('id', -1) for ch in channels]
            
            available_slot = None
            for slot in range(8):
                if slot not in used_slots:
                    available_slot = slot
                    break
            
            if available_slot is None:
                self.logger.error("No available channel slots")
                return False
            
            # Set the channel
            channel_config = {
                'name': channel_name,
                'key': key,
                'id': available_slot
            }
            
            result = await self.meshcore.commands.set_channel(available_slot, channel_config)
            if result.type == EventType.ERROR:
                self.logger.error(f"Failed to join channel {channel_name}: {result}")
                return False
            
            self.logger.info(f"Successfully joined channel {channel_name} on slot {available_slot}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error joining channel {channel_name}: {e}")
            return False

    async def send_channel_message(self, channel_id: int, message: str) -> bool:
        """Send a message to a specific channel."""
        if not self.meshcore:
            return False

        try:
            result = await self.meshcore.commands.send_chan_msg(channel_id, message)
            if result.type == EventType.ERROR:
                self.logger.error(f"Failed to send channel message: {result}")
                return False
            
            self.logger.info(f"Sent message to channel {channel_id}: {message}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error sending channel message: {e}")
            return False

    def clear_received_messages(self):
        """Clear the received messages buffer."""
        if hasattr(self, 'received_messages'):
            self.received_messages.clear()
            self.logger.debug("Cleared received messages buffer")
