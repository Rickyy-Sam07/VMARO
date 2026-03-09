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

# ── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="VMARO Research Orchestrator", layout="wide")

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .main-title {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.4rem;
        font-weight: 700;
        margin-bottom: 0;
    }
    .subtitle {
        color: #888;
        font-size: 1rem;
        margin-top: -8px;
        margin-bottom: 24px;
    }
    .paper-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #2a2a4a;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 12px;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .paper-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(102, 126, 234, 0.15);
    }
    .paper-card h4 { color: #a78bfa; margin-bottom: 8px; }
    .paper-card .year-badge {
        display: inline-block;
        background: #7c3aed33;
        color: #c4b5fd;
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 500;
    }
    .gap-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border-left: 4px solid #f59e0b;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 10px;
        transition: transform 0.2s;
    }
    .gap-card:hover {
        transform: translateX(4px);
    }
    .score-big {
        font-size: 4rem;
        font-weight: 700;
        text-align: center;
        line-height: 1;
    }
    .score-label {
        text-align: center;
        font-size: 1rem;
        color: #888;
        margin-top: 4px;
    }

    /* Grant sections */
    .grant-section { margin-bottom: 20px; }
    .grant-section h3 {
        color: #a78bfa;
        border-bottom: 1px solid #2a2a4a;
        padding-bottom: 6px;
    }

    /* Pipeline stage badges */
    .stage-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 500;
        margin: 3px 0;
    }
    .stage-complete {
        background: rgba(34, 197, 94, 0.15);
        color: #22c55e;
        border: 1px solid rgba(34, 197, 94, 0.3);
    }
    .stage-running {
        background: rgba(234, 179, 8, 0.15);
        color: #eab308;
        border: 1px solid rgba(234, 179, 8, 0.3);
        animation: pulse 1.5s ease-in-out infinite;
    }
    .stage-pending {
        background: rgba(100, 100, 100, 0.1);
        color: #666;
        border: 1px solid rgba(100, 100, 100, 0.2);
    }
    .stage-error {
        background: rgba(239, 68, 68, 0.15);
        color: #ef4444;
        border: 1px solid rgba(239, 68, 68, 0.3);
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.6; }
    }

    div[data-testid="stMetricValue"] { font-size: 3rem; }

    /* Smooth tab transitions */
    .stTabs [data-baseweb="tab-panel"] {
        animation: fadeIn 0.3s ease-in;
    }
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(8px); }
        to { opacity: 1; transform: translateY(0); }
    }

    /* Debug console styles */
    .debug-console {
        background: #0d1117;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 16px;
        font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
        font-size: 0.78rem;
        max-height: 500px;
        overflow-y: auto;
        line-height: 1.6;
    }
    .log-line {
        padding: 2px 0;
        border-bottom: 1px solid #161b22;
    }
    .log-ts { color: #484f58; }
    .log-info { color: #58a6ff; }
    .log-warn { color: #d29922; }
    .log-error { color: #f85149; }
    .log-rate { color: #f0883e; font-weight: 600; }
    .log-ok { color: #3fb950; }
    .log-stage {
        color: #bc8cff;
        font-weight: 600;
        border-top: 1px solid #30363d;
        margin-top: 4px;
        padding-top: 4px;
    }
    .log-timing { color: #79c0ff; font-style: italic; }
</style>
""", unsafe_allow_html=True)

# ── Session State Init ───────────────────────────────────────────────────────
# All pipeline results are stored in session_state so they survive reruns.
RESULT_KEYS = ["papers", "tree", "qg1", "trends", "gaps", "qg2", "user_gap_selection", "methodology_a", "methodology_b", "methodology_eval", "format_match", "grant", "novelty"]

if "pipeline_run" not in st.session_state:
    st.session_state.pipeline_run = False
if "pipeline_topic" not in st.session_state:
    st.session_state.pipeline_topic = ""
if "pipeline_errors" not in st.session_state:
    st.session_state.pipeline_errors = {}
if "stage_status" not in st.session_state:
    st.session_state.stage_status = {}
if "debug_logs" not in st.session_state:
    st.session_state.debug_logs = []
if "stage_timings" not in st.session_state:
    st.session_state.stage_timings = {}

# Grant format session states
if "formats" not in st.session_state:
    st.session_state.formats = load_all_formats()
if "phase" not in st.session_state:
    st.session_state.phase = 1   # 1 = pre-format-selection, 2 = post
if "user_format_override" not in st.session_state:
    st.session_state.user_format_override = None


class StreamCapture:
    """Captures stdout/print output and logs it with timestamps."""
    def __init__(self, original_stdout):
        self.original = original_stdout
        self.buffer = io.StringIO()

    def write(self, text):
        self.original.write(text)  # still print to terminal
        if text.strip():  # skip empty lines
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            line = text.strip()
            # Classify the log line
            if "429" in line:
                level = "rate"
            elif any(w in line.lower() for w in ["error", "failed", "fail", "invalid", "exception"]):
                level = "error"
            elif any(w in line.lower() for w in ["warning", "warn", "revise", "retry", "swapping", "unavailable", "503"]):
                level = "warn"
            elif any(w in line.lower() for w in ["pass", "complete", "success", "ok"]):
                level = "ok"
            elif line.startswith("["):
                level = "stage"
            else:
                level = "info"
            st.session_state.debug_logs.append((ts, level, line))

    def flush(self):
        self.original.flush()


def format_debug_html(logs):
    """Convert log tuples to styled HTML for the debug console."""
    if not logs:
        return '<div class="debug-console"><span class="log-info">No logs captured yet. Run the pipeline to see output.</span></div>'
    lines = []
    for ts, level, text in logs:
        lines.append(
            f'<div class="log-line">'
            f'<span class="log-ts">[{ts}]</span> '
            f'<span class="log-{level}">{text}</span>'
            f'</div>'
        )
    return '<div class="debug-console">' + ''.join(lines) + '</div>'

def render_tree_agraph(tree: dict):
    if not tree or not tree.get("themes"):
        st.info("Tree not yet built — run the pipeline first.")
        return
        
    nodes = []
    edges = []
    
    root_val = tree.get("root", "Topic string")
    root_label = root_val[:30] + "\\n" + root_val[30:] if len(root_val) > 30 else root_val
    nodes.append(Node(
        id="root",
        label=root_label,
        size=30,
        color="#7c3aed",
        font={"color": "#ffffff", "size": 14, "face": "Inter"},
        shape="ellipse",
        title=root_val
    ))
    
    theme_colors = ["#6d28d9", "#1d4ed8", "#0f766e", "#b45309", "#be123c"]
    paper_colors = ["#a78bfa", "#93c5fd", "#5eead4", "#fcd34d", "#fca5a5"]
    
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
            size=22,
            color=t_color,
            font={"color": "#ffffff", "size": 12, "face": "Inter"},
            shape="box",
            title=t_title
        ))
        
        edges.append(Edge(
            source="root",
            target=theme_id,
            color="#4b5563",
            width=2,
            arrows="to",
            smooth={"type": "cubicBezier"}
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
                font={"color": "#1f2937", "size": 11, "face": "Inter"},
                shape="box",
                title=p_title
            ))
            
            edges.append(Edge(
                source=theme_id,
                target=p_id,
                color="#374151",
                width=1,
                arrows="to",
                smooth={"type": "cubicBezier"}
            ))
            
    config = Config(
        width="100%",
        height=550,
        directed=True,
        physics=True,
        hierarchical=True,
        hierarchical_layout={
            "enabled": True,
            "direction": "UD",
            "sortMethod": "directed",
            "levelSeparation": 120,
            "nodeSpacing": 100,
            "treeSpacing": 150,
            "blockShifting": True,
            "edgeMinimization": True,
            "parentCentralization": True,
        },
        nodeHighlightBehavior=True,
        highlightColor="#a78bfa",
        backgroundColor="rgba(0,0,0,0)",
        stabilization=True,
    )
    
    agraph(nodes=nodes, edges=edges, config=config)

# Auto-load cached results on first visit
for key in RESULT_KEYS:
    if key not in st.session_state:
        cached = load(key)
        if cached:
            st.session_state[key] = cached
            st.session_state.pipeline_run = True
        else:
            st.session_state[key] = None

# Load topic from cache if available
if not st.session_state.pipeline_topic:
    topic_file = os.path.join(CACHE_DIR, "_topic.txt")
    if os.path.exists(topic_file):
        st.session_state.pipeline_topic = open(topic_file).read().strip()

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown('<p class="main-title">🔬 VMARO Research Orchestrator</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">AI-powered research pipeline — from literature to grant proposal in minutes</p>', unsafe_allow_html=True)

# ── Pipeline Stages Definition ───────────────────────────────────────────────
STAGES = [
    ("", "Literature Mining",       "papers"),
    ("", "Thematic Clustering",     "tree"),
    ("", "Quality Gate 1",          "qg1"),
    ("", "Trend Analysis",          "trends"),
    ("", "Gap Identification",      "gaps"),
    ("", "Quality Gate 2",          "qg2"),
    ("", "Gap Selection",           "user_gap_selection"),
    ("", "Methodology Design",     "methodology_a"),
    ("", "Methodology Evaluation", "methodology_eval"),
    ("", "Format Selection",       "format_match"),
    ("", "Grant Writing",          "grant"),
    ("", "Novelty Scoring",        "novelty"),
]

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Configuration")
    topic = st.text_input(
        "Research Topic",
        value=st.session_state.pipeline_topic,
        placeholder="e.g. Federated Learning in Healthcare"
    )

    st.markdown("---")
    run_btn = st.button("Run Analysis", use_container_width=True, type="primary")

    st.markdown("---")
    st.markdown("##### Pipeline Stages")

    # Show dynamic stage status
    for emoji, name, key in STAGES:
        status = st.session_state.stage_status.get(key, "pending")
        if status == "complete":
            badge_class = "stage-complete"
            icon = "[✓]"
        elif status == "running":
            badge_class = "stage-running"
            icon = "[>]"
        elif status == "error":
            badge_class = "stage-error"
            icon = "[X]"
        else:
            badge_class = "stage-pending"
            icon = "[ ]"
        st.markdown(
            f'<div class="stage-badge {badge_class}">{icon} {name}</div>',
            unsafe_allow_html=True
        )

    st.markdown("---")
    st.markdown("### Custom Grant Format")
    
    # Download template button
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

    # Upload widget
    uploaded_file = st.file_uploader(
        "Upload Custom Format (JSON)",
        type=["json"],
        help="Upload a filled-in format template to add it to the selector."
    )
    if uploaded_file:
        try:
            custom_fmt = json.load(uploaded_file)
            success, errors = register_custom_format(custom_fmt, st.session_state.formats)
            if success:
                st.success(f"Format '{custom_fmt['format_id']}' loaded successfully.")
            else:
                st.error("Validation failed:")
                for err in errors:
                    st.markdown(f"- {err}")
        except json.JSONDecodeError:
            st.error("Invalid JSON — check your file and try again.")

    # Debug toggle
    st.markdown("---")
    st.markdown("##### Developer")
    show_debug = st.checkbox("Show Debug Console", value=True, key="show_debug")

    # Clear cache button
    st.markdown("---")
    if st.button("Clear Cache & Reset", use_container_width=True):
        import shutil
        if os.path.exists(CACHE_DIR):
            shutil.rmtree(CACHE_DIR)
        for key in RESULT_KEYS:
            st.session_state[key] = None
        st.session_state.pipeline_run = False
        st.session_state.pipeline_topic = ""
        st.session_state.pipeline_errors = {}
        st.session_state.stage_status = {}
        st.session_state.debug_logs = []
        st.session_state.stage_timings = {}
        st.rerun()

    if st.button("Clear Logs", use_container_width=True):
        st.session_state.debug_logs = []
        st.session_state.stage_timings = {}
        st.rerun()


# ── Helpers ──────────────────────────────────────────────────────────────────
def is_fallback(data, required_keys):
    """Check if result is a fallback/empty dict that shouldn't be cached."""
    if not data or not isinstance(data, dict):
        return True
    for k in required_keys:
        v = data.get(k)
        if v is None or v == "" or v == [] or v == {}:
            return True
    return False


def set_stage(key, status):
    """Update stage status in session state."""
    st.session_state.stage_status[key] = status


# ── Run Pipeline ─────────────────────────────────────────────────────────────
if run_btn:
    if not topic.strip():
        st.error("Please enter a research topic.")
        st.stop()

    # Clear cache if topic changed
    last_topic_file = os.path.join(CACHE_DIR, "_topic.txt")
    if os.path.exists(CACHE_DIR) and os.path.exists(last_topic_file):
        prev_topic = open(last_topic_file).read().strip()
        if prev_topic != topic.strip():
            import shutil
            shutil.rmtree(CACHE_DIR)
            for key in RESULT_KEYS:
                st.session_state[key] = None
            st.session_state.phase = 1

    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(last_topic_file, "w") as f:
        f.write(topic.strip())

    st.session_state.pipeline_topic = topic.strip()
    st.session_state.pipeline_errors = {}
    st.session_state.stage_status = {}
    st.session_state.debug_logs = []
    st.session_state.stage_timings = {}
    st.session_state.phase = 1

    # Start capturing stdout for the debug console
    _original_stdout = sys.stdout
    sys.stdout = StreamCapture(_original_stdout)

    # Lazy imports
    from agents.literature_agent import run as run_literature
    from agents.tree_agent import run as run_tree
    from agents.trend_agent import run as run_trend
    from agents.gap_agent import run as run_gap
    from agents.methodology_agent import run as run_methodology
    from agents.grant_agent import run as run_grant
    from agents.novelty_agent import run as run_novelty
    from utils.quality_gate import evaluate_quality

    progress_bar = st.progress(0, text="Initializing pipeline...")
    status_container = st.status("🚀 **Running VMARO Pipeline**", expanded=True)

    total = len(STAGES)

    def update_progress(step_idx, label):
        pct = int((step_idx / total) * 100)
        progress_bar.progress(pct, text=f"Stage {step_idx}/{total} — {label}")

    with status_container:
        # ── Stage 1: Literature ──
        set_stage("papers", "running")
        update_progress(1, "Literature Mining")
        st.write("**Fetching papers sequentially**: Semantic Scholar → arXiv → CrossRef → OpenAlex...")
        _t0 = time.time()
        try:
            papers = load("papers")
            if papers and not is_fallback(papers, ["papers"]):
                st.write("  ↳ _Loaded from cache_")
            else:
                papers = run_literature(topic)
                if not is_fallback(papers, ["papers"]):
                    save("papers", papers)
                time.sleep(1)
            st.session_state.papers = papers
            n_papers = len(papers.get("papers", []))
            st.write(f"  ↳ Retrieved **{n_papers} papers**")
            set_stage("papers", "complete")
        except Exception as e:
            st.write(f"  ↳ Error: {e}")
            st.session_state.pipeline_errors["papers"] = str(e)
            set_stage("papers", "error")
        st.session_state.stage_timings["papers"] = round(time.time() - _t0, 1)

        # ── Stage 2: Tree ──
        set_stage("tree", "running")
        update_progress(2, "Thematic Clustering")
        st.write("**Clustering** papers into thematic groups...")
        _t0 = time.time()
        try:
            tree = load("tree")
            if tree and not is_fallback(tree, ["themes"]):
                st.write("  ↳ _Loaded from cache_")
            else:
                papers_data = st.session_state.papers or {"topic": topic, "papers": []}
                tree = run_tree(papers_data)
                if not is_fallback(tree, ["themes"]):
                    save("tree", tree)
                time.sleep(1)
            st.session_state.tree = tree
            n_themes = len(tree.get("themes", []))
            st.write(f"  ↳ Built **{n_themes} themes**")
            set_stage("tree", "complete")
        except Exception as e:
            st.write(f"  ↳ Error: {e}")
            st.session_state.pipeline_errors["tree"] = str(e)
            set_stage("tree", "error")
        st.session_state.stage_timings["tree"] = round(time.time() - _t0, 1)

        # ── Stage 3: Quality Gate 1 ──
        set_stage("qg1", "running")
        update_progress(3, "Quality Gate 1")
        st.write("**Quality Gate 1** — evaluating literature tree...")
        _t0 = time.time()
        try:
            qg1 = load("qg1")
            if qg1 and not is_fallback(qg1, ["decision", "confidence"]):
                st.write("  ↳ _Loaded from cache_")
            else:
                tree_data = st.session_state.tree or {}
                qg1 = evaluate_quality("post_literature", tree_data)
                if not is_fallback(qg1, ["decision", "confidence"]):
                    save("qg1", qg1)
                time.sleep(1)
            st.session_state.qg1 = qg1
            qg1_decision = qg1.get("decision", "?")
            qg1_conf = qg1.get("confidence", 0)
            st.write(f"  ↳ Gate: **{qg1_decision}** (confidence {qg1_conf})")
            set_stage("qg1", "complete")
        except Exception as e:
            st.write(f"  ↳ Error: {e}")
            st.session_state.pipeline_errors["qg1"] = str(e)
            set_stage("qg1", "error")
        st.session_state.stage_timings["qg1"] = round(time.time() - _t0, 1)

        # ── Stage 4: Trends ──
        set_stage("trends", "running")
        update_progress(4, "Trend Analysis")
        st.write("**Analyzing trends** in the research landscape...")
        _t0 = time.time()
        try:
            trends = load("trends")
            if trends and not is_fallback(trends, ["dominant_clusters", "emerging_trends"]):
                st.write("  ↳ _Loaded from cache_")
            else:
                tree_data = st.session_state.tree or {}
                trends = run_trend(tree_data)
                if not is_fallback(trends, ["dominant_clusters", "emerging_trends"]):
                    save("trends", trends)
                time.sleep(1)
            st.session_state.trends = trends
            st.write(f"  ↳ Found **{len(trends.get('dominant_clusters', []))} clusters**, **{len(trends.get('emerging_trends', []))} trends**")
            set_stage("trends", "complete")
        except Exception as e:
            st.write(f"  ↳ Error: {e}")
            st.session_state.pipeline_errors["trends"] = str(e)
            set_stage("trends", "error")
        st.session_state.stage_timings["trends"] = round(time.time() - _t0, 1)

        # ── Stage 5: Gaps ──
        set_stage("gaps", "running")
        update_progress(5, "Gap Identification")
        st.write("**Identifying research gaps** at theme intersections...")
        _t0 = time.time()
        try:
            gaps = load("gaps")
            if gaps and not is_fallback(gaps, ["identified_gaps"]):
                st.write("  ↳ _Loaded from cache_")
            else:
                tree_data = st.session_state.tree or {}
                trends_data = st.session_state.trends or {}
                gaps = run_gap(tree_data, trends_data)
                if not is_fallback(gaps, ["identified_gaps"]):
                    save("gaps", gaps)
                time.sleep(1)
            st.session_state.gaps = gaps
            st.write(f"  ↳ Found **{len(gaps.get('identified_gaps', []))} gaps**, selected: **{gaps.get('selected_gap', '?')}**")
            set_stage("gaps", "complete")
        except Exception as e:
            st.write(f"  ↳ Error: {e}")
            st.session_state.pipeline_errors["gaps"] = str(e)
            set_stage("gaps", "error")
        st.session_state.stage_timings["gaps"] = round(time.time() - _t0, 1)

        # ── Stage 6: Quality Gate 2 ──
        set_stage("qg2", "running")
        update_progress(6, "Quality Gate 2")
        st.write("**Quality Gate 2** — evaluating gap analysis...")
        _t0 = time.time()
        try:
            qg2 = load("qg2")
            if qg2 and not is_fallback(qg2, ["decision", "confidence"]):
                st.write("  ↳ _Loaded from cache_")
            else:
                gaps_data = st.session_state.gaps or {}
                qg2 = evaluate_quality("post_gap", gaps_data)
                if not is_fallback(qg2, ["decision", "confidence"]):
                    save("qg2", qg2)
                time.sleep(1)
            st.session_state.qg2 = qg2
            qg2_decision = qg2.get("decision", "?")
            qg2_conf = qg2.get("confidence", 0)
            st.write(f"  ↳ Gate: **{qg2_decision}** (confidence {qg2_conf})")
            set_stage("qg2", "complete")
        except Exception as e:
            st.write(f"  ↳ Error: {e}")
            st.session_state.pipeline_errors["qg2"] = str(e)
            set_stage("qg2", "error")
        st.session_state.stage_timings["qg2"] = round(time.time() - _t0, 1)

    # Phase 1 complete. Await user for Gap Selection.
    st.session_state.phase = 2
    st.session_state.pipeline_run = True

    # Restore stdout temporarily
    sys.stdout = _original_stdout

if st.session_state.get("phase") == 2:
    st.markdown("---")
    st.subheader("🎯 Select Research Gap")
    
    gaps_data = st.session_state.gaps or {}
    all_gaps = gaps_data.get("identified_gaps", [])
    llm_selected_id = gaps_data.get("selected_gap", "")
    
    if not all_gaps:
        st.warning("No gaps found by Agent 3. Please restart the pipeline.")
    else:
        st.write("Agent 3 identified the following gaps. Select one to develop into a methodology, or define your own.")
        
        # We need a session state var for the radio selection to control the custom text area
        if "gap_radio_choice" not in st.session_state:
            st.session_state.gap_radio_choice = llm_selected_id
            
        # Build options
        gap_options = [g["gap_id"] for g in all_gaps] + ["custom"]
        
        def format_gap_label(gid):
            if gid == "custom":
                return "Define your own gap"
            g = next(x for x in all_gaps if x["gap_id"] == gid)
            rank = g.get("priority_rank", 3)
            stars = "★" * (4 - rank) + "☆" * (rank - 1) if isinstance(rank, int) and 1 <= rank <= 3 else ""
            rec = " 💡 (LLM Recommended)" if gid == llm_selected_id else ""
            return f"[{gid} {stars}] {g['description']}{rec}"
            
        selected_gap_id = st.radio(
            "Identified Gaps:",
            options=gap_options,
            format_func=format_gap_label,
            key="gap_radio_choice"
        )
        
        # Display feasibility note for the selected predefined gap
        if selected_gap_id != "custom":
            g = next((x for x in all_gaps if x["gap_id"] == selected_gap_id), None)
            if g and g.get("feasibility_note"):
                st.caption(f"**Feasibility:** {g['feasibility_note']}")
                
        custom_gap_text = ""
        if selected_gap_id == "custom":
            custom_gap_text = st.text_area(
                "Custom Gap Description",
                placeholder="Describe your research gap here...",
                help="Agent 4 will treat this as authoritative."
            )
            
        col1, col2 = st.columns([1, 4])
        with col1:
            confirm_gap = st.button("Confirm Gap →", type="primary", disabled=(selected_gap_id == "custom" and not custom_gap_text.strip()))
            
        if confirm_gap:
            if selected_gap_id == "custom":
                selection = {
                    "gap_id": "custom",
                    "source": "user_custom",
                    "description": custom_gap_text.strip(),
                    "is_custom": True
                }
            else:
                g = next(x for x in all_gaps if x["gap_id"] == selected_gap_id)
                selection = {
                    "gap_id": g["gap_id"],
                    "source": "user_selected" if g["gap_id"] != llm_selected_id else "llm_suggested",
                    "description": g["description"],
                    "is_custom": False
                }
            
            save("user_gap_selection", selection)
            st.session_state.user_gap_selection = selection
            set_stage("user_gap_selection", "complete")
            st.session_state.phase = 3
            st.rerun()

if st.session_state.get("phase") == 3:
    # ── Stage 7 & Eval: Methodology ──
    from agents.methodology_agent import run as run_methodology
    from agents.methodology_evaluator import run as run_evaluator
    
    _original_stdout = sys.stdout
    sys.stdout = StreamCapture(_original_stdout)

    progress_bar = st.progress(0, text="Designing Methodologies...")
    status_container = st.status("🚀 **Generating Parallel Methodologies**", expanded=True)
    total = len(STAGES)
    
    def update_progress(step_idx, label):
        pct = int((step_idx / total) * 100)
        progress_bar.progress(pct, text=f"Stage {step_idx}/{total} — {label}")

    with status_container:
        set_stage("methodology_a", "running")
        update_progress(7, "Methodology Design (Primary & Challenger)")
        
        st.write("**Designing experimental methodology** for primary gap...")
        _t0 = time.time()
        try:
            methodology_a = load("methodology_a")
            if methodology_a and not is_fallback(methodology_a, ["suggested_datasets", "experimental_design"]):
                st.write("  ↳ _Primary loaded from cache_")
            else:
                user_gap = st.session_state.user_gap_selection or load("user_gap_selection")
                gap_desc = user_gap["description"] if user_gap else ""
                topic = st.session_state.pipeline_topic
                methodology_a = run_methodology(gap_desc, topic)
                if not is_fallback(methodology_a, ["suggested_datasets", "experimental_design"]):
                    save("methodology_a", methodology_a)
                time.sleep(1)
            st.session_state.methodology_a = methodology_a
            set_stage("methodology_a", "complete")
        except Exception as e:
            st.write(f"  ↳ Error in Primary: {e}")
            st.session_state.pipeline_errors["methodology_a"] = str(e)
            set_stage("methodology_a", "error")
            
        st.write("**Designing methodology for challenger gap**...")
        try:
            methodology_b = load("methodology_b")
            if methodology_b:
                st.write("  ↳ _Challenger loaded from cache_")
            else:
                # Figure out challenger
                all_gaps = st.session_state.gaps.get("identified_gaps", []) if st.session_state.gaps else []
                user_gap = st.session_state.user_gap_selection or load("user_gap_selection")
                challenger_desc = None
                if user_gap and all_gaps:
                    sorted_gaps = sorted(all_gaps, key=lambda g: g.get("priority_rank", 3))
                    if user_gap.get("source") == "user_custom":
                        challenger_desc = sorted_gaps[0]["description"]
                    else:
                        prim_id = user_gap.get("gap_id")
                        chs = [g for g in sorted_gaps if g["gap_id"] != prim_id]
                        if chs:
                            challenger_desc = chs[0]["description"]
                
                if not challenger_desc:
                    st.write("  ↳ _No challenger gap available, skipping._")
                    methodology_b = None
                else:
                    topic = st.session_state.pipeline_topic
                    methodology_b = run_methodology(challenger_desc, topic)
                    if not is_fallback(methodology_b, ["suggested_datasets", "experimental_design"]):
                        save("methodology_b", methodology_b)
                    time.sleep(1)
            st.session_state.methodology_b = methodology_b
        except Exception as e:
            st.write(f"  ↳ Error in Challenger: {e}")
            methodology_b = None
            
        # Evaluator
        set_stage("methodology_eval", "running")
        update_progress(8, "Methodology Evaluation")
        st.write("**Evaluating competing methodologies**...")
        try:
            methodology_eval = load("methodology_eval")
            if methodology_eval:
                st.write("  ↳ _Evaluator loaded from cache_")
            else:
                topic = st.session_state.pipeline_topic
                user_gap = st.session_state.user_gap_selection or load("user_gap_selection")
                primary_desc = user_gap["description"] if user_gap else ""
                
                challenger_desc = ""
                if methodology_b:
                    all_gaps = st.session_state.gaps.get("identified_gaps", []) if st.session_state.gaps else []
                    sorted_gaps = sorted(all_gaps, key=lambda g: g.get("priority_rank", 3))
                    if user_gap.get("source") == "user_custom":
                        challenger_desc = sorted_gaps[0]["description"]
                    else:
                        prim_id = user_gap.get("gap_id")
                        chs = [g for g in sorted_gaps if g["gap_id"] != prim_id]
                        if chs:
                            challenger_desc = chs[0]["description"]
                
                methodology_eval = run_evaluator(
                    topic, 
                    primary_desc, 
                    st.session_state.methodology_a, 
                    challenger_desc, 
                    methodology_b
                )
                save("methodology_eval", methodology_eval)
            st.session_state.methodology_eval = methodology_eval
            set_stage("methodology_eval", "complete")
        except Exception as e:
            st.write(f"  ↳ Evaluator error: {e}")
            st.session_state.pipeline_errors["methodology_eval"] = str(e)
            set_stage("methodology_eval", "error")

        st.session_state.stage_timings["methodology_a"] = round(time.time() - _t0, 1)

    # Phase 3 complete. Await Format Selection.
    st.session_state.phase = 4
    
    sys.stdout = _original_stdout
    st.rerun()

if st.session_state.get("phase") == 4:
    # Render Parallel Evaluation Expander if it ran
    if "methodology_eval" in st.session_state and st.session_state.methodology_eval:
        mev = st.session_state.methodology_eval
        if mev.get("parallel_was_run"):
            with st.expander("▼ Methodology Evaluation (parallel run)", expanded=True):
                st.markdown("Two methodologies were generated in parallel. The stronger one was selected automatically.")
                
                win_label = "A" if mev.get("winner") == "A" else "B"
                a_score = mev.get("methodology_a_score", 0)
                b_score = mev.get("methodology_b_score", 0)
                
                st.markdown(f"**Primary gap methodology (A)** — score: {a_score:.2f} {'✓ **WINNER**' if win_label == 'A' else ''}")
                st.markdown(f"**Challenger gap methodology (B)** — score: {b_score:.2f} {'✓ **WINNER**' if win_label == 'B' else ''}")
                
                st.markdown("**Evaluator reasoning:**")
                st.info(mev.get("reasoning", ""))
                
                if st.button("Override — use Challenger instead", key="override_eval"):
                    # Swap the winner directly in cache/session state
                    mev["winner"] = "B" if win_label == "A" else "A"
                    mev["winning_methodology"] = st.session_state.methodology_b if win_label == "A" else st.session_state.methodology_a
                    save("methodology_eval", mev)
                    st.session_state.methodology_eval = mev
                    # Clear downstream caches
                    for k in ["format_match", "grant", "novelty"]:
                        st.session_state[k] = None
                        import os, ssl
                        p = f"cache/{k}.json"
                        if os.path.exists(p): os.remove(p)
                    st.rerun()
        else:
            st.caption("Single methodology generated — parallel run skipped (insufficient distinct gaps).")
    st.markdown("---")
    st.subheader("📋 Select Grant Format")
    
    # ── Stage 7.5: Intercept Format Selection ──
    # Run the invisible LLM format matcher default if not cached
    if not load("format_match"):
        with st.spinner("Analyzing methodology to recommend best grant format..."):
            _original_stdout = sys.stdout
            sys.stdout = StreamCapture(_original_stdout)
            
            fm = run_format_matcher(
                st.session_state.pipeline_topic,
                st.session_state.get("methodology_eval", {}).get("winning_methodology", {}),
                st.session_state.formats,
                None
            )
            save("format_match", fm)
            st.session_state.format_match = fm
            
            sys.stdout = _original_stdout

    formats = st.session_state.formats
    format_options = {
        fid: f"{fmt['name']} — {fmt['funding_body']}" 
        for fid, fmt in formats.items()
    }
    
    cached_match = load("format_match")
    llm_default = cached_match.get("selected_format_id") if cached_match else None
    
    # If the default is invalid, fall back safely
    if llm_default not in format_options:
        llm_default = list(format_options.keys())[0] if format_options else None
    
    col1, col2 = st.columns([3, 1])
    with col1:
        selected_format_id = st.selectbox(
            "Grant Format",
            options=list(format_options.keys()),
            format_func=lambda x: format_options[x],
            index=list(format_options.keys()).index(llm_default) if llm_default else 0,
            help="LLM recommendation pre-selected. Override as needed."
        )

    with col2:
        if llm_default and cached_match.get("llm_selected"):
            st.info(f"💡 LLM Recommended: **{llm_default}**")
            
    # Save the manual override if user changed it
    st.session_state.user_format_override = selected_format_id
    
    if selected_format_id in formats:
        with st.expander(f"About: {formats[selected_format_id].get('name', selected_format_id)}", expanded=False):
            fmt = formats[selected_format_id]
            st.markdown(f"**Funding Body:** {fmt.get('funding_body', 'N/A')}")
            st.markdown(f"**Typical Award:** {fmt.get('typical_award_usd', 'N/A')} USD")
            st.markdown(f"**Duration:** {fmt.get('typical_duration_years', 'N/A')} years")
            st.markdown(f"**Emphasis:** {fmt.get('emphasis', '')}")
            if fmt.get("avoid"):
                st.markdown(f"**Avoid:** {fmt['avoid']}")
            st.markdown("**Sections:**")
            for s in fmt.get("sections", []):
                req = "required" if s.get("required") else "optional"
                limit = f"{s.get('max_words')} words" if s.get("max_words") else f"{s.get('max_pages')} pages" if s.get("max_pages") else "no limit"
                st.markdown(f"- **{s.get('name', 'Section')}** ({req}, {limit})")

    generate_btn = st.button("Generate Grant Proposal →", type="primary", use_container_width=True)

if st.session_state.get("phase") == 4 and globals().get('generate_btn'):
    from agents.grant_agent import run as run_grant
    from agents.novelty_agent import run as run_novelty

    _original_stdout = sys.stdout
    sys.stdout = StreamCapture(_original_stdout)

    progress_bar = st.progress(0, text="Drafting Proposal...")
    status_container = st.status("🚀 **Generating Grant & Assessing Novelty**", expanded=True)
    total = len(STAGES)

    def update_progress(step_idx, label):
        pct = int((step_idx / total) * 100)
        progress_bar.progress(pct, text=f"Stage {step_idx}/{total} — {label}")

    with status_container:
        # Re-save format match with user override applied
        fm = run_format_matcher(
            st.session_state.pipeline_topic,
            st.session_state.get("methodology_eval", {}).get("winning_methodology", {}),
            st.session_state.formats,
            st.session_state.user_format_override
        )
        save("format_match", fm)
        st.session_state.format_match = fm
        set_stage("format_match", "complete")

        # ── Stage 8: Grant ──
        set_stage("grant", "running")
        update_progress(8, "Grant Writing")
        st.write("**Drafting grant proposal**...")
        _t0 = time.time()
        try:
            grant = load("grant")
            if grant and not is_fallback(grant, ["problem_statement", "proposed_methodology"]):
                st.write("  ↳ _Loaded from cache_")
            else:
                topic = st.session_state.pipeline_topic
                user_gap_selection = st.session_state.get("user_gap_selection", {}) or load("user_gap_selection") or {}
                gap_desc = st.session_state.get("methodology_eval", {}).get("winning_gap_description", user_gap_selection.get("description", ""))
                meth_data = st.session_state.get("methodology_eval", {}).get("winning_methodology", {})
                format_match = st.session_state.format_match or {}
                grant = run_grant(topic, gap_desc, meth_data, format_match)
                if not is_fallback(grant, ["problem_statement", "proposed_methodology"]):
                    save("grant", grant)
                time.sleep(1)
            st.session_state.grant = grant
            st.write("  ↳ Grant proposal drafted")
            set_stage("grant", "complete")
        except Exception as e:
            st.write(f"  ↳ Error: {e}")
            st.session_state.pipeline_errors["grant"] = str(e)
            set_stage("grant", "error")
        st.session_state.stage_timings["grant"] = round(time.time() - _t0, 1)

        # ── Stage 10: Novelty ──
        set_stage("novelty", "running")
        update_progress(10, "Novelty Scoring")
        st.write("**Scoring novelty** against existing literature...")
        _t0 = time.time()
        try:
            novelty = load("novelty")
            if novelty and not is_fallback(novelty, ["closest_papers", "score_justification"]):
                st.write("  ↳ _Loaded from cache_")
            else:
                grant_data = st.session_state.grant or {}
                tree_data = st.session_state.tree or {}
                novelty = run_novelty(grant_data, tree_data)
                if not is_fallback(novelty, ["closest_papers", "score_justification"]):
                    save("novelty", novelty)
                time.sleep(1)
            st.session_state.novelty = novelty
            score = novelty.get("novelty_score", 0)
            st.write(f"  ↳ Novelty score: **{score}/100**")
            set_stage("novelty", "complete")
        except Exception as e:
            st.write(f"  ↳ Error: {e}")
            st.session_state.pipeline_errors["novelty"] = str(e)
            set_stage("novelty", "error")
        st.session_state.stage_timings["novelty"] = round(time.time() - _t0, 1)

    # Restore stdout
    sys.stdout = _original_stdout

    progress_bar.progress(100, text="Pipeline complete!")
    status_container.update(label="**Pipeline Complete**", state="complete", expanded=False)
    st.session_state.pipeline_run = True
    st.balloons()


# ══════════════════════════════════════════════════════════════════════════════
#  RESULTS DISPLAY  (reads from session_state, survives reruns)
# ══════════════════════════════════════════════════════════════════════════════

# Check if we have any results to display
has_results = st.session_state.pipeline_run and any(
    st.session_state.get(k) for k in RESULT_KEYS
)

if has_results:
    st.markdown("---")

    # Show errors if any
    if st.session_state.pipeline_errors:
        with st.expander("Pipeline Errors", expanded=False):
            for stage, err in st.session_state.pipeline_errors.items():
                st.error(f"**{stage}**: {err}")

    tabs = st.tabs([
        "Literature",
        "Tree Index",
        "Trends & Gaps",
        "Methodology",
        "Grant Proposal",
        "Novelty Score"
    ])

    display_topic = st.session_state.pipeline_topic or "Unknown"

    # ── Tab 1: Literature ────────────────────────────────────────────────────
    with tabs[0]:
        papers_data = st.session_state.papers or {}
        if papers_data:
            st.markdown("## Retrieved Literature")
            paper_list = papers_data.get("papers", [])
            st.caption(f"Topic: **{papers_data.get('topic', display_topic)}** · {len(paper_list)} papers")

            for p in paper_list:
                st.markdown(f"""
<div class="paper-card">
    <h4>{p.get('title', 'Unknown')}</h4>
    <span class="year-badge">{p.get('year', 'N/A')}</span>
    <p style="margin-top:10px; color:#ccc;">{p.get('summary', '')}</p>
    <p style="color:#a78bfa;"><strong>Contribution:</strong> {p.get('contribution', '')}</p>
    <a href="{p.get('url', '#')}" style="color:#667eea;">Source</a>
</div>
                """, unsafe_allow_html=True)
        else:
            st.info("No literature data available. Run the pipeline to generate results.")

    # ── Tab 2: Tree Index ────────────────────────────────────────────────────
    with tabs[1]:
        tree_data = st.session_state.tree or {}
        if tree_data and tree_data.get("themes"):
            render_tree_agraph(tree_data)
            
            # Emerging directions below the chart
            directions = tree_data.get("emerging_directions", [])
            if directions:
                st.markdown("#### Emerging Directions")
                pills_html = []
                for d in directions:
                    pills_html.append(f'<span style="background:#3b0764; color:#e9d5ff; padding:4px 12px; border-radius:20px; font-size:0.85rem; margin:4px; display:inline-block;">{d}</span>')
                st.markdown("".join(pills_html), unsafe_allow_html=True)
            
            st.markdown("---")

            with st.expander("Raw tree JSON", expanded=False):
                st.json(tree_data)
        else:
            st.info("Tree not yet built — run the pipeline first.")

    # ── Tab 3: Trends & Gaps ─────────────────────────────────────────────────
    with tabs[2]:
        trends_data = st.session_state.trends or {}
        gaps_data = st.session_state.gaps or {}

        if trends_data or gaps_data:
            st.markdown("## Trends & Gaps")
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("### Dominant Clusters")
                for i, c in enumerate(trends_data.get("dominant_clusters", [])):
                    st.markdown(f"**{i+1}.** {c}")

                st.markdown("### Emerging Trends")
                for t in trends_data.get("emerging_trends", []):
                    st.info(f"{t}")

            with col2:
                st.markdown("### Identified Gaps")
                for g in gaps_data.get("identified_gaps", []):
                    st.markdown(f"""
<div class="gap-card">
    <strong style="color:#f59e0b;">{g.get('gap_id', '')}</strong>
    <p style="color:#e2e8f0; margin: 6px 0;">{g.get('description', '')}</p>
    <p style="color:#94a3b8; font-size:0.85rem;"><em>Why underexplored:</em> {g.get('why_underexplored', '')}</p>
</div>
                    """, unsafe_allow_html=True)

                selected = gaps_data.get('selected_gap', '?')
                st.success(f"**Selected Gap:** {selected}")
        else:
            st.info("No trends/gaps data available. Run the pipeline to generate results.")

    # ── Tab 4: Methodology ───────────────────────────────────────────────────
    with tabs[3]:
        mev = st.session_state.get("methodology_eval", {})
        meth_a = st.session_state.get("methodology_a", {})
        meth_b = st.session_state.get("methodology_b", {})

        def render_meth(m):
            if not m:
                st.info("No data available.")
                return

            st.markdown("**Datasets:** " + ", ".join(m.get("suggested_datasets", [])) if m.get("suggested_datasets") else "**Datasets:** None suggested")
            st.markdown("**Metrics:** " + ", ".join(m.get("evaluation_metrics", [])) if m.get("evaluation_metrics") else "**Metrics:** None suggested")
            st.markdown("**Baselines:** " + ", ".join(m.get("baseline_models", [])) if m.get("baseline_models") else "**Baselines:** None suggested")

            st.markdown("**Experimental Design**")
            st.markdown(m.get("experimental_design", "_No design generated._"))

            st.markdown("**Tools & Frameworks**")
            tools = m.get("tools_and_frameworks", [])
            if tools:
                st.markdown(" · ".join([f"`{t}`" for t in tools]))

        if mev and mev.get("parallel_was_run") and meth_a and meth_b:
            st.markdown("## Parallel Methodologies Comparison")
            colA, colB = st.columns(2)
            
            with colA:
                st.markdown("### Methodology A (Primary)")
                if mev.get("winner") == "A":
                    st.success("Currently Selected (Winner)")
                render_meth(meth_a)
                
            with colB:
                st.markdown("### Methodology B (Challenger)")
                if mev.get("winner") == "B":
                    st.success("Currently Selected (Winner)")
                render_meth(meth_b)
        else:
            meth = mev.get("winning_methodology") or meth_a or {}
            if meth:
                st.markdown("## Experimental Methodology")
                render_meth(meth)
            else:
                st.info("No methodology data available. Run the pipeline to generate results.")

    # ── Tab 5: Grant Proposal ────────────────────────────────────────────────
    with tabs[4]:
        grant_data = st.session_state.grant or {}
        if grant_data:
            st.markdown("## Grant Proposal")

            sections = [
                ("Problem Statement", "problem_statement"),
                ("Proposed Methodology", "proposed_methodology"),
                ("Evaluation Plan", "evaluation_plan"),
                ("Expected Contribution", "expected_contribution"),
                ("Timeline", "timeline"),
                ("Budget Estimate", "budget_estimate"),
            ]
            for title, key in sections:
                content = grant_data.get(key, "")
                if content:
                    st.markdown(f'<div class="grant-section"><h3>{title}</h3><p>{content}</p></div>', unsafe_allow_html=True)

            st.markdown("---")
            col_dl1, col_dl2 = st.columns([1, 3])
            with col_dl1:
                st.download_button(
                    label="Download JSON",
                    data=json.dumps(grant_data, indent=2),
                    file_name=f"{display_topic.replace(' ', '_').lower()}_grant.json",
                    mime="application/json",
                    use_container_width=True
                )
        else:
            st.info("No grant proposal data available. Run the pipeline to generate results.")

    # ── Tab 6: Novelty Score ─────────────────────────────────────────────────
    with tabs[5]:
        nov = st.session_state.novelty or {}
        if nov:
            st.markdown("## Novelty Assessment")
            score = nov.get("novelty_score", 0)

            if score < 40:
                color, emoji, label = "#ef4444", "[LOW]", "Low Novelty"
            elif score < 70:
                color, emoji, label = "#eab308", "[MOD]", "Moderate Novelty"
            else:
                color, emoji, label = "#22c55e", "[HIGH]", "High Novelty"

            col_s1, col_s2 = st.columns([1, 2])
            with col_s1:
                st.markdown(f'<p class="score-big" style="color:{color};">{emoji} {score}</p>', unsafe_allow_html=True)
                st.markdown(f'<p class="score-label">{label} · out of 100</p>', unsafe_allow_html=True)

            with col_s2:
                st.markdown("### Justification")
                st.markdown(nov.get("score_justification", "_No justification available._"))

            st.markdown("### Similarity Reasoning")
            st.markdown(nov.get("similarity_reasoning", "_No reasoning available._"))

            st.markdown("### Closest Papers")
            closest = nov.get("closest_papers", [])
            if closest:
                for p in closest:
                    st.markdown(f"- {p}")
            else:
                st.caption("No closest papers identified.")
        else:
            st.info("No novelty data available. Run the pipeline to generate results.")

elif not st.session_state.pipeline_run:
    # ── Welcome Screen ──
    st.markdown("---")
    col_w1, col_w2, col_w3 = st.columns(3)
    with col_w1:
        st.markdown("""
        ### Literature Mining
        Fetch from **multiple academic databases** (Semantic Scholar, arXiv, CrossRef, OpenAlex, PubMed) with automatic deduplication.
        """)
    with col_w2:
        st.markdown("""
        ### Gap Analysis
        Identify underexplored intersections and select the most promising research gaps.
        """)
    with col_w3:
        st.markdown("""
        ### Grant Writing
        Generate a funding-ready research proposal with methodology and novelty scoring.
        """)
    st.markdown("---")
    st.markdown(
        '<p style="text-align:center; color:#888; font-size:1.1rem;">'
        'Enter a research topic in the sidebar and click <b>Run Analysis</b> to get started.'
        '</p>',
        unsafe_allow_html=True
    )

# ══════════════════════════════════════════════════════════════════════════════
#  DEBUG CONSOLE  (always at bottom when enabled)
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.get("show_debug", False):
    st.markdown("---")
    st.markdown("### Debug Console")

    # Stage timing summary
    timings = st.session_state.stage_timings
    if timings:
        st.markdown("#### Stage Timings")
        timing_cols = st.columns(min(len(timings), 5))
        stage_labels = {
            "papers": "Literature",
            "tree": "Tree",
            "qg1": "QG1",
            "trends": "Trends",
            "gaps": "Gaps",
            "qg2": "QG2",
            "methodology": "Methodology",
            "grant": "Grant",
            "novelty": "Novelty",
        }
        for i, (stage_key, elapsed) in enumerate(timings.items()):
            col_idx = i % min(len(timings), 5)
            with timing_cols[col_idx]:
                label = stage_labels.get(stage_key, stage_key)
                color = "#f85149" if elapsed > 30 else "#d29922" if elapsed > 10 else "#3fb950"
                st.markdown(
                    f'<div style="text-align:center;">'
                    f'<span style="font-size:1.6rem; font-weight:700; color:{color};">{elapsed}s</span><br>'
                    f'<span style="font-size:0.8rem; color:#888;">{label}</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )
        total_time = sum(timings.values())
        st.caption(f"Total pipeline time: **{total_time:.1f}s**")

    # Log output
    st.markdown("#### Pipeline Logs")
    n_429 = sum(1 for _, level, _ in st.session_state.debug_logs if level == "rate")
    n_errors = sum(1 for _, level, _ in st.session_state.debug_logs if level == "error")
    n_warns = sum(1 for _, level, _ in st.session_state.debug_logs if level == "warn")
    total_logs = len(st.session_state.debug_logs)

    summary_parts = [f"{total_logs} entries"]
    if n_429:
        summary_parts.append(f"[ERROR] {n_429} rate-limits (429)")
    if n_errors:
        summary_parts.append(f"❌ {n_errors} errors")
    if n_warns:
        summary_parts.append(f"⚠️ {n_warns} warnings")
    st.caption(" · ".join(summary_parts))

    # Filter buttons
    filter_col1, filter_col2, filter_col3, filter_col4, filter_col5 = st.columns(5)
    with filter_col1:
        show_all = st.button("All", use_container_width=True, key="dbg_all")
    with filter_col2:
        show_429 = st.button(f"429s ({n_429})", use_container_width=True, key="dbg_429")
    with filter_col3:
        show_errs = st.button(f"Errors ({n_errors})", use_container_width=True, key="dbg_err")
    with filter_col4:
        show_warns = st.button(f"Warns ({n_warns})", use_container_width=True, key="dbg_warn")
    with filter_col5:
        dl_logs = st.download_button(
            "⬇️ Export",
            data="\n".join(f"[{ts}] [{level.upper()}] {text}" for ts, level, text in st.session_state.debug_logs),
            file_name="vmaro_debug_logs.txt",
            mime="text/plain",
            use_container_width=True,
            key="dbg_export"
        )

    # Apply filter
    filtered_logs = st.session_state.debug_logs
    if show_429:
        filtered_logs = [(ts, lv, tx) for ts, lv, tx in filtered_logs if lv == "rate"]
    elif show_errs:
        filtered_logs = [(ts, lv, tx) for ts, lv, tx in filtered_logs if lv == "error"]
    elif show_warns:
        filtered_logs = [(ts, lv, tx) for ts, lv, tx in filtered_logs if lv in ("warn", "rate")]

    st.markdown(format_debug_html(filtered_logs), unsafe_allow_html=True)
