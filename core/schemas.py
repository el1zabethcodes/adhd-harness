"""Typed data models shared across the harness (Pydantic v2).

Every artefact that flows between agents, the orchestrator, the tool layer and
the lesson store is defined here, so the whole system has one schema source of
truth.
"""
from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


def _now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# --------------------------------------------------------------------------- #
# Long-term memory: lessons
# --------------------------------------------------------------------------- #
class Lesson(BaseModel):
    """A durable, generalizable rule distilled by the Reflection agent."""

    id: str = Field(default_factory=lambda: _new_id("lesson"))
    problem_type: str
    failure_mode: str
    rule_to_follow: str
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_utc)
    origin_run_id: str | None = None
    times_reinforced: int = 0  # re-proposed by later reflections (dedup merges)
    times_used: int = 0        # injected into a worker context
    times_helped: int = 0      # injected AND the run ended successfully

    def match_text(self) -> str:
        """Text used for retrieval scoring (problem type + failure + rule + tags)."""
        return " ".join(
            [
                self.problem_type.replace("_", " "),
                self.failure_mode.replace("_", " "),
                self.rule_to_follow,
                " ".join(self.tags),
            ]
        )


class LessonDraft(BaseModel):
    """A lesson candidate proposed by the Reflection agent (before storage)."""

    problem_type: str
    failure_mode: str
    rule_to_follow: str
    tags: list[str] = Field(default_factory=list)


class ScoredLesson(BaseModel):
    lesson: Lesson
    score: float


# --------------------------------------------------------------------------- #
# Tool layer
# --------------------------------------------------------------------------- #
class ToolCall(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    ok: bool
    output: str = ""
    error: str | None = None


# --------------------------------------------------------------------------- #
# Worker protocol (Thought - Action - Observation)
# --------------------------------------------------------------------------- #
class WorkerTurn(BaseModel):
    """One Worker reply: exactly one of `action` or `final_answer`."""

    thought: str = ""
    action: ToolCall | None = None
    final_answer: str | None = None

    @model_validator(mode="after")
    def _exactly_one_of_action_or_final(self) -> "WorkerTurn":
        if (self.action is None) == (self.final_answer is None):
            raise ValueError(
                "exactly one of 'action' or 'final_answer' must be provided"
            )
        return self


class TAOStep(BaseModel):
    """One executed Thought-Action-Observation step of the trajectory."""

    step: int
    thought: str = ""
    tool: str | None = None
    arguments: dict[str, Any] | None = None
    observation: str | None = None
    ok: bool | None = None


# --------------------------------------------------------------------------- #
# Critic protocol
# --------------------------------------------------------------------------- #
class CriticVerdict(BaseModel):
    verdict: Literal["approve", "revise", "fail"]
    issues: list[str] = Field(default_factory=list)
    hint: str | None = None
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


# --------------------------------------------------------------------------- #
# Reflection protocol
# --------------------------------------------------------------------------- #
class ReflectionOutcome(BaseModel):
    summary: str = ""
    lessons: list[LessonDraft] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
class RunConfig(BaseModel):
    """Hard safety limits and loop behaviour of the orchestrator."""

    max_turns: int = 12
    max_revisions: int = 3              # critic "revise" loops on final answers
    max_tokens_budget: int = 60_000
    timeout_seconds: float = 300.0
    repeat_call_abort: int = 3          # identical tool call N times in a row
    critic_every_step: bool = True      # critic also judges intermediate steps
    max_lessons_injected: int = 3


class RunResult(BaseModel):
    run_id: str
    task: str
    problem_type: str
    status: str  # success | failed | max_turns | max_revisions | no_progress |
    #             loop_detected | budget_exhausted | timeout | invalid_output
    final_answer: str | None = None
    steps: list[TAOStep] = Field(default_factory=list)
    critic_verdicts: list[CriticVerdict] = Field(default_factory=list)
    lessons_injected: list[str] = Field(default_factory=list)
    lessons_created: list[str] = Field(default_factory=list)
    lessons_reinforced: list[str] = Field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_seconds: float = 0.0
    revisions: int = 0
