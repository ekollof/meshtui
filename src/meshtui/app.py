#!/usr/bin/env python3
"""
meshtui - Textual TUI interface to meshcore companion radios
"""

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    ListView,
    ListItem,
    Log,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)
from textual.binding import Binding

from .connection import MeshConnection


def sanitize_id(name: str) -> str:
    """Convert a name to a valid HTML/CSS ID.
    
    Args:
        name: The name to sanitize
        
    Returns:
        Valid ID string with only letters, numbers, underscores, and hyphens
    """
    # Replace spaces and invalid characters with underscores
    import re
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    # Ensure it doesn't start with a number
    if sanitized and sanitized[0].isdigit():
        sanitized = f"_{sanitized}"
    return sanitized


class TextualLogHandler(logging.Handler):
    """Custom logging handler that writes to a Textual Log widget."""

    def __init__(self, app):
        super().__init__()
        self.app = app

    def emit(self, record):
        """Emit a log record to the Textual log panel."""
        try:
            msg = self.format(record)
            # Write directly, assuming logging happens in main thread
            if hasattr(self.app, "log_panel") and self.app.log_panel:
                self._write_to_log(msg)
            else:
                # Fallback: print to stdout if log panel not available
                print(f"LOG: {msg}")
        except Exception as e:
            print(f"Logging error: {e}")
            self.handleError(record)

    def _write_to_log(self, message):
        """Write message to the log panel."""
        try:
            if hasattr(self.app, "log_panel") and self.app.log_panel:
                self.app.log_panel.write(message + "\n")
            else:
                print(f"LOG FALLBACK: {message}")
        except Exception as e:
            print(f"Log write error: {e}")


class MeshTUI(App):
    """Main Textual application for meshcore TUI client."""

    TITLE = "MeshTUI"
    SUB_TITLE = "MeshCore Companion Radio TUI"
    CSS_PATH = "app.css"

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+r", "refresh", "Refresh"),
        Binding("f1", "help", "Help"),
    ]

    def __init__(self, args):
        super().__init__()
        self.args = args
        self.connection = MeshConnection()
        self.current_contact = None
        self.current_channel = None
        self._awaiting_room_password = False  # Flag for room password input
        self._contact_id_map = {}  # Map sanitized IDs back to contact names
        self._channel_id_map = {}  # Map sanitized IDs back to channel names
        self.messages = []

        # Setup logging (will be configured in on_mount)
        self.logger = logging.getLogger("meshtui")
        self.logger.setLevel(logging.DEBUG)  # Enable debug logging

    def compose(self) -> ComposeResult:
        """Compose the UI layout."""
        yield Header()

        with Horizontal():
            # Left sidebar - Contacts and Channels
            with Vertical(id="sidebar"):
                yield Static("Contacts", id="contacts-header")
                yield ListView(id="contacts-list")
                
                yield Static("Channels", id="channels-header")
                yield ListView(id="channels-list")
                
                yield Button("Send Advert (0-hop)", id="advert-0hop-btn", variant="primary")
                yield Button("Send Advert (Flood)", id="advert-flood-btn", variant="default")

            # Main content area with tabs
            with Vertical(id="main-content"):
                with TabbedContent():
                    with TabPane("Chat", id="chat-tab"):
                        with Vertical(id="chat-container"):
                            # Chat area - using RichLog to support markup
                            yield RichLog(id="chat-area", highlight=True, markup=True)

                            # Input area
                            with Horizontal(id="input-container"):
                                yield Input(
                                    placeholder="Type message or command...",
                                    id="message-input",
                                )
                                yield Button("Send", id="send-btn", variant="primary")

                    with TabPane("Node Management", id="node-tab"):
                        # Node management area
                        with Horizontal():
                            # Left: Node list
                            with Vertical(id="node-list-container"):
                                yield Static("Available Nodes", id="nodes-header")
                                yield ListView(id="nodes-list")
                                yield Button(
                                    "Refresh Nodes",
                                    id="refresh-nodes-btn",
                                    variant="primary",
                                )

                            # Right: Node control panel
                            with Vertical(id="node-control-container"):
                                yield Static("Node Control", id="node-control-header")

                                # Login section
                                with Horizontal():
                                    yield Input(
                                        placeholder="Node name", id="node-name-input"
                                    )
                                    yield Input(
                                        placeholder="Password", id="node-password-input"
                                    )
                                    yield Button(
                                        "Login", id="node-login-btn", variant="primary"
                                    )

                                # Command section
                                with Horizontal():
                                    yield Input(
                                        placeholder="Command", id="node-command-input"
                                    )
                                    yield Button(
                                        "Send Command",
                                        id="node-send-cmd-btn",
                                        variant="primary",
                                    )

                                # Status section
                                yield Button(
                                    "Get Status",
                                    id="node-status-btn",
                                    variant="primary",
                                )
                                yield TextArea(
                                    "", id="node-status-area", read_only=True
                                )

            # Right sidebar - Logs
            with Vertical(id="log-sidebar"):
                yield Static("Logs", id="logs-header")
                yield Log(id="log-panel", auto_scroll=True)

        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        # Setup UI references first
        self.contacts_list = self.query_one("#contacts-list", ListView)
        self.channels_list = self.query_one("#channels-list", ListView)
        self.chat_area = self.query_one("#chat-area", RichLog)
        self.message_input = self.query_one("#message-input", Input)
        self.log_panel = self.query_one("#log-panel", Log)

        # Node management UI references
        self.nodes_list = self.query_one("#nodes-list", ListView)
        self.node_name_input = self.query_one("#node-name-input", Input)
        self.node_password_input = self.query_one("#node-password-input", Input)
        self.node_command_input = self.query_one("#node-command-input", Input)
        self.node_status_area = self.query_one("#node-status-area", TextArea)

        # Setup logging handler now that we have the log panel
        self.log_handler = TextualLogHandler(self)
        self.log_handler.setLevel(logging.INFO)  # TUI shows INFO+ only
        self.log_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )

        # Add handler to root logger to capture all logging
        root_logger = logging.getLogger()
        root_logger.addHandler(self.log_handler)

        self.logger.info("MeshTUI started - logging to ~/.config/meshtui/meshtui.log")
        
        # Register message callback for notifications
        self.connection.set_message_callback(self._on_new_message)

        # Try to auto-connect if possible (schedule after mount)
        self.call_later(lambda: asyncio.create_task(self.auto_connect()))
        
        # Start periodic message refresh (every 2 seconds)
        self.set_interval(2.0, self.periodic_message_refresh)

    def _on_new_message(self, sender: str, text: str, msg_type: str, channel_name: Optional[str] = None):
        """Callback when a new message arrives."""
        # Check if this message is for the current view
        is_current_view = False
        
        if (msg_type == 'contact' or msg_type == 'room') and self.current_contact == sender:
            is_current_view = True
        elif msg_type == 'channel' and channel_name:
            is_current_view = (self.current_channel == channel_name or 
                             (channel_name == "Public" and self.current_channel == "Public"))
        
        if is_current_view:
            # Message is for current view - refresh immediately and mark as read
            self.logger.debug(f"New message in current view from {sender}")
            self.connection.mark_as_read(sender)
            asyncio.create_task(self.refresh_messages())
        else:
            # Message is from another contact/channel - show notification and update list
            source = channel_name if msg_type == 'channel' else sender
            preview = text[:50] + "..." if len(text) > 50 else text
            self.logger.info(f"💬 New message from {source}: {preview}")
            self.notify(f"New message from {source}", title="Message Received", severity="information")
            # Update contact list to show new unread count
            asyncio.create_task(self.update_contacts())

    async def auto_connect(self) -> None:
        """Attempt to auto-connect to a meshcore device."""
        import asyncio

        try:
            self.logger.info("Attempting auto-connect...")
            self.logger.debug(f"Args: serial={self.args.serial}, tcp={self.args.tcp}, address={self.args.address}, baudrate={self.args.baudrate}")

            # Check command line arguments for specific connection type
            if self.args.serial:
                self.logger.info(
                    f"Connecting to specified serial device: {self.args.serial}"
                )
                try:
                    success = await asyncio.wait_for(
                        self.connection.connect_serial(
                            port=self.args.serial, baudrate=self.args.baudrate
                        ),
                        timeout=10.0,
                    )
                except asyncio.TimeoutError:
                    self.logger.error("Timeout connecting to specified serial device")
                    success = False
                if success:
                    self.logger.info("Connected via serial successfully")
                    self.logger.debug("About to update contacts in UI...")
                    await asyncio.wait_for(self.update_contacts(), timeout=5.0)
                    self.logger.debug("About to update channels in UI...")
                    await asyncio.wait_for(self.update_channels(), timeout=5.0)
                    self.logger.debug("About to refresh messages...")
                    await asyncio.wait_for(self.refresh_messages(), timeout=5.0)
                else:
                    self.logger.error(f"Failed to connect to specified serial device: {self.args.serial}")
                return  # Don't try auto-detection when serial is explicitly specified
                    
            elif self.args.tcp:
                self.logger.info(
                    f"Connecting to TCP device: {self.args.tcp}:{self.args.port}"
                )
                try:
                    success = await asyncio.wait_for(
                        self.connection.connect_tcp(
                            hostname=self.args.tcp, port=self.args.port
                        ),
                        timeout=10.0,
                    )
                except asyncio.TimeoutError:
                    self.logger.error("Timeout connecting to TCP device")
                    success = False
                if success:
                    self.logger.info("Connected via TCP successfully")
                    await asyncio.wait_for(self.update_contacts(), timeout=5.0)
                    await asyncio.wait_for(self.update_channels(), timeout=5.0)
                    await asyncio.wait_for(self.refresh_messages(), timeout=5.0)
                else:
                    self.logger.error(f"Failed to connect to specified TCP device: {self.args.tcp}:{self.args.port}")
                return  # Don't try auto-detection when TCP is explicitly specified
                    
            elif self.args.address:
                self.logger.info(f"Connecting to BLE device: {self.args.address}")
                try:
                    success = await asyncio.wait_for(
                        self.connection.connect_ble(address=self.args.address),
                        timeout=15.0,
                    )
                except asyncio.TimeoutError:
                    self.logger.error("Timeout connecting to BLE device")
                    success = False
                if success:
                    self.logger.info("Connected via BLE successfully")
                    await asyncio.wait_for(self.update_contacts(), timeout=5.0)
                    await asyncio.wait_for(self.update_channels(), timeout=5.0)
                    await asyncio.wait_for(self.refresh_messages(), timeout=5.0)
                else:
                    self.logger.error(f"Failed to connect to specified BLE device: {self.args.address}")
                return  # Don't try auto-detection when BLE address is explicitly specified
                    
            # Fall back to auto-detection if no args provided
            self.logger.info("No connection args provided, attempting auto-detection...")
            
            # First try BLE connection
            try:
                success = await asyncio.wait_for(
                    self.connection.connect_ble(), timeout=15.0
                )
            except asyncio.TimeoutError:
                self.logger.error("Timeout auto-connecting via BLE")
                success = False
            if success:
                self.logger.info("Auto-connected via BLE successfully")
                await asyncio.wait_for(self.update_contacts(), timeout=5.0)
                await asyncio.wait_for(self.update_channels(), timeout=5.0)
                await asyncio.wait_for(self.refresh_messages(), timeout=5.0)
                return

            # If BLE fails, try serial devices
            self.logger.info("BLE auto-connect failed, trying serial devices...")
            try:
                serial_devices = await asyncio.wait_for(
                    self.connection.scan_serial_devices(), timeout=5.0
                )
            except asyncio.TimeoutError:
                self.logger.error("Timeout scanning serial devices")
                serial_devices = []
            if serial_devices:
                # Prioritize /dev/ttyUSB0 if available
                usb_device = next(
                    (d for d in serial_devices if d["device"] == "/dev/ttyUSB0"), None
                )
                device_to_try = (
                    usb_device["device"] if usb_device else serial_devices[0]["device"]
                )
                self.logger.info(f"Attempting to connect to: {device_to_try}")

                try:
                    success = await asyncio.wait_for(
                        self.connection.connect_serial(port=device_to_try), timeout=10.0
                    )
                except asyncio.TimeoutError:
                    self.logger.error(
                        f"Timeout connecting to serial device {device_to_try}"
                    )
                    success = False
                if success:
                    self.logger.info("Auto-connected via serial successfully")
                    self.logger.debug("About to update contacts in UI...")
                    await asyncio.wait_for(self.update_contacts(), timeout=5.0)
                    self.logger.debug("About to refresh messages...")
                    await asyncio.wait_for(self.refresh_messages(), timeout=5.0)
                    return

            self.logger.info("Auto-connect failed - no compatible devices found")
        except Exception as e:
            self.logger.error(f"Auto-connect failed: {e}")

    @on(Button.Pressed, "#advert-0hop-btn")
    async def send_zero_hop_advert(self) -> None:
        """Send a zero-hop advertisement (only to direct neighbors)."""
        self.logger.info("Sending 0-hop advertisement...")
        try:
            if not self.connection.is_connected():
                self.logger.warning("Not connected to device")
                return
            
            success = await self.connection.send_advertisement(hops=0)
            if success:
                self.logger.info("✓ Sent 0-hop advertisement successfully")
            else:
                self.logger.error("✗ Failed to send 0-hop advertisement")
        except Exception as e:
            self.logger.error(f"Error sending 0-hop advertisement: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())

    @on(Button.Pressed, "#advert-flood-btn")
    async def send_flood_advert(self) -> None:
        """Send a flooding advertisement (max hops, reaches entire network)."""
        self.logger.info("Sending flood advertisement...")
        try:
            if not self.connection.is_connected():
                self.logger.warning("Not connected to device")
                return
            
            success = await self.connection.send_advertisement(hops=3)
            if success:
                self.logger.info("✓ Sent flood advertisement successfully (3 hops)")
            else:
                self.logger.error("✗ Failed to send flood advertisement")
        except Exception as e:
            self.logger.error(f"Error sending flood advertisement: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())

        if self.connection.is_connected():
            self.logger.info(
                "🧪 TEST: Connection is active, testing connection logging"
            )
            test_result = self.connection.test_logging()
            self.logger.info(f"🧪 TEST: Connection test result: {test_result}")
        else:
            self.logger.warning("🧪 TEST: No active connection")

        # Test UI updates
        self.logger.info("🧪 TEST: Testing UI updates")
        await self.update_contacts()
        await self.refresh_messages()

        # Test log panel directly
        if hasattr(self, "log_panel") and self.log_panel:
            self.log_panel.write(
                "🧪 DIRECT LOG PANEL TEST: This should appear in logs\n"
            )
            self.logger.info("🧪 TEST: Direct log panel write attempted")

        self.logger.info("🧪 TEST: Logging test completed")

    @on(Button.Pressed, "#send-btn")
    async def send_message(self) -> None:
        """Send a message or command."""
        message = self.message_input.value.strip()
        if not message:
            return

        if not self.connection.is_connected():
            self.chat_area.write("[red]Not connected to any device[/red]")
            return

        try:
            if self.current_contact:
                # Check if we're waiting for room password
                if self._awaiting_room_password:
                    # This is a password input for room login
                    self.chat_area.write(f"[dim]Logging in...[/dim]")
                    success = await self.connection.login_to_room(self.current_contact, message)
                    if success:
                        self.chat_area.write(f"[green]✓ Logged in successfully![/green]")
                        self.chat_area.write(f"[dim]Loading queued messages...[/dim]")
                        self._awaiting_room_password = False
                        self.message_input.value = ""
                        # Reload the contact messages (now includes room messages)
                        await self.load_contact_messages(self.current_contact)
                        self.chat_area.write(f"[dim]Ready to chat![/dim]")
                    else:
                        self.chat_area.write(f"[red]✗ Login failed. Try again.[/red]")
                    self.message_input.value = ""
                    return
                
                # Sending to a contact (direct message)
                from datetime import datetime
                timestamp = datetime.now().strftime("%H:%M:%S")
                
                # Show message as "sending" immediately
                self.chat_area.write(
                    f"[dim]{timestamp}[/dim] [blue]You → {self.current_contact}:[/blue] {message} [yellow](sending...)[/yellow]"
                )
                
                result = await self.connection.send_message(
                    self.current_contact, message
                )
                
                if result:
                    # Update status based on result
                    status = result.get('status', 'sent')
                    if status == 'delivered':
                        self.chat_area.write(f"[dim]{timestamp}[/dim] [green]✓ Delivered[/green]")
                    elif status == 'repeated':
                        self.chat_area.write(f"[dim]{timestamp}[/dim] [cyan]⟲ Repeated[/cyan]")
                    elif status == 'acked':
                        self.chat_area.write(f"[dim]{timestamp}[/dim] [green]✓ Acknowledged[/green]")
                    else:
                        self.chat_area.write(f"[dim]{timestamp}[/dim] [green]✓ Sent[/green]")
                    self.message_input.value = ""
                else:
                    self.chat_area.write(f"[dim]{timestamp}[/dim] [red]✗ Failed to send[/red]")
            elif self.current_channel:
                # Sending to a channel
                if self.current_channel == "Public":
                    # Public is channel 0
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    self.chat_area.write(
                        f"[dim]{timestamp}[/dim] [blue]You → Public:[/blue] {message} [yellow](sending...)[/yellow]"
                    )
                    success = await self.connection.send_channel_message(0, message)
                    if success:
                        self.chat_area.write(f"[dim]{timestamp}[/dim] [green]✓ Sent to public channel[/green]")
                        self.message_input.value = ""
                    else:
                        self.chat_area.write(f"[dim]{timestamp}[/dim] [red]✗ Failed to send[/red]")
                else:
                    success = await self.connection.send_channel_message(
                        self.current_channel, message
                    )
                    if success:
                        from datetime import datetime
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        self.chat_area.write(
                            f"[dim]{timestamp}[/dim] [blue]You → #{self.current_channel}:[/blue] {message}"
                        )
                        self.message_input.value = ""
                    else:
                        self.chat_area.write("[red]Failed to send channel message[/red]")
            else:
                self.chat_area.write("[yellow]No contact or channel selected. Click a contact or channel to start chatting.[/yellow]")
        except Exception as e:
            self.chat_area.write(f"[red]Error sending message: {e}[/red]")

    @on(Input.Submitted, "#message-input")
    async def on_message_submit(self) -> None:
        """Handle message input submission."""
        await self.send_message()

    @on(ListView.Selected, "#contacts-list")
    async def on_contact_selected(self, event: ListView.Selected) -> None:
        """Handle contact selection."""
        if event.item and event.item.id:
            # Look up the contact name from the ID mapping
            contact_name = self._contact_id_map.get(event.item.id)
            if not contact_name:
                self.logger.warning(f"No contact found for ID: {event.item.id}")
                return
            
            self.current_contact = contact_name
            self.current_channel = None  # Clear channel selection
            self.logger.info(f"Selected contact: {contact_name}")
            
            # Mark messages as read
            self.connection.mark_as_read(contact_name)
            
            # Check if this is a room server (type 3) and prompt for password if needed
            contact = self.connection.get_contact_by_name(contact_name)
            if contact and contact.get('type') == 3:
                # This is a room server - check if we're logged in
                if not self.connection.is_logged_into_room(contact_name):
                    self.chat_area.clear()
                    self.chat_area.write(f"[bold cyan]{contact_name} (Room Server)[/bold cyan]")
                    self.chat_area.write(f"[yellow]This is a room server. You need to login first.[/yellow]")
                    self.chat_area.write(f"[dim]Type password in the input field below and press Enter to login.[/dim]")
                    self.logger.info(f"{contact_name} is a room server, waiting for password")
                    # Set a flag to indicate we're waiting for password
                    self._awaiting_room_password = True
                    self.message_input.focus()
                    return
            
            # Regular contact or already logged in
            self._awaiting_room_password = False
            
            # Update chat area header
            self.chat_area.clear()
            if contact and contact.get('type') == 3:
                self.chat_area.write(f"[bold cyan]Chat with {contact_name} (Room Server)[/bold cyan]\n")
            elif contact and contact.get('type') == 2:
                self.chat_area.write(f"[bold cyan]Chat with {contact_name} (Repeater)[/bold cyan]\n")
            else:
                self.chat_area.write(f"[bold cyan]Chat with {contact_name}[/bold cyan]\n")
            
            # Load message history for this contact
            await self.load_contact_messages(contact_name)
            
            # Focus the message input
            self.message_input.focus()

    @on(ListView.Selected, "#channels-list")
    async def on_channel_selected(self, event: ListView.Selected) -> None:
        """Handle channel selection."""
        if event.item and event.item.id:
            # Look up the channel name from the ID mapping
            channel_name = self._channel_id_map.get(event.item.id)
            if not channel_name:
                self.logger.warning(f"No channel found for ID: {event.item.id}")
                return
            
            self.current_channel = channel_name
            self.current_contact = None  # Clear contact selection
            self.logger.info(f"Selected channel: {channel_name}")
            
            # Mark channel messages as read
            self.connection.mark_as_read(channel_name)
            
            # Update chat area header
            self.chat_area.clear()
            
            # Show last seen for contacts
            contact = self.connection.get_contact_by_name(channel_name)
            if contact:
                last_seen = contact.get("last_seen", 0)
                if last_seen > 0:
                    from datetime import datetime
                    import time
                    age_seconds = time.time() - last_seen
                    
                    if age_seconds < 60:
                        last_seen_str = "just now"
                    elif age_seconds < 3600:
                        last_seen_str = f"{int(age_seconds / 60)} min ago"
                    elif age_seconds < 86400:
                        last_seen_str = f"{int(age_seconds / 3600)} hr ago"
                    else:
                        last_seen_str = f"{int(age_seconds / 86400)} days ago"
                    
                    self.chat_area.write(f"[bold cyan]{channel_name}[/bold cyan] [dim](last seen: {last_seen_str})[/dim]\n")
                else:
                    self.chat_area.write(f"[bold cyan]{channel_name}[/bold cyan]\n")
            elif channel_name == "Public":
                self.chat_area.write(f"[bold cyan]Public Channel (All Messages)[/bold cyan]\n")
            else:
                self.chat_area.write(f"[bold cyan]Channel: {channel_name}[/bold cyan]\n")
            
            # Load message history for this channel
            await self.load_channel_messages(channel_name)
            
            # Focus the message input
            self.message_input.focus()

    def action_refresh(self) -> None:
        """Refresh the current view."""
        self.logger.info("Refreshing...")

    def action_help(self) -> None:
        """Show help information."""
        self.logger.info("Showing help...")

    async def load_contact_messages(self, contact_name: str) -> None:
        """Load and display message history for a contact."""
        try:
            self.logger.debug(f"Loading messages for contact: {contact_name}")
            messages = self.connection.get_messages_for_contact(contact_name)
            self.logger.debug(f"Retrieved {len(messages)} messages for {contact_name}")
            if messages:
                from datetime import datetime
                for msg in messages:
                    timestamp = msg.get('timestamp', 0)
                    if timestamp and timestamp > 0:
                        try:
                            # Handle both ISO format and unix timestamp
                            if isinstance(timestamp, str):
                                dt = datetime.fromisoformat(timestamp)
                            else:
                                dt = datetime.fromtimestamp(timestamp)
                            time_str = dt.strftime("%H:%M:%S")
                        except:
                            time_str = str(timestamp)
                    else:
                        time_str = "--:--:--"
                    
                    sender = msg.get('sender', 'Unknown')
                    actual_sender = msg.get('actual_sender')  # For room messages
                    msg_type = msg.get('type', 'contact')
                    text = msg.get('text', '')
                    signature = msg.get('signature', '')
                    
                    # Check if sender is a room server (type 3)
                    sender_contact = self.connection.get_contact_by_name(sender)
                    is_room_server = sender_contact and sender_contact.get('type') == 3
                    
                    # If no actual_sender but we have a signature, try to decode it
                    if is_room_server and not actual_sender and signature:
                        sig_contact = self.connection.contacts.get_by_key(signature) if self.connection.contacts else None
                        if sig_contact:
                            actual_sender = sig_contact.get('adv_name') or sig_contact.get('name', signature)
                        else:
                            actual_sender = signature[:8]  # Show short key if unknown
                    
                    # Format sender display (same as refresh_messages)
                    if (msg_type == "room" or is_room_server) and actual_sender:
                        # Room message - show "Room / Sender: message"
                        display_sender = f"{sender} / {actual_sender}"
                        self.chat_area.write(f"[dim]{time_str}[/dim] [cyan]{display_sender}:[/cyan] {text}\n")
                    elif msg_type == "room" or is_room_server:
                        # Room message without sender info - show as anonymous
                        self.chat_area.write(f"[dim]{time_str}[/dim] [cyan]{sender} / [dim]Anonymous[/dim]:[/cyan] {text}\n")
                    elif sender == "Me":
                        # Message sent by me
                        self.chat_area.write(f"[dim]{time_str}[/dim] [blue]You:[/blue] {text}\n")
                    elif sender == contact_name:
                        self.chat_area.write(f"[dim]{time_str}[/dim] [green]{sender}:[/green] {text}\n")
                    else:
                        self.chat_area.write(f"[dim]{time_str}[/dim] [blue]You:[/blue] {text}\n")
            else:
                self.chat_area.write("[dim]No message history[/dim]")
        except Exception as e:
            self.logger.error(f"Error loading contact messages: {e}")

    async def load_channel_messages(self, channel_name: str) -> None:
        """Load and display message history for a channel."""
        try:
            messages = self.connection.get_messages_for_channel(channel_name)
            if messages:
                from datetime import datetime
                for msg in messages:
                    timestamp = msg.get('timestamp', 0)
                    if timestamp and timestamp > 0:
                        try:
                            # Handle both ISO format and unix timestamp
                            if isinstance(timestamp, str):
                                dt = datetime.fromisoformat(timestamp)
                            else:
                                dt = datetime.fromtimestamp(timestamp)
                            time_str = dt.strftime("%H:%M:%S")
                        except:
                            time_str = str(timestamp)
                    else:
                        time_str = "--:--:--"
                    
                    sender = msg.get('sender', 'Unknown')
                    text = msg.get('text', '')
                    channel = msg.get('channel', 0)
                    
                    # Show "You" for messages sent by me
                    if sender == "Me":
                        self.chat_area.write(f"[dim]{time_str}[/dim] [blue]You:[/blue] {text}\n")
                    else:
                        self.chat_area.write(f"[dim]{time_str}[/dim] [yellow]{sender}:[/yellow] {text}\n")
            else:
                self.chat_area.write("[dim]No message history[/dim]")
        except Exception as e:
            self.logger.error(f"Error loading channel messages: {e}")

    async def update_contacts(self) -> None:
        """Update the contacts list in the UI."""
        import asyncio

        try:
            self.logger.debug("Starting contact update process...")
            await asyncio.wait_for(self.connection.refresh_contacts(), timeout=5.0)
            contacts = self.connection.get_contacts()
            self.logger.debug(f"Retrieved {len(contacts)} contacts from connection")

            # Clear and repopulate contacts list
            self.contacts_list.clear()
            self._contact_id_map.clear()  # Clear the mapping
            for contact in contacts:
                contact_name = contact.get("name", "Unknown")
                contact_type = contact.get("type", 0)
                
                # Get unread count
                unread = self.connection.get_unread_count(contact_name)
                
                # Determine freshness color based on last_seen
                last_seen = contact.get("last_seen", 0)
                import time
                age_seconds = time.time() - last_seen if last_seen > 0 else 999999
                
                # Color: green < 5min, yellow < 1hr, red > 1hr
                if age_seconds < 300:  # 5 minutes
                    color = "green"
                elif age_seconds < 3600:  # 1 hour
                    color = "yellow"
                else:
                    color = "red"
                
                # Format display with unread indicator and freshness
                type_icon = "🏠" if contact_type == 3 else ""  # Room server icon
                if unread > 0:
                    display_text = f"[{color}]●[/{color}] {type_icon}{contact_name} ({unread})"
                else:
                    display_text = f"[{color}]○[/{color}] {type_icon}{contact_name}"
                
                # Create ListItem with sanitized contact name as id for data retrieval
                contact_id = f"contact-{sanitize_id(contact_name)}"
                self._contact_id_map[contact_id] = contact_name  # Store mapping
                list_item = ListItem(Static(display_text, markup=True), id=contact_id)
                    
                self.contacts_list.append(list_item)
                self.logger.debug(f"Added contact to UI: {contact_name}")

            self.logger.info(f"Updated {len(contacts)} contacts in UI")
        except asyncio.TimeoutError:
            self.logger.error("Timeout updating contacts")
        except Exception as e:
            self.logger.error(f"Failed to update contacts: {e}")
            import traceback

            self.logger.debug(f"Contact update traceback: {traceback.format_exc()}")

    async def update_channels(self) -> None:
        """Update the channels list in the UI."""
        import asyncio

        try:
            self.logger.debug("Starting channel update process...")
            channels = await self.connection.get_channels()  # Await the async method
            self.logger.debug(f"Retrieved {len(channels)} channels from connection")

            # Clear and repopulate channels list
            self.channels_list.clear()
            self._channel_id_map.clear()  # Clear the mapping
            
            # Always add "Public" as first item with unread count
            public_unread = self.connection.get_unread_count("Public")
            if public_unread > 0:
                public_display = f"Public ({public_unread})"
            else:
                public_display = "Public"
            public_id = "channel-Public"
            self._channel_id_map[public_id] = "Public"
            self.channels_list.append(ListItem(Static(public_display), id=public_id))
            
            # Add other channels (channels is a list, not dict)
            for channel_info in channels:
                channel_name = channel_info.get('name', 'Unknown')
                if channel_name and channel_name != "Public":
                    # Get unread count for this channel
                    channel_display_name = f"Channel {channel_info.get('channel_idx', '?')}"
                    channel_unread = self.connection.get_unread_count(channel_display_name)
                    
                    if channel_unread > 0:
                        display_text = f"{channel_name} ({channel_unread})"
                    else:
                        display_text = channel_name
                    
                    channel_id = f"channel-{sanitize_id(channel_name)}"
                    self._channel_id_map[channel_id] = channel_name
                    self.channels_list.append(ListItem(Static(display_text), id=channel_id))
                    self.logger.debug(f"Added channel to UI: {channel_name}")

            self.logger.info(f"Updated {len(channels) + 1} channels in UI (including Public)")
        except Exception as e:
            self.logger.error(f"Failed to update channels: {e}")
            import traceback

            self.logger.debug(f"Channel update traceback: {traceback.format_exc()}")

    async def refresh_messages(self) -> None:
        """Refresh and display messages for the current view."""
        import asyncio

        try:
            self.logger.debug("Refreshing messages...")
            
            # Clear the chat area
            self.chat_area.clear()
            
            # Get filtered messages based on current view
            if self.current_contact:
                messages = self.connection.get_messages_for_contact(self.current_contact)
                self.logger.debug(f"Retrieved {len(messages)} messages for contact {self.current_contact}")
            elif self.current_channel is not None:
                messages = self.connection.get_messages_for_channel(
                    self.current_channel if isinstance(self.current_channel, str) else "Public"
                )
                self.logger.debug(f"Retrieved {len(messages)} messages for channel {self.current_channel}")
            else:
                # No view selected, show nothing
                messages = []
                self.logger.debug("No contact or channel selected")
            
            # Display messages
            for msg in messages:
                sender = msg.get("sender", "Unknown")
                content = msg.get("text", "")
                msg_type = msg.get("type", "contact")
                actual_sender = msg.get("actual_sender")  # For room messages
                
                self.logger.debug(f"Displaying message: type={msg_type}, sender={sender}, actual_sender={actual_sender}, text={content[:30]}")
                
                # Format sender display
                if msg_type == "room" and actual_sender:
                    # Room message - show "Room / Sender: message"
                    display_sender = f"{sender} / {actual_sender}"
                    self.chat_area.write(f"[cyan]{display_sender}:[/cyan] {content}\n")
                elif msg_type == "room":
                    # Room message without sender info
                    self.chat_area.write(f"[cyan]{sender}:[/cyan] {content}\n")
                elif msg_type == "channel":
                    self.chat_area.write(f"[yellow]{sender}:[/yellow] {content}\n")
                else:
                    self.chat_area.write(f"[green]{sender}:[/green] {content}\n")
                    
                self.logger.debug(f"Added message to chat: {sender}: {content[:50]}...")
                
        except asyncio.TimeoutError:
            self.logger.error("Timeout refreshing messages")
        except Exception as e:
            self.logger.error(f"Failed to refresh messages: {e}")
            import traceback
            self.logger.debug(f"Message refresh traceback: {traceback.format_exc()}")
    
    async def periodic_message_refresh(self) -> None:
        """Periodically check for and display new messages."""
        if not self.connection.is_connected():
            return
        
        try:
            # Track the number of messages we've already displayed
            if not hasattr(self, '_displayed_message_count'):
                self._displayed_message_count = 0
            
            # Get all messages
            all_messages = await self.connection.get_messages()
            
            # Only display new messages
            new_messages = all_messages[self._displayed_message_count:]
            
            for msg in new_messages:
                sender = msg.get("sender", "Unknown")
                content = msg.get("text", "")
                msg_type = msg.get("type", "")
                
                # Filter based on current view
                if self.current_contact:
                    # Show messages from/to this contact
                    if msg_type == "contact" and sender == self.current_contact:
                        self.chat_area.write(f"[green]{sender}:[/green] {content}\n")
                elif self.current_channel is not None:
                    # Show messages from this channel
                    if msg_type == "channel" and msg.get("channel") == self.current_channel:
                        self.chat_area.write(f"[cyan]{sender}:[/cyan] {content}\n")
            
            self._displayed_message_count = len(all_messages)
                
        except Exception as e:
            self.logger.debug(f"Periodic refresh error: {e}")

    @on(Button.Pressed, "#refresh-nodes-btn")
    async def refresh_nodes(self) -> None:
        """Refresh the available nodes list."""
        self.logger.info("Refreshing nodes list...")
        try:
            nodes = await self.connection.get_available_nodes()

            # Clear and repopulate nodes list
            self.nodes_list.clear()
            for node in nodes:
                node_name = node.get("name", "Unknown")
                self.nodes_list.append(ListItem(Static(node_name)))

            self.logger.info(f"Refreshed {len(nodes)} nodes in UI")
        except Exception as e:
            self.logger.error(f"Failed to refresh nodes: {e}")

    @on(Button.Pressed, "#node-login-btn")
    async def node_login(self) -> None:
        """Log into a node."""
        node_name = self.node_name_input.value.strip()
        password = self.node_password_input.value.strip()

        if not node_name or not password:
            self.node_status_area.insert("Please enter both node name and password\n")
            return

        self.logger.info(f"Logging into node: {node_name}")
        success = await self.connection.login_to_repeater(node_name, password)

        if success:
            self.node_status_area.insert(f"Successfully logged into {node_name}\n")
            self.node_name_input.value = ""
            self.node_password_input.value = ""
        else:
            self.node_status_area.insert(f"Failed to log into {node_name}\n")

    @on(Button.Pressed, "#node-send-cmd-btn")
    async def node_send_command(self) -> None:
        """Send a command to the logged-in node."""
        command = self.node_command_input.value.strip()

        if not command:
            self.node_status_area.insert("Please enter a command\n")
            return

        # For now, assume the node name is still in the input field
        node_name = self.node_name_input.value.strip()
        if not node_name:
            self.node_status_area.insert("Please specify node name first\n")
            return

        self.logger.info(f"Sending command to {node_name}: {command}")
        success = await self.connection.send_command_to_repeater(node_name, command)

        if success:
            self.node_status_area.insert(f"Command sent to {node_name}: {command}\n")
            self.node_command_input.value = ""
        else:
            self.node_status_area.insert(f"Failed to send command to {node_name}\n")

    @on(Button.Pressed, "#node-status-btn")
    async def node_get_status(self) -> None:
        """Get status from a node."""
        node_name = self.node_name_input.value.strip()

        if not node_name:
            self.node_status_area.insert("Please specify node name\n")
            return

        self.logger.info(f"Requesting status from node: {node_name}")
        status = await self.connection.request_repeater_status(node_name)

        if status:
            self.node_status_area.insert(f"Status from {node_name}:\n")
            self.node_status_area.insert(f"{json.dumps(status, indent=2)}\n")
        else:
            self.node_status_area.insert(f"Failed to get status from {node_name}\n")

    async def on_unmount(self) -> None:
        """Called when the app is unmounting."""
        self.logger.info("MeshTUI shutting down...")
        try:
            await self.connection.disconnect()
            self.logger.info("Connection closed successfully")
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
    
    def action_quit(self) -> None:
        """Override quit action to ensure proper cleanup."""
        self.logger.info("Quit action triggered")
        # Textual will call on_unmount automatically
        self.exit()


def main():
    """Main entry point."""
    # Configure logging to prevent stdout output
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Allow all levels through root
    # Remove any existing handlers to prevent stdout output
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add file logging for postmortem analysis (DEBUG+)
    from pathlib import Path

    log_dir = Path.home() / ".config" / "meshtui"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "meshtui.log"

    # Use rotating file handler to prevent log files from growing too large
    from logging.handlers import RotatingFileHandler

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5MB per file
        backupCount=3,  # Keep 3 backup files
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Log startup message to file
    startup_logger = logging.getLogger("meshtui.startup")
    startup_logger.info("MeshTUI starting up - all logs will be saved to %s", log_file)

    parser = argparse.ArgumentParser(
        description="MeshTUI - Textual TUI for MeshCore companion radios"
    )
    parser.add_argument(
        "-s", "--serial", help="Connect via serial port (e.g., /dev/ttyUSB0)"
    )
    parser.add_argument(
        "-b",
        "--baudrate",
        type=int,
        default=115200,
        help="Serial baudrate (default: 115200)",
    )
    parser.add_argument("-t", "--tcp", help="Connect via TCP/IP hostname")
    parser.add_argument(
        "-p", "--port", type=int, default=5000, help="TCP port (default: 5000)"
    )
    parser.add_argument("-a", "--address", help="Connect via BLE address or name")

    args = parser.parse_args()

    app = MeshTUI(args)
    app.run()


if __name__ == "__main__":
    main()
