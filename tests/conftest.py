"""Shared pytest fixtures for SQL-Refinery."""

from __future__ import annotations

import pytest

from app.sql_runner import create_connection


@pytest.fixture
def db_conn():
    """In-memory DuckDB with the demo schema."""
    conn = create_connection(":memory:")
    yield conn
    conn.close()
