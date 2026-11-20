"""Journal quartile (SCImago, optionally Clarivate JCR) and conference rank (CORE) lookup.

SCImago and JCR files are exports that a person downloads in a browser (both block scripts);
see README.md. Nothing here guesses: a venue with no exact ISSN / title / acronym match gets a
blank quartile.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .config import CONFIG, resolve

QUARTILES = {"Q1", "Q2", "Q3", "Q4"}
CORE_RANKS = {"A*", "A", "B", "C"}


def norm_issn(value: str) -> str:
    return re.sub(r"[^0-9X]", "", str(value).upper())


def norm_title(value: str) -> str:
    text = re.sub(r"&", " and ", str(value).lower())
    text = re.sub(r"\bthe\b", " ", text)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text)).strip()


def to_float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


# ---------------------------------------------------------------- SCImago

@dataclass
class YearTable:
    by_issn: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_title: dict[str, dict[str, Any]] = field(default_factory=dict)


def load_scimago(folder: Path | None = None) -> dict[int, YearTable]:
    """scimagojr_YYYY.csv (semicolon separated, as exported by scimagojr.com) -> {year: table}."""
    folder = folder or resolve(CONFIG["quartile"]["scimago_dir"])
    tables: dict[int, YearTable] = {}
    for path in sorted(folder.glob("*.csv")) if folder.exists() else []:
        match = re.search(r"(19|20)\d{2}", path.name)
        if not match:
            continue
        frame = pd.read_csv(path, sep=";", dtype=str, keep_default_na=False)
        # "Cites / Doc. (2years)" in older exports, "Citations / Doc. (2years)" in newer ones
        cpd_column = next((c for c in frame.columns if re.match(r"cit\w* / doc\. \(2", c.lower())), None)
        table = YearTable()
        for row in frame.to_dict("records"):
            quartile = row.get("SJR Best Quartile", "")
            entry = {"quartile": quartile if quartile in QUARTILES else "",
                     "sjr": to_float(row.get("SJR", "")),
                     "cites_per_doc_2y": to_float(row.get(cpd_column, "")) if cpd_column else None}
            for issn in str(row.get("Issn", "")).split(","):
                issn = norm_issn(issn)
                if issn:
                    table.by_issn.setdefault(issn, entry)
            title = norm_title(row.get("Title", ""))
            if title:
                table.by_title.setdefault(title, entry)
        tables[int(match.group())] = table
    return tables


def load_scimago_areas(folder: Path | None = None) -> dict[str, set[str]]:
    """ISSN -> every SCImago subject area the venue had in any downloaded year."""
    folder = folder or resolve(CONFIG["quartile"]["scimago_dir"])
    areas: dict[str, set[str]] = {}
    for path in sorted(folder.glob("*.csv")) if folder.exists() else []:
        frame = pd.read_csv(path, sep=";", dtype=str, keep_default_na=False, usecols=["Issn", "Areas"])
        for issns, names in zip(frame["Issn"], frame["Areas"]):
            found = {name.strip() for name in names.split(";") if name.strip()}
            for issn in issns.split(","):
                if norm_issn(issn):
                    areas.setdefault(norm_issn(issn), set()).update(found)
    return areas


def candidate_years(tables: dict[int, YearTable], year: int, nearest: bool) -> list[int]:
    """The paper's own year first; then, if allowed, the other years by distance (earlier wins ties)."""
    years = [year] if year in tables else []
    if nearest:
        years += sorted((y for y in tables if y != year), key=lambda y: (abs(y - year), y))
    return years


def scimago_lookup(tables: dict[int, YearTable], issns: list[str], title: str, year: int) -> dict[str, Any]:
    """Best SCImago entry for a journal: same year first, then (if allowed) the nearest year;
    ISSN match first, then exact normalised title. Returns quartile/sjr/cites_per_doc_2y/source."""
    empty = {"quartile": "", "sjr": None, "cites_per_doc_2y": None, "source": ""}
    if not tables:
        return empty
    settings = CONFIG["quartile"]
    years = candidate_years(tables, year, settings["nearest_year_fallback"])
    keys = [norm_issn(i) for i in issns if norm_issn(i)]
    title_key = norm_title(title) if title and settings["title_fallback"] else ""
    fallback: dict[str, Any] | None = None  # an entry without a quartile (metrics only)
    for method, lookups in (("", keys), (" (title match)", [title_key] if title_key else [])):
        for y in years:
            table = tables[y].by_issn if method == "" else tables[y].by_title
            for key in lookups:
                entry = table.get(key)
                if not entry:
                    continue
                label = f"SCImago {y}" + ("" if y == year else " (nearest year)") + method
                if entry["quartile"]:
                    return {**entry, "source": label}
                fallback = fallback or {**entry, "source": label}
    return fallback or empty


# ---------------------------------------------------------------- Clarivate JCR (optional)

def load_jcr(folder: Path | None = None) -> dict[str, dict[str, Any]]:
    """JCR 'Journal Data' CSV exports -> {issn: {jif, jif_quartile, jif_year}}.

    JCR lists a journal once per category; the best (lowest) quartile is kept. Columns are found
    by name so small layout changes between JCR versions do not matter. Files with a title line
    before the header row are handled. This reader has not been tested against a real export
    in this repository (no JCR access); check the first rows of jcr_journals.csv in the output.
    """
    folder = folder or resolve(CONFIG["quartile"]["jcr_dir"])
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(folder.glob("*.csv")) if folder.exists() else []:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        header_at = next((i for i, row in enumerate(rows) if any(c.strip().lower() == "journal name" for c in row)), None)
        if header_at is None:
            continue
        header = [c.strip() for c in rows[header_at]]
        jif_col = next((i for i, c in enumerate(header) if re.fullmatch(r"(\d{4}) JIF", c)), None)
        quartile_col = next((i for i, c in enumerate(header) if c.lower() == "jif quartile"), None)
        issn_cols = [i for i, c in enumerate(header) if "issn" in c.lower()]
        if jif_col is None:
            continue
        year = int(header[jif_col][:4])
        for row in rows[header_at + 1 :]:
            if len(row) <= jif_col:
                continue
            jif = to_float(row[jif_col])
            quartile = row[quartile_col].strip() if quartile_col is not None and len(row) > quartile_col else ""
            for column in issn_cols:
                issn = norm_issn(row[column]) if len(row) > column else ""
                if len(issn) != 8:
                    continue
                current = result.get(issn)
                if current is None or year > current["jif_year"]:
                    result[issn] = {"jif": jif, "jif_quartile": quartile if quartile in QUARTILES else "", "jif_year": year}
                elif year == current["jif_year"] and quartile in QUARTILES and (
                        not current["jif_quartile"] or quartile < current["jif_quartile"]):
                    current["jif_quartile"] = quartile
    return result


def jcr_lookup(table: dict[str, dict[str, Any]], issns: list[str]) -> dict[str, Any]:
    for issn in issns:
        entry = table.get(norm_issn(issn))
        if entry:
            return entry
    return {"jif": None, "jif_quartile": "", "jif_year": None}


# ---------------------------------------------------------------- CORE

def normalise_venue(name: str) -> str:
    text = name.lower()
    text = re.sub(r"\b(19|20)\d{2}\b", " ", text)
    text = re.sub(r"\b\d+(st|nd|rd|th)\b", " ", text)
    text = re.sub(r"\b(proceedings of( the)?|ieee|acm|ieee/acm|annual)\b", " ", text)
    text = re.sub(r"\([^)]*\)", " ", text)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text)).strip()


@dataclass
class CoreTable:
    by_title: dict[str, tuple[str, str]] = field(default_factory=dict)
    by_acronym: dict[str, tuple[str, str]] = field(default_factory=dict)


def load_core(path: Path | None = None) -> CoreTable:
    path = path or resolve(CONFIG["quartile"]["core_file"])
    table = CoreTable()
    if not path.exists():
        return table
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 5 or row[4].strip() not in CORE_RANKS:
                continue
            title, acronym, rank = row[1], row[2].strip(), row[4].strip()
            table.by_title.setdefault(normalise_venue(title), (rank, title))
            if acronym:
                table.by_acronym.setdefault(acronym.lower(), (rank, title))
    return table


def core_lookup(table: CoreTable, venue: str) -> tuple[str, str]:
    """(rank, matched CORE title) by exact normalised title, whole-name acronym or a
    parenthesised acronym such as 'International Conference on X (ICX)'. No fuzzy matching."""
    if not venue:
        return "", ""
    hit = table.by_title.get(normalise_venue(venue)) or table.by_acronym.get(venue.strip().lower())
    if not hit:
        for acronym in re.findall(r"\(([A-Za-z0-9&\-]{2,15})\)", venue):
            hit = table.by_acronym.get(acronym.lower())
            if hit:
                break
    return hit or ("", "")
