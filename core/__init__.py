"""Multi-agent self-improvement harness.

A minimal, framework-free harness that runs a Worker <-> Critic loop with hard
safety limits, reflects on every trajectory, and persists the resulting
lessons so future runs start smarter. See ``README.md`` for the architecture.
"""
from .agents import AgentFormatError, BaseAgent, CriticAgent, ReflectionAgent, WorkerAgent
from .llm import (
    LLMClient,
    LLMResponse,
    OpenAICompatClient,
    ScriptedLLM,
    ScriptedTurn,
    UsageTracker,
    estimate_tokens,
)
from .memory import LessonStore
from .orchestrator import Harness
from .schemas import (
    CriticVerdict,
    Lesson,
    LessonDraft,
    ReflectionOutcome,
    RunConfig,
    RunResult,
    ScoredLesson,
    TAOStep,
    ToolCall,
    ToolResult,
    WorkerTurn,
)
from .tools import Tool, ToolRegistry, default_registry
from .tracing import ConsoleReporter, TraceLogger

__all__ = [
    "AgentFormatError",
    "BaseAgent",
    "CriticAgent",
    "ReflectionAgent",
    "WorkerAgent",
    "LLMClient",
    "LLMResponse",
    "OpenAICompatClient",
    "ScriptedLLM",
    "ScriptedTurn",
    "UsageTracker",
    "estimate_tokens",
    "LessonStore",
    "Harness",
    "CriticVerdict",
    "Lesson",
    "LessonDraft",
    "ReflectionOutcome",
    "RunConfig",
    "RunResult",
    "ScoredLesson",
    "TAOStep",
    "ToolCall",
    "ToolResult",
    "WorkerTurn",
    "Tool",
    "ToolRegistry",
    "default_registry",
    "ConsoleReporter",
    "TraceLogger",
]
