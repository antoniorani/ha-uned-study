"""Tests for durable multi-user SQLite persistence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from custom_components.uned_study.database import StudyDatabase
from custom_components.uned_study.scheduler import ScheduleDecision


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "uned_study.db"
        self.db = StudyDatabase(self.path)
        self.db._initialize()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_preferences_are_isolated_by_home_assistant_user(self) -> None:
        self.db._set_favorite("user-a", "civil", True)
        self.assertTrue(
            self.db._get_subject_preferences("user-a")["civil"]["favorite"]
        )
        self.assertEqual(
            self.db._get_subject_preferences("user-b"),
            {},
        )

    def test_progress_survives_new_database_instance(self) -> None:
        self.db._create_session(
            "session-1",
            "user-a",
            "civil",
            "adaptive",
            {},
        )
        self.db._set_current_item(
            "session-1",
            "user-a",
            "civil-q001",
        )

        now = datetime.now(timezone.utc)
        decision = ScheduleDecision(
            interval_days=1.0,
            next_review_at=now + timedelta(days=1),
            mastery=0.65,
            difficulty=0.35,
        )
        committed = self.db._record_review(
            "request-1",
            "user-a",
            "civil",
            "civil-q001",
            "session-1",
            "correct",
            None,
            1200,
            decision,
        )
        self.assertTrue(committed)

        reopened = StudyDatabase(self.path)
        reopened._initialize()
        progress = reopened._get_progress_map("user-a", "civil")
        self.assertEqual(progress["civil-q001"].times_seen, 1)
        self.assertEqual(progress["civil-q001"].correct_count, 1)

    def test_request_id_prevents_double_counting(self) -> None:
        self.db._create_session(
            "session-1",
            "user-a",
            "civil",
            "adaptive",
            {},
        )
        decision = ScheduleDecision(
            interval_days=1.0,
            next_review_at=datetime.now(timezone.utc) + timedelta(days=1),
            mastery=0.65,
            difficulty=0.35,
        )
        first = self.db._record_review(
            "request-1",
            "user-a",
            "civil",
            "civil-q001",
            "session-1",
            "correct",
            None,
            1000,
            decision,
        )
        second = self.db._record_review(
            "request-1",
            "user-a",
            "civil",
            "civil-q001",
            "session-1",
            "correct",
            None,
            1000,
            decision,
        )
        self.assertTrue(first)
        self.assertFalse(second)
        progress = self.db._get_progress_map("user-a", "civil")
        self.assertEqual(progress["civil-q001"].times_seen, 1)

    def test_new_session_pauses_previous_subject_session(self) -> None:
        self.db._create_session(
            "session-old",
            "user-a",
            "civil",
            "adaptive",
            {},
        )
        self.db._create_session(
            "session-new",
            "user-a",
            "civil",
            "errors",
            {},
        )
        old = self.db._get_session("session-old", "user-a")
        new = self.db._get_session("session-new", "user-a")
        self.assertEqual(old["state"], "paused")
        self.assertEqual(new["state"], "active")
        active = self.db._get_active_sessions("user-a")
        self.assertEqual(active["civil"]["session_id"], "session-new")

    def test_checkpoint_is_safe(self) -> None:
        self.db._checkpoint()
        self.assertTrue(self.path.exists())


if __name__ == "__main__":
    unittest.main()
