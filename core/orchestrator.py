"""Deterministic orchestration of the closed loop:

    retrieve lessons -> [worker -> tool -> critic]* -> reflection -> store

Safety limits (all hard stops): ``max_turns``, ``max_revisions`` (critic
revise loops), ``max_tokens_budget``, ``timeout_seconds``, repeated identical
tool calls (``repeat_call_abort``) and repeated identical final answers
(no-progress detection).

Every run is traced to ``logs/<run_id>.jsonl`` and mirrored to a live,
colour-coded console view.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .agents import AgentFormatError, CriticAgent, ReflectionAgent, WorkerAgent
from .llm import LLMClient, UsageTracker
from .memory import LessonStore
from .schemas import (
    CriticVerdict,
    RunConfig,
    RunResult,
    TAOStep,
)
from .tools import ToolRegistry
from .tracing import ConsoleReporter, TraceLogger

_TERMINAL_STATUSES = {
    "success",
    "failed",
    "max_turns",
    "max_revisions",
    "no_progress",
    "loop_detected",
    "budget_exhausted",
    "invalid_output",
}


def _new_run_id() -> str:
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"run_{stamp}_{uuid.uuid4().hex[:4]}"


@dataclass
class _RunState:
    """Mutable working state of a single run (survives a timeout intact)."""

    run_id: str
    task: str
    problem_type: str
    steps: list[TAOStep] = field(default_factory=list)
    critic_verdicts: list[CriticVerdict] = field(default_factory=list)
    lessons_injected: list[str] = field(default_factory=list)
    final_answer: str | None = None
    revisions: int = 0
    status: str = "running"


class Harness:
    """Runs the worker/critic/reflection loop with persistent self-improvement."""

    def __init__(
        self,
        llm: LLMClient,
        lesson_store: LessonStore,
        tool_registry: ToolRegistry,
        config: RunConfig | None = None,
        *,
        logs_dir: str | Path = "logs",
        reflect: bool = True,
        reporter: ConsoleReporter | None = None,
    ) -> None:
        self.llm = llm
        self.store = lesson_store
        self.tools = tool_registry
        self.config = config or RunConfig()
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.reflect_enabled = reflect
        self.reporter = reporter or ConsoleReporter()
        self._tools_description = tool_registry.describe_for_prompt()

    # ------------------------------------------------------------------ run
    async def run(self, task: str, problem_type: str = "general") -> RunResult:
        run_id = _new_run_id()
        state = _RunState(run_id=run_id, task=task, problem_type=problem_type)
        usage = UsageTracker()
        trace = TraceLogger(self.logs_dir / f"{run_id}.jsonl")
        started = time.perf_counter()

        self.reporter.run_start(run_id, task)
        trace.event("run_start", task=task, problem_type=problem_type,
                    config=self.config.model_dump())

        try:
            await asyncio.wait_for(
                self._solve(task, problem_type, state, usage, trace),
                timeout=self.config.timeout_seconds,
            )
        except asyncio.TimeoutError:
            state.status = "timeout"
            trace.event("timeout", seconds=self.config.timeout_seconds)

        duration = time.perf_counter() - started
        created: list[str] = []
        reinforced: list[str] = []
        if self.reflect_enabled and state.status != "timeout":
            created, reinforced = await self._reflect(state, usage, trace)
        if state.status == "success":
            self.store.record_success(state.lessons_injected)

        result = RunResult(
            run_id=run_id,
            task=task,
            problem_type=problem_type,
            status=state.status,
            final_answer=state.final_answer,
            steps=state.steps,
            critic_verdicts=state.critic_verdicts,
            lessons_injected=state.lessons_injected,
            lessons_created=created,
            lessons_reinforced=reinforced,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            duration_seconds=round(duration, 3),
            revisions=state.revisions,
        )
        trace.event(
            "run_end",
            status=result.status,
            final_answer=result.final_answer,
            tokens=usage.total_tokens,
            duration_seconds=result.duration_seconds,
        )
        trace.close()
        self.reporter.run_end(result)
        return result

    # ----------------------------------------------------------- solve loop
    async def _solve(
        self,
        task: str,
        problem_type: str,
        state: _RunState,
        usage: UsageTracker,
        trace: TraceLogger,
    ) -> None:
        cfg = self.config
        worker = WorkerAgent(self.llm)
        critic = CriticAgent(self.llm)

        # 1. Retrieve and inject the most relevant lessons.
        scored = self.store.retrieve(
            f"{problem_type} {task}",
            top_k=cfg.max_lessons_injected,
            problem_type=problem_type,
        )
        lessons = [item.lesson for item in scored]
        state.lessons_injected = [lesson.id for lesson in lessons]
        if lessons:
            self.store.record_use(state.lessons_injected)
        trace.event(
            "lessons_retrieved",
            lessons=[
                {"id": item.lesson.id, "score": round(item.score, 4),
                 "rule": item.lesson.rule_to_follow}
                for item in scored
            ],
        )
        self.reporter.lessons(lessons)

        hint: str | None = None
        last_call: tuple[str, str] | None = None
        repeat_calls = 0
        last_final: str | None = None
        invalid_outputs = 0

        for turn in range(1, cfg.max_turns + 1):
            if usage.total_tokens >= cfg.max_tokens_budget:
                state.status = "budget_exhausted"
                trace.event("budget_exhausted", tokens=usage.total_tokens)
                return

            # 2. Worker turn (tool call or final answer claim).
            try:
                worker_turn = await worker.act(
                    task=task,
                    tools=self._tools_description,
                    lessons=lessons,
                    history=state.steps,
                    critic_hint=hint,
                    usage=usage,
                )
            except AgentFormatError as exc:
                invalid_outputs += 1
                hint = (
                    "Your previous reply was not valid JSON for the required "
                    f"schema ({exc}). Reply with ONE JSON object only."
                )
                trace.event("worker_invalid_output", attempt=invalid_outputs,
                            error=str(exc))
                if invalid_outputs >= 2:
                    state.status = "invalid_output"
                    return
                continue
            hint = None
            trace.event("worker_turn", turn=turn, output=worker_turn.model_dump())

            if worker_turn.action is not None:
                action = worker_turn.action
                self.reporter.worker_action(
                    worker_turn.thought, action.tool, action.arguments
                )
                # 3. Loop detection: identical tool call repeated in a row.
                call_key = (action.tool, json.dumps(action.arguments, sort_keys=True))
                repeat_calls = repeat_calls + 1 if call_key == last_call else 0
                last_call = call_key
                if repeat_calls + 1 >= cfg.repeat_call_abort:
                    state.status = "loop_detected"
                    trace.event("loop_detected", tool=action.tool,
                                repeated=repeat_calls + 1)
                    return

                result = await self.tools.dispatch(action.tool, action.arguments)
                observation = (
                    result.output if result.ok
                    else "ERROR (" + result.tool + "): " + str(result.error)
                )
                step = TAOStep(
                    step=turn,
                    thought=worker_turn.thought,
                    tool=action.tool,
                    arguments=action.arguments,
                    observation=observation,
                    ok=result.ok,
                )
                state.steps.append(step)
                trace.event("tool_result", step=step.model_dump())
                self.reporter.tool(result)

                # 4a. Critic judges the intermediate step.
                if cfg.critic_every_step:
                    verdict = await critic.evaluate_step(
                        task=task, step=step, history=state.steps, usage=usage
                    )
                    state.critic_verdicts.append(verdict)
                    trace.event("critic_verdict", scope="step",
                                turn=turn, verdict=verdict.model_dump())
                    self.reporter.critic(verdict, final=False)
                    if verdict.verdict == "fail":
                        state.status = "failed"
                        return
                    if verdict.verdict == "revise":
                        hint = verdict.hint or "; ".join(verdict.issues)
                continue

            # 4b. Critic judges the final answer claim.
            assert worker_turn.final_answer is not None
            self.reporter.worker_final(worker_turn.thought, worker_turn.final_answer)
            state.final_answer = worker_turn.final_answer
            normalized = worker_turn.final_answer.strip()
            if last_final is not None and normalized == last_final:
                state.status = "no_progress"
                trace.event("no_progress", answer=worker_turn.final_answer)
                return
            last_final = normalized

            verdict = await critic.evaluate_final(
                task=task,
                final_answer=worker_turn.final_answer,
                thought=worker_turn.thought,
                history=state.steps,
                usage=usage,
            )
            state.critic_verdicts.append(verdict)
            trace.event("critic_verdict", scope="final", turn=turn,
                        verdict=verdict.model_dump())
            self.reporter.critic(verdict, final=True)

            if verdict.verdict == "approve":
                state.status = "success"
                return
            if verdict.verdict == "fail":
                state.status = "failed"
                return
            state.revisions += 1
            if state.revisions >= cfg.max_revisions:
                state.status = "max_revisions"
                return
            hint = verdict.hint or "; ".join(verdict.issues)

        state.status = "max_turns"

    # ------------------------------------------------------------ reflection
    async def _reflect(
        self, state: _RunState, usage: UsageTracker, trace: TraceLogger
    ) -> tuple[list[str], list[str]]:
        """Analyse the trajectory and store the distilled lessons."""
        reflector = ReflectionAgent(self.llm)
        try:
            outcome = await reflector.reflect(
                task=state.task,
                problem_type=state.problem_type,
                steps=state.steps,
                verdicts=state.critic_verdicts,
                status=state.status,
                final_answer=state.final_answer,
                usage=usage,
            )
        except AgentFormatError as exc:
            trace.event("reflection_failed", error=str(exc))
            self.reporter._emit("system", "reflection skipped: " + str(exc))
            return [], []

        trace.event(
            "reflection",
            summary=outcome.summary,
            drafts=[draft.model_dump() for draft in outcome.lessons],
        )
        self.reporter.reflection(outcome.summary)

        created: list[str] = []
        reinforced: list[str] = []
        for draft in outcome.lessons:
            lesson, is_new = self.store.add(draft, origin_run_id=state.run_id)
            (created if is_new else reinforced).append(lesson.id)
            trace.event(
                "lesson_saved",
                lesson_id=lesson.id,
                is_new=is_new,
                problem_type=lesson.problem_type,
                rule=lesson.rule_to_follow,
            )
            self.reporter.lesson(lesson, is_new)
        return created, reinforced
