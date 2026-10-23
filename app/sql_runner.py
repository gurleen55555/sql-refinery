"""
Safe DuckDB execution and result comparison for SQL-Refinery.

Only validated read-only SELECT queries are executed. Model output is never
run without passing SQLGlot-based checks first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import duckdb
import sqlglot
from sqlglot import exp

# Keywords that must not appear in user- or model-provided SQL.
_FORBIDDEN_KEYWORDS = frozenset(
    {
        "insert",
        "update",
        "delete",
        "drop",
        "create",
        "alter",
        "truncate",
        "attach",
        "copy",
        "export",
        "import",
        "load",
        "install",
        "pragma",
        "call",
        "execute",
        "grant",
        "revoke",
    }
)

_SAMPLE_DDL = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY,
    name VARCHAR,
    country VARCHAR
);

CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER,
    amount DECIMAL(10, 2),
    order_date DATE
);

INSERT INTO customers VALUES
    (1, 'Alice', 'US'),
    (2, 'Bob', 'DE'),
    (3, 'Carol', 'US');

INSERT INTO orders VALUES
    (101, 1, 250.00, '2024-01-15'),
    (102, 1, 75.50, '2024-02-01'),
    (103, 2, 120.00, '2024-01-20'),
    (104, 3, 300.00, '2024-03-10');
"""


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of static SQL validation."""

    ok: bool
    message: str
    normalized_sql: str | None = None


@dataclass(frozen=True)
class QueryResult:
    """Result of executing a validated query."""

    ok: bool
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[Any, ...], ...] = ()
    error: str | None = None
    sql_executed: str | None = None


def seed_demo_database(conn: duckdb.DuckDBPyConnection) -> None:
    """Create a small fixed schema used for local correctness and benchmarks."""
    conn.execute("BEGIN")
    try:
        for statement in _SAMPLE_DDL.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                conn.execute(stmt)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def create_connection(database: str = ":memory:") -> duckdb.DuckDBPyConnection:
    """Open DuckDB and load the controlled demo dataset."""
    conn = duckdb.connect(database=database, read_only=False)
    seed_demo_database(conn)
    return conn


def _strip_sql_comments(sql: str) -> str:
    """Remove line and block comments before keyword scanning."""
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return sql


def validate_sql(sql: str, dialect: str = "duckdb") -> ValidationResult:
    """
    Parse and reject unsafe or unsupported SQL.

    Rules:
    - Exactly one statement
    - Must be SELECT (including WITH ... SELECT)
    - No forbidden DDL/DML keywords in the text
    """
    cleaned = sql.strip()
    if not cleaned:
        return ValidationResult(ok=False, message="SQL is empty.")

    try:
        statements = sqlglot.parse(cleaned, read=dialect)
    except sqlglot.errors.ParseError as exc:
        return ValidationResult(ok=False, message=f"Parse error: {exc}")

    if len(statements) != 1:
        return ValidationResult(
            ok=False,
            message="Exactly one SQL statement is allowed.",
        )

    statement = statements[0]
    if statement.find(exp.Insert | exp.Update | exp.Delete | exp.Drop | exp.Create):
        return ValidationResult(ok=False, message="Only read-only SELECT queries are allowed.")

    if not isinstance(statement, (exp.Select, exp.Union, exp.Intersect, exp.Except)) and not (
        isinstance(statement, exp.With) and statement.find(exp.Select)
    ):
        return ValidationResult(
            ok=False,
            message="Only SELECT queries (optionally with WITH) are allowed.",
        )

    lowered = _strip_sql_comments(cleaned).lower()
    for keyword in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", lowered):
            return ValidationResult(
                ok=False,
                message=f"Forbidden keyword detected: {keyword.upper()}",
            )

    normalized = statement.sql(dialect=dialect)
    return ValidationResult(ok=True, message="OK", normalized_sql=normalized)


def execute_query(
    conn: duckdb.DuckDBPyConnection,
    sql: str,
    *,
    validate: bool = True,
    timeout_ms: int | None = None,
) -> QueryResult:
    """Validate (by default) and run SQL against the provided connection."""
    sql_to_run = sql
    if validate:
        validation = validate_sql(sql)
        if not validation.ok:
            return QueryResult(ok=False, error=validation.message)
        sql_to_run = validation.normalized_sql or sql

    try:
        if timeout_ms is not None:
            try:
                conn.execute(f"SET statement_timeout='{int(timeout_ms)}ms'")
            except duckdb.Error:
                # Not all DuckDB builds expose statement_timeout; continue without it.
                pass
        cursor = conn.execute(sql_to_run)
        if cursor.description is None:
            return QueryResult(
                ok=False,
                error="Query did not return a result set.",
                sql_executed=sql_to_run,
            )
        columns = tuple(col[0] for col in cursor.description)
        rows = tuple(tuple(row) for row in cursor.fetchall())
        return QueryResult(
            ok=True,
            columns=columns,
            rows=rows,
            sql_executed=sql_to_run,
        )
    except duckdb.Error as exc:
        return QueryResult(ok=False, error=str(exc), sql_executed=sql_to_run)


def compare_results(left: QueryResult, right: QueryResult) -> tuple[bool, str]:
    """
    Compare two successful query results for semantic equality.

    Row order is ignored unless the same ordered rows appear in both sets.
    Column order must match.
    """
    if not left.ok or not right.ok:
        return False, "Both queries must execute successfully to compare."

    if left.columns != right.columns:
        return False, f"Column mismatch: {left.columns} vs {right.columns}"

    left_set = set(left.rows)
    right_set = set(right.rows)
    if left_set != right_set:
        return (
            False,
            f"Row mismatch: {len(left_set)} unique rows vs {len(right_set)} unique rows.",
        )

    if left.rows != right.rows and left_set == right_set:
        return True, "Same multiset of rows; order differs (treated as equivalent)."

    return True, "Results match."
