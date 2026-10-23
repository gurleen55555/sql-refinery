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
DuckDB database schema:

1. customers(
    customer_id INTEGER,
    name VARCHAR,
    email VARCHAR,
    country VARCHAR,
    signup_date DATE
)

2. orders(
    order_id INTEGER,
    customer_id INTEGER,
    amount DECIMAL(12, 2),
    order_date DATE,
    status VARCHAR
)

3. products(
    product_id INTEGER,
    product_name VARCHAR,
    category VARCHAR,
    price DECIMAL(10, 2)
)

4. order_items(
    order_item_id INTEGER,
    order_id INTEGER,
    product_id INTEGER,
    quantity INTEGER,
    unit_price DECIMAL(10, 2)
)

5. payments(
    payment_id INTEGER,
    order_id INTEGER,
    payment_date DATE,
    amount DECIMAL(12, 2),
    payment_method VARCHAR,
    status VARCHAR
)

Relationships:
- orders.customer_id references customers.customer_id
- order_items.order_id references orders.order_id
- order_items.product_id references products.product_id
- payments.order_id references orders.order_id

Business rules:
- orders.status can be completed, pending, or cancelled.
- payments.status can be paid, pending, or refunded.
- Revenue from order items is calculated as quantity * unit_price.
- Use orders.amount for the order-level amount.
- Do not assume that orders.amount always equals the sum of its order items.
""".strip()


_SYSTEM_PROMPT = f"""You are an expert SQL optimization assistant for DuckDB.

Your task is to propose ONE alternative SQL query that preserves the
original query's exact result semantics on the supplied schema.

Rules:
- Output only a JSON object with "optimized_sql" and "rationale".
- optimized_sql must contain exactly one DuckDB-compatible SELECT query.
- WITH clauses and common table expressions are allowed.
- Preserve the selected columns, column order, aliases, data types where
  practical, filtering, joins, grouping, NULL behavior, and duplicate counts.
- Do not change the meaning of aggregates, joins, or subqueries.
- Do not add or remove rows unless the original query does so.
- Never invent tables or columns.
- Do not use INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, or other
  data-changing or administrative statements.
- If you cannot identify a safe optimization, return the original query
  unchanged and explain why in the rationale.
- Do not claim a query is faster unless benchmarking confirms it.
- Preserve every JOIN and its join condition from the original query.
- Do not add or remove tables, joins, filters, grouping, or aggregations
  unless the transformation is provably equivalent.
- Preserve the exact semantics of SUM, AVG, COUNT, and COUNT DISTINCT.
- If you cannot safely optimize the query, return the original SQL unchanged.

Database schema:
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
    """Extract a JSON object from plain, fenced, or surrounding text."""
    text = (text or "").strip()

    if not text:
        return None

    # Try parsing the complete response first.
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    # Remove Markdown code fences, if present.
    cleaned = re.sub(
        r"^\s*```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s*```\s*$", "", cleaned).strip()

    try:
        payload = json.loads(cleaned)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    # Search for a JSON object embedded in surrounding text.
    decoder = json.JSONDecoder()

    for match in re.finditer(r"\{", cleaned):
        try:
            payload, _ = decoder.raw_decode(cleaned[match.start():])
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            continue

    # Some models return SQL directly instead of JSON.
    # Accept that only if the response looks like a SELECT query.
    direct_sql = re.sub(
        r"^\s*```(?:sql)?\s*|\s*```\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    if re.match(r"^(SELECT|WITH)\b", direct_sql, re.IGNORECASE):
        return {
            "optimized_sql": direct_sql,
            "rationale": (
                "The model returned SQL directly rather than JSON. "
                "Review and validate the query before benchmarking."
            ),
        }

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
            error=(
                "Nemotron returned a response that could not be parsed. "
                "Inspect raw_content to see the model's actual response."
            ),
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
