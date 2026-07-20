import pytest
import os
import sys
import time

# Ensure the root project directory is on the path so we can import services
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from persistence.sqlite_store import SQLiteStore

@pytest.fixture
def mock_store():
    """Provides a temporary SQLite store that is properly cleaned up after each test."""
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)  # Close the file descriptor immediately; SQLite will manage it
    store = SQLiteStore(path)
    yield store
    store.close()  # Close the DB connection before file deletion
    time.sleep(0.1)  # Small grace period for Windows file handles to release
    try:
        os.remove(path)
    except OSError:
        pass  # Non-fatal: temp file cleanup failure

@pytest.fixture
def sample_schema():
    return {
        "company_name": {"type": "string", "description": "Name of the startup"},
        "industry": {"type": "string", "description": "Industry or sector"}
    }
