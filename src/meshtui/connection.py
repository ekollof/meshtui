#!/usr/bin/env python3
"""
Connection manager for MeshCore devices.
Orchestrates transport, contacts, channels, and rooms.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

import serial.tools.list_ports
from bleak import BleakScanner
from meshcore import MeshCore, EventType

from .contact import ContactManager
from .channel import ChannelManager
from .room import RoomManager
from .transport import SerialTransport, BLETransport, TCPTransport, ConnectionType


class MeshConnection:
    """Manages connection to MeshCore devices and orchestrates domain managers.

    Architecture:
    - Transport Layer: SerialTransport, BLETransport, TCPTransport (low-level connection)
    - Manager Layer: ContactManager, ChannelManager, RoomManager (domain logic)
    - Database Layer: MessageDatabase (persistence)
    - Connection Layer (this class): Orchestrates managers, handles events, stores messages

    Responsibilities:
    - Connection lifecycle (connect, disconnect, reconnect)
    - Event handling and routing to managers
    - Message persistence (sends via managers, stores in DB)
    - Provides unified API for UI layer

    Delegates domain logic to:
    - ContactManager: contact refresh, direct messaging
    - ChannelManager: channel discovery, channel messaging
    - RoomManager: room authentication, room messaging
    """

    def __init__(self):
        self.meshcore: Optional[MeshCore] = None
        self.connected = False
        self.connection_type: Optional[ConnectionType] = None
        self.device_info: Optional[Dict[str, Any]] = None
        self.messages: List[Dict[str, Any]] = []  # In-memory cache for quick access
        self.logger = logging.getLogger("meshtui.connection")

        # Enable DEBUG logging for meshcore to see raw packets
        meshcore_logger = logging.getLogger("meshcore")
        meshcore_logger.setLevel(logging.DEBUG)
        self.logger.info(
            "🔍 Enabled DEBUG logging for meshcore library (raw packet logging)"
        )

        # Managers (will be initialized after connection)
        self.contacts: Optional[ContactManager] = None
        self.channels: Optional[ChannelManager] = None
        self.rooms: Optional[RoomManager] = None

        # Flags to prevent spam
        self._refreshing_contacts = False

        # Callbacks for UI updates
        self._message_callback = None
        self._contacts_callback = None

        # ACK tracking for sent messages
        self._pending_acks: Dict[str, Dict[str, Any]] = (
            {}
        )  # ack_code -> {timestamp, repeats, message_preview}

        # Unread message tracking
        self.unread_counts: Dict[str, int] = {}  # contact_name -> unread count
        self.last_read_index: Dict[str, int] = (
            {}
        )  # contact_name -> last read message index
        self._messages_dirty = False  # Track if messages need saving
        self._save_task = None  # Background save task

        # Configuration
        self.config_dir = Path.home() / ".config" / "meshtui"
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Database for persistent storage (will be initialized per-device after connection)
        from .database import MessageDatabase

        self.db: Optional[MessageDatabase] = None
        self._db_initialized = False

        self.address_file = self.config_dir / "default_address"

        # Transport layers
        self.serial_transport = SerialTransport()
        self.ble_transport = BLETransport(self.config_dir)
        self.tcp_transport = TCPTransport()

    async def identify_meshcore_device(
        self, device_path: str, timeout: float = 5.0
    ) -> bool:
        """Identify if a serial device is a MeshCore device by attempting to connect and query.

        Delegates to SerialTransport for improved reliability with retries.
        """
        return await self.serial_transport.identify_device(device_path, timeout=timeout)

    async def scan_ble_devices(self, timeout: float = 2.0) -> List[Dict[str, Any]]:
        """Scan for available BLE MeshCore devices."""
        self.logger.info(f"Scanning for BLE devices (timeout: {timeout}s)...")
        try:
            devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
            meshcore_devices = []

            for device, advertisement_data in devices.items():
                if device.name and device.name.startswith("MeshCore-"):
                    meshcore_devices.append(
                        {
                            "name": device.name,
                            "address": device.address,
                            "rssi": (
                                advertisement_data.rssi if advertisement_data else None
                            ),
                            "device": device,
                        }
                    )

            self.logger.info(f"Found {len(meshcore_devices)} BLE MeshCore devices")
            return meshcore_devices

        except Exception as e:
            self.logger.error(f"BLE scan failed: {e}")
            return []

    async def scan_serial_devices(
        self, quick_scan: bool = False
    ) -> List[Dict[str, Any]]:
        """Scan for available serial devices and identify MeshCore devices.

        Args:
            quick_scan: If True, only scan likely candidates (USB/ACM) for faster detection

        Returns:
            List of device info dictionaries with is_meshcore flag
        """
        self.logger.info("Scanning for serial devices...")
        try:
            ports = serial.tools.list_ports.comports()
            serial_devices = []

            # Prioritize likely MeshCore devices first
            priority_ports = []
            other_ports = []

            for port in ports:
                device_path = port.device.lower()
                # USB serial devices are most likely to be MeshCore
                if (
                    "usb" in device_path
                    or "acm" in device_path
                    or "tty.usb" in device_path
                ):
                    priority_ports.append(port)
                else:
                    other_ports.append(port)

            # Sort priority ports - prefer ttyUSB0, then ttyUSB*, then ttyACM*
            def sort_key(port):
                device = port.device.lower()
                if "ttyusb0" in device:
                    return 0
                elif "ttyusb" in device:
                    return 1
                elif "ttyacm" in device:
                    return 2
                else:
                    return 3

            priority_ports.sort(key=sort_key)

            # In quick scan mode, only check priority ports
            ports_to_check = (
                priority_ports if quick_scan else priority_ports + other_ports
            )

            self.logger.info(
                f"Found {len(ports)} serial ports, checking {len(ports_to_check)} ports..."
            )

            for port in ports_to_check:
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
                    # Found one! Add it and we can stop if we want
                    serial_devices.append(device_info)
                    if quick_scan:
                        # In quick scan, return as soon as we find one
                        self.logger.info(
                            "Quick scan found MeshCore device, stopping search"
                        )
                        break
                else:
                    device_info["is_meshcore"] = False
                    serial_devices.append(device_info)

            meshcore_count = sum(
                1 for d in serial_devices if d.get("is_meshcore", False)
            )
            self.logger.info(
                f"Scanned {len(serial_devices)} devices, {meshcore_count} are MeshCore devices"
            )
            return serial_devices

        except Exception as e:
            self.logger.error(f"Serial scan failed: {e}")
            return []

    async def connect_ble(
        self,
        address: Optional[str] = None,
        device=None,
        pin: Optional[str] = None,
        timeout: float = 2.0,
    ) -> bool:
        """Connect to a MeshCore device via BLE.

        Args:
            address: BLE address to connect to
            device: BLE device object (alternative to address)
            pin: PIN for BLE pairing authentication (usually shown on device screen)
            timeout: Scan timeout if no address provided

        Returns:
            True if connected successfully
        """
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

            self.logger.info(
                f"Connecting to BLE device: {address}" + (" with PIN" if pin else "")
            )
            try:
                self.meshcore = await MeshCore.create_ble(
                    address=address,
                    device=device,
                    pin=pin,
                    debug=False,
                    only_error=False,
                )
            except Exception as e:
                self.logger.error(f"BLE connection failed during initialization: {e}")
                import traceback

                self.logger.debug(f"BLE connection traceback: {traceback.format_exc()}")
                return False

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

            # Initialize device-specific database
            self._initialize_device_database()

            # Initialize managers
            self._initialize_managers()

            # Explicitly refresh contacts after connection
            self.logger.debug("Refreshing contacts after BLE connection...")
            await self.refresh_contacts()

            # Auto-sync time if device has no GPS
            await self.auto_sync_time_if_needed()

            contact_count = len(self.contacts.get_all()) if self.contacts else 0
            self.logger.info(
                f"Connected to {self.device_info.get('name', 'Unknown')} via BLE. Found {contact_count} contacts."
            )
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

            # Initialize device-specific database
            self._initialize_device_database()

            # Initialize managers
            self._initialize_managers()

            # Explicitly refresh contacts after connection
            self.logger.debug("Refreshing contacts after TCP connection...")
            await self.refresh_contacts()

            # Auto-sync time if device has no GPS
            await self.auto_sync_time_if_needed()

            contact_count = len(self.contacts.get_all()) if self.contacts else 0
            self.logger.info(
                f"Connected to {self.device_info.get('name', 'Unknown')} via TCP. Found {contact_count} contacts."
            )
            return True

        except Exception as e:
            self.logger.error(f"TCP connection failed: {e}")
            return False

    async def connect_serial(
        self, port: str, baudrate: int = 115200, verify_meshcore: bool = True
    ) -> bool:
        """Connect to a MeshCore device via serial.

        Args:
            port: Serial port path (e.g., '/dev/ttyUSB0')
            baudrate: Connection baudrate (default: 115200)
            verify_meshcore: If True, verify device is MeshCore before connecting (default: True)

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Optional: Verify this is a MeshCore device first
            if verify_meshcore:
                self.logger.info(f"Verifying {port} is a MeshCore device...")
                is_meshcore = await self.identify_meshcore_device(port)
                if not is_meshcore:
                    self.logger.error(f"{port} is not a MeshCore device")
                    return False

            self.logger.info(f"Connecting to serial device: {port}@{baudrate}")
            self.meshcore = await MeshCore.create_serial(
                port=port, baudrate=baudrate, debug=False, only_error=False
            )

            # Give device time to initialize
            await asyncio.sleep(0.2)

            # Test connection
            self.logger.debug("Sending device query to test connection...")
            result = await asyncio.wait_for(
                self.meshcore.commands.send_device_query(), timeout=5.0
            )
            if result.type == EventType.ERROR:
                self.logger.error(f"Device query failed: {result}")
                await self.meshcore.disconnect()
                self.meshcore = None
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

            # Initialize device-specific database
            self._initialize_device_database()

            # Initialize managers
            self._initialize_managers()

            # Explicitly refresh contacts after connection
            self.logger.debug("Refreshing contacts after connection...")
            await self.refresh_contacts()

            # Auto-sync time if device has no GPS
            await self.auto_sync_time_if_needed()

            contact_count = len(self.contacts.get_all()) if self.contacts else 0
            self.logger.info(
                f"Connected to {self.device_info.get('name', 'Unknown')} via serial. Found {contact_count} contacts."
            )
            return True

        except asyncio.TimeoutError:
            self.logger.error(f"Timeout connecting to serial device {port}")
            if self.meshcore:
                try:
                    await self.meshcore.disconnect()
                except Exception:
                    pass
                self.meshcore = None
            return False
        except Exception as e:
            self.logger.error(f"Serial connection failed: {e}")
            import traceback

            self.logger.debug(f"Traceback: {traceback.format_exc()}")
            if self.meshcore:
                try:
                    await self.meshcore.disconnect()
                except Exception:
                    pass
                self.meshcore = None
            return False

    def _initialize_device_database(self):
        """Initialize database specific to this device using its public key.

        This creates a per-device database in ~/.config/meshtui/devices/<pubkey>.db
        to avoid data collision when connecting to different devices.
        """
        if self._db_initialized:
            return

        try:
            # Get device public key from self_info
            device_pubkey = None
            if self.meshcore and hasattr(self.meshcore, "self_info"):
                self_info = self.meshcore.self_info
                device_pubkey = self_info.get("public_key")

            # Create devices directory
            devices_dir = self.config_dir / "devices"
            devices_dir.mkdir(parents=True, exist_ok=True)

            if device_pubkey:
                # Use first 16 chars of pubkey for filename (enough to be unique)
                pubkey_short = device_pubkey[:16]
                db_path = devices_dir / f"{pubkey_short}.db"
                self.logger.info(f"Using device-specific database: {db_path.name}")
            else:
                # Fallback: use temporary database if pubkey not available
                self.logger.warning(
                    "Device public key not available, using temporary database"
                )
                db_path = self.config_dir / "meshtui-temp.db"

            # Initialize database for this device
            from .database import MessageDatabase

            self.db = MessageDatabase(db_path)
            self._db_initialized = True

            # Load recent messages into cache
            self._load_recent_messages()

            self.logger.debug(f"Database initialized at {db_path}")

        except Exception as e:
            self.logger.error(f"Failed to initialize device database: {e}")
            # Fallback to legacy database
            self.logger.info("Falling back to legacy database")
            from .database import MessageDatabase

            self.db = MessageDatabase(self.config_dir / "meshtui.db")
            self._db_initialized = True

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
            self.logger.debug(
                "auto_update_contacts not available on this MeshCore instance"
            )

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
        self.meshcore.subscribe(
            EventType.CONTACT_MSG_RECV, self._handle_contact_message
        )
        self.meshcore.subscribe(
            EventType.CHANNEL_MSG_RECV, self._handle_channel_message
        )
        self.meshcore.subscribe(EventType.ADVERTISEMENT, self._handle_advertisement)
        self.meshcore.subscribe(EventType.PATH_UPDATE, self._handle_path_update)
        self.meshcore.subscribe(EventType.CHANNEL_INFO, self._handle_channel_info)
        self.meshcore.subscribe(EventType.ACK, self._handle_ack)
        self.logger.debug("Event handlers subscribed")

    async def _handle_new_contact(self, event):
        """Handle new contact event - store immediately."""
        self.logger.info(f"📡 EVENT: New contact detected: {event.payload}")

        # Store new contact immediately
        contact_data = event.payload or {}
        if self.db and contact_data.get("public_key"):
            self.db.store_contact(contact_data, is_me=False)
            self.logger.info(
                f"Stored new contact: {contact_data.get('name', 'Unknown')}"
            )

        # Update contacts list
        await self.refresh_contacts()

    async def _handle_advertisement(self, event):
        """Handle advertisement event - update contact when they broadcast."""
        self.logger.info(f"📡 EVENT: Advertisement received: {event.payload}")

        # Extract contact info from advertisement
        adv_data = event.payload or {}
        pubkey = adv_data.get("public_key")

        if pubkey and self.contacts:
            # Try to find this contact
            contact = self.contacts.get_by_key(pubkey)
            if self.db and contact:
                # Update their last_seen timestamp
                self.db.store_contact(contact, is_me=False)
                self.logger.debug(
                    f"Updated contact {contact.get('name')} from advertisement"
                )
            elif self.db:
                # New contact from advertisement - create minimal contact record
                contact_data = {
                    "public_key": pubkey,
                    "name": adv_data.get("name", pubkey[:12]),
                    "adv_name": adv_data.get(
                        "adv_name", adv_data.get("name", pubkey[:12])
                    ),
                    "type": adv_data.get("type", 0),
                }
                self.db.store_contact(contact_data, is_me=False)
                self.logger.info(
                    f"Created new contact from advertisement: {contact_data.get('name')}"
                )

                # Trigger contacts refresh to update UI (with small delay to avoid overwhelming device)
                await asyncio.sleep(0.5)
                await self.refresh_contacts()

    async def _handle_path_update(self, event):
        """Handle path update event."""
        self.logger.info(f"📡 EVENT: Path update: {event.payload}")

    async def _handle_contacts_update(self, event):
        """Handle contacts list update event."""
        # Prevent refresh loops
        if self._refreshing_contacts:
            self.logger.debug("Skipping contacts update event (already refreshing)")
            return

        self.logger.info("📡 EVENT: Contacts update received")
        # Refresh contacts through the manager
        await self.refresh_contacts()

    async def _handle_contact_message(self, event):
        """Handle direct contact message received event."""
        self.logger.info(f"📧 EVENT: Direct message received: {event.payload}")

        # Store message in the messages list
        msg_data = event.payload or {}
        sender_key = msg_data.get("pubkey_prefix", msg_data.get("sender", "Unknown"))

        # Try to identify if this is from a room server
        sender_name = sender_key
        is_room_message = False
        actual_sender_name = None
        signature = msg_data.get("signature", "")

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
                        actual_sender_name = actual_sender.get(
                            "adv_name"
                        ) or actual_sender.get("name", signature)
                        self.logger.debug(f"Room message sender: {actual_sender_name}")
                    else:
                        actual_sender_name = signature
                        self.logger.debug(f"Room message sender (unknown): {signature}")

        # If not a room, try to find contact name
        if not is_room_message and self.contacts:
            contact = self.contacts.get_by_key(sender_key)
            if contact:
                sender_name = contact.get("adv_name") or contact.get("name", sender_key)

        self.messages.append(
            {
                "type": "room" if is_room_message else "contact",
                "sender": sender_name,
                "sender_pubkey": sender_key,
                "actual_sender": actual_sender_name,  # For room messages, this is the real sender
                "actual_sender_pubkey": signature if is_room_message else None,
                "text": msg_data.get("text", ""),
                "timestamp": msg_data.get(
                    "timestamp", msg_data.get("sender_timestamp", 0)
                ),
                "channel": None,
                "snr": msg_data.get("SNR"),
                "path_len": msg_data.get("path_len"),
                "txt_type": msg_data.get("txt_type"),
                "signature": signature,
            }
        )

        # Store in database
        if self.db:
            self.db.store_message(self.messages[-1])

        # Update contact last_seen when receiving a message from them
        if self.db and self.contacts and sender_key:
            contact = self.contacts.get_by_key(sender_key)
            if contact:
                self.db.store_contact(contact, is_me=False)

        self.logger.info(
            f"Stored message from {sender_name}: {msg_data.get('text', '')[:50]}"
        )

        # Trigger callback for UI notification
        txt_type = msg_data.get("txt_type", 0)
        if self._message_callback:
            try:
                msg_type = "room" if is_room_message else "contact"
                self.logger.info(
                    f"🔔 Triggering message callback: sender={sender_name}, msg_type={msg_type}, text={msg_data.get('text', '')[:50]}"
                )
                self._message_callback(
                    sender=sender_name,
                    text=msg_data.get("text", ""),
                    msg_type=msg_type,
                    txt_type=txt_type,  # Pass txt_type so UI can route command responses
                )
            except Exception as e:
                self.logger.error(f"Error in message callback: {e}")
                import traceback

                self.logger.error(f"Callback traceback: {traceback.format_exc()}")

    async def _handle_channel_message(self, event):
        """Handle channel message received event."""
        self.logger.info(f"📢 EVENT: Channel message received: {event.payload}")

        # Store message in the messages list
        msg_data = event.payload or {}
        sender_key = msg_data.get("pubkey_prefix", msg_data.get("sender", ""))

        # Channel messages have sender name embedded in text like "SenderName: message"
        text = msg_data.get("text", "")
        sender_name = "Unknown"

        # Try to extract sender from text prefix
        if ": " in text:
            potential_sender, message_text = text.split(": ", 1)
            # Verify this looks like a sender name (not part of the message)
            if len(potential_sender) < 50 and not potential_sender.startswith(" "):
                sender_name = potential_sender
                text = message_text  # Use message without sender prefix

        # Try to find contact by name or key
        if self.contacts:
            if sender_key:
                contact = self.contacts.get_by_key(sender_key)
                if contact:
                    sender_name = contact.get("adv_name") or contact.get(
                        "name", sender_name
                    )
            else:
                # Try to find by name we extracted
                contact = self.contacts.get_by_name(sender_name)
                if contact:
                    sender_key = contact.get("public_key", "")

        channel_idx = msg_data.get("channel_idx", msg_data.get("channel", 0))
        channel_name = f"Channel {channel_idx}" if channel_idx != 0 else "Public"

        self.messages.append(
            {
                "type": "channel",
                "sender": sender_name,
                "sender_pubkey": sender_key,
                "text": text,
                "timestamp": msg_data.get(
                    "sender_timestamp", msg_data.get("timestamp", 0)
                ),
                "channel": channel_idx,
                "snr": msg_data.get("SNR"),
                "path_len": msg_data.get("path_len"),
                "txt_type": msg_data.get("txt_type"),
            }
        )

        # Store in database
        if self.db:
            self.db.store_message(self.messages[-1])

        # Update contact last_seen when receiving a channel message from them
        if self.db and self.contacts and sender_key:
            contact = self.contacts.get_by_key(sender_key)
            if contact:
                self.db.store_contact(contact, is_me=False)
        elif self.db and self.contacts and sender_name != "Unknown":
            contact = self.contacts.get_by_name(sender_name)
            if contact:
                self.db.store_contact(contact, is_me=False)

        self.logger.info(
            f"Stored channel message from {sender_name} on channel {channel_idx}"
        )

        # Trigger callback for UI notification
        if self._message_callback:
            try:
                # Look up actual channel name instead of using generic "Channel X"
                channel_name = "Public"
                if channel_idx != 0 and self.channels:
                    channels = await self.channels.get_channels()
                    for ch in channels:
                        if ch.get("id") == channel_idx:
                            channel_name = ch.get("name", f"Channel {channel_idx}")
                            break
                    else:
                        # Channel not found in list, use generic name
                        channel_name = f"Channel {channel_idx}"

                self._message_callback(
                    sender_name, msg_data.get("text", ""), "channel", channel_name
                )
            except Exception as e:
                self.logger.error(f"Error in message callback: {e}")

    async def _handle_channel_info(self, event):
        """Handle channel information event."""
        self.logger.info(f"📻 EVENT: Channel info: {event.payload}")

        # Store channel info
        if not hasattr(self, "channel_info_list"):
            self.channel_info_list = []

        # Add or update channel info
        channel_data = event.payload
        if channel_data:
            # Update existing or append new
            channel_idx = channel_data.get("channel_idx")
            found = False
            for i, ch in enumerate(self.channel_info_list):
                if ch.get("channel_idx") == channel_idx:
                    self.channel_info_list[i] = channel_data
                    found = True
                    break
            if not found:
                self.channel_info_list.append(channel_data)

    async def _handle_ack(self, event):
        """Handle ACK event - message was repeated by a repeater."""
        self.logger.info(f"📡 EVENT: ACK received: {event.payload}")

        # Extract ACK code
        ack_code = event.payload.get("code", "")

        # Check if this is a tracked message
        if ack_code in self._pending_acks:
            ack_info = self._pending_acks[ack_code]
            ack_info["repeats"] += 1
            repeats = ack_info["repeats"]

            # Update database with delivery status
            if self.db:
                self.db.update_message_delivery_status(ack_code, repeats)

            # Show updated status
            if self._message_callback:
                try:
                    if repeats == 1:
                        self._message_callback(
                            "System", f"✓ Heard {repeats} repeat", "status"
                        )
                    else:
                        self._message_callback(
                            "System", f"✓ Heard {repeats} repeats", "status"
                        )
                except Exception as e:
                    self.logger.error(f"Error in ACK callback: {e}")
        else:
            # Unknown ACK - just log it
            self.logger.debug(f"Received ACK for unknown message: {ack_code[:8]}")

    async def _check_message_timeout(self, ack_code: str, timeout_seconds: int):
        """Check if a message failed to be delivered after timeout."""
        await asyncio.sleep(timeout_seconds)

        # Check if message is still pending (no ACKs received)
        if ack_code in self._pending_acks:
            ack_info = self._pending_acks[ack_code]

            # If no repeats received, message likely failed
            if ack_info["repeats"] == 0 and not ack_info.get("failed"):
                ack_info["failed"] = True

                # Update database to mark as failed
                if self.db:
                    try:
                        cursor = self.db.conn.cursor()
                        cursor.execute(
                            """
                            UPDATE messages 
                            SET delivery_status = 'failed'
                            WHERE ack_code = ?
                        """,
                            (ack_code,),
                        )
                        self.db.conn.commit()
                    except Exception as e:
                        self.logger.error(f"Failed to update message status: {e}")

                # Show failure notification
                if self._message_callback:
                    self._message_callback(
                        "System", "✗ Delivery failed (no repeaters)", "status"
                    )

                self.logger.warning(
                    f"Message delivery failed: {ack_info['message_preview']}"
                )

    async def refresh_contacts(self):
        """Refresh the contacts list."""
        if not self.meshcore:
            self.logger.warning("Cannot refresh contacts: no meshcore connection")
            return

        # Prevent refresh loops
        if self._refreshing_contacts:
            self.logger.debug("Already refreshing contacts, skipping")
            return

        self._refreshing_contacts = True
        try:
            self.logger.debug("Refreshing contacts via ContactManager...")

            # Delegate to ContactManager
            if self.contacts:
                await self.contacts.refresh()
                contact_list = self.contacts.get_all()
                self.logger.info(f"Successfully refreshed {len(contact_list)} contacts")

                # Store contacts in database
                if self.db:
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

        except asyncio.TimeoutError:
            self.logger.error("Timeout refreshing contacts")
        except Exception as e:
            self.logger.error(f"Failed to refresh contacts: {e}")
            import traceback

            self.logger.debug(f"Traceback: {traceback.format_exc()}")
        finally:
            self._refreshing_contacts = False

            # Notify UI that contacts were updated
            if self._contacts_callback:
                try:
                    self._contacts_callback()
                except Exception as e:
                    self.logger.error(f"Error in contacts callback: {e}")

    async def send_message(
        self, recipient_name: str, message: str
    ) -> Optional[Dict[str, Any]]:
        """Send a direct message to a contact.

        Routes through ContactManager for consistency, then stores in database.

        Args:
            recipient_name: The display name of the contact
            message: The message text to send

        Returns:
            Dict with status info if successful, None if failed
        """
        if not self.meshcore or not self.contacts:
            return None

        try:
            import time

            # Use ContactManager to send the message
            status_info = await self.contacts.send_message(recipient_name, message)

            if not status_info:
                return None

            # Track the ACK code if available
            ack_code_hex = None
            suggested_timeout = status_info.get("result", {}).get(
                "suggested_timeout", 30
            )
            if status_info.get("expected_ack"):
                ack_code_hex = status_info["expected_ack"].hex()
                self._pending_acks[ack_code_hex] = {
                    "timestamp": time.time(),
                    "repeats": 0,
                    "message_preview": message[:30],
                    "recipient": recipient_name,
                    "timeout": suggested_timeout,
                    "failed": False,
                }
                self.logger.debug(
                    f"Tracking ACK for message: {ack_code_hex} (timeout: {suggested_timeout}s)"
                )

                # Show "Sent" notification
                if self._message_callback:
                    self._message_callback("System", "✓ Sent", "status")

                # Schedule timeout check
                asyncio.create_task(
                    self._check_message_timeout(ack_code_hex, suggested_timeout)
                )

            # Look up contact to get public_key for storage
            contact = self.contacts.get_by_name(recipient_name)
            recipient_pubkey = contact.get("public_key", "") if contact else ""

            # Determine message type based on recipient type
            is_room = contact and contact.get("type") == 3  # Type 3 = Room Server
            msg_type = "room" if is_room else "contact"

            # Store sent message in database with ACK code for tracking
            sent_msg = {
                "type": msg_type,
                "sender": "Me",
                "sender_pubkey": "",
                "recipient": recipient_name,
                "recipient_pubkey": recipient_pubkey,
                "text": message,
                "timestamp": int(time.time()),
                "channel": None,
                "sent": True,
                "ack_code": ack_code_hex,
                "delivery_status": "sent",
                "repeat_count": 0,
            }
            self.messages.append(sent_msg)
            if self.db:
                self.db.store_message(sent_msg)
                # Mark as read so our own sent message doesn't show as unread
                self.db.mark_as_read(recipient_pubkey or recipient_name)

            self.logger.info(f"Sent and stored {msg_type} message to {recipient_name}")
            return status_info

        except Exception as e:
            self.logger.error(f"Error sending message: {e}")
            import traceback

            self.logger.debug(f"Traceback: {traceback.format_exc()}")
            return None

    async def send_advertisement(self, hops: int = 3) -> bool:
        """Send an advertisement packet to announce presence.

        Args:
            hops: Number of hops (0 = direct neighbors only, 3 = flood entire network)

        Returns:
            True if successful
        """
        if not self.meshcore:
            return False

        try:
            # MeshCore API uses boolean flood parameter
            # hops 0 = not flood (direct neighbors), hops > 0 = flood
            flood = hops > 0
            self.logger.info(f"Sending advertisement (flood={flood}, hops={hops})")
            result = await self.meshcore.commands.send_advert(flood)

            if result.type == EventType.ERROR:
                self.logger.error(f"Failed to send advertisement: {result}")
                return False

            self.logger.info(f"Advertisement sent successfully (flood={flood})")
            return True

        except Exception as e:
            self.logger.error(f"Error sending advertisement: {e}")
            import traceback

            self.logger.debug(f"Traceback: {traceback.format_exc()}")
            return False

    def is_logged_into_room(self, room_name: str) -> bool:
        """Check if we're logged into a room server."""
        if self.rooms:
            return self.rooms.is_logged_in(room_name)
        return False

    async def _login_to_repeater(self, contact: dict, password: str) -> bool:
        """Login to a repeater node (type 2).

        This is a simple helper for repeater authentication. Unlike room servers,
        repeaters don't require complex state management, so this logic stays in
        the connection layer rather than having a dedicated RepeaterManager.

        Args:
            contact: Contact dictionary for the repeater
            password: Password for authentication

        Returns:
            True if login successful, False otherwise
        """
        try:
            node_name = contact.get("adv_name") or contact.get("name", "Unknown")
            result = await self.meshcore.commands.send_login(contact, password)

            if result.type == EventType.ERROR:
                self.logger.error(
                    f"Failed to login to repeater '{node_name}': {result}"
                )
                return False

            self.logger.info(f"Successfully logged into repeater '{node_name}'")
            return True

        except Exception as e:
            self.logger.error(f"Error logging into repeater: {e}")
            return False

    async def login_to_room(self, room_name: str, password: str) -> bool:
        """Login to a room server (type 3).

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

            # Delegate to RoomManager (pass contact dict, not just key)
            return await self.rooms.login(room_name, contact, password)

        except Exception as e:
            self.logger.error(f"Error logging into room: {e}")
            return False

    async def logout_from_room(self, room_name: str) -> bool:
        """Logout from a room server (type 3).

        Args:
            room_name: Name of the room server contact

        Returns:
            True if logout successful, False otherwise
        """
        if not self.rooms or not self.contacts:
            return False

        try:
            # Look up the room contact
            contact = self.contacts.get_by_name(room_name)
            if not contact:
                self.logger.error(f"Room '{room_name}' not found")
                return False

            # Get the room's public key
            room_key = contact.get("public_key")
            if not room_key:
                self.logger.error(f"Room '{room_name}' has no public_key")
                return False

            # Delegate to RoomManager
            return await self.rooms.logout(room_name, room_key)

        except Exception as e:
            self.logger.error(f"Error logging out from room: {e}")
            return False

    async def _logout_from_repeater(self, contact: dict) -> bool:
        """Logout from a repeater node (type 2).

        Args:
            contact: Contact dictionary for the repeater

        Returns:
            True if logout successful, False otherwise
        """
        try:
            node_name = contact.get("adv_name") or contact.get("name", "Unknown")
            result = await self.meshcore.commands.send_logout(contact)

            if result.type == EventType.ERROR:
                self.logger.error(
                    f"Failed to logout from repeater '{node_name}': {result}"
                )
                return False

            self.logger.info(f"Successfully logged out from repeater '{node_name}'")
            return True

        except Exception as e:
            self.logger.error(f"Error logging out from repeater: {e}")
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
                    self.meshcore.commands.get_msg(), timeout=3.0
                )

                if result.type == EventType.NO_MORE_MSGS:
                    self.logger.info(
                        f"Retrieved {message_count} queued messages from room"
                    )
                    break
                elif result.type == EventType.CONTACT_MSG_RECV:
                    # Got a message - store it
                    msg_data = result.payload
                    self.messages.append(
                        {
                            "type": "contact",
                            "sender": msg_data.get("pubkey_prefix", "Unknown"),
                            "text": msg_data.get("text", ""),
                            "timestamp": msg_data.get("timestamp", 0),
                            "channel": None,
                        }
                    )
                    message_count += 1
                    self.logger.debug(
                        f"Received room message {message_count}: {msg_data.get('text', '')[:50]}"
                    )
                elif result.type == EventType.ERROR:
                    self.logger.error(f"Error fetching room message: {result.payload}")
                    break
                else:
                    # Got some other event, skip it
                    self.logger.debug(
                        f"Got unexpected event while fetching room messages: {result.type}"
                    )

        except asyncio.TimeoutError:
            self.logger.info(
                f"Timeout fetching room messages after {message_count} messages"
            )
        except Exception as e:
            self.logger.error(f"Error fetching room messages: {e}")
            import traceback

            self.logger.debug(f"Traceback: {traceback.format_exc()}")

    # NOTE: Removed duplicate send_channel_message() - now using the one at end of file
    # which routes through ChannelManager for consistency

    async def get_messages(self) -> List[Dict[str, Any]]:
        """Get all messages (both received via events and polled)."""
        if not self.meshcore:
            return []

        try:
            messages = []

            # Get messages from event storage first
            if hasattr(self, "received_messages"):
                messages.extend(self.received_messages)
                self.logger.debug(
                    f"Found {len(self.received_messages)} messages from events"
                )

            # Poll for additional messages that might not have triggered events
            max_poll_messages = 50
            message_count = 0

            try:
                while message_count < max_poll_messages:
                    msg_result = await asyncio.wait_for(
                        self.meshcore.commands.get_msg(), timeout=1.0
                    )
                    if (
                        msg_result.type == EventType.ERROR
                        or msg_result.type == EventType.NO_MORE_MSGS
                    ):
                        break

                    # Add timestamp and type info
                    message_data = {
                        "type": "polled",
                        "timestamp": self.meshcore.time,
                        **msg_result.payload,
                    }
                    messages.append(message_data)
                    self.logger.debug(f"Polled message: {msg_result.payload}")
                    message_count += 1

            except asyncio.TimeoutError:
                self.logger.debug("Finished polling messages (timeout)")
            except Exception as e:
                self.logger.debug(f"Finished polling messages: {e}")

            # Sort messages by timestamp if available
            messages.sort(key=lambda x: x.get("timestamp", 0))

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

    def set_contacts_callback(self, callback):
        """Set callback for contacts list updates.

        Args:
            callback: Function to call when contacts list changes.
                     Signature: callback()
        """
        self._contacts_callback = callback

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
                old_meshcore = self.meshcore
                self.meshcore = None

                # Give a moment for any pending events to complete
                await asyncio.sleep(0.2)

                # Now delete the instance (may produce EventDispatcher warnings from meshcore)
                del old_meshcore

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
        """Get current contacts list.

        Contacts returned from MeshCore are fresh by definition -
        if the device has them, they're active.
        """
        if not self.contacts:
            return []

        now = int(time.time())

        contacts = self.contacts.get_all()

        # Mark all contacts as fresh since MeshCore has them
        for contact in contacts:
            contact["last_seen"] = now

        return contacts

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
        if not self.db:
            return []
        return self.db.get_messages_for_contact(contact_name, limit=1000)

    def get_messages_for_channel(self, channel_name: str) -> List[Dict[str, Any]]:
        """Get messages for a specific channel from database.

        Args:
            channel_name: "Public" or channel name

        Returns:
            List of message dictionaries
        """
        if not self.db:
            return []

        # Determine channel index
        if channel_name == "Public":
            channel_idx = 0
        else:
            # Try to extract channel index from name like "Channel 1"
            try:
                channel_idx = int(channel_name.split()[-1])
            except (ValueError, IndexError):
                channel_idx = 0

        return self.db.get_messages_for_channel(channel_idx, limit=1000)

    def mark_as_read(self, contact_or_channel: str):
        """Mark all messages from a contact/channel as read.

        Args:
            contact_or_channel: Name of contact, room, or channel
        """
        if not self.db:
            return

        self.db.mark_as_read(contact_or_channel, int(time.time()))
        self.logger.debug(f"Marked {contact_or_channel} as read")

    def get_unread_count(self, contact_or_channel: str) -> int:
        """Get the number of unread messages for a contact/channel.

        Args:
            contact_or_channel: Name of contact, room, or channel

        Returns:
            Number of unread messages
        """
        if not self.db:
            return 0
        return self.db.get_unread_count(contact_or_channel)

    def get_all_unread_counts(self) -> Dict[str, int]:
        """Get unread counts for all contacts/channels.

        Returns:
            Dictionary mapping contact/channel names to unread counts
        """
        if not self.db:
            return {}
        return self.db.get_all_unread_counts()

    def _load_recent_messages(self):
        """Load recent messages from database into memory cache."""
        if not self.db:
            self.logger.warning("Database not initialized, skipping message load")
            return

        try:
            # Load recent conversations to initialize unread counts
            conversations = self.db.get_recent_conversations(limit=50)
            self.logger.info(
                f"Loaded {len(conversations)} recent conversations from database"
            )
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
            return bool(
                self.connected
                and self.meshcore
                and getattr(self.meshcore, "is_connected", False)
            )
        except Exception:
            return bool(self.connected)

    def has_gps(self) -> bool:
        """Check if the connected device has GPS available.

        Detects GPS by checking if location telemetry mode is enabled.
        Note: Coordinates alone are not reliable since they can be set manually
        via set_coords() even without GPS hardware.

        Returns:
            True if device appears to have GPS hardware, False otherwise
        """
        if not self.meshcore or not hasattr(self.meshcore, "self_info"):
            return False

        self_info = self.meshcore.self_info
        if not self_info:
            return False

        # Check if location telemetry mode is enabled (indicates GPS capability)
        # telemetry_mode_loc values:
        # 0 = Disabled (no GPS or GPS not active)
        # 1 = Enabled (GPS hardware present and active)
        # 2+ = Other modes
        telemetry_mode_loc = self_info.get("telemetry_mode_loc", 0)

        # Also get coordinates for logging purposes
        lat = self_info.get("adv_lat", 0)
        lon = self_info.get("adv_lon", 0)

        # Debug logging to see actual values
        self.logger.debug(
            f"GPS detection: telemetry_mode_loc={telemetry_mode_loc}, "
            f"lat={lat}, lon={lon}"
        )

        if telemetry_mode_loc > 0:
            self.logger.debug("GPS detected: location telemetry mode is enabled")
            return True
        else:
            self.logger.debug(
                "No GPS detected: location telemetry mode is disabled "
                "(coordinates may be manually set)"
            )
            return False

    async def auto_sync_time_if_needed(self) -> None:
        """Automatically sync device time if GPS is not available.

        GPS-enabled devices typically have accurate time from satellites.
        Devices without GPS may have incorrect time and benefit from sync.
        """
        if not self.is_connected():
            self.logger.debug("Not connected, skipping auto time sync")
            return

        try:
            if self.has_gps():
                self.logger.info(
                    "Device has GPS - skipping auto time sync (GPS provides accurate time)"
                )
                return

            self.logger.info(
                "Device has no GPS - performing automatic time sync..."
            )
            current_time = int(time.time())
            result = await asyncio.wait_for(
                self.meshcore.commands.set_time(current_time), timeout=5.0
            )

            if hasattr(result, "type") and result.type == EventType.OK:
                self.logger.info(
                    f"✓ Auto time sync successful - set device time to {current_time}"
                )
            else:
                self.logger.warning(
                    f"Auto time sync failed or returned unexpected result: {result}"
                )

        except asyncio.TimeoutError:
            self.logger.warning("Auto time sync timed out")
        except Exception as e:
            self.logger.error(f"Error during auto time sync: {e}")

    def is_room_admin(self, room_name: str) -> bool:
        """Check if we have admin privileges in a room.

        Args:
            room_name: Name of the room server

        Returns:
            True if we're logged in as admin, False otherwise
        """
        if not self.rooms:
            return False
        return self.rooms.is_admin(room_name)

    async def login_to_node(self, node_name: str, password: str) -> bool:
        """Log into a node (repeater or room server).

        This is a convenience method that routes to the appropriate handler
        based on node type. It's a thin orchestration layer.

        Args:
            node_name: Name of the node (repeater or room server)
            password: Authentication password

        Returns:
            True if login successful, False otherwise

        Note:
            - Type 3 (room server) -> delegates to login_to_room()
            - Type 2 (repeater) -> delegates to _login_to_repeater()
        """
        if not self.meshcore or not self.contacts:
            return False

        try:
            # Look up the contact
            contact = self.contacts.get_by_name(node_name)
            if not contact:
                self.logger.error(f"Node '{node_name}' not found")
                return False

            node_type = contact.get("type", 0)

            # Route to appropriate handler based on type
            if node_type == 3:
                # Room server - use dedicated method
                return await self.login_to_room(node_name, password)
            elif node_type == 2:
                # Repeater - use helper method
                return await self._login_to_repeater(contact, password)
            else:
                self.logger.error(
                    f"Node '{node_name}' is not a repeater or room server (type={node_type})"
                )
                return False

        except Exception as e:
            self.logger.error(f"Error logging into node '{node_name}': {e}")
            return False

    async def logout_from_node(self, node_name: str) -> bool:
        """Log out from a node (repeater or room server).

        This is a convenience method that routes to the appropriate handler
        based on node type. It's a thin orchestration layer.

        Args:
            node_name: Name of the node (repeater or room server)

        Returns:
            True if logout successful, False otherwise

        Note:
            - Type 3 (room server) -> delegates to logout_from_room()
            - Type 2 (repeater) -> delegates to _logout_from_repeater()
        """
        if not self.meshcore or not self.contacts:
            return False

        try:
            # Look up the contact
            contact = self.contacts.get_by_name(node_name)
            if not contact:
                self.logger.error(f"Node '{node_name}' not found")
                return False

            node_type = contact.get("type", 0)

            # Route to appropriate handler based on type
            if node_type == 3:
                # Room server - use dedicated method
                return await self.logout_from_room(node_name)
            elif node_type == 2:
                # Repeater - use helper method
                return await self._logout_from_repeater(contact)
            else:
                self.logger.error(
                    f"Node '{node_name}' is not a repeater or room server (type={node_type})"
                )
                return False

        except Exception as e:
            self.logger.error(f"Error logging out from node '{node_name}': {e}")
            return False

    async def send_command_to_node(self, node_name: str, command: str) -> bool:
        """Send a command to a node (repeater, room server, or sensor).

        Uses the correct MeshCore API: send_cmd(contact, command_text)
        Works for type 2 (repeater), 3 (room server), and 4 (sensor) nodes.

        For room servers: You must be logged in with admin password first.
        The login happens in the Chat tab, and admin status is tracked by RoomManager.
        """
        if not self.meshcore or not self.contacts:
            return False

        try:
            # Get contact
            contact = self.contacts.get_by_name(node_name)
            if not contact:
                self.logger.error(f"Node '{node_name}' not found")
                return False

            node_type = contact.get("type", 0)
            if node_type not in [2, 3, 4]:  # repeater, room, or sensor
                self.logger.error(
                    f"Node '{node_name}' does not support commands (type={node_type})"
                )
                return False

            # For room servers, check if we're logged in and have admin rights
            if node_type == 3:  # Room server
                if not self.rooms or not self.rooms.is_logged_in(node_name):
                    self.logger.error(
                        f"Not logged into room '{node_name}'. Login via Chat tab first."
                    )
                    return False
                is_admin = self.rooms.is_admin(node_name)
                self.logger.debug(
                    f"🔍 Admin check for '{node_name}': is_admin={is_admin}, room_admin_status={self.rooms.room_admin_status}"
                )
                if not is_admin:
                    self.logger.warning(
                        f"Not admin in room '{node_name}'. Admin commands may be rejected."
                    )
                    # Don't return False - let the command through, server will reject if needed

            # Use send_cmd API (correct API from meshcore-cli)
            result = await self.meshcore.commands.send_cmd(contact, command)
            if result.type == EventType.ERROR:
                self.logger.error(f"Failed to send command to {node_name}: {result}")
                return False

            self.logger.info(f"Command sent to {node_name}: {command}")
            return True

        except Exception as e:
            self.logger.error(f"Error sending command to {node_name}: {e}")
            return False

    async def request_node_status(self, node_name: str) -> Optional[Dict[str, Any]]:
        """Request status from a node (repeater, room server, or sensor).

        Works for type 2 (repeater), 3 (room server), and 4 (sensor) nodes.
        """
        if not self.meshcore or not self.contacts:
            return None

        try:
            # Get contact
            contact = self.contacts.get_by_name(node_name)
            if not contact:
                self.logger.error(f"Node '{node_name}' not found")
                return None

            node_type = contact.get("type", 0)
            if node_type not in [2, 3, 4]:
                self.logger.error(
                    f"Node '{node_name}' does not support status requests (type={node_type})"
                )
                return None

            result = await self.meshcore.commands.request_status(node_name)
            if result.type == EventType.ERROR:
                self.logger.error(f"Failed to get status from {node_name}: {result}")
                return None

            self.logger.info(f"Received status from {node_name}")
            return result.payload

        except Exception as e:
            self.logger.error(f"Error requesting status from {node_name}: {e}")
            return None

    async def ping_contact(self, contact_name: str) -> Dict[str, Any]:
        """Ping a contact to test connectivity.

        Sends a status request (not a message) and waits for acknowledgment.
        Uses send_statusreq which doesn't create a visible message.

        Args:
            contact_name: Name of the contact to ping

        Returns:
            Dict with ping result:
            - success: bool - whether contact responded with ACK
            - latency: float - round trip time in seconds (if successful)
            - error: str - error message (if failed)
        """

        if not self.meshcore or not self.contacts:
            return {"success": False, "error": "Not connected"}

        try:
            # Get contact
            contact = self.contacts.get_by_name(contact_name)
            if not contact:
                return {
                    "success": False,
                    "error": f"Contact '{contact_name}' not found",
                }

            pubkey = contact.get("public_key")
            if not pubkey:
                return {"success": False, "error": "Contact has no public key"}

            self.logger.info(f"Pinging {contact_name} ({pubkey[:16]}...)")

            # Send a status request (doesn't create a visible message)
            start_time = time.time()

            # Use send_statusreq instead of send_msg - this doesn't send a message
            result = await self.meshcore.commands.send_statusreq(pubkey)

            if result.type == EventType.ERROR:
                return {
                    "success": False,
                    "error": f"Failed to send ping: {result.payload if hasattr(result, 'payload') else 'unknown error'}",
                }

            # Get the expected ACK code
            expected_ack = result.payload.get("expected_ack", b"").hex()
            suggested_timeout = result.payload.get("suggested_timeout", 5000) / 1000.0

            self.logger.debug(
                f"Waiting for ACK {expected_ack}, suggested timeout: {suggested_timeout}s"
            )

            # Wait for the ACK event
            try:
                await asyncio.wait_for(
                    self.meshcore.dispatcher.wait_for_event(
                        EventType.ACK, attribute_filters={"code": expected_ack}
                    ),
                    timeout=min(
                        suggested_timeout * 1.5, 15.0
                    ),  # Use suggested timeout with margin
                )

                latency = time.time() - start_time
                self.logger.info(
                    f"✓ Ping successful to {contact_name}: {latency*1000:.0f}ms"
                )

                return {"success": True, "latency": latency}

            except asyncio.TimeoutError:
                latency = time.time() - start_time
                self.logger.warning(
                    f"✗ Ping timeout to {contact_name} after {latency:.1f}s (no ACK received)"
                )
                return {
                    "success": False,
                    "error": f"Timeout after {latency:.1f}s - no ACK received (contact may be out of range or offline)",
                }

        except Exception as e:
            self.logger.error(f"Error pinging {contact_name}: {e}")
            import traceback

            self.logger.debug(f"Traceback: {traceback.format_exc()}")
            return {"success": False, "error": str(e)}

    async def trace_path_to_contact(self, contact_name: str) -> Dict[str, Any]:
        """Trace the routing path to a contact.

        First checks if path is already known from contact data,
        otherwise sends path discovery request.

        Args:
            contact_name: Name of the contact to trace

        Returns:
            Dict with trace result:
            - success: bool - whether path was discovered
            - path: List[str] - list of repeater names in the path
            - latency: float - round trip time in seconds (if successful)
            - cached: bool - whether this is from cached contact data
            - error: str - error message (if failed)
        """

        if not self.meshcore or not self.contacts:
            return {"success": False, "error": "Not connected"}

        try:
            # Get contact
            contact = self.contacts.get_by_name(contact_name)
            if not contact:
                return {
                    "success": False,
                    "error": f"Contact '{contact_name}' not found",
                }

            pubkey = contact.get("public_key")
            if not pubkey:
                return {"success": False, "error": "Contact has no public key"}

            self.logger.info(f"Tracing path to {contact_name} ({pubkey[:16]}...)")

            # Check if we already have path information in the contact
            out_path_len = contact.get("out_path_len", 0)
            out_path = contact.get("out_path", "")

            # Use match/case for cleaner path type handling (Python 3.10+)
            match out_path_len:
                case -1:
                    # Flood routing (no specific path)
                    self.logger.debug("Contact uses flood routing (no fixed path)")
                    return {
                        "success": True,
                        "path": [],
                        "cached": True,
                    }
                case 0:
                    # Direct connection (no repeaters)
                    self.logger.debug("Direct connection (no repeaters)")
                    return {
                        "success": True,
                        "path": [],
                        "cached": True,
                    }
                case _ if out_path_len > 0 and out_path:
                    # We have cached path information
                    self.logger.debug(f"Using cached path: len={out_path_len}, path={out_path}")

                    # Parse the path hex string into repeater hashes
                    path_names = []
                    # Each hop is 1 byte (2 hex chars)
                    for i in range(0, len(out_path), 2):
                        if i >= out_path_len * 2:
                            break
                        hop_hash = out_path[i:i+2]
                        # Try to find contact with this hash prefix
                        hop_contact = self.contacts.get_by_key(hop_hash)
                        if hop_contact:
                            path_names.append(hop_contact.get("name", f"#{hop_hash}"))
                        else:
                            path_names.append(f"#{hop_hash}")

                    return {
                        "success": True,
                        "path": path_names,
                        "cached": True,
                    }
                case _:
                    # Unknown path - need to discover
                    self.logger.debug("No cached path available, initiating discovery")

            # Send path discovery request
            start_time = time.time()

            self.logger.debug(f"Sending path discovery request to {pubkey[:16]}...")
            result = await self.meshcore.commands.send_path_discovery(pubkey)

            self.logger.debug(f"Path discovery result: {result.type}, payload: {result.payload if hasattr(result, 'payload') else 'N/A'}")

            if result.type == EventType.ERROR:
                error_msg = result.payload if hasattr(result, 'payload') else 'unknown error'
                self.logger.error(f"Failed to send path discovery: {error_msg}")
                return {
                    "success": False,
                    "error": f"Failed to send path discovery: {error_msg}",
                }

            # Wait for PATH_RESPONSE event
            self.logger.debug("Waiting for PATH_RESPONSE event...")
            try:
                path_response = await self.meshcore.dispatcher.wait_for_event(
                    EventType.PATH_RESPONSE,
                    timeout=10.0
                )

                self.logger.debug(f"Received PATH_RESPONSE: {path_response}")
                latency = time.time() - start_time

                if path_response and path_response.payload:
                    # Extract path from response
                    path_data = path_response.payload.get("path", [])

                    # Convert path to readable format (contact names if available)
                    path_names = []
                    for hop_pubkey in path_data:
                        # Look up contact by pubkey
                        hop_contact = self.contacts.get_by_key(hop_pubkey)
                        if hop_contact:
                            path_names.append(hop_contact.get("name", hop_pubkey[:12]))
                        else:
                            path_names.append(hop_pubkey[:12] + "...")

                    self.logger.info(f"✓ Path to {contact_name}: {' → '.join(path_names)} ({latency:.2f}s)")
                    return {
                        "success": True,
                        "path": path_names,
                        "latency": latency,
                    }
                else:
                    return {
                        "success": False,
                        "error": "No path response received",
                    }

            except asyncio.TimeoutError:
                latency = time.time() - start_time
                self.logger.warning(
                    f"✗ Path discovery timeout to {contact_name} after {latency:.1f}s"
                )
                return {
                    "success": False,
                    "error": f"Timeout after {latency:.1f}s - path discovery failed",
                }

        except Exception as e:
            self.logger.error(f"Error tracing path to {contact_name}: {e}")
            import traceback
            self.logger.debug(f"Traceback: {traceback.format_exc()}")
            return {"success": False, "error": str(e)}

    # Deprecated methods - kept for backward compatibility
    async def login_to_repeater(self, repeater_name: str, password: str) -> bool:
        """Deprecated: Use login_to_node() instead."""
        return await self.login_to_node(repeater_name, password)

    async def logout_from_repeater(self, repeater_name: str) -> bool:
        """Deprecated: Use logout_from_node() instead."""
        return await self.logout_from_node(repeater_name)

    async def send_command_to_repeater(self, repeater_name: str, command: str) -> bool:
        """Deprecated: Use send_command_to_node() instead."""
        return await self.send_command_to_node(repeater_name, command)

    async def request_repeater_status(
        self, repeater_name: str
    ) -> Optional[Dict[str, Any]]:
        """Deprecated: Use request_node_status() instead."""
        return await self.request_node_status(repeater_name)

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

    async def remove_contact(self, contact_name: str) -> bool:
        """Remove a contact from the device.

        Args:
            contact_name: Name of the contact to remove

        Returns:
            True if successful, False otherwise
        """
        if not self.meshcore or not self.contacts:
            self.logger.error("Cannot remove contact - not connected")
            return False

        try:
            # Get contact to find pubkey
            contact = self.contacts.get_by_name(contact_name)
            if not contact:
                self.logger.error(f"Contact '{contact_name}' not found")
                return False

            pubkey = (
                contact.get("public_key") or contact.get("pubkey") or contact.get("id")
            )
            if not pubkey:
                self.logger.error(f"Contact '{contact_name}' has no public key")
                return False

            self.logger.info(f"Removing contact '{contact_name}' ({pubkey[:12]}...)")

            # Remove from device
            result = await self.meshcore.commands.remove_contact(pubkey)

            if result.type == EventType.OK:
                self.logger.info(f"✓ Contact '{contact_name}' removed from device")

                # Remove from database if present
                if self.db:
                    self.db.delete_contact(pubkey)
                    self.logger.debug(f"Removed '{contact_name}' from database")

                # Refresh contacts to update UI
                await self.refresh_contacts()

                return True
            else:
                self.logger.error(f"✗ Failed to remove contact: {result}")
                return False

        except Exception as e:
            self.logger.error(f"Error removing contact: {e}")
            import traceback

            self.logger.debug(traceback.format_exc())
            return False

    async def get_channels(self) -> List[Dict[str, Any]]:
        """Get list of available channels.

        Routes through ChannelManager for consistency.
        """
        if not self.channels:
            return []

        return await self.channels.get_channels()

    async def join_channel(self, channel_name: str, key: str = "") -> bool:
        """Join a channel by name and optional key.

        Routes through ChannelManager for consistency.
        """
        if not self.channels:
            return False

        return await self.channels.join_channel(channel_name, key)

    async def create_channel(
        self,
        channel_idx: int,
        channel_name: str,
        channel_secret: Optional[bytes] = None,
    ) -> bool:
        """Create or update a channel.

        Args:
            channel_idx: Channel slot (1-7, 0 is reserved for Public)
            channel_name: Name of the channel (use # prefix for auto-hash secret)
            channel_secret: Optional 16-byte secret (auto-generated if name starts with #)

        Returns:
            True if successful
        """
        if not self.meshcore:
            return False

        try:
            self.logger.info(f"Creating channel {channel_idx}: {channel_name}")
            result = await self.meshcore.commands.set_channel(
                channel_idx, channel_name, channel_secret
            )

            if result.type == EventType.ERROR:
                self.logger.error(f"Failed to create channel: {result}")
                return False

            self.logger.info(f"Channel {channel_idx} created successfully")
            # Refresh channels list
            if self.channels:
                await self.channels.refresh()
            return True

        except Exception as e:
            self.logger.error(f"Error creating channel: {e}")
            return False

    async def send_channel_message(self, channel_id: int, message: str) -> bool:
        """Send a message to a specific channel.

        Routes through ChannelManager for consistency, then stores in database.
        """
        if not self.meshcore or not self.channels:
            return False

        try:
            import time

            # Use ChannelManager to send the message
            status_info = await self.channels.send_message(channel_id, message)

            if not status_info:
                self.logger.error(
                    f"ChannelManager returned False for channel {channel_id}"
                )
                return False

            self.logger.info(
                f"Channel message sent successfully, result type: {type(status_info)}"
            )
            self.logger.debug(f"Channel status_info: {status_info}")

            # Note: Channel messages don't support ACK tracking (they're broadcasts)
            # Only show "Sent" status, no repeat tracking

            # Show "Sent" notification
            if self._message_callback:
                self._message_callback("System", "✓ Sent (broadcast)", "status")

            # Store sent channel message in database (no ACK code for broadcasts)
            sent_msg = {
                "type": "channel",
                "sender": "Me",
                "sender_pubkey": "",
                "text": message,
                "timestamp": int(time.time()),
                "channel": channel_id,
                "sent": True,
                "ack_code": None,
                "delivery_status": "broadcast",
                "repeat_count": 0,
            }
            self.messages.append(sent_msg)
            if self.db:
                self.db.store_message(sent_msg)
                # Mark channel as read so our own sent message doesn't show as unread
                channel_name = f"Channel {channel_id}" if channel_id != 0 else "Public"
                self.db.mark_as_read(channel_name)

            self.logger.info(
                f"Sent and stored message to channel {channel_id}: {message}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Error sending channel message: {e}")
            return False

    def clear_received_messages(self):
        """Clear the received messages buffer."""
        if hasattr(self, "received_messages"):
            self.received_messages.clear()
            self.logger.debug("Cleared received messages buffer")
