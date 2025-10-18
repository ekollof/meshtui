"""
Pytest configuration and shared fixtures for MeshTUI tests.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, AsyncMock, MagicMock
import sys

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def temp_db_path():
    """Provide a temporary database path that is cleaned up after the test."""
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test.db"
    yield db_path
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_meshcore():
    """Provide a mocked MeshCore instance."""
    mock = AsyncMock()
    mock.commands = Mock()

    # Contact-related commands
    mock.commands.get_contacts = AsyncMock()
    mock.commands.send_msg = AsyncMock()

    # Channel-related commands
    mock.commands.send_chan_msg = AsyncMock()
    mock.commands.get_channel = AsyncMock()
    mock.commands.set_channel = AsyncMock()

    # Room-related commands
    mock.commands.send_login = AsyncMock()
    mock.commands.send_logout = AsyncMock()
    mock.commands.get_msg = AsyncMock()

    # Device-related commands
    mock.commands.send_device_query = AsyncMock()

    # Event subscription
    mock.subscribe = Mock(return_value=None)
    mock.unsubscribe = Mock()
    mock.disconnect = AsyncMock()

    # Channel info list attribute
    mock.channel_info_list = []

    # Contact lookup methods (used by managers)
    mock.get_contact_by_name = Mock(return_value=None)
    mock.get_contact_by_key_prefix = Mock(return_value=None)

    return mock


@pytest.fixture
def sample_contacts():
    """Provide sample contact data for testing."""
    return [
        {
            "pubkey": "abc123",
            "name": "Alice",
            "adv_name": "Alice",
            "type": 0,
            "last_seen": 1234567890,
        },
        {
            "pubkey": "def456",
            "name": "Bob",
            "adv_name": "Bob",
            "type": 0,
            "last_seen": 1234567800,
        },
        {
            "pubkey": "ghi789",
            "name": "Room1",
            "adv_name": "Room1",
            "type": 3,  # Room server
            "last_seen": 1234567850,
        },
    ]


@pytest.fixture
def sample_messages():
    """Provide sample message data for testing."""
    return [
        {
            "type": "contact",
            "sender": "Alice",
            "sender_pubkey": "abc123",
            "text": "Hello!",
            "timestamp": 1234567890,
            "channel": None,
        },
        {
            "type": "channel",
            "sender": "Bob",
            "sender_pubkey": "def456",
            "text": "Hi everyone",
            "timestamp": 1234567900,
            "channel": 0,  # Public
        },
        {
            "type": "contact",
            "sender": "Alice",
            "sender_pubkey": "abc123",
            "text": "How are you?",
            "timestamp": 1234567910,
            "channel": None,
        },
    ]


@pytest.fixture
def mock_event():
    """Provide a mock event object."""
    event = Mock()
    event.type = Mock()
    event.payload = {}
    return event
