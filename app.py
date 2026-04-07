import streamlit as st
import json
import time
import os
import io
import sys
from datetime import datetime
import plotly.graph_objects as go
from streamlit_agraph import agraph, Node, Edge, Config
from utils.cache import save, load, CACHE_DIR
from utils.format_loader import load_all_formats, register_custom_format
from agents.format_matcher import run as run_format_matcher
from utils.latex_exporter import generate_pdf_bytes, generate_latex_source

# ── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="VMARO — Research Orchestrator", layout="wide", page_icon="🔬")

# Reset sys.stdout if an old StreamCapture was left hanging by Streamlit hot-reloading
if hasattr(sys.stdout, "original"):
    sys.stdout = sys.__stdout__

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* ═══════════════════════════════════════════════════════════════════════
       VMARO — RESEARCH COMMAND CENTER  |  Premium Dark UI System
       ═══════════════════════════════════════════════════════════════════════ */

    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

    /* ── CSS Custom Properties ─────────────────────────────────────────── */
    :root {
        --bg-primary:        #0a0e17;
        --bg-card:           rgba(13, 21, 38, 0.65);
        --bg-card-solid:     #0d1526;
        --bg-sidebar:        #070b14;
        --bg-elevated:       rgba(20, 32, 56, 0.8);

        --accent-cyan:       #00e5ff;
        --accent-violet:     #7b61ff;
        --accent-mint:       #00ffa3;
        --accent-orange:     #ff6b35;
        --accent-red:        #ff3355;
        --accent-amber:      #ffb627;

        --text-primary:      #e0e6f0;
        --text-secondary:    #5a6a85;
        --text-muted:        #2e3d58;

        --border-subtle:     rgba(0, 229, 255, 0.07);
        --border-active:     rgba(0, 229, 255, 0.25);
        --border-glow:       rgba(0, 229, 255, 0.5);

        --glow-cyan:         0 0 20px rgba(0, 229, 255, 0.12), 0 0 40px rgba(0, 229, 255, 0.05);
        --glow-violet:       0 0 20px rgba(123, 97, 255, 0.15), 0 0 40px rgba(123, 97, 255, 0.06);
        --glow-mint:         0 0 20px rgba(0, 255, 163, 0.15);
        --glow-orange:       0 0 20px rgba(255, 107, 53, 0.2);

        --radius-sm:         6px;
        --radius-md:         10px;
        --radius-lg:         14px;
        --radius-pill:       100px;

        --transition-fast:   0.15s ease;
        --transition-med:    0.25s ease;
    }

    /* ── Global Reset & Fonts ──────────────────────────────────────────── */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        color: var(--text-primary);
    }

    /* ── Page Background — Data Grid ──────────────────────────────────── */
    .stApp {
        background-color: var(--bg-primary);
        background-image:
            radial-gradient(circle, rgba(0, 229, 255, 0.028) 1px, transparent 1px),
            radial-gradient(circle, rgba(123, 97, 255, 0.015) 1px, transparent 1px);
        background-size: 32px 32px, 80px 80px;
        background-position: 0 0, 16px 16px;
    }

    /* ── Sidebar ──────────────────────────────────────────────────────── */
    section[data-testid="stSidebar"] {
        background: var(--bg-sidebar) !important;
        border-right: 1px solid var(--border-subtle);
    }
    section[data-testid="stSidebar"] .stMarkdown h3,
    section[data-testid="stSidebar"] .stMarkdown h5 {
        font-family: 'Space Grotesk', sans-serif;
        color: var(--text-secondary);
        letter-spacing: 0.08em;
        text-transform: uppercase;
        font-size: 0.7rem;
    }
    section[data-testid="stSidebar"] .stTextInput input {
        background: rgba(0, 229, 255, 0.04);
        border: 1px solid var(--border-subtle);
        color: var(--text-primary);
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.85rem;
        border-radius: var(--radius-md);
        transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
    }
    section[data-testid="stSidebar"] .stTextInput input:focus {
        border-color: var(--accent-cyan);
        box-shadow: 0 0 0 2px rgba(0, 229, 255, 0.12);
        outline: none;
    }

    /* ── Stage Ribbon ─────────────────────────────────────────────────── */
    .ribbon-wrap {
        display: flex;
        align-items: center;
        gap: 0;
        background: rgba(7, 11, 20, 0.85);
        backdrop-filter: blur(16px);
        border: 1px solid var(--border-subtle);
        border-radius: var(--radius-lg);
        padding: 10px 20px;
        margin-bottom: 24px;
        overflow-x: auto;
        scrollbar-width: none;
    }
    .ribbon-wrap::-webkit-scrollbar { display: none; }
    .ribbon-node {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 5px;
        min-width: 80px;
        cursor: default;
        position: relative;
        padding: 4px 8px;
        border-radius: var(--radius-md);
        transition: background var(--transition-fast);
    }
    .ribbon-node.clickable { cursor: pointer; }
    .ribbon-node.clickable:hover { background: rgba(0,229,255,0.06); }
    .ribbon-node.active { background: rgba(0,229,255,0.08); }
    .ribbon-dot {
        width: 28px; height: 28px;
        border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 0.7rem; font-weight: 700;
        font-family: 'JetBrains Mono', monospace;
        flex-shrink: 0;
        transition: box-shadow var(--transition-med);
    }
    .ribbon-dot.complete  { background: rgba(0,255,163,0.15);  color: #00ffa3; border: 1.5px solid rgba(0,255,163,0.4);  box-shadow: 0 0 12px rgba(0,255,163,0.2); }
    .ribbon-dot.awaiting  { background: rgba(0,229,255,0.12);  color: #00e5ff; border: 1.5px solid rgba(0,229,255,0.4);  box-shadow: 0 0 12px rgba(0,229,255,0.25); animation: glow-pulse-cyan 2s ease-in-out infinite; }
    .ribbon-dot.running   { background: rgba(255,107,53,0.15); color: #ff6b35; border: 1.5px solid rgba(255,107,53,0.4); box-shadow: 0 0 12px rgba(255,107,53,0.3); animation: glow-pulse-orange 1s ease-in-out infinite; }
    .ribbon-dot.pending   { background: rgba(46,61,88,0.3);    color: #2e3d58; border: 1.5px solid #1a2540; }
    .ribbon-dot.active-ring { outline: 2px solid var(--accent-cyan); outline-offset: 3px; }
    .ribbon-label {
        font-size: 0.62rem;
        font-family: 'JetBrains Mono', monospace;
        text-align: center;
        white-space: nowrap;
        color: var(--text-secondary);
        letter-spacing: 0.02em;
    }
    .ribbon-label.active { color: var(--accent-cyan); }
    .ribbon-connector {
        flex: 1;
        min-width: 16px;
        height: 1px;
        background: var(--border-subtle);
        margin: 0 2px;
        margin-bottom: 18px;
    }
    .ribbon-connector.done { background: rgba(0,255,163,0.25); }

    /* ── Dashboard ────────────────────────────────────────────────────── */
    .dash-panel {
        background: var(--bg-card);
        backdrop-filter: blur(14px);
        -webkit-backdrop-filter: blur(14px);
        border: 1px solid var(--border-subtle);
        border-radius: var(--radius-lg);
        padding: 20px;
        height: 100%;
        transition: border-color var(--transition-med), box-shadow var(--transition-med);
    }
    .dash-panel:hover {
        border-color: var(--border-active);
        box-shadow: var(--glow-cyan);
    }
    .dash-panel-title {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.65rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: var(--text-muted);
        margin-bottom: 14px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .dash-panel-title::before {
        content: '';
        display: inline-block;
        width: 6px; height: 6px;
        border-radius: 50%;
        background: var(--accent-cyan);
        box-shadow: 0 0 6px var(--accent-cyan);
    }
    .dash-stat-row {
        display: flex;
        gap: 12px;
        margin-bottom: 16px;
    }
    .dash-stat {
        flex: 1;
        background: rgba(0,229,255,0.04);
        border: 1px solid var(--border-subtle);
        border-radius: var(--radius-md);
        padding: 10px 14px;
        text-align: center;
    }
    .dash-stat-value {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1.8rem;
        font-weight: 700;
        color: var(--accent-cyan);
        line-height: 1;
    }
    .dash-stat-label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.6rem;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-top: 4px;
    }
    .dash-mini-paper {
        padding: 10px 12px;
        border-left: 2px solid var(--border-subtle);
        margin-bottom: 8px;
        transition: border-color var(--transition-fast);
    }
    .dash-mini-paper:hover { border-left-color: var(--accent-cyan); }
    .dash-mini-paper h5 {
        font-family: 'Inter', sans-serif;
        font-size: 0.82rem;
        color: var(--text-primary);
        margin: 0 0 3px 0;
        line-height: 1.3;
    }
    .dash-mini-paper span {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.65rem;
        color: var(--text-muted);
    }
    .dash-gap-chip {
        background: rgba(255,107,53,0.08);
        border: 1px solid rgba(255,107,53,0.18);
        border-radius: var(--radius-sm);
        padding: 8px 12px;
        margin-bottom: 8px;
        font-size: 0.82rem;
        color: #9aaac2;
        line-height: 1.5;
    }
    .dash-gap-chip strong {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        color: #ff6b35;
    }
    .dash-qg-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 12px;
        border-radius: var(--radius-pill);
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        font-weight: 600;
        margin-right: 6px;
    }

    /* ── Main Title ───────────────────────────────────────────────────── */
    .main-title {
        font-family: 'Space Grotesk', sans-serif;
        background: linear-gradient(135deg, var(--accent-cyan) 0%, var(--accent-violet) 60%, var(--accent-cyan) 100%);
        background-size: 200% auto;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: 2.5rem;
        font-weight: 700;
        margin-bottom: 0;
        letter-spacing: -0.5px;
        animation: gradient-shift 6s linear infinite;
    }
    .subtitle {
        color: var(--text-secondary);
        font-size: 0.9rem;
        margin-top: -4px;
        margin-bottom: 28px;
        font-family: 'JetBrains Mono', monospace;
        letter-spacing: 0.02em;
    }
    .subtitle::after {
        content: '▌';
        color: var(--accent-cyan);
        opacity: 0.8;
        animation: blink 1.2s step-end infinite;
    }

    /* ── Gate Banner ──────────────────────────────────────────────────── */
    .gate-banner {
        background: rgba(255, 107, 53, 0.08);
        border-left: 3px solid var(--accent-orange);
        border-radius: 0 var(--radius-md) var(--radius-md) 0;
        color: #ffd0b8;
        padding: 12px 20px;
        margin-bottom: 20px;
        font-size: 0.9rem;
        backdrop-filter: blur(8px);
    }

    /* ── Pipeline Step States ─────────────────────────────────────────── */
    .step-complete {
        color: var(--accent-mint);
        cursor: pointer;
        font-family: 'JetBrains Mono', monospace;
        text-shadow: 0 0 8px rgba(0, 255, 163, 0.4);
    }
    .step-awaiting {
        color: var(--accent-cyan);
        animation: glow-pulse-cyan 2s ease-in-out infinite;
        cursor: pointer;
        font-family: 'JetBrains Mono', monospace;
    }
    .step-pending {
        color: var(--text-muted);
        font-family: 'JetBrains Mono', monospace;
    }
    .step-running {
        color: var(--accent-orange);
        font-family: 'JetBrains Mono', monospace;
        animation: glow-pulse-orange 1s ease-in-out infinite;
    }

    /* ── Card System (Glassmorphic) ───────────────────────────────────── */
    .paper-card {
        background: var(--bg-card);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid var(--border-subtle);
        border-radius: var(--radius-lg);
        padding: 20px;
        margin-bottom: 12px;
        transition: transform var(--transition-med), box-shadow var(--transition-med), border-color var(--transition-med);
        position: relative;
        overflow: hidden;
    }
    .paper-card::before {
        content: '';
        position: absolute;
        top: 0; left: -100%;
        width: 100%; height: 1px;
        background: linear-gradient(90deg, transparent, rgba(0,229,255,0.4), transparent);
        transition: left 0.6s ease;
    }
    .paper-card:hover::before { left: 100%; }
    .paper-card:hover {
        transform: translateY(-3px);
        box-shadow: var(--glow-cyan);
        border-color: var(--border-active);
    }
    .paper-card h4 {
        color: var(--accent-cyan);
        margin-bottom: 8px;
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1rem;
    }
    .paper-card .year-badge {
        display: inline-block;
        background: rgba(0, 229, 255, 0.1);
        color: var(--accent-cyan);
        padding: 2px 10px;
        border-radius: var(--radius-pill);
        font-size: 0.75rem;
        font-weight: 600;
        font-family: 'JetBrains Mono', monospace;
        border: 1px solid rgba(0, 229, 255, 0.18);
    }

    /* ── Gap Card ─────────────────────────────────────────────────────── */
    .gap-card {
        background: var(--bg-card);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border-left: 3px solid var(--accent-orange);
        border-radius: 0 var(--radius-md) var(--radius-md) 0;
        padding: 16px 20px;
        margin-bottom: 10px;
        transition: transform var(--transition-med), box-shadow var(--transition-med);
        position: relative;
    }
    .gap-card:hover {
        transform: translateX(5px);
        box-shadow: var(--glow-orange);
    }
    .gap-auto-selected {
        border-color: var(--accent-cyan);
        box-shadow: 0 0 12px rgba(0, 229, 255, 0.1);
    }

    /* ── Methodology Cards ────────────────────────────────────────────── */
    .methodology-winner {
        border: 1px solid rgba(0, 255, 163, 0.35) !important;
        border-radius: var(--radius-lg) !important;
        box-shadow: var(--glow-mint);
    }
    .methodology-loser {
        opacity: 0.45;
        filter: saturate(0.6);
    }

    /* ── Format Card — Recommended ────────────────────────────────────── */
    .format-card-recommended {
        border-radius: var(--radius-lg);
        border: 1px solid rgba(0, 229, 255, 0.3) !important;
        box-shadow: var(--glow-cyan);
    }

    /* ── Ribbon Nav Buttons (invisible click layer) ─────────────────── */
    [data-testid="stButton"] button[kind="secondary"]:has(+ div[data-testid="stMarkdown"]) { display: none; }
    /* Hide ribbon nav buttons — keyed by class pattern for ribbon_nav_ keys */
    div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] > button {
        opacity: 0 !important;
        height: 4px !important;
        min-height: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
        border: none !important;
        background: transparent !important;
        pointer-events: auto;
        cursor: pointer;
    }
    div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] {
        margin-top: -32px;
        margin-bottom: 0;
    }

    /* ── Pull Quote ─────────────────────────────────────────────────────*/
    .pull-quote {
        border-left: 3px solid var(--accent-violet);
        padding: 12px 20px;
        background: rgba(123, 97, 255, 0.06);
        border-radius: 0 var(--radius-md) var(--radius-md) 0;
        color: var(--text-secondary);
        font-style: italic;
        margin: 20px 0;
        line-height: 1.7;
    }

    /* ── Source Badges ─────────────────────────────────────────────────  */
    .source-badge-arxiv    { background: rgba(0, 229, 255, 0.12); color: #00e5ff; border: 1px solid rgba(0, 229, 255, 0.2); }
    .source-badge-pubmed   { background: rgba(100, 160, 255, 0.12); color: #80b4ff; border: 1px solid rgba(100, 160, 255, 0.2); }
    .source-badge-semantic { background: rgba(123, 97, 255, 0.12); color: #9f87ff; border: 1px solid rgba(123, 97, 255, 0.2); }
    .source-badge-crossref { background: rgba(0, 255, 163, 0.1); color: #00ffa3; border: 1px solid rgba(0, 255, 163, 0.18); }
    .source-badge-openalex { background: rgba(255, 182, 39, 0.1); color: #ffb627; border: 1px solid rgba(255, 182, 39, 0.18); }
    .source-badge-default  { background: rgba(90, 106, 133, 0.15); color: #8a9bb5; border: 1px solid rgba(90, 106, 133, 0.2); }

    .source-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: var(--radius-pill);
        font-size: 0.72rem;
        font-weight: 600;
        margin-left: 8px;
        font-family: 'JetBrains Mono', monospace;
        letter-spacing: 0.03em;
    }

    /* ── Grant Section ────────────────────────────────────────────────── */
    .grant-section { margin-bottom: 24px; }
    .grant-section h3 {
        font-family: 'Space Grotesk', sans-serif;
        color: var(--accent-cyan);
        border-bottom: 1px solid var(--border-subtle);
        padding-bottom: 8px;
        margin-bottom: 12px;
        font-size: 1rem;
        letter-spacing: 0.02em;
    }
    .grant-section p {
        color: var(--text-primary);
        line-height: 1.75;
        font-size: 0.95rem;
    }

    /* ── Score Display ────────────────────────────────────────────────── */
    .score-big {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 4.5rem;
        font-weight: 700;
        text-align: center;
        line-height: 1;
        background: linear-gradient(135deg, var(--accent-mint), var(--accent-cyan));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .score-label {
        text-align: center;
        font-size: 0.85rem;
        color: var(--text-secondary);
        margin-top: 6px;
        font-family: 'JetBrains Mono', monospace;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }

    /* ── Streamlit Component Overrides ───────────────────────────────── */
    div[data-testid="stMetricValue"] {
        font-size: 2.8rem;
        font-family: 'Space Grotesk', sans-serif;
        color: var(--accent-cyan);
    }
    div[data-testid="stMetricLabel"] {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--text-secondary);
    }
    div[data-testid="stMetricDelta"] { color: var(--accent-mint); }

    div[data-testid="stMetric"] {
        background: var(--bg-card);
        backdrop-filter: blur(10px);
        border: 1px solid var(--border-subtle);
        border-radius: var(--radius-lg);
        padding: 16px 20px;
        transition: box-shadow var(--transition-med), border-color var(--transition-med);
    }
    div[data-testid="stMetric"]:hover {
        box-shadow: var(--glow-cyan);
        border-color: var(--border-active);
    }

    /* Streamlit buttons */
    .stButton > button {
        background: rgba(0, 229, 255, 0.06);
        color: var(--accent-cyan);
        border: 1px solid rgba(0, 229, 255, 0.2);
        border-radius: var(--radius-md);
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.8rem;
        letter-spacing: 0.04em;
        transition: background var(--transition-fast), box-shadow var(--transition-fast), border-color var(--transition-fast);
    }
    .stButton > button:hover {
        background: rgba(0, 229, 255, 0.12);
        border-color: rgba(0, 229, 255, 0.45);
        box-shadow: 0 0 14px rgba(0, 229, 255, 0.15);
        color: #fff;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, rgba(0, 229, 255, 0.15), rgba(123, 97, 255, 0.15));
        border-color: rgba(0, 229, 255, 0.35);
        color: var(--accent-cyan);
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, rgba(0, 229, 255, 0.25), rgba(123, 97, 255, 0.25));
        box-shadow: var(--glow-cyan);
    }

    /* Divider */
    hr {
        border: none;
        border-top: 1px solid var(--border-subtle);
        margin: 24px 0;
    }

    /* Expanders */
    .streamlit-expanderHeader {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.82rem;
        color: var(--text-secondary);
        background: var(--bg-card-solid) !important;
        border-radius: var(--radius-md);
        border: 1px solid var(--border-subtle) !important;
    }
    .streamlit-expanderContent {
        background: var(--bg-card-solid) !important;
        border: 1px solid var(--border-subtle) !important;
        border-top: none !important;
    }

    /* Status/Spinner */
    div[data-testid="stStatusWidget"] {
        background: var(--bg-card) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: var(--radius-lg) !important;
        backdrop-filter: blur(12px);
    }

    /* File uploader */
    div[data-testid="stFileUploader"] {
        background: rgba(0, 229, 255, 0.03);
        border: 1px dashed rgba(0, 229, 255, 0.15);
        border-radius: var(--radius-md);
        padding: 8px;
    }

    /* Download button */
    div[data-testid="stDownloadButton"] > button {
        background: rgba(0, 255, 163, 0.06);
        color: var(--accent-mint);
        border-color: rgba(0, 255, 163, 0.2);
    }
    div[data-testid="stDownloadButton"] > button:hover {
        background: rgba(0, 255, 163, 0.12);
        border-color: rgba(0, 255, 163, 0.4);
        box-shadow: var(--glow-mint);
    }

    /* Info/Error/Warning boxes */
    div[data-testid="stInfo"] {
        background: rgba(0, 229, 255, 0.05);
        border: 1px solid rgba(0, 229, 255, 0.15);
        border-radius: var(--radius-md);
        color: var(--text-secondary);
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.85rem;
    }
    div[data-testid="stError"] {
        background: rgba(255, 51, 85, 0.08);
        border-color: rgba(255, 51, 85, 0.25);
        color: #ff8fa0;
    }
    div[data-testid="stSuccess"] {
        background: rgba(0, 255, 163, 0.07);
        border-color: rgba(0, 255, 163, 0.2);
        color: var(--accent-mint);
    }
    div[data-testid="stWarning"] {
        background: rgba(255, 182, 39, 0.07);
        border-color: rgba(255, 182, 39, 0.2);
        color: var(--accent-amber);
    }

    /* Scrollbar */
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: var(--bg-primary); }
    ::-webkit-scrollbar-thumb {
        background: rgba(0, 229, 255, 0.2);
        border-radius: 10px;
    }
    ::-webkit-scrollbar-thumb:hover { background: rgba(0, 229, 255, 0.4); }

    /* Hide fullscreen */
    button[title="View fullscreen"] { display: none; }

    /* ── Animations ─────────────────────────────────────────────────────*/
    @keyframes blink {
        0%, 100% { opacity: 1; }
        50% { opacity: 0; }
    }
    @keyframes gradient-shift {
        0%   { background-position: 0% 50%; }
        50%  { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    @keyframes glow-pulse-cyan {
        0%, 100% { opacity: 1; text-shadow: 0 0 6px rgba(0, 229, 255, 0.4); }
        50% { opacity: 0.7; text-shadow: 0 0 14px rgba(0, 229, 255, 0.7); }
    }
    @keyframes glow-pulse-orange {
        0%, 100% { opacity: 1; text-shadow: 0 0 6px rgba(255, 107, 53, 0.5); }
        50% { opacity: 0.7; text-shadow: 0 0 16px rgba(255, 107, 53, 0.8); }
    }
    @keyframes scan-line {
        0%   { transform: translateX(-100%); }
        100% { transform: translateX(100%); }
    }
    @keyframes led-blink {
        0%, 90%, 100% { opacity: 1; }
        95% { opacity: 0.2; }
    }
</style>
""", unsafe_allow_html=True)

# ── Constants & Helpers ──────────────────────────────────────────────────────
RESULT_KEYS = ["papers", "tree", "qg1", "trends", "gaps", "qg2", "user_gap_selection", "methodology_a", "methodology_b", "methodology_eval", "format_match", "grant", "novelty"]

def is_fallback(data, required_keys):
    """Check if result is a fallback/empty dict that shouldn't be cached."""
    if not data or not isinstance(data, dict):
        return True
    for k in required_keys:
        v = data.get(k)
        if v is None or v == "" or v == [] or v == {}:
            return True
    return False

def get_source_badge_class(url_or_source):
    if not url_or_source: return "source-badge-default"
    s = url_or_source.lower()
    if "arxiv" in s: return "source-badge-arxiv"
    if "pubmed" in s or "ncbi" in s: return "source-badge-pubmed"
    if "semantic" in s or "semanticscholar" in s: return "source-badge-semantic"
    if "crossref" in s or "doi.org" in s: return "source-badge-crossref"
    if "openalex" in s: return "source-badge-openalex"
    return "source-badge-default"

def get_source_name(url_or_source):
    if not url_or_source: return "Source"
    s = url_or_source.lower()
    if "arxiv" in s: return "arXiv"
    if "pubmed" in s or "ncbi" in s: return "PubMed"
    if "semantic" in s or "semanticscholar" in s: return "Semantic Scholar"
    if "crossref" in s or "doi.org" in s: return "CrossRef"
    if "openalex" in s: return "OpenAlex"
    return "Source"

# ── Session State Init ───────────────────────────────────────────────────────
if "pipeline_run" not in st.session_state: st.session_state.pipeline_run = False
if "pipeline_topic" not in st.session_state: st.session_state.pipeline_topic = ""
if "pipeline_errors" not in st.session_state: st.session_state.pipeline_errors = {}
if "stage_status" not in st.session_state: st.session_state.stage_status = {}
if "formats" not in st.session_state: st.session_state.formats = load_all_formats()
if "user_format_override" not in st.session_state: st.session_state.user_format_override = None
if "active_step" not in st.session_state: st.session_state.active_step = 0
if "debug_logs" not in st.session_state: st.session_state.debug_logs = []
if "is_running_pipeline" not in st.session_state: st.session_state.is_running_pipeline = False

class StreamCapture:
    def __init__(self, original_stdout):
        self.original = original_stdout
        self.buffer = io.StringIO()
    def write(self, text):
        self.original.write(text)
    def flush(self):
        self.original.flush()

# Auto-load cached results
for key in RESULT_KEYS:
    if key not in st.session_state:
        cached = load(key)
        if cached:
            st.session_state[key] = cached
            st.session_state.pipeline_run = True
        else:
            st.session_state[key] = None

if not st.session_state.pipeline_topic:
    topic_file = os.path.join(CACHE_DIR, "_topic.txt")
    if os.path.exists(topic_file):
        st.session_state.pipeline_topic = open(topic_file).read().strip()

if st.session_state.pipeline_run and st.session_state.active_step == 0 and not load("papers"):
    st.session_state.active_step = 0

def set_stage(key, status):
    st.session_state.stage_status[key] = status

# ── Layout structure ─────────────────────────────────────────────────────────
col_main = st.container()

# ── Sidebar: Config Only ─────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:4px 0 16px 0;">
        <div style="font-family:'Space Grotesk',sans-serif; font-size:1rem; font-weight:600;
                    color:#e0e6f0; margin-bottom:2px;">VMARO</div>
        <div style="font-family:'JetBrains Mono',monospace; font-size:0.65rem;
                    color:#2e3d58; letter-spacing:0.08em;">RESEARCH ORCHESTRATOR v1.0</div>
    </div>
    """, unsafe_allow_html=True)

    topic = st.text_input(
        "Research Topic",
        value=st.session_state.pipeline_topic,
        placeholder="e.g. Federated Learning in Healthcare",
        label_visibility="collapsed"
    )
    st.markdown('<div style="font-family:\'JetBrains Mono\',monospace; font-size:0.65rem; color:#2e3d58; margin-bottom:8px;">// enter topic then run</div>', unsafe_allow_html=True)

    run_btn = st.button("⬡  Run Analysis", use_container_width=True, type="primary")
    if st.button("↺  Clear & Restart", use_container_width=True):
        import shutil
        if os.path.exists(CACHE_DIR):
            shutil.rmtree(CACHE_DIR)
        for key in RESULT_KEYS:
            st.session_state[key] = None
        st.session_state.pipeline_run = False
        st.session_state.active_step = 0
        st.session_state.debug_logs = []
        st.rerun()

    # ── Live pipeline status in sidebar (compact) ─────────────────────────
    if st.session_state.pipeline_run or load("papers"):
        st.markdown("---")
        qg1_d = (load("qg1") or {}).get("decision", "PENDING")
        qg2_d = (load("qg2") or {}).get("decision", "PENDING")
        qg_colors = {"PASS": "#00ffa3", "REVISE": "#ff6b35", "FAIL": "#ff3355", "PENDING": "#2e3d58"}
        papers_n  = len((load("papers") or {}).get("papers", []))
        themes_n  = len((load("tree") or {}).get("themes", []))
        gaps_n    = len((load("gaps") or {}).get("identified_gaps", []))
        nov_score = (load("novelty") or {}).get("novelty_score", "—")
        fmt_id    = (load("format_match") or {}).get("selected_format_id", "—")
        st.markdown(f"""
        <div style="font-family:'JetBrains Mono',monospace; font-size:0.68rem; color:#2e3d58;
                    line-height:2; padding:2px 0;">
            <div style="display:flex;justify-content:space-between;"><span>Papers</span><span style="color:#00e5ff;">{papers_n}</span></div>
            <div style="display:flex;justify-content:space-between;"><span>Themes</span><span style="color:#7b61ff;">{themes_n}</span></div>
            <div style="display:flex;justify-content:space-between;"><span>Gaps found</span><span style="color:#ff6b35;">{gaps_n}</span></div>
            <div style="display:flex;justify-content:space-between;"><span>Format</span><span style="color:#00e5ff;">{fmt_id}</span></div>
            <div style="display:flex;justify-content:space-between;"><span>Novelty</span><span style="color:#00ffa3;">{nov_score}</span></div>
            <div style="height:1px;background:#0d1526;margin:8px 0;"></div>
            <div style="display:flex;justify-content:space-between;"><span>QG-1</span><span style="color:{qg_colors.get(qg1_d,'#2e3d58')};">{qg1_d}</span></div>
            <div style="display:flex;justify-content:space-between;"><span>QG-2</span><span style="color:{qg_colors.get(qg2_d,'#2e3d58')};">{qg2_d}</span></div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("⬡  Dashboard", use_container_width=True):
            st.session_state.active_step = 0
            st.rerun()

    def update_pipeline_sidebar():
        pass  # Sidebar pipeline list removed — now using horizontal ribbon

    st.markdown("---")
    st.markdown("### Custom Grant Format")
    try:
        with open("schemas_for_user/custom_grant_format_template.json", "r") as f:
            template_content = f.read()
        st.download_button(
            label="Download Blank Template (JSON)",
            data=template_content,
            file_name="custom_grant_format_template.json",
            mime="application/json",
            help="Fill in this template and upload below to use your own grant format."
        )
    except FileNotFoundError:
        st.caption("Custom format template not found.")

    uploaded_file = st.file_uploader(
        "Upload Custom Format (JSON)",
        type=["json"]
    )
    if uploaded_file:
        try:
            custom_fmt = json.load(uploaded_file)
            success, errors = register_custom_format(custom_fmt, st.session_state.formats)
            if success:
                st.success(f"Format '{custom_fmt['format_id']}' loaded.")
            else:
                st.error("Validation failed.")
        except json.JSONDecodeError:
            st.error("Invalid JSON.")


# ── Run Pipeline Logic ───────────────────────────────────────────────────────
if run_btn:
    if not topic.strip():
        st.error("Please enter a research topic.")
        st.stop()

    st.session_state.is_running_pipeline = True

    last_topic_file = os.path.join(CACHE_DIR, "_topic.txt")
    if os.path.exists(CACHE_DIR) and os.path.exists(last_topic_file):
        prev_topic = open(last_topic_file).read().strip()
        if prev_topic != topic.strip():
            import shutil
            shutil.rmtree(CACHE_DIR)
            for key in RESULT_KEYS:
                st.session_state[key] = None
            st.session_state.active_step = 1

    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(last_topic_file, "w") as f:
        f.write(topic.strip())

    st.session_state.pipeline_topic = topic.strip()
    st.session_state.pipeline_run = True
    st.session_state.active_step = 1

    from agents.literature_agent import run as run_literature
    from agents.tree_agent import run as run_tree
    from agents.trend_agent import run as run_trend
    from agents.gap_agent import run as run_gap
    from utils.quality_gate import evaluate_quality
    
    _original_stdout = sys.stdout
    sys.stdout = StreamCapture(_original_stdout)

    with col_main:
        with st.status("🚀 **Running Phase 1 Pipeline**", expanded=True):
            set_stage("papers", "running")
            update_pipeline_sidebar()
            st.write("**Fetching papers parallely...**")
            papers = load("papers") or run_literature(topic)
            if not load("papers"): save("papers", papers)
            st.session_state.papers = papers
            set_stage("papers", "complete")
            update_pipeline_sidebar()

            set_stage("tree", "running")
            update_pipeline_sidebar()
            st.write("**Clustering papers...**")
            tree = load("tree") or run_tree(papers)
            if not load("tree"): save("tree", tree)
            st.session_state.tree = tree
            set_stage("tree", "complete")
            update_pipeline_sidebar()

            set_stage("qg1", "running")
            update_pipeline_sidebar()
            qg1 = load("qg1") or evaluate_quality("post_literature", tree)
            if not load("qg1"): save("qg1", qg1)
            st.session_state.qg1 = qg1
            set_stage("qg1", "complete")
            update_pipeline_sidebar()

            set_stage("trends", "running")
            update_pipeline_sidebar()
            st.write("**Analyzing trends...**")
            trends = load("trends") or run_trend(tree)
            if not load("trends"): save("trends", trends)
            st.session_state.trends = trends
            set_stage("trends", "complete")
            update_pipeline_sidebar()
            
            set_stage("gaps", "running")
            update_pipeline_sidebar()
            st.write("**Identifying research gaps...**")
            gaps = load("gaps") or run_gap(tree, trends)
            if not load("gaps"): save("gaps", gaps)
            st.session_state.gaps = gaps
            set_stage("gaps", "complete")
            update_pipeline_sidebar()
            
            set_stage("qg2", "running")
            update_pipeline_sidebar()
            qg2 = load("qg2") or evaluate_quality("post_gap", gaps)
            if not load("qg2"): save("qg2", qg2)
            st.session_state.qg2 = qg2
            set_stage("qg2", "complete")
            update_pipeline_sidebar()

    st.session_state.is_running_pipeline = False
    sys.stdout = _original_stdout
    st.session_state.active_step = 4
    st.rerun()

# ── STEP STATE HELPER ────────────────────────────────────────────────────────
def get_step_state(step_num, cache_key):
    if step_num == 4:
        if load("user_gap_selection"): return "complete"
        if load("gaps"): return "awaiting"
    if step_num == 6:
        if load("grant"): return "complete"
        if load("methodology_eval"): return "awaiting"
    if step_num == 5:
        if load("methodology_a") or load("methodology_eval"): return "complete"
    if step_num == 3:
        if load("trends") or load("gaps"): return "complete"
    if load(cache_key): return "complete"
    for k in st.session_state.stage_status:
        if st.session_state.stage_status[k] == "running":
            if step_num == 1 and k == "papers": return "running"
            if step_num == 2 and k == "tree": return "running"
            if step_num == 3 and k in ["trends", "gaps"]: return "running"
            if step_num == 5 and k in ["methodology_a", "methodology_b", "methodology_eval"]: return "running"
            if step_num == 7 and k == "grant": return "running"
            if step_num == 8 and k == "novelty": return "running"
    return "pending"

RIBBON_STEPS = [
    (0, "Overview",   None,                "⬡"),
    (1, "Literature", "papers",            "01"),
    (2, "Tree",       "tree",              "02"),
    (3, "Trends",     "gaps",              "03"),
    (4, "Gaps",       "user_gap_selection","04"),
    (5, "Method",     "methodology_eval",  "05"),
    (6, "Format",     "format_match",      "06"),
    (7, "Grant",      "grant",             "07"),
    (8, "Novelty",    "novelty",           "08"),
]

# ── Right Column: Content Area ───────────────────────────────────────────────
with col_main:
    # Header
    st.markdown('<p class="main-title">VMARO Research Orchestrator</p>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">// AI-powered 8-stage research pipeline &mdash; from literature to grant proposal</p>', unsafe_allow_html=True)

    # ── No data at all — show landing ────────────────────────────────────
    if not st.session_state.pipeline_run and not load("papers"):
        st.markdown("""
        <div style="margin-top:40px; padding:48px; background:rgba(13,21,38,0.7);
                    border:1px solid rgba(0,229,255,0.08); border-radius:16px;
                    backdrop-filter:blur(12px); text-align:center;">
            <div style="font-size:3.2rem; margin-bottom:20px; filter:drop-shadow(0 0 20px rgba(0,229,255,0.3));">🔬</div>
            <h2 style="font-family:'Space Grotesk',sans-serif; font-size:1.8rem;
                       font-weight:700; color:#e0e6f0; margin-bottom:10px;
                       background:linear-gradient(135deg,#00e5ff,#7b61ff);
                       -webkit-background-clip:text; -webkit-text-fill-color:transparent;">Research Command Center</h2>
            <p style="color:#5a6a85; font-family:'JetBrains Mono',monospace;
                      font-size:0.85rem; margin-bottom:36px; max-width:500px; margin-left:auto; margin-right:auto;">
                Enter a research topic in the left panel and click <strong style='color:#00e5ff;'>Run Analysis</strong> to launch the 8-stage pipeline.
            </p>
            <div style="display:flex; gap:12px; justify-content:center; flex-wrap:wrap;">
        """, unsafe_allow_html=True)
        for _, label, _, icon in RIBBON_STEPS[1:]:
            st.markdown(f'<span style="background:rgba(0,229,255,0.06); border:1px solid rgba(0,229,255,0.12); color:#2e3d58; padding:7px 18px; border-radius:100px; font-family:\'JetBrains Mono\',monospace; font-size:0.72rem; display:inline-block; margin:4px;">{icon} {label}</span>', unsafe_allow_html=True)
        st.markdown("</div></div>", unsafe_allow_html=True)
        st.stop()

    # ── Horizontal Stage Ribbon ───────────────────────────────────────────
    has_data = load("papers") is not None
    ribbon_html = '<div class="ribbon-wrap">'
    ribbon_items = []
    for idx, (snum, label, key, icon) in enumerate(RIBBON_STEPS):
        if snum == 0:
            state = "complete" if has_data else "pending"
        else:
            state = get_step_state(snum, key) if key else "pending"
        is_active = st.session_state.active_step == snum
        clickable = (state in ("complete", "awaiting")) or (snum == 0 and has_data)
        dot_cls = state + (" active-ring" if is_active else "")
        label_cls = "active" if is_active else ""
        node_cls = "ribbon-node" + (" clickable" if clickable else "") + (" active" if is_active else "")
        # Use check mark for complete, icon otherwise
        disp = "✓" if state == "complete" else ("▶" if state == "running" else ("◈" if state == "awaiting" else icon))
        conn_cls = "ribbon-connector done" if (idx > 0 and ribbon_items and ribbon_items[-1]["state"] == "complete") else "ribbon-connector"
        if idx > 0:
            ribbon_html += f'<div class="{conn_cls}"></div>'
        ribbon_html += f'<div class="{node_cls}" id="rnode_{snum}"><div class="ribbon-dot {dot_cls}">{disp}</div><div class="ribbon-label {label_cls}">{label}</div></div>'
        ribbon_items.append({"snum": snum, "state": state, "clickable": clickable})
    ribbon_html += '</div>'
    st.markdown(ribbon_html, unsafe_allow_html=True)

    # Invisible nav buttons that map to ribbon clicks via columns
    if not getattr(st.session_state, "is_running_pipeline", False):
        nav_cols = st.columns(len(RIBBON_STEPS))
        for idx, (snum, label, key, _) in enumerate(RIBBON_STEPS):
            if snum == 0:
                state = "complete" if has_data else "pending"
            else:
                state = get_step_state(snum, key) if key else "pending"
            clickable = (state in ("complete", "awaiting")) or (snum == 0 and has_data)
            if clickable:
                with nav_cols[idx]:
                    if st.button(label, key=f"ribbon_nav_{snum}", use_container_width=True,
                                 help=f"Go to {label}"):
                        st.session_state.active_step = snum
                        st.rerun()

    st.markdown("<div style='margin-top:-8px'></div>", unsafe_allow_html=True)
    step = st.session_state.active_step
    
    # ── Step 0: Bloomberg Dashboard ───────────────────────────────────────
    if step == 0:
        papers_data  = load("papers")  or {}
        tree_data    = load("tree")    or {}
        gaps_data    = load("gaps")    or {}
        trends_data  = load("trends")  or {}
        nov_data     = load("novelty") or {}
        sel_gap      = load("user_gap_selection") or {}
        mev_data     = load("methodology_eval") or {}
        paper_list   = papers_data.get("papers", [])
        themes       = tree_data.get("themes", [])
        all_gaps     = gaps_data.get("identified_gaps", [])
        nov_score    = nov_data.get("novelty_score", None)
        topic_str    = st.session_state.pipeline_topic or "Research Topic"

        # ── Top stat strip ────────────────────────────────────────────────
        s1, s2, s3, s4, s5 = st.columns(5)
        def stat_card(col, val, label, color="#00e5ff"):
            col.markdown(f"""
            <div class="dash-stat">
                <div class="dash-stat-value" style="color:{color};">{val}</div>
                <div class="dash-stat-label">{label}</div>
            </div>""", unsafe_allow_html=True)
        qg1_d = (load("qg1") or {}).get("decision", "—")
        qg2_d = (load("qg2") or {}).get("decision", "—")
        qg_col = {"PASS":"#00ffa3","REVISE":"#ff6b35","FAIL":"#ff3355"}
        stat_card(s1, len(paper_list), "Papers Retrieved", "#00e5ff")
        stat_card(s2, len(themes), "Themes Clustered", "#7b61ff")
        stat_card(s3, len(all_gaps), "Gaps Identified", "#ff6b35")
        stat_card(s4, nov_score if nov_score is not None else "—", "Novelty Score", "#00ffa3")
        stat_card(s5, qg1_d, "QG-1 Status", qg_col.get(qg1_d, "#2e3d58"))

        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

        # ── Main 3-panel row ─────────────────────────────────────────────
        left, mid, right = st.columns([1.1, 1.5, 1.1])

        # Left panel: Terminal Data Grid (Papers)
        with left:
            st.markdown('<div class="dash-panel">', unsafe_allow_html=True)
            st.markdown('<div class="dash-panel-title">Paper Index</div>', unsafe_allow_html=True)
            if paper_list:
                import textwrap
                grid_html = textwrap.dedent("""
                <div style="max-height: 440px; overflow-y: auto; padding-right: 8px;">
                    <style>
                        .dg-row { display: flex; align-items: center; padding: 10px 0; border-bottom: 1px solid rgba(0,229,255,0.05); gap: 12px; }
                        .dg-row:last-child { border-bottom: none; }
                        .dg-year { font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #5a6a85; min-width: 36px; }
                        .dg-title { font-family: 'Inter', sans-serif; font-size: 0.8rem; color: #c0cce0; flex: 1; line-height: 1.3; font-weight: 500; }
                        .dg-title-clamp { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
                        .dg-dot { width: 8px; height: 8px; border-radius: 50%; background: #00e5ff; flex-shrink: 0; box-shadow: 0 0 5px rgba(0,229,255,0.4); }
                    </style>
                """)
                # Palette for themes to color the dots based on mapped theme if we have it
                # We can map paper IDs/URLs to themes. Since themes contain complete paper objects in "papers",
                # let's create a map going from paper title/url to theme index.
                paper_to_theme = {}
                tc = ["#7b61ff", "#00ffa3", "#ff6b35", "#ff3355", "#ffb627", "#00e5ff"]
                for i, th in enumerate(themes):
                    c = tc[i % len(tc)]
                    for pt in th.get("papers", []):
                        pid_key = pt.get("title", "") if isinstance(pt, dict) else str(pt)
                        if pid_key: paper_to_theme[pid_key[:30]] = c

                # Sort by year descending
                sorted_papers = sorted(paper_list, key=lambda x: str(x.get("year", "")), reverse=True)

                for p in sorted_papers:
                    pyear = p.get("year", "—")
                    ptitle = p.get("title", "Untitled")
                    pdot_col = paper_to_theme.get(ptitle[:30], "#2e3d58") # Default datagrids dot if unmapped

                    grid_html += textwrap.dedent(f"""
                    <div class="dg-row">
                        <div class="dg-year">{pyear}</div>
                        <div class="dg-dot" style="background: {pdot_col}; box-shadow: 0 0 5px {pdot_col}80;"></div>
                        <div class="dg-title"><div class="dg-title-clamp" title="{ptitle}">{ptitle}</div></div>
                    </div>
                    """)
                grid_html += "</div>"
                st.markdown(grid_html, unsafe_allow_html=True)
            else:
                st.markdown('<div style="color:#2e3d58;font-size:0.82rem;'
                            'padding:30px 0;text-align:center;">No papers yet</div>',
                            unsafe_allow_html=True)
            if st.button("Browse All Papers \u2192", key="dash_papers"):
                st.session_state.active_step = 1
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        # Centre: Force-directed thematic knowledge web
        with mid:
            st.markdown('<div class="dash-panel">', unsafe_allow_html=True)
            st.markdown('<div class="dash-panel-title">Thematic Knowledge Web</div>',
                        unsafe_allow_html=True)
            if themes:
                _dn, _de = [], []
                _short_top = topic_str[:22] + ("\u2026" if len(topic_str) > 22 else "")
                _dn.append(Node(
                    id="root", label=_short_top, size=34,
                    color="#00e5ff",
                    font={"color": "#0a0e17", "size": 12, "face": "Space Grotesk", "bold": True},
                    shape="ellipse", title=topic_str
                ))
                _tc = ["#7b61ff", "#00ffa3", "#ff6b35", "#ff3355", "#ffb627", "#00e5ff"]
                _pc = ["rgba(123,97,255,0.5)", "rgba(0,255,163,0.5)", "rgba(255,107,53,0.5)",
                       "rgba(255,51,85,0.5)",  "rgba(255,182,39,0.5)", "rgba(0,229,255,0.5)"]
                for _i, _th in enumerate(themes):
                    _tid    = _th.get("theme_id", "T{}".format(_i))
                    _tname  = _th.get("theme_name", "Theme")
                    _tpaps  = _th.get("papers", [])
                    _pcount = len(_tpaps)
                    _sname  = _tname[:16] + ("\u2026" if len(_tname) > 16 else "")
                    _tlabel = "{}\n({}p)".format(_sname, _pcount)
                    _dn.append(Node(
                        id=_tid, label=_tlabel,
                        size=20 + min(_pcount * 2, 16),
                        color=_tc[_i % len(_tc)],
                        font={"color": "#fff", "size": 11, "face": "Inter"},
                        shape="box",
                        title="{} \u2014 {} papers".format(_tname, _pcount)
                    ))
                    _de.append(Edge(
                        source="root", target=_tid,
                        color="rgba(0,229,255,0.15)", width=2,
                        arrows="to", smooth={"type": "dynamic"}
                    ))
                    # Satellite paper nodes (all per theme)
                    for _j, _pap in enumerate(_tpaps):
                        _pt = _pap.get("title", "Untitled") if isinstance(_pap, dict) else str(_pap)
                        _py = _pap.get("year", "")          if isinstance(_pap, dict) else ""
                        _pl = _pt[:18] + ("\u2026" if len(_pt) > 18 else "")
                        _pid = "{}_p{}".format(_tid, _j)
                        _dn.append(Node(
                            id=_pid, label=_pl, size=9,
                            color=_pc[_i % len(_pc)],
                            font={"color": "#c0cce0", "size": 9, "face": "Inter"},
                            shape="dot",
                            title="{} ({})".format(_pt, _py)
                        ))
                        _de.append(Edge(
                            source=_tid, target=_pid,
                            color="rgba(46,61,88,0.5)", width=1,
                            arrows="", smooth={"type": "dynamic"}
                        ))
                _dcfg = Config(
                    width="100%", height=430,
                    directed=False, physics=True, hierarchical=False,
                    nodeHighlightBehavior=True, highlightColor="#00e5ff",
                    backgroundColor="rgba(0,0,0,0)", stabilization=True
                )
                agraph(nodes=_dn, edges=_de, config=_dcfg)
            else:
                st.markdown('<div style="color:#2e3d58;font-size:0.82rem;'
                            'padding:60px 0;text-align:center;">'
                            'Run pipeline to see thematic web</div>',
                            unsafe_allow_html=True)
            if st.button("Explore Full Tree \u2192", key="dash_tree"):
                st.session_state.active_step = 2
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        # Right: Gaps + novelty
        with right:
            st.markdown('<div class="dash-panel">', unsafe_allow_html=True)
            st.markdown('<div class="dash-panel-title">Research Gaps</div>', unsafe_allow_html=True)
            if all_gaps:
                llm_sel = gaps_data.get("selected_gap","")
                for g in all_gaps[:4]:
                    is_sel = g.get("gap_id") == llm_sel
                    border = "border:1px solid rgba(0,229,255,0.25);" if is_sel else ""
                    st.markdown(f"""
                    <div class="dash-gap-chip" style="{border}">
                        <strong>{g.get('gap_id','')}</strong>
                        {'<span style="color:#00e5ff;font-size:0.65rem;margin-left:6px;">◈ LLM</span>' if is_sel else ''}<br>
                        {g.get('description','')[:90]}{'…' if len(g.get('description',''))>90 else ''}
                    </div>""", unsafe_allow_html=True)
            else:
                st.markdown('<div style="color:#2e3d58;font-size:0.82rem;font-family:\'JetBrains Mono\',monospace;">No gaps identified yet</div>', unsafe_allow_html=True)

            if nov_score is not None:
                st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
                bar_col = "#00ffa3" if nov_score>=70 else ("#ff6b35" if nov_score>=40 else "#ff3355")
                st.markdown(f"""
                <div style="background:rgba(0,229,255,0.04); border:1px solid var(--border-subtle);
                             border-radius:10px; padding:14px; text-align:center;">
                    <div style="font-family:'Space Grotesk',sans-serif; font-size:2.2rem; font-weight:700;
                                color:{bar_col}; line-height:1;">{nov_score}</div>
                    <div style="font-family:'JetBrains Mono',monospace; font-size:0.62rem;
                                color:#2e3d58; margin-top:4px; text-transform:uppercase;">Novelty Score</div>
                    <div style="height:4px; background:#0d1526; border-radius:2px; margin-top:10px; overflow:hidden;">
                        <div style="height:100%; width:{nov_score}%; background:{bar_col}; border-radius:2px;"></div>
                    </div>
                </div>""", unsafe_allow_html=True)

            if st.button("Gap Selection →", key="dash_gaps"):
                st.session_state.active_step = 4
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        # ── Bottom row: Trend pills + Methodology ─────────────────────────
        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
        bot_l, bot_r = st.columns([1.5, 1])
        with bot_l:
            st.markdown('<div class="dash-panel">', unsafe_allow_html=True)
            st.markdown('<div class="dash-panel-title">Dominant Trends</div>', unsafe_allow_html=True)
            dominant = trends_data.get("dominant_clusters", [])
            emerging = trends_data.get("emerging_trends", [])
            if dominant or emerging:
                pills = ""
                for t in dominant[:4]:
                    pills += f'<span style="background:rgba(123,97,255,0.1); color:#9f87ff; border:1px solid rgba(123,97,255,0.2); padding:5px 14px; border-radius:100px; font-size:0.75rem; margin:3px; display:inline-block;">{t[:50]}</span>'
                for t in emerging[:3]:
                    pills += f'<span style="background:rgba(0,229,255,0.06); color:#5a6a85; border:1px solid rgba(0,229,255,0.1); padding:5px 14px; border-radius:100px; font-size:0.75rem; margin:3px; display:inline-block; font-style:italic;">{t[:50]}</span>'
                st.markdown(f'<div style="line-height:2;">{pills}</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div style="color:#2e3d58;font-size:0.82rem;font-family:\'JetBrains Mono\',monospace;">No trend data yet</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with bot_r:
            st.markdown('<div class="dash-panel">', unsafe_allow_html=True)
            st.markdown('<div class="dash-panel-title">Selected Methodology</div>', unsafe_allow_html=True)
            win_meth = mev_data.get("winning_methodology") or load("methodology_a") or {}
            if win_meth:
                metrics = win_meth.get("evaluation_metrics", [])
                datasets = win_meth.get("suggested_datasets", [])
                tools = win_meth.get("tools_and_frameworks", [])
                for label_t, items in [("Metrics", metrics[:3]), ("Datasets", datasets[:2]), ("Tools", tools[:3])]:
                    if items:
                        st.markdown(f'<div style="margin-bottom:10px;"><div style="font-family:\'JetBrains Mono\',monospace; font-size:0.62rem; color:#2e3d58; text-transform:uppercase; margin-bottom:4px;">{label_t}</div><div style="color:#9aaac2; font-size:0.82rem;">{" · ".join(items)}</div></div>', unsafe_allow_html=True)
                if st.button("View Grant →", key="dash_grant"):
                    st.session_state.active_step = 7
                    st.rerun()
            else:
                st.markdown('<div style="color:#2e3d58;font-size:0.82rem;font-family:\'JetBrains Mono\',monospace;">Select a gap to generate methodology</div>', unsafe_allow_html=True)
                if st.button("Select Gap →", key="dash_gap2"):
                    st.session_state.active_step = 4
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    # ── Step 1: Literature ────────────────────────────────────────────────
    elif step == 1:
        papers_data = load("papers") or {}
        paper_list = papers_data.get("papers", [])

        st.markdown('<h2 style="font-family:\'Space Grotesk\',sans-serif; font-size:1.4rem; color:#e0e6f0; font-weight:600;">📄 Retrieved Literature</h2>', unsafe_allow_html=True)

        if paper_list:
            sources = set([p.get("url").split("/")[2] if p.get("url") and isinstance(p.get("url"), str) and "//" in p.get("url") else "Unknown" for p in paper_list])
            years = [p.get("year") for p in paper_list if p.get("year")]
            yr_str = f"{min(years)}\u2013{max(years)}" if years else "N/A"

            c1, c2, c3 = st.columns(3)
            c1.metric("Total Papers", len(paper_list))
            c2.metric("API Sources", len(sources))
            c3.metric("Year Range", yr_str)

        for p in paper_list:
            source_badge = f'<span class="source-badge {get_source_badge_class(p.get("url", ""))}">{get_source_name(p.get("url", ""))}</span>'
            st.markdown(f"""
            <div class="paper-card">
                <h4>{p.get('title', 'Unknown')}</h4>
                <span class="year-badge">{p.get('year', 'N/A')}</span>{source_badge}
                <p style="margin-top:12px; color:#9aaac2; line-height:1.65; font-size:0.92rem;">{p.get('summary', '')}</p>
                <p style="color:#7b61ff; font-size:0.9rem; margin-top:8px;"><strong style="color:#5a6a85;">Contribution:</strong> {p.get('contribution', '')}</p>
                <a href="{p.get('url', '#')}" style="color:#00e5ff; font-size:0.82rem; font-family:'JetBrains Mono',monospace; text-decoration:none;">⬡ Source Link &rarr;</a>
            </div>
            """, unsafe_allow_html=True)

    elif step == 2:
        tree = load("tree") or {}
        if tree and tree.get("themes"):
            nodes = []
            edges = []
            
            root_val = tree.get("root", "Topic string")
            root_label = root_val[:30] + "\\n" + root_val[30:] if len(root_val) > 30 else root_val
            nodes.append(Node(
                id="root",
                label=root_label,
                size=16,
                color="#00e5ff",
                font={"color": "#0a0e17", "size": 10, "face": "Space Grotesk"},
                shape="ellipse",
                title=root_val
            ))

            theme_colors = ["#7b61ff", "#00e5ff", "#00ffa3", "#ff6b35", "#ff3355"]
            paper_colors = ["rgba(123,97,255,0.55)", "rgba(0,229,255,0.55)", "rgba(0,255,163,0.55)", "rgba(255,107,53,0.55)", "rgba(255,51,85,0.55)"]
            
            for i, theme in enumerate(tree.get("themes", [])):
                theme_id = theme.get("theme_id", f"T{i}")
                theme_name = theme.get("theme_name", "Theme")
                papers = theme.get("papers", [])
                
                t_color = theme_colors[i % len(theme_colors)]
                p_color = paper_colors[i % len(paper_colors)]
                
                t_label = theme_name[:25] + "\\n" + theme_name[25:] if len(theme_name) > 25 else theme_name
                t_title = f"{theme_name} — {len(papers)} papers"
                if len(papers) == 0:
                    t_title += " (no papers)"
                    
                nodes.append(Node(
                    id=theme_id,
                    label=t_label,
                    size=8,
                    color=t_color,
                    font={"color": "#0a0e17", "size": 8, "face": "Inter", "bold": True},
                    shape="box",
                    title=t_title
                ))

                edges.append(Edge(
                    source="root",
                    target=theme_id,
                    color="rgba(0,229,255,0.25)",
                    width=2,
                    arrows="to",
                    smooth={"type": "dynamic"},
                    length=300
                ))
                
                for p_idx, paper in enumerate(papers):
                    title = paper.get("title", "Untitled paper") if isinstance(paper, dict) else str(paper)
                    year = paper.get("year", "") if isinstance(paper, dict) else ""
                    summary = paper.get("summary", "") if isinstance(paper, dict) else ""
                    
                    p_label = title[:35] + "…" if len(title) > 35 else title
                    p_id = f"{theme_id}_{p_idx}"
                    
                    p_title = f"{title}\\n{year}\\n\\n{summary[:150]}…"
                    
                    nodes.append(Node(
                        id=p_id,
                        label=p_label,
                        size=14,
                        color=p_color,
                        font={"color": "#c0cce0", "size": 11, "face": "Inter"},
                        shape="dot",
                        title=p_title
                    ))

                    edges.append(Edge(
                        source=theme_id,
                        target=p_id,
                        color="rgba(46,61,88,0.5)",
                        width=1,
                        arrows="",
                        smooth={"type": "dynamic"}
                    ))
                    
            c_graph, c_panel = st.columns([1.6, 1.4], gap="large")

            with c_graph:
                st.markdown('<div class="dash-panel-title" style="margin-top:0;">Interactive Knowledge Web</div>', unsafe_allow_html=True)
                config = Config(
                    width="100%",
                    height=800,
                    directed=False,
                    physics=True,
                    hierarchical=False,
                    nodeHighlightBehavior=True,
                    highlightColor="#00e5ff",
                    backgroundColor="rgba(0,0,0,0)",
                    stabilization=True,
                )
                
                agraph(nodes=nodes, edges=edges, config=config)
                
                directions = tree.get("emerging_directions", [])
                if directions:
                    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
                    st.markdown('<p style="font-family:\\\'Space Grotesk\\\',sans-serif; font-size:0.75rem; letter-spacing:0.1em; text-transform:uppercase; color:#2e3d58; margin-bottom:8px;">Emerging Macros</p>', unsafe_allow_html=True)
                    pills_html = []
                    for d in directions:
                        pills_html.append(f'<span style="background:rgba(0,229,255,0.08); color:#00e5ff; border:1px solid rgba(0,229,255,0.18); padding:5px 14px; border-radius:100px; font-size:0.8rem; margin:4px; display:inline-block; font-family:\\\'JetBrains Mono\\\',monospace;">{d}</span>')
                    st.markdown("".join(pills_html), unsafe_allow_html=True)
                
                st.markdown("---")
                with st.expander("Raw tree JSON", expanded=False):
                    st.json(tree)

            with c_panel:
                st.markdown('<div class="dash-panel-title" style="margin-top:0;">Cluster Synthesis & Contributions</div>', unsafe_allow_html=True)
                
                # Extract themes and render them explicitly
                panel_html = '<div style="max-height: 850px; overflow-y: auto; padding-right: 12px;">'
                
                for i, theme in enumerate(tree.get("themes", [])):
                    t_name = theme.get("theme_name", "Theme")
                    t_papers = theme.get("papers", [])
                    t_color = theme_colors[i % len(theme_colors)]
                    
                    panel_html += (
                        f'<div style="background: rgba(255,255,255,0.02); border-left: 3px solid {t_color}; padding: 14px; margin-bottom: 16px; border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">'
                        f'<div style="color: {t_color}; font-size: 0.9rem; font-family: \'Space Grotesk\', sans-serif; font-weight: 700; margin-bottom: 12px; line-height: 1.3;">'
                        f'{t_name} <span style="color:#5a6a85; font-size:0.75rem; font-family:\'JetBrains Mono\',monospace;">({len(t_papers)} papers)</span>'
                        f'</div>'
                    )
                    
                    for p in t_papers:
                        ptitle = p.get("title", "Untitled") if isinstance(p, dict) else str(p)
                        pcontrib = p.get("contribution", p.get("summary", "No contribution noted.")) if isinstance(p, dict) else ""
                        
                        panel_html += (
                            f'<div style="margin-bottom: 12px; border-bottom: 1px dashed rgba(255,255,255,0.05); padding-bottom: 12px;">'
                            f'<div style="color: #c0cce0; font-size: 0.8rem; font-weight: 500; line-height: 1.4; margin-bottom: 6px;">{ptitle}</div>'
                            f'<div style="color: #8c9baf; font-size: 0.75rem; font-family: \'Inter\', sans-serif; line-height: 1.5; background: #0a0e17; padding: 10px; border-radius: 4px; border: 1px solid rgba(0,229,255,0.1);">'
                            f'<div style="color:#00e5ff; font-weight: 600; font-family: \'JetBrains Mono\', monospace; font-size: 0.65rem; text-transform: uppercase; margin-bottom: 4px;">Key Contribution</div>'
                            f'{pcontrib}'
                            f'</div></div>'
                        )
                    
                    panel_html += '</div>'
                
                panel_html += '</div>'
                st.markdown(panel_html, unsafe_allow_html=True)
        else:
            st.info("No tree data available.")

    elif step == 3:
        trends_data = load("trends") or {}
        gaps_data = load("gaps") or {}

        c1, c2 = st.columns(2)
        with c1:
            st.markdown('<p style="font-family:\'Space Grotesk\',sans-serif; font-weight:600; font-size:1rem; color:#e0e6f0; margin-bottom:12px;">📈 Dominant Trends</p>', unsafe_allow_html=True)
            for c in trends_data.get("dominant_clusters", []):
                st.markdown(f'<div class="paper-card" style="padding:12px 16px; border-left:3px solid #7b61ff;"><strong style="color:#9f87ff;">{c}</strong></div>', unsafe_allow_html=True)
            for t in trends_data.get("emerging_trends", []):
                st.markdown(f'<div class="paper-card" style="padding:12px 16px;"><em style="color:#5a6a85;">{t}</em></div>', unsafe_allow_html=True)

        with c2:
            st.markdown('<p style="font-family:\'Space Grotesk\',sans-serif; font-weight:600; font-size:1rem; color:#e0e6f0; margin-bottom:12px;">🔍 Identified Gaps</p>', unsafe_allow_html=True)
            selected = gaps_data.get('selected_gap', '?')
            for g in gaps_data.get("identified_gaps", []):
                hl = "gap-auto-selected" if g.get('gap_id') == selected else ""
                rank = g.get('priority_rank', '')
                fnote = g.get('feasibility_note', '')
                f_html = f'<p style="color:#2e3d58; font-size:0.82rem; margin-top:8px; font-family:\'JetBrains Mono\',monospace;"><em>Rank {rank}</em> — {fnote}</p>' if fnote else ''
                html_str = (
                    f'<div class="gap-card {hl}">'
                    f'<strong style="color:#ff6b35; font-family:\'JetBrains Mono\',monospace; font-size:0.85rem;">{g.get("gap_id", "")}</strong>'
                    f'<p style="color:#9aaac2; margin: 8px 0; line-height:1.6; font-size:0.9rem;">{g.get("description", "")}</p>'
                    f'{f_html}'
                    f'</div>'
                )
                st.markdown(html_str, unsafe_allow_html=True)
                
        st.markdown("---")
        if st.button("Proceed to Gap Selection →"):
            st.session_state.active_step = 4
            st.rerun()

    elif step == 4:
        st.markdown('<div class="gate-banner">Your input is needed — select or define the research gap to develop.</div>', unsafe_allow_html=True)
        gaps_data = load("gaps") or {}
        all_gaps = gaps_data.get("identified_gaps", [])
        llm_selected_id = gaps_data.get("selected_gap", "")
        
        if all_gaps:
            for g in all_gaps:
                gid = g.get("gap_id")
                rank = g.get("priority_rank", 3)
                stars = "★" * (4 - rank) + "☆" * (rank - 1) if isinstance(rank, int) and 1 <= rank <= 3 else ""
                llm_badge = '<span style="background:linear-gradient(135deg,rgba(0,229,255,0.2),rgba(123,97,255,0.2)); border:1px solid rgba(0,229,255,0.3); color:#00e5ff; padding:2px 10px; border-radius:100px; font-size:0.72rem; margin-left:8px; font-family:\'JetBrains Mono\',monospace;">⬡ LLM Recommended</span>' if gid == llm_selected_id else ''

                with st.container():
                    html_str = (
                        f'<div class="paper-card" style="position:relative;">'
                        f'<div style="display:flex; justify-content:space-between; align-items:center;">'
                        f'<div>'
                        f'<strong style="background:rgba(0,229,255,0.1); color:#00e5ff; padding:3px 10px; border-radius:6px; font-family:\'JetBrains Mono\',monospace; font-size:0.82rem;">{gid}</strong>'
                        f'{llm_badge}'
                        f'</div>'
                        f'<div style="color:#ff6b35; letter-spacing:2px;">{stars}</div>'
                        f'</div>'
                        f'<p style="margin:12px 0; color:#9aaac2; line-height:1.65; font-size:0.92rem;">{g.get("description", "")}</p>'
                        f'<p style="color:#2e3d58; font-size:0.82rem; font-family:\'JetBrains Mono\',monospace;">{g.get("feasibility_note", "")}</p>'
                        f'</div>'
                    )
                    st.markdown(html_str, unsafe_allow_html=True)
                    if st.button(f"Select {gid}", key=f"sel_{gid}"):
                        selection = {
                            "gap_id": gid,
                            "source": "user_selected" if gid != llm_selected_id else "llm_suggested",
                            "description": g["description"],
                            "is_custom": False
                        }
                        save("user_gap_selection", selection)
                        st.success("Gap confirmed — pipeline continuing")
                        time.sleep(1)
                        # Trigger methodology run
                        from agents.methodology_agent import run as run_methodology
                        from agents.methodology_evaluator import run as run_evaluator
                        topic = st.session_state.pipeline_topic
                        
                        meth_a = run_methodology(selection["description"], topic)
                        save("methodology_a", meth_a)
                        st.session_state.methodology_a = meth_a
                        
                        sorted_gaps = sorted(all_gaps, key=lambda x: x.get("priority_rank", 3))
                        chs = [x for x in sorted_gaps if x["gap_id"] != gid]
                        if chs:
                            meth_b = run_methodology(chs[0]["description"], topic)
                            save("methodology_b", meth_b)
                            st.session_state.methodology_b = meth_b
                            eval_res = run_evaluator(topic, selection["description"], meth_a, chs[0]["description"], meth_b)
                            save("methodology_eval", eval_res)
                        
                        st.session_state.active_step = 5
                        st.rerun()
                        
            st.markdown("---")
            st.markdown('<div class="paper-card" style="border:1px dashed rgba(0,229,255,0.2);"><h4 style="color:#7b61ff;">✦ Define your own gap</h4><p style="color:#5a6a85; font-size:0.85rem; margin:0;">Identify a gap not listed above and describe it below.</p></div>', unsafe_allow_html=True)
            custom_desc = st.text_area("Describe a research gap you've identified that isn't listed above")
            if st.button("Use my gap →", disabled=not custom_desc.strip()):
                selection = {
                    "gap_id": "custom",
                    "source": "user_custom",
                    "description": custom_desc.strip(),
                    "is_custom": True
                }
                save("user_gap_selection", selection)
                st.success("Gap confirmed — pipeline continuing")
                time.sleep(1)
                
                from agents.methodology_agent import run as run_methodology
                from agents.methodology_evaluator import run as run_evaluator
                topic = st.session_state.pipeline_topic
                
                meth_a = run_methodology(selection["description"], topic)
                save("methodology_a", meth_a)
                st.session_state.methodology_a = meth_a
                
                sorted_gaps = sorted(all_gaps, key=lambda x: x.get("priority_rank", 3))
                if sorted_gaps:
                    meth_b = run_methodology(sorted_gaps[0]["description"], topic)
                    save("methodology_b", meth_b)
                    st.session_state.methodology_b = meth_b
                    eval_res = run_evaluator(topic, selection["description"], meth_a, sorted_gaps[0]["description"], meth_b)
                    save("methodology_eval", eval_res)
                
                st.session_state.active_step = 5
                st.rerun()

    elif step == 5:
        mev = load("methodology_eval") or {}
        meth_a = load("methodology_a") or {}
        meth_b = load("methodology_b") or {}
        
        def render_meth(m, label, is_winner):
            cls = "methodology-winner" if is_winner else "methodology-loser"
            badge = '<span style="background:rgba(0,255,163,0.15); color:#00ffa3; border:1px solid rgba(0,255,163,0.3); padding:3px 12px; border-radius:100px; font-size:0.72rem; font-family:\'JetBrains Mono\',monospace; float:right;">✓ Selected</span>' if is_winner else '<span style="background:rgba(46,61,88,0.5); color:#2e3d58; border:1px solid #2e3d58; padding:3px 12px; border-radius:100px; font-size:0.72rem; font-family:\'JetBrains Mono\',monospace; float:right;">Challenger</span>'
            html = f'<div class="paper-card {cls}"><h4>{label}</h4>{badge}<div style="clear:both; margin-top:16px;">'
            if m:
                def row(k, v): return f'<div style="margin-bottom:10px;"><span style="color:#2e3d58; font-size:0.75rem; font-family:\'JetBrains Mono\',monospace; text-transform:uppercase; letter-spacing:0.06em;">{k}</span><br><span style="color:#9aaac2; font-size:0.9rem;">{v}</span></div>'
                html += row("Datasets", ', '.join(m.get('suggested_datasets', [])))
                html += row("Metrics", ', '.join(m.get('evaluation_metrics', [])))
                html += row("Baselines", ', '.join(m.get('baseline_models', [])))
                html += row("Experimental Design", m.get('experimental_design', ''))
                html += row("Tools / Frameworks", ', '.join(m.get('tools_and_frameworks', [])))
            html += "</div></div>"
            st.markdown(html, unsafe_allow_html=True)
            
        if mev and mev.get("parallel_was_run") and meth_a and meth_b:
            # We must stack them vertically
            win_label = mev.get("winner")
            render_meth(meth_a, "Primary Gap Methodology", win_label == "A")
            
            st.markdown(f'<div class="pull-quote">{mev.get("reasoning", "")}</div>', unsafe_allow_html=True)
            
            render_meth(meth_b, "Challenger Gap Methodology", win_label == "B")
            
            if st.button("Use challenger methodology instead"):
                mev["winner"] = "B" if win_label == "A" else "A"
                mev["winning_methodology"] = meth_b if win_label == "A" else meth_a
                save("methodology_eval", mev)
                for k in ["format_match", "grant", "novelty"]:
                    st.session_state[k] = None
                    p = f"cache/{k}.json"
                    if os.path.exists(p): os.remove(p)
                st.rerun()
            
            st.markdown("---")
            if st.button("Proceed to Format Selection →"):
                st.session_state.active_step = 6
                st.rerun()
        else:
            meth = mev.get("winning_methodology") if mev else meth_a
            if meth:
                render_meth(meth, "Experimental Methodology", 1)
                st.markdown("---")
                if st.button("Proceed to Format Selection →"):
                    st.session_state.active_step = 6
                    st.rerun()

    elif step == 6:
        st.markdown('<div class="gate-banner">Your input is needed — select a grant format.</div>', unsafe_allow_html=True)
        
        fm = load("format_match")
        if not fm:
            with st.spinner("Analyzing methodology to recommend best grant format..."):
                meth = load("methodology_eval").get("winning_methodology") if load("methodology_eval") else load("methodology_a")
                fm = run_format_matcher(st.session_state.pipeline_topic, meth, st.session_state.formats, None)
                save("format_match", fm)
                st.rerun()
                
        llm_default = fm.get("selected_format_id")
        formats = st.session_state.formats
        
        # Grid layout
        cols = st.columns(3)
        for i, (fid, fmt) in enumerate(formats.items()):
            with cols[i % 3]:
                is_rec = (fid == llm_default)
                cls = "format-card-recommended" if is_rec else "paper-card"
                badge = '<br><span style="background:linear-gradient(135deg,rgba(0,229,255,0.18),rgba(123,97,255,0.18)); border:1px solid rgba(0,229,255,0.3); color:#00e5ff; padding:3px 12px; border-radius:100px; font-size:0.7rem; font-family:\'JetBrains Mono\',monospace;">⬡ LLM Recommended</span>' if is_rec else ''
                award = f'<span style="background:rgba(0,255,163,0.1); color:#00ffa3; border:1px solid rgba(0,255,163,0.2); padding:3px 10px; border-radius:100px; font-size:0.72rem; font-family:\'JetBrains Mono\',monospace;">{fmt.get("typical_award_usd", "Varies")}</span>'
                emph = fmt.get("emphasis", "")
                emph_html = "".join([f'<span style="background:rgba(0,229,255,0.07); color:#5a6a85; border:1px solid rgba(0,229,255,0.12); padding:2px 8px; border-radius:6px; font-size:0.72rem; margin-right:4px; font-family:\'JetBrains Mono\',monospace;">{e}</span>' for e in emph.split()[:3]])

                st.markdown(f"""
                <div class="{cls}" style="padding:16px; margin-bottom:12px;">
                    <h4 style="margin:0; font-family:'Space Grotesk',sans-serif;">{fmt['name']}</h4>
                    <p style="color:#2e3d58; font-size:0.8rem; margin:4px 0; font-family:'JetBrains Mono',monospace;">{fmt['funding_body']}</p>
                    {award} {badge}
                    <div style="margin-top:12px;">{emph_html}</div>
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"Select {fid}", key=f"sel_{fid}"):
                    st.session_state.user_format_override = fid
                    save("format_match", run_format_matcher(st.session_state.pipeline_topic, load("methodology_eval").get("winning_methodology") if load("methodology_eval") else load("methodology_a"), st.session_state.formats, fid))
                    st.success("Format confirmed — generating grant")
                    
                    from agents.grant_agent import run as run_grant
                    from agents.novelty_agent import run as run_novelty
                    
                    topic = st.session_state.pipeline_topic
                    user_gap = load("user_gap_selection") or {}
                    meth_data = load("methodology_eval").get("winning_methodology") if load("methodology_eval") else load("methodology_a")
                    format_match = load("format_match")
                    
                    grant = run_grant(topic, user_gap.get("description", ""), meth_data, format_match)
                    save("grant", grant)
                    
                    novelty = run_novelty(grant, load("tree"))
                    save("novelty", novelty)
                    
                    st.session_state.active_step = 7
                    st.rerun()

    elif step == 7:
        grant_data = load("grant") or {}
        fm = load("format_match") or {}
        if grant_data:
            topic = st.session_state.pipeline_topic
            fmt_id = fm.get("selected_format_id", "Unknown")
            fmt_name = (st.session_state.formats or {}).get(fmt_id, {}).get("name", fmt_id)
            is_auto = "" if st.session_state.user_format_override else " — LLM selected"
            
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f'<h1 style="font-family:\'Space Grotesk\',sans-serif; font-size:1.6rem; font-weight:700; color:#e0e6f0;">{topic}</h1>', unsafe_allow_html=True)
                st.markdown(f'<span style="background:rgba(0,229,255,0.08); color:#00e5ff; border:1px solid rgba(0,229,255,0.2); padding:4px 12px; border-radius:100px; font-size:0.78rem; font-family:\'JetBrains Mono\',monospace;">Format: {fmt_id}{is_auto}</span>', unsafe_allow_html=True)
            with c2:
                # ── PDF download ──────────────────────────────────────────
                try:
                    pdf_bytes = generate_pdf_bytes(grant_data, topic, fmt_name)
                    st.download_button(
                        label="⬇ Download as PDF",
                        data=pdf_bytes,
                        file_name="grant_proposal.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                except Exception as _pdf_err:
                    st.warning(f"PDF generation unavailable: {_pdf_err}")

                # ── LaTeX source download ─────────────────────────────────
                tex_source = generate_latex_source(grant_data, topic, fmt_name)
                st.download_button(
                    label="⬇ Download as LaTeX (.tex)",
                    data=tex_source,
                    file_name="grant_proposal.tex",
                    mime="text/x-tex",
                    use_container_width=True,
                )

                # ── Raw JSON fallback ─────────────────────────────────────
                with st.expander("Raw JSON export"):
                    st.download_button(
                        "Download JSON",
                        data=json.dumps(grant_data, indent=2),
                        file_name="grant_proposal.json",
                        mime="application/json",
                    )
                
            st.markdown("---")
            for key, val in grant_data.items():
                if key in ["title", "format_used", "sections"]: continue
                title = key.replace("_", " ").title()
                if isinstance(val, list): val = "<br>• " + "<br>• ".join(str(v) for v in val)
                st.markdown(f'<div class="grant-section"><h3>{title}</h3><p>{val}</p></div>', unsafe_allow_html=True)
                
            if "sections" in grant_data:
                for title, content in grant_data["sections"].items():
                    if isinstance(content, str):
                        content = content.replace("\\n", "<br>")
                    st.markdown(f'<div class="grant-section"><h3>{title}</h3><p>{content}</p></div>', unsafe_allow_html=True)
        else:
            st.info("No grant generated yet.")

    elif step == 8:
        nov = load("novelty") or {}
        if nov:
            score = nov.get("novelty_score", 0)

            # Colour the bar based on score
            if score >= 70:
                bar_color = "#00ffa3"
            elif score >= 40:
                bar_color = "#ff6b35"
            else:
                bar_color = "#ff3355"

            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=score,
                number={
                    "font": {"size": 64, "family": "Space Grotesk", "color": bar_color},
                    "suffix": "/100"
                },
                domain={'x': [0, 1], 'y': [0, 1]},
                gauge={
                    'axis': {
                        'range': [0, 100],
                        'tickcolor': '#2e3d58',
                        'tickfont': {'color': '#2e3d58', 'size': 11, 'family': 'JetBrains Mono'},
                    },
                    'bar': {'color': bar_color, 'thickness': 0.25},
                    'bgcolor': '#0d1526',
                    'borderwidth': 0,
                    'steps': [
                        {'range': [0,  40], 'color': 'rgba(255,51,85,0.15)'},
                        {'range': [40, 70], 'color': 'rgba(255,107,53,0.15)'},
                        {'range': [70,100], 'color': 'rgba(0,255,163,0.12)'},
                    ],
                    'threshold': {
                        'line': {'color': bar_color, 'width': 2},
                        'thickness': 0.75,
                        'value': score
                    }
                }
            ))
            fig.update_layout(
                height=320,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font={'color': '#e0e6f0', 'family': 'Space Grotesk'},
                margin=dict(t=20, b=20, l=20, r=20)
            )
            st.plotly_chart(fig, use_container_width=True)

            st.markdown(f'<div class="pull-quote">{nov.get("score_justification", "")}</div>', unsafe_allow_html=True)

            st.markdown('<p style="font-family:\'Space Grotesk\',sans-serif; font-weight:600; font-size:1rem; color:#e0e6f0; margin:16px 0 8px;">🔗 Closest Existing Papers</p>', unsafe_allow_html=True)
            closest = nov.get("closest_papers", [])
            for p in closest:
                st.markdown(f"""
                <div class="paper-card">
                    <h4>{p}</h4>
                    <p style="color:#5a6a85; font-style:italic; font-size:0.88rem; margin-top:6px;">{nov.get('similarity_reasoning', '')}</p>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No novelty score generated yet.")

# ── Debug Console (Full Width at Bottom) ─────────────────────────────────────
st.markdown("---")
with st.expander("⬡ Terminal Logs", expanded=False):
    if not st.session_state.debug_logs:
        st.markdown(
            '<div style="background:#070b14; border:1px solid rgba(0,229,255,0.06); border-radius:10px; padding:16px; font-family:\'JetBrains Mono\',monospace; font-size:0.8rem; color:#2e3d58;">'
            '<span style="color:#2e3d58;">// </span>No pipeline logs yet — run an analysis to see output here.'
            '</div>',
            unsafe_allow_html=True
        )
    else:
        log_html = '<div style="background:#070b14; border:1px solid rgba(0,229,255,0.06); border-radius:10px; padding:16px; font-family:\'JetBrains Mono\',monospace; font-size:0.78rem; max-height:400px; overflow-y:auto; line-height:1.7;">'
        for ts, level, msg in st.session_state.debug_logs:
            color = "#2e3d58"
            if level == "stage":   color = "#00e5ff"
            elif level == "error": color = "#ff3355"
            elif level == "warning": color = "#ff6b35"
            elif level == "success": color = "#00ffa3"
            log_html += f'<div style="margin-bottom:2px;"><span style="color:#1a2540; font-size:0.7rem;">[{ts}]</span> <span style="color:#2e3d58;">// </span><span style="color:{color};">{msg}</span></div>'
        log_html += '</div>'
        st.markdown(log_html, unsafe_allow_html=True)