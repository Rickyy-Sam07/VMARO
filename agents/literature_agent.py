import os
import json
from utils.schema import safe_parse, call_gemini_with_retry
from utils.multi_api_fetcher import MultiAPIFetcher
from utils.topic_normalizer import normalize_topic

def run(topic: str) -> dict:
    # ── Stage 00: Normalize any freeform user input ───────────────────────
    print("[Stage 00]     Topic Normalization")
    topic_payload = normalize_topic(topic)
    core_topic = topic_payload["core_topic"]
    print(f"  ✓ core_topic:  {core_topic}")
    print(f"  ✓ domain:      {topic_payload['domain']}")
    print(f"  ✓ keywords:    {topic_payload['keywords']}")
    print(f"  ✓ variants:    {topic_payload['query_variants']}\n")

    print("[Agent 1]      Literature Mining")
    
    # MOCK_MODE check
    if os.getenv("MOCK_MODE", "").lower() == "true":
        with open("mock_data/mock_papers.json") as f:
            return json.load(f)

    fallback = {
        "topic": topic,        # raw user input — must match _topic.txt for cache validation
        "papers": []
    }

    try:
        # Pass 1 — Multi-API fan-out using structured payload
        # Fans out over query_variants × domain-selected APIs, then deduplicates
        print(f"  🔍 Starting multi-source retrieval for: '{core_topic}'")
        
        fetcher = MultiAPIFetcher()
        filtered = fetcher.fetch_all(topic_payload, max_papers=20)
        
        if not filtered:
            print("  ❌ No papers found from any source")
            return fallback
        
        print(f"  ✓ Retrieved {len(filtered)} unique papers after deduplication\n")
        
        # Prepare papers for LLM (rename 'source' to 'api_source' for clarity)
        papers_for_llm = []
        for paper in filtered:
            papers_for_llm.append({
                "title": paper.get("title", ""),
                "abstract": paper.get("abstract", ""),
                "year": paper.get("year", 0),
                "authors": paper.get("authors", []),
                "api_source": paper.get("source", "Unknown"),
                "url": paper.get("url", "")
            })
        
        # Pass 2 - Summarisation via Groq
        # Use core_topic (clean canonical form) instead of raw user paragraph
        sys_inst = f"""You are a research assistant.
Return ONLY valid JSON matching this schema:
{{
  "topic": "{core_topic}",
  "papers": [
    {{
      "title": "exact title from input",
      "year": 2024,
      "summary": "2-3 sentence summary",
      "contribution": "single most novel contribution",
      "api_source": "exact api_source from input (e.g., Semantic Scholar, arXiv, PubMed)",
      "url": "exact url from input"
    }}
  ]
}}"""

        prompt = f"""Below are research papers on "{core_topic}" from multiple academic databases.
For each paper, write a 2–3 sentence plain-English summary and identify the single most
important contribution. Keep the 'api_source' and 'url' fields exactly as provided.

IMPORTANT: Process ALL {len(papers_for_llm)} papers provided. Do not drop any papers.

Papers: {json.dumps(papers_for_llm)}"""

        # Retry logic for JSON failure
        for attempt in range(2):
            try:
                response = call_gemini_with_retry(prompt, system_instruction=sys_inst)
                result = safe_parse(response.text, required_keys=["topic", "papers"])
                
                # Post-process: ensure api_source and url are preserved
                source_lookup = {p["title"]: {"api_source": p["api_source"], "url": p["url"]} 
                                for p in papers_for_llm}
                
                for paper in result.get("papers", []):
                    title = paper.get("title", "")
                    # If LLM dropped api_source or url, restore from original data
                    if not paper.get("api_source") or paper.get("api_source") == "Unknown":
                        if title in source_lookup:
                            paper["api_source"] = source_lookup[title]["api_source"]
                            paper["url"] = source_lookup[title]["url"]
                    if not paper.get("url"):
                        if title in source_lookup:
                            paper["url"] = source_lookup[title]["url"]
                
                # Force topic field to raw user input — cache.py validates
                # papers.json["topic"] against _topic.txt, which stores the original.
                # core_topic was only used for retrieval quality; the cache key
                # must be the original string the user typed.
                result["topic"] = topic

                return result
            except Exception as e:
                if attempt == 1:
                    print(f"Agent1 Groq failed: {e}")
                    raise
    
    except Exception as e:
        print(f"Agent1 failed: {e}")
        return fallback
