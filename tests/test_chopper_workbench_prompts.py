import json
from pathlib import Path
import unittest
from unittest.mock import patch

from backend.core import project_assistant
from backend.core.project_assistant import _complete_sequence_question
from backend.core.run_history import current_user


SUITE_PATH = Path(__file__).resolve().parents[1] / "src" / "features" / "assist" / "chopperQuestionSuite.json"


class ChopperWorkbenchPromptSuiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suite = json.loads(SUITE_PATH.read_text(encoding="utf-8"))

    def test_all_reference_test_cases_are_present_once(self):
        cases = [case for group in self.suite["categories"] for case in group["tests"]]
        cases.extend(self.suite["wordingVariationTests"])
        ids = [case["id"] for case in cases]
        self.assertEqual(len(ids), 40)
        self.assertEqual(len(set(ids)), 40)
        self.assertTrue(all(case.get("question") and case.get("expected") for case in cases))
        self.assertEqual(len(self.suite["categories"]), 6)

    def test_machine_function_and_wording_variations_use_machine_analysis_route(self):
        machine = next(group for group in self.suite["categories"] if group["id"] == "machine")
        questions = [case["question"] for case in machine["tests"]]
        questions += [case["question"] for case in self.suite["wordingVariationTests"]]
        misses = [question for question in questions if not _complete_sequence_question(question)]
        self.assertEqual(misses, [])

    def test_auto_and_deep_modes_request_different_evidence_budgets(self):
        class Index:
            def __init__(self):
                self.requested_characters = []

            def retrieve(self, question, characters, passes):
                self.requested_characters.append(characters)
                return {"evidence": [], "notices": [], "passes": [], "tasks": [], "identity": {},
                        "candidateCount": 0, "projectId": "fixture"}

        index = Index()
        index.key = "fixture"
        index.root = Path("fixture")
        user_token = current_user.set({"id": "workbench-test"})
        try:
            with patch.object(project_assistant, "opened", return_value=index), \
                    patch.object(project_assistant, "reference_evidence", return_value=[]), \
                    patch.object(project_assistant, "configuration", return_value={"provider": "local"}):
                for mode in ("auto", "deep"):
                    project_assistant.answer({"question": "Summarize the project layout", "context": {
                        "intelligenceProjectId": "a" * 64, "investigationMode": mode}})
        finally:
            current_user.reset(user_token)
        self.assertEqual(index.requested_characters, [16000, 28000])


if __name__ == "__main__":
    unittest.main()
