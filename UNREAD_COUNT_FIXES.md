# Unread Message Count Reliability Fixes

## Overview

Fixed multiple issues causing unreliable unread message counts in the contact and channel panes. The unread counts now accurately reflect new messages and update properly when viewing conversations.

## Problems Identified

### Problem 1: Incorrect Channel Message Query (database.py:614-620)

**Issue**: The `get_unread_count()` method was querying channel messages incorrectly.

**Before**:
```python
cursor.execute("""
    SELECT COUNT(*) FROM messages
    WHERE type = 'channel'
      AND sender = ?  # WRONG: sender is the person's name, not channel name
      AND received_at > ?
      AND sender != 'Me'
""", (identifier, last_read))
```

**Problem**: Channel messages are stored with:
- `type`: 'channel'
- `sender`: actual person's name (e.g., "Alice")
- `channel`: channel index (0 for Public, 1/2/3 for others)

The query was checking `sender = "Public"` which would never match because the sender is the person who sent the message, not the channel name.

**After**:
```python
# Extract channel index from name
channel_idx = 0
if identifier == "Public":
    channel_idx = 0
elif identifier.startswith("Channel "):
    channel_idx = int(identifier.split(" ")[1])

cursor.execute("""
    SELECT COUNT(*) FROM messages
    WHERE type = 'channel'
      AND channel = ?  # CORRECT: check the channel field
      AND received_at > ?
      AND sender != 'Me'
""", (channel_idx, last_read))
```

### Problem 2: Missing Display Updates After Mark As Read

**Issue**: When marking messages as read, the UI didn't immediately update the unread count display.

**Locations Affected**:
1. `on_contact_selected()` - When user selects a contact (app.py:712)
2. `on_channel_selected()` - When user selects a channel (app.py:775)
3. `on_message_received()` - When viewing current conversation (app.py:340)

**Fix**: Added calls to update the display after marking as read:
```python
self.connection.mark_as_read(contact_name)
self._update_single_contact_display(contact_name)  # NEW
```

### Problem 3: Missing Channel Display Update Method

**Issue**: Only contacts had a display update method, channels did not.

**Fix**: Added `_update_single_channel_display()` method (app.py:402-427) to mirror the contact display update logic.

### Problem 4: Inconsistent Last Read Tracking

**Issue**: The `mark_as_read()` method documentation mentioned using pubkey for contacts but the implementation was inconsistent.

**Fix**: Clarified and ensured consistent behavior:
- Contacts/rooms: Use pubkey as identifier
- Channels: Use channel name as identifier

## Files Modified

### 1. src/meshtui/database.py

**get_unread_count() (lines 600-631)**:
- Fixed channel message query to use `channel` field instead of `sender`
- Added logic to extract channel index from channel name
- Added debug logging for channel queries

**mark_as_read() (lines 534-553)**:
- Added explicit comment clarifying channel identifier handling
- Improved code structure for identifier type determination

### 2. src/meshtui/app.py

**on_message_received() (lines 342-346)**:
- Added display update after marking messages as read
- Updates both contact and channel displays when viewing current conversation

**_update_single_channel_display() (lines 402-427) - NEW**:
- Added method to update channel display with unread count
- Mirrors _update_single_contact_display() logic
- Updates channel ListItem with new unread count

**on_contact_selected() (line 713)**:
- Added display update call after marking as read

**on_channel_selected() (line 776)**:
- Added display update call after marking as read

## How Unread Counts Work Now

### For Contacts (Direct Messages and Rooms)

1. **Storage**: Messages stored with `sender_pubkey`, `actual_sender_pubkey`, or `signature` containing the contact's public key
2. **Tracking**: Last read timestamp stored using contact's pubkey as identifier
3. **Query**: Counts messages where any pubkey field matches and `received_at > last_read`
4. **Display**: Shows `(n)` next to contact name, e.g., "Alice (3)"

### For Channels

1. **Storage**: Messages stored with `type='channel'` and `channel` field set to index (0, 1, 2, etc.)
2. **Tracking**: Last read timestamp stored using channel name as identifier ("Public", "Channel 1", etc.)
3. **Query**: Extracts channel index from name, counts messages where `channel=idx` and `received_at > last_read`
4. **Display**: Shows `(n)` next to channel name, e.g., "Public (5)"

### When Counts Update

**Increment**:
- New message received from any contact/channel
- Message is stored with current `received_at` timestamp
- If not viewing that conversation, unread count increases

**Mark as Read**:
- User selects contact/channel
- User views conversation with new messages
- Sets `last_read` timestamp to current time
- All messages with `received_at <= last_read` are considered read

**Display Refresh**:
- Immediately after marking as read
- When new message arrives
- When contact list is refreshed

## Testing

### Test Channel Unread Counts

1. Switch to a different channel or contact
2. Have someone send messages to a channel (e.g., Public)
3. Verify unread count appears: "Public (3)"
4. Select that channel
5. Verify unread count clears: "Public"

### Test Contact Unread Counts

1. Switch to a different contact or channel
2. Receive direct messages from a contact
3. Verify unread count appears: "Alice (2)"
4. Select that contact
5. Verify unread count clears: "Alice"

### Test Multiple Conversations

1. Receive messages in multiple channels and from multiple contacts
2. Verify each shows correct unread count
3. Select each one in turn
4. Verify unread count clears for the selected one
5. Verify other unread counts remain unchanged

## Known Behavior

### Messages Sent by User

Messages sent by the user (sender = 'Me') are excluded from unread counts. This is intentional - you don't need to be notified about your own messages.

### Room Server Messages

Room server messages are treated like contact messages, using the room server's pubkey for tracking. Unread counts work the same way as regular contacts.

### Channel vs Contact Ambiguity

If a channel has the same name as a contact, the system will try to match it as a contact first (by pubkey). If no contact is found, it's treated as a channel. This should rarely be an issue in practice.

## Performance Considerations

### Database Queries

Each unread count check runs a SQL query. With proper indexing on:
- `messages.channel`
- `messages.sender_pubkey`
- `messages.received_at`
- `last_read.identifier`

Performance should be acceptable even with thousands of messages.

### Display Updates

Display updates are targeted - only the affected contact or channel is updated, not the entire list. This keeps the UI responsive.

## Debugging

Enable DEBUG logging to see detailed unread count queries:

```python
import logging
logging.getLogger("meshtui.database").setLevel(logging.DEBUG)
```

Log output will show:
- Which identifier is being queried
- Whether it's a contact or channel
- The last read timestamp
- The final count
- Example: `🔍 Unread query: channel=Public (idx=0), last_read=1234567890`

## Summary

The unread count system now works reliably for both contacts and channels:

✅ **Channels**: Correctly query by channel index, not sender name
✅ **Contacts**: Use pubkey-based matching for accuracy
✅ **Display**: Updates immediately after marking as read
✅ **Consistency**: Both contacts and channels have update methods
✅ **Debugging**: Comprehensive logging for troubleshooting

The fixes address the root causes of unreliable unread counts and ensure the UI always reflects the correct state.
