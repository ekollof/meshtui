# How to Chat in MeshTUI

## Quick Start

1. **Launch the app:**
   ```bash
   python -m meshtui -s /dev/ttyUSB0
   ```

2. **Select a contact or channel:**
   - **For direct messages:** Click on a contact name in the left "Contacts" list
   - **For channel messages:** Click on a channel name in the "Channels" list
   
3. **Send a message:**
   - Type your message in the input field at the bottom
   - Press **Enter** or click the **Send** button

## Features Added

### ✅ Contact Selection
- Click any contact in the contacts list to start a direct message conversation
- The chat area will update with the contact's name and message history
- Messages you send will appear in blue
- Messages you receive will appear in green

### ✅ Channel Selection
- Click any channel in the channels list to join the conversation
- Select "Public" to see all channel messages
- Channel messages show sender → #channel format
- Cannot send to "Public" view (select a specific channel instead)

### ✅ Message History
- When you select a contact or channel, previous messages automatically load
- Messages include timestamps (HH:MM:SS format)
- Color-coded for easy reading:
  - **Blue**: Your messages
  - **Green**: Received messages (contacts)
  - **Cyan**: Channel names

### ✅ Visual Feedback
- Selected contact/channel is highlighted
- Chat area header shows who you're talking to
- Message input automatically gets focus when you select a contact/channel
- Clear error messages if something goes wrong

## UI Layout

```
┌──────────────┬────────────────────────┬────────────┐
│  Contacts    │      Chat Area         │   Logs     │
│  - Contact1  │ ┌──────────────────┐   │            │
│  - Contact2  │ │ Chat with Name   │   │            │
│              │ ├──────────────────┤   │            │
│  Channels    │ │ Message history  │   │            │
│  - Public    │ │ appears here     │   │            │
│  - Channel1  │ └──────────────────┘   │            │
│              │                         │            │
│ [Scan]       │ [Input         ] [Send]│            │
│ [Test Log]   │                         │            │
└──────────────┴────────────────────────┴────────────┘
```

## Common Issues

### "No contact or channel selected"
**Solution:** Click on a contact or channel name in the left sidebar first

### "Cannot send to 'Public' view"
**Solution:** Public shows all channel messages. Click a specific channel to send messages

### Contact list is empty
**Solution:** 
- Make sure you're connected to a device
- Click "Scan Devices" to search for devices
- Wait a few seconds for contacts to populate after connection

## Keyboard Shortcuts

- **Ctrl+C**: Quit the application
- **Ctrl+R**: Refresh (future feature)
- **F1**: Help (future feature)
- **Enter**: Send message (when input field is focused)

## Tips

1. **Quick messaging**: After selecting a contact, just type and press Enter - no need to click Send
2. **Switch conversations**: Click different contacts/channels to switch who you're chatting with
3. **Monitor logs**: Check the right panel for connection status and errors
4. **Test connectivity**: Use the "Test Logging" button to verify your connection is working

Enjoy chatting on your mesh network! 📡
