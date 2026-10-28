
import io
import re
from datetime import datetime, timezone
from statistics import mean, median
from time import perf_counter
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import get_settings, llm_configured
from app.llm import suggest_sql_rewrite
from app.sql_runner import (
    create_connection,
    validate_sql,
    execute_query,
    compare_results,
)
from app.benchmark import benchmark_query


# ============================================================
# APPLICATION SETUP
# ============================================================

app = FastAPI(title="SQL-Refinery API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://sql-refinery-usra-eight.vercel.app",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

settings = get_settings()

# Shared DuckDB connection.
# Imported CSV tables remain available while this API process runs.
conn = create_connection(
    database=settings.duckdb_path,
    seed_demo=True,
)


# ============================================================
# REQUEST MODELS
# ============================================================

class RewriteRequest(BaseModel):
    sql: str


class CompareRequest(BaseModel):
    baselineSql: str
    candidateSql: str
    warmupRuns: int = Field(default=1, ge=0, le=10)
    timedRuns: int = Field(default=5, ge=1, le=20)


class BatchItem(BaseModel):
    originalSql: str
    rewrittenSql: str


class BatchCompareRequest(BaseModel):
    batchItems: list[BatchItem]
    warmupRuns: int = Field(default=1, ge=0, le=10)
    timedRuns: int = Field(default=5, ge=1, le=20)


# ============================================================
# SERIALIZATION HELPERS
# ============================================================

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_value(obj: Any, name: str, default=None):
    """Read a field from either a dictionary or a Python object."""
    if isinstance(obj, dict):
        return obj.get(name, default)

    return getattr(obj, name, default)


def validation_payload(result) -> dict:
    return {
        "ok": bool(get_value(result, "ok", False)),
        "message": str(
            get_value(result, "message", "Validation failed.")
        ),
    }


def result_payload(result, duration_ms=None):
    if result is None:
        return None

    columns = get_value(result, "columns", []) or []
    rows = get_value(result, "rows", []) or []

    return {
        "ok": bool(get_value(result, "ok", False)),
        "columns": [str(column) for column in columns],
        "rows": [list(row) for row in rows],
        "durationMs": duration_ms,
        "error": get_value(result, "error"),
    }


def benchmark_payload(result) -> dict:
    durations = [
        float(value)
        for value in (
            get_value(result, "durations_ms", []) or []
        )
    ]

    median_ms = get_value(result, "median_ms")
    mean_ms = get_value(result, "mean_ms")

    return {
        "ok": bool(get_value(result, "ok", False)),
        "durationsMs": durations,
        "medianMs": (
            float(median_ms)
            if median_ms is not None
            else (median(durations) if durations else 0.0)
        ),
        "meanMs": (
            float(mean_ms)
            if mean_ms is not None
            else (mean(durations) if durations else 0.0)
        ),
        "minMs": min(durations) if durations else None,
        "maxMs": max(durations) if durations else None,
        "warmupRuns": get_value(result, "warmup_runs", 1),
        "timedRuns": get_value(
            result, "timed_runs", len(durations)
        ),
        "error": get_value(result, "error"),
    }


def empty_report(error: str, stage: str = "execution") -> dict:
    return {
        "timestamp": now_iso(),
        "stage": stage,
        "error": error,
        "baselineValidation": None,
        "candidateValidation": None,
        "baselineResult": None,
        "candidateResult": None,
        "equivalent": None,
        "equivalenceMessage": None,
        "baselineBenchmark": None,
        "candidateBenchmark": None,
        "benchmarkComparison": None,
    }


# ============================================================
# BATCH BENCHMARK AGGREGATION
# ============================================================

def aggregate_batch_benchmarks(query_reports: list[dict]) -> dict:
    """
    Aggregate successful per-query benchmark timings into one batch
    benchmark report.

    Each aggregate timing represents the sum of the individual query
    timings for the corresponding timed run. This lets the frontend
    display an overall original-versus-rewritten comparison.
    """

    successful_reports = [
        item
        for item in query_reports
        if item.get("stage") == "complete"
        and item.get("equivalent") is True
        and item.get("baselineBenchmark")
        and item.get("candidateBenchmark")
        and item["baselineBenchmark"].get("ok")
        and item["candidateBenchmark"].get("ok")
    ]

    if not successful_reports:
        return {
            "baselineBenchmark": None,
            "candidateBenchmark": None,
            "benchmarkComparison": None,
        }

    baseline_runs = [
        item["baselineBenchmark"].get("durationsMs", [])
        for item in successful_reports
    ]

    candidate_runs = [
        item["candidateBenchmark"].get("durationsMs", [])
        for item in successful_reports
    ]

    # A batch timing is the sum of the per-query timings for each run.
    # Only combine run positions available for every included query.
    baseline_run_count = min(
        (len(values) for values in baseline_runs),
        default=0,
    )
    candidate_run_count = min(
        (len(values) for values in candidate_runs),
        default=0,
    )

    baseline_totals = [
        sum(float(values[index]) for values in baseline_runs)
        for index in range(baseline_run_count)
    ]

    candidate_totals = [
        sum(float(values[index]) for values in candidate_runs)
        for index in range(candidate_run_count)
    ]

    if not baseline_totals or not candidate_totals:
        return {
            "baselineBenchmark": None,
            "candidateBenchmark": None,
            "benchmarkComparison": None,
        }

    baseline_median = median(baseline_totals)
    candidate_median = median(candidate_totals)

    delta = baseline_median - candidate_median

    baseline_payload = {
        "ok": True,
        "durationsMs": baseline_totals,
        "medianMs": baseline_median,
        "meanMs": mean(baseline_totals),
        "minMs": min(baseline_totals),
        "maxMs": max(baseline_totals),
        "warmupRuns": successful_reports[0][
            "baselineBenchmark"
        ].get("warmupRuns", 1),
        "timedRuns": len(baseline_totals),
        "error": None,
    }

    candidate_payload = {
        "ok": True,
        "durationsMs": candidate_totals,
        "medianMs": candidate_median,
        "meanMs": mean(candidate_totals),
        "minMs": min(candidate_totals),
        "maxMs": max(candidate_totals),
        "warmupRuns": successful_reports[0][
            "candidateBenchmark"
        ].get("warmupRuns", 1),
        "timedRuns": len(candidate_totals),
        "error": None,
    }

    comparison_payload = {
        "faster": candidate_median < baseline_median,
        "deltaMs": abs(delta),
        "improvementPct": (
            (delta / baseline_median) * 100
            if baseline_median > 0
            else 0.0
        ),
        "speedupRatio": (
            baseline_median / candidate_median
            if candidate_median > 0
            else 0.0
        ),
        "message": (
            "Rewritten batch is faster."
            if candidate_median < baseline_median
            else (
                "Original and rewritten batch have equal median times."
                if candidate_median == baseline_median
                else "Rewritten batch is slower."
            )
        ),
    }

    return {
        "baselineBenchmark": baseline_payload,
        "candidateBenchmark": candidate_payload,
        "benchmarkComparison": comparison_payload,
    }


# ============================================================
# SQL COMPARISON
# ============================================================

def compare_one(
    baseline_sql: str,
    candidate_sql: str,
    warmup_runs: int,
    timed_runs: int,
) -> dict:

    report = {
        "timestamp": now_iso(),
        "stage": "validation",
        "error": None,
        "baselineValidation": None,
        "candidateValidation": None,
        "baselineResult": None,
        "candidateResult": None,
        "equivalent": None,
        "equivalenceMessage": "Execution has not completed.",
        "baselineBenchmark": None,
        "candidateBenchmark": None,
        "benchmarkComparison": None,
    }

    # 1. Validate both SQL statements.
    try:
        baseline_validation = validate_sql(baseline_sql)
        candidate_validation = validate_sql(candidate_sql)

        report["baselineValidation"] = validation_payload(
            baseline_validation
        )
        report["candidateValidation"] = validation_payload(
            candidate_validation
        )

    except Exception as exc:
        report["error"] = f"SQL validation failed: {exc}"
        return report

    if not get_value(baseline_validation, "ok", False):
        report["error"] = (
            "Baseline SQL is invalid: "
            + str(get_value(baseline_validation, "message", ""))
        )
        return report

    if not get_value(candidate_validation, "ok", False):
        report["error"] = (
            "Candidate SQL is invalid: "
            + str(get_value(candidate_validation, "message", ""))
        )
        return report

    # Use normalized SQL if the validator supplies it.
    baseline_sql = (
        get_value(baseline_validation, "normalized_sql")
        or baseline_sql
    )

    candidate_sql = (
        get_value(candidate_validation, "normalized_sql")
        or candidate_sql
    )

    # 2. Execute the original query.
    report["stage"] = "execution"

    start = perf_counter()
    baseline_result = execute_query(conn, baseline_sql)
    baseline_duration = (perf_counter() - start) * 1000

    report["baselineResult"] = result_payload(
        baseline_result,
        baseline_duration,
    )

    if not get_value(baseline_result, "ok", False):
        report["error"] = (
            "Baseline query failed: "
            + str(
                get_value(
                    baseline_result,
                    "error",
                    "Unknown error",
                )
            )
        )

        report["equivalenceMessage"] = (
            "Baseline query could not execute."
        )
        return report

    # 3. Execute the rewritten query.
    start = perf_counter()
    candidate_result = execute_query(conn, candidate_sql)
    candidate_duration = (perf_counter() - start) * 1000

    report["candidateResult"] = result_payload(
        candidate_result,
        candidate_duration,
    )

    if not get_value(candidate_result, "ok", False):
        report["error"] = (
            "Candidate query failed: "
            + str(
                get_value(
                    candidate_result,
                    "error",
                    "Unknown error",
                )
            )
        )

        report["equivalent"] = False
        report["equivalenceMessage"] = (
            "Candidate query could not execute."
        )
        return report

    # 4. Verify correctness before benchmarking.
    try:
        equivalent, message = compare_results(
            baseline_result,
            candidate_result,
        )
    except Exception as exc:
        report["error"] = f"Result comparison failed: {exc}"
        report["equivalenceMessage"] = (
            "The query results could not be compared."
        )
        return report

    report["equivalent"] = bool(equivalent)
    report["equivalenceMessage"] = str(message)

    if not equivalent:
        report["stage"] = "mismatch"
        report["error"] = (
            "The query results differ. Benchmarking was skipped."
        )
        return report

    # 5. Benchmark only equivalent queries.
    report["stage"] = "benchmark"

    try:
        baseline_benchmark = benchmark_query(
            conn,
            baseline_sql,
            warmup_runs=warmup_runs,
            timed_runs=timed_runs,
        )

        candidate_benchmark = benchmark_query(
            conn,
            candidate_sql,
            warmup_runs=warmup_runs,
            timed_runs=timed_runs,
        )

    except Exception as exc:
        report["error"] = f"Benchmarking failed: {exc}"
        return report

    report["baselineBenchmark"] = benchmark_payload(
        baseline_benchmark
    )

    report["candidateBenchmark"] = benchmark_payload(
        candidate_benchmark
    )

    if (
        not get_value(baseline_benchmark, "ok", False)
        or not get_value(candidate_benchmark, "ok", False)
    ):
        report["error"] = (
            get_value(baseline_benchmark, "error")
            or get_value(candidate_benchmark, "error")
            or "Benchmarking failed."
        )
        return report

    baseline_ms = get_value(baseline_benchmark, "median_ms")
    candidate_ms = get_value(candidate_benchmark, "median_ms")

    if baseline_ms is None or candidate_ms is None:
        report["error"] = "Benchmark timing data is missing."
        return report

    baseline_ms = float(baseline_ms)
    candidate_ms = float(candidate_ms)
    delta = baseline_ms - candidate_ms

    report["benchmarkComparison"] = {
        "faster": candidate_ms < baseline_ms,
        "deltaMs": abs(delta),
        "improvementPct": (
            (delta / baseline_ms) * 100
            if baseline_ms > 0
            else 0.0
        ),
        "speedupRatio": (
            baseline_ms / candidate_ms
            if candidate_ms > 0
            else 0.0
        ),
        "message": (
            "Candidate is faster."
            if candidate_ms < baseline_ms
            else (
                "Both queries have equal median times."
                if candidate_ms == baseline_ms
                else "Candidate is slower."
            )
        ),
    }

    report["stage"] = "complete"
    return report


# ============================================================
# API: STATUS
# ============================================================

@app.get("/api/status")
def status():
    current_settings = get_settings()

    try:
        table_rows = conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'main'
            """
        ).fetchall()

        table_count = len(table_rows)

    except Exception:
        table_count = 0

    return {
        "databaseReady": True,
        "aiConfigured": bool(
            llm_configured(current_settings)
        ),
        "aiProvider": current_settings.nebius_model,
        "stats": {
            "customTablesCount": table_count,
        },
    }


# ============================================================
# API: AI SQL REWRITE
# ============================================================

@app.post("/api/rewrite")
def rewrite(request: RewriteRequest):
    sql = request.sql.strip()

    if not sql:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "SQL cannot be empty.",
            },
        )

    try:
        result = suggest_sql_rewrite(sql)

        if not get_value(result, "ok", False):
            return {
                "ok": False,
                "error": str(
                    get_value(
                        result,
                        "error",
                        "AI rewrite failed.",
                    )
                ),
                "provider": get_value(result, "model"),
            }

        return {
            "ok": True,
            "optimized_sql": get_value(
                result, "optimized_sql", ""
            ),
            "rationale": get_value(result, "rationale", ""),
            "provider": get_value(result, "model"),
        }

    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": f"AI rewrite failed: {exc}",
            },
        )


# ============================================================
# API: SINGLE QUERY COMPARISON
# ============================================================

@app.post("/api/compare")
def compare(request: CompareRequest):
    if not request.baselineSql.strip():
        return empty_report("Baseline SQL cannot be empty.")

    if not request.candidateSql.strip():
        return empty_report("Candidate SQL cannot be empty.")

    try:
        return compare_one(
            request.baselineSql,
            request.candidateSql,
            request.warmupRuns,
            request.timedRuns,
        )

    except Exception as exc:
        return empty_report(
            f"Comparison failed: {exc}",
            stage="execution",
        )


# ============================================================
# API: BATCH COMPARISON
# ============================================================

@app.post("/api/batch-compare")
def batch_compare(request: BatchCompareRequest):
    if not request.batchItems:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "Please provide at least one SQL statement.",
            },
        )

    query_reports = []

    for index, item in enumerate(
        request.batchItems,
        start=1,
    ):
        original_sql = item.originalSql.strip()
        rewritten_sql = (
            item.rewrittenSql.strip() or original_sql
        )

        if not original_sql:
            one_report = empty_report(
                "Original SQL cannot be empty."
            )
        else:
            try:
                one_report = compare_one(
                    original_sql,
                    rewritten_sql,
                    request.warmupRuns,
                    request.timedRuns,
                )
            except Exception as exc:
                one_report = empty_report(
                    f"Comparison failed: {exc}"
                )

        query_reports.append(
            {
                "index": index,
                "originalSql": original_sql,
                "rewrittenSql": rewritten_sql,
                "equivalent": (
                    one_report.get("equivalent") is True
                ),
                "message": (
                    one_report.get("equivalenceMessage")
                    or one_report.get("error")
                    or "Comparison completed."
                ),
                "baselineResult": one_report.get(
                    "baselineResult"
                ),
                "candidateResult": one_report.get(
                    "candidateResult"
                ),
                "baselineBenchmark": one_report.get(
                    "baselineBenchmark"
                ),
                "candidateBenchmark": one_report.get(
                    "candidateBenchmark"
                ),
                "benchmarkComparison": one_report.get(
                    "benchmarkComparison"
                ),
                "stage": one_report.get("stage"),
                "error": one_report.get("error"),
            }
        )

    all_equivalent = bool(query_reports) and all(
        item["equivalent"] for item in query_reports
    )

    all_complete = bool(query_reports) and all(
        item["stage"] == "complete"
        for item in query_reports
    )

    all_baseline_valid = all(
        item.get("baselineResult") is not None
        and item["baselineResult"].get("ok", False)
        for item in query_reports
    )

    all_candidate_valid = all(
        item.get("candidateResult") is not None
        and item["candidateResult"].get("ok", False)
        for item in query_reports
    )

    # IMPORTANT:
    # The PerformanceReport component reads the three benchmark
    # fields from the top-level report. Populate them for batch mode.
    batch_benchmarks = aggregate_batch_benchmarks(
        query_reports
    )

    return {
        "timestamp": now_iso(),
        "stage": (
            "complete"
            if all_equivalent and all_complete
            else "mismatch"
            if any(
                item["stage"] == "mismatch"
                for item in query_reports
            )
            else "execution"
        ),
        "error": (
            None
            if all_equivalent and all_complete
            else (
                "One or more queries failed, differed, "
                "or could not be benchmarked."
            )
        ),
        "baselineValidation": {
            "ok": all_baseline_valid,
            "message": (
                "All original queries executed successfully."
                if all_baseline_valid
                else "One or more original queries failed."
            ),
        },
        "candidateValidation": {
            "ok": all_candidate_valid,
            "message": (
                "All rewritten queries executed successfully."
                if all_candidate_valid
                else "One or more rewritten queries failed."
            ),
        },
        "baselineResult": None,
        "candidateResult": None,
        "equivalent": all_equivalent,
        "equivalenceMessage": (
            "All query pairs returned equivalent results."
            if all_equivalent
            else "At least one query pair failed verification."
        ),

        # These were previously always None in batch mode.
        # They now contain aggregated timing information.
        "baselineBenchmark": batch_benchmarks[
            "baselineBenchmark"
        ],
        "candidateBenchmark": batch_benchmarks[
            "candidateBenchmark"
        ],
        "benchmarkComparison": batch_benchmarks[
            "benchmarkComparison"
        ],

        "batchMode": True,
        "queryReports": query_reports,
    }


# ============================================================
# API: CSV UPLOAD
# ============================================================

@app.post("/api/upload-csv")
async def upload_csv(
    csvFiles: list[UploadFile] = File(...),
):
    imported_tables = {}

    if not csvFiles:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "Please select at least one CSV file.",
            },
        )

    try:
        for file in csvFiles:
            filename = file.filename or "uploaded.csv"

            if not filename.lower().endswith(".csv"):
                return JSONResponse(
                    status_code=400,
                    content={
                        "ok": False,
                        "error": (
                            f"{filename} is not a CSV file."
                        ),
                    },
                )

            # Create a safe SQL table name from the filename.
            table_name = re.sub(
                r"[^A-Za-z0-9_]",
                "_",
                filename.rsplit(".", 1)[0],
            ).strip("_")

            if not table_name:
                table_name = "uploaded_table"

            if table_name[0].isdigit():
                table_name = f"table_{table_name}"

            content = await file.read()

            if not content:
                return JSONResponse(
                    status_code=400,
                    content={
                        "ok": False,
                        "error": f"{filename} is empty.",
                    },
                )

            try:
                dataframe = pd.read_csv(
                    io.BytesIO(content)
                )
            except Exception as exc:
                return JSONResponse(
                    status_code=400,
                    content={
                        "ok": False,
                        "error": (
                            f"Could not read {filename}: {exc}"
                        ),
                    },
                )

            if len(dataframe.columns) == 0:
                return JSONResponse(
                    status_code=400,
                    content={
                        "ok": False,
                        "error": (
                            f"{filename} has no columns."
                        ),
                    },
                )

            temp_name = f"_upload_temp_{table_name}"

            conn.register(temp_name, dataframe)

            quoted_table = (
                '"' + table_name.replace('"', '""') + '"'
            )
            quoted_temp = (
                '"' + temp_name.replace('"', '""') + '"'
            )

            try:
                conn.execute(
                    f"CREATE OR REPLACE TABLE {quoted_table} "
                    f"AS SELECT * FROM {quoted_temp}"
                )
            finally:
                conn.unregister(temp_name)

            imported_tables[table_name] = [
                str(column)
                for column in dataframe.columns
            ]

        return {
            "ok": True,
            "message": (
                f"Successfully imported "
                f"{len(imported_tables)} CSV table(s)."
            ),
            "importedTables": imported_tables,
        }

    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": f"CSV import failed: {exc}",
            },
        )
