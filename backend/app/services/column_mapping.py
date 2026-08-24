"""
RouteCare AI - Column mapping suggestion.

TheraOffice (and every other EMR) exports patient data under different
column names, so this never hardcodes one exact spreadsheet layout.
Instead: normalize each header, match it against a curated alias list
per target field, and fall back to fuzzy matching for anything close
but not exact. The user always sees and can override the result before
anything is validated or imported.

Only fields that exist on the Patient model are offered as mapping
targets - there's deliberately no DOB target, since Patient has no such
column (it isn't a clinical record system, see app/models/patient.py).
"""

import difflib
import re
from dataclasses import dataclass, field

REQUIRED_ADDRESS_TARGETS = ("address_line_1", "city", "state", "zip_code")

OPTIONAL_TARGETS = (
    "phone",
    "email",
    "address_line_2",
    "external_patient_id",
    "visit_duration_minutes",
    "priority_level",
    "scheduling_notes",
)

ALL_TARGETS = ("first_name", "last_name", "full_name", *REQUIRED_ADDRESS_TARGETS, *OPTIONAL_TARGETS)

# Order matters for tie-breaking: earlier entries win when a header
# matches more than one field's alias list equally well.
_ALIASES: dict[str, list[str]] = {
    "external_patient_id": ["patient id", "patient number", "mrn", "chart number", "external id", "id number"],
    "first_name": ["first name", "firstname", "fname", "given name"],
    "last_name": ["last name", "lastname", "lname", "surname", "family name"],
    "full_name": ["full name", "patient name", "patient full name", "name", "client name"],
    "phone": ["phone", "phone number", "telephone", "cell", "cell phone", "mobile", "contact number"],
    "email": ["email", "email address", "e mail"],
    "address_line_1": ["address", "address 1", "address line 1", "street address", "street", "home address"],
    "address_line_2": ["address 2", "address line 2", "apt", "apartment", "suite", "unit"],
    "city": ["city", "town"],
    "state": ["state", "province"],
    "zip_code": ["zip", "zip code", "zipcode", "postal code"],
    "visit_duration_minutes": ["visit duration", "duration", "visit length", "minutes", "appointment length"],
    "priority_level": ["priority", "priority level"],
    "scheduling_notes": ["notes", "scheduling notes", "comments", "remarks"],
}

_FUZZY_THRESHOLD = 0.75


def _normalize(header: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", header.strip().lower())
    return re.sub(r"\s+", " ", normalized).strip()


@dataclass
class MappingSuggestion:
    mapping: dict[str, str] = field(default_factory=dict)  # target_field -> original header
    unmapped_headers: list[str] = field(default_factory=list)


def suggest_mapping(headers: list[str]) -> MappingSuggestion:
    normalized_headers = {header: _normalize(header) for header in headers}
    used_headers: set[str] = set()
    mapping: dict[str, str] = {}

    # Pass 1: exact alias matches, in target-priority order.
    for target in ALL_TARGETS:
        for header, normalized in normalized_headers.items():
            if header in used_headers:
                continue
            if normalized in _ALIASES.get(target, []):
                mapping[target] = header
                used_headers.add(header)
                break

    # Pass 2: fuzzy matches for anything still unmapped.
    for target in ALL_TARGETS:
        if target in mapping:
            continue
        best_header: str | None = None
        best_score = 0.0
        for header, normalized in normalized_headers.items():
            if header in used_headers:
                continue
            for alias in _ALIASES.get(target, []):
                score = difflib.SequenceMatcher(None, normalized, alias).ratio()
                if score > best_score:
                    best_score = score
                    best_header = header
        if best_header is not None and best_score >= _FUZZY_THRESHOLD:
            mapping[target] = best_header
            used_headers.add(best_header)

    # first_name/last_name and full_name are alternatives - don't
    # suggest both if the sheet plausibly has just one naming scheme.
    if "full_name" in mapping and "first_name" in mapping and "last_name" in mapping:
        del mapping["full_name"]

    unmapped = [h for h in headers if h not in used_headers]
    return MappingSuggestion(mapping=mapping, unmapped_headers=unmapped)


def validate_mapping(mapping: dict[str, str], headers: list[str]) -> list[str]:
    """Returns a list of human-readable problems with a user-submitted mapping. Empty list = valid."""
    problems: list[str] = []
    unknown_targets = set(mapping.keys()) - set(ALL_TARGETS)
    if unknown_targets:
        problems.append(f"Unknown field(s): {', '.join(sorted(unknown_targets))}.")

    unknown_headers = set(mapping.values()) - set(headers)
    if unknown_headers:
        problems.append(f"Column(s) not found in the uploaded file: {', '.join(sorted(unknown_headers))}.")

    has_full_name = bool(mapping.get("full_name"))
    has_first_last = bool(mapping.get("first_name")) and bool(mapping.get("last_name"))
    if not has_full_name and not has_first_last:
        problems.append("Map either 'Full Name', or both 'First Name' and 'Last Name'.")

    for target in REQUIRED_ADDRESS_TARGETS:
        if not mapping.get(target):
            problems.append(f"'{target.replace('_', ' ').title()}' must be mapped to a column.")

    return problems


def split_full_name(full_name: str) -> tuple[str, str]:
    """Simple heuristic: first token is the first name, everything else is the last name."""
    parts = full_name.strip().split(maxsplit=1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return parts[0] if parts else "", ""
