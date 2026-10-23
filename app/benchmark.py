"""
Simple, repeatable DuckDB query timing for SQL-Refinery.

Benchmarks measure wall-clock time on the local DuckDB instance. A faster
benchmark does not prove production performance; it only compares queries on
this dataset and hardware.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

import duckdb

from app.sql_runner import ValidationResult, execute_query, validate_sql


@dataclass(frozen=True)
class BenchmarkResult:
    """Aggregated timing for one SQL statement."""

    ok: bool
    sql: str
    warmup_runs: int
    timed_runs: int
    durations_ms: tuple[float, ...] = ()
    median_ms: float | None = None
    mean_ms: float | None = None
    error: str | None = None


def benchmark_query(
    conn: duckdb.DuckDBPyConnection,
    sql: str,
    *,
    warmup_runs: int = 1,
    timed_runs: int = 3,
    validate: bool = True,
) -> BenchmarkResult:
    """
    Time query execution after optional warmup runs.

    Returns an error result if validation fails or every timed run fails.
    """
    validation = validate_sql(sql) if validate else ValidationResult(ok=True, message="OK", normalized_sql=sql)
    if not validation.ok:
        return BenchmarkResult(
            ok=False,
            sql=sql,
            warmup_runs=warmup_runs,
            timed_runs=timed_runs,
            error=validation.message,
        )

    sql_to_run = validation.normalized_sql or sql
    durations: list[float] = []

    for _ in range(max(0, warmup_runs)):
        result = execute_query(conn, sql_to_run, validate=False)
        if not result.ok:
            return BenchmarkResult(
                ok=False,
                sql=sql_to_run,
                warmup_runs=warmup_runs,
                timed_runs=timed_runs,
                error=result.error,
            )

    for _ in range(max(1, timed_runs)):
        start = time.perf_counter()
        result = execute_query(conn, sql_to_run, validate=False)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        if not result.ok:
            return BenchmarkResult(
                ok=False,
                sql=sql_to_run,
                warmup_runs=warmup_runs,
                timed_runs=timed_runs,
                error=result.error,
            )
        durations.append(elapsed_ms)

    return BenchmarkResult(
        ok=True,
        sql=sql_to_run,
        warmup_runs=warmup_runs,
        timed_runs=timed_runs,
        durations_ms=tuple(durations),
        median_ms=statistics.median(durations),
        mean_ms=statistics.mean(durations),
    )


def compare_benchmarks(
    baseline: BenchmarkResult,
    candidate: BenchmarkResult,
) -> tuple[bool, str]:
    """
    Report whether the candidate median is lower than the baseline median.

    Both benchmarks must have completed successfully.
    """
    if not baseline.ok or not candidate.ok:
        return False, "Both benchmarks must succeed before comparing speed."
    if baseline.median_ms is None or candidate.median_ms is None:
        return False, "Missing median timing data."

    if candidate.median_ms < baseline.median_ms:
        delta = baseline.median_ms - candidate.median_ms
        return True, f"Candidate median is lower by {delta:.3f} ms on this run."

    if candidate.median_ms > baseline.median_ms:
        delta = candidate.median_ms - baseline.median_ms
        return False, f"Candidate median is higher by {delta:.3f} ms on this run."

    return False, "Medians are equal on this run."
