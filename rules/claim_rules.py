CLAIM_RULES = {
    "business": {
        "property_damage": {
            "required_documents": ["claim_form", "policy_copy", "incident_report", "repair_estimate"],
            "conditional_documents": [{"document": "police_report", "condition": "theft_or_legal_case"}],
            "field_checks": ["policy_number", "incident_date", "claim_amount"],
            "consistency_checks": ["policy_number", "company_name"],
        },
        "cybersecurity": {
            "required_documents": ["claim_form", "policy_copy", "incident_report", "forensic_report", "loss_estimate"],
            "conditional_documents": [{"document": "police_report", "condition": "fraud_extortion_or_legal_case"}],
            "field_checks": ["policy_number", "incident_date", "claim_amount"],
            "consistency_checks": ["policy_number", "company_name"],
        },
    },
    "individual": {
        "health": {
            "required_documents": ["claim_form", "policy_copy", "hospital_bill", "discharge_summary"],
            "conditional_documents": [],
            "field_checks": ["policy_number", "patient_name", "claim_amount"],
            "consistency_checks": ["policy_number", "patient_name"],
        },
    },
}
