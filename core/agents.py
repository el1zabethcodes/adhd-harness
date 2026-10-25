"""The three agents: Worker (executor), Critic (evaluator), Reflection (analyst).

All agents share one strict contract: the model must reply with a single JSON
object, which is parsed and validated against a Pydantic schema. One repair
round-trip is attempted before giving up (``AgentFormatError``). This keeps a
single unified protocol for live OpenAI-compatible models and the offline
scripted client alike.
"""
from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel

from .llm import LLMClient, UsageTracker
from .schemas import (
    CriticVerdict,
    Lesson,
    ReflectionOutcome,
    TAOStep,
    WorkerTurn,
)

TModel = TypeVar("TModel", bound=BaseModel)

REPAIR_INSTRUCTION = (
    "Your previous reply was not a single valid JSON object matching the "
    "required schema. Reply again with ONLY the JSON object: no prose, no "
    "markdown fences."
)


class AgentFormatError(Exception):
    """The model failed to produce schema-valid JSON even after a repair turn."""


def extract_json(text: str) -> dict:
    """Extract the first balanced JSON object from an LLM reply."""
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip())
    start = cleaned.find("{")
    if start == -1:
        raise ValueError("no JSON object found in reply")
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(cleaned[start : i + 1])
    raise ValueError("unbalanced JSON object in reply")


def format_lessons(lessons: list[Lesson]) -> str:
    """Render injected lessons as prompt lines for the Worker."""
    if not lessons:
        return "No lessons stored yet - you are the first agent to try this kind of task."
    lines: list[str] = []
    for i, lesson in enumerate(lessons, 1):
        lines.append(f"{i}. [{lesson.problem_type}] RULE: {lesson.rule_to_follow}")
        lines.append(
            f"   past failure mode: {lesson.failure_mode}; "
            f"confirmed in {lesson.times_reinforced + 1} run(s)"
        )
    return "\n".join(lines)


def format_history(history: list[TAOStep]) -> str:
    """Render the Thought-Action-Observation transcript."""
    if not history:
        return "(no steps taken yet)"
    lines: list[str] = []
    for step in history:
        lines.append(f"step {step.step} thought: {step.thought}")
        if step.tool:
            args = json.dumps(step.arguments or {}, sort_keys=True)
            lines.append(f"step {step.step} action: {step.tool}({args})")
        if step.observation is not None:
            lines.append(f"step {step.step} observation: {step.observation}")
    return "\n".join(lines)


class BaseAgent:
    """Shared machinery: one LLM, one role tag, strict-JSON completion."""

    role: str = "base"

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def _complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: type[TModel],
        usage: UsageTracker,
    ) -> TModel:
        messages = [{"role": "user", "content": user}]
        response = await self.llm.complete(
            agent_role=self.role, system=system, messages=messages
        )
        usage.add(response.prompt_tokens, response.completion_tokens)
        try:
            return schema.model_validate(extract_json(response.text))
        except Exception as first_error:
            repair = await self.llm.complete(
                agent_role=self.role,
                system=system,
                messages=[
                    *messages,
                    {"role": "assistant", "content": response.text},
                    {"role": "user", "content": REPAIR_INSTRUCTION},
                ],
            )
            usage.add(repair.prompt_tokens, repair.completion_tokens)
            try:
                return schema.model_validate(extract_json(repair.text))
            except Exception as second_error:
                raise AgentFormatError(
                    f"{self.role}: invalid JSON output "
                    f"(first: {first_error}; retry: {second_error})"
                ) from second_error


class WorkerAgent(BaseAgent):
    """Executor: thinks, calls tools, and eventually claims a final answer."""

    role = "worker"

    async def act(
        self,
        *,
        task: str,
        tools: str,
        lessons: list[Lesson],
        history: list[TAOStep],
        critic_hint: str | None,
        usage: UsageTracker,
    ) -> WorkerTurn:
        system = (
            "You are the Worker agent in a self-improving multi-agent harness.\n"
            "Solve the task step by step. Prefer tools over guessing: every\n"
            "factual or numeric claim should come from a tool observation,\n"
            "not from memory.\n\n"
            "OUTPUT PROTOCOL (strict): reply with exactly one JSON object, "
            "nothing else.\n"
            'To call a tool:  {"thought": "...", "action": {"tool": "<name>", '
            '"arguments": {...}}}\n'
            'To finish:       {"thought": "...", "final_answer": '
            '"<complete answer>"}\n'
            "The tool result arrives as an observation on your next turn.\n"
            "Use final_answer only when the task is fully solved and every\n"
            "claim is verified.\n\n"
            "AVAILABLE TOOLS:\n" + tools + "\n\n"
            "LESSONS FROM PAST RUNS (learned the hard way - follow them):\n"
            + format_lessons(lessons)
        )
        user = "TASK:\n" + task + "\n\nTRANSCRIPT SO FAR:\n" + format_history(history)
        if critic_hint:
            user += "\n\nCRITIC FEEDBACK (address this now):\n" + critic_hint
        user += "\n\nReply with one JSON object: an action or a final_answer."
        return await self._complete_json(
            system=system, user=user, schema=WorkerTurn, usage=usage
        )


class CriticAgent(BaseAgent):
    """Evaluator: judges intermediate steps and final answers for evidence."""

    role = "critic"

    SYSTEM = (
        "You are the Critic agent: a strict, evidence-driven reviewer inside a\n"
        "multi-agent harness. Judge the Worker's output against the task, the\n"
        "transcript and the tool observations.\n\n"
        "Check for:\n"
        "- claims or numbers not backed by a tool observation (mental math,\n"
        "  hallucinated facts)\n"
        "- contradictions, logic errors, unanswered parts of the task\n"
        "- final answers that ignore previous critic feedback or lessons\n\n"
        "Verdicts:\n"
        '- "approve": the step is sound / the final answer is correct and\n'
        "  supported by observations\n"
        '- "revise": fixable problems; always give a concrete hint describing\n'
        "  the next action\n"
        '- "fail": hopeless or unsafe; explain why\n\n'
        "Reply with a single JSON object, nothing else:\n"
        '{"verdict": "approve" | "revise" | "fail", "issues": ["..."], '
        '"hint": "..." or null, "confidence": 0.0}'
    )

    async def evaluate_step(
        self,
        *,
        task: str,
        step: TAOStep,
        history: list[TAOStep],
        usage: UsageTracker,
    ) -> CriticVerdict:
        args = json.dumps(step.arguments or {}, sort_keys=True)
        user = (
            "TASK:\n" + task + "\n\n"
            "FULL TRANSCRIPT:\n" + format_history(history) + "\n\n"
            "WORKER'S LATEST STEP (already executed):\n"
            "thought: " + step.thought + "\n"
            "action: " + str(step.tool) + "(" + args + ")\n"
            "observation: " + str(step.observation) + "\n\n"
            "Judge this step. Reply with the verdict JSON."
        )
        return await self._complete_json(
            system=self.SYSTEM, user=user, schema=CriticVerdict, usage=usage
        )

    async def evaluate_final(
        self,
        *,
        task: str,
        final_answer: str,
        thought: str,
        history: list[TAOStep],
        usage: UsageTracker,
    ) -> CriticVerdict:
        user = (
            "TASK:\n" + task + "\n\n"
            "FULL TRANSCRIPT:\n" + format_history(history) + "\n\n"
            'WORKER FINAL ANSWER CLAIM: "' + final_answer + '"\n'
            "worker's closing thought: " + thought + "\n\n"
            "Judge whether the final answer is correct, complete and supported\n"
            "by the observations above. Reply with the verdict JSON."
        )
        return await self._complete_json(
            system=self.SYSTEM, user=user, schema=CriticVerdict, usage=usage
        )


class ReflectionAgent(BaseAgent):
    """Analyst: turns a finished trajectory into durable lesson drafts."""

    role = "reflector"

    SYSTEM = (
        "You are the Reflection agent of a self-improving harness.\n"
        "After a run finishes you analyse the full trajectory (thoughts, tool\n"
        "calls, observations, critic verdicts) and distill durable lessons for\n"
        "future runs.\n\n"
        "A good lesson:\n"
        "- is concrete and actionable (which tool to call, which check to run,\n"
        "  in what order)\n"
        "- names the failure mode in general terms, without the specific\n"
        "  numbers of this task\n"
        "- would have prevented the failure if injected before the run\n"
        "A clean, successful run produces no new lessons (or only confirms\n"
        "existing rules). Never write generic advice like 'be careful'.\n\n"
        "Reply with a single JSON object, nothing else (max 3 lessons):\n"
        '{"summary": "<short analysis of what happened and why>", '
        '"lessons": [{"problem_type": "...", "failure_mode": "...", '
        '"rule_to_follow": "...", "tags": ["..."]}]}'
    )

    async def reflect(
        self,
        *,
        task: str,
        problem_type: str,
        steps: list[TAOStep],
        verdicts: list[CriticVerdict],
        status: str,
        final_answer: str | None,
        usage: UsageTracker,
    ) -> ReflectionOutcome:
        if verdicts:
            verdict_lines = "\n".join(
                f"{i}. {v.verdict}"
                + (": " + "; ".join(v.issues) if v.issues else "")
                + ((" | hint: " + v.hint) if v.hint else "")
                for i, v in enumerate(verdicts, 1)
            )
        else:
            verdict_lines = "(none)"
        user = (
            "TASK:\n" + task + "\n"
            "problem_type: " + problem_type + "\n"
            "run status: " + status + "\n"
            "final answer: " + (final_answer or "(none)") + "\n\n"
            "TRAJECTORY:\n" + format_history(steps) + "\n\n"
            "CRITIC VERDICTS:\n" + verdict_lines + "\n\n"
            "Analyse the run and reply with the lessons JSON."
        )
        return await self._complete_json(
            system=self.SYSTEM, user=user, schema=ReflectionOutcome, usage=usage
        )
