from __future__ import annotations

from datetime import datetime, timedelta, timezone
import random
import unittest

from uned_study.exam import build_exam_state, expired, score
from uned_study.models import AnswerOption, StudyItem, Subject, Topic


def subject() -> Subject:
    items = tuple(
        StudyItem(
            id=f"q{index}",
            item_type="mcq",
            topic="tema",
            importance=index,
            question_md=f"Pregunta {index}",
            answers=(
                AnswerOption("a", "A"),
                AnswerOption("b", "B"),
            ),
            correct_answer="a",
        )
        for index in range(1, 6)
    )
    return Subject(
        schema_version=1,
        id="demo",
        title="Demo",
        subject_type="test",
        content_version="1",
        topics=(Topic("tema", "Tema"),),
        items=items,
        exam={
            "questions": 3,
            "duration_minutes": 30,
            "wrong_answer_penalty": 0.25,
        },
    )


class ExamTests(unittest.TestCase):
    def test_plan_has_unique_questions_and_deadline(self) -> None:
        now = datetime(2026, 9, 27, 20, 0, tzinfo=timezone.utc)
        state = build_exam_state(
            subject(),
            now=now,
            rng=random.Random(4),
        )
        self.assertEqual(len(state["item_ids"]), 3)
        self.assertEqual(len(set(state["item_ids"])), 3)
        self.assertEqual(
            state["expires_at"],
            (now + timedelta(minutes=30)).isoformat(),
        )

    def test_expiry_is_server_timestamp_based(self) -> None:
        now = datetime(2026, 9, 27, 20, 0, tzinfo=timezone.utc)
        state = build_exam_state(
            subject(),
            now=now,
            rng=random.Random(1),
        )
        self.assertFalse(expired(state, now=now + timedelta(minutes=29)))
        self.assertTrue(expired(state, now=now + timedelta(minutes=30)))

    def test_penalty_is_applied(self) -> None:
        state = {
            "item_ids": ["q1", "q2", "q3", "q4"],
            "answers": {"q1": "a", "q2": "a", "q3": "b"},
            "wrong_answer_penalty": 0.25,
        }
        result = score(subject(), state)
        self.assertEqual(result["correct"], 2)
        self.assertEqual(result["incorrect"], 1)
        self.assertEqual(result["blank"], 1)
        self.assertAlmostEqual(result["raw_points"], 1.75)
        self.assertAlmostEqual(result["grade_10"], 4.375)


if __name__ == "__main__":
    unittest.main()
