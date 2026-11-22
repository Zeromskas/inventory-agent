"""Shared run result. Stop reasons describe execution, not task correctness.

completed means a reply was produced, including clarification or rejection;
step_limit and execution_error indicate execution could not finish normally.
"""
from dataclasses import dataclass, field


@dataclass
class RunResult:
    answer: str
    tool_calls: list[dict]
    stop_reason: str | None = None
    messages: list[dict] = field(default_factory=list)
