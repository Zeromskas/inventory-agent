"""Run evaluation: python3 project/evaluate.py [--system baseline] [--judge-model MODEL]."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from evaluation.evaluator import evaluate
from evaluation.answer_judge import DEFAULT_JUDGE_MODEL

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", choices=("agent", "baseline"), default="agent")
    parser.add_argument("--tasks", type=Path, default=ROOT / "evaluation" / "tasks.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model", help="Ollama model for agent evaluation")
    judge = parser.add_mutually_exclusive_group()
    judge.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL,
                       help=f"Answer judge model (default: {DEFAULT_JUDGE_MODEL})")
    judge.add_argument("--no-judge", dest="judge_model", action="store_const", const=None,
                       help="Skip model grading and review answers manually")
    parser.add_argument("--think", action=argparse.BooleanOptionalAction, default=None,
                        help="Enable or disable thinking for a supported model")
    args = parser.parse_args()
    if args.system == "baseline":
        if args.model is not None or args.think is not None:
            parser.error("--model and --think apply only to the agent")
        from evaluation.baseline import ScriptedBaseline
        system_class = ScriptedBaseline
    else:
        from inventory.agent import InventoryAgent, MODEL
        system_class = InventoryAgent
    suite = json.loads(args.tasks.read_text())
    output = args.output or ROOT / "results" / datetime.now(timezone.utc).strftime(args.system + "-%Y%m%dT%H%M%S-%fZ")
    options = {} if args.system == "baseline" else {"model": args.model or MODEL, "think": args.think}
    summary = evaluate(system_class, suite, output, judge_model=args.judge_model, **options)
    print(json.dumps(summary, indent=2))
    print(f"Traces saved to {output}")
    print("Unjudged answers need manual review. LLM judgments are approximate.")


if __name__ == "__main__":
    main()
