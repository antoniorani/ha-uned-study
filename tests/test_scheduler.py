"""Tests for adaptive scheduling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import unittest

from custom_components.uned_study.scheduler import (
    ProgressSnapshot,
    choose_next_item,
    compute_priority,
    schedule_flashcard,
    schedule_test,
)


@dataclass(frozen=True)
class Item:
    id: str
    importance: int


class SchedulerTests(unittest.TestCase):
    def test_importance_increases_new_item_priority(self) -> None:
        low = Item("low", 1)
        high = Item("high", 5)
        self.assertGreater(
            compute_priority(high, None),
            compute_priority(low, None),
        )

    def test_errors_raise_priority(self) -> None:
        item = Item("item", 3)
        now = datetime.now(timezone.utc)
        strong = ProgressSnapshot(
            item_id="item",
            times_seen=10,
            correct_count=10,
            incorrect_count=0,
            current_streak=10,
            last_seen_at=now - timedelta(days=3),
            next_review_at=now - timedelta(days=1),
        )
        weak = ProgressSnapshot(
            item_id="item",
            times_seen=10,
            correct_count=4,
            incorrect_count=6,
            current_streak=0,
            last_seen_at=now - timedelta(days=3),
            next_review_at=now - timedelta(days=1),
        )
        self.assertGreater(
            compute_priority(item, weak, now=now),
            compute_priority(item, strong, now=now),
        )

    def test_recent_window_excludes_item_when_possible(self) -> None:
        recent = Item("recent", 5)
        other = Item("other", 1)
        chosen = choose_next_item(
            [recent, other],
            {},
            recent_item_ids={"recent"},
        )
        self.assertEqual(chosen.id, "other")

    def test_failed_test_returns_soon(self) -> None:
        now = datetime.now(timezone.utc)
        decision = schedule_test(
            importance=3,
            was_correct=False,
            previous_interval_days=5,
            now=now,
        )
        self.assertLess(
            decision.next_review_at,
            now + timedelta(hours=1),
        )

    def test_mastery_accumulates_across_correct_reviews(self) -> None:
        first = schedule_test(
            importance=3,
            was_correct=True,
            previous_interval_days=0,
        )
        second = schedule_test(
            importance=3,
            was_correct=True,
            previous_interval_days=first.interval_days,
            previous_mastery=first.mastery,
            previous_difficulty=first.difficulty,
        )
        self.assertGreater(second.mastery, first.mastery)
        self.assertLess(second.difficulty, first.difficulty)

    def test_failure_reduces_existing_mastery(self) -> None:
        decision = schedule_test(
            importance=3,
            was_correct=False,
            previous_interval_days=7,
            previous_mastery=0.8,
            previous_difficulty=0.3,
        )
        self.assertLess(decision.mastery, 0.8)
        self.assertGreater(decision.difficulty, 0.3)

    def test_important_easy_card_is_capped(self) -> None:
        decision = schedule_flashcard(
            importance=5,
            rating="easy",
            previous_interval_days=30,
        )
        self.assertLessEqual(decision.interval_days, 14)


if __name__ == "__main__":
    unittest.main()
