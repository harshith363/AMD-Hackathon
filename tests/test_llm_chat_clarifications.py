import unittest

from cli.llm_chat import _answer_clarification, _empty_intake


class FakeClient:
    def answer_with_tool_result(self, user_text, collected, missing, tool_result):
        return None


class LLMChatClarificationTests(unittest.TestCase):
    def test_options_question_answers_supported_workflows(self):
        collected = _empty_intake()
        collected["customer_type"] = "individual"
        answer = _answer_clarification(FakeClient(), "What options do you have?", collected, ["workflow_type"])

        self.assertIn("find new insurance", answer)
        self.assertIn("validate claim documents", answer)
        self.assertIn("complete KYC validation", answer)
        self.assertIn("Which one", answer)

    def test_new_individual_insurance_options_answers_categories(self):
        collected = _empty_intake()
        collected["customer_type"] = "individual"
        collected["workflow_type"] = "new_insurance"
        answer = _answer_clarification(FakeClient(), "What options do you have?", collected, ["insurance_category"])

        self.assertIn("health", answer)
        self.assertIn("motor", answer)
        self.assertIn("personal accident", answer)

    def test_give_me_options_answers_supported_workflows(self):
        collected = _empty_intake()
        collected["customer_type"] = "individual"
        answer = _answer_clarification(FakeClient(), "give me options", collected, ["workflow_type"])

        self.assertIn("find new insurance", answer)
        self.assertIn("validate claim documents", answer)


if __name__ == "__main__":
    unittest.main()
