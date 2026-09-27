from __future__ import annotations

from datetime import datetime, timedelta, timezone
import random
import unittest

from uned_study.models import StudyItem
from uned_study.scheduler import (
    Progress,
    choose_next,
    priority,
    schedule_flashcard,
    schedule_test,
)


class SchedulerTests(unittest.TestCase):
    def test_importance_affects_new_items(self) -> None:
        low = StudyItem("low", "mcq", "t", 1)
        high = StudyItem("high", "mcq", "t", 5)
        self.assertGreater(priority(high, None), priority(low, None))

    def test_errors_raise_priority(self) -> None:
        now = datetime.now(timezone.utc)
        item = StudyItem("q", "mcq", "t", 3)
        strong = Progress(
            item_id="q",
            times_seen=10,
            correct_count=10,
            incorrect_count=0,
            last_seen_at=now - timedelta(days=2),
            next_review_at=now - timedelta(hours=1),
        )
        weak = Progress(
            item_id="q",
            times_seen=10,
            correct_count=4,
            incorrect_count=6,
            last_seen_at=now - timedelta(days=2),
            next_review_at=now - timedelta(hours=1),
        )
        self.assertGreater(
            priority(item, weak, now=now),
            priority(item, strong, now=now),
        )

    def test_recent_items_are_avoided_when_possible(self) -> None:
        recent = StudyItem("recent", "mcq", "t", 5)
        other = StudyItem("other", "mcq", "t", 1)
        selected = choose_next(
            [recent, other],
            {},
            recent_item_ids={"recent"},
            rng=random.Random(1),
        )
        self.assertEqual(selected.id, "other")

    def test_wrong_test_answer_returns_soon(self) -> None:
        decision = schedule_test(
            importance=3,
            correct=False,
            previous=None,
        )
        self.assertLess(decision.interval_days, 1)

    def test_easy_important_card_has_interval_cap(self) -> None:
        previous = Progress(
            item_id="c",
            interval_days=30,
            mastery=0.8,
            difficulty=0.2,
        )
        decision = schedule_flashcard(
            importance=5,
            rating="easy",
            previous=previous,
        )
        self.assertLessEqual(decision.interval_days, 14)


if __name__ == "__main__":
    unittest.main()
