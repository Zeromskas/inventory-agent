"""Isolated task execution, scoring, and saved evaluation traces."""
from contextlib import closing
from dataclasses import asdict
import hashlib
import json
import logging
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from time import perf_counter

from tqdm import tqdm

from inventory.database import create_database, get_connection
from inventory.run_result import RunResult
from .answer_judge import DEFAULT_JUDGE_MODEL, judge_answer

logger = logging.getLogger(__name__)


def read_products(db_path):
    with closing(get_connection(db_path)) as conn:
        return [dict(row) for row in conn.execute(
            "SELECT id, name, quantity, price_cents FROM products ORDER BY id"
        )]


def check_result(task, initial_products, actual_products, result):
    expected = task["expected_products"] if task["operation"] == "write" else initial_products
    products_correct = actual_products == sorted(expected, key=lambda product: product["id"])
    stop_correct = None if result.stop_reason is None else result.stop_reason == task["expected_stop_reason"]
    return {"products_correct": products_correct, "answer_correct": None,
            "stop_reason_correct": stop_correct}


def count_tool_calls(result):
    """Count rejected calls separately from task correctness and business outcomes."""
    invalid = 0
    for call in result.tool_calls:
        code = (call["result"]["error"] or "").split(":", 1)[0]
        if code.startswith("INVALID_") or code in {"UNKNOWN_TOOL", "NO_CHANGES"}:
            invalid += 1
    return {"total": len(result.tool_calls), "invalid": invalid}


def validate_tasks(tasks):
    """Check task definitions before creating output files or databases."""
    identifiers = [task["id"] for task in tasks]
    if not identifiers or len(set(identifiers)) != len(identifiers):
        raise ValueError("Task IDs must be nonempty and unique")
    for task in tasks:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", task["id"]):
            raise ValueError("Task IDs must contain only letters, digits, underscores or hyphens")
        if task["operation"] not in {"read", "write"}:
            raise ValueError("Task operation must be read or write")
        task["expected_stop_reason"]
        if task["operation"] == "read" or "expected_answer" in task:
            if not isinstance(task["expected_answer"], str) or not task["expected_answer"].strip():
                raise ValueError("Answer checks need a nonempty expected_answer string")
        if task["operation"] == "write":
            task["expected_products"]


def task_status(task, result, checks, error):
    """Known failures take priority over checks awaiting review."""
    if error or result.stop_reason == "execution_error" or any(value is False for value in checks.values()):
        return "failed"
    if (checks["stop_reason_correct"] is None
            or ("expected_answer" in task and checks["answer_correct"] is None)):
        return "needs_review"
    return "passed"


def run_task(system_class, task, seed_products, *, judge_model, system_options):
    """Run and score one task against its own temporary database."""
    with TemporaryDirectory(prefix="inventory-evaluation-") as directory:
        db_path = create_database(Path(directory) / "test.db", seed_products)
        initial_products = read_products(db_path)
        error = None
        started = perf_counter()
        try:
            system = system_class(db_path=db_path, **system_options)
            messages = [{"role": "user", "content": task["request"]}]
            result = system.run(messages)
            if not isinstance(result, RunResult):
                raise TypeError("run(messages) must return RunResult")
        except Exception as exc:
            logger.exception("Task %s failed", task["id"])
            error = f"{type(exc).__name__}: {exc}"
            result = RunResult("", [], "execution_error")
        seconds = round(perf_counter() - started, 6)
        actual_products = read_products(db_path)
        checks = check_result(task, initial_products, actual_products, result)
        grade = None
        if judge_model and "expected_answer" in task:
            grade = judge_answer(task, result, judge_model)
            checks["answer_correct"] = grade["correct"]
        tool_counts = count_tool_calls(result)
        status = task_status(task, result, checks, error)
        return {"id": task["id"], "system": system_class.__name__, "task": task,
                "system_options": system_options,
                "initial_products": initial_products, "run": asdict(result),
                "actual_products": actual_products, "checks": checks,
                "tool_calls": tool_counts, "answer_judge": grade,
                "status": status, "error": error, "seconds": seconds}


def build_summary(traces, config, elapsed_seconds):
    """Aggregate task results without changing their individual verdicts."""
    return {
        "config": config,
        "total": len(traces),
        "passed": sum(t["status"] == "passed" for t in traces),
        "failed": sum(t["status"] == "failed" for t in traces),
        "needs_review": sum(t["status"] == "needs_review" for t in traces),
        "db_state": {"correct": sum(t["checks"]["products_correct"] for t in traces),
                     "incorrect": sum(not t["checks"]["products_correct"] for t in traces)},
        "tool_calls": {"total": sum(t["tool_calls"]["total"] for t in traces),
                       "invalid": sum(t["tool_calls"]["invalid"] for t in traces)},
        "answer_checks": {"passed": sum(t["checks"]["answer_correct"] is True for t in traces),
                          "failed": sum(t["checks"]["answer_correct"] is False for t in traces),
                          "needs_review": sum("expected_answer" in t["task"] and t["checks"]["answer_correct"] is None for t in traces)},
        "timing": {
            "system_seconds": round(sum(t["seconds"] for t in traces), 6),
            "judge_seconds": round(sum((t["answer_judge"] or {}).get("seconds", 0) for t in traces), 6),
            "total_seconds": round(elapsed_seconds, 6),
        },
    }


def evaluate(system_class, suite, output_dir, *, judge_model=DEFAULT_JUDGE_MODEL, **system_options):
    """Run each request in isolation. Expected fields are never passed to a system."""
    started = perf_counter()
    validate_tasks(suite["tasks"])
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    task_snapshot = json.dumps(suite, indent=2, ensure_ascii=False) + "\n"
    (output_dir / "tasks.json").write_text(task_snapshot)
    config = {
        "system": f"{system_class.__module__}.{system_class.__name__}",
        "system_options": system_options,
        "judge_model": judge_model,
        "tasks_sha256": hashlib.sha256(task_snapshot.encode()).hexdigest(),
    }

    traces = []
    for task in tqdm(suite["tasks"], desc="Evaluating", unit="task"):
        trace = run_task(system_class, task, suite["initial_products"],
                         judge_model=judge_model, system_options=system_options)
        (output_dir / f"{task['id']}.json").write_text(json.dumps(trace, indent=2, ensure_ascii=False) + "\n")
        traces.append(trace)
        tqdm.write(f"{task['id']}: {trace['status']}")

    summary = build_summary(traces, config, perf_counter() - started)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary
