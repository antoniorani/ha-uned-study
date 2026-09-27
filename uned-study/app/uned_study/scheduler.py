"""Adaptive scheduling hidden behind the simple Continue experience."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import random
from typing import Sequence

from .models import StudyItem

ALGORITHM_VERSION = 1
IMPORTANCE_WEIGHT = {1: 0.7, 2: 0.9, 3: 1.2, 4: 1.6, 5: 2.2}
MAX_INTERVAL_DAYS = {1: 120.0, 2: 90.0, 3: 60.0, 4: 30.0, 5: 14.0}


@dataclass(frozen=True, slots=True)
class Progress:
    item_id: str
    times_seen: int = 0
    correct_count: int = 0
    incorrect_count: int = 0
    streak: int = 0
    mastery: float = 0.0
    difficulty: float = 0.5
    interval_days: float = 0.0
    last_seen_at: datetime | None = None
    next_review_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ScheduleDecision:
    interval_days: float
    next_review_at: datetime
    mastery: float
    difficulty: float


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def priority(
    item: StudyItem,
    progress: Progress | None,
    *,
    now: datetime | None = None,
) -> float:
    """Return a sampling weight from importance, weakness, due state and novelty."""
    now = _utc(now) or datetime.now(timezone.utc)

    if progress is None or progress.times_seen == 0:
        return IMPORTANCE_WEIGHT[item.importance] * 1.35 * 1.25

    error_rate = progress.incorrect_count / max(progress.times_seen, 1)
    weakness = 1.0 + (2.25 * error_rate)

    due = _utc(progress.next_review_at)
    if due is None:
        due_factor = 1.0
    else:
        hours = (now - due).total_seconds() / 3600.0
        due_factor = 0.35 if hours < 0 else min(
            3.0,
            1.0 + math.log1p(hours / 12.0),
        )

    last_seen = _utc(progress.last_seen_at)
    if last_seen is None:
        recency = 1.0
    else:
        minutes = (now - last_seen).total_seconds() / 60.0
        recency = 0.08 if minutes < 2 else (0.35 if minutes < 10 else 1.0)

    return max(
        0.001,
        IMPORTANCE_WEIGHT[item.importance] * weakness * due_factor * recency,
    )


def choose_next(
    items: Sequence[StudyItem],
    progress: dict[str, Progress],
    *,
    recent_item_ids: set[str] | None = None,
    rng: random.Random | None = None,
    now: datetime | None = None,
) -> StudyItem | None:
    """Mix new, weak, important and due content automatically."""
    if not items:
        return None

    recent = recent_item_ids or set()
    candidates = [item for item in items if item.id not in recent]
    if not candidates:
        candidates = list(items)

    weights = [
        priority(item, progress.get(item.id), now=now)
        for item in candidates
    ]
    chooser = rng or random.Random()
    return chooser.choices(candidates, weights=weights, k=1)[0]


def _bounded_interval(importance: int, days: float) -> float:
    minimum = 10.0 / (24.0 * 60.0)
    return max(minimum, min(days, MAX_INTERVAL_DAYS[importance]))


def schedule_test(
    *,
    importance: int,
    correct: bool,
    previous: Progress | None,
    now: datetime | None = None,
) -> ScheduleDecision:
    now = _utc(now) or datetime.now(timezone.utc)
    old_interval = previous.interval_days if previous else 0.0
    old_mastery = previous.mastery if previous else 0.0
    old_difficulty = previous.difficulty if previous else 0.5

    if correct:
        interval = 1.0 if old_interval <= 0 else max(1.0, old_interval * 2.0)
        mastery = min(1.0, old_mastery + 0.20)
        difficulty = max(0.05, old_difficulty - 0.08)
    else:
        interval = 10.0 / (24.0 * 60.0)
        mastery = max(0.0, old_mastery * 0.55 - 0.05)
        difficulty = min(1.0, old_difficulty + 0.15)

    interval = _bounded_interval(importance, interval)
    return ScheduleDecision(
        interval_days=interval,
        next_review_at=now + timedelta(days=interval),
        mastery=mastery,
        difficulty=difficulty,
    )


def schedule_flashcard(
    *,
    importance: int,
    rating: str,
    previous: Progress | None,
    now: datetime | None = None,
) -> ScheduleDecision:
    now = _utc(now) or datetime.now(timezone.utc)
    old_interval = previous.interval_days if previous else 0.0
    old_mastery = previous.mastery if previous else 0.0
    old_difficulty = previous.difficulty if previous else 0.5

    if rating == "again":
        interval = 10.0 / (24.0 * 60.0)
        mastery = max(0.0, old_mastery * 0.45 - 0.05)
        difficulty = min(1.0, old_difficulty + 0.18)
    elif rating == "hard":
        interval = max(1.0, old_interval * 1.2)
        mastery = min(1.0, old_mastery + 0.06)
        difficulty = min(1.0, old_difficulty + 0.05)
    elif rating == "good":
        interval = 3.0 if old_interval <= 0 else old_interval * 2.5
        mastery = min(1.0, old_mastery + 0.20)
        difficulty = max(0.05, old_difficulty - 0.08)
    elif rating == "easy":
        interval = 7.0 if old_interval <= 0 else old_interval * 3.5
        mastery = min(1.0, old_mastery + 0.30)
        difficulty = max(0.05, old_difficulty - 0.15)
    else:
        raise ValueError("rating must be again, hard, good or easy")

    interval = _bounded_interval(importance, interval)
    return ScheduleDecision(
        interval_days=interval,
        next_review_at=now + timedelta(days=interval),
        mastery=mastery,
        difficulty=difficulty,
    )
