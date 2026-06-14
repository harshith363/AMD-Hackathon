import unittest
from pathlib import Path

from orchestrator.workflow import WorkflowOrchestrator
from schemas.messages import DocumentPacketMessage


def _packet(
    orchestrator: WorkflowOrchestrator,
    customer_type: str,
    workflow_type: str,
    case_type: str,
    folder: str,
    **kwargs,
) -> DocumentPacketMessage:
    paths = sorted(str(path) for path in Path(folder).glob("*.txt"))
    return DocumentPacketMessage(
        session_id=orchestrator.new_session_id(),
        customer_type=customer_type,
        workflow_type=workflow_type,
        case_type=case_type,
        file_paths=paths,
        **kwargs,
    )


class WorkflowTests(unittest.TestCase):
    def test_business_property_claim_missing_repair_estimate(self):
        orchestrator = WorkflowOrchestrator()
        report = orchestrator.run_document_validation(
            _packet(orchestrator, "business", "claim_validation", "property_damage", "sample_data/business_property_claim")
        )
        self.assertEqual(report.json_report["status"], "Needs Additional Documents")
        self.assertIn("repair_estimate", report.json_report["missing_documents"])

    def test_business_kyb_missing_beneficial_ownership_only(self):
        orchestrator = WorkflowOrchestrator()
        report = orchestrator.run_document_validation(
            _packet(orchestrator, "business", "kyb_validation", "kyb", "sample_data/business_kyb")
        )
        self.assertEqual(report.json_report["status"], "Needs Additional Documents")
        self.assertEqual(report.json_report["missing_documents"], ["beneficial_ownership_declaration"])

    def test_individual_kyc_name_mismatch(self):
        orchestrator = WorkflowOrchestrator()
        report = orchestrator.run_document_validation(
            _packet(orchestrator, "individual", "kyc_validation", "kyc", "sample_data/individual_kyc_mismatch")
        )
        self.assertIn(report.json_report["status"], {"Needs Correction", "Human Review Required"})
        self.assertTrue(any("customer_name mismatch" in issue["message"] for issue in report.json_report["validation_issues"]))

    def test_individual_claim_requires_incident_description(self):
        orchestrator = WorkflowOrchestrator()
        report = orchestrator.run_document_validation(
            _packet(orchestrator, "individual", "claim_validation", "health", "sample_data/individual_health_claim")
        )
        self.assertTrue(
            any(issue["field"] == "incident_description" for issue in report.json_report["validation_issues"])
        )

    def test_individual_kyc_checks_user_detail_consistency(self):
        orchestrator = WorkflowOrchestrator()
        report = orchestrator.run_document_validation(
            _packet(
                orchestrator,
                "individual",
                "kyc_validation",
                "kyc",
                "sample_data/individual_kyc_mismatch",
                user_inputs={"address": "221B Baker Street, London"},
            )
        )
        self.assertTrue(any(issue.get("field") == "address" for issue in report.json_report["validation_issues"]))


if __name__ == "__main__":
    unittest.main()
