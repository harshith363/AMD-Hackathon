from __future__ import annotations


BUSINESS_INSURANCE_CATEGORIES = {
    "1": "property",
    "2": "employee_life",
    "3": "employee_health",
    "4": "professional_liability",
}

INDIVIDUAL_INSURANCE_CATEGORIES = {
    "1": "health",
    "2": "life",
    "3": "motor",
    "4": "travel",
    "5": "home",
    "6": "personal_accident",
}

BUSINESS_CLAIM_TYPES = {
    "1": "property_damage",
    "2": "employee_health",
    "3": "employee_life",
    "4": "professional_liability",
}

INDIVIDUAL_CLAIM_TYPES = {
    "1": "health",
    "2": "life",
    "3": "motor",
    "4": "travel",
    "5": "home",
    "6": "personal_accident",
}


def choose(prompt: str, options: dict[str, str]) -> str:
    while True:
        print(prompt)
        for key, value in options.items():
            print(f"{key}. {value.replace('_', ' ').title()}")
        selected = input("> ").strip()
        if selected in options:
            return options[selected]
        print("Please choose a valid option.")


def collect_key_values(prompt: str) -> dict[str, str]:
    print(prompt)
    print("Enter key=value pairs. Leave blank when done.")
    values: dict[str, str] = {}
    while True:
        row = input("> ").strip()
        if not row:
            return values
        if "=" not in row:
            print("Use key=value format.")
            continue
        key, value = row.split("=", 1)
        values[key.strip()] = value.strip()


def collect_file_paths() -> list[str]:
    print("Enter document file paths, one per line. Leave blank when done.")
    paths: list[str] = []
    while True:
        row = input("> ").strip()
        if not row:
            return paths
        paths.append(row)
