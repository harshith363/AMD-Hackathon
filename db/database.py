from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path("outputs/insurance_assistant.sqlite3")


class DatabaseAgent:
    name = "Database Agent"

    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS product_recommendations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_id TEXT,
                    session_id TEXT,
                    customer_type TEXT,
                    category TEXT,
                    payload_json TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS validation_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_id TEXT,
                    session_id TEXT,
                    workflow_type TEXT,
                    customer_type TEXT,
                    case_type TEXT,
                    status TEXT,
                    payload_json TEXT,
                    markdown_report TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def save_report(self, session_id: str, report) -> None:
        payload: dict[str, Any] = report.json_report
        with self._connect() as conn:
            if report.report_type == "new_insurance":
                conn.execute(
                    """
                    INSERT INTO product_recommendations
                    (report_id, session_id, customer_type, category, payload_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        report.report_id,
                        session_id,
                        payload.get("customer_type"),
                        payload.get("category"),
                        json.dumps(payload, indent=2),
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO validation_reports
                    (report_id, session_id, workflow_type, customer_type, case_type, status, payload_json, markdown_report)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report.report_id,
                        session_id,
                        payload.get("workflow_type"),
                        payload.get("customer_type"),
                        payload.get("case_type"),
                        payload.get("status"),
                        json.dumps(payload, indent=2),
                        report.markdown_report,
                    ),
                )
