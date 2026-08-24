"""
RouteCare AI - Duplicate detection.

Two independent checks, per Phase 3 requirements:
1. Within the uploaded file (rows compared to earlier rows in the same file)
2. Against the clinic's existing active patients

Matching never relies on name similarity alone - an exact match always
requires an exact signal (email, phone, or name+ZIP combination), and a
"probable" match always requires name similarity *plus* a corroborating
signal (same ZIP). Two people who happen to share a common name in
different parts of town are not flagged as the same person.
"""

import difflib
import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

MatchKind = Literal["EXACT", "PROBABLE"]

_NAME_SIMILARITY_THRESHOLD = 0.85


def _normalize_email(email: str | None) -> str | None:
    return email.strip().lower() if email else None


def _normalize_phone(phone: str | None) -> str | None:
    digits = re.sub(r"\D", "", phone or "")
    return digits or None


def _normalize_name(first: str | None, last: str | None) -> str:
    return f"{(first or '').strip().lower()} {(last or '').strip().lower()}".strip()


@dataclass(frozen=True)
class PatientSignature:
    patient_id: UUID
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    zip_code: str | None


@dataclass(frozen=True)
class DuplicateMatch:
    kind: MatchKind
    confidence: float
    patient_id: UUID | None = None
    row_number: int | None = None


def _exact_key_set(
    first: str | None, last: str | None, email: str | None, phone: str | None, zip_code: str | None
) -> set[str]:
    keys = set()
    norm_email = _normalize_email(email)
    norm_phone = _normalize_phone(phone)
    if norm_email:
        keys.add(f"email:{norm_email}")
    if norm_phone:
        keys.add(f"phone:{norm_phone}")
    if first and last and zip_code:
        keys.add(f"namezip:{_normalize_name(first, last)}|{zip_code.strip().lower()}")
    return keys


def match_against_existing_patients(
    *,
    first_name: str | None,
    last_name: str | None,
    email: str | None,
    phone: str | None,
    zip_code: str | None,
    existing: list[PatientSignature],
) -> DuplicateMatch | None:
    candidate_keys = _exact_key_set(first_name, last_name, email, phone, zip_code)

    for sig in existing:
        existing_keys = _exact_key_set(sig.first_name, sig.last_name, sig.email, sig.phone, sig.zip_code)
        if candidate_keys & existing_keys:
            return DuplicateMatch(kind="EXACT", confidence=100.0, patient_id=sig.patient_id)

    candidate_name = _normalize_name(first_name, last_name)
    candidate_zip = (zip_code or "").strip().lower()
    if not candidate_name or not candidate_zip:
        return None

    best: DuplicateMatch | None = None
    for sig in existing:
        if candidate_zip != (sig.zip_code or "").strip().lower():
            continue
        ratio = difflib.SequenceMatcher(None, candidate_name, _normalize_name(sig.first_name, sig.last_name)).ratio()
        if ratio >= _NAME_SIMILARITY_THRESHOLD and (best is None or ratio * 100 > best.confidence):
            best = DuplicateMatch(kind="PROBABLE", confidence=round(ratio * 100, 2), patient_id=sig.patient_id)

    return best


class WithinFileDuplicateTracker:
    """Call `check_and_register(row_number, ...)` for each row in file order. Returns the earlier
    row_number it matches, or None if this row introduces new signatures."""

    def __init__(self) -> None:
        self._seen: dict[str, int] = {}

    def check_and_register(
        self,
        row_number: int,
        *,
        first_name: str | None,
        last_name: str | None,
        email: str | None,
        phone: str | None,
        zip_code: str | None,
    ) -> int | None:
        keys = _exact_key_set(first_name, last_name, email, phone, zip_code)
        matched_row: int | None = None
        for key in keys:
            if key in self._seen:
                matched_row = self._seen[key]
                break

        for key in keys:
            self._seen.setdefault(key, row_number)

        return matched_row
