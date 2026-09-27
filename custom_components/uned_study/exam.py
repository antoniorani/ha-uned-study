"""Mock-exam planning and scoring.

Exam mode deliberately ignores personal study progress. It samples a stable
set of questions from the subject bank using content importance only, stores
the resulting order in the session, and withholds correction until finish.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import random
from typing import Mapping, Sequence

from .content.models import Subject, SubjectType, TestQuestion
from .scheduler.engine import IMPORTANCE_WEIGHT


class ExamConfigurationError(ValueError):
    """Raised when a subject cannot produce a mock exam."""


@dataclass(frozen=True, slots=True)
class ExamScore:
    """Final correction summary for one mock exam."""

    total: int
    answered: int
    correct: int
    incorrect: int
    blank: int
    wrong_answer_penalty: float
    raw_points: float
    percentage: float
    grade_10: float

    def as_dict(self) -> dict[str, int | float]:
        return {
            "total": self.total,
            "answered": self.answered,
            "correct": self.correct,
            "incorrect": self.incorrect,
            "blank": self.blank,
            "wrong_answer_penalty": self.wrong_answer_penalty,
            "raw_points": self.raw_points,
            "percentage": self.percentage,
            "grade_10": self.grade_10,
        }


def _weighted_sample_without_replacement(
    questions: Sequence[TestQuestion],
    count: int,
    *,
    rng: random.Random,
) -> list[TestQuestion]:
    """Sample questions without replacement using exam importance weights."""
    pool = list(questions)
    chosen: list[TestQuestion] = []

    while pool and len(chosen) < count:
        weights = [IMPORTANCE_WEIGHT[item.importance] for item in pool]
        picked = rng.choices(pool, weights=weights, k=1)[0]
        chosen.append(picked)
        pool.remove(picked)

    return chosen


def build_exam_filters(
    subject: Subject,
    *,
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> dict[str, object]:
    """Create the durable session payload for a new mock exam."""
    if subject.type is not SubjectType.TEST:
        raise ExamConfigurationError(
            "Mock exams are available only for test subjects"
        )

    questions = [
        item for item in subject.items if isinstance(item, TestQuestion)
    ]
    if not questions:
        raise ExamConfigurationError(
            "The subject does not contain test questions"
        )

    configured_count = subject.exam.get("questions", len(questions))
    if (
        not isinstance(configured_count, int)
        or isinstance(configured_count, bool)
        or configured_count < 1
    ):
        raise ExamConfigurationError(
            "exam.questions must be a positive integer"
        )
    count = min(configured_count, len(questions))

    duration = subject.exam.get("duration_minutes", 60)
    if (
        not isinstance(duration, int)
        or isinstance(duration, bool)
        or duration < 1
    ):
        raise ExamConfigurationError(
            "exam.duration_minutes must be a positive integer"
        )

    penalty = subject.exam.get("wrong_answer_penalty", 0.0)
    if (
        not isinstance(penalty, (int, float))
        or isinstance(penalty, bool)
        or penalty < 0
    ):
        raise ExamConfigurationError(
            "exam.wrong_answer_penalty must be a non-negative number"
        )

    started = now or datetime.now(timezone.utc)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    else:
        started = started.astimezone(timezone.utc)

    chooser = rng or random.Random()
    selected = _weighted_sample_without_replacement(
        questions,
        count,
        rng=chooser,
    )

    return {
        "exam": {
            "item_ids": [item.id for item in selected],
            "answers": {},
            "started_at": started.isoformat(),
            "expires_at": (
                started + timedelta(minutes=duration)
            ).isoformat(),
            "duration_minutes": duration,
            "wrong_answer_penalty": float(penalty),
        }
    }


def exam_payload(filters: Mapping[str, object]) -> dict[str, object]:
    """Return and validate the exam object stored in session filters."""
    value = filters.get("exam")
    if not isinstance(value, dict):
        raise ExamConfigurationError(
            "Study session does not contain mock-exam state"
        )

    item_ids = value.get("item_ids")
    answers = value.get("answers")
    if (
        not isinstance(item_ids, list)
        or not all(isinstance(item, str) for item in item_ids)
        or not isinstance(answers, dict)
    ):
        raise ExamConfigurationError("Mock-exam session data is invalid")
    return value


def exam_expired(
    filters: Mapping[str, object],
    *,
    now: datetime | None = None,
) -> bool:
    """Return whether the server-side exam deadline has passed."""
    exam = exam_payload(filters)
    expires_raw = exam.get("expires_at")
    if not isinstance(expires_raw, str):
        raise ExamConfigurationError("Mock exam has no expiry timestamp")

    expires = datetime.fromisoformat(expires_raw)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    else:
        expires = expires.astimezone(timezone.utc)

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    return current >= expires


def score_exam(
    subject: Subject,
    item_ids: Sequence[str],
    answers: Mapping[str, str],
    *,
    wrong_answer_penalty: float,
) -> ExamScore:
    """Correct an exam without mutating user study progress."""
    correct = 0
    incorrect = 0
    answered = 0

    for item_id in item_ids:
        item = subject.items_by_id.get(item_id)
        if not isinstance(item, TestQuestion):
            raise ExamConfigurationError(
                f"Mock exam references unavailable question {item_id!r}"
            )

        answer = answers.get(item_id)
        if answer is None:
            continue

        answered += 1
        if answer == item.correct_answer:
            correct += 1
        else:
            incorrect += 1

    total = len(item_ids)
    blank = total - answered
    raw_points = correct - (incorrect * wrong_answer_penalty)
    percentage = (100.0 * raw_points / total) if total else 0.0
    grade_10 = (10.0 * raw_points / total) if total else 0.0

    return ExamScore(
        total=total,
        answered=answered,
        correct=correct,
        incorrect=incorrect,
        blank=blank,
        wrong_answer_penalty=float(wrong_answer_penalty),
        raw_points=raw_points,
        percentage=percentage,
        grade_10=grade_10,
    )
