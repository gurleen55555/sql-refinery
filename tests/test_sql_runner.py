"""Tests for SQL validation, execution, and result comparison."""

from __future__ import annotations

from app.sql_runner import compare_results, execute_query, validate_sql


def test_validate_accepts_simple_select():
    result = validate_sql("SELECT customer_id, name FROM customers")
    assert result.ok
    assert result.normalized_sql is not None


def test_validate_rejects_empty_sql():
    result = validate_sql("   ")
    assert not result.ok


def test_validate_rejects_dml():
    result = validate_sql("DELETE FROM customers WHERE customer_id = 1")
    assert not result.ok


def test_validate_rejects_multiple_statements():
    result = validate_sql("SELECT 1; SELECT 2")
    assert not result.ok


def test_execute_valid_query(db_conn):
    result = execute_query(db_conn, "SELECT COUNT(*) FROM customers")
    assert result.ok
    assert result.rows == ((3,),)


def test_execute_invalid_query_returns_error(db_conn):
    result = execute_query(db_conn, "SELECT no_such_column FROM customers")
    assert not result.ok
    assert result.error


def test_execute_rejects_unsafe_sql_without_running(db_conn):
    result = execute_query(db_conn, "DROP TABLE customers")
    assert not result.ok
    assert "DROP" in (result.error or "").upper() or "Only" in (result.error or "")


def test_compare_results_match(db_conn):
    left = execute_query(
        db_conn,
        "SELECT customer_id FROM customers ORDER BY customer_id",
        validate=False,
    )
    right = execute_query(
        db_conn,
        "SELECT customer_id FROM customers ORDER BY customer_id",
        validate=False,
    )
    match, _ = compare_results(left, right)
    assert match


def test_compare_results_detect_mismatch(db_conn):
    left = execute_query(db_conn, "SELECT customer_id FROM customers", validate=False)
    right = execute_query(
        db_conn,
        "SELECT customer_id FROM customers WHERE customer_id = 1",
        validate=False,
    )
    match, detail = compare_results(left, right)
    assert not match
    assert "Row mismatch" in detail
