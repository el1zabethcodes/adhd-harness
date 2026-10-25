"""Render README assets: terminal-style SVG snapshots and animated GIF replays.

Runs the real two-run demo with a recording rich console, then exports:

    docs/img/run1.svg   - SVG "screenshot" of run 1 (mistake -> lesson)
    docs/img/run2.svg   - SVG "screenshot" of run 2 (lesson -> clean solve)
    docs/img/run1.gif   - line-by-line animated replay of run 1
    docs/img/run2.gif   - line-by-line animated replay of run 2

Everything runs offline (ScriptedLLM); no API key is required.

Usage:
    python scripts/render_assets.py
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rich.console import Console

from core.llm import ScriptedLLM, ScriptedTurn
from core.memory import LessonStore
from core.orchestrator import Harness
from core.schemas import RunConfig
from core.tools import default_registry
from core.tracing import ConsoleReporter
from examples.demo_two_runs import PROBLEM_TYPE, TASK_1, TASK_2, build_script

IMG_DIR = ROOT / "docs" / "img"

ROLE_RGB = {
    "worker": (97, 175, 239),    # blue
    "critic": (224, 175, 104),   # amber
    "reflector": (209, 154, 209),  # magenta
    "tool": (152, 195, 121),     # green
    "system": (150, 158, 168),   # gray
    "lesson": (130, 170, 255),   # bright blue
}

BG = (13, 17, 23)        # GitHub dark canvas
FG = (240, 246, 252)
FONT_PATHS = {
    "regular": "C:/Windows/Fonts/consola.ttf",
    "bold": "C:/Windows/Fonts/consolab.ttf",
}


class RecordingReporter(ConsoleReporter):
    """Feeds a recording rich console and collects every emitted line."""

    def __init__(self, console: Console) -> None:
        super().__init__(console=console)
        self.lines: list[tuple[str, str]] = []

    def _emit(self, role: str, text: str, bold: bool = False) -> None:
        self.lines.append((role, text))
        super()._emit(role, text, bold)

    def run_start(self, run_id: str, task: str) -> None:
        self.lines.append(("system", "run " + run_id))
        super().run_start(run_id, task)


def _wrap_lines(lines: list[tuple[str, str]], wrap: int) -> list[tuple[tuple[int, int, int], str]]:
    wrapped: list[tuple[tuple[int, int, int], str]] = []
    for role, text in lines:
        color = ROLE_RGB.get(role, (200, 204, 210))
        for chunk in textwrap.wrap(text, wrap) or [" "]:
            wrapped.append((color, chunk))
    return wrapped


def make_gif(
    lines: list[tuple[str, str]],
    path: Path,
    title: str,
    *,
    width: int = 980,
    line_height: int = 24,
    font_size: int = 16,
    wrap: int = 96,
    frame_ms: int = 420,
) -> None:
    """Animated replay: reveal one terminal line per frame, blinking cursor."""
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(FONT_PATHS["regular"], font_size)
    bold = ImageFont.truetype(FONT_PATHS["bold"], font_size)
    wrapped = _wrap_lines(lines, wrap)
    top = 56
    height = top + line_height * max(len(wrapped) + 1, 14) + 16

    def frame(visible: int, cursor: bool) -> Image.Image:
        img = Image.new("RGB", (width, height), BG)
        draw = ImageDraw.Draw(img)
        draw.text((24, 18), title, font=bold, fill=FG)
        y = top
        for color, chunk in wrapped[:visible]:
            draw.text((24, y), chunk, font=font, fill=color)
            y += line_height
        if cursor:
            draw.rectangle([24, y + 2, 24 + 9, y + line_height - 6], fill=FG)
        return img

    frames = [frame(n, True) for n in range(1, len(wrapped) + 1)]
    # Hold the last frame with a blinking cursor before the loop restarts.
    frames.append(frame(len(wrapped), False))
    durations = [frame_ms] * (len(frames) - 2) + [1600, 350]
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    print(f"  wrote {path.name}: {len(frames)} frames, {path.stat().st_size // 1024} KB")


async def render_run(
    task: str,
    turns: list[ScriptedTurn],
    store: LessonStore,
    svg_name: str,
    gif_name: str,
    gif_title: str,
    logs_dir: Path,
) -> None:
    console = Console(record=True, width=100, force_terminal=True, highlight=False)
    reporter = RecordingReporter(console)
    harness = Harness(
        ScriptedLLM(turns),
        store,
        default_registry(),
        RunConfig(max_turns=10, max_revisions=3),
        logs_dir=logs_dir,
        reporter=reporter,
    )
    await harness.run(task, problem_type=PROBLEM_TYPE)

    svg = console.export_svg(title="adhd-harness | " + gif_title)
    (IMG_DIR / svg_name).write_text(svg, encoding="utf-8")
    print(f"  wrote {svg_name}: {(IMG_DIR / svg_name).stat().st_size // 1024} KB")
    make_gif(reporter.lines, IMG_DIR / gif_name, gif_title)


async def main() -> None:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    print("Rendering README assets (offline, deterministic)...")
    turns = build_script()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        store = LessonStore(tmp_path / "lessons.jsonl")
        # 9 scripted turns belong to run 1, the remaining 7 to run 2.
        await render_run(
            TASK_1,
            turns[:9],
            store,
            svg_name="run1.svg",
            gif_name="run1.gif",
            gif_title="run 1 - fresh store: mistake, caught, fixed, learned",
            logs_dir=tmp_path / "logs",
        )
        await render_run(
            TASK_2,
            turns[9:],
            store,
            svg_name="run2.svg",
            gif_name="run2.gif",
            gif_title="run 2 - lesson retrieved: clean solve, zero revisions",
            logs_dir=tmp_path / "logs",
        )
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
