# Multi-Agent Self-Improvement Harness

A modular, framework-free Python harness that combines multi-agent interaction
(Worker <-> Critic) with long-term, in-context self-improvement (Reflection ->
persistent Lesson Store -> context injection on future runs). No LangChain,
CrewAI or other heavy frameworks: plain `asyncio`, Pydantic v2, an
OpenAI-compatible client, and a deterministic offline mode that needs no API
key.

The loop it runs:

1. The **Orchestrator** retrieves the most relevant past lessons for the task.
2. The **Worker** solves the task step by step (Thought - Action - Observation)
   with schema-validated tools and the injected lessons in its context.
3. The **Critic** judges every intermediate step and every final-answer claim;
   unsupported numbers, hallucinations and logic errors are sent back as hints.
4. The **Reflection** agent analyses the finished trajectory and distills
   concrete, generalizable rules (lessons).
5. The **Lesson Store** persists the lessons (with deduplication) and feeds
   them back into step 1 - the harness gets smarter without any fine-tuning.

## Architecture

```
                    +-------------------------------------------+
                    |               ORCHESTRATOR                |
                    |   Harness.run(task, problem_type)         |
                    |   - deterministic turn manager            |
                    |   - max_turns / max_revisions             |
                    |   - token budget / timeout                |
                    |   - loop & no-progress detection          |
                    +------+----------------+-------------------+
                           |                |                |
        1. retrieve        |                | 2. inject      | 5. after the run
        top-k lessons      |                | lessons        |    reflect on the
                           v                v                |    full trajectory
                  +----------------+   +-----------+   +---------------+
                  |  LESSON STORE  |   |  WORKER   |   |  REFLECTION   |
                  |  data/*.jsonl  |   |  AGENT    |   |  AGENT        |
                  |  - idf-weight  |   +-----+-----+   |  - summary    |
                  |    retrieval   |         |         |  - lesson     |
                  |  - trigram     |         | 3. tool |    drafts     |
                  |    dedup       |         | calls   +-------+-------+
                  |  - used/helped |         | (schema-        |6. add()
                  |    effectiveness|        |  validated)     |  (dedup/merge)
                  +-------+--------+         |                 |
                     ^   |                  v                 |
                     |   +-----------+ +----------+           |
                     |               | | TOOL     |           |
                     |               | | REGISTRY |           |
                     |               | | mock +   |           |
                     |               | | real fns |           |
                     |               | +----+-----+           |
                     |               |      | observations    |
                     |               |      v                 |
                     |               | +------------+         |
                     +---------------|-|  CRITIC    |         |
                      6. lessons     | |  AGENT     |---------+
                      survive runs   | | step+final |-- 4. revise hints
                                     | +------------+    back to WORKER
                                     +-----------------> next run starts
                                       smarter (lessons re-injected)
```

Numbered dataflow: (1) retrieval, (2) context injection, (3) validated tool
calls, (4) critic verdicts/hints, (5) post-run reflection, (6) lessons stored
and re-used.

## Project layout

```
multi_agent_harness/
├── core/
│   ├── __init__.py        # public API re-exports
│   ├── schemas.py         # Pydantic models: Lesson, WorkerTurn, CriticVerdict...
│   ├── llm.py             # LLMClient + OpenAICompatClient + ScriptedLLM (offline)
│   ├── tools.py           # ToolRegistry: mock tools + real functions + validation
│   ├── memory.py          # LessonStore: JSONL persistence, retrieval, dedup
│   ├── agents.py          # WorkerAgent / CriticAgent / ReflectionAgent
│   ├── tracing.py         # TraceLogger (JSONL) + ConsoleReporter (rich/ANSI)
│   └── orchestrator.py    # Harness: turn manager + safety limits + reflection
├── examples/
│   └── demo_two_runs.py   # End-to-end demo: mistake -> lesson -> clean rerun
├── tests/
│   └── test_core.py       # offline smoke tests (no API key needed)
├── data/                  # persistent lesson stores (*.jsonl, gitignored)
├── logs/                  # full run trajectories (*.jsonl, gitignored)
├── requirements.txt
└── README.md
```

## Quickstart

```bash
cd multi_agent_harness
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Offline, deterministic (default; no API key required):
python examples/demo_two_runs.py

# Against a live OpenAI-compatible model:
export OPENAI_API_KEY=sk-...
export HARNESS_MODEL=gpt-4o-mini                  # optional
export OPENAI_BASE_URL=https://api.openai.com/v1  # optional (gateways, vLLM...)
python examples/demo_two_runs.py
```

Run the offline test suite:

```bash
python tests/test_core.py    # or: pytest tests/
```

## What the demo shows

```
RUN 1 (fresh store):
  WORKER   mental math -> "FINAL ANSWER: 556"      (wrong)
  CRITIC   REVISE: answer not backed by any tool observation...
  WORKER   calculator("17 * 23") -> 391 ; calculator("459 / 3") -> 153
  WORKER   "FINAL ANSWER: 544"                       (correct)
  CRITIC   APPROVE
  REFLECT  saves lesson: "Never evaluate arithmetic mentally. Call the
           calculator tool for every subexpression..."
  => status=success, revisions=1

RUN 2 (same problem type, new numbers):
  LESSON   retrieved 1 lesson(s) into the worker context
  WORKER   calculator("12 * 47") -> 564 ; calculator("816 / 4") -> 204
  WORKER   "FINAL ANSWER: 768"
  CRITIC   APPROVE (first pass)
  REFLECT  re-proposes the same rule -> store deduplicates (reinforced, not duplicated)
  => status=success, revisions=0
```

Every run writes a full audit trail (prompts metadata, worker turns, tool
results, critic verdicts, reflections, lessons) to `logs/run_*.jsonl`, and the
console shows the live colour-coded dialogue (`rich` when installed, plain
ANSI otherwise).

## How the run loop works

`Harness.run(task, problem_type)` executes, under `asyncio` with a hard
timeout:

1. `LessonStore.retrieve(problem_type + task, top_k)` scores lessons by
   idf-weighted keyword coverage (x1.5 for an exact `problem_type` match, mild
   boosts for reinforcement count and observed helped/used ratio).
2. Turn loop (max `max_turns`):
   - Worker replies with exactly one JSON object: a tool `action` or a
     `final_answer` (Pydantic-validated; one repair round-trip on bad JSON,
     then `invalid_output`).
   - Tool calls go through `ToolRegistry.dispatch()`: argument-schema
     validation, safe execution, structured errors as observations. The same
     tool called `repeat_call_abort` times in a row aborts (`loop_detected`).
   - Critic judges every executed step and every final claim:
     `approve` ends the run, `revise` sends a hint back (bounded by
     `max_revisions`), `fail` aborts. A repeated identical final answer aborts
     (`no_progress`).
3. The Reflection agent converts the trajectory into lesson drafts; the store
   merges near-duplicates (character-trigram Jaccard >= 0.45 within the same
   problem type, 0.65 across types) instead of accumulating copies.
4. On success, all injected lessons get their `times_helped` bumped - lessons
   that demonstrably work are ranked higher by retrieval.

All limits live in `RunConfig` (`core/schemas.py`).

## Adding new tools

Mock tools and real Python functions share one registry:

```python
from core.tools import ToolRegistry

registry = default_registry()

# 1. A real function - the argument schema is derived from type hints:
def word_count(text: str) -> int:
    """Count words in a text."""
    return len(text.split())

registry.register_function(word_count, description="Count words in a text.")

# 2. Decorator flavour:
@registry.tool(description="Convert km to miles.")
def km_to_miles(km: float) -> float:
    return km * 0.621371

# 3. Full control (custom Pydantic model, async handlers also work):
registry.register(name="fetch", description="...", args_model=FetchArgs,
                  handler=fetch_handler, is_mock=False)
```

Bad arguments never crash the run - they come back as `ERROR: ...`
observations the Worker can react to.

## Adding new roles

1. Subclass `BaseAgent` in `core/agents.py`, set `role` (this tag is what
   `ScriptedLLM` checks), and add a method that returns a Pydantic model via
   `self._complete_json(...)`.
2. Define the new output model in `core/schemas.py`.
3. Call it from `Harness._solve()` (before/after the Worker, on critic
   verdicts, ...) or from `_reflect()`.
4. If the role changes turn economics, adjust `RunConfig` and, if needed, the
   token-budget check.

Example - a Planner that runs once before the Worker:

```python
class PlannerAgent(BaseAgent):
    role = "planner"

    async def plan(self, *, task: str, lessons: list[Lesson],
                   usage: UsageTracker) -> Plan:
        return await self._complete_json(
            system=PLANNER_SYSTEM + format_lessons(lessons),
            user="TASK:\n" + task,
            schema=Plan,
            usage=usage,
        )
```

## Scaling notes

- **Semantic retrieval**: `LessonStore.retrieve()` is intentionally small.
  Replace its scoring with embeddings (OpenAI embeddings, sentence-transformers)
  and keep the same signature; nothing else changes. The JSONL store can be
  swapped for SQLite/pgvector behind the same `add/retrieve` interface.
- **Native tool calling**: agents use a strict JSON protocol instead of
  provider-specific function calling, so one code path serves any
  OpenAI-compatible endpoint *and* the offline scripted client. If you are
  OpenAI-only, `OpenAICompatClient` can be extended to pass native tool
  schemas.
- **Cost control**: set `critic_every_step=False` in `RunConfig` to have the
  critic judge only final answers.
- **Parallelism**: `Harness` is ordinary asyncio - run independent tasks with
  `asyncio.gather(*(harness.run(t) for t in tasks))`; each run gets its own
  trace file. Give concurrent runs separate `logs_dir`s or share one safely
  (appends are line-atomic).
- **Dedup tuning**: `LessonStore(dedup_threshold=...)` - lower merges more
  aggressively; with embeddings, switch to cosine similarity on lesson
  vectors.

## Design decisions

- **No agent frameworks** - the whole point is a readable, auditable loop you
  can lift into your own system (~1k lines total).
- **Deterministic offline mode** - `ScriptedLLM` pins each scripted reply to a
  role, so demos and CI verify the *orchestration* (retrieval, injection,
  safety limits, dedup) without an API key and without flakiness.
- **Observability first** - every run leaves a complete `.jsonl` trajectory;
  the pretty console is a view, not the record.
- **Safety limits are hard stops**, not suggestions: budget, timeout, turns,
  revision loops, repeated calls and repeated answers all terminate the run
  with an explicit status recorded in the trace.

## References

- Reflexion: Language Agents with Verbal Reinforcement Learning -
  https://arxiv.org/abs/2303.11366 (and https://github.com/noahshinn/reflexion)
- Memento: case-based reasoning without fine-tuning -
  https://github.com/Agent-on-the-Fly/Memento

## Repository conventions

Code, identifiers, documentation and commit messages are kept in English.
