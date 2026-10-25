"""Logging, tracing and the live console view.

- ``TraceLogger``: appends every orchestration event (prompts metadata,
  worker turns, tool results, critic verdicts, reflections, lessons) to a
  per-run ``.jsonl`` file - the full audit trail of the run.
- ``ConsoleReporter``: pretty real-time dialogue view. Uses ``rich`` when
  installed and degrades gracefully to plain ANSI colours.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from .schemas import Lesson, RunResult
from .tools import ToolResult

try:
    from rich.console import Console as RichConsole

    _HAS_RICH = True
except ImportError:  # pragma: no cover - rich is optional
    _HAS_RICH = False

_COLORS = {
    "worker": "cyan",
    "critic": "yellow",
    "reflector": "magenta",
    "tool": "green",
    "system": "bright_black",
    "lesson": "bright_blue",
}
_ANSI = {
    "cyan": "36",
    "yellow": "33",
    "magenta": "35",
    "green": "32",
    "bright_black": "90",
    "bright_blue": "94",
    "white": "37",
}


def _short(text: Any, limit: int = 110) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 3] + "..."


def _now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


class TraceLogger:
    """Append-only JSONL trace of one run."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a", encoding="utf-8")

    def event(self, name: str, **payload: Any) -> None:
        record = {"ts": _now_utc(), "event": name, **payload}
        self._handle.write(json.dumps(record, ensure_ascii=True, default=str) + "\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()


class ConsoleReporter:
    """Colour-coded live view of the agent dialogue."""

    def __init__(self, quiet: bool = False, console: "RichConsole | None" = None) -> None:
        self.quiet = quiet
        if console is not None:
            self._console = console
        else:
            self._console = RichConsole(highlight=False) if _HAS_RICH else None

    # ------------------------------------------------------------------ core
    def _emit(self, role: str, text: str, bold: bool = False) -> None:
        if self.quiet:
            return
        tag = ("[" + role.upper() + "]").ljust(12)
        if self._console is not None:
            color = _COLORS.get(role, "white")
            style = f"bold {color}" if bold else color
            self._console.print(f"[{style}]{tag}[/{style}] {_short(text, 400)}")
        else:
            code = _ANSI.get(_COLORS.get(role, "white"), "37")
            prefix = "\033[1m" if bold else ""
            print(f"\033[{code}m{prefix}{tag}\033[0m {_short(text, 400)}")

    # ----------------------------------------------------------------- events
    def run_start(self, run_id: str, task: str) -> None:
        if self.quiet:
            return
        if self._console is not None:
            self._console.rule(f"[bold]run {run_id}[/bold]")
        else:
            print("\n===== run " + run_id + " =====")
        self._emit("system", "task: " + task)

    def lessons(self, lessons: list[Lesson]) -> None:
        if not lessons:
            self._emit("system", "no relevant lessons found in the store")
            return
        self._emit(
            "lesson",
            "retrieved " + str(len(lessons)) + " lesson(s) into the worker context",
        )
        for lesson in lessons:
            self._emit("lesson", "- [" + lesson.problem_type + "] " + lesson.rule_to_follow)

    def worker_action(self, thought: str, tool: str, arguments: dict) -> None:
        self._emit("worker", thought)
        self._emit("worker", "-> tool " + tool + "(" + json.dumps(arguments, sort_keys=True) + ")")

    def worker_final(self, thought: str, answer: str) -> None:
        self._emit("worker", thought)
        self._emit("worker", "FINAL ANSWER: " + answer, bold=True)

    def tool(self, result: ToolResult) -> None:
        if result.ok:
            self._emit("tool", result.tool + " -> " + _short(result.output, 200))
        else:
            self._emit("tool", result.tool + " -> ERROR: " + str(result.error), bold=True)

    def critic(self, verdict, *, final: bool) -> None:
        scope = "final" if final else "step"
        text = "[" + scope + "] " + verdict.verdict.upper()
        if verdict.issues:
            text += ": " + "; ".join(verdict.issues)
        if verdict.verdict != "approve" and verdict.hint:
            text += " | hint: " + verdict.hint
        self._emit("critic", text, bold=verdict.verdict != "approve")

    def reflection(self, summary: str) -> None:
        self._emit("reflector", summary)

    def lesson(self, lesson: Lesson, is_new: bool) -> None:
        action = "saved new lesson" if is_new else "reinforced existing lesson (dedup)"
        self._emit("lesson", action + ": " + lesson.rule_to_follow, bold=is_new)

    def run_end(self, result: RunResult) -> None:
        self._emit(
            "system",
            "run finished: status=" + result.status
            + " | tool_steps=" + str(len(result.steps))
            + " | revisions=" + str(result.revisions)
            + " | tokens=" + str(result.prompt_tokens + result.completion_tokens)
            + " | duration=" + str(result.duration_seconds) + "s",
            bold=True,
        )
