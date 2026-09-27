"""Tests for atomic GitHub content activation."""

from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from custom_components.uned_study.content.sync import (
    ContentSyncError,
    GitHubContentSynchronizer,
    SyncReport,
)


def archive_with_subject(subject: object) -> bytes:
    """Build an in-memory GitHub-like tar.gz archive."""
    payload = json.dumps(subject).encode()
    output = BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as tar:
        info = tarfile.TarInfo(
            "uned-study-content-main/subjects/demo/subject.json"
        )
        info.size = len(payload)
        tar.addfile(info, BytesIO(payload))
    return output.getvalue()


VALID_SUBJECT = {
    "schema_version": 1,
    "id": "demo",
    "title": "Demo",
    "type": "flashcards",
    "content_version": "2026.09.1",
    "topics": [{"id": "tema_01", "title": "Tema 1"}],
    "items": [
        {
            "id": "demo-t01-c001",
            "topic": "tema_01",
            "importance": 3,
            "front_md": "Pregunta",
            "back_md": "Respuesta",
        }
    ],
}


class ContentSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp.name)
        self.content_dir = self.data_dir / "content"
        self.sync = GitHubContentSynchronizer(
            data_dir=self.data_dir,
            content_dir=self.content_dir,
            repository="antoniorani/uned-study-content",
            branch="main",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_valid_snapshot_is_activated(self) -> None:
        report = self.sync._install_archive(
            archive_with_subject(VALID_SUBJECT)
        )
        self.assertEqual(report.subject_count, 1)
        subject = json.loads(
            (self.content_dir / "demo" / "subject.json").read_text()
        )
        self.assertEqual(subject["id"], "demo")

    def test_invalid_snapshot_keeps_previous_content(self) -> None:
        self.sync._install_archive(
            archive_with_subject(VALID_SUBJECT)
        )
        before = (
            self.content_dir / "demo" / "subject.json"
        ).read_bytes()

        broken = dict(VALID_SUBJECT)
        broken["id"] = "wrong"
        with self.assertRaises(ContentSyncError):
            self.sync._install_archive(
                archive_with_subject(broken)
            )

        after = (
            self.content_dir / "demo" / "subject.json"
        ).read_bytes()
        self.assertEqual(after, before)

    def test_sync_state_survives_new_synchronizer(self) -> None:
        self.sync.last_report = SyncReport(
            repository="antoniorani/uned-study-content",
            branch="main",
            subject_count=4,
            synced_at="2026-09-27T20:00:00+00:00",
        )
        self.sync.last_error = None
        self.sync._save_state()

        restored = GitHubContentSynchronizer(
            data_dir=self.data_dir,
            content_dir=self.content_dir,
            repository="antoniorani/uned-study-content",
            branch="main",
        )
        restored._load_state()

        self.assertIsNotNone(restored.last_report)
        self.assertEqual(restored.last_report.subject_count, 4)


if __name__ == "__main__":
    unittest.main()
