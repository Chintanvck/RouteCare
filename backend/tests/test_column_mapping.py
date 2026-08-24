"""Tests for app.services.column_mapping."""

from app.services.column_mapping import split_full_name, suggest_mapping, validate_mapping


def test_suggests_exact_alias_matches() -> None:
    result = suggest_mapping(["First Name", "Last Name", "Phone", "Email", "Address", "City", "State", "ZIP"])
    assert result.mapping["first_name"] == "First Name"
    assert result.mapping["last_name"] == "Last Name"
    assert result.mapping["address_line_1"] == "Address"
    assert result.mapping["zip_code"] == "ZIP"


def test_suggests_full_name_when_no_split_name_columns() -> None:
    result = suggest_mapping(["Patient Full Name", "Address", "City", "State", "ZIP Code"])
    assert result.mapping["full_name"] == "Patient Full Name"
    assert "first_name" not in result.mapping


def test_prefers_first_last_over_full_name_when_both_present() -> None:
    result = suggest_mapping(["First Name", "Last Name", "Full Name", "Address", "City", "State", "ZIP"])
    assert result.mapping["first_name"] == "First Name"
    assert result.mapping["last_name"] == "Last Name"
    assert "full_name" not in result.mapping


def test_fuzzy_matches_close_but_not_exact_headers() -> None:
    result = suggest_mapping(["Frist Name", "Lsat Name", "Zip Cde"])
    assert result.mapping.get("first_name") == "Frist Name"
    assert result.mapping.get("last_name") == "Lsat Name"


def test_unrecognized_headers_left_unmapped() -> None:
    result = suggest_mapping(["First Name", "Last Name", "Favorite Color", "Shoe Size"])
    assert "Favorite Color" in result.unmapped_headers
    assert "Shoe Size" in result.unmapped_headers


def test_no_header_mapped_to_two_fields() -> None:
    result = suggest_mapping(["Name"])
    # "Name" should map to exactly one target (full_name), not be double-counted
    assert list(result.mapping.values()).count("Name") <= 1


def test_validate_mapping_accepts_full_name_scheme() -> None:
    mapping = {
        "full_name": "Patient Name",
        "address_line_1": "Address",
        "city": "City",
        "state": "State",
        "zip_code": "ZIP",
    }
    headers = ["Patient Name", "Address", "City", "State", "ZIP"]
    assert validate_mapping(mapping, headers) == []


def test_validate_mapping_accepts_first_last_scheme() -> None:
    mapping = {
        "first_name": "First",
        "last_name": "Last",
        "address_line_1": "Address",
        "city": "City",
        "state": "State",
        "zip_code": "ZIP",
    }
    headers = ["First", "Last", "Address", "City", "State", "ZIP"]
    assert validate_mapping(mapping, headers) == []


def test_validate_mapping_rejects_missing_name_scheme() -> None:
    mapping = {"address_line_1": "Address", "city": "City", "state": "State", "zip_code": "ZIP"}
    problems = validate_mapping(mapping, ["Address", "City", "State", "ZIP"])
    assert any("Full Name" in p or "First Name" in p for p in problems)


def test_validate_mapping_rejects_missing_required_address_fields() -> None:
    mapping = {"full_name": "Name"}
    problems = validate_mapping(mapping, ["Name"])
    assert len(problems) >= 4  # address_line_1, city, state, zip_code


def test_validate_mapping_rejects_column_not_in_file() -> None:
    mapping = {
        "full_name": "Name",
        "address_line_1": "Address",
        "city": "City",
        "state": "State",
        "zip_code": "Nonexistent Column",
    }
    problems = validate_mapping(mapping, ["Name", "Address", "City", "State", "ZIP"])
    assert any("Nonexistent Column" in p for p in problems)


def test_split_full_name_two_parts() -> None:
    assert split_full_name("John Smith") == ("John", "Smith")


def test_split_full_name_multiple_parts_keeps_remainder_as_last() -> None:
    assert split_full_name("John A Smith") == ("John", "A Smith")


def test_split_full_name_single_word() -> None:
    assert split_full_name("Cher") == ("Cher", "")
