"""
Streamlit entry point for SQL-Refinery.

Run locally:
    streamlit run app/main.py
"""

from __future__ import annotations

import streamlit as st

from app.benchmark import benchmark_query, compare_benchmarks
from app.config import get_settings, llm_configured
from app.llm import suggest_sql_rewrite
from app.sql_runner import compare_results, create_connection, execute_query, validate_sql

_DEFAULT_ORIGINAL = """
SELECT c.name, SUM(o.amount) AS total_spent
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
WHERE c.country = 'US'
GROUP BY c.name
ORDER BY total_spent DESC
""".strip()


def _render_header() -> None:
    st.set_page_config(page_title="SQL-Refinery", layout="wide")
    st.title("SQL-Refinery")
    st.caption(
        "Suggest SQL rewrites with Nemotron (Nebius Token Factory), then verify "
        "correctness and benchmark locally with DuckDB."
    )


def main() -> None:
    _render_header()
    settings = get_settings()

    with st.sidebar:
        st.subheader("Configuration")
        st.text(f"Model: {settings.nebius_model}")
        st.text(f"API base: {settings.nebius_base_url.rstrip('/')}")
        if llm_configured(settings):
            st.success("NEBIUS_API_KEY is set")
        else:
            st.warning("NEBIUS_API_KEY missing — LLM suggestions disabled")

    original_sql = st.text_area("Original SQL", value=_DEFAULT_ORIGINAL, height=180)
    col_run, col_llm = st.columns(2)

    optimized_sql = st.session_state.get("optimized_sql", "")

    with col_llm:
        if st.button("Suggest rewrite (Nemotron)", disabled=not llm_configured(settings)):
            with st.spinner("Calling Nebius Token Factory..."):
                suggestion = suggest_sql_rewrite(original_sql, settings=settings)
            if suggestion.ok and suggestion.optimized_sql:
                st.session_state["optimized_sql"] = suggestion.optimized_sql
                st.session_state["rationale"] = suggestion.rationale
                optimized_sql = suggestion.optimized_sql
                st.success(f"Received suggestion from {suggestion.model}")
            else:
                st.error(suggestion.error or "Unknown LLM error")

    optimized_sql = st.text_area(
        "Candidate SQL (editable)",
        value=optimized_sql or original_sql,
        height=180,
        key="optimized_sql_area",
    )

    rationale = st.session_state.get("rationale")
    if rationale:
        st.info(rationale)

    with col_run:
        run_checks = st.button("Validate, compare & benchmark")

    if run_checks:
        conn = create_connection(settings.duckdb_path)
        try:
            orig_validation = validate_sql(original_sql)
            cand_validation = validate_sql(optimized_sql)

            st.subheader("Validation")
            st.write(f"Original: {orig_validation.message}")
            st.write(f"Candidate: {cand_validation.message}")

            if not orig_validation.ok or not cand_validation.ok:
                st.stop()

            orig_result = execute_query(
                conn,
                original_sql,
                validate=False,
                timeout_ms=settings.sql_statement_timeout_ms,
            )
            cand_result = execute_query(
                conn,
                optimized_sql,
                validate=False,
                timeout_ms=settings.sql_statement_timeout_ms,
            )

            st.subheader("Correctness")
            if not orig_result.ok:
                st.error(f"Original failed: {orig_result.error}")
                st.stop()
            if not cand_result.ok:
                st.error(f"Candidate failed: {cand_result.error}")
                st.stop()

            match, detail = compare_results(orig_result, cand_result)
            if match:
                st.success(detail)
            else:
                st.error(detail)

            st.subheader("Benchmark (local DuckDB)")
            base_bench = benchmark_query(
                conn,
                original_sql,
                warmup_runs=settings.benchmark_warmup_runs,
                timed_runs=settings.benchmark_timed_runs,
                validate=False,
            )
            cand_bench = benchmark_query(
                conn,
                optimized_sql,
                warmup_runs=settings.benchmark_warmup_runs,
                timed_runs=settings.benchmark_timed_runs,
                validate=False,
            )

            if base_bench.ok:
                st.write(
                    f"Original median: {base_bench.median_ms:.3f} ms "
                    f"({base_bench.durations_ms})"
                )
            else:
                st.error(base_bench.error)

            if cand_bench.ok:
                st.write(
                    f"Candidate median: {cand_bench.median_ms:.3f} ms "
                    f"({cand_bench.durations_ms})"
                )
            else:
                st.error(cand_bench.error)

            faster = False
            if base_bench.ok and cand_bench.ok:
                faster, speed_detail = compare_benchmarks(base_bench, cand_bench)
                if faster:
                    st.success(speed_detail)
                else:
                    st.warning(speed_detail)

            if match and faster:
                st.success(
                    "On this demo dataset, the candidate matched results and had a "
                    "lower median time. Re-run tests on your machine to confirm."
                )
            elif match:
                st.info(
                    "Results match on this dataset; speedup was not observed in this run."
                )
        finally:
            conn.close()


if __name__ == "__main__":
    main()
