import pandas as pd

from dpcn_mapping.config import DATASET, RAW_COLUMNS
from dpcn_mapping.validate_data import load_raw_data, validate_raw_data


def test_deliverable_has_required_columns():
    frame = load_raw_data(DATASET)
    assert list(frame.columns) == list(RAW_COLUMNS)


def test_deliverable_passes_validation():
    assert validate_raw_data(load_raw_data(DATASET)) == []


def test_empty_template_is_valid():
    assert validate_raw_data(pd.DataFrame(columns=RAW_COLUMNS)) == []


def test_validation_catches_bad_values():
    row = dict(zip(RAW_COLUMNS, ["16", "University of Delhi", "A", "T", "2015", "book", "", "", "10.1/x", "-1",
                                 "Q5", "", "yes", ""]))
    errors = " ".join(validate_raw_data(pd.DataFrame([row], columns=RAW_COLUMNS)))
    for expected in ("year", "type", "quartile", "cites_indian_inst", "citations", "doi"):
        assert expected in errors


def test_latest_build_has_audit():
    import json

    from dpcn_mapping.config import BUILDS

    build_id = (BUILDS / "LATEST").read_text().strip()
    audit = json.loads((BUILDS / build_id / "audit.json").read_text())
    assert audit["build_id"] == build_id
    assert audit["B_duplicates"]["13_identical_rows_left_in_deliverable"] == 0
