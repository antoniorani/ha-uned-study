from __future__ import annotations

import copy
import unittest

from uned_study.content import ContentError, parse_subject


SUBJECT = {
    "schema_version": 1,
    "id": "demo",
    "title": "Demo",
    "type": "test",
    "content_version": "1",
    "topics": [{"id": "tema", "title": "Tema"}],
    "items": [
        {
            "id": "q1",
            "topic": "tema",
            "importance": 3,
            "exam_history": ["2025-02", "2025-06"],
            "question_md": "Pregunta",
            "answers": [
                {"id": "a", "text_md": "A"},
                {"id": "b", "text_md": "B"},
            ],
            "correct_answer": "a",
        }
    ],
}


class ContentTests(unittest.TestCase):
    def test_valid_subject_parses(self) -> None:
        value = parse_subject(SUBJECT, directory_name="demo")
        self.assertEqual(value.id, "demo")
        self.assertEqual(value.items[0].correct_answer, "a")
        self.assertEqual(value.items[0].exam_history, ("2025-02", "2025-06"))

    def test_folder_id_is_durable_contract(self) -> None:
        with self.assertRaises(ContentError):
            parse_subject(SUBJECT, directory_name="other")

    def test_correct_answer_must_exist(self) -> None:
        value = copy.deepcopy(SUBJECT)
        value["items"][0]["correct_answer"] = "z"
        with self.assertRaises(ContentError):
            parse_subject(value, directory_name="demo")

    def test_topic_reference_must_exist(self) -> None:
        value = copy.deepcopy(SUBJECT)
        value["items"][0]["topic"] = "missing"
        with self.assertRaises(ContentError):
            parse_subject(value, directory_name="demo")

    def test_exam_history_must_be_a_string_list(self) -> None:
        value = copy.deepcopy(SUBJECT)
        value["items"][0]["exam_history"] = "2025-02"
        with self.assertRaises(ContentError):
            parse_subject(value, directory_name="demo")


if __name__ == "__main__":
    unittest.main()
