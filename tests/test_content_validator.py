"""Tests for the subject content contract."""

from __future__ import annotations

import copy
import unittest

from custom_components.uned_study.content.models import (
    Flashcard,
    TestQuestion,
)
from custom_components.uned_study.content.validator import (
    ContentValidationError,
    parse_subject,
)


TEST_SUBJECT = {
    "schema_version": 1,
    "id": "demo_test",
    "title": "Demo test",
    "type": "test",
    "content_version": "2026.09.1",
    "topics": [{"id": "tema_01", "title": "Tema 1"}],
    "items": [
        {
            "id": "demo-t01-q001",
            "topic": "tema_01",
            "importance": 5,
            "question_md": "Pregunta",
            "answers": [
                {"id": "a", "text_md": "A"},
                {"id": "b", "text_md": "B"},
            ],
            "correct_answer": "a",
            "explanation_md": "Explicación",
        }
    ],
}


class ContentValidatorTests(unittest.TestCase):
    def test_parses_test_subject(self) -> None:
        subject = parse_subject(
            TEST_SUBJECT,
            directory_name="demo_test",
        )
        self.assertEqual(subject.id, "demo_test")
        self.assertIsInstance(subject.items[0], TestQuestion)

    def test_folder_id_must_match(self) -> None:
        with self.assertRaises(ContentValidationError):
            parse_subject(
                TEST_SUBJECT,
                directory_name="different",
            )

    def test_correct_answer_must_exist(self) -> None:
        value = copy.deepcopy(TEST_SUBJECT)
        value["items"][0]["correct_answer"] = "z"
        with self.assertRaises(ContentValidationError):
            parse_subject(value, directory_name="demo_test")

    def test_flashcard_requires_back(self) -> None:
        value = {
            "schema_version": 1,
            "id": "demo_cards",
            "title": "Demo cards",
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
        subject = parse_subject(
            value,
            directory_name="demo_cards",
        )
        self.assertIsInstance(subject.items[0], Flashcard)


if __name__ == "__main__":
    unittest.main()
