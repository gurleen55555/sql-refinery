"""
Nemotron suggestions via Nebius Token Factory (OpenAI-compatible API).

This module only requests rewrites from the model. It does not execute SQL.
Execution and correctness checks live in ``sql_runner`` and ``benchmark``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from openai import OpenAI

from app.config import Settings, get_settings, llm_configured

_DEMO_SCHEMA = """
Tables:
- customers(customer_id INTEGER, name VARCHAR, country VARCHAR)
- orders(order_id INTEGER, customer_id INTEGER, amount DECIMAL, order_date DATE)
""".strip()

_SYSTEM_PROMPT = f"""You are a SQL optimization assistant for DuckDB.
Given a SQL query and schema, suggest ONE alternative SELECT query that preserves
the same result semantics on the provided schema.

Rules:
- Output only DuckDB-compatible SELECT SQL (WITH allowed).
- Do not include markdown fences or explanations outside JSON.
- Respond with JSON: {{"optimized_sql": "...", "rationale": "..."}}

Schema:
{_DEMO_SCHEMA}
"""


@dataclass(frozen=True)
class RewriteSuggestion:
    """Parsed model output (not verified until DuckDB checks run)."""

    ok: bool
    optimized_sql: str | None = None
    rationale: str | None = None
    raw_content: str | None = None
    error: str | None = None
    model: str | None = None


def build_client(settings: Settings | None = None) -> OpenAI:
    """Create an OpenAI SDK client pointed at Nebius Token Factory."""
    settings = settings or get_settings()
    if not settings.nebius_api_key:
        raise ValueError(
            "NEBIUS_API_KEY is not set. Add it to your environment or .env file."
        )
    return OpenAI(
        base_url=settings.nebius_base_url,
        api_key=settings.nebius_api_key,
    )


def _extract_json_object(text: str) -> dict | None:
    """Best-effort JSON parse from model text."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def suggest_sql_rewrite(
    original_sql: str,
    *,
    settings: Settings | None = None,
    client: OpenAI | None = None,
) -> RewriteSuggestion:
    """
    Ask the configured Nemotron model for an optimized SELECT rewrite.

    Network failures and malformed responses are returned in ``RewriteSuggestion.error``.
    This function does not claim the rewrite is correct or faster.
    """
    settings = settings or get_settings()
    if not llm_configured(settings):
        return RewriteSuggestion(ok=False, error="NEBIUS_API_KEY is not configured.")

    user_content = (
        "Original SQL:\n"
        f"{original_sql.strip()}\n\n"
        "Return JSON with optimized_sql and rationale."
    )

    try:
        api_client = client or build_client(settings)
        completion = api_client.chat.completions.create(
            model=settings.nebius_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
        )
    except Exception as exc:  # noqa: BLE001 — surface API errors to UI
        return RewriteSuggestion(
            ok=False,
            error=f"LLM request failed: {exc}",
            model=settings.nebius_model,
        )

    message = completion.choices[0].message.content or ""
    payload = _extract_json_object(message)
    if not payload or "optimized_sql" not in payload:
        return RewriteSuggestion(
            ok=False,
            raw_content=message,
            error="Model response did not contain valid JSON with optimized_sql.",
            model=settings.nebius_model,
        )

    optimized = str(payload.get("optimized_sql", "")).strip()
    rationale = str(payload.get("rationale", "")).strip() or None
    if not optimized:
        return RewriteSuggestion(
            ok=False,
            raw_content=message,
            error="optimized_sql was empty.",
            model=settings.nebius_model,
        )

    return RewriteSuggestion(
        ok=True,
        optimized_sql=optimized,
        rationale=rationale,
        raw_content=message,
        model=settings.nebius_model,
    )
