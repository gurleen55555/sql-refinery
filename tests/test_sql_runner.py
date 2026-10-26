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
    assert result.rows == ((10000,),)


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


def test_validate_rejects_insert():
    result = validate_sql(
        "INSERT INTO customers (customer_id, name) VALUES (4, 'Test')"
    )
    assert not result.ok


def test_validate_rejects_update():
    result = validate_sql(
        "UPDATE customers SET name = 'Changed' WHERE customer_id = 1"
    )
    assert not result.ok


def test_validate_rejects_drop_table():
    result = validate_sql("DROP TABLE customers")
    assert not result.ok


def test_validate_accepts_select_with_where():
    result = validate_sql(
        "SELECT customer_id, name FROM customers WHERE customer_id = 1"
    )
    assert result.ok
    assert result.normalized_sql is not None


def test_validate_accepts_forbidden_word_inside_string():
    result = validate_sql("SELECT 'update' AS message")
    assert result.ok


def test_validate_rejects_copy():
    result = validate_sql("COPY customers TO '/tmp/customers.csv'")
    assert not result.ok


def test_validate_rejects_attach():
    result = validate_sql("ATTACH ':memory:' AS other_db")
    assert not result.ok


def test_validate_rejects_install():
    result = validate_sql("INSTALL httpfs")
    assert not result.ok


def test_validate_rejects_load():
    result = validate_sql("LOAD httpfs")
    assert not result.ok
