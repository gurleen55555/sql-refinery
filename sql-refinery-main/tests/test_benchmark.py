"""Tests for local DuckDB benchmarking helpers."""

from __future__ import annotations

from app.benchmark import benchmark_query, compare_benchmarks


def test_benchmark_success_returns_timings(db_conn):
    result = benchmark_query(
        db_conn,
        "SELECT customer_id, name FROM customers",
        warmup_runs=0,
        timed_runs=2,
    )
    assert result.ok
    assert len(result.durations_ms) == 2
    assert result.median_ms is not None
    assert result.median_ms >= 0


def test_benchmark_invalid_sql_fails(db_conn):
    result = benchmark_query(db_conn, "SELECT bad_column FROM customers")
    assert not result.ok
    assert result.error


def test_compare_benchmarks_faster_candidate(db_conn):
    baseline = benchmark_query(
        db_conn,
        """
        SELECT c.name, o.amount
        FROM customers c
        JOIN orders o ON c.customer_id = o.customer_id
        """,
        warmup_runs=0,
        timed_runs=2,
    )
    candidate = benchmark_query(
        db_conn,
        "SELECT customer_id FROM customers",
        warmup_runs=0,
        timed_runs=2,
    )
    assert baseline.ok and candidate.ok
    faster, detail = compare_benchmarks(baseline, candidate)
    assert isinstance(faster, bool)
    assert detail
