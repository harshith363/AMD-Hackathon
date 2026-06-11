CLAIM_RULES = {
    "business": {
        "property_damage": {
            "required_documents": ["claim_form", "policy_copy", "incident_report", "repair_estimate"],
            "conditional_documents": [{"document": "police_report", "condition": "theft_or_legal_case"}],
            "field_checks": ["policy_number", "incident_date", "claim_amount"],
            "consistency_checks": ["policy_number", "company_name"],
        },
        "employee_health": {
            "required_documents": ["claim_form", "policy_copy", "hospital_bill", "discharge_summary", "employee_id_proof"],
            "conditional_documents": [],
            "field_checks": ["policy_number", "patient_name", "claim_amount"],
            "consistency_checks": ["policy_number", "patient_name"],
        },
        "employee_life": {
            "required_documents": ["claim_form", "policy_copy", "death_certificate", "employee_id_proof", "nominee_id_proof"],
            "conditional_documents": [{"document": "police_report", "condition": "accidental_or_suspicious_death"}],
            "field_checks": ["policy_number", "employee_name", "date_of_death"],
            "consistency_checks": ["policy_number", "employee_name"],
        },
        "professional_liability": {
            "required_documents": ["claim_form", "policy_copy", "legal_notice", "client_contract", "incident_summary"],
            "conditional_documents": [],
            "field_checks": ["policy_number", "claim_amount", "incident_date"],
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
        "life": {
            "required_documents": ["claim_form", "policy_copy", "death_certificate", "nominee_id_proof"],
            "conditional_documents": [{"document": "police_report", "condition": "accidental_or_suspicious_death"}],
            "field_checks": ["policy_number", "insured_name", "date_of_death"],
            "consistency_checks": ["policy_number", "insured_name"],
        },
        "motor": {
            "required_documents": ["claim_form", "policy_copy", "registration_certificate", "driving_license", "repair_estimate"],
            "conditional_documents": [{"document": "police_report", "condition": "third_party_or_theft"}],
            "field_checks": ["policy_number", "vehicle_number", "incident_date", "claim_amount"],
            "consistency_checks": ["policy_number", "vehicle_number"],
        },
        "travel": {
            "required_documents": ["claim_form", "policy_copy", "ticket_or_itinerary", "expense_receipts"],
            "conditional_documents": [{"document": "medical_report", "condition": "medical_claim"}],
            "field_checks": ["policy_number", "travel_date", "claim_amount"],
            "consistency_checks": ["policy_number", "customer_name"],
        },
        "home": {
            "required_documents": ["claim_form", "policy_copy", "incident_report", "repair_estimate"],
            "conditional_documents": [{"document": "police_report", "condition": "theft_or_legal_case"}],
            "field_checks": ["policy_number", "incident_date", "claim_amount"],
            "consistency_checks": ["policy_number", "customer_name"],
        },
        "personal_accident": {
            "required_documents": ["claim_form", "policy_copy", "medical_report", "identity_proof"],
            "conditional_documents": [{"document": "police_report", "condition": "accidental_or_legal_case"}],
            "field_checks": ["policy_number", "incident_date", "insured_name"],
            "consistency_checks": ["policy_number", "insured_name"],
        },
    },
}
