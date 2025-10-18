# MeshTUI Testing Documentation

## Overview

MeshTUI now includes a comprehensive unit test suite using pytest. This document provides an overview of the testing setup and how to use it.

## Quick Start

### Install Test Dependencies

```bash
# Install with development dependencies
venv/bin/pip install -e ".[dev]"
```

### Run Tests

```bash
# Run all tests
venv/bin/pytest

# Run with coverage
venv/bin/pytest --cov=src/meshtui --cov-report=html
```

## Test Suite Structure

### Files Created

1. **pyproject.toml** - Updated with test dependencies and pytest configuration
2. **tests/__init__.py** - Test package initialization
3. **tests/conftest.py** - Shared fixtures and pytest configuration
4. **tests/test_database.py** - Database module tests (30+ tests)
5. **tests/test_transport.py** - Transport layer tests (Serial, BLE, TCP)
6. **tests/test_managers.py** - Manager tests (Contact, Channel, Room)
7. **tests/README.md** - Detailed testing documentation
8. **.gitignore** - Updated to exclude test artifacts

## Test Coverage

### Database Module (test_database.py)

**30+ tests covering**:
- Message storage (contact, channel, room messages)
- Message retrieval (by contact, by channel)
- Unread count tracking
  - ✅ Contact-based queries
  - ✅ Channel-based queries (fixed bug tested)
  - ✅ Marking as read
  - ✅ After-read count verification
- Contact persistence
  - ✅ Store and retrieve by pubkey
  - ✅ Store and retrieve by name
  - ✅ Contact updates
- Database migrations
  - ✅ Adding recipient_pubkey column
- Edge cases
  - ✅ Excluding own messages from unread counts
  - ✅ Channel index extraction ("Public", "Channel 1", etc.)

### Transport Module (test_transport.py)

**18+ tests covering**:
- **SerialTransport**:
  - ✅ Device identification (success/failure)
  - ✅ Retry logic with backoff
  - ✅ Timeout handling
  - ✅ Invalid payload handling
  - ✅ Port listing
  - ✅ Connection success/failure

- **BLETransport**:
  - ✅ Device scanning
  - ✅ Device filtering (MeshCore vs non-MeshCore)
  - ✅ Address persistence
  - ✅ Connection with/without scanning

- **TCPTransport**:
  - ✅ Connection success/failure

### Manager Modules (test_managers.py)

**25+ tests covering**:
- **ContactManager**:
  - ✅ Contact refresh
  - ✅ Lookup by name/pubkey/prefix
  - ✅ Room server detection
  - ✅ Repeater detection
  - ✅ Direct messaging

- **ChannelManager**:
  - ✅ Channel refresh
  - ✅ Channel lookup by index
  - ✅ Channel messaging
  - ✅ Join operations

- **RoomManager**:
  - ✅ Login/logout
  - ✅ Admin status tracking
  - ✅ Command sending
  - ✅ Room lookup by pubkey

## Test Fixtures

### Provided by conftest.py

```python
# Temporary database (auto-cleaned)
def test_something(temp_db_path):
    db = MessageDatabase(temp_db_path)
    # Test code...

# Mocked MeshCore instance
def test_with_mock(mock_meshcore):
    manager = ContactManager(mock_meshcore)
    # Test code...

# Sample data
def test_with_samples(sample_contacts, sample_messages):
    # Test code...
```

## Running Tests

### All Tests

```bash
venv/bin/pytest
```

### Specific Test File

```bash
venv/bin/pytest tests/test_database.py
```

### Specific Test

```bash
venv/bin/pytest tests/test_database.py::TestMessageDatabase::test_get_unread_count_channel
```

### By Pattern

```bash
venv/bin/pytest -k "unread"
```

### With Coverage

```bash
venv/bin/pytest --cov=src/meshtui --cov-report=term-missing
venv/bin/pytest --cov=src/meshtui --cov-report=html  # HTML report in htmlcov/
```

## Benefits

### 1. Regression Prevention

Tests catch bugs before they reach production:
- ✅ Unread count channel query bug caught by tests
- ✅ Retry logic verified to work correctly
- ✅ Database migrations tested

### 2. Refactoring Confidence

Change code with confidence knowing tests will catch breakage:
- ✅ Can refactor database queries safely
- ✅ Can modify transport logic without fear
- ✅ Can restructure managers knowing behavior is preserved

### 3. Documentation

Tests serve as executable documentation:
- ✅ Shows how to use each module
- ✅ Demonstrates expected behavior
- ✅ Clarifies edge cases

### 4. Faster Development

Find bugs immediately without manual testing:
- ✅ No need to connect to hardware for every change
- ✅ Tests run in seconds
- ✅ Automated verification

## Test-Driven Development (TDD)

For new features, consider writing tests first:

1. **Write failing test** - Define expected behavior
2. **Implement feature** - Make test pass
3. **Refactor** - Clean up while tests ensure correctness

Example:
```python
def test_new_feature():
    """Test the new feature I'm about to implement."""
    result = new_feature("input")
    assert result == "expected output"
```

## Mocking Strategy

### What We Mock

- ✅ MeshCore library (hardware dependency)
- ✅ Serial port operations
- ✅ BLE scanning
- ✅ Network connections

### What We Don't Mock

- ✅ Database operations (use temp database)
- ✅ Manager logic (test real implementations)
- ✅ Data transformations

## Coverage Goals

### Current Coverage

Run `pytest --cov` to see current coverage. Aim for:
- **Database module**: >90% (high value, easy to test)
- **Transport module**: >80% (hardware mocking complexity)
- **Manager modules**: >85% (business logic)
- **Overall**: >80%

### Improving Coverage

```bash
# See what's not covered
venv/bin/pytest --cov=src/meshtui --cov-report=term-missing

# Generate HTML report to browse
venv/bin/pytest --cov=src/meshtui --cov-report=html
open htmlcov/index.html
```

## Best Practices Applied

### ✅ Test Isolation

Each test is independent:
- Uses temp databases
- Mocks external dependencies
- No shared state between tests

### ✅ Clear Test Names

```python
test_get_unread_count_channel  # ✅ Clear what's tested
test_stuff                      # ❌ Unclear
```

### ✅ Arrange-Act-Assert

```python
def test_example():
    # Arrange - Set up test data
    db = MessageDatabase(temp_db_path)

    # Act - Perform the action
    result = db.get_unread_count("Public")

    # Assert - Verify the result
    assert result == 5
```

### ✅ Test Both Paths

```python
def test_success_case():
    # Test when everything works

def test_failure_case():
    # Test when things go wrong
```

## Integration with CI/CD

Tests can be run in GitHub Actions, GitLab CI, etc.:

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install -e ".[dev]"
      - run: pytest --cov --cov-report=xml
      - uses: codecov/codecov-action@v2
```

## Future Test Additions

Suggested areas for additional tests:

1. **Connection Module** - Complex orchestration logic
2. **App Module** - UI event handlers (may require Textual testing helpers)
3. **Integration Tests** - End-to-end workflows
4. **Performance Tests** - Database query performance
5. **Stress Tests** - Many messages/contacts

## Troubleshooting

### Tests Failing After Changes

1. **Check if behavior intentionally changed** - Update tests if yes
2. **Check if bug was introduced** - Fix the code if no
3. **Check if test is flaky** - Fix test isolation issues

### Import Errors

Ensure `src` is in Python path (handled by conftest.py):
```python
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
```

### Async Test Issues

Mark async tests with `@pytest.mark.asyncio`:
```python
@pytest.mark.asyncio
async def test_async_function():
    result = await async_function()
    assert result is not None
```

## Resources

- **tests/README.md** - Detailed testing guide
- **tests/conftest.py** - Fixture examples
- **Pytest Docs** - https://docs.pytest.org/
- **pytest-asyncio** - https://pytest-asyncio.readthedocs.io/

## Summary

The test suite provides:
- ✅ **73+ unit tests** covering core functionality
- ✅ **Comprehensive fixtures** for easy test writing
- ✅ **Mocked dependencies** so no hardware needed
- ✅ **Coverage reporting** to track test quality
- ✅ **Clear documentation** for writing more tests
- ✅ **CI/CD ready** for automated testing

Tests run in **seconds** and catch bugs **before** they reach users!
