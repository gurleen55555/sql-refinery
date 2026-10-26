"""Tests for LLM client wiring (no live API calls)."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.llm import build_client, suggest_sql_rewrite


def test_suggest_without_api_key():
    settings = Settings(
        nebius_api_key=None,
        nebius_base_url="https://api.tokenfactory.nebius.com/v1/",
        nebius_model="nvidia/Nemotron-3_5-Lightning",
        duckdb_path=":memory:",
        sql_statement_timeout_ms=5000,
        benchmark_warmup_runs=1,
        benchmark_timed_runs=3,
    )
    result = suggest_sql_rewrite("SELECT 1", settings=settings)
    assert not result.ok
    assert "NEBIUS_API_KEY" in (result.error or "")


def test_build_client_requires_key():
    settings = Settings(
        nebius_api_key=None,
        nebius_base_url="https://api.tokenfactory.nebius.com/v1/",
        nebius_model="nvidia/Nemotron-3_5-Lightning",
        duckdb_path=":memory:",
        sql_statement_timeout_ms=5000,
        benchmark_warmup_runs=1,
        benchmark_timed_runs=3,
    )
    with pytest.raises(ValueError, match="NEBIUS_API_KEY"):
        build_client(settings)
