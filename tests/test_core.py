"""Offline smoke tests for the harness core. No API keys required.

Run with either:
    python tests/test_core.py
    pytest tests/
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.llm import ScriptedLLM
from core.memory import LessonStore
from core.orchestrator import Harness
from core.schemas import LessonDraft, RunConfig
from core.tools import default_registry
from core.tracing import ConsoleReporter


def test_calculator_tool() -> None:
    registry = default_registry()
    result = asyncio.run(registry.dispatch("calculator", {"expression": "2 + 2 * 3"}))
    assert result.ok and result.output == "8", result
    result = asyncio.run(registry.dispatch("calculator", {"expression": "459 / 3"}))
    assert result.ok and result.output == "153", result
    result = asyncio.run(registry.dispatch("calculator", {"expression": "15 / 2"}))
    assert result.ok and result.output == "7.5", result


def test_calculator_rejects_unsafe_expressions() -> None:
    registry = default_registry()
    result = asyncio.run(
        registry.dispatch("calculator", {"expression": "__import__('os').system('echo pwned')"})
    )
    assert not result.ok and "unsupported" in (result.error or ""), result
    result = asyncio.run(registry.dispatch("calculator", {"expression": "2 ** 99999999"}))
    assert not result.ok and "exponent" in (result.error or ""), result


def test_tool_schema_validation() -> None:
    registry = default_registry()
    result = asyncio.run(registry.dispatch("calculator", {"expression": 123}))
    assert not result.ok and "invalid arguments" in (result.error or ""), result
    result = asyncio.run(registry.dispatch("no_such_tool", {}))
    assert not result.ok and "unknown tool" in (result.error or ""), result


def test_register_real_python_function() -> None:
    registry = default_registry()

    def slugify(text: str, max_length: int = 20) -> str:
        """Turn text into a URL slug."""
        return "".join(ch if ch.isalnum() else "-" for ch in text.lower())[:max_length]

    registry.register_function(slugify, description="Turn text into a URL slug.")
    result = asyncio.run(registry.dispatch("slugify", {"text": "Hello World!"}))
    assert result.ok and result.output == "hello-world-", result
    bad = asyncio.run(registry.dispatch("slugify", {"text": 42}))
    assert not bad.ok, bad


def test_lesson_store_dedup() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = LessonStore(Path(tmp) / "lessons.jsonl")
        base = LessonDraft(
            problem_type="arithmetic_word_problem",
            failure_mode="mental_math_error",
            rule_to_follow="Never evaluate arithmetic mentally. Call the "
            "calculator tool for every subexpression.",
        )
        lesson, created = store.add(base)
        assert created

        reworded = LessonDraft(
            problem_type="arithmetic_word_problem",
            failure_mode="mental_math_error",
            rule_to_follow="Never evaluate arithmetic mentally. Call the "
            "calculator tool for every subexpression before combining.",
        )
        merged, created_again = store.add(reworded)
        assert not created_again
        assert merged.id == lesson.id
        assert merged.times_reinforced == 1
        assert len(store.all_lessons()) == 1

        different = LessonDraft(
            problem_type="arithmetic_word_problem",
            failure_mode="unit_confusion",
            rule_to_follow="Always convert units to SI before computing anything.",
        )
        _, created_other = store.add(different)
        assert created_other
        assert len(store.all_lessons()) == 2


def test_lesson_store_retrieval() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = LessonStore(Path(tmp) / "lessons.jsonl")
        store.add(
            LessonDraft(
                problem_type="arithmetic_word_problem",
                failure_mode="mental_math_error",
                rule_to_follow="Never evaluate arithmetic mentally, always call "
                "the calculator tool for each subexpression.",
                tags=["arithmetic"],
            )
        )
        store.add(
            LessonDraft(
                problem_type="text_summary",
                failure_mode="hallucinated_details",
                rule_to_follow="Only state facts that appear verbatim in the "
                "source text.",
                tags=["grounding"],
            )
        )
        hits = store.retrieve(
            "arithmetic_word_problem compute 81 * 13",
            problem_type="arithmetic_word_problem",
        )
        assert hits and hits[0].lesson.problem_type == "arithmetic_word_problem"

        hits = store.retrieve("grounding summary of the article", problem_type="text_summary")
        assert hits and hits[0].lesson.problem_type == "text_summary"


def test_end_to_end_two_runs() -> None:
    from examples.demo_two_runs import PROBLEM_TYPE, TASK_1, TASK_2, build_script

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        store = LessonStore(tmp_path / "lessons.jsonl")
        harness = Harness(
            ScriptedLLM(build_script()),
            store,
            default_registry(),
            RunConfig(max_turns=10),
            logs_dir=tmp_path / "logs",
            reporter=ConsoleReporter(quiet=True),
        )
        run1 = asyncio.run(harness.run(TASK_1, problem_type=PROBLEM_TYPE))
        assert run1.status == "success", run1.status
        assert run1.final_answer == "544"
        assert run1.revisions == 1
        assert len(run1.lessons_created) == 1

        run2 = asyncio.run(harness.run(TASK_2, problem_type=PROBLEM_TYPE))
        assert run2.status == "success", run2.status
        assert run2.final_answer == "768"
        assert run2.revisions == 0
        assert run2.lessons_injected, "lesson was not retrieved for run 2"
        assert run2.lessons_reinforced and not run2.lessons_created, "dedup failed"

        lesson = store.all_lessons()[0]
        assert lesson.times_used == 1
        assert lesson.times_helped == 1
        assert lesson.times_reinforced == 1


def main() -> None:
    tests = [
        fn
        for name, fn in sorted(globals().items())
        if name.startswith("test_") and callable(fn)
    ]
    failures = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {fn.__name__}: {exc!r}")
    print(f"\n{len(tests) - failures}/{len(tests)} tests passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
