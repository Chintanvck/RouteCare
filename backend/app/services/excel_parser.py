"""
RouteCare AI - Workbook parsing.

Reads the first sheet of a validated upload into plain headers + row
dicts. Everything is read as strings (dtype=str) deliberately - letting
pandas auto-infer types produces surprising results for ZIP codes
("07030" becoming 7030) and phone numbers, and downstream validation
(app.schemas.patient.PatientCreate) already knows how to parse/validate
strings.
"""

from io import BytesIO

import pandas as pd

from app.core.exceptions import BusinessRuleError


def parse_workbook(content: bytes, extension: str) -> tuple[list[str], list[dict[str, str | None]]]:
    engine = "openpyxl" if extension == ".xlsx" else "xlrd"
    try:
        frame = pd.read_excel(BytesIO(content), sheet_name=0, dtype=str, engine=engine)
    except Exception as exc:
        raise BusinessRuleError(
            "This file could not be read. It may be corrupted, password-protected, or empty.",
            code="IMPORT_FILE_UNREADABLE",
        ) from exc

    frame = frame.where(pd.notnull(frame), None)
    headers = [str(column).strip() for column in frame.columns]

    if not headers or all(header.startswith("Unnamed:") for header in headers):
        raise BusinessRuleError(
            "No column headers were found in the first row of the spreadsheet.",
            code="IMPORT_NO_HEADERS",
        )

    records: list[dict[str, str | None]] = []
    for raw_row in frame.to_dict(orient="records"):
        row: dict[str, str | None] = {}
        for header, value in raw_row.items():
            row[str(header).strip()] = value.strip() if isinstance(value, str) else value
        records.append(row)

    return headers, records
