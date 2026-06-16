import unittest

from cli.llm_chat import _answer_clarification, _empty_intake, _missing_fields


class FakeClient:
    def answer_with_tool_result(self, user_text, collected, missing, tool_result):
        return None


class LLMChatClarificationTests(unittest.TestCase):
    def test_options_question_answers_supported_workflows(self):
        collected = _empty_intake()
        collected["customer_type"] = "individual"
        answer = _answer_clarification(FakeClient(), "What options do you have?", collected, ["workflow_type"])

        self.assertIn("start policy onboarding", answer)
        self.assertIn("validate claim compliance", answer)
        self.assertIn("complete KYC validation", answer)
        self.assertIn("Which one", answer)

    def test_new_individual_insurance_options_answers_categories(self):
        collected = _empty_intake()
        collected["customer_type"] = "individual"
        collected["workflow_type"] = "new_insurance"
        answer = _answer_clarification(FakeClient(), "What options do you have?", collected, ["insurance_category"])

        self.assertIn("health", answer)
        self.assertIn("motor", answer)
        self.assertNotIn("life", answer)
        self.assertNotIn("personal accident", answer)

    def test_give_me_options_answers_supported_workflows(self):
        collected = _empty_intake()
        collected["customer_type"] = "individual"
        answer = _answer_clarification(FakeClient(), "give me options", collected, ["workflow_type"])

        self.assertIn("start policy onboarding", answer)
        self.assertIn("validate claim compliance", answer)

    def test_individual_claim_details_are_requested_after_action(self):
        collected = _empty_intake()
        collected["customer_type"] = "individual"
        collected["workflow_type"] = "claim_validation"

        self.assertEqual(_missing_fields(collected), ["claim_type", "claim details", "incident description", "document file paths"])

    def test_business_details_are_requested_after_action(self):
        collected = _empty_intake()
        collected["customer_type"] = "business"
        collected["workflow_type"] = "kyb_validation"

        self.assertEqual(_missing_fields(collected), ["business details"])

    def test_business_claim_details_unlock_document_upload(self):
        collected = _empty_intake()
        collected["customer_type"] = "business"
        collected["workflow_type"] = "claim_validation"
        collected["case_type"] = "property_damage"
        collected["user_inputs"] = {
            "company_name": "Acme Manufacturing Pvt Ltd",
            "policy_number": "BUS-PROP-7788",
            "incident_date": "14/05/2026",
            "claim_amount": "450000",
        }

        self.assertEqual(_missing_fields(collected), ["incident description", "document file paths"])
        collected["incident_description"] = "Warehouse roof was damaged during heavy rain on 10 May."

        self.assertEqual(_missing_fields(collected), ["document file paths"])


if __name__ == "__main__":
    unittest.main()
