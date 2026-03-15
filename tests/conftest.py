"""Shared test fixtures."""

from __future__ import annotations

import pytest

from reclawed.config import Config
from reclawed.models import Message, Session
from reclawed.store import Store


@pytest.fixture
def store():
    """In-memory SQLite store."""
    s = Store(":memory:")
    yield s
    s.close()


@pytest.fixture
def session(store: Store) -> Session:
    """A pre-created session."""
    s = Session(name="Test Session")
    store.create_session(s)
    return s


@pytest.fixture
def config(tmp_path) -> Config:
    """Config using a temp directory."""
    return Config(data_dir=tmp_path)
