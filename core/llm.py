"""LLM client layer.

- ``LLMClient``: minimal async interface used by every agent.
- ``OpenAICompatClient``: any OpenAI-compatible chat endpoint (OpenAI, vLLM,
  Ollama, corporate gateways). Configured via ``OPENAI_API_KEY``,
  ``HARNESS_MODEL`` and ``OPENAI_BASE_URL`` environment variables.
- ``ScriptedLLM``: deterministic offline client that replays a scripted
  dialogue. Used by the demo and tests so the full loop can be verified
  end to end without any API key.

Agents speak a strict JSON protocol (parsed and validated with Pydantic on the
agent side), which keeps one unified code path for live and scripted models.
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from typing import Any


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token) when usage stats are absent."""
    return max(1, (len(text) + 3) // 4)


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int


class UsageTracker:
    """Accumulates token usage across all agents of a single run."""

    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def add(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMClient(ABC):
    @abstractmethod
    async def complete(
        self,
        *,
        agent_role: str,
        system: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
    ) -> LLMResponse:
        """Return the assistant reply for a system prompt + chat messages."""


class OpenAICompatClient(LLMClient):
    """Async client for any OpenAI-compatible chat completions endpoint."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.2,
    ) -> None:
        self.model = model or os.environ.get("HARNESS_MODEL", "gpt-4o-mini")
        self.temperature = temperature
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "The `openai` package is required for live models: "
                "pip install openai"
            ) from exc
        self._client = AsyncOpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url or os.environ.get("OPENAI_BASE_URL") or None,
        )

    async def complete(
        self,
        *,
        agent_role: str,
        system: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
    ) -> LLMResponse:
        response = await self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature if temperature is None else temperature,
            messages=[{"role": "system", "content": system}, *messages],
        )
        text = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=text,
            prompt_tokens=(
                usage.prompt_tokens if usage else estimate_tokens(system + json.dumps(messages))
            ),
            completion_tokens=(
                usage.completion_tokens if usage else estimate_tokens(text)
            ),
        )


@dataclass
class ScriptedTurn:
    """One pre-written reply, pinned to a specific agent role."""

    role: str  # "worker" | "critic" | "reflector"
    payload: dict[str, Any] | str


class ScriptedLLM(LLMClient):
    """Deterministic client for offline demos and tests.

    Pops scripted turns in order and verifies the harness asks for the expected
    role, which turns a stale script into an immediate, loud error instead of
    silently desynchronised behaviour.
    """

    def __init__(self, turns: list[ScriptedTurn]) -> None:
        self._turns: deque[ScriptedTurn] = deque(turns)
        self.consumed = 0

    async def complete(
        self,
        *,
        agent_role: str,
        system: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
    ) -> LLMResponse:
        if not self._turns:
            raise RuntimeError(
                f"script exhausted, but the harness asked the {agent_role!r} "
                "agent for another reply"
            )
        turn = self._turns.popleft()
        self.consumed += 1
        if turn.role != agent_role:
            raise RuntimeError(
                f"script desync: next scripted turn is {turn.role!r}, but the "
                f"harness asked for {agent_role!r}"
            )
        text = turn.payload if isinstance(turn.payload, str) else json.dumps(turn.payload)
        return LLMResponse(
            text=text,
            prompt_tokens=estimate_tokens(system + json.dumps(messages)),
            completion_tokens=estimate_tokens(text),
        )
