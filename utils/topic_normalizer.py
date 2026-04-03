# utils/topic_normalizer.py
"""
Stage 00 — Topic Normalization

Converts any freeform user input (word, phrase, paragraph) into a
structured retrieval payload consumed by literature_agent → multi_api_fetcher.

Short inputs (<= 5 words) → instant passthrough, no API call.
Long inputs            → Groq LLM (tries models in order, heuristic on full failure).

Output schema (guaranteed — every key always present):
{
    "core_topic":        str,       # 2-5 word canonical label
    "keywords":          List[str], # 4-8 high-signal academic terms
    "domain":            str,       # biomedical|cs_ai|engineering|social_science|physics|general
    "scope_constraints": str,       # exclusions/focus areas implied, or ""
    "research_intent":   str,       # explore_topic|survey_gaps|propose_methodology|...
    "query_variants":    List[str], # 3 alternative search strings
    "relations":         List[str], # "X applied to Y" phrases, or []
}
"""

import re
import time

from groq import Groq
from utils.schema import get_api_key, safe_parse


# ── Model priority list ────────────────────────────────────────────────────────
# Tried in order. First success wins. All are fast/cheap — this is parsing not reasoning.
GROQ_FAST_MODELS = [
    "llama-3.1-8b-instant",    # Groq's current recommended fast model
    "llama-3.2-3b-preview",    # cheaper fallback
    "gemma2-9b-it",            # last resort
]

KNOWN_DOMAINS = {"biomedical", "cs_ai", "engineering", "social_science", "physics", "general"}


# ── Prompt ────────────────────────────────────────────────────────────────────

NORMALIZER_PROMPT = """You are a research topic parser for an academic literature retrieval system.
Given any user input — a word, phrase, or multi-sentence paragraph — extract structured intent.

Return ONLY valid JSON, no markdown, no preamble:
{{
  "core_topic": "2-5 word canonical label for this research area",
  "keywords": ["4-8 terms, 1-3 words each. HIGH-SIGNAL academic terms for arXiv/PubMed/Semantic Scholar APIs. BAD: ai, data, improve. GOOD: federated learning, differential privacy, clinical NLP"],
  "domain": "one of exactly: biomedical | cs_ai | engineering | social_science | physics | general",
  "scope_constraints": "any exclusions or focus areas implied by the user, or empty string",
  "research_intent": "one of exactly: survey_gaps | propose_methodology | review_trends | benchmark_comparison | explore_topic",
  "query_variants": ["3 alternative search strings covering different framings of the same topic"],
  "relations": ["X applied to Y or X using Z phrases if clearly implied, else empty list"]
}}

User input: {raw_input}"""


# ── Public API ─────────────────────────────────────────────────────────────────

def normalize_topic(raw_input: str) -> dict:
    """
    Stage 00: Convert any freeform user input into a structured retrieval payload.

    Flow:
      <= 5 words → _passthrough()          (no API call, already a clean query)
      > 5 words  → try GROQ_FAST_MODELS    (LLM parsing, cheapest model first)
                 → _heuristic_fallback()   (if all LLM calls fail — still useful signal)
    """
    raw_input = raw_input.strip()
    word_count = len(raw_input.split())

    if word_count <= 5:
        print("  ⚡ [Stage 00] Short input — passthrough (no API call)")
        return _passthrough(raw_input)

    print(f"  🧠 [Stage 00] Normalizing {word_count}-word input via LLM...")

    parsed = None
    for model in GROQ_FAST_MODELS:
        try:
            parsed = _call_normalizer(raw_input, model=model)
            print(f"  ✓ [Stage 00] Parsed via {model}")
            break
        except Exception as e:
            print(f"  ⚠️  [Stage 00] {model} failed: {str(e)[:80]}")

    if not parsed:
        print("  ⚠️  [Stage 00] All models failed — using heuristic extraction")
        return _heuristic_fallback(raw_input)

    # Hardened field defaults — pipeline never breaks on a partial parse
    core = parsed.get("core_topic") or _extract_core(raw_input)
    payload = {
        "core_topic":        core,
        "keywords":          parsed.get("keywords") or _extract_keywords(raw_input),
        "domain":            parsed.get("domain", "general"),
        "scope_constraints": parsed.get("scope_constraints", ""),
        "research_intent":   parsed.get("research_intent", "explore_topic"),
        "query_variants":    parsed.get("query_variants") or [core],
        "relations":         parsed.get("relations", []),
    }

    # Clamp domain to known set (downstream uses it as a dict key)
    if payload["domain"] not in KNOWN_DOMAINS:
        payload["domain"] = "general"

    return payload


# ── Internal ───────────────────────────────────────────────────────────────────

def _call_normalizer(raw_input: str, model: str, retries: int = 2) -> dict:
    """
    Call Groq with the given model and return a parsed dict.
    Retries on 429/503 only; other errors surface immediately so the
    caller can try the next model in GROQ_FAST_MODELS.
    """
    client = Groq(api_key=get_api_key())
    prompt = NORMALIZER_PROMPT.format(raw_input=raw_input)

    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1,    # near-deterministic for reliable JSON
                max_tokens=512,
            )
            raw_json = response.choices[0].message.content
            return safe_parse(raw_json)

        except Exception as e:
            err = str(e)
            if "429" in err or "rate_limit" in err.lower():
                match = (re.search(r'try again in (\d+\.?\d*)s', err.lower()) or
                         re.search(r'retry after (\d+)', err.lower()))
                wait = int(float(match.group(1))) + 2 if match else 15
                wait = min(max(wait, 5), 45)
                print(f"    429 — waiting {wait}s (attempt {attempt+1}/{retries})")
                time.sleep(wait)
                client = Groq(api_key=get_api_key())  # rotate key on 429
            elif "503" in err or "unavailable" in err.lower():
                print(f"    503 — waiting 10s (attempt {attempt+1}/{retries})")
                time.sleep(10)
            else:
                raise   # model error / decommissioned → try next model immediately

    raise Exception(f"Max retries exceeded for {model}")


def _heuristic_fallback(raw_input: str) -> dict:
    """
    When ALL LLM calls fail on a long input, extract signal heuristically.
    Produces meaningful query terms instead of dumping the full paragraph
    into API queries (which is what the old bare-except passthrough did).
    """
    # Strip filler words that appear in natural language research descriptions
    filler = (
        r'\b(i want to|i am interested in|explore|looking into|can we|how to|'
        r'please|also|especially|whether|or not|the|a|an|in|on|of|for|with|by|'
        r'is|are|was|were|be|been|being|have|has|had|do|does|did|will|would|'
        r'could|should|may|might|shall|improve|introduce|use|used|using|'
        r'approach|method|technique|study|research|paper|work)\b'
    )
    cleaned = re.sub(filler, ' ', raw_input.lower())
    cleaned = re.sub(r'[^\w\s-]', ' ', cleaned)   # drop punctuation
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    # Words >4 chars are rarely stopwords — use length as an informativeness proxy
    words = list(dict.fromkeys(w for w in cleaned.split() if len(w) > 4))

    # Bigrams from meaningful words (captures "federated learning", "secure aggregation")
    bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]

    keywords = words[:6]
    core = " ".join(keywords[:4])
    variants = [core]
    if len(keywords) > 3:
        variants.append(" ".join(keywords[2:6]))  # shifted window = different framing

    return {
        "core_topic":        core or raw_input[:50],
        "keywords":          keywords or raw_input.split()[:6],
        "domain":            "general",
        "scope_constraints": "",
        "research_intent":   "explore_topic",
        "query_variants":    variants or [raw_input[:50]],
        "relations":         bigrams[:3],
    }


def _extract_core(raw_input: str) -> str:
    """Extract a short core label from raw text — used as field-level fallback."""
    words = [w for w in raw_input.split() if len(w) > 3]
    return " ".join(words[:4]) if words else raw_input[:50]


def _extract_keywords(raw_input: str) -> list:
    """Extract meaningful keyword candidates — used as field-level fallback."""
    words = list(dict.fromkeys(
        w.lower() for w in raw_input.split()
        if len(w) > 4 and w.lower() not in
        {'that', 'this', 'with', 'from', 'have', 'they', 'their', 'about', 'which', 'while'}
    ))
    return words[:8]


def _passthrough(raw_input: str) -> dict:
    """
    Fast path for short, already-clean inputs.
    Produces a minimal but valid payload so downstream agents
    never need to branch on whether Stage 00 ran.
    """
    return {
        "core_topic":        raw_input,
        "keywords":          raw_input.split(),
        "domain":            "general",
        "scope_constraints": "",
        "research_intent":   "explore_topic",
        "query_variants":    [raw_input],
        "relations":         [],
    }
