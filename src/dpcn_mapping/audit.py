"""Audit a build: count every known gap and duplicate, and write review lists.

    python -m dpcn_mapping.audit              # audit the build named in data/builds/LATEST
    python -m dpcn_mapping.audit <build_id>

build_dataset runs this automatically. It reads the build's outputs, the SCImago files
and the sealed snapshot, and changes no data. It writes audit.json/audit.md to
data/builds/<build_id>/ and the review lists to data/builds/latest/ (overwritten each build):

- audit.json / audit.md: the numbered gap and duplicate list (#1-#21 in handoffs/gaps.md),
  the text-cleanup check (D-017: cells cleaned, untidy cells left), and why
  coauthor_institutes is empty plus ROR match counts (#22-#23, D-015)
- review_title_duplicates.csv: works sharing a normalised title and year (#14)
- review_affiliation_uoh.csv / review_affiliation_jnu.csv: suspect affiliations (#19, #20)
- review_split_authors.csv: ORCIDs carried by more than one OpenAlex author ID (#15)

Heuristics (regular expressions, ID lists) are in the [audit] section of config/build.toml.
"""

from __future__ import annotations

import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from .build_dataset import sha256_file, short_id
from .collect_openalex import read_jsonl
from .config import BUILDS, CONFIG, DATASET, ENRICHED, LISTS, PROCESSED, ROOT, snapshot_dir

DU = "I110166357"
AUTHOR_CAP = 5000  # OpenAlex returns at most this many authorships per work


def _scimago_presence() -> dict[int, dict[str, str]]:
    """{year: {issn: best quartile or '-'}} for every journal in the SCImago files."""
    by_year: dict[int, dict[str, str]] = {}
    for path in sorted(glob.glob(str(ROOT / CONFIG["quartile"]["scimago_dir"] / "*.csv"))):
        match = re.search(r"(20\d{2}|19\d{2})", Path(path).name)
        if not match:
            continue
        frame = pd.read_csv(path, sep=";", dtype=str, keep_default_na=False)
        mapping: dict[str, str] = {}
        for issns, quartile in zip(frame["Issn"], frame["SJR Best Quartile"]):
            for issn in str(issns).split(","):
                issn = issn.strip().replace("-", "").upper()
                if issn:
                    mapping[issn] = quartile
        by_year[int(match.group(1))] = mapping
    return by_year


def _quartile_gap_reasons(missing: pd.DataFrame) -> Counter:
    by_year = _scimago_presence()
    reasons: Counter = Counter()
    if not by_year:
        reasons["no SCImago files"] = len(missing)
        return reasons
    any_year = set().union(*(set(mapping) for mapping in by_year.values()))
    for all_issns, year in zip(missing["all_issns"], missing["year"]):
        issns = [issn.replace("-", "").upper() for issn in all_issns.split("; ") if issn]
        lookup = by_year.get(min(int(year), max(by_year)), {})
        if not issns:
            reasons["no ISSN in OpenAlex"] += 1
        elif any(issn in lookup for issn in issns):
            reasons["in SCImago that year but no quartile ('-')"] += 1
        elif any(issn in any_year for issn in issns):
            reasons["in SCImago in other years only"] += 1
        else:
            reasons["journal not in any SCImago file"] += 1
    return reasons


def _du_entry_kinds(authorships: list[dict[str, Any]], medical: set[str]) -> list[str]:
    """For each DU-affiliated authorship: 'medical', 'both' or 'other' (D-004)."""
    kinds = []
    for authorship in authorships:
        ids = [short_id(inst.get("id")) for inst in authorship.get("institutions") or []
               if DU in {short_id(item) for item in inst.get("lineage") or []}]
        if ids:
            med = any(i in medical for i in ids)
            non = any(i not in medical for i in ids)
            kinds.append("both" if med and non else "medical" if med else "other")
    return kinds


def _snapshot_checks(snapshot_id: str) -> dict[str, Any]:
    """Facts that need the raw snapshot: truncation check (D-010) and DU medical entries (D-004).

    Records are streamed and reduced immediately so memory stays low.
    """
    cache = snapshot_dir(snapshot_id)
    targets = {"I152429107", "I36893310", DU}
    medical = set(CONFIG["audit"]["du_medical_institution_ids"])
    full_kinds: dict[str, list[str]] = {}
    beyond_100 = 0
    for record in read_jsonl(cache / "full_authorships.jsonl"):
        authorships = record.get("authorships") or []
        full_kinds[short_id(record["id"])] = _du_entry_kinds(authorships, medical)
        positions = [
            index for index, authorship in enumerate(authorships)
            for inst in authorship.get("institutions") or []
            if targets & {short_id(item) for item in inst.get("lineage") or []}
        ]
        if positions and min(positions) >= 100:
            beyond_100 += 1
    totals: Counter = Counter()
    works_only_medical = 0
    for work in read_jsonl(cache / "works.jsonl"):
        work_id = short_id(work["id"])
        kinds = full_kinds[work_id] if work_id in full_kinds else _du_entry_kinds(work.get("authorships") or [], medical)
        totals.update(kinds)
        works_only_medical += "medical" in kinds and "both" not in kinds and "other" not in kinds
    return {
        "refetched_works": len(full_kinds),
        "refetched_works_first_assigned_author_beyond_position_100": beyond_100,
        "du_author_entries_only_via_medical_ids": totals["medical"],
        "du_author_entries_via_medical_and_other_du_units": totals["both"],
        "du_author_entries_via_other_du_units_only": totals["other"],
        "works_whose_du_authors_are_all_medical_college": works_only_medical,
    }


UNTIDY = (r"^\s|\s$|\s{2,}|[\n\r\t]|&(?:amp|lt|gt|quot|#\d+);"
          "|[\x00-\x1f\x7f-\x9f\u200b\u2060\ufeff\u200e\u200f\u202a-\u202e\u2066-\u2069\u00ad]")


def _formatting_checks(build_dir: Path) -> dict[str, Any]:
    """D-017: cells the build cleaned, and untidy cells left in each output (should be 0)."""
    cleanup_path = build_dir / "text_cleanup.json"
    cleaned = json.loads(cleanup_path.read_text()) if cleanup_path.exists() else "not recorded for this build"
    remaining = {}
    for path in (DATASET, ENRICHED, PROCESSED / "authors.csv"):
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        remaining[path.name] = int(sum(frame[column].str.contains(UNTIDY, regex=True).sum() for column in frame.columns))
    return {"cells_cleaned_by_build": cleaned, "untidy_cells_remaining": remaining}


def _coauthor_checks(rows: pd.DataFrame, coverage: dict[str, Any]) -> dict[str, Any]:
    """D-015: why coauthor_institutes is empty, per (paper, institution) pair, and ROR use."""
    if "coauthor_institutes_status" not in rows.columns:
        return {"22_coauthor_institutes_status": "not recorded for this build"}
    # The status depends only on the paper and the institution, so one row per pair is enough.
    pairs = rows.drop_duplicates(["openalex_work_id", "institution"])["coauthor_institutes_status"]
    shares = pairs.value_counts()
    return {
        "22_coauthor_institutes_status_pairs": {
            status: f"{count} ({100 * count / len(pairs):.1f}%)" for status, count in shares.items()},
        "23_ror_matches_used": coverage.get("ror_matches_used"),
        "23_ror_authorships_resolved": coverage.get("ror_authorships_resolved"),
        "23_ror_authorships_inside_assigned_institution": coverage.get("ror_authorships_inside_assigned_institution"),
    }


def run_audit(build_dir: Path) -> dict[str, Any]:
    LISTS.mkdir(parents=True, exist_ok=True)
    build_manifest = json.loads((build_dir / "build_manifest.json").read_text())
    coverage = json.loads((build_dir / "coverage_report.json").read_text())
    expected = build_manifest["outputs"][str(ENRICHED.relative_to(ROOT))]["sha256"]
    if sha256_file(ENRICHED) != expected:
        raise SystemExit(f"{ENRICHED.name} no longer matches build {build_manifest['build_id']}; "
                         "only the latest build can be audited (or rebuild with that build's config)")
    rows = pd.read_csv(ENRICHED, dtype=str, keep_default_na=False)
    deliverable = pd.read_csv(DATASET, dtype=str, keep_default_na=False)
    authors = pd.read_csv(PROCESSED / "authors.csv", dtype=str, keep_default_na=False)
    works = rows.drop_duplicates("openalex_work_id")
    audit_cfg = CONFIG["audit"]
    journal, conference = rows["type"] == "journal", rows["type"] == "conference"

    def count(mask: pd.Series) -> dict[str, int]:
        return {"rows": int(mask.sum()), "papers": int(rows.loc[mask, "openalex_work_id"].nunique())}

    missing_quartile = journal & (rows["quartile"] == "")
    reasons = _quartile_gap_reasons(works[(works["type"] == "journal") & (works["quartile"] == "")])
    no_core = conference & (rows["quartile"] == "")
    cs_no_core = works[(works["type"] == "conference") & (works["quartile"] == "")
                       & (works["primary_field"] == "Computer Science")]
    author_ids = set(rows["openalex_author_id"]) - {""}

    titles = works.assign(key=works["title"].str.lower().str.replace(r"[^a-z0-9]", "", regex=True))
    titles = titles[titles["key"].str.len() >= audit_cfg["title_duplicate_min_length"]]
    title_dups = titles[titles.duplicated(["key", "year"], keep=False)].copy()
    title_dups["group"] = title_dups.groupby(["key", "year"]).ngroup()
    title_dups.sort_values(["group", "openalex_work_id"])[
        ["group", "openalex_work_id", "doi", "title", "year", "journal_name", "openalex_work_type", "institution",
         "citations"]].to_csv(LISTS / "review_title_duplicates.csv", index=False)

    with_orcid = rows[rows["author_orcid"] != ""].drop_duplicates(["author_orcid", "openalex_author_id"])
    split = with_orcid[with_orcid.duplicated("author_orcid", keep=False)]
    split.sort_values("author_orcid")[["author_orcid", "openalex_author_id", "author", "institution"]].to_csv(
        LISTS / "review_split_authors.csv", index=False)

    raw = rows["raw_affiliation"].str.lower()
    uoh = rows["institution"] == "University of Hyderabad"
    uoh_suspect = uoh & ~raw.str.contains(audit_cfg["uoh_name"], regex=True) & raw.str.contains(
        audit_cfg["uoh_other"], regex=True)
    jnu_suspect = (rows["institution"] == "Jawaharlal Nehru University") & raw.str.contains(
        audit_cfg["jnu_confusable"], regex=True)
    review_columns = ["openalex_work_id", "openalex_author_id", "author", "institution", "affiliation_institution_ids",
                      "raw_affiliation", "title", "year"]
    rows.loc[uoh_suspect, review_columns].to_csv(LISTS / "review_affiliation_uoh.csv", index=False)
    rows.loc[jnu_suspect, review_columns].to_csv(LISTS / "review_affiliation_jnu.csv", index=False)

    medical_ids = set(audit_cfg["du_medical_institution_ids"])
    row_ids = rows["affiliation_institution_ids"].apply(lambda text: [i for i in text.split("; ") if i])
    du = rows["institution"] == "University of Delhi"
    du_only_medical = du & row_ids.apply(lambda ids: bool(ids) and all(i in medical_ids for i in ids))
    n_authors = pd.to_numeric(rows["n_authors"])

    result: dict[str, Any] = {
        "build_id": build_manifest["build_id"],
        "rows": len(rows),
        "papers": int(rows["openalex_work_id"].nunique()),
        "A_missing_values": {
            "1_journal_quartile_blank": {**count(missing_quartile), "papers_by_reason": dict(reasons.most_common())},
            "2_conference_core_rank_blank": {**count(no_core), "computer_science_papers": len(cs_no_core)},
            "3_doi_blank": count(rows["doi"] == ""),
            "4_journal_name_blank": count(rows["journal_name"] == ""),
            "5_issn_blank_journals": count(journal & (rows["issn"] == "")),
            "6_title_blank": count(rows["title"] == ""),
            "7_cites_indian_inst_blank_no_reference_list": count(rows["cites_indian_inst"] == ""),
            "7b_rows_with_no_reference_list": count(rows["referenced_works_count"] == "0"),
            "8_rows_without_openalex_author_id": int((rows["openalex_author_id"] == "").sum()),
            "9_author_ids_without_profile": len(author_ids - set(authors["openalex_author_id"])),
            "10_papers_without_primary_topic": int((works["primary_field"] == "").sum()),
            f"11_papers_at_{AUTHOR_CAP}_author_cap": int((pd.to_numeric(works["n_authors"]) == AUTHOR_CAP).sum()),
            "12_department_and_faculty_status": "not available from OpenAlex (D-007)",
        },
        "B_duplicates": {
            "13_identical_rows_in_build": coverage.get("identical_rows"),
            "13_identical_rows_dropped": coverage.get("identical_rows_dropped"),
            "13_identical_rows_left_in_deliverable": int(deliverable.duplicated().sum()),
            "14_title_year_duplicates": {"papers": len(title_dups), "groups": int(title_dups["group"].nunique())},
            "15_orcids_on_several_author_ids": {"orcids": int(split["author_orcid"].nunique()),
                                                "author_ids": len(split)},
            "16_merged_namesakes": "not measurable from the data; stated as a limitation",
            "17_doi_shared_by_several_works": int(works.loc[works["doi"] != "", "doi"].str.lower().duplicated().sum()),
        },
        "C_scope_and_affiliation": {
            "18_du_rows_only_via_medical_college_ids": int(du_only_medical.sum()),
            "19_uoh_rows_naming_another_institution": int(uoh_suspect.sum()),
            "20_jnu_rows_mentioning_confusable_names": int(jnu_suspect.sum()),
            "21_papers_with_at_least_100_authors": int(rows.loc[n_authors >= 100, "openalex_work_id"].nunique()),
            "21_papers_with_at_least_1000_authors": int(rows.loc[n_authors >= 1000, "openalex_work_id"].nunique()),
        },
        "snapshot_checks": _snapshot_checks(build_manifest["snapshot_id"]),
    }
    result["D_formatting"] = _formatting_checks(build_dir)
    result["E_coauthor_institutes"] = _coauthor_checks(rows, coverage)
    (build_dir / "audit.json").write_text(json.dumps(result, indent=2))
    (build_dir / "audit.md").write_text(_markdown(result))
    print(f"audit written to {build_dir.relative_to(ROOT)}/audit.md")
    return result


def _markdown(result: dict[str, Any]) -> str:
    lines = [f"# Audit of build {result['build_id']}", "",
             f"{result['rows']} rows, {result['papers']} papers. Generated by `python -m dpcn_mapping.audit`.", ""]
    for section in ("A_missing_values", "B_duplicates", "C_scope_and_affiliation", "D_formatting",
                    "E_coauthor_institutes", "snapshot_checks"):
        lines += [f"## {section.replace('_', ' ', 1)}", "", "| Item | Value |", "|---|---|"]
        for key, value in result[section].items():
            shown = ", ".join(f"{k}: {v}" for k, v in value.items()) if isinstance(value, dict) else value
            lines.append(f"| {key} | {shown} |")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    build_id = args[0] if args else (BUILDS / "LATEST").read_text().strip()
    run_audit(BUILDS / build_id)


if __name__ == "__main__":
    main()
