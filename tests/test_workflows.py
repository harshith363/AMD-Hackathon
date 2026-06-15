import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from document_processing.intake import parse_document
from document_processing.classifier import classify_document
from document_processing.extraction import extract_fields
from agents.reconciliation import ReconciliationAgent
from agents.validation import ValidationAgent
from orchestrator.trace import WorkflowTrace
from orchestrator.workflow import WorkflowOrchestrator
from schemas.messages import ClassifiedDocumentMessage, DocumentPacketMessage, ExtractionResultMessage, ReconciliationMessage


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

    def test_kyc_extracts_camera_ocr_text_without_strict_labels(self):
        documents = [
            classify_document(
                {
                    "document_type": "unknown",
                    "confidence": 0.75,
                    "extracted_text": "INCOME TAX DEPARTMENT\nName Rohan Mehta\nDOB 05/03/1992\nAABPM 1234 C",
                }
            ),
            classify_document(
                {
                    "document_type": "unknown",
                    "confidence": 0.75,
                    "extracted_text": "Government of India\nRohan Mehta\nDate of Birth 05/03/1992\n1234 5678 9012\nAddress 77 Park Street Mumbai\nMobile 98765 43210",
                }
            ),
        ]

        extracted, _, _ = extract_fields(documents)
        canonical = extracted["canonical"]

        self.assertEqual(documents[0]["document_type"], "pan")
        self.assertEqual(documents[1]["document_type"], "identity_proof")
        self.assertEqual(canonical["pan_number"], "AABPM1234C")
        self.assertEqual(canonical["aadhaar_number"], "1234 5678 9012")
        self.assertEqual(canonical["phone_number"], "9876543210")
        self.assertEqual(canonical["date_of_birth"], "05/03/1992")

    def test_kyc_extracts_structured_vision_fields(self):
        documents = [
            {
                "document_type": "pan",
                "confidence": 0.88,
                "extracted_text": "",
                "vision_extracted_fields": {
                    "customer_name": "Rohan Mehta",
                    "pan_number": "AABPM 1234 C",
                },
            }
        ]

        extracted, evidence, _ = extract_fields(documents)

        self.assertEqual(extracted["canonical"]["customer_name"], "Rohan Mehta")
        self.assertEqual(extracted["canonical"]["pan_number"], "AABPM1234C")
        self.assertEqual(evidence["pan_number"][0]["snippet"], "vision_extracted_fields")

    def test_kyc_image_prefers_llm_parsing(self):
        with TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "camera_upload.png"
            image_path.write_bytes(b"not a real image, vision extractor is mocked")

            def fake_vision_extractor(path):
                self.assertEqual(path, image_path)
                return {
                    "document_type": "pan",
                    "fields": {
                        "customer_name": "Rahul Kumar",
                        "date_of_birth": "01/01/1990",
                        "pan_number": "ABCDE1234F",
                    },
                    "summary": "PAN card sample",
                }

            document = parse_document(
                str(image_path),
                vision_extractor=fake_vision_extractor,
                prefer_vision=True,
            )

        self.assertEqual(document["extraction_method"], "vision_llm")
        self.assertFalse(document["ocr_used"])
        self.assertEqual(document["document_type"], "pan")
        self.assertEqual(document["vision_extracted_fields"]["pan_number"], "ABCDE1234F")
        self.assertTrue(document["debug"]["vision_preferred"])

    def test_kyc_llm_nested_field_values_do_not_crash(self):
        with TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "camera_upload.png"
            image_path.write_bytes(b"not a real image, vision extractor is mocked")

            def fake_vision_extractor(_path):
                return {
                    "document_type": "pan",
                    "fields": {
                        "customer_name": {"value": "Rahul Kumar", "confidence": 0.95},
                        "pan_number": {"value": "ABCDE1234F", "confidence": 0.9},
                    },
                }

            document = parse_document(
                str(image_path),
                vision_extractor=fake_vision_extractor,
                prefer_vision=True,
            )

        extracted, _, _ = extract_fields([document])

        self.assertEqual(document["vision_extracted_fields"]["customer_name"], "Rahul Kumar")
        self.assertEqual(extracted["canonical"]["pan_number"], "ABCDE1234F")

    def test_reconciliation_normalizes_aadhaar_spacing(self):
        message = ExtractionResultMessage(
            session_id="SES-TEST",
            extracted_fields={
                "canonical": {"aadhaar_number": "1234 5678 9012"},
                "by_field": {
                    "aadhaar_number": [
                        {"value": "1234 5678 9012", "document_type": "identity_proof"},
                        {"value": "123456789012", "document_type": "identity_proof"},
                    ]
                },
            },
            evidence={},
            confidence=0.88,
        )

        reconciled = ReconciliationAgent().reconcile(message, WorkflowTrace("SES-TEST"))

        self.assertEqual(reconciled.inconsistencies, [])

    def test_kyc_user_date_accepts_iso_against_document_date(self):
        validation = ValidationAgent().validate(
            "individual",
            "kyc_validation",
            "kyc",
            ClassifiedDocumentMessage(
                session_id="SES-TEST",
                documents=[
                    {"document_type": "pan"},
                    {"document_type": "identity_proof"},
                ],
            ),
            ExtractionResultMessage(
                session_id="SES-TEST",
                extracted_fields={
                    "canonical": {
                        "customer_name": "Harshith Kumar",
                        "date_of_birth": "03/06/2003",
                        "pan_number": "ABCDE1234F",
                        "aadhaar_number": "1234 5678 9012",
                    }
                },
                evidence={},
                confidence=0.88,
            ),
            ReconciliationMessage(session_id="SES-TEST", inconsistencies=[], canonical_fields={}),
            WorkflowTrace("SES-TEST"),
            user_inputs={"name": "Harshith Kumar", "date_of_birth": "2003-06-03"},
        )

        self.assertFalse(any(issue.get("field") == "date_of_birth" for issue in validation.issues))


if __name__ == "__main__":
    unittest.main()
