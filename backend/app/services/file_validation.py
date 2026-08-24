"""
RouteCare AI - Upload file validation.

Never trusts the client-supplied filename or Content-Type - both are
attacker-controlled. File type is determined by sniffing the first few
bytes against known container-format signatures, matching
docs/09_Security_Privacy_Compliance.md's "Do not trust the filename or
MIME type alone" requirement.
"""

from dataclasses import dataclass

from app.core.config import settings
from app.core.exceptions import BusinessRuleError, ValidationError

# .xlsx (and .xlsm/.docx/...) files are ZIP archives; .xls is an OLE2
# Compound File. Sniffing these signatures is what actually determines
# the file type here - the extension is only used to pick which parser
# (openpyxl vs xlrd) to hand the validated bytes to.
_XLSX_SIGNATURE = b"PK\x03\x04"
_XLS_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

_ALLOWED_EXTENSIONS = {".xlsx", ".xls"}


@dataclass
class ValidatedFile:
    content: bytes
    extension: str  # ".xlsx" or ".xls" - which parser engine to use


def _extension_of(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot != -1 else ""


def validate_upload(*, filename: str, content: bytes) -> ValidatedFile:
    """
    Raises BusinessRuleError/ValidationError with a user-facing message
    for any problem; returns the validated bytes + detected extension
    otherwise. Callers should never need to inspect `content` further
    to determine file type - this is the one place that decision is made.
    """
    if not filename or not content:
        raise ValidationError("No file was uploaded.", code="IMPORT_FILE_MISSING")

    extension = _extension_of(filename)
    if extension not in _ALLOWED_EXTENSIONS:
        raise ValidationError(
            "Unsupported file type. Please upload a .xlsx or .xls file.",
            code="IMPORT_UNSUPPORTED_FILE_TYPE",
            details={"extension": extension or None},
        )

    if len(content) > settings.IMPORT_MAX_FILE_SIZE_BYTES:
        max_mb = settings.IMPORT_MAX_FILE_SIZE_BYTES / (1024 * 1024)
        raise ValidationError(
            f"File is too large. The maximum upload size is {max_mb:.0f} MB.",
            code="IMPORT_FILE_TOO_LARGE",
        )

    if content.startswith(_XLSX_SIGNATURE):
        detected = ".xlsx"
    elif content.startswith(_XLS_SIGNATURE):
        detected = ".xls"
    else:
        raise BusinessRuleError(
            "This file doesn't look like a valid Excel file. It may be corrupted, renamed, or a "
            "different format entirely.",
            code="IMPORT_FILE_CONTENT_MISMATCH",
        )

    return ValidatedFile(content=content, extension=detected)


def scan_for_malware(content: bytes) -> bool:
    """
    Malware scanning extension point - not implemented yet.

    Per docs/09_Security_Privacy_Compliance.md section 10 ("Malware
    scanning (future)"). Always returns True (clean) today, checked
    in-memory before the file is ever written to disk. Wire a real
    scanner (e.g. ClamAV via clamd) here before accepting uploads in a
    production deployment that handles files from untrusted sources -
    this is the single call site (see import_service.upload_import) to
    change when that happens.
    """
    return True
