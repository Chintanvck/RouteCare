"""Tests for app.services.file_validation."""

import pytest

from app.core.exceptions import AppError
from app.services.file_validation import ValidatedFile, scan_for_malware, validate_upload

XLSX_SIGNATURE = b"PK\x03\x04" + b"\x00" * 20
XLS_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 20


def test_valid_xlsx_signature_accepted() -> None:
    result = validate_upload(filename="patients.xlsx", content=XLSX_SIGNATURE)
    assert isinstance(result, ValidatedFile)
    assert result.extension == ".xlsx"


def test_valid_xls_signature_accepted() -> None:
    result = validate_upload(filename="patients.xls", content=XLS_SIGNATURE)
    assert result.extension == ".xls"


def test_rejects_unsupported_extension() -> None:
    with pytest.raises(AppError) as exc_info:
        validate_upload(filename="patients.csv", content=XLSX_SIGNATURE)
    assert exc_info.value.code == "IMPORT_UNSUPPORTED_FILE_TYPE"


def test_rejects_empty_file() -> None:
    with pytest.raises(AppError) as exc_info:
        validate_upload(filename="patients.xlsx", content=b"")
    assert exc_info.value.code == "IMPORT_FILE_MISSING"


def test_rejects_missing_filename() -> None:
    with pytest.raises(AppError) as exc_info:
        validate_upload(filename="", content=XLSX_SIGNATURE)
    assert exc_info.value.code == "IMPORT_FILE_MISSING"


def test_rejects_content_that_does_not_match_extension() -> None:
    """A .xlsx-named file whose actual bytes aren't a ZIP/OLE2 signature - renamed or corrupted."""
    with pytest.raises(AppError) as exc_info:
        validate_upload(filename="patients.xlsx", content=b"not actually an excel file, just text")
    assert exc_info.value.code == "IMPORT_FILE_CONTENT_MISMATCH"


def test_extension_never_trusted_over_content() -> None:
    """A .xls-named file whose bytes are actually a ZIP (xlsx) signature is still detected correctly."""
    result = validate_upload(filename="patients.xls", content=XLSX_SIGNATURE)
    assert result.extension == ".xlsx"


def test_rejects_oversized_file(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "IMPORT_MAX_FILE_SIZE_BYTES", 10)
    with pytest.raises(AppError) as exc_info:
        validate_upload(filename="patients.xlsx", content=XLSX_SIGNATURE)
    assert exc_info.value.code == "IMPORT_FILE_TOO_LARGE"


def test_malware_scan_extension_point_defaults_clean() -> None:
    assert scan_for_malware(b"anything") is True
