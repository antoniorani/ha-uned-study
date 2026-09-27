"""Tests for mock exam planning and scoring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import random
import unittest

from custom_components.uned_study.content.models import (
    AnswerOption,
    Subject,
    SubjectType,
    TestQuestion,
    Topic,
)
from custom_components.uned_study.exam import (
    ExamConfigurationError,
    build_exam_filters,
    exam_expired,
    exam_payload,
    score_exam,
)


def subject() -> Subject:
    questions = tuple(
        TestQuestion(
            id=f"q{index}",
            topic="tema_01",
            importance=index,
            question_md=f"Pregunta {index}",
            answers=(
                AnswerOption(id="a", text_md="A"),
                AnswerOption(id="b", text_md="B"),
            ),
            correct_answer="a",
            explanation_md="Explicación",
        )
        for index in range(1, 6)
    )
    return Subject(
        schema_version=1,
        id="demo",
        title="Demo",
        type=SubjectType.TEST,
        content_version="2026.09.1",
        topics=(Topic(id="tema_01", title="Tema 1"),),
        items=questions,
        exam={
            "questions": 3,
            "duration_minutes": 30,
            "wrong_answer_penalty": 0.25,
        },
    )


class ExamTests(unittest.TestCase):
    def test_plan_is_stable_payload_with_configured_size(self) -> None:
        now = datetime(2026, 9, 27, 20, 0, tzinfo=timezone.utc)
        filters = build_exam_filters(
            subject(),
            now=now,
            rng=random.Random(7),
        )
        exam = exam_payload(filters)

        self.assertEqual(len(exam["item_ids"]), 3)
        self.assertEqual(len(set(exam["item_ids"])), 3)
        self.assertEqual(exam["answers"], {})
        self.assertEqual(exam["current_index"], 0)
        self.assertEqual(
            exam["expires_at"],
            (now + timedelta(minutes=30)).isoformat(),
        )

    def test_same_rng_seed_reproduces_exam_order(self) -> None:
        first = build_exam_filters(
            subject(),
            rng=random.Random(99),
        )
        second = build_exam_filters(
            subject(),
            rng=random.Random(99),
        )
        self.assertEqual(
            exam_payload(first)["item_ids"],
            exam_payload(second)["item_ids"],
        )

    def test_expiry_uses_server_timestamp(self) -> None:
        now = datetime(2026, 9, 27, 20, 0, tzinfo=timezone.utc)
        filters = build_exam_filters(
            subject(),
            now=now,
            rng=random.Random(1),
        )
        self.assertFalse(
            exam_expired(
                filters,
                now=now + timedelta(minutes=29, seconds=59),
            )
        )
        self.assertTrue(
            exam_expired(
                filters,
                now=now + timedelta(minutes=30),
            )
        )

    def test_score_applies_wrong_answer_penalty(self) -> None:
        result = score_exam(
            subject(),
            ["q1", "q2", "q3", "q4"],
            {
                "q1": "a",
                "q2": "a",
                "q3": "b",
            },
            wrong_answer_penalty=0.25,
        )
        self.assertEqual(result.total, 4)
        self.assertEqual(result.answered, 3)
        self.assertEqual(result.correct, 2)
        self.assertEqual(result.incorrect, 1)
        self.assertEqual(result.blank, 1)
        self.assertAlmostEqual(result.raw_points, 1.75)
        self.assertAlmostEqual(result.grade_10, 4.375)

    def test_flashcard_subject_cannot_create_exam(self) -> None:
        value = Subject(
            schema_version=1,
            id="cards",
            title="Cards",
            type=SubjectType.FLASHCARDS,
            content_version="1",
            topics=(Topic(id="tema_01", title="Tema 1"),),
            items=(),
        )
        with self.assertRaises(ExamConfigurationError):
            build_exam_filters(value)


if __name__ == "__main__":
    unittest.main()
