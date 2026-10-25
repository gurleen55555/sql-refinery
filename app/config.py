"""
Environment-backed configuration for Nebius Token Factory and the app.

All secrets come from the environment. Copy `.env.example` to `.env` for local dev.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv
import streamlit as st

load_dotenv()

# Documented defaults from Nebius Token Factory OpenAI-compatible API:
# https://docs.tokenfactory.nebius.com/api-reference/introduction
DEFAULT_NEBIUS_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
# Nemotron model IDs: https://tokenfactory.nebius.com/model-catalog.md
DEFAULT_NEBIUS_MODEL = "nvidia/Nemotron-3_5-Lightning"


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded once at import time."""

    nebius_api_key: str | None
    nebius_base_url: str
    nebius_model: str
    duckdb_path: str
    sql_statement_timeout_ms: int
    benchmark_warmup_runs: int
    benchmark_timed_runs: int



def get_settings() -> Settings:
    """Build settings from environment variables or Streamlit secrets."""

    def get_value(name: str, default: str | None = None) -> str | None:
        # Environment variables take priority; useful for local development.
        value = os.getenv(name)
        if value:
            return value

        # Read Streamlit Community Cloud secrets when available.
        try:
            value = st.secrets.get(name, default)
            return str(value) if value is not None else default
        except Exception:
            # Streamlit secrets may not be configured locally.
            return default

    return Settings(
        nebius_api_key=get_value("NEBIUS_API_KEY"),
        nebius_base_url=get_value(
            "NEBIUS_BASE_URL", DEFAULT_NEBIUS_BASE_URL
        ),
        nebius_model=get_value(
            "NEBIUS_MODEL", DEFAULT_NEBIUS_MODEL
        ),
        duckdb_path=get_value("DUCKDB_PATH", ":memory:"),
        sql_statement_timeout_ms=int(
            get_value("SQL_STATEMENT_TIMEOUT_MS", "5000")
        ),
        benchmark_warmup_runs=int(
            get_value("BENCHMARK_WARMUP_RUNS", "1")
        ),
        benchmark_timed_runs=int(
            get_value("BENCHMARK_TIMED_RUNS", "3")
        ),
    )


def llm_configured(settings: Settings | None = None) -> bool:
    """True when an API key is present (LLM calls may still fail at runtime)."""
    settings = settings or get_settings()
    return bool(settings.nebius_api_key)
