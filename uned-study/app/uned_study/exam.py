"""Mock exam planning and scoring, independent of personal weaknesses."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import random
from typing import Mapping

from .models import StudyItem, Subject
from .scheduler import IMPORTANCE_WEIGHT


def build_exam_state(
    subject: Subject,
    *,
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> dict[str, object]:
    if subject.subject_type != "test":
        raise ValueError("mock exams require a test subject")

    questions = [item for item in subject.items if item.item_type == "mcq"]
    if not questions:
        raise ValueError("subject has no test questions")

    if not all(
        key in subject.exam
        for key in (
            "questions",
            "duration_minutes",
            "wrong_answer_penalty",
        )
    ):
        raise ValueError(
            "mock exam requires explicit questions, duration and penalty metadata"
        )

    count = subject.exam["questions"]
    duration = subject.exam["duration_minutes"]
    penalty = subject.exam["wrong_answer_penalty"]

    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise ValueError("exam.questions must be a positive integer")
    if not isinstance(duration, int) or isinstance(duration, bool) or duration < 1:
        raise ValueError("exam.duration_minutes must be a positive integer")
    if (
        not isinstance(penalty, (int, float))
        or isinstance(penalty, bool)
        or penalty < 0
    ):
        raise ValueError("exam.wrong_answer_penalty must be non-negative")

    chooser = rng or random.Random()
    pool = list(questions)
    selected: list[StudyItem] = []
    for _ in range(min(count, len(pool))):
        weights = [IMPORTANCE_WEIGHT[item.importance] for item in pool]
        item = chooser.choices(pool, weights=weights, k=1)[0]
        selected.append(item)
        pool.remove(item)

    started = now or datetime.now(timezone.utc)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    else:
        started = started.astimezone(timezone.utc)

    return {
        "item_ids": [item.id for item in selected],
        "answers": {},
        "current_index": 0,
        "started_at": started.isoformat(),
        "expires_at": (
            started + timedelta(minutes=duration)
        ).isoformat(),
        "duration_minutes": duration,
        "wrong_answer_penalty": float(penalty),
    }


def expired(state: Mapping[str, object], *, now: datetime | None = None) -> bool:
    raw = state.get("expires_at")
    if not isinstance(raw, str):
        raise ValueError("exam state has no expiry")
    deadline = datetime.fromisoformat(raw)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc) >= deadline.astimezone(timezone.utc)


def score(
    subject: Subject,
    state: Mapping[str, object],
) -> dict[str, int | float]:
    item_ids = state.get("item_ids")
    answers = state.get("answers")
    penalty = float(state.get("wrong_answer_penalty", 0.0))

    if not isinstance(item_ids, list) or not isinstance(answers, dict):
        raise ValueError("invalid exam state")

    correct = 0
    incorrect = 0
    for item_id in item_ids:
        item = subject.items_by_id.get(str(item_id))
        if item is None or item.item_type != "mcq":
            raise ValueError("exam question is unavailable")
        chosen = answers.get(item.id)
        if chosen is None:
            continue
        if chosen == item.correct_answer:
            correct += 1
        else:
            incorrect += 1

    total = len(item_ids)
    answered = correct + incorrect
    blank = total - answered
    raw_points = correct - (incorrect * penalty)
    return {
        "total": total,
        "answered": answered,
        "correct": correct,
        "incorrect": incorrect,
        "blank": blank,
        "wrong_answer_penalty": penalty,
        "raw_points": raw_points,
        "percentage": (100.0 * raw_points / total) if total else 0.0,
        "grade_10": (10.0 * raw_points / total) if total else 0.0,
    }
