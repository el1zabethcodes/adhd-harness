"""End-to-end demo: two runs of the self-improvement loop.

Run 1 (fresh lesson store): the Worker tries mental arithmetic and produces a
wrong final answer. The Critic catches the unsupported claim and sends it
back; the Worker re-does the computation with the calculator tool and
succeeds. The Reflection agent distills a durable rule, which the LessonStore
persists.

Run 2 (same problem type, new numbers): the harness automatically retrieves
the stored lesson and injects it into the Worker context. The Worker uses the
calculator from the very first turn and the Critic approves the final answer
with zero revisions. The reflection re-proposes the same rule, which the
store's deduplication merges into the existing lesson.

By default this runs fully offline and deterministically (ScriptedLLM), so no
API key is needed. To run the same loop against a live OpenAI-compatible
model:

    export OPENAI_API_KEY=sk-...
    export HARNESS_MODEL=gpt-4o-mini          # optional
    export OPENAI_BASE_URL=https://api.openai.com/v1  # optional (gateways)

Usage:
    python examples/demo_two_runs.py
    python -m examples.demo_two_runs
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.llm import LLMClient, OpenAICompatClient, ScriptedLLM, ScriptedTurn
from core.memory import LessonStore
from core.orchestrator import Harness
from core.schemas import RunConfig
from core.tools import default_registry

PROBLEM_TYPE = "arithmetic_word_problem"
TASK_1 = "Compute 17 * 23 + 459 / 3"   # correct answer: 544
TASK_2 = "Compute 12 * 47 + 816 / 4"   # correct answer: 768


def build_script() -> list[ScriptedTurn]:
    """Deterministic dialogue for the offline mode (worker/critic/reflector)."""
    return [
        # ---------------- RUN 1: mistake, caught, fixed, reflected ----------
        ScriptedTurn(
            "worker",
            {
                "thought": "Simple arithmetic, I can do this in my head: "
                "17*23 is 401, 459/3 is 155, so the total is 556.",
                "final_answer": "556",
            },
        ),
        ScriptedTurn(
            "critic",
            {
                "verdict": "revise",
                "issues": [
                    "The answer 556 is not backed by any tool observation; "
                    "mental arithmetic is error-prone (17*23 is actually 391)."
                ],
                "hint": "Call the calculator tool for each subexpression, "
                "then combine the verified results.",
                "confidence": 0.95,
            },
        ),
        ScriptedTurn(
            "worker",
            {
                "thought": "I will verify each subexpression with the calculator.",
                "action": {"tool": "calculator", "arguments": {"expression": "17 * 23"}},
            },
        ),
        ScriptedTurn("critic", {"verdict": "approve", "issues": [], "confidence": 0.9}),
        ScriptedTurn(
            "worker",
            {
                "thought": "Now the division.",
                "action": {"tool": "calculator", "arguments": {"expression": "459 / 3"}},
            },
        ),
        ScriptedTurn("critic", {"verdict": "approve", "issues": [], "confidence": 0.9}),
        ScriptedTurn(
            "worker",
            {
                "thought": "Combining the verified results: 391 + 153 = 544.",
                "final_answer": "544",
            },
        ),
        ScriptedTurn("critic", {"verdict": "approve", "issues": [], "confidence": 0.98}),
        ScriptedTurn(
            "reflector",
            {
                "summary": "The worker attempted mental arithmetic and produced "
                "a wrong answer (556 vs the correct 544). After critic feedback "
                "it switched to the calculator tool and succeeded. Durable "
                "rule: never evaluate arithmetic mentally.",
                "lessons": [
                    {
                        "problem_type": PROBLEM_TYPE,
                        "failure_mode": "mental_math_error",
                        "rule_to_follow": "Never evaluate arithmetic mentally. "
                        "Call the calculator tool for every subexpression, "
                        "then combine the verified results.",
                        "tags": ["arithmetic", "calculator", "verification"],
                    }
                ],
            },
        ),
        # ------------- RUN 2: lesson retrieved, clean first pass -------------
        ScriptedTurn(
            "worker",
            {
                "thought": "Applying the stored lesson: compute each "
                "subexpression with the calculator before combining.",
                "action": {"tool": "calculator", "arguments": {"expression": "12 * 47"}},
            },
        ),
        ScriptedTurn("critic", {"verdict": "approve", "issues": [], "confidence": 0.95}),
        ScriptedTurn(
            "worker",
            {
                "thought": "Division next.",
                "action": {"tool": "calculator", "arguments": {"expression": "816 / 4"}},
            },
        ),
        ScriptedTurn("critic", {"verdict": "approve", "issues": [], "confidence": 0.95}),
        ScriptedTurn(
            "worker",
            {
                "thought": "Combining the verified results: 564 + 204 = 768.",
                "final_answer": "768",
            },
        ),
        ScriptedTurn("critic", {"verdict": "approve", "issues": [], "confidence": 0.99}),
        ScriptedTurn(
            "reflector",
            {
                "summary": "Clean run: the injected lesson was followed and the "
                "task was solved on the first pass with zero revisions. "
                "Proposing the same rule again so the store can reinforce it.",
                "lessons": [
                    {
                        "problem_type": PROBLEM_TYPE,
                        "failure_mode": "mental_math_error",
                        "rule_to_follow": "Never evaluate arithmetic mentally. "
                        "Call the calculator tool for every subexpression, "
                        "then combine the verified tool results.",
                        "tags": ["arithmetic", "calculator"],
                    }
                ],
            },
        ),
    ]


def _print_header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


async def main() -> None:
    store_path = ROOT / "data" / "demo_lessons.jsonl"
    store_path.parent.mkdir(parents=True, exist_ok=True)
    if store_path.exists():
        store_path.unlink()  # deterministic replay of the learning story
    store = LessonStore(store_path)

    if os.environ.get("OPENAI_API_KEY"):
        llm: LLMClient = OpenAICompatClient()
        mode = "live model '" + llm.model + "' via OpenAI-compatible API"
    else:
        llm = ScriptedLLM(build_script())
        mode = "offline scripted mode (deterministic, no API key needed)"

    harness = Harness(
        llm,
        store,
        default_registry(),
        RunConfig(max_turns=10, max_revisions=3),
        logs_dir=ROOT / "logs",
    )

    _print_header("Multi-agent self-improvement harness | " + mode)

    _print_header("RUN 1: fresh store - the worker is expected to make a mistake")
    run1 = await harness.run(TASK_1, problem_type=PROBLEM_TYPE)

    _print_header("RUN 2: same problem type - the stored lesson is retrieved and injected")
    run2 = await harness.run(TASK_2, problem_type=PROBLEM_TYPE)

    _print_header("Summary")
    for name, result in (("run 1", run1), ("run 2", run2)):
        tokens = result.prompt_tokens + result.completion_tokens
        print(
            f"  {name}: status={result.status} | revisions={result.revisions} | "
            f"tool_steps={len(result.steps)} | answer={result.final_answer!r} | "
            f"tokens={tokens}"
        )
    print(f"  lesson store: {store_path} | {store.stats()}")
    for lesson in store.all_lessons():
        print(f"    - [{lesson.problem_type}] {lesson.rule_to_follow}")
        print(
            f"      used={lesson.times_used} helped={lesson.times_helped} "
            f"reinforced={lesson.times_reinforced}"
        )
    print(f"  traces: {ROOT / 'logs' / (run1.run_id + '.jsonl')}")
    print(f"          {ROOT / 'logs' / (run2.run_id + '.jsonl')}")


if __name__ == "__main__":
    asyncio.run(main())
