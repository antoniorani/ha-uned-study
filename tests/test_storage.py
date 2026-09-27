from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from uned_study.scheduler import ScheduleDecision
from uned_study.storage import Storage


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "study.db"
        self.storage = Storage(self.path)
        self.storage.initialize()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_users_are_isolated(self) -> None:
        self.storage.set_favorite("user-a", "civil", True)
        self.assertTrue(
            self.storage.preferences("user-a")["civil"]["favorite"]
        )
        self.assertEqual(self.storage.preferences("user-b"), {})

    def test_session_survives_new_storage_instance(self) -> None:
        session = self.storage.create_session(
            session_id="s1",
            user_id="user-a",
            subject_id="civil",
            kind="topic",
            topic_id="tema_01",
        )
        self.storage.set_current_item("user-a", "s1", "q1")

        reopened = Storage(self.path)
        reopened.initialize()
        loaded = reopened.get_session("user-a", "s1")
        self.assertEqual(loaded["topic_id"], "tema_01")
        self.assertEqual(loaded["current_item_id"], "q1")
        self.assertEqual(session["state"], "active")

    def test_new_session_pauses_previous_one(self) -> None:
        self.storage.create_session(
            session_id="old",
            user_id="user-a",
            subject_id="civil",
            kind="adaptive",
        )
        self.storage.create_session(
            session_id="new",
            user_id="user-a",
            subject_id="civil",
            kind="topic",
            topic_id="tema_01",
        )
        self.assertEqual(
            self.storage.get_session("user-a", "old")["state"],
            "paused",
        )
        self.assertEqual(
            self.storage.active_session("user-a", "civil")["session_id"],
            "new",
        )

    def test_review_request_is_idempotent(self) -> None:
        self.storage.create_session(
            session_id="s1",
            user_id="user-a",
            subject_id="civil",
            kind="adaptive",
        )
        decision = ScheduleDecision(
            interval_days=1,
            next_review_at=datetime.now(timezone.utc) + timedelta(days=1),
            mastery=0.2,
            difficulty=0.4,
        )
        first = self.storage.record_review(
            request_id="r1",
            user_id="user-a",
            subject_id="civil",
            item_id="q1",
            session_id="s1",
            result="correct",
            answer_id="a",
            rating=None,
            response_ms=1000,
            decision=decision,
        )
        second = self.storage.record_review(
            request_id="r1",
            user_id="user-a",
            subject_id="civil",
            item_id="q1",
            session_id="s1",
            result="correct",
            answer_id="a",
            rating=None,
            response_ms=1000,
            decision=decision,
        )
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(
            self.storage.progress_map("user-a", "civil")["q1"].times_seen,
            1,
        )


if __name__ == "__main__":
    unittest.main()
