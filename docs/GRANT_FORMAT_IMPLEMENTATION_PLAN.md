# VMARO — Grant Format System: Full Implementation Plan

---

## 1. What We Are Adding

A **grant format routing layer** between Agent 4 (Methodology) and Agent 5 (Grant Writing), consisting of:

- A `grant_formats/` database of JSON format records (seeded with 6 formats)
- A `FormatMatcher` agent that selects the best format via LLM reasoning
- A `FormatLoader` utility for loading and validating format records
- A **two-phase Streamlit UI** that pauses between Agent 4 and Agent 5 for user format selection
- A **custom format upload** flow with JSON template download

The pipeline remains sequential. The only change to the pipeline graph is the insertion of `FormatMatcher` as a new step, and the split of the Streamlit run into two phases with a user interaction gate.

---

## 2. File Changes Summary

### New Files

```
vmaro/
├── grant_formats/                     ← NEW directory
│   ├── nsf_cise.json
│   ├── nih_r01.json
│   ├── nih_r21.json
│   ├── eu_horizon_europe.json
│   ├── darpa.json
│   └── wellcome_discovery.json
├── utils/
│   └── format_loader.py               ← NEW
├── agents/
│   └── format_matcher.py              ← NEW
└── schemas_for_user/
    └── custom_grant_format_template.json  ← NEW (downloadable by user)
```

### Modified Files

```
agents/grant_agent.py       ← Updated: now accepts format_selection argument
main.py                     ← Updated: FormatMatcher inserted before Agent 5
app.py                      ← Updated: two-phase UI, format selector, upload widget
cache/                      ← format_match.json added as checkpoint key
```

---

## 3. Grant Format JSON Schema

Every format record (whether seeded or user-uploaded) must conform to this schema.

### Top-Level Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `format_id` | string | YES | Unique identifier. Lowercase, underscores only. |
| `name` | string | YES | Full human-readable format name. |
| `funding_body` | string | YES | Name of the funding organization. |
| `typical_award_usd` | string | no | Award range string, e.g. `"200000-600000"`. |
| `typical_duration_years` | string | no | Duration string, e.g. `"3-5"`. |
| `domain_keywords` | list[string] | YES | Topic words used for LLM matching. Min 3 items. |
| `career_stage` | list[string] | no | `["early"]`, `["established"]`, or both. |
| `emphasis` | string | YES | What reviewers care about. Injected into Agent 5 system prompt. |
| `avoid` | string | no | What NOT to write. Injected into Agent 5 system prompt. |
| `rhetorical_tone` | string | no | Tone descriptor injected into Agent 5 system prompt. |
| `sections` | list[Section] | YES | Ordered list of section specs. Min 1 item. |
| `source_url` | string | no | URL to official grant documentation. |
| `notes` | string | no | Additional context not fitting other fields. |

### Section Object Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | YES | Section name as it appears in the format. |
| `max_words` | int or null | YES | Word limit. Set to null if not applicable. |
| `max_pages` | int or null | YES | Page limit. Set to null if not applicable. |
| `required` | bool | YES | Whether this section is mandatory. |
| `notes` | string | no | Specific guidance injected into Agent 5 for this section. |

> Use `max_words` OR `max_pages`, not both. Set the unused one to `null`.

### Validation Rules (enforced by `format_loader.validate_format`)

- `format_id` must be lowercase with no spaces or slashes
- `domain_keywords` must be a non-empty list
- `sections` must be a non-empty list with all required section keys present
- The `_instructions` block from the template must be removed before upload

---

## 4. New Agent: FormatMatcher

**File:** `agents/format_matcher.py`  
**Position in pipeline:** Between Agent 4 (Methodology) and Agent 5 (Grant Writing)

### Inputs
- `topic` (str) — the research topic
- `methodology` (dict) — Agent 4 Schema 4 output
- `formats` (dict) — all loaded format records from `format_loader.load_all_formats()`
- `user_override` (str | None) — `format_id` if user selected manually, else `None`

### Logic
1. If `user_override` is set and valid → return immediately, skip LLM call
2. Build a compact `format_summary_list` (excludes full section specs to keep prompt small)
3. Single Groq call: topic + methodology summary + format summaries → `selected_format_id` + `reasoning`
4. Validate returned `format_id` exists in loaded formats
5. Return full format record + reasoning

### Output (cache key: `format_match`)
```json
{
  "selected_format_id": "nsf_cise",
  "selected_format": { ...full format record... },
  "reasoning": "Topic is CS/AI, methodology is algorithmic — NSF CISE is the natural home.",
  "llm_selected": true
}
```

### Fallback
If LLM fails or returns an invalid `format_id`, falls back to the first format in the loaded dict without crashing.

---

## 5. Updated Agent 5: Grant Writing

**File:** `agents/grant_agent.py`  
**Signature change:** `run(topic, gap_description, methodology, format_selection)`

### What Changes
- System prompt now dynamically constructed from `format_selection["selected_format"]`
- Section instructions rendered from the `sections` array: name, limit, required flag, notes
- `emphasis`, `avoid`, and `rhetorical_tone` fields injected into the system prompt
- Output JSON now includes `"format_used"` field and a `"sections"` dict keyed by section name
- Fallback return includes `format_used` for traceability

### Section Schema Generation
The output `sections` dict is built dynamically from the format record:
```python
section_schema = { s["name"]: "string content" for s in sections }
```
So a proposal using NSF CISE will have keys `"Project Summary"`, `"Project Description"`, etc., while an NIH R01 will have `"Specific Aims"`, `"Research Strategy"`, etc.

---

## 6. Updated Orchestrator: main.py

### Changes to `run_pipeline`

```python
# At startup: load all formats once
from utils.format_loader import load_all_formats
from agents.format_matcher import run as run_format_matcher

formats = load_all_formats()  # loaded once, passed into tasks

# New task: FormatMatcher (between t5/methodology and t6/grant)
t5b = CustomTask(
    description="Format Matching",
    expected_output="Format selection JSON",
    agent=dummy_agent,
    func=lambda: state.setdefault(
        "format_match",
        load("format_match") or (
            save("format_match", run_format_matcher(
                topic,
                state.get("methodology"),
                formats,
                state.get("user_format_override")   # None if no UI override yet
            )) or delay()
        ) or load("format_match")
    )
)

# Updated t6: now passes format_selection
t6 = CustomTask(
    description="Grant Writing",
    expected_output="Grant JSON",
    agent=dummy_agent,
    func=lambda: state.setdefault(
        "grant",
        load("grant") or (
            save("grant", run_grant(
                topic,
                get_gap_desc(),
                state.get("methodology"),
                state.get("format_match")     # NEW argument
            )) or delay()
        ) or load("grant")
    )
)
```

### Updated task list
```python
tasks=[t1, t2, t2_gate, t3, t4, t4_gate, t5, t5b, t6, t7]
#                                                  ^^^
#                                        FormatMatcher inserted here
```

---

## 7. Streamlit UI Changes: app.py

### Two-Phase Pipeline Split

The UI now runs in two phases with a user interaction gate between them.

**Phase 1** — runs Agents 1–4 automatically on topic submit:
- Literature Mining → Tree → QG1 → Trends → Gaps → QG2 → Methodology
- Displays results: papers, tree visualization, gaps, methodology

**Phase 2** — waits for user format selection, then runs Agents 5–6:
- Format selector shown as UI widget
- User confirms → FormatMatcher runs (or override applied) → Grant + Novelty

### New UI Components

#### A. Format Selector Widget
Shown after Phase 1 completes. Position: between Methodology tab and Grant tab.

```python
# In app.py, after methodology results are displayed:
st.markdown("---")
st.subheader("Select Grant Format")

formats = load_all_formats()  # load at app startup, cache in st.session_state

format_options = {
    fid: f"{fmt['name']} — {fmt['funding_body']}" 
    for fid, fmt in formats.items()
}

# Show LLM recommendation if format_match already cached
cached_match = load("format_match")
llm_default = cached_match.get("selected_format_id") if cached_match else None

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
    if llm_default:
        st.info(f"LLM recommended: **{llm_default}**")

# Show format detail expander
with st.expander(f"About: {formats[selected_format_id]['name']}", expanded=False):
    fmt = formats[selected_format_id]
    st.markdown(f"**Funding Body:** {fmt['funding_body']}")
    st.markdown(f"**Typical Award:** {fmt.get('typical_award_usd', 'N/A')} USD")
    st.markdown(f"**Duration:** {fmt.get('typical_duration_years', 'N/A')} years")
    st.markdown(f"**Emphasis:** {fmt.get('emphasis', '')}")
    if fmt.get("avoid"):
        st.markdown(f"**Avoid:** {fmt['avoid']}")
    st.markdown("**Sections:**")
    for s in fmt.get("sections", []):
        req = "required" if s["required"] else "optional"
        limit = f"{s['max_words']} words" if s.get("max_words") else f"{s.get('max_pages')} pages" if s.get("max_pages") else "no limit"
        st.markdown(f"- **{s['name']}** ({req}, {limit})")

generate_btn = st.button("Generate Grant Proposal →", type="primary")
```

#### B. Custom Format Upload Widget
Shown in a sidebar expander or dedicated tab.

```python
st.sidebar.markdown("---")
st.sidebar.subheader("Custom Grant Format")

# Download template button
with open("schemas_for_user/custom_grant_format_template.json", "r") as f:
    template_content = f.read()

st.sidebar.download_button(
    label="Download Format Template (JSON)",
    data=template_content,
    file_name="custom_grant_format_template.json",
    mime="application/json",
    help="Fill in this template and upload below to use your own grant format."
)

# Upload widget
uploaded_file = st.sidebar.file_uploader(
    "Upload Custom Format (JSON)",
    type=["json"],
    help="Upload a filled-in format template to add it to the selector."
)

if uploaded_file:
    try:
        custom_fmt = json.load(uploaded_file)
        success, errors = register_custom_format(custom_fmt, st.session_state.formats)
        if success:
            st.sidebar.success(
                f"Format '{custom_fmt['format_id']}' loaded and added to the selector."
            )
        else:
            st.sidebar.error("Validation failed:")
            for err in errors:
                st.sidebar.markdown(f"- {err}")
    except json.JSONDecodeError:
        st.sidebar.error("Invalid JSON — check your file and try again.")
```

#### C. Format Badge on Grant Output
When the grant proposal is displayed, show which format was used:

```python
fmt_used = grant_data.get("format_used", "unknown")
fmt_name = formats.get(fmt_used, {}).get("name", fmt_used)
was_llm = cached_match.get("llm_selected", False) if cached_match else False

badge_label = f"{'LLM-selected' if was_llm else 'User-selected'}: {fmt_name}"
st.caption(badge_label)
```

#### D. Tree Visualization (bonus, recommended)
Using Plotly sunburst on the tree JSON from Agent 2:

```python
import plotly.graph_objects as go

def render_tree(tree: dict):
    themes = tree.get("themes", [])
    labels, parents, values = ["Root"], [""], [1]
    for theme in themes:
        labels.append(theme["theme_name"])
        parents.append("Root")
        values.append(len(theme.get("papers", [])))
        for paper in theme.get("papers", []):
            labels.append(paper.get("title", "")[:40])
            parents.append(theme["theme_name"])
            values.append(1)

    fig = go.Figure(go.Sunburst(
        labels=labels, parents=parents, values=values,
        branchvalues="total",
        hovertemplate="<b>%{label}</b><extra></extra>",
        maxdepth=2
    ))
    fig.update_layout(margin=dict(t=0, l=0, r=0, b=0), height=450)
    st.plotly_chart(fig, use_container_width=True)
```

---

## 8. Session State Management

Add to `app.py` initialization block:

```python
# Initialize session state keys
if "formats" not in st.session_state:
    st.session_state.formats = load_all_formats()

if "phase" not in st.session_state:
    st.session_state.phase = 1   # 1 = pre-format-selection, 2 = post

if "user_format_override" not in st.session_state:
    st.session_state.user_format_override = None
```

The `formats` dict lives in session state so custom uploads persist for the session duration without re-loading from disk on every Streamlit rerender.

---

## 9. Cache Keys (full updated list)

| Key | Agent | Written after |
|---|---|---|
| `papers` | Agent 1 | Literature Mining |
| `tree` | Tree Builder | Thematic Clustering |
| `qg1` | Quality Gate 1 | Post-literature gate |
| `trends` | Agent 2 | Trend Analysis |
| `gaps` | Agent 3 | Gap Identification |
| `qg2` | Quality Gate 2 | Post-gap gate |
| `methodology` | Agent 4 | Methodology Design |
| `format_match` | FormatMatcher | **NEW** Format Selection |
| `grant` | Agent 5 | Grant Writing |
| `novelty` | Agent 6 | Novelty Scoring |

The `format_match` cache key means:
- If the user re-runs after changing the format selection in the UI, the old `format_match` must be cleared so the new selection is used
- Add a "Clear format selection" button in the UI that deletes `cache/format_match.json`

---

## 10. Implementation Order

Follow this sequence to avoid broken intermediate states:

```
Step 1 — grant_formats/ directory
  Create all 6 format JSON files.
  Test: python -c "from utils.format_loader import load_all_formats; print(load_all_formats())"

Step 2 — utils/format_loader.py
  Implement load_all_formats(), validate_format(), register_custom_format(), format_summary_list().
  Test: all 6 formats load cleanly with no validation errors printed.

Step 3 — agents/format_matcher.py
  Implement run() with user_override path and LLM path.
  Test: run with MOCK_MODE=true using mock_methodology.json — should return a valid format_id.

Step 4 — agents/grant_agent.py update
  Add format_selection parameter.
  Update system prompt construction from format record.
  Test: run with each of the 6 format records and verify sections dict keys match format sections.

Step 5 — main.py update
  Insert FormatMatcher task between t5 and t6.
  Update t6 lambda to pass format_match.
  Add load_all_formats() call at pipeline startup.
  Test: full CLI run with --topic "..." — verify format_match.json appears in cache/.

Step 6 — app.py update
  Add session_state initialization.
  Implement Phase 1 / Phase 2 split.
  Add format selector widget.
  Add custom upload sidebar widget.
  Add download template button.
  Add format badge on grant output.
  Test: full UI run, change format in dropdown, verify grant output changes.

Step 7 — Tree visualization (if time allows)
  Add Plotly sunburst render function.
  Place in Literature / Tree tab.
```

---

## 11. Testing Checklist

- [ ] All 6 seeded formats load without validation errors
- [ ] `validate_format` catches: missing required keys, bad format_id, empty sections
- [ ] FormatMatcher returns correct `format_id` for a CS/AI topic (expect nsf_cise)
- [ ] FormatMatcher returns correct `format_id` for a biomedical topic (expect nih_r01 or nih_r21)
- [ ] User override bypasses LLM call (verify no Groq API call made)
- [ ] Grant output sections dict keys match the selected format's section names
- [ ] Custom format template downloads correctly from UI
- [ ] Valid custom JSON uploads and appears in dropdown
- [ ] Invalid custom JSON shows per-error validation messages
- [ ] `format_match.json` written to cache/ after FormatMatcher runs
- [ ] Clearing format_match cache and re-selecting triggers re-run of Agent 5
- [ ] `format_used` field appears correctly in grant output display

---

## 12. Future Work Items (for report)

- **PDF grant-call ingestion:** User uploads an official funding call PDF → a sub-agent extracts the section structure and populates the format schema automatically. Enables self-extending format DB without manual JSON authoring.
- **Multi-format comparison:** Run Agent 5 with the top-2 LLM-recommended formats in parallel (CrewAI hierarchical) and let the user choose the better output.
- **Gap × Format joint selection:** Currently gap is auto-selected before format is chosen. A richer UI would show gaps × recommended formats as a matrix and let the researcher select a (gap, format) pair together.
- **Format version tracking:** Grant calls update annually. Add a `version_year` field and a staleness warning in the UI when a format record is older than 12 months.
