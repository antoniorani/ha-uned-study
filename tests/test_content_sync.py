from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from uned_study.content import ContentError, ContentManager


VALID = {
    "schema_version": 1,
    "id": "demo",
    "title": "Demo",
    "type": "flashcards",
    "content_version": "1",
    "topics": [{"id": "tema", "title": "Tema"}],
    "items": [
        {
            "id": "c1",
            "topic": "tema",
            "importance": 3,
            "front_md": "Pregunta",
            "back_md": "Respuesta",
        }
    ],
}


def archive(subject: object) -> bytes:
    payload = json.dumps(subject).encode()
    output = BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as tar:
        info = tarfile.TarInfo(
            "repo-main/subjects/demo/subject.json"
        )
        info.size = len(payload)
        tar.addfile(info, BytesIO(payload))
    return output.getvalue()


class ContentSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = ContentManager(
            data_dir=self.root,
            repository="https://github.com/antoniorani/uned-study-content",
            branch="main",
        )
        self.manager.content_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_valid_snapshot_activates(self) -> None:
        subjects = self.manager._install_archive(archive(VALID))
        self.assertIn("demo", subjects)
        self.assertTrue(
            (self.manager.content_dir / "demo" / "subject.json").is_file()
        )

    def test_invalid_snapshot_does_not_replace_active_content(self) -> None:
        self.manager._install_archive(archive(VALID))
        path = self.manager.content_dir / "demo" / "subject.json"
        before = path.read_bytes()

        invalid = dict(VALID)
        invalid["id"] = "wrong"
        with self.assertRaises(ContentError):
            self.manager._install_archive(archive(invalid))

        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
