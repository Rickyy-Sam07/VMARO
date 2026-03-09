import json
from utils.schema import safe_parse, call_gemini_with_retry

def run(topic: str, primary_desc: str, primary_meth: dict, challenger_desc: str, challenger_meth: dict) -> dict:
    print("[Evaluator]    Methodology Quality Evaluation")
    
    if not challenger_meth:
        print("  ↳ Single methodology detected, skipping parallel evaluation.")
        return {
            "winner": "A",
            "methodology_a_score": 1.0,
            "methodology_b_score": 0.0,
            "reasoning": "Single methodology generated (no challenger gap available).",
            "winning_methodology": primary_meth,
            "winning_gap_description": primary_desc,
            "parallel_was_run": False
        }

    sys_inst = """You are a senior scientific reviewer evaluating two competing research methodologies for a grant proposal.
Return ONLY valid JSON matching this schema:
{
  "winner": "A",
  "methodology_a_score": 0.85,
  "methodology_b_score": 0.72,
  "reasoning": "A short paragraph explaining why the winner is stronger.",
  "winning_methodology": { ... the exact JSON of the winning methodology ... },
  "winning_gap_description": "the exact text of the winning gap description"
}"""

    prompt = f"""Evaluate these two methodologies for the topic "{topic}".

Criteria:
1. Scientific coherence (does the methodology logically address the gap?)
2. Scope appropriateness (is it realistic for a standard grant cycle?)
3. Methodological novelty (does it go beyond obvious approaches?)
4. Phase clarity (are the research phases and deliverables clear?)
5. Gap fit (how tightly does the methodology address its specific stated gap?)

Methodology A (Addresses Gap: "{primary_desc}")
{json.dumps(primary_meth, indent=2)}

Methodology B (Addresses Gap: "{challenger_desc}")
{json.dumps(challenger_meth, indent=2)}

Pick the strongest methodology based on the criteria above."""

    for attempt in range(2):
        try:
            response = call_gemini_with_retry(prompt, system_instruction=sys_inst)
            result = safe_parse(response.text, required_keys=["winner", "methodology_a_score", "methodology_b_score", "reasoning", "winning_methodology", "winning_gap_description"])
            result["parallel_was_run"] = True
            
            # Enforce output matches input structures
            if result["winner"] == "B":
                result["winning_methodology"] = challenger_meth
                result["winning_gap_description"] = challenger_desc
            else:
                result["winning_methodology"] = primary_meth
                result["winning_gap_description"] = primary_desc
                
            return result
        except Exception as e:
            if attempt == 1:
                print(f"[Evaluator] LLM failed: {e}")
                # Fallback to A
                return {
                    "winner": "A",
                    "methodology_a_score": 1.0,
                    "methodology_b_score": 0.0,
                    "reasoning": f"Evaluator failed to parse LLM response ({e}). Defaulting to primary gap.",
                    "winning_methodology": primary_meth,
                    "winning_gap_description": primary_desc,
                    "parallel_was_run": True
                }
