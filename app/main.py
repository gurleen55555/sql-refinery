
from __future__ import annotations

import html
import time
from typing import Any

import streamlit as st

from app.benchmark import benchmark_query, compare_benchmarks
from app.config import llm_configured
from app.llm import suggest_sql_rewrite
from app.sql_runner import (
    compare_results,
    create_connection,
    execute_query,
    import_csv_tables,
    validate_sql,
)


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="SQL-Refinery | Query Performance Studio",
    page_icon="🟢",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# DESIGN SYSTEM — WHITE + GREEN ANALYTICS DASHBOARD
# ============================================================

GREEN = "#16845B"
GREEN_DARK = "#116747"
GREEN_LIGHT = "#E8F5EE"
GREEN_PALE = "#F4FAF6"
TEXT = "#172B24"
MUTED = "#687871"
BORDER = "#E1E9E4"
WHITE = "#FFFFFF"
CANVAS = "#F7F9F8"
RED = "#C63D45"
AMBER = "#A56A13"

st.markdown(
    f"""
    <style>
    @import url(
        'https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap'
    );

    :root {{
        --green: {GREEN};
        --green-dark: {GREEN_DARK};
        --green-light: {GREEN_LIGHT};
        --text: {TEXT};
        --muted: {MUTED};
        --border: {BORDER};
        --white: {WHITE};
        --canvas: {CANVAS};
    }}

    html, body, [class*="css"] {{
        font-family: 'DM Sans', -apple-system, BlinkMacSystemFont,
                     'Segoe UI', sans-serif;
        color: var(--text);
    }}

    .stApp {{
        background: var(--canvas);
    }}

    [data-testid="stHeader"] {{
        background: rgba(247, 249, 248, 0.96);
        border-bottom: 1px solid var(--border);
    }}

    [data-testid="stAppViewContainer"] > .main {{
        background: var(--canvas);
    }}

    .block-container {{
        max-width: 1600px;
        padding: 1.5rem 2.1rem 3rem 2.1rem;
    }}

    [data-testid="stSidebar"] {{
        background: #FFFFFF;
        border-right: 1px solid var(--border);
    }}

    [data-testid="stSidebar"] > div:first-child {{
        padding-top: 1.4rem;
    }}

    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{
        color: var(--muted);
        font-size: 0.9rem;
    }}

    h1, h2, h3 {{
        color: var(--text) !important;
        letter-spacing: -0.035em;
    }}

    h1 {{
        font-weight: 700 !important;
    }}

    h2, h3 {{
        font-weight: 650 !important;
    }}

    p, label {{
        color: var(--text);
    }}

    .brand {{
        display: flex;
        align-items: center;
        gap: 11px;
        margin-bottom: 1.1rem;
    }}

    .brand-mark {{
        display: flex;
        align-items: center;
        justify-content: center;
        width: 42px;
        height: 42px;
        border-radius: 12px;
        background: var(--green-light);
        color: var(--green-dark);
        font-size: 23px;
        font-weight: 700;
        border: 1px solid #D1E9DA;
    }}

    .brand-name {{
        font-size: 19px;
        font-weight: 700;
        color: var(--text);
        line-height: 1.25;
        letter-spacing: -0.5px;
    }}

    .brand-subtitle {{
        font-size: 11px;
        color: var(--muted);
        margin-top: 3px;
    }}

    .topline {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 14px;
        flex-wrap: wrap;
        margin: 0.2rem 0 1.5rem 0;
    }}

    .eyebrow {{
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        color: var(--green);
        margin-bottom: 7px;
    }}

    .page-heading {{
        font-size: clamp(27px, 3vw, 37px);
        line-height: 1.18;
        font-weight: 700;
        letter-spacing: -1.4px;
        color: var(--text);
        margin: 0;
    }}

    .page-description {{
        color: var(--muted);
        font-size: 14px;
        line-height: 1.65;
        margin-top: 9px;
        max-width: 680px;
    }}

    .status-pill {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: #FFFFFF;
        border: 1px solid var(--border);
        border-radius: 999px;
        padding: 9px 13px;
        font-size: 12px;
        font-weight: 600;
        color: var(--text);
        white-space: nowrap;
    }}

    .status-dot {{
        width: 8px;
        height: 8px;
        background: #20A46A;
        border-radius: 50%;
        display: inline-block;
    }}

    .section-heading {{
        font-size: 17px;
        font-weight: 700;
        letter-spacing: -0.35px;
        color: var(--text);
        margin: 0;
    }}

    .section-caption {{
        color: var(--muted);
        font-size: 12px;
        margin-top: 5px;
        line-height: 1.5;
    }}

    .editor-heading {{
        display: flex;
        align-items: center;
        gap: 9px;
        margin-bottom: 5px;
    }}

    .editor-icon {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 31px;
        height: 31px;
        border-radius: 9px;
        background: var(--green-light);
        color: var(--green-dark);
        font-weight: 700;
        font-size: 14px;
        flex-shrink: 0;
    }}

    .editor-icon.neutral {{
        background: #F0F3F1;
        color: #526159;
    }}

    .editor-title {{
        color: var(--text);
        font-size: 15px;
        font-weight: 700;
    }}

    .editor-description {{
        color: var(--muted);
        font-size: 11px;
        margin-top: 2px;
    }}

    .panel {{
        background: #FFFFFF;
        border: 1px solid var(--border);
        border-radius: 13px;
        padding: 17px 18px;
        margin-bottom: 12px;
    }}

    .metric-label {{
        color: var(--muted);
        font-size: 12px;
        font-weight: 600;
        margin-bottom: 9px;
    }}

    .metric-value {{
        font-size: 26px;
        font-weight: 700;
        color: var(--text);
        letter-spacing: -0.8px;
        line-height: 1.2;
    }}

    .metric-footnote {{
        color: var(--muted);
        font-size: 11px;
        margin-top: 8px;
        line-height: 1.4;
    }}

    .metric-positive {{
        color: var(--green);
    }}

    .metric-negative {{
        color: {RED};
    }}

    .divider {{
        height: 1px;
        background: var(--border);
        margin: 20px 0;
    }}

    .step-label {{
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 1.8rem 0 1rem 0;
    }}

    .step-number {{
        display: flex;
        align-items: center;
        justify-content: center;
        width: 29px;
        height: 29px;
        border-radius: 9px;
        background: var(--green-light);
        color: var(--green-dark);
        font-weight: 700;
        font-size: 13px;
    }}

    .step-title {{
        font-size: 17px;
        font-weight: 700;
        color: var(--text);
    }}

    .step-subtitle {{
        font-size: 12px;
        color: var(--muted);
        margin-top: 3px;
    }}

    .small-label {{
        font-size: 11px;
        color: var(--muted);
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.8px;
    }}

    .empty-state {{
        text-align: center;
        padding: 30px 15px;
        border: 1px dashed #D3DFD7;
        border-radius: 12px;
        background: #FFFFFF;
    }}

    .empty-icon {{
        font-size: 27px;
        margin-bottom: 8px;
    }}

    .empty-title {{
        font-size: 15px;
        font-weight: 700;
        color: var(--text);
    }}

    .empty-description {{
        font-size: 12px;
        color: var(--muted);
        margin-top: 6px;
        line-height: 1.6;
    }}

    .footer {{
        border-top: 1px solid var(--border);
        margin-top: 35px;
        padding-top: 16px;
        color: var(--muted);
        font-size: 11px;
        display: flex;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 8px;
    }}

    /* Buttons */

    .stButton > button,
    .stDownloadButton > button {{
        border-radius: 9px;
        min-height: 40px;
        font-weight: 600;
        font-size: 13px;
        border: 1px solid var(--border);
        transition: all 0.15s ease;
    }}

    .stButton > button[kind="primary"] {{
        background: var(--green);
        color: white;
        border: 1px solid var(--green);
    }}

    .stButton > button[kind="primary"]:hover {{
        background: var(--green-dark);
        border-color: var(--green-dark);
        color: white;
    }}

    .stButton > button[kind="secondary"]:hover,
    .stDownloadButton > button:hover {{
        border-color: var(--green);
        color: var(--green-dark);
        background: var(--green-pale);
    }}

    /* Inputs */

    [data-testid="stTextArea"] textarea {{
        background: #FFFFFF;
        border: 1px solid var(--border);
        border-radius: 9px;
        font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
        font-size: 12px;
        line-height: 1.6;
    }}

    [data-testid="stTextArea"] textarea:focus {{
        border-color: var(--green);
        box-shadow: 0 0 0 1px var(--green);
    }}

    [data-testid="stSelectbox"] > div > div {{
        border-radius: 8px;
        border-color: var(--border);
    }}

    [data-testid="stMetric"] {{
        background: #FFFFFF;
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 16px;
    }}

    [data-testid="stMetricLabel"] {{
        color: var(--muted);
        font-size: 12px;
    }}

    [data-testid="stMetricValue"] {{
        color: var(--text);
        font-weight: 700;
    }}

    [data-testid="stDataFrame"] {{
        border: 1px solid var(--border);
        border-radius: 10px;
        overflow: hidden;
    }}

    [data-testid="stExpander"] {{
        background: #FFFFFF;
        border: 1px solid var(--border);
        border-radius: 10px;
    }}

    div[data-testid="stAlert"] {{
        border-radius: 10px;
    }}

    code {{
        color: var(--green-dark);
    }}

    @media (max-width: 800px) {{
        .block-container {{
            padding: 1rem 1rem 2rem 1rem;
        }}
        .page-heading {{
            font-size: 28px;
        }}
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


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
            theme="chrome",
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
    css_class = f"metric-value {value_class}".strip()
    st.markdown(
        f"""
        <div class="panel">
            <div class="metric-label">{html.escape(label)}</div>
            <div class="{css_class}">{html.escape(value)}</div>
            <div class="metric-footnote">{html.escape(footnote)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_step(number: str, title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="step-label">
            <div class="step-number">{html.escape(number)}</div>
            <div>
                <div class="step-title">{html.escape(title)}</div>
                <div class="step-subtitle">{html.escape(subtitle)}</div>
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
        <div class="brand">
            <div class="brand-mark">↗</div>
            <div>
                <div class="brand-name">SQL-Refinery</div>
                <div class="brand-subtitle">Query Performance Studio</div>
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
        index=1,
        help="Warmup executions are excluded from the recorded timings.",
        key="warmup_runs",
    )

    timed_runs = st.select_slider(
        "Timed executions",
        options=[3, 5, 7, 10],
        value=5,
        help="More executions can make median timings more stable.",
        key="benchmark_runs",
    )

    st.markdown(
        """
        <div style="
            padding: 12px;
            border: 1px solid #E1E9E4;
            border-radius: 10px;
            background: #F7F9F8;
            margin-top: 10px;
        ">
            <div style="font-size:12px;font-weight:700;color:#172B24;">
                Benchmark methodology
            </div>
            <div style="
                font-size:11px;
                line-height:1.6;
                color:#687871;
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
        st.warning("AI configuration not detected", icon="!")
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
            color: #89958F;
        ">
            SQL-Refinery<br>
            AI-assisted SQL optimization<br>
            Built with Streamlit + DuckDB
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# PAGE HEADER
# ============================================================

ai_ready = False
try:
    ai_ready = bool(llm_configured())
except Exception:
    pass

st.markdown(
    f"""
    <div class="topline">
        <div>
            <div class="eyebrow">QUERY ANALYTICS / WORKSPACE</div>
            <div class="page-heading">SQL Performance Studio</div>
            <div class="page-description">
                Refine your SQL. Validate correctness. Measure performance.
                All from one clean workspace.
            </div>
        </div>
        <div class="status-pill">
            <span class="status-dot"
                  style="background:{'#20A46A' if ai_ready else '#D69E2E'}">
            </span>
            {"AI configured" if ai_ready else "AI not configured"}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# STEP 1 — SQL EDITORS
# ============================================================

render_step(
    "01",
    "Query workspace",
    "Compare your original query with a candidate optimization.",
)

left_col, right_col = st.columns(2, gap="large")

baseline_version = st.session_state.get("baseline_editor_version", 0)
candidate_version = st.session_state.get("candidate_editor_version", 0)

with left_col:
    st.markdown(
        """
        <div class="editor-heading">
            <div class="editor-icon neutral">01</div>
            <div>
                <div class="editor-title">Baseline query</div>
                <div class="editor-description">
                    Original SQL · Reference implementation
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    baseline_sql = sql_editor(
        "Baseline SQL",
        "baseline_sql",
        f"baseline_editor_{baseline_version}",
    )

    if st.button(
        "Copy baseline to candidate",
        key="copy_baseline",
        use_container_width=True,
    ):
        st.session_state["candidate_sql"] = baseline_sql
        st.session_state["candidate_editor_version"] = candidate_version + 1
        st.rerun()

with right_col:
    st.markdown(
        """
        <div class="editor-heading">
            <div class="editor-icon">02</div>
            <div>
                <div class="editor-title">Candidate query</div>
                <div class="editor-description">
                    Optimized SQL · Compare against the baseline
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    candidate_sql = sql_editor(
        "Candidate SQL",
        "candidate_sql",
        f"candidate_editor_{candidate_version}",
    )

    if st.button(
        "Reset candidate to baseline",
        key="reset_candidate",
        use_container_width=True,
    ):
        st.session_state["candidate_sql"] = baseline_sql
        st.session_state["candidate_editor_version"] = candidate_version + 1
        st.session_state["comparison"] = None
        st.rerun()


# ============================================================
# STEP 2 — ACTIONS
# ============================================================

render_step(
    "02",
    "Analyze and optimize",
    "Generate an AI rewrite or run the validation and performance workflow.",
)

action_col1, action_col2, action_col3 = st.columns(
    [1.15, 1.15, 1],
    gap="medium",
)

with action_col1:
    ai_clicked = st.button(
        "✦  Generate AI rewrite",
        type="secondary",
        use_container_width=True,
        disabled=not ai_ready,
    )

with action_col2:
    compare_clicked = st.button(
        "▶  Run comparison",
        type="primary",
        use_container_width=True,
    )

with action_col3:
    if st.button(
        "Clear results",
        use_container_width=True,
    ):
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
# AI REWRITE
# ============================================================

if ai_clicked:
    baseline_sql = st.session_state.get("baseline_sql", "").strip()

    if not baseline_sql:
        st.session_state["last_ai_error"] = (
            "Enter a baseline SQL query first."
        )
        st.session_state["last_ai_message"] = None
    else:
        try:
            with st.spinner("Asking Nemotron to suggest a SQL rewrite..."):
                rewrite = suggest_sql_rewrite(baseline_sql)

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
                        else "Nemotron returned no SQL. Check app/llm.py."
                    )

            if not rewritten_sql:
                raise ValueError("The AI returned an empty SQL rewrite.")

            st.session_state["candidate_sql"] = rewritten_sql
            st.session_state["candidate_editor_version"] = (
                st.session_state.get("candidate_editor_version", 0) + 1
            )
            st.session_state["last_ai_error"] = None
            st.session_state["last_ai_message"] = (
                "AI rewrite generated successfully. Review the candidate "
                "SQL before running the comparison."
            )
            st.session_state["last_ai_rationale"] = rationale

            st.rerun()

        except Exception as exc:
            st.session_state["last_ai_error"] = str(exc)
            st.session_state["last_ai_message"] = None


if st.session_state.get("last_ai_message"):
    st.success(st.session_state["last_ai_message"])

if st.session_state.get("last_ai_error"):
    st.error(f"AI rewrite failed: {st.session_state['last_ai_error']}")

if st.session_state.get("last_ai_rationale"):
    with st.expander("View AI optimization rationale"):
        st.write(st.session_state["last_ai_rationale"])

    


# ============================================================
# STEP 3 — VALIDATION AND BENCHMARK
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



if compare_clicked:
    baseline_sql = st.session_state.get("baseline_sql", "").strip()
    candidate_sql = st.session_state.get("candidate_sql", "").strip()

    if not baseline_sql:
        st.error("Please enter a baseline SQL query.")
    elif not candidate_sql:
        st.error("Please enter a candidate SQL query.")
    else:
        with st.spinner(
            "Validating queries, checking results, and benchmarking..."
        ):
            st.session_state["comparison"] = run_comparison(
                baseline_sql,
                candidate_sql,
                int(warmup_runs),
                int(timed_runs),
            )

        st.rerun()


# ============================================================
# STEP 4 — RESULTS DASHBOARD
# ============================================================

report = st.session_state.get("comparison")

render_step(
    "03",
    "Performance report",
    "Inspect correctness, execution timings, and the benchmark comparison.",
)

if not report:
    st.markdown(
        """
        <div class="empty-state">
            <div class="empty-icon">📊</div>
            <div class="empty-title">Your performance report will appear here</div>
            <div class="empty-description">
                Enter your SQL queries above and select
                <b>Run comparison</b> to validate correctness and measure
                execution time.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

else:
    stage = report.get("stage")
    error = report.get("error")

    # --------------------------------------------------------
    # Validation status
    # --------------------------------------------------------

    st.markdown("#### Validation and correctness")

    validation_col1, validation_col2, validation_col3 = st.columns(3)

    baseline_validation = report.get("baseline_validation")
    candidate_validation = report.get("candidate_validation")

    with validation_col1:
        if safe_attr(baseline_validation, "ok", False):
            st.success("Baseline SQL valid")
        elif baseline_validation is not None:
            st.error(
                "Baseline SQL invalid: "
                + str(safe_attr(baseline_validation, "message", "Invalid"))
            )
        else:
            st.info("Baseline validation pending")

    with validation_col2:
        if safe_attr(candidate_validation, "ok", False):
            st.success("Candidate SQL valid")
        elif candidate_validation is not None:
            st.error(
                "Candidate SQL invalid: "
                + str(safe_attr(candidate_validation, "message", "Invalid"))
            )
        else:
            st.info("Candidate validation pending")

    with validation_col3:
        if report.get("equivalent") is True:
            st.success("Results are equivalent")
        elif report.get("equivalent") is False:
            st.error("Results differ")
        else:
            st.info("Result equivalence pending")

    if report.get("equivalence_message"):
        st.caption(str(report["equivalence_message"]))

    if error:
        if stage == "mismatch":
            st.warning(error)
        else:
            st.error(error)

    # --------------------------------------------------------
    # Metrics and chart only when both benchmarks succeeded
    # --------------------------------------------------------

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

        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
        st.markdown("#### Performance overview")

        metric1, metric2, metric3, metric4 = st.columns(4, gap="medium")

        with metric1:
            st.metric(
                label="Baseline median",
                value=format_ms(baseline_ms),
                help="Median time across recorded baseline executions.",
            )

        with metric2:
            st.metric(
                label="Candidate median",
                value=format_ms(candidate_ms),
                help="Median time across recorded candidate executions.",
            )

        with metric3:
            if improvement_pct is None:
                st.metric(label="Performance change", value="—")
            else:
                st.metric(
                    label="Performance change",
                    value=f"{improvement_pct:+.2f}%",
                    delta=f"{improvement_pct:+.2f}% vs baseline",
                    delta_color="normal",
                    help=(
                        "Positive means the candidate ran faster; "
                        "negative means it ran slower."
                    ),
                )

        with metric4:
            if (
                baseline_ms is not None
                and candidate_ms is not None
                and float(candidate_ms) > 0
            ):
                speedup = float(baseline_ms) / float(candidate_ms)
                st.metric(
                    label="Speedup ratio",
                    value=f"{speedup:.2f}×",
                    help="Baseline median divided by candidate median.",
                )
            else:
                st.metric(label="Speedup ratio", value="—")

        if improvement_pct is not None:
            if improvement_pct > 0:
                st.success(
                    f"The candidate was {improvement_pct:.2f}% faster "
                    "by median execution time in this benchmark."
                )
            elif improvement_pct < 0:
                st.warning(
                    f"The candidate was {abs(improvement_pct):.2f}% slower "
                    "by median execution time in this benchmark."
                )
            else:
                st.info("Both queries have the same median execution time.")

        # Chart data
        st.markdown("#### Execution time comparison")

        import pandas as pd

        chart_df = pd.DataFrame(
            {
                "Query": ["Baseline", "Candidate"],
                "Median execution time (ms)": [
                    float(baseline_ms),
                    float(candidate_ms),
                ],
            }
        ).set_index("Query")

        st.bar_chart(
            chart_df,
            use_container_width=True,
            color=GREEN,
        )

        st.caption(
            f"Recorded {safe_attr(baseline_benchmark, 'timed_runs', timed_runs)} "
            "timed execution(s) per query. Lower is better. Results are "
            "specific to this local DuckDB session and sample dataset."
        )

        with st.expander("View individual benchmark timings"):
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

        # ----------------------------------------------------
        # Result tables
        # ----------------------------------------------------

        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
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

        # ----------------------------------------------------
        # Benchmark comparison message
        # ----------------------------------------------------

        benchmark_comparison = report.get("benchmark_comparison")

        if isinstance(benchmark_comparison, tuple) and len(benchmark_comparison) >= 2:
            comparison_ok, comparison_message = benchmark_comparison[:2]
            if comparison_ok:
                st.success(str(comparison_message))
            else:
                st.info(str(comparison_message))

        # ----------------------------------------------------
        # Export report
        # ----------------------------------------------------

        report_lines = [
            "SQL-Refinery Performance Report",
            f"Generated: {report.get('timestamp', 'Unknown')}",
            "",
            f"Results equivalent: {report.get('equivalent')}",
            f"Equivalence details: {report.get('equivalence_message')}",
            f"Baseline median (ms): {baseline_ms}",
            f"Candidate median (ms): {candidate_ms}",
            f"Performance change (%): {improvement_pct}",
            "",
            "BASELINE SQL",
            st.session_state.get("baseline_sql", ""),
            "",
            "CANDIDATE SQL",
            st.session_state.get("candidate_sql", ""),
        ]

        st.download_button(
            "Download performance report",
            data="\n".join(report_lines),
            file_name="sql_refinery_performance_report.txt",
            mime="text/plain",
            use_container_width=False,
        )

    else:
        st.caption(
            "Performance metrics are shown only after both queries execute "
            "successfully, produce equivalent results, and complete benchmarking."
        )

        # Allow inspecting result sets when execution succeeded but the
        # queries differ or the benchmark could not be completed.
        baseline_result = report.get("baseline_result")
        candidate_result = report.get("candidate_result")

        if baseline_result is not None or candidate_result is not None:
            st.markdown("#### Inspect executed results")

            result_col1, result_col2 = st.columns(2, gap="large")

            with result_col1:
                with st.expander("Baseline result set", expanded=False):
                    if baseline_result is not None:
                        show_query_result("Baseline results", baseline_result)

            with result_col2:
                with st.expander("Candidate result set", expanded=False):
                    if candidate_result is not None:
                        show_query_result("Candidate results", candidate_result)


# ============================================================
# FOOTER
# ============================================================

st.markdown(
    """
    <div class="footer">
        <span>SQL-Refinery · Query Performance Studio</span>
        <span>Validate first. Compare second. Optimize with confidence.</span>
    </div>
    """,
    unsafe_allow_html=True,
)
