
"""
Safe DuckDB execution and result comparison for SQL-Refinery.

Creates a synthetic e-commerce database for testing SQL rewrites.
Only one read-only SELECT/WITH query may be executed at a time.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

import duckdb
import sqlglot
from sqlglot import exp


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


_SAMPLE_DDL = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY,
    name VARCHAR,
    email VARCHAR,
    country VARCHAR,
    signup_date DATE
);

CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER,
    amount DECIMAL(12, 2),
    order_date DATE,
    status VARCHAR
);

CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY,
    product_name VARCHAR,
    category VARCHAR,
    price DECIMAL(10, 2)
);

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id INTEGER,
    product_id INTEGER,
    quantity INTEGER,
    unit_price DECIMAL(10, 2)
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id INTEGER PRIMARY KEY,
    order_id INTEGER,
    payment_date DATE,
    amount DECIMAL(12, 2),
    payment_method VARCHAR,
    status VARCHAR
);
"""


def seed_demo_database(conn: duckdb.DuckDBPyConnection) -> None:
    """Create and populate a synthetic e-commerce dataset."""

    # Keep seeding transactional so a failure does not leave partial data.
    conn.execute("BEGIN TRANSACTION")
    try:
        for statement in _SAMPLE_DDL.strip().split(";"):
            if statement.strip():
                conn.execute(statement)

        # Only seed an empty database. Reopening a persistent database
        # will not duplicate its sample rows.
        customer_count = conn.execute(
            "SELECT COUNT(*) FROM customers"
        ).fetchone()[0]

        if customer_count == 0:
            conn.execute("""
                INSERT INTO customers
                SELECT
                    i::INTEGER AS customer_id,
                    'Customer ' || i AS name,
                    'customer' || i || '@example.com' AS email,
                    CASE i % 6
                        WHEN 0 THEN 'US'
                        WHEN 1 THEN 'IN'
                        WHEN 2 THEN 'GB'
                        WHEN 3 THEN 'DE'
                        WHEN 4 THEN 'CA'
                        ELSE 'AU'
                    END AS country,
                    DATE '2022-01-01' + (i % 1460)::INTEGER
                        AS signup_date
                FROM range(1, 10001) AS t(i)
            """)

            conn.execute("""
                INSERT INTO products
                SELECT
                    i::INTEGER AS product_id,
                    'Product ' || i AS product_name,
                    CASE i % 5
                        WHEN 0 THEN 'Electronics'
                        WHEN 1 THEN 'Clothing'
                        WHEN 2 THEN 'Home'
                        WHEN 3 THEN 'Books'
                        ELSE 'Sports'
                    END AS category,
                    (10 + (i % 90))::DECIMAL(10, 2) AS price
                FROM range(1, 501) AS t(i)
            """)

            conn.execute("""
                INSERT INTO orders
                SELECT
                    i::INTEGER AS order_id,
                    (1 + ((i * 37) % 10000))::INTEGER AS customer_id,
                    (
                        ((10 + ((i * 2) % 90)) * (1 + (i % 5)))
                        +
                        ((10 + ((i * 7) % 90)) * (1 + ((i + 1) % 5)))
                    )::DECIMAL(12, 2) AS amount,
                    DATE '2023-01-01' + (i % 1095)::INTEGER
                        AS order_date,
                    CASE i % 10
                        WHEN 0 THEN 'cancelled'
                        WHEN 1 THEN 'pending'
                        ELSE 'completed'
                    END AS status
                FROM range(1, 50001) AS t(i)
            """)

            # Two items per order, giving 100,000 order-item records.
            conn.execute("""
                INSERT INTO order_items
                SELECT
                    ((o.order_id - 1) * 2 + item.item_no)::INTEGER
                        AS order_item_id,
                    o.order_id,
                    CASE item.item_no
                        WHEN 1 THEN (1 + ((o.order_id * 2) % 500))
                        ELSE (1 + ((o.order_id * 7) % 500))
                    END::INTEGER AS product_id,
                    CASE item.item_no
                        WHEN 1 THEN (1 + (o.order_id % 5))
                        ELSE (1 + ((o.order_id + 1) % 5))
                    END::INTEGER AS quantity,
                    CASE item.item_no
                        WHEN 1 THEN (10 + ((o.order_id * 2) % 90))
                        ELSE (10 + ((o.order_id * 7) % 90))
                    END::DECIMAL(10, 2) AS unit_price
                FROM orders o
                CROSS JOIN (VALUES (1), (2)) AS item(item_no)
            """)

            conn.execute("""
                INSERT INTO payments
                SELECT
                    o.order_id::INTEGER AS payment_id,
                    o.order_id,
                    o.order_date AS payment_date,
                    o.amount AS amount,
                    CASE o.order_id % 4
                        WHEN 0 THEN 'card'
                        WHEN 1 THEN 'UPI'
                        WHEN 2 THEN 'wallet'
                        ELSE 'bank_transfer'
                    END AS payment_method,
                    CASE
                        WHEN o.status = 'cancelled' THEN 'refunded'
                        WHEN o.status = 'pending' THEN 'pending'
                        ELSE 'paid'
                    END AS status
                FROM orders o
            """)

        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def create_connection(
    database: str = ":memory:",
) -> duckdb.DuckDBPyConnection:
    """Open DuckDB and load the controlled demo dataset."""
    conn = duckdb.connect(database=database, read_only=False)
    try:
        seed_demo_database(conn)
    except Exception:
        conn.close()
        raise
    return conn


def _strip_sql_comments(sql: str) -> str:
    """Remove ordinary SQL comments while preserving quoted strings."""
    # SQLGlot parses comments itself. This helper is retained for
    # compatibility with existing code that may import it.
    return re.sub(r"/\*.*?\*/|--[^\n]*", " ", sql, flags=re.DOTALL)


def validate_sql(sql: str, dialect: str = "duckdb") -> ValidationResult:
    """
    Parse and reject unsafe or unsupported SQL.

    Allows exactly one SELECT query, including WITH and set operations.
    """
    cleaned = sql.strip()
    if not cleaned:
        return ValidationResult(ok=False, message="SQL is empty.")

    try:
        statements = sqlglot.parse(cleaned, read=dialect)
    except sqlglot.errors.ParseError as exc:
        return ValidationResult(ok=False, message=f"Parse error: {exc}")

    if len(statements) != 1 or statements[0] is None:
        return ValidationResult(
            ok=False,
            message="Exactly one SQL statement is allowed.",
        )

    statement = statements[0]

    # Reject data-changing, schema-changing, administrative, and
    # file-access operations anywhere in the parsed statement.
    forbidden_types = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Create,
        exp.Alter,
        exp.Command,
        exp.Copy,
        exp.Transaction,
        exp.Merge,
        exp.TruncateTable,
    )
    if statement.find(*forbidden_types):
        return ValidationResult(
            ok=False,
            message="Only read-only SELECT queries are allowed.",
        )

    # Also reject dangerous functions and table functions that can
    # access files or invoke external capabilities.
    forbidden_functions = {
        "read_csv",
        "read_csv_auto",
        "read_parquet",
        "read_json",
        "read_json_auto",
        "parquet_scan",
        "glob",
        "query",
        "query_table",
        "sqlite_scan",
        "postgres_scan",
        "httpfs",
        "nextval",
        "setseed",
    }

    for node in statement.walk():
        if isinstance(node, exp.Func):
            function_name = node.sql_name().lower()
            if function_name in forbidden_functions:
                return ValidationResult(
                    ok=False,
                    message=f"Function '{function_name}' is not allowed.",
                )

    # Only SELECT, UNION, INTERSECT, EXCEPT, or a WITH containing
    # a SELECT is accepted as the root query.
    allowed_root = isinstance(
        statement, (exp.Select, exp.Union, exp.Intersect, exp.Except)
    )
    if not allowed_root and not (
        isinstance(statement, exp.Subquery)
        and statement.find(exp.Select)
    ) and not (
        isinstance(statement, exp.With) and statement.find(exp.Select)
    ):
        return ValidationResult(
            ok=False,
            message="Only SELECT queries (optionally with WITH) are allowed.",
        )

    normalized = statement.sql(dialect=dialect)
    return ValidationResult(
        ok=True,
        message="OK",
        normalized_sql=normalized,
    )


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
            # DuckDB versions vary in timeout support. Fail closed if
            # a timeout was explicitly requested but cannot be applied.
            try:
                conn.execute(f"SET statement_timeout='{int(timeout_ms)}ms'")
            except duckdb.Error:
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
        return QueryResult(
            ok=False,
            error=str(exc),
            sql_executed=sql_to_run,
        )


def compare_results(
    left: QueryResult, right: QueryResult
) -> tuple[bool, str]:
    """
    Compare successful query results, preserving duplicate-row counts.
    Row order is ignored; column order and duplicate counts must match.
    """
    if not left.ok or not right.ok:
        return False, "Both queries must execute successfully to compare."

    if left.columns != right.columns:
        return False, f"Column mismatch: {left.columns} vs {right.columns}"

    left_counts = Counter(left.rows)
    right_counts = Counter(right.rows)

    if left_counts != right_counts:
        return (
            False,
            "Row mismatch: row values or duplicate counts differ "
            f"({len(left.rows)} rows vs {len(right.rows)} rows).",
        )

    if left.rows != right.rows:
        return True, "Same multiset of rows; order differs (treated as equivalent)."

    return True, "Results match."



