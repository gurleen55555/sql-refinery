from __future__ import annotations

import html
import time
import sys
from pathlib import Path
from typing import Any

import streamlit as st

# Fix Python imports when deployed on Streamlit Cloud
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.batch import (
    DEFAULT_BATCH_LIMIT,
    MAX_BATCH_LIMIT,
    enforce_batch_limit,
    split_sql_queries,
)

from app.benchmark import (
    benchmark_batch,
    benchmark_query,
    compare_benchmarks,
)

from app.config import llm_configured
from app.llm import suggest_sql_rewrite
from app.sql_runner import (
    compare_results,
    create_connection,
    execute_query,
    import_csv_tables,
    validate_sql,
)

from app.ui.components import (
    inject_custom_theme,
    render_glass_metric,
    render_hero_3d,
    render_nav_bar,
)


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Nemotron SQL Lab | SQL-Refinery",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# DESIGN SYSTEM — DARK FROSTED GLASS WITH ACCENT GLOWS
# ============================================================

GREEN = "#3DFF8A"
GREEN_DARK = "#128243"
GREEN_LIGHT = "rgba(61, 255, 138, 0.15)"
GREEN_PALE = "rgba(61, 255, 138, 0.08)"
TEXT = "#F1F3F9"
MUTED = "#9BA3B8"
BORDER = "rgba(255, 255, 255, 0.08)"
WHITE = "#FFFFFF"
CANVAS = "#0B0B0D"
RED = "#EF4444"
AMBER = "#FF7A2F"

# Inject external custom CSS stylesheet
inject_custom_theme()


# ============================================================
# DEFAULT QUERY AND SESSION STATE
# ============================================================

DEFAULT_SQL = """SELECT
    c.name,
    SUM(o.amount) AS total_spent
FROM customers c
JOIN orders o
    ON c.customer_id = o.customer_id
WHERE c.country = 'US'
GROUP BY c.name
ORDER BY total_spent DESC;"""


def initialize_state() -> None:
    """Set initial values without overwriting edits during reruns."""
    defaults = {
        "baseline_sql": DEFAULT_SQL,
        "candidate_sql": DEFAULT_SQL,
        "comparison": None,
        "last_ai_error": None,
        "last_ai_message": None,
        "benchmark_runs": 5,
        "warmup_runs": 1,
        "batch_sql": "",
        "batch_rewrites": [],
        "batch_comparisons": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize_state()


# ============================================================
# EDITOR HELPER
# ============================================================

def sql_editor(
    label: str,
    state_key: str,
    editor_key: str,
    height: int = 360,
) -> str:
    """
    Use Ace when installed; otherwise fall back to a normal text area.
    The returned value is always a string.
    """
    current_value = st.session_state.get(state_key, DEFAULT_SQL)

    try:
        from streamlit_ace import st_ace

        edited_value = st_ace(
            value=current_value,
            language="sql",
            theme="tomorrow_night",
            key=editor_key,
            height=height,
            font_size=13,
            tab_size=4,
            show_gutter=True,
            show_print_margin=False,
            wrap=False,
            auto_update=True,
            min_lines=12,
            annotations=None,
            markers=None,
        )

        if isinstance(edited_value, str):
            st.session_state[state_key] = edited_value
            return edited_value

        return current_value

    except ImportError:
        st.caption(
            "Install `streamlit-ace` for syntax highlighting and line numbers."
        )
        edited_value = st.text_area(
            label,
            value=current_value,
            height=height,
            key=f"{editor_key}_fallback",
            label_visibility="collapsed",
        )
        st.session_state[state_key] = edited_value
        return edited_value


# ============================================================
# HELPERS
# ============================================================

def safe_attr(value: Any, attribute: str, default: Any = None) -> Any:
    """Safely read an attribute from a backend result object."""
    return getattr(value, attribute, default)


def format_ms(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):,.2f} ms"
    except (TypeError, ValueError):
        return "—"


def render_metric(
    label: str,
    value: str,
    footnote: str = "",
    value_class: str = "",
) -> None:
    css_class = f"f-metric-value {value_class}".strip()
    st.markdown(
        f"""
        <div class="frosted-metric-card">
            <div class="f-metric-label">{html.escape(label)}</div>
            <div class="{css_class}">{html.escape(value)}</div>
            <div class="metric-footnote" style="color:#9BA3B8; font-size:11px; margin-top:4px;">{html.escape(footnote)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_step(number: str, title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="step-label" style="display:flex; align-items:center; gap:10px; margin: 1.5rem 0 0.8rem 0;">
            <div class="card-icon-pill orange" style="width:28px; height:28px; font-size:12px;">{html.escape(number)}</div>
            <div>
                <div style="font-size:16px; font-weight:700; color:#FFFFFF;">{html.escape(title)}</div>
                <div style="font-size:12px; color:#9BA3B8;">{html.escape(subtitle)}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def result_to_dataframe(result: Any):
    """Convert a QueryResult into a dataframe without assuming extra fields."""
    import pandas as pd

    columns = list(safe_attr(result, "columns", ()) or ())
    rows = list(safe_attr(result, "rows", ()) or ())

    if not columns:
        return pd.DataFrame(rows)

    return pd.DataFrame(rows, columns=columns)


def show_query_result(title: str, result: Any) -> None:
    if not safe_attr(result, "ok", False):
        st.error(
            f"{title}: {safe_attr(result, 'error', 'Query execution failed.')}"
        )
        return

    frame = result_to_dataframe(result)
    st.caption(f"{len(frame):,} row(s) · {len(frame.columns):,} column(s)")
    st.dataframe(frame, use_container_width=True, hide_index=True)

    csv_data = frame.to_csv(index=False).encode("utf-8")
    st.download_button(
        label=f"Download {title} as CSV",
        data=csv_data,
        file_name=f"{title.lower().replace(' ', '_')}.csv",
        mime="text/csv",
        key=f"download_{title.lower().replace(' ', '_')}",
        use_container_width=False,
    )


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.markdown(
        """
        <div class="brand" style="display:flex; align-items:center; gap:12px; margin-bottom:1rem;">
            <div class="brand-mark" style="width:40px; height:40px; border-radius:10px; background:rgba(255,122,47,0.15); color:#FF7A2F; display:flex; align-items:center; justify-content:center; font-size:20px; font-weight:700; border:1px solid rgba(255,122,47,0.35); box-shadow:0 0 14px rgba(255,122,47,0.25);">⚡</div>
            <div>
                <div class="brand-name" style="font-size:17px; font-weight:700; color:#FFFFFF; line-height:1.2;">Nemotron SQL Lab</div>
                <div class="brand-subtitle" style="font-size:11px; color:#9BA3B8;">SQL Refinery Studio</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    st.markdown("#### Workspace")
    st.caption("Edit, validate, and compare SQL queries.")

    st.markdown("#### Database")

    database_mode = st.radio(
        "Choose data source",
        options=["Demo database", "Upload CSV files"],
        index=0,
        key="database_mode",
        help="Use the built-in sample data or import your own CSV tables.",
    )

    if database_mode == "Upload CSV files":
        uploaded_files = st.file_uploader(
            "Upload CSV files",
            type=["csv"],
            accept_multiple_files=True,
            key="csv_uploads",
            help=(
                "Each CSV becomes a table named after its filename. "
                "For example, customers.csv becomes customers."
            ),
        )

        if uploaded_files:
            upload_signature = tuple(
                (file.name, file.size) for file in uploaded_files
            )

            if st.session_state.get("csv_upload_signature") != upload_signature:
                custom_conn = None

                old_conn = st.session_state.get("custom_db_connection")
                if old_conn is not None:
                    try:
                        old_conn.close()
                    except Exception:
                        pass

                try:
                    custom_conn = create_connection(seed_demo=False)
                    imported_tables = import_csv_tables(
                        custom_conn,
                        uploaded_files,
                    )

                    st.session_state["custom_db_connection"] = custom_conn
                    st.session_state["custom_db_tables"] = imported_tables
                    st.session_state["csv_upload_signature"] = upload_signature
                    st.session_state["comparison"] = None

                except Exception as exc:
                    if custom_conn is not None:
                        try:
                            custom_conn.close()
                        except Exception:
                            pass

                    st.session_state["custom_db_connection"] = None
                    st.session_state["custom_db_tables"] = {}
                    st.session_state["csv_upload_signature"] = None
                    st.error(f"CSV import failed: {exc}")

        imported_tables = st.session_state.get("custom_db_tables", {})

        if imported_tables:
            st.success(f"{len(imported_tables)} table(s) imported")

            for table_name, columns in imported_tables.items():
                with st.expander(f"Table: {table_name}"):
                    st.caption("Columns")
                    st.write(", ".join(columns))
        else:
            st.info("Upload one or more CSV files to create your database.")

    st.markdown("#### Benchmark settings")

    warmup_runs = st.selectbox(
        "Warmup executions",
        options=[0, 1, 2, 3],
        help="Warmup executions are excluded from the recorded timings.",
        key="warmup_runs",
    )

    timed_runs = st.select_slider(
        "Timed executions",
        options=[3, 5, 7, 10],
        help="More executions can make median timings more stable.",
        key="benchmark_runs",
    )

    st.markdown(
        """
        <div style="
            padding: 12px;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 10px;
            background: rgba(16, 20, 28, 0.85);
            margin-top: 10px;
        ">
            <div style="font-size:12px;font-weight:700;color:#FFFFFF;">
                Benchmark methodology
            </div>
            <div style="
                font-size:11px;
                line-height:1.6;
                color:#9BA3B8;
                margin-top:6px;
            ">
                Queries run locally on DuckDB. Compare median execution
                times under the same session and sample database.
                Results can vary with caching and machine load.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    ai_ready = False
    try:
        ai_ready = bool(llm_configured())
    except Exception:
        ai_ready = False

    st.markdown("#### AI connection")

    if ai_ready:
        st.success("AI configuration detected", icon="✅")
        st.caption("Nemotron/Nebius settings appear configured.")
    else:
        st.warning("AI configuration not detected", icon="⚠️")
        st.caption(
            "Check your environment configuration and API credentials."
        )

    st.divider()

    if st.button("Reset workspace", use_container_width=True):
        st.session_state["baseline_sql"] = DEFAULT_SQL
        st.session_state["candidate_sql"] = DEFAULT_SQL
        st.session_state["comparison"] = None
        st.session_state["last_ai_error"] = None
        st.session_state["last_ai_message"] = None

        # Change editor keys to force a fresh Ace component instance.
        st.session_state["baseline_editor_version"] = (
            st.session_state.get("baseline_editor_version", 0) + 1
        )
        st.session_state["candidate_editor_version"] = (
            st.session_state.get("candidate_editor_version", 0) + 1
        )
        st.rerun()

    st.markdown(
        """
        <div style="
            padding-top: 18px;
            font-size: 11px;
            line-height: 1.7;
            color: #5E667E;
        ">
            Nemotron SQL Lab<br>
            AI-assisted SQL optimization<br>
            Built with Streamlit + DuckDB
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# PAGE HEADER & 3D HERO SCENE
# ============================================================

ai_ready = False
try:
    ai_ready = bool(llm_configured())
except Exception:
    pass

# Determine 3D Refinery Machine State
refinery_state = "idle"
if st.session_state.get("comparison") and safe_attr(st.session_state["comparison"], "stage") == "complete":
    refinery_state = "done"
elif st.session_state.get("batch_rewrites"):
    refinery_state = "done"

# 1. Top Glass Nav Bar
render_nav_bar(ai_ready=ai_ready)

# 2. 3D Hero Scene with machine conveyor & live state
render_hero_3d(state=refinery_state)


# ============================================================
# THREE FROSTED-GLASS CARDS IN A ROW
# ============================================================

col_input, col_refined, col_stats = st.columns([1.1, 1.1, 1.0], gap="medium")


# ------------------------------------------------------------
# CARD 1: INPUT QUERY (CODE EDITOR LOOK)
# ------------------------------------------------------------
with col_input:
    st.markdown(
        """
        <div class="glass-card-header">
            <div class="card-title-group">
                <div class="card-icon-pill orange">01</div>
                <div>
                    <div class="card-title">Input Query</div>
                    <div style="font-size:11px; color:#9BA3B8;">Enter SQL statement(s) to optimize</div>
                </div>
            </div>
            <div class="card-badge">Raw SQL</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    batch_limit = st.number_input(
        "Maximum queries to process",
        min_value=1,
        max_value=MAX_BATCH_LIMIT,
        value=DEFAULT_BATCH_LIMIT,
        step=1,
        key="batch_limit",
        help="Controls how many SQL statements can be processed at once.",
    )

    baseline_version = st.session_state.get("baseline_editor_version", 0)

    baseline_sql = sql_editor(
        "SQL queries",
        "baseline_sql",
        f"baseline_editor_{baseline_version}",
        height=380,
    )

    st.caption(
        "Separate multiple statements with semicolons. Single queries work too."
    )

    # Primary Action Buttons
    action_btn_col1, action_btn_col2 = st.columns([1.2, 1], gap="small")

    with action_btn_col1:
        ai_clicked = st.button(
            "✦  Refine",
            type="primary",
            use_container_width=True,
            disabled=not ai_ready,
            help="Generate an optimized SQL rewrite using NVIDIA Nemotron.",
        )

    with action_btn_col2:
        compare_clicked = st.button(
            "▶  Run comparison",
            type="secondary",
            use_container_width=True,
            help="Validate correctness and benchmark execution time against DuckDB.",
        )

    if st.button("Clear results", use_container_width=True):
        st.session_state["comparison"] = None
        st.session_state["last_ai_error"] = None
        st.session_state["last_ai_message"] = None
        st.rerun()

    if not ai_ready:
        st.caption(
            "AI rewriting is disabled until the Nemotron/Nebius configuration "
            "is available. You can still validate and benchmark SQL locally."
        )


# ============================================================
# AI REWRITE EXECUTION (BACKEND LOGIC — UNTOUCHED)
# ============================================================

if ai_clicked:
    raw_sql = st.session_state.get("baseline_sql", "").strip()

    if not raw_sql:
        st.session_state["last_ai_error"] = (
            "Enter at least one SQL query first."
        )
        st.session_state["last_ai_message"] = None

    else:
        try:
            # Split the editor contents into individual SQL statements.
            queries = split_sql_queries(raw_sql)

            if not queries:
                raise ValueError("No SQL statements were found.")

            # Enforce the configurable batch limit.
            queries = enforce_batch_limit(
                queries,
                int(batch_limit),
            )

            rewrites = []

            with st.spinner(
                f"Generating AI rewrites for {len(queries)} query(s)..."
            ):
                progress = st.progress(0)
                status = st.empty()

                for index, original_sql in enumerate(queries, start=1):
                    status.write(
                        f"Rewriting query {index} of {len(queries)}..."
                    )

                    try:
                        rewrite = suggest_sql_rewrite(original_sql)

                        if isinstance(rewrite, str):
                            rewritten_sql = rewrite.strip()
                            rationale = None
                            rewrite_error = None
                        else:
                            rewritten_sql = (
                                safe_attr(rewrite, "optimized_sql")
                                or safe_attr(rewrite, "sql")
                                or safe_attr(rewrite, "rewritten_sql")
                                or safe_attr(rewrite, "suggestion")
                                or ""
                            )

                            rationale = safe_attr(rewrite, "rationale")
                            rewrite_error = safe_attr(rewrite, "error")

                            if not isinstance(rewritten_sql, str):
                                rewritten_sql = ""

                            rewritten_sql = rewritten_sql.strip()

                        if not rewritten_sql:
                            raise ValueError(
                                str(rewrite_error)
                                if rewrite_error
                                else "Nemotron returned an empty SQL rewrite."
                            )

                        rewrites.append({
                            "index": index,
                            "original_sql": original_sql,
                            "rewritten_sql": rewritten_sql,
                            "rationale": rationale,
                            "error": None,
                        })

                    except Exception as exc:
                        # Keep processing the remaining queries.
                        rewrites.append({
                            "index": index,
                            "original_sql": original_sql,
                            "rewritten_sql": "",
                            "rationale": None,
                            "error": str(exc),
                        })

                    progress.progress(index / len(queries))

                status.empty()
                progress.empty()

            # Save results without changing the original editor contents.
            st.session_state["batch_sql"] = raw_sql
            st.session_state["batch_rewrites"] = rewrites
            st.session_state["batch_comparisons"] = []
            st.session_state["comparison"] = None

            succeeded = sum(
                1 for item in rewrites if not item["error"]
            )
            failed = len(rewrites) - succeeded

            st.session_state["last_ai_error"] = None
            st.session_state["last_ai_message"] = (
                f"Processed {len(rewrites)} query(s): "
                f"{succeeded} rewrite(s) succeeded, "
                f"{failed} failed."
            )

            st.rerun()

        except Exception as exc:
            st.session_state["last_ai_error"] = str(exc)
            st.session_state["last_ai_message"] = None


# ------------------------------------------------------------
# CARD 2: REFINED QUERY OUTPUT WITH COPY BUTTON
# ------------------------------------------------------------
with col_refined:
    st.markdown(
        """
        <div class="glass-card-header">
            <div class="card-title-group">
                <div class="card-icon-pill green">02</div>
                <div>
                    <div class="card-title">Refined Query</div>
                    <div style="font-size:11px; color:#9BA3B8;">Nemotron AI proposed optimization</div>
                </div>
            </div>
            <div class="card-badge active-green">Optimized</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.get("last_ai_message"):
        st.success(st.session_state["last_ai_message"])

    if st.session_state.get("last_ai_error"):
        st.error(f"AI rewrite failed: {st.session_state['last_ai_error']}")

    batch_rewrites = st.session_state.get("batch_rewrites", [])

    if batch_rewrites:
        for item in batch_rewrites:
            if len(batch_rewrites) > 1:
                st.caption(f"Statement {item['index']} of {len(batch_rewrites)}")

            if item["error"]:
                st.error(f"Rewrite failed: {item['error']}")
            else:
                # Code block with built-in Streamlit 1-click copy button
                st.code(item["rewritten_sql"], language="sql")

                if item["rationale"]:
                    with st.expander("Optimization rationale", expanded=True):
                        st.markdown(
                            f"<div style='color:#C2CADB; font-size:12px; line-height:1.6;'>{html.escape(item['rationale'])}</div>",
                            unsafe_allow_html=True,
                        )
    else:
        # Shimmer skeleton / waiting placeholder
        st.markdown(
            """
            <div style="background: rgba(14, 17, 24, 0.7); border: 1px dashed rgba(255,255,255,0.1); border-radius: 14px; padding: 42px 20px; text-align: center; margin-bottom: 12px;">
                <div style="font-size: 28px; margin-bottom: 8px;">✦</div>
                <div style="font-size: 15px; font-weight: 700; color: #FFFFFF; margin-bottom: 6px;">Ready for Refinement</div>
                <div style="font-size: 12px; color: #8C96AB; line-height: 1.6; max-width: 320px; margin: 0 auto 16px auto;">
                    Click <b>Refine</b> to propose an AI-assisted SQL rewrite using NVIDIA Nemotron.
                </div>
                <div class="skeleton-shimmer" style="height: 12px; width: 75%; margin: 8px auto;"></div>
                <div class="skeleton-shimmer" style="height: 12px; width: 55%; margin: 8px auto;"></div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ============================================================
# VALIDATION AND BENCHMARKING ENGINE (BACKEND LOGIC — UNTOUCHED)
# ============================================================

def run_comparison(
    baseline_query: str,
    candidate_query: str,
    warmups: int,
    repetitions: int,
) -> dict[str, Any]:
    """
    Validate and execute both queries.
    Do not benchmark if either query fails or results differ.
    """
    report: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "baseline_validation": None,
        "candidate_validation": None,
        "baseline_result": None,
        "candidate_result": None,
        "equivalent": None,
        "equivalence_message": None,
        "baseline_benchmark": None,
        "candidate_benchmark": None,
        "benchmark_comparison": None,
        "stage": "validation",
        "error": None,
    }

    # First validate both statements.
    try:
        baseline_validation = validate_sql(baseline_query)
        candidate_validation = validate_sql(candidate_query)

        report["baseline_validation"] = baseline_validation
        report["candidate_validation"] = candidate_validation

    except Exception as exc:
        report["error"] = f"SQL validation failed: {exc}"
        return report

    if not safe_attr(report["baseline_validation"], "ok", False):
        report["error"] = (
            "Baseline SQL is invalid: "
            + str(
                safe_attr(
                    report["baseline_validation"],
                    "message",
                    "Unknown validation error.",
                )
            )
        )
        return report

    if not safe_attr(report["candidate_validation"], "ok", False):
        report["error"] = (
            "Candidate SQL is invalid: "
            + str(
                safe_attr(
                    report["candidate_validation"],
                    "message",
                    "Unknown validation error.",
                )
            )
        )
        return report

    report["stage"] = "execution"

    # Use the uploaded CSV database or the built-in demo database.
    custom_mode = (
        st.session_state.get("database_mode") == "Upload CSV files"
    )

    conn = None
    owns_connection = False

    try:
        if custom_mode:
            conn = st.session_state.get("custom_db_connection")

            if conn is None:
                report["error"] = (
                    "Upload at least one CSV file before comparing queries."
                )
                return report
        else:
            conn = create_connection()
            owns_connection = True

        baseline_result = execute_query(conn, baseline_query)
        report["baseline_result"] = baseline_result

        if not safe_attr(baseline_result, "ok", False):
            report["error"] = (
                "Baseline execution failed: "
                + str(
                    safe_attr(
                        baseline_result,
                        "error",
                        "Unknown execution error.",
                    )
                )
            )
            return report

        candidate_result = execute_query(conn, candidate_query)
        report["candidate_result"] = candidate_result

        if not safe_attr(candidate_result, "ok", False):
            report["error"] = (
                "Candidate execution failed: "
                + str(
                    safe_attr(
                        candidate_result,
                        "error",
                        "Unknown execution error.",
                    )
                )
            )
            return report

        # Correctness comes before performance.
        equivalent, equivalence_message = compare_results(
            baseline_result,
            candidate_result,
        )

        report["equivalent"] = equivalent
        report["equivalence_message"] = equivalence_message

        if not equivalent:
            report["stage"] = "mismatch"
            report["error"] = (
                "The queries returned different results. Benchmarking was "
                "skipped because correctness must be established first."
            )
            return report

        report["stage"] = "benchmark"

        baseline_benchmark = benchmark_query(
            conn,
            baseline_query,
            warmup_runs=warmups,
            timed_runs=repetitions,
        )
        report["baseline_benchmark"] = baseline_benchmark

        if not safe_attr(baseline_benchmark, "ok", False):
            report["error"] = (
                "Baseline benchmark failed: "
                + str(
                    safe_attr(
                        baseline_benchmark,
                        "error",
                        "Unknown benchmark error.",
                    )
                )
            )
            return report

        candidate_benchmark = benchmark_query(
            conn,
            candidate_query,
            warmup_runs=warmups,
            timed_runs=repetitions,
        )
        report["candidate_benchmark"] = candidate_benchmark

        if not safe_attr(candidate_benchmark, "ok", False):
            report["error"] = (
                "Candidate benchmark failed: "
                + str(
                    safe_attr(
                        candidate_benchmark,
                        "error",
                        "Unknown benchmark error.",
                    )
                )
            )
            return report

        report["benchmark_comparison"] = compare_benchmarks(
            baseline_benchmark,
            candidate_benchmark,
        )
        report["stage"] = "complete"

        return report

    except Exception as exc:
        report["error"] = f"Comparison failed: {exc}"
        return report

    finally:
        if owns_connection and conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def run_batch_comparison(
    original_queries: list[str],
    rewrites: list[dict[str, Any]],
    warmups: int,
    repetitions: int,
) -> dict[str, Any]:
    """Validate, compare, and benchmark an entire batch of SQL rewrites."""
    report: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stage": "validation",
        "error": None,
        "equivalent": None,
        "equivalence_message": None,
        "baseline_validation": None,
        "candidate_validation": None,
        "baseline_result": None,
        "candidate_result": None,
        "baseline_benchmark": None,
        "candidate_benchmark": None,
        "benchmark_comparison": None,
        "query_reports": [],
        "batch_mode": True,
    }

    if not original_queries:
        report["error"] = "Enter at least one SQL query."
        return report

    if len(original_queries) != len(rewrites):
        report["error"] = (
            "The number of original queries does not match the number "
            "of AI rewrites. Generate the rewrites again."
        )
        return report

    for index, (original, item) in enumerate(
        zip(original_queries, rewrites), start=1
    ):
        if item.get("error") or not item.get("rewritten_sql", "").strip():
            report["error"] = (
                f"Query {index} has no valid AI rewrite. "
                "Generate the missing rewrite before comparing."
            )
            return report

        original_validation = validate_sql(original)
        candidate_sql = item["rewritten_sql"].strip()
        candidate_validation = validate_sql(candidate_sql)

        if index == 1:
            report["baseline_validation"] = original_validation
            report["candidate_validation"] = candidate_validation

        if not safe_attr(original_validation, "ok", False):
            report["error"] = (
                f"Original query {index} is invalid: "
                f"{safe_attr(original_validation, 'message', 'Validation failed.')}"
            )
            return report

        if not safe_attr(candidate_validation, "ok", False):
            report["error"] = (
                f"Rewritten query {index} is invalid: "
                f"{safe_attr(candidate_validation, 'message', 'Validation failed.')}"
            )
            return report

    report["stage"] = "execution"

    custom_mode = (
        st.session_state.get("database_mode") == "Upload CSV files"
    )
    conn = None
    owns_connection = False

    try:
        if custom_mode:
            conn = st.session_state.get("custom_db_connection")
            if conn is None:
                report["error"] = (
                    "Upload at least one CSV file before comparing queries."
                )
                return report
        else:
            conn = create_connection()
            owns_connection = True

        candidate_queries = [
            item["rewritten_sql"].strip() for item in rewrites
        ]

        all_equivalent = True

        for index, (original, candidate) in enumerate(
            zip(original_queries, candidate_queries), start=1
        ):
            baseline_result = execute_query(conn, original)
            if not safe_attr(baseline_result, "ok", False):
                report["error"] = (
                    f"Original query {index} failed: "
                    f"{safe_attr(baseline_result, 'error', 'Execution failed.')}"
                )
                return report

            candidate_result = execute_query(conn, candidate)
            if not safe_attr(candidate_result, "ok", False):
                report["error"] = (
                    f"Rewritten query {index} failed: "
                    f"{safe_attr(candidate_result, 'error', 'Execution failed.')}"
                )
                return report

            equivalent, message = compare_results(
                baseline_result, candidate_result
            )

            report["query_reports"].append({
                "index": index,
                "original_sql": original,
                "rewritten_sql": candidate,
                "equivalent": equivalent,
                "message": message,
                "baseline_result": baseline_result,
                "candidate_result": candidate_result,
            })

            if not equivalent:
                all_equivalent = False

        report["equivalent"] = all_equivalent
        report["equivalence_message"] = (
            f"All {len(original_queries)} query pair(s) returned equivalent results."
            if all_equivalent
            else "At least one query pair returned different results."
        )

        # Keep representative result objects for compatibility with the
        # existing dashboard. The complete results remain in query_reports.
        if report["query_reports"]:
            first = report["query_reports"][0]
            report["baseline_result"] = first["baseline_result"]
            report["candidate_result"] = first["candidate_result"]

        if not all_equivalent:
            report["stage"] = "mismatch"
            report["error"] = (
                "Batch benchmarking was skipped because at least one "
                "original/rewrite pair returned different results."
            )
            return report

        report["stage"] = "benchmark"

        baseline_benchmark = benchmark_batch(
            conn,
            original_queries,
            warmup_runs=warmups,
            timed_runs=repetitions,
        )
        report["baseline_benchmark"] = baseline_benchmark

        if not safe_attr(baseline_benchmark, "ok", False):
            report["error"] = (
                "Original batch benchmark failed: "
                f"{safe_attr(baseline_benchmark, 'error', 'Unknown error.')}"
            )
            return report

        candidate_benchmark = benchmark_batch(
            conn,
            candidate_queries,
            warmup_runs=warmups,
            timed_runs=repetitions,
        )
        report["candidate_benchmark"] = candidate_benchmark

        if not safe_attr(candidate_benchmark, "ok", False):
            report["error"] = (
                "Rewritten batch benchmark failed: "
                f"{safe_attr(candidate_benchmark, 'error', 'Unknown error.')}"
            )
            return report

        report["benchmark_comparison"] = compare_benchmarks(
            baseline_benchmark, candidate_benchmark
        )
        report["stage"] = "complete"
        return report

    except Exception as exc:
        report["error"] = f"Batch comparison failed: {exc}"
        return report

    finally:
        if owns_connection and conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# Execution of Comparison Trigger
if compare_clicked:
    raw_sql = st.session_state.get("baseline_sql", "").strip()
    rewrites = st.session_state.get("batch_rewrites", [])

    if not raw_sql:
        st.session_state["last_ai_error"] = (
            "Enter at least one SQL query before comparing."
        )
        st.rerun()

    try:
        original_queries = split_sql_queries(raw_sql)
        enforce_batch_limit(
            original_queries,
            int(st.session_state.get("batch_limit", DEFAULT_BATCH_LIMIT)),
        )
    except ValueError as exc:
        st.session_state["last_ai_error"] = str(exc)
        st.rerun()

    if not rewrites:
        st.session_state["last_ai_error"] = (
            "Generate AI rewrites before running the comparison."
        )
        st.rerun()

    with st.spinner(
        "Validating queries, comparing results, and benchmarking..."
    ):
        st.session_state["comparison"] = run_batch_comparison(
            original_queries,
            rewrites,
            int(warmup_runs),
            int(timed_runs),
        )

    st.session_state["last_ai_error"] = None
    st.rerun()


# ------------------------------------------------------------
# CARD 3: STATS / DIFF PANEL (BEFORE VS AFTER, IMPROVEMENTS)
# ------------------------------------------------------------
with col_stats:
    st.markdown(
        """
        <div class="glass-card-header">
            <div class="card-title-group">
                <div class="card-icon-pill">03</div>
                <div>
                    <div class="card-title">Stats & Diff</div>
                    <div style="font-size:11px; color:#9BA3B8;">Equivalence check & speedup</div>
                </div>
            </div>
            <div class="card-badge">Measured</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    report = st.session_state.get("comparison")

    if not report:
        st.markdown(
            """
            <div style="background: rgba(14, 17, 24, 0.7); border: 1px dashed rgba(255,255,255,0.1); border-radius: 14px; padding: 42px 20px; text-align: center; margin-bottom: 12px;">
                <div style="font-size: 28px; margin-bottom: 8px;">📊</div>
                <div style="font-size: 15px; font-weight: 700; color: #FFFFFF; margin-bottom: 6px;">Awaiting Verification</div>
                <div style="font-size: 12px; color: #8C96AB; line-height: 1.6; max-width: 320px; margin: 0 auto 16px auto;">
                    Select <b>Run comparison</b> to validate correctness and benchmark execution time against DuckDB.
                </div>
                <div class="skeleton-shimmer" style="height: 12px; width: 70%; margin: 8px auto;"></div>
                <div class="skeleton-shimmer" style="height: 12px; width: 50%; margin: 8px auto;"></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        stage = report.get("stage")
        error = report.get("error")
        batch_mode = report.get("batch_mode", False)

        # Equivalence Chip
        if report.get("equivalent") is True:
            st.success("✔ Exact result equivalence verified", icon="🟢")
        elif report.get("equivalent") is False:
            st.error("✖ Result sets differ — benchmark skipped", icon="🔴")
        else:
            st.info("Validation in progress...")

        baseline_benchmark = report.get("baseline_benchmark")
        candidate_benchmark = report.get("candidate_benchmark")

        benchmarks_ready = (
            report.get("stage") == "complete"
            and safe_attr(baseline_benchmark, "ok", False)
            and safe_attr(candidate_benchmark, "ok", False)
        )

        if benchmarks_ready:
            baseline_ms = safe_attr(baseline_benchmark, "median_ms")
            candidate_ms = safe_attr(candidate_benchmark, "median_ms")

            improvement_pct = None
            if (
                baseline_ms is not None
                and candidate_ms is not None
                and float(baseline_ms) > 0
            ):
                improvement_pct = (
                    (float(baseline_ms) - float(candidate_ms))
                    / float(baseline_ms)
                ) * 100

            speedup = None
            if (
                baseline_ms is not None
                and candidate_ms is not None
                and float(candidate_ms) > 0
            ):
                speedup = float(baseline_ms) / float(candidate_ms)

            # Metrics cards
            stat_c1, stat_c2 = st.columns(2)
            with stat_c1:
                st.metric(
                    label="Original median",
                    value=format_ms(baseline_ms),
                )
            with stat_c2:
                st.metric(
                    label="Refined median",
                    value=format_ms(candidate_ms),
                )

            if improvement_pct is not None and speedup is not None:
                st.metric(
                    label="Speedup Ratio",
                    value=f"{speedup:.2f}×",
                    delta=f"{improvement_pct:+.1f}% faster" if improvement_pct >= 0 else f"{improvement_pct:+.1f}%",
                    delta_color="normal",
                )

            # Visual Bar Comparison
            import pandas as pd
            chart_df = pd.DataFrame(
                {
                    "Query": [
                        "Original batch" if batch_mode else "Baseline",
                        "Rewritten batch" if batch_mode else "Refined",
                    ],
                    "Median execution time (ms)": [
                        float(baseline_ms),
                        float(candidate_ms),
                    ],
                }
            ).set_index("Query")

            st.bar_chart(
                chart_df,
                use_container_width=True,
                color=AMBER,
            )
        elif error:
            st.error(error)


# ============================================================
# DETAILED PERFORMANCE & DATA INSPECTION (BELOW 3-CARD HERO)
# ============================================================

report = st.session_state.get("comparison")

if report:
    st.markdown('<div class="divider" style="height:1px; background:rgba(255,255,255,0.08); margin:2rem 0;"></div>', unsafe_allow_html=True)
    
    render_step(
        "04",
        "Deep Performance Analysis",
        "Inspect execution timings, individual runs, and result set verification.",
    )

    stage = report.get("stage")
    error = report.get("error")
    batch_mode = report.get("batch_mode", False)

    # Validation Status Breakdown
    st.markdown("#### Validation status")
    validation_col1, validation_col2, validation_col3 = st.columns(3)

    baseline_validation = report.get("baseline_validation")
    candidate_validation = report.get("candidate_validation")

    with validation_col1:
        if safe_attr(baseline_validation, "ok", False):
            st.success("Original batch valid" if batch_mode else "Baseline SQL valid")
        elif baseline_validation is not None:
            st.error(
                ("Original batch invalid: " if batch_mode else "Baseline SQL invalid: ")
                + str(safe_attr(baseline_validation, "message", "Invalid"))
            )
        else:
            st.info("Original batch validation pending" if batch_mode else "Baseline validation pending")

    with validation_col2:
        if safe_attr(candidate_validation, "ok", False):
            st.success("Rewritten batch valid" if batch_mode else "Candidate SQL valid")
        elif candidate_validation is not None:
            st.error(
                ("Rewritten batch invalid: " if batch_mode else "Candidate SQL invalid: ")
                + str(safe_attr(candidate_validation, "message", "Invalid"))
            )
        else:
            st.info("Rewritten batch validation pending" if batch_mode else "Candidate validation pending")

    with validation_col3:
        if report.get("equivalent") is True:
            st.success("Batch results are equivalent" if batch_mode else "Results are equivalent")
        elif report.get("equivalent") is False:
            st.error("Batch results differ" if batch_mode else "Results differ")
        else:
            st.info("Result equivalence pending")

    if report.get("equivalence_message"):
        st.caption(str(report["equivalence_message"]))

    # Individual Timings & Result Sets
    baseline_benchmark = report.get("baseline_benchmark")
    candidate_benchmark = report.get("candidate_benchmark")

    benchmarks_ready = (
        report.get("stage") == "complete"
        and safe_attr(baseline_benchmark, "ok", False)
        and safe_attr(candidate_benchmark, "ok", False)
    )

    if benchmarks_ready:
        with st.expander("View individual benchmark timings", expanded=False):
            timing_col1, timing_col2 = st.columns(2)

            with timing_col1:
                st.markdown("**Baseline timings**")
                baseline_durations = list(
                    safe_attr(baseline_benchmark, "durations_ms", ()) or ()
                )
                if baseline_durations:
                    st.dataframe(
                        {
                            "Run": list(range(1, len(baseline_durations) + 1)),
                            "Time (ms)": baseline_durations,
                        },
                        hide_index=True,
                        use_container_width=True,
                    )
                else:
                    st.caption("No individual timings returned.")

            with timing_col2:
                st.markdown("**Candidate timings**")
                candidate_durations = list(
                    safe_attr(candidate_benchmark, "durations_ms", ()) or ()
                )
                if candidate_durations:
                    st.dataframe(
                        {
                            "Run": list(range(1, len(candidate_durations) + 1)),
                            "Time (ms)": candidate_durations,
                        },
                        hide_index=True,
                        use_container_width=True,
                    )
                else:
                    st.caption("No individual timings returned.")

        # Query Result Tables
        st.markdown("#### Query results")
        results_col1, results_col2 = st.columns(2, gap="large")

        with results_col1:
            with st.expander("Baseline result set", expanded=False):
                show_query_result(
                    "Baseline results",
                    report["baseline_result"],
                )

        with results_col2:
            with st.expander("Candidate result set", expanded=False):
                show_query_result(
                    "Candidate results",
                    report["candidate_result"],
                )

        # Benchmark comparison message
        benchmark_comparison = report.get("benchmark_comparison")
        if isinstance(benchmark_comparison, tuple) and len(benchmark_comparison) >= 2:
            comparison_ok, comparison_message = benchmark_comparison[:2]
            if comparison_ok:
                st.success(str(comparison_message))
            else:
                st.info(str(comparison_message))

        # Download Report
        baseline_ms = safe_attr(baseline_benchmark, "median_ms")
        candidate_ms = safe_attr(candidate_benchmark, "median_ms")
        improvement_pct = None
        if (
            baseline_ms is not None
            and candidate_ms is not None
            and float(baseline_ms) > 0
        ):
            improvement_pct = (
                (float(baseline_ms) - float(candidate_ms))
                / float(baseline_ms)
            ) * 100

        report_lines = [
            "Nemotron SQL Lab / SQL-Refinery Performance Report",
            f"Generated: {report.get('timestamp', 'Unknown')}",
            "",
            f"Results equivalent: {report.get('equivalent')}",
            f"Equivalence details: {report.get('equivalence_message')}",
            f"Baseline median (ms): {baseline_ms}",
            f"Candidate median (ms): {candidate_ms}",
            f"Performance change (%): {improvement_pct}",
            "",
            "ORIGINAL SQL BATCH",
            st.session_state.get("baseline_sql", ""),
            "",
            "AI REWRITES",
            "\n\n".join(
                item.get("rewritten_sql", "")
                for item in st.session_state.get("batch_rewrites", [])
            ),
        ]

        st.download_button(
            "Download performance report",
            data="\n".join(report_lines),
            file_name="nemotron_sql_refinery_report.txt",
            mime="text/plain",
            use_container_width=False,
        )


# ============================================================
# FOOTER
# ============================================================

st.markdown(
    """
    <div class="footer" style="border-top: 1px solid rgba(255,255,255,0.08); margin-top: 40px; padding-top: 16px; color: #5E667E; font-size: 11px; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
        <span>Nemotron SQL Lab · SQL-Refinery</span>
        <span>AI proposes. DuckDB validates. Latency measurements decide.</span>
    </div>
    """,
    unsafe_allow_html=True,
)
