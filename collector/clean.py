"""Clean the built dataset (no API calls): `python -m collector clean`.

Reads output/build/group16_data_extended.csv and writes the cleaned deliverables to output/:

  1. drops papers that are not in scope or not original research
     - venue outside science/engineering according to its SCImago subject areas
     - retracted / withdrawn papers, publication notices (errata, prefaces, editorials ...)
     - venues that are abstract digests, meeting-abstract books or news (config list)
  2. drops rows whose "author" is a group, not a person
  3. tidies values: author names (footnote digits, ORCID text, stray symbols, ALL CAPS) and a
     single trailing full stop on titles
  4. removes any rows that became identical, validates, and writes the CSVs

Every dropped paper/row and every changed value is listed in output/review/ with its rule.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from .build import EXTRA_COLUMNS, GROUP, RAW_COLUMNS, name_key, validate
from .collect import Run, read_jsonl
from .config import CONFIG
from .quartiles import load_scimago_areas, norm_issn

SETTINGS = CONFIG["clean"]


# ---------------------------------------------------------------- value fixes

SYMBOLS = re.compile(r"[⧧†‡§¶*#]+")
DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", " ": " "})
ABBREVIATION_END = re.compile(r"(\b(al|sp|spp|subsp|var|vs|etc|cf|Inc|Ltd|Co|Jr|Sr|St)|\b[A-Z])\.$")


def clean_author(name: str) -> str:
    """Remove noise OpenAlex copied from the paper into the author name; leave real names alone."""
    text = name.translate(DASHES)
    text = re.sub(r"\s*\bORCID\b.*$", "", text, flags=re.I)  # "Shailesh ORCID 0000-0003-..."
    text = re.sub(r"\s*\(\d+\)\s*$", "", text)                # "Manish Kumar (50435)"
    text = re.sub(r"(?<=[a-z])\d+$", "", text)                # "Rakesh Kumar Sonker1" (footnote mark)
    text = SYMBOLS.sub("", text)
    text = re.sub(r"\s+", " ", text).strip(" ,;-")
    words = text.split(" ")
    half = len(words) // 2
    if len(words) % 2 == 0 and half and words[:half] == words[half:]:  # "Shilpi Gupta Shilpi Gupta"
        text = " ".join(words[:half])
    # Honorifics: "Dr." / "PROF." in any case, undotted only in title case ("Dr", "Ms"), because
    # an undotted "MS" / "DR" is usually initials ("MS Bhatia"). "Shri" is left: it is also a name.
    text = re.sub(r"^((?i:dr|prof|professor|mr|mrs|ms|smt)\.\s*|(Dr|Prof|Professor|Mr|Mrs|Ms|Smt)\s+)+", "", text)
    if text.isupper() and len(re.sub(r"[^A-Z]", "", text)) > 3:  # "VED PRAKASH GUPTA", not "D. K."
        text = re.sub(r"[A-Z]+", lambda m: m.group()[0] + m.group()[1:].lower(), text)
    return text or name


def clean_title(title: str) -> str:
    """Drop one trailing full stop ("... in the rat." -> "... in the rat"), but not after an
    abbreviation or initial ("et al.", "sp.", "strain B.") or an ellipsis."""
    if title.endswith(".") and not title.endswith("..") and not ABBREVIATION_END.search(title):
        return title[:-1].rstrip()
    return title


# ---------------------------------------------------------------- paper rules

def paper_rules(papers: pd.DataFrame) -> dict[str, tuple[str, str]]:
    """openalex_work_id -> (rule, detail) for every paper to drop. The first rule that matches wins."""
    drop: dict[str, tuple[str, str]] = {}
    titles = papers["title"].str.lower()
    in_scope = set(CONFIG["scope"]["include_fields"]) | set(SETTINGS["extra_venue_areas"])
    areas_of = load_scimago_areas() if SETTINGS["check_venue_areas"] else {}
    if SETTINGS["check_venue_areas"] and not areas_of:
        print("WARNING: no SCImago files, so the venue subject-area check is skipped")
    excluded_venues = {v.lower() for v in SETTINGS["exclude_venues"]}
    notices = re.compile("|".join(f"(?:{p})" for p in SETTINGS["notice_patterns"]), re.I)
    for paper, title in zip(papers.itertuples(), titles):
        rule = detail = ""
        if SETTINGS["drop_retracted"] and re.match(r"\s*(retracted|withdrawn)\b", title):
            rule, detail = "retracted or withdrawn", paper.title[:80]
        elif SETTINGS["drop_notices"] and notices.search(title.strip()):
            rule, detail = "publication notice, not a research paper", paper.title[:80]
        elif paper.journal_name.lower() in excluded_venues:
            rule, detail = "excluded venue (config clean.exclude_venues)", paper.journal_name
        elif areas_of:
            areas: set[str] = set()
            for issn in paper.all_issns.split(";"):
                areas |= areas_of.get(norm_issn(issn), set())
            if areas and not areas & in_scope:
                rule, detail = "venue outside science/engineering (SCImago areas)", "; ".join(sorted(areas))
        if rule:
            drop[paper.openalex_work_id] = (rule, detail)
    return drop


# ---------------------------------------------------------------- main

def clean(build_dir: Path, out_dir: Path, run: Run) -> pd.DataFrame:
    source = build_dir / f"group{GROUP}_data_extended.csv"
    if not source.exists():
        raise SystemExit(f"{source} not found: run `python -m collector build` first")
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    review_dir = out_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"input_rows": len(frame), "input_papers": frame["openalex_work_id"].nunique(),
                              "papers_dropped": {}, "rows_dropped": {}, "values_changed": {}}

    # 1. papers
    papers = frame.drop_duplicates("openalex_work_id")
    drop = paper_rules(papers)
    dropped = papers[papers["openalex_work_id"].isin(drop)].copy()
    dropped["rule"] = dropped["openalex_work_id"].map(lambda w: drop[w][0])
    dropped["detail"] = dropped["openalex_work_id"].map(lambda w: drop[w][1])
    dropped["institutions"] = dropped["openalex_work_id"].map(
        frame.groupby("openalex_work_id")["institution"].agg(lambda s: "; ".join(sorted(set(s)))))
    dropped[["rule", "detail", "openalex_work_id", "title", "year", "type", "journal_name", "doi", "citations",
             "primary_field", "institutions"]].sort_values(["rule", "journal_name"]).to_csv(
        review_dir / "dropped_papers.csv", index=False)
    report["papers_dropped"] = dict(Counter(rule for rule, _ in drop.values()))
    frame = frame[~frame["openalex_work_id"].isin(drop)].copy()

    # 2. rows that are not a person
    group_author = frame["author"].str.contains(SETTINGS["non_person_author"], case=False, regex=True)
    frame[group_author][["institution", "author", "openalex_author_id", "openalex_work_id", "title"]].to_csv(
        review_dir / "dropped_rows_non_person.csv", index=False)
    report["rows_dropped"]["author is a group, not a person"] = int(group_author.sum())
    frame = frame[~group_author].copy()

    # 3. value fixes (each distinct change listed once)
    changes = []
    for column, fix in (("author", clean_author), ("title", clean_title)):
        fixed = frame[column].map(fix)
        changed = fixed != frame[column]
        report["values_changed"][column] = int(changed.sum())
        for before, after in sorted(set(zip(frame.loc[changed, column], fixed[changed]))):
            changes.append({"column": column, "before": before, "after": after})
        frame[column] = fixed
    pd.DataFrame(changes, columns=["column", "before", "after"]).to_csv(review_dir / "changed_values.csv", index=False)

    # 4. rows that became duplicates after the fixes (same person twice on one paper)
    frame["_key"] = [a if a else name_key(n) for a, n in zip(frame["openalex_author_id"], frame["author"])]
    before = len(frame)
    frame = frame[~frame.duplicated(["institution", "openalex_work_id", "_key"])]
    frame = frame[~frame.duplicated(RAW_COLUMNS)]
    report["rows_dropped"]["duplicate after name cleanup"] = before - len(frame)
    frame = frame.drop(columns="_key").reset_index(drop=True)

    for column in ("year", "citations", "n_authors", "indian_citing_works"):
        frame[column] = frame[column].astype(int)
    validate(frame)
    frame[RAW_COLUMNS].to_csv(out_dir / f"group{GROUP}_data.csv", index=False)
    frame[RAW_COLUMNS + [c for c in EXTRA_COLUMNS if c in frame.columns]].to_csv(
        out_dir / f"group{GROUP}_data_extended.csv", index=False)
    write_authors(frame, run, out_dir)

    papers = frame.drop_duplicates(["institution", "openalex_work_id"])
    journal = papers[papers["type"] == "journal"]
    report.update({
        "output_rows": len(frame), "output_papers": int(frame["openalex_work_id"].nunique()),
        "papers_per_institution": papers["institution"].value_counts().to_dict(),
        "journal_papers_with_quartile": f"{(journal['quartile'] != '').sum()} of {len(journal)}",
    })
    (out_dir / "cleaning_report.json").write_text(json.dumps(report, indent=2))
    (out_dir / "cleaning_report.md").write_text(report_markdown(report))
    print(report_markdown(report))
    return frame


def write_authors(frame: pd.DataFrame, run: Run, out_dir: Path) -> None:
    """One row per (institution, person): faculty-list / h-index inputs for the dashboard."""
    profiles = {r["id"]: r for r in read_jsonl(run.path("authors.jsonl"))}
    data = frame.assign(_key=[a if a else name_key(n) for a, n in zip(frame["openalex_author_id"], frame["author"])])
    records = []
    for (institution, _), group in data.groupby(["institution", "_key"], sort=True):
        papers = group.drop_duplicates("openalex_work_id")
        author_id = group["openalex_author_id"].iloc[0]
        profile = profiles.get(author_id, {})
        journals = papers[papers["type"] == "journal"]["journal_name"].replace("", pd.NA).dropna()
        records.append({
            "institution": institution, "author": group["author"].iloc[0], "openalex_author_id": author_id,
            "orcid": next((o for o in group["author_orcid"] if o), ""),
            "papers_in_dataset": len(papers), "citations_in_dataset": int(papers["citations"].sum()),
            "top_journal": journals.value_counts().index[0] if len(journals) else "",
            "main_field": papers["primary_field"].value_counts().index[0],
            "h_index_all_time": profile.get("h_index"), "i10_index_all_time": profile.get("i10_index"),
            "works_count_all_time": profile.get("works_count"),
        })
    pd.DataFrame(records).to_csv(out_dir / "authors.csv", index=False)


def report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Cleaning report", "",
             f"- in: {report['input_rows']} rows, {report['input_papers']} papers",
             f"- out: **{report['output_rows']} rows, {report['output_papers']} papers**",
             f"- papers per institution: {report['papers_per_institution']}",
             f"- journal papers with a quartile: {report['journal_papers_with_quartile']}",
             "", "## Papers dropped", ""]
    lines += [f"- {rule}: {count}" for rule, count in report["papers_dropped"].items()]
    lines += ["", "## Rows dropped", ""] + [f"- {rule}: {count}" for rule, count in report["rows_dropped"].items()]
    lines += ["", "## Values changed (rows)", ""] + [f"- {c}: {n}" for c, n in report["values_changed"].items()]
    lines += ["", "Every change is listed in `review/` (dropped_papers.csv, dropped_rows_non_person.csv, "
              "changed_values.csv).", ""]
    return "\n".join(lines)
