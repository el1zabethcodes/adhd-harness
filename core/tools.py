"""Tool & action execution layer.

A single registry holds mock tools (safe, offline) and real Python functions.
Every call is validated against a Pydantic argument schema before the handler
runs, and handler exceptions are converted into structured errors so agents
can observe and recover from them instead of crashing the run.
"""
from __future__ import annotations

import ast
import inspect
import json
import operator
import re
from dataclasses import dataclass
from typing import Any, Callable, get_type_hints

from pydantic import BaseModel, Field, ValidationError, create_model

from .schemas import ToolResult


# --------------------------------------------------------------------------- #
# Safe mock tools
# --------------------------------------------------------------------------- #
class CalculatorArgs(BaseModel):
    expression: str = Field(description="Arithmetic expression, e.g. '17 * 23 + 4'")


class KnowledgeSearchArgs(BaseModel):
    query: str = Field(description="Factual question or keyword query")


_BINARY_OPS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS: dict[type, Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_MAX_EXPONENT = 4096  # guard against 2**10**10 style resource blow-ups


def _eval_node(node: ast.AST) -> int | float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_EXPONENT:
            raise ValueError(f"exponent too large (max {_MAX_EXPONENT})")
        return _BINARY_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError(
        "unsupported expression element (only numbers, + - * / // % ** "
        "and parentheses are allowed)"
    )


def calculator(expression: str) -> str:
    """Evaluate an arithmetic expression via a whitelisted AST walker (no eval)."""
    value = _eval_node(ast.parse(expression, mode="eval"))
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


_KB: dict[str, str] = {
    "earth": "The Earth orbits the Sun in about 365.25 days.",
    "light": "The speed of light in vacuum is 299792458 m/s.",
    "water": "Water boils at 100 degrees Celsius at standard atmospheric pressure.",
    "hour": "One hour has 3600 seconds.",
    "python": "CPython's asyncio event loop schedules coroutines on a single thread.",
    "reflexion": "Reflexion (arXiv:2303.11366) augments LLM agents with verbal "
    "self-reflection stored in episodic memory.",
}


def knowledge_search(query: str) -> str:
    """Look up a keyword query in a tiny offline knowledge base."""
    tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    hits = [fact for key, fact in _KB.items() if key in tokens]
    return "\n".join(hits) if hits else "No matching knowledge found."


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
@dataclass
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[..., Any]
    is_mock: bool = True


def _model_from_signature(fn: Callable[..., Any]) -> type[BaseModel]:
    """Derive a Pydantic argument model from a plain function's type hints."""
    hints = get_type_hints(fn)
    fields: dict[str, Any] = {}
    for name, param in inspect.signature(fn).parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        annotation = hints.get(name, str)
        if param.default is inspect.Parameter.empty:
            fields[name] = (annotation, ...)
        else:
            fields[name] = (annotation, param.default)
    return create_model(f"{fn.__name__.title()}Args", **fields)


class ToolRegistry:
    """Unified registry: mock tools + real Python functions, schema-validated."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    # -- registration -------------------------------------------------------
    def register(
        self,
        *,
        name: str,
        description: str,
        args_model: type[BaseModel],
        handler: Callable[..., Any],
        is_mock: bool = True,
    ) -> None:
        if name in self._tools:
            raise ValueError(f"tool {name!r} is already registered")
        self._tools[name] = Tool(
            name=name,
            description=description,
            args_model=args_model,
            handler=handler,
            is_mock=is_mock,
        )

    def register_function(
        self,
        fn: Callable[..., Any],
        *,
        name: str | None = None,
        description: str | None = None,
        is_mock: bool = False,
    ) -> None:
        """Register a real Python function; the schema is derived from hints."""
        if description is None:
            doc = inspect.getdoc(fn) or ""
            description = doc.splitlines()[0] if doc else "Call the function."
        self.register(
            name=name or fn.__name__,
            description=description,
            args_model=_model_from_signature(fn),
            handler=fn,
            is_mock=is_mock,
        )

    def tool(
        self,
        name: str | None = None,
        description: str | None = None,
        is_mock: bool = False,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator flavour of ``register_function``."""

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.register_function(fn, name=name, description=description, is_mock=is_mock)
            return fn

        return decorator

    # -- dispatch -----------------------------------------------------------
    async def dispatch(self, name: str, arguments: dict[str, Any] | None) -> ToolResult:
        """Validate the argument schema, then run the tool handler.

        The handler may be sync or async; every failure mode (unknown tool,
        schema violation, runtime exception) becomes a structured ToolResult
        so agents can observe the error and recover.
        """
        tool = self._tools.get(name)
        if tool is None:
            available = ", ".join(self._tools)
            error = "unknown tool '" + name + "'; available: " + available
            return ToolResult(tool=name, arguments=arguments or {}, ok=False, error=error)
        try:
            args = tool.args_model.model_validate(arguments or {})
        except ValidationError as exc:
            error = "invalid arguments for '" + name + "': " + str(exc.error_count()) + " schema violation(s)"
            return ToolResult(tool=name, arguments=arguments or {}, ok=False, error=error)
        try:
            output = tool.handler(**args.model_dump())
            if inspect.isawaitable(output):
                output = await output
        except Exception as exc:  # noqa: BLE001 - tool errors are observations
            error = type(exc).__name__ + ": " + str(exc)
            return ToolResult(tool=name, arguments=arguments or {}, ok=False, error=error)
        return ToolResult(tool=name, arguments=arguments or {}, ok=True, output=str(output))

    # -- introspection ------------------------------------------------------
    def names(self) -> list[str]:
        return list(self._tools)

    def describe_for_prompt(self) -> str:
        if not self._tools:
            return "(no tools registered)"
        lines: list[str] = []
        for tool in self._tools.values():
            schema = tool.args_model.model_json_schema()
            props = {
                key: {k: v for k, v in spec.items() if k != "title"}
                for key, spec in schema.get("properties", {}).items()
            }
            required = schema.get("required", [])
            line = f"- {tool.name}: {tool.description}\n"
            line += f"  arguments (JSON): {json.dumps(props, sort_keys=True)}"
            if required:
                line += "\n  required: " + json.dumps(required)
            lines.append(line)
        return "\n".join(lines)


def default_registry() -> ToolRegistry:
    """Registry with the two built-in mock tools used by the demo."""
    registry = ToolRegistry()
    registry.register(
        name="calculator",
        description=(
            "Evaluate an arithmetic expression (+ - * / // % ** and parentheses). "
            "Use it for EVERY numeric computation instead of mental math."
        ),
        args_model=CalculatorArgs,
        handler=calculator,
        is_mock=True,
    )
    registry.register(
        name="knowledge_search",
        description="Search a small offline knowledge base for a factual question.",
        args_model=KnowledgeSearchArgs,
        handler=knowledge_search,
        is_mock=True,
    )
    return registry
