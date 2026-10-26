"""UI components and presentation helpers for Nemotron SQL Lab."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

CURRENT_DIR = Path(__file__).resolve().parent
THEME_CSS_PATH = CURRENT_DIR / "theme.css"
SCENE_HTML_PATH = CURRENT_DIR / "scene.html"


def inject_custom_theme() -> None:
    """Inject the dark frosted-glass theme CSS."""
    if THEME_CSS_PATH.exists():
        css = THEME_CSS_PATH.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def render_nav_bar(ai_ready: bool = True) -> None:
    """Render the slim frosted glass top navigation bar."""
    status_class = "" if ai_ready else "offline"
    status_label = "Nemotron-3.5 Connected" if ai_ready else "AI Not Configured"
    
    st.markdown(
        f"""
        <div class="glass-nav">
            <div class="glass-nav-brand">
                <div class="brand-icon-box">⚡</div>
                <div>
                    <div class="brand-title">Nemotron SQL Lab</div>
                    <div class="brand-subtitle-tag">SQL Refinery & Performance Studio</div>
                </div>
            </div>
            <div class="glass-nav-tabs">
                <div class="nav-tab-pill active">
                    <span>✦</span> Studio
                </div>
                <div class="nav-tab-pill">
                    <span>⚙</span> DuckDB Engine
                </div>
                <div class="nav-status-indicator">
                    <span class="status-dot-pulse {status_class}"></span>
                    <span>{status_label}</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_hero_3d(state: str = "idle") -> None:
    """
    Render the Three.js 3D isometric SQL Refinery machine hero scene.
    State can be: 'idle', 'processing' (or 'refining'), or 'done'.
    """
    if SCENE_HTML_PATH.exists():
        template = SCENE_HTML_PATH.read_text(encoding="utf-8")
        html_content = template.replace("{{INITIAL_STATE}}", state)
        
        st.markdown(
            """
            <div class="hero-wrapper">
                <div class="hero-header-overlay">
                    <div class="hero-badge">⚡ Real-time 3D Pipeline</div>
                    <h1 class="hero-title">Intelligent SQL Refinery</h1>
                    <p class="hero-tagline">AI-assisted SQL optimization with mathematical correctness verification and DuckDB performance benchmarking.</p>
                </div>
            """,
            unsafe_allow_html=True,
        )
        
        components.html(html_content, height=350, scrolling=False)
        
        st.markdown("</div>", unsafe_allow_html=True)


def render_glass_metric(
    label: str,
    value: str,
    delta: str = "",
    positive: bool = True,
    highlight: str = "",
) -> str:
    """Return HTML for a styled frosted glass metric card."""
    h_class = f"highlight-{highlight}" if highlight else ""
    delta_class = "positive" if positive else "negative"
    delta_html = (
        f'<div class="f-metric-delta {delta_class}">{html.escape(delta)}</div>'
        if delta
        else ""
    )
    return f"""
    <div class="frosted-metric-card {h_class}">
        <div class="f-metric-label">{html.escape(label)}</div>
        <div class="f-metric-value">{html.escape(value)}</div>
        {delta_html}
    </div>
    """
