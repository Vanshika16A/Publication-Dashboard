from pathlib import Path

import pandas as pd

from .config import END_YEAR, GROUP_NUMBER, INSTITUTIONS, RAW_COLUMNS, START_YEAR

TYPES = {"journal", "conference"}
BOOLEANS = {"TRUE", "FALSE", ""}
QUARTILES = {"", "Q1", "Q2", "Q3", "Q4", "A*", "A", "B", "C"}
INVISIBLE_CHARS = "[\x00-\x1f\x7f-\x9f\u200b\u2060\ufeff\u200e\u200f\u202a-\u202e\u2066-\u2069\u00ad]"


def load_raw_data(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [column for column in RAW_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    return frame


def validate_raw_data(frame: pd.DataFrame) -> list[str]:
    """Return every schema or value problem in the deliverable dataset (empty list = valid)."""
    errors: list[str] = []
    if list(frame.columns) != list(RAW_COLUMNS):
        errors.append(f"columns must be exactly {', '.join(RAW_COLUMNS)}")
        return errors
    if frame.empty:
        return errors
    frame = frame.astype(str).replace({"nan": "", "None": ""})

    def check(mask: pd.Series, message: str) -> None:
        bad = int(mask.sum())
        if bad:
            errors.append(f"{message} ({bad} rows)")

    years = pd.to_numeric(frame["year"], errors="coerce")
    check(years.isna() | ~years.between(START_YEAR, END_YEAR), f"year must be between {START_YEAR} and {END_YEAR}")
    check(pd.to_numeric(frame["group"], errors="coerce") != GROUP_NUMBER, f"group must be {GROUP_NUMBER}")
    check(~frame["institution"].isin(INSTITUTIONS), "unknown institution")
    absent = sorted(set(INSTITUTIONS) - set(frame["institution"]))
    if absent:
        errors.append(f"institutions missing from dataset: {', '.join(absent)}")
    check(~frame["type"].isin(TYPES), "type must be journal or conference")
    check((frame["type"] == "conference") & (frame["issn"] != ""), "issn must be blank for conference rows")
    check(~frame["quartile"].isin(QUARTILES), "quartile must be Q1-Q4, A*/A/B/C or blank")
    for column in ("cites_indian_inst", "cited_by_indian_inst"):
        check(~frame[column].isin(BOOLEANS), f"{column} must be TRUE, FALSE or blank")
    citations = pd.to_numeric(frame["citations"], errors="coerce")
    check(citations.isna() | (citations < 0), "citations must be a non-negative number")
    check((frame["doi"] != "") & ~frame["doi"].str.startswith("https://doi.org/"), "doi must be a https://doi.org/ URL")
    check(frame["doi"].str.contains(r"[\s\"<>&?#]|\.html?$", regex=True),
          "doi must not contain spaces, quotes, <, >, &, ?, # or end in .html")
    check(frame["author"] == "", "author must not be blank")
    text = frame[list(RAW_COLUMNS)]
    untidy = text.apply(lambda column: (column != column.str.strip()) | column.str.contains(r"\s{2,}|[\n\r\t]", regex=True))
    check(untidy.any(axis=1), "text must have no leading/trailing, repeated or line-break whitespace")
    invisible = text.apply(lambda column: column.str.contains(INVISIBLE_CHARS, regex=True))
    check(invisible.any(axis=1), "text must have no control codes, zero-width, direction or soft-hyphen characters")
    return errors
