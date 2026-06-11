KYC_RULES = {
    "individual": {
        "required_documents": ["pan", "identity_proof", "address_proof", "bank_proof"],
        "field_checks": ["customer_name", "date_of_birth", "pan_number", "address", "bank_account_holder"],
        "consistency_checks": ["customer_name", "date_of_birth", "address"],
    },
    "business": {
        "required_documents": [
            "certificate_of_incorporation",
            "company_pan",
            "gst_certificate",
            "registered_address_proof",
            "board_resolution",
            "authorized_signatory_id_proof",
            "authorized_signatory_address_proof",
            "beneficial_ownership_declaration",
            "bank_account_proof",
        ],
        "field_checks": ["company_name", "pan_number", "gstin", "registered_address", "authorized_signatory", "bank_account_holder"],
        "consistency_checks": ["company_name", "pan_number", "registered_address"],
    },
}
