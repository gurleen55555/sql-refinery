
"""Helpers for processing multiple SQL statements."""

import sqlglot
from sqlglot.errors import ParseError


DEFAULT_BATCH_LIMIT = 10
MAX_BATCH_LIMIT = 100


def split_sql_queries(sql: str) -> list[str]:
    """Split SQL text into individual statements."""
    if not sql or not sql.strip():
        return []

    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except ParseError as exc:
        raise ValueError(f"Could not parse the SQL batch: {exc}") from exc

    queries = []

    for statement in statements:
        if statement is None:
            continue

        query = statement.sql(dialect="duckdb").strip()

        if query:
            queries.append(query)

    return queries


def validate_batch_limit(limit: int) -> int:
    """Ensure the requested batch limit is between 1 and 100."""
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError("Batch limit must be an integer.")

    if not 1 <= limit <= MAX_BATCH_LIMIT:
        raise ValueError(
            f"Batch limit must be between 1 and {MAX_BATCH_LIMIT}."
        )

    return limit


def enforce_batch_limit(
    queries: list[str],
    limit: int = DEFAULT_BATCH_LIMIT,
) -> list[str]:
    """Validate the limit and reject batches that exceed it."""
    validate_batch_limit(limit)

    if len(queries) > limit:
        raise ValueError(
            f"You provided {len(queries)} queries, but the batch limit "
            f"is {limit}. Increase the limit or submit fewer queries."
        )

    return queries
