"""Dynamic experience & memory store (persistent lessons).

- Persistence: one JSON object per line in a ``.jsonl`` file.
- Retrieval: idf-weighted keyword coverage over each lesson's match text,
  with a strong boost for exact ``problem_type`` matches and mild boosts for
  reinforcement history and observed effectiveness.
- Deduplication: character-trigram Jaccard similarity on ``rule_to_follow``,
  so morphological rewordings merge into one lesson instead of flooding the
  store with near-identical advice.

The retrieval interface is deliberately small (``retrieve``/``add``); swap the
scoring internals for real embeddings without touching the rest of the harness.
"""
from __future__ import annotations

import json
import math
import re
import warnings
from pathlib import Path

from .schemas import Lesson, LessonDraft, ScoredLesson

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "is", "are",
    "with", "on", "at", "by", "it", "this", "that", "be", "as", "from",
    "was", "were", "then", "than", "so", "no", "not", "do", "does", "did",
    "you", "your", "we", "they", "he", "she", "its", "their", "there",
    "here", "what", "which", "who", "when", "how", "all", "any", "can",
    "will", "just", "into", "up", "down", "out", "about",
}


def _tokenize(text: str) -> list[str]:
    text = text.lower().replace("_", " ")
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text)
        if token not in _STOPWORDS and len(token) > 1
    ]


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _trigrams(text: str) -> set[str]:
    normalized = _normalize(text)
    if not normalized:
        return set()
    if len(normalized) < 3:
        return {normalized}
    return {normalized[i : i + 3] for i in range(len(normalized) - 2)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class LessonStore:
    def __init__(
        self,
        path: str | Path,
        *,
        dedup_threshold: float = 0.45,
        cross_type_dedup_threshold: float = 0.65,
        min_retrieval_score: float = 0.05,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.dedup_threshold = dedup_threshold
        self.cross_type_dedup_threshold = cross_type_dedup_threshold
        self.min_retrieval_score = min_retrieval_score
        self._lessons: list[Lesson] = []
        self._load()

    # ------------------------------------------------------------------ I/O
    def _load(self) -> None:
        self._lessons = []
        if not self.path.exists():
            return
        for line_no, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            line = line.strip()
            if not line:
                continue
            try:
                self._lessons.append(Lesson.model_validate(json.loads(line)))
            except Exception as exc:  # noqa: BLE001 - skip corrupt lines
                warnings.warn(
                    f"lesson store {self.path.name}: skipping corrupt line "
                    f"{line_no}: {exc}"
                )

    def _append(self, lesson: Lesson) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(lesson.model_dump(), ensure_ascii=True) + "\n")

    def _rewrite(self) -> None:
        tmp = self.path.with_suffix(".jsonl.tmp")
        tmp.write_text(
            "".join(
                json.dumps(lesson.model_dump(), ensure_ascii=True) + "\n"
                for lesson in self._lessons
            ),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    # --------------------------------------------------------------- writes
    def add(
        self, draft: LessonDraft, origin_run_id: str | None = None
    ) -> tuple[Lesson, bool]:
        """Store a lesson draft; returns (lesson, created_new).

        Near-duplicate rules (trigram Jaccard above the threshold, lower bar
        inside the same problem type) are merged into the existing lesson by
        bumping ``times_reinforced`` instead of creating a copy.
        """
        new_trigrams = _trigrams(draft.rule_to_follow)
        best: Lesson | None = None
        best_score = 0.0
        for existing in self._lessons:
            same_type = existing.problem_type == draft.problem_type
            threshold = self.dedup_threshold if same_type else self.cross_type_dedup_threshold
            score = _jaccard(new_trigrams, _trigrams(existing.rule_to_follow))
            if score >= threshold and score > best_score:
                best, best_score = existing, score
        if best is not None:
            best.times_reinforced += 1
            for tag in draft.tags:
                if tag not in best.tags:
                    best.tags.append(tag)
            self._rewrite()
            return best, False
        lesson = Lesson(**draft.model_dump(), origin_run_id=origin_run_id)
        self._lessons.append(lesson)
        self._append(lesson)
        return lesson, True

    def record_use(self, lesson_ids: list[str]) -> None:
        ids = set(lesson_ids)
        if not ids:
            return
        for lesson in self._lessons:
            if lesson.id in ids:
                lesson.times_used += 1
        self._rewrite()

    def record_success(self, lesson_ids: list[str]) -> None:
        """Mark lessons that were injected into a run which then succeeded."""
        ids = set(lesson_ids)
        if not ids:
            return
        for lesson in self._lessons:
            if lesson.id in ids:
                lesson.times_helped += 1
        self._rewrite()

    # ---------------------------------------------------------------- reads
    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        problem_type: str | None = None,
    ) -> list[ScoredLesson]:
        """Return the most relevant lessons for a new task.

        score = idf-weighted coverage of the query by the lesson text,
        boosted by 1.5x for an exact problem_type match, mildly by
        reinforcement count and by the observed helped/used ratio.
        """
        if not self._lessons:
            return []

        doc_freq: dict[str, int] = {}
        for lesson in self._lessons:
            for token in set(_tokenize(lesson.match_text())):
                doc_freq[token] = doc_freq.get(token, 0) + 1
        total = len(self._lessons)

        def idf(token: str) -> float:
            return 1.0 + math.log((total + 1) / (doc_freq.get(token, 0) + 0.5))

        query_tokens = list(dict.fromkeys(_tokenize(query)))
        scored: list[ScoredLesson] = []
        for lesson in self._lessons:
            doc_tokens = set(_tokenize(lesson.match_text()))
            denominator = sum(
                idf(token) for token in query_tokens if doc_freq.get(token)
            )
            if denominator <= 0:
                continue
            numerator = sum(idf(token) for token in query_tokens if token in doc_tokens)
            score = numerator / denominator
            if problem_type is not None and lesson.problem_type == problem_type:
                score *= 1.5
            score *= 1.0 + min(lesson.times_reinforced, 5) * 0.1
            if lesson.times_used > 0:
                score *= 1.0 + 0.25 * (lesson.times_helped / lesson.times_used)
            if score >= self.min_retrieval_score:
                scored.append(ScoredLesson(lesson=lesson, score=score))
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]

    def all_lessons(self) -> list[Lesson]:
        return list(self._lessons)

    def stats(self) -> dict[str, object]:
        by_type: dict[str, int] = {}
        for lesson in self._lessons:
            by_type[lesson.problem_type] = by_type.get(lesson.problem_type, 0) + 1
        return {
            "total": len(self._lessons),
            "by_problem_type": by_type,
            "injections": sum(l.times_used for l in self._lessons),
            "successful_runs_with_lesson": sum(l.times_helped for l in self._lessons),
        }
