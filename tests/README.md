# MeshTUI Test Suite

## Overview

This directory contains comprehensive unit tests for the MeshTUI application. The test suite uses pytest and covers all major modules including database operations, transport layers, manager classes, and connection handling.

## Test Structure

```
tests/
├── __init__.py           # Test package initialization
├── conftest.py           # Pytest fixtures and configuration
├── test_database.py      # Database module tests
├── test_transport.py     # Transport layer tests (Serial, BLE, TCP)
├── test_managers.py      # Manager tests (Contact, Channel, Room)
└── README.md             # This file
```

## Running Tests

### Install Test Dependencies

```bash
# Install development dependencies
venv/bin/pip install -e ".[dev]"

# Or manually:
venv/bin/pip install pytest pytest-asyncio pytest-cov pytest-mock
```

### Run All Tests

```bash
# Run all tests with coverage
venv/bin/pytest

# Run with verbose output
venv/bin/pytest -v

# Run with coverage report
venv/bin/pytest --cov=src/meshtui --cov-report=term-missing
```

### Run Specific Test Files

```bash
# Run only database tests
venv/bin/pytest tests/test_database.py

# Run only transport tests
venv/bin/pytest tests/test_transport.py

# Run only manager tests
venv/bin/pytest tests/test_managers.py
```

### Run Specific Test Classes or Functions

```bash
# Run specific test class
venv/bin/pytest tests/test_database.py::TestMessageDatabase

# Run specific test function
venv/bin/pytest tests/test_database.py::TestMessageDatabase::test_store_message_contact

# Run tests matching a pattern
venv/bin/pytest -k "unread"
```

## Test Coverage

The test suite provides comprehensive coverage of:

### Database Module (test_database.py)
- ✅ Message storage (contacts, channels, rooms)
- ✅ Message retrieval
- ✅ Unread count tracking (contacts and channels)
- ✅ Mark as read functionality
- ✅ Contact persistence
- ✅ Contact lookup (by pubkey, name, adv_name)
- ✅ Database migrations
- ✅ Channel index extraction

### Transport Module (test_transport.py)
- ✅ Serial device identification
- ✅ Serial device retry logic
- ✅ Serial port listing
- ✅ BLE device scanning
- ✅ BLE device filtering
- ✅ BLE address persistence
- ✅ TCP connections
- ✅ Connection failure handling

### Manager Modules (test_managers.py)
- ✅ ContactManager: refresh, lookup, room/repeater detection
- ✅ ChannelManager: refresh, channel lookup, messaging
- ✅ RoomManager: login/logout, admin status, commands

## Test Fixtures

### Shared Fixtures (conftest.py)

- `temp_db_path`: Temporary database path for isolated tests
- `mock_meshcore`: Mocked MeshCore instance with common methods
- `sample_contacts`: Sample contact data for testing
- `sample_messages`: Sample message data for testing
- `mock_event`: Mock event object for event handlers

## Writing New Tests

### Test Structure

```python
import pytest
from unittest.mock import Mock, AsyncMock

class TestYourModule:
    """Tests for YourModule class."""

    def test_synchronous_function(self):
        """Test a synchronous function."""
        # Arrange
        expected = "result"

        # Act
        actual = your_function()

        # Assert
        assert actual == expected

    @pytest.mark.asyncio
    async def test_async_function(self):
        """Test an asynchronous function."""
        # Arrange
        mock = AsyncMock()

        # Act
        result = await your_async_function(mock)

        # Assert
        assert result is not None
        mock.assert_called_once()
```

### Using Fixtures

```python
def test_with_temp_db(temp_db_path):
    """Test using temporary database."""
    db = MessageDatabase(temp_db_path)
    # Test code here
    # Cleanup happens automatically

def test_with_mock(mock_meshcore):
    """Test with mocked MeshCore."""
    manager = ContactManager(mock_meshcore)
    # Test code here
```

### Mocking MeshCore

```python
from unittest.mock import Mock, AsyncMock, patch

# Mock device query
mock_result = Mock()
mock_result.type = EventType.DEVICE_INFO
mock_result.payload = {"model": "Test Device"}

with patch("module.MeshCore.create_serial", return_value=mock_meshcore):
    mock_meshcore.commands.send_device_query.return_value = mock_result
    # Test code here
```

## Best Practices

### Test Naming
- Use descriptive test names: `test_get_unread_count_for_channel`
- Include what's being tested and expected outcome
- Use `test_<function>_<scenario>` pattern

### Test Organization
- Group related tests in classes
- One test file per module
- Use fixtures for common setup

### Assertions
- Use specific assertions: `assert x == y` not `assert x`
- Include helpful messages: `assert result, "Expected non-empty result"`
- Test both success and failure cases

### Async Tests
- Always mark async tests with `@pytest.mark.asyncio`
- Use `AsyncMock` for async methods
- Test timeout scenarios

### Mocking
- Mock external dependencies (MeshCore, serial ports, BLE)
- Don't mock the code you're testing
- Use `patch` for module-level imports

## Continuous Integration

Tests can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - run: pip install -e ".[dev]"
      - run: pytest --cov=src/meshtui --cov-report=xml
      - uses: codecov/codecov-action@v2
```

## Coverage Reports

### Terminal Report
```bash
venv/bin/pytest --cov=src/meshtui --cov-report=term-missing
```

### HTML Report
```bash
venv/bin/pytest --cov=src/meshtui --cov-report=html
# Open htmlcov/index.html in browser
```

### XML Report (for CI)
```bash
venv/bin/pytest --cov=src/meshtui --cov-report=xml
```

## Troubleshooting

### Import Errors
If you get import errors, ensure the `src` directory is in the Python path:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
```

### Async Test Failures
Make sure async tests are marked with `@pytest.mark.asyncio` and that `pytest-asyncio` is installed.

### Database Locked Errors
Use the `temp_db_path` fixture to ensure each test gets its own isolated database.

### Mock Not Called
Check that you're patching the correct module path and that the mock is set up before the code under test runs.

## Adding Tests for New Features

When adding new features to MeshTUI:

1. **Write tests first** (TDD approach) or alongside the code
2. **Test both success and failure cases**
3. **Mock external dependencies** (hardware, network)
4. **Update this README** if adding new test files
5. **Aim for >80% code coverage** for new code

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/)
- [unittest.mock Documentation](https://docs.python.org/3/library/unittest.mock.html)
- [Pytest Coverage Plugin](https://pytest-cov.readthedocs.io/)

## Contributing

When contributing tests:

- Follow the existing test structure and naming conventions
- Add docstrings to test functions explaining what they test
- Keep tests isolated and independent
- Use fixtures for common setup
- Run the full test suite before submitting changes

---

For questions or issues with tests, please check the main project documentation or open an issue on GitHub.
