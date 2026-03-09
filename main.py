import argparse
import time
import os
from agents.literature_agent import run as run_literature
from agents.tree_agent import run as run_tree
from agents.trend_agent import run as run_trend
from agents.gap_agent import run as run_gap
from agents.methodology_agent import run as run_methodology
from agents.methodology_evaluator import run as run_evaluator
from agents.grant_agent import run as run_grant
from agents.novelty_agent import run as run_novelty
from agents.grant_agent import run as run_grant
from agents.novelty_agent import run as run_novelty
from utils.cache import save, load, CACHE_DIR
from utils.quality_gate import evaluate_quality
from utils.format_loader import load_all_formats
from agents.format_matcher import run as run_format_matcher

try:
    from crewai import Agent, Task, Crew, Process
except ImportError:
    pass

def execute_task_wrapper(func, args_getter, cache_key):
    """A helper to wrap our python functions inside a CrewAI Task execution."""
    def wrapper(context=None):
        cached = load(cache_key)
        if cached:
            return cached
        result = func(*args_getter(context))
        save(cache_key, result)
        delay()
        return result
    return wrapper

def delay():
    print("Cooling down for 2s to allow rotating keys to reset limits...")
    time.sleep(2)

def run_pipeline(topic: str, gap_arg: str = None, no_parallel: bool = False) -> dict:
    print(f"Starting pipeline for topic: '{topic}'\n")
    
    # Write topic marker so Streamlit can detect topic changes
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(os.path.join(CACHE_DIR, "_topic.txt"), "w") as f:
        f.write(topic)

    formats = load_all_formats()

    # Mock OpenAI key to satisfy CrewAI's default Agent(llm=ChatOpenAI()) instantiation without errors
    os.environ["OPENAI_API_KEY"] = "sk-mock-key-for-crewai-init"

    # State container for dicts
    state = {}

    # Define minimal Agents (they don't need real LLMs because we override task.execute)
    dummy_agent = Agent(
        role="VMARO Orchestrator",
        goal="Run the pipeline",
        backstory="Automated pipeline runner",
        allow_delegation=False
    )

    class CustomTask(Task):
        func: object = None
        def execute_sync(self, *args, **kwargs):
            import crewai.task
            # Return a mocked TaskOutput
            try:
                self.func()
                return "Task Complete"
            except Exception as e:
                return f"Task Failed: {e}"

    # Agent 1
    t1 = CustomTask(
        description="Literature Mining",
        expected_output="JSON with papers",
        agent=dummy_agent,
        func=lambda: state.setdefault("papers", load("papers") or (save("papers", run_literature(topic)) or delay()) or load("papers"))
    )

    # Tree Builder
    t2 = CustomTask(
        description="Thematic Clustering",
        expected_output="Tree hierarchy JSON",
        agent=dummy_agent,
        func=lambda: state.setdefault("tree", load("tree") or (save("tree", run_tree(state.get("papers"))) or delay()) or load("tree"))
    )
    
    t2_gate = CustomTask(description="Quality Gate 1", expected_output="QG output", agent=dummy_agent, 
        func=lambda: state.setdefault("qg1", load("qg1") or (save("qg1", evaluate_quality("post_literature", state.get("tree"))) or delay()) or load("qg1")))

    # Agent 2
    t3 = CustomTask(
        description="Trend Analysis",
        expected_output="Trends JSON",
        agent=dummy_agent,
        func=lambda: state.setdefault("trends", load("trends") or (save("trends", run_trend(state.get("tree"))) or delay()) or load("trends"))
    )

    # Agent 3
    t4 = CustomTask(
        description="Gap Identification",
        expected_output="Gaps JSON",
        agent=dummy_agent,
        func=lambda: state.setdefault("gaps", load("gaps") or (save("gaps", run_gap(state.get("tree"), state.get("trends"))) or delay()) or load("gaps"))
    )

    t4_gate = CustomTask(description="Quality Gate 2", expected_output="QG output", agent=dummy_agent,
        func=lambda: state.setdefault("qg2", load("qg2") or (save("qg2", evaluate_quality("post_gap", state.get("gaps"))) or delay()) or load("qg2")))

    def get_confirmed_gap():
        selection = load("user_gap_selection")
        if not selection:
            # Interactive CLI fallback if not cached (i.e., not running from Streamlit)
            all_gaps = state.get("gaps", {}).get("identified_gaps", [])
            selected_gap_id = state.get("gaps", {}).get("selected_gap", "")
            
            if gap_arg:
                # User provided --gap arg
                matched = next((g for g in all_gaps if g["gap_id"] == gap_arg), None)
                if matched:
                    selection = {
                        "gap_id": gap_arg,
                        "source": "user_selected",
                        "description": matched["description"],
                        "is_custom": False
                    }
                else:
                    selection = {
                        "gap_id": "custom",
                        "source": "user_custom",
                        "description": gap_arg,
                        "is_custom": True
                    }
            else:
                # Interactive prompt
                print("\n[CLI] --- Action Required: Select a Research Gap ---")
                for i, g in enumerate(all_gaps):
                    rec = " [LLM Recommended]" if g["gap_id"] == selected_gap_id else ""
                    print(f"{i+1}. [{g['gap_id']}] {g['description']}{rec}")
                print(f"{len(all_gaps)+1}. Define Custom Gap")
                
                choice = input("\nEnter choice number: ").strip()
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(all_gaps):
                        g = all_gaps[idx]
                        selection = {
                            "gap_id": g["gap_id"],
                            "source": "user_selected" if g["gap_id"] != selected_gap_id else "llm_suggested",
                            "description": g["description"],
                            "is_custom": False
                        }
                    else:
                        custom_txt = input("Enter your custom research gap description:\n").strip()
                        selection = {
                            "gap_id": "custom",
                            "source": "user_custom",
                            "description": custom_txt,
                            "is_custom": True
                        }
                except ValueError:
                    print("Invalid choice. Falling back to LLM recommended gap.")
                    g = next(g for g in all_gaps if g["gap_id"] == selected_gap_id)
                    selection = {
                        "gap_id": g["gap_id"],
                        "source": "llm_suggested",
                        "description": g["description"],
                        "is_custom": False
                    }
            
            save("user_gap_selection", selection)

        return selection["description"]

    def get_challenger_gap():
        all_gaps = state.get("gaps", {}).get("identified_gaps", [])
        selection = load("user_gap_selection")
        if not selection or not all_gaps: return None
        
        sorted_gaps = sorted(all_gaps, key=lambda g: g.get("priority_rank", 3))
        if selection.get("source") == "user_custom":
            return sorted_gaps[0]["description"]
        else:
            primary_id = selection.get("gap_id")
            challengers = [g for g in sorted_gaps if g["gap_id"] != primary_id]
            if challengers:
                return challengers[0]["description"]
        return None

    # Agent 4-A (Primary)
    t5a = CustomTask(
        description="Methodology Design (Primary gap)",
        expected_output="Methodology JSON",
        agent=dummy_agent,
        func=lambda: state.setdefault("methodology_a", load("methodology_a") or (save("methodology_a", run_methodology(get_confirmed_gap(), topic)) or delay()) or load("methodology_a"))
    )

    # Agent 4-B (Challenger)
    t5b_meth = CustomTask(
        description="Methodology Design (Challenger gap)",
        expected_output="Methodology JSON",
        agent=dummy_agent,
        func=lambda: state.setdefault(
            "methodology_b", 
            load("methodology_b") or (
                None if no_parallel or not get_challenger_gap() 
                else (save("methodology_b", run_methodology(get_challenger_gap(), topic)) or delay())
            ) or load("methodology_b")
        )
    )

    # Methodology Evaluator
    t5_eval = CustomTask(
        description="Methodology Evaluation",
        expected_output="Evaluated Methodology JSON",
        agent=dummy_agent,
        func=lambda: state.setdefault(
            "methodology_eval", 
            load("methodology_eval") or (
                save("methodology_eval", run_evaluator(
                    topic, 
                    get_confirmed_gap(), 
                    state.get("methodology_a"), 
                    get_challenger_gap() if not no_parallel else None, 
                    state.get("methodology_b")
                )) or delay()
            ) or load("methodology_eval")
        )
    )

    t5b = CustomTask(
        description="Format Matching",
        expected_output="Format selection JSON",
        agent=dummy_agent,
        func=lambda: state.setdefault(
            "format_match",
            load("format_match") or (
                save("format_match", run_format_matcher(
                    topic,
                    state.get("methodology_eval", {}).get("winning_methodology", {}),
                    formats,
                    state.get("user_format_override")
                )) or delay()
            ) or load("format_match")
        )
    )

    # Agent 5
    t6 = CustomTask(
        description="Grant Writing",
        expected_output="Grant JSON",
        agent=dummy_agent,
        func=lambda: state.setdefault("grant", load("grant") or (save("grant", run_grant(topic, state.get("methodology_eval", {}).get("winning_gap_description", get_confirmed_gap()), state.get("methodology_eval", {}).get("winning_methodology", {}), state.get("format_match"))) or delay()) or load("grant"))
    )

    # Agent 6
    t7 = CustomTask(
        description="Novelty Scoring",
        expected_output="Novelty Score JSON",
        agent=dummy_agent,
        func=lambda: state.setdefault("novelty", load("novelty") or (save("novelty", run_novelty(state.get("grant"), state.get("tree"))) or delay()) or load("novelty"))
    )

    # Orchestrate with CrewAI
    crew = Crew(
        agents=[dummy_agent],
        tasks=[t1, t2, t2_gate, t3, t4, t4_gate, t5a, t5b_meth, t5_eval, t5b, t6, t7],
        process=Process.sequential,
        verbose=True
    )
    
    print("[CrewAI] Triggering Crew kickoff...")
    try:
        crew.kickoff()
    except Exception as e:
        print(f"[CrewAI] Real Crew kickoff encountered an error (likely due to mock LLM auth): {e}")
        print("[CrewAI] Falling back to sequential execution of custom tasks...")
        for task in crew.tasks:
            try:
                task.func()
                print(f"[CrewAI] Executed {task.description} successfully.")
            except Exception as e2:
                print(f"[CrewAI] Error executing {task.description}: {e2}")

    return state

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VMARO Orchestrator Pipeline")
    parser.add_argument("--topic", type=str, required=True, help="The research topic to analyze.")
    parser.add_argument("--gap", type=str, required=False, help="Gap ID (e.g., G1) or a custom gap string.")
    parser.add_argument("--no-parallel", action="store_true", help="Skip the challenger gap methodology and evaluation step.")
    args = parser.parse_args()

    results = run_pipeline(args.topic, gap_arg=args.gap, no_parallel=args.no_parallel)
    print("\nPipeline execution complete. Results saved to cache/ directory.")
