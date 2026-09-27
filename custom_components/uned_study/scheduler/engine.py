"""Adaptive study scheduling logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import random
from typing import Protocol, Sequence

ALGORITHM_VERSION = 1
IMPORTANCE_WEIGHT = {1: 0.7, 2: 0.9, 3: 1.2, 4: 1.6, 5: 2.2}
MAX_INTERVAL_DAYS = {1: 120.0, 2: 90.0, 3: 60.0, 4: 30.0, 5: 14.0}


class SchedulableItem(Protocol):
    id: str
    importance: int


@dataclass(frozen=True, slots=True)
class ProgressSnapshot:
    item_id: str
    times_seen: int = 0
    correct_count: int = 0
    incorrect_count: int = 0
    current_streak: int = 0
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


def compute_priority(
    item: SchedulableItem,
    progress: ProgressSnapshot | None,
    *,
    now: datetime | None = None,
    recently_seen: bool = False,
) -> float:
    """Return a study priority from importance, weakness, due date and recency."""
    now = _utc(now) or datetime.now(timezone.utc)

    if progress is None or progress.times_seen == 0:
        weakness = 1.25
        novelty = 1.35
        due_factor = 1.2
        recency_factor = 1.0
    else:
        error_rate = progress.incorrect_count / max(progress.times_seen, 1)
        weakness = 1.0 + 2.25 * error_rate
        novelty = 1.0

        due = _utc(progress.next_review_at)
        if due is None:
            due_factor = 1.0
        else:
            hours = (now - due).total_seconds() / 3600.0
            due_factor = 0.35 if hours < 0 else min(
                3.0, 1.0 + math.log1p(hours / 12.0)
            )

        last_seen = _utc(progress.last_seen_at)
        if last_seen is None:
            recency_factor = 1.0
        else:
            minutes = (now - last_seen).total_seconds() / 60.0
            recency_factor = 0.08 if minutes < 2 else (
                0.35 if minutes < 10 else 1.0
            )

    if recently_seen:
        recency_factor *= 0.15

    return max(
        0.001,
        IMPORTANCE_WEIGHT[item.importance]
        * weakness
        * novelty
        * due_factor
        * recency_factor,
    )


def choose_next_item(
    items: Sequence[SchedulableItem],
    progress: dict[str, ProgressSnapshot],
    *,
    recent_item_ids: set[str] | None = None,
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> SchedulableItem | None:
    """Choose by weighted priority outside the recent-review window."""
    if not items:
        return None

    recent = recent_item_ids or set()
    candidates = [item for item in items if item.id not in recent]
    if not candidates:
        candidates = list(items)

    weights = [
        compute_priority(
            item,
            progress.get(item.id),
            now=now,
        )
        for item in candidates
    ]
    chooser = rng or random.Random()
    return chooser.choices(candidates, weights=weights, k=1)[0]


def _bounded_interval(importance: int, interval_days: float) -> float:
    minimum = 10.0 / (24.0 * 60.0)
    return max(minimum, min(interval_days, MAX_INTERVAL_DAYS[importance]))


def schedule_test(
    *,
    importance: int,
    was_correct: bool,
    previous_interval_days: float,
    now: datetime | None = None,
) -> ScheduleDecision:
    """Schedule the next review after a test answer."""
    now = _utc(now) or datetime.now(timezone.utc)
    if was_correct:
        interval = 1.0 if previous_interval_days <= 0 else max(
            1.0, previous_interval_days * 2.0
        )
        mastery, difficulty = 0.65, 0.35
    else:
        interval = 10.0 / (24.0 * 60.0)
        mastery, difficulty = 0.15, 0.85

    interval = _bounded_interval(importance, interval)
    return ScheduleDecision(
        interval,
        now + timedelta(days=interval),
        mastery,
        difficulty,
    )


def schedule_flashcard(
    *,
    importance: int,
    rating: str,
    previous_interval_days: float,
    now: datetime | None = None,
) -> ScheduleDecision:
    """Schedule after Again/Hard/Good/Easy self-rating."""
    now = _utc(now) or datetime.now(timezone.utc)

    if rating == "again":
        interval, mastery, difficulty = 10.0 / (24.0 * 60.0), 0.1, 0.9
    elif rating == "hard":
        interval, mastery, difficulty = max(
            1.0, previous_interval_days * 1.2
        ), 0.45, 0.7
    elif rating == "good":
        interval, mastery, difficulty = (
            3.0 if previous_interval_days <= 0
            else previous_interval_days * 2.5
        ), 0.72, 0.4
    elif rating == "easy":
        interval, mastery, difficulty = (
            7.0 if previous_interval_days <= 0
            else previous_interval_days * 3.5
        ), 0.9, 0.2
    else:
        raise ValueError("rating must be again, hard, good or easy")

    interval = _bounded_interval(importance, interval)
    return ScheduleDecision(
        interval,
        now + timedelta(days=interval),
        mastery,
        difficulty,
    )
