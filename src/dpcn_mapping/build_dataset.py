"""Build data/processed/group16_data.csv from a sealed OpenAlex snapshot.

    python -m dpcn_mapping.build_dataset

Inputs: the snapshot named by build.snapshot_id in config/build.toml (it must have a
MANIFEST.json), the SCImago, CORE and (optional) ROR match files in data/external/, and
the choices in config/build.toml. The same inputs always give the same output. Each run overwrites
the deliverable and writes data/builds/<timestamp>/ with a build manifest, a coverage
report and a diff against the previous deliverable. If validation fails, nothing is
overwritten. If the outputs are byte-identical to the latest build, no new folder is
made; the rerun is appended to that build's reproduced.log instead. 
Column rules are documented in docs/codebook.md.

One row is written per (paper, assigned institution, author affiliated with that
institution on the paper). Values that could not be collected are left blank;
nothing is imputed.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import platform
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd

from .collect_openalex import MANIFEST_NAME, OPENALEX_INSTITUTIONS, read_jsonl
from .config import (BUILDS, CONFIG, CONFIG_FILE, DATASET, END_YEAR, ENRICHED, GROUP_NUMBER, LISTS, PROCESSED, RAW_COLUMNS,
                     ROOT, START_YEAR, snapshot_dir)
from .validate_data import validate_raw_data

CORE_RANKS = {"A*", "A", "B", "C"}
TARGET_IDS = {openalex_id: name for name, (openalex_id, _) in OPENALEX_INSTITUTIONS.items()}
EXCLUDED_INSTITUTIONS = set(CONFIG["scope"]["exclude_institution_ids"])

IndianInst = tuple[str, str, frozenset[str]]  # (id, display_name, effective lineage ids)


def short_id(url: str | None) -> str:
    return (url or "").rsplit("/", 1)[-1]


def lineage_ids(institution: dict[str, Any]) -> set[str]:
    """Institution id plus its OpenAlex lineage; excluded institutions stand alone."""
    own = short_id(institution.get("id"))
    if own in EXCLUDED_INSTITUTIONS:
        return {own}
    ids = {short_id(item) for item in institution.get("lineage") or []}
    ids.add(own)
    return ids


CONFERENCE_BOOK_SERIES = {name.lower() for name in CONFIG["build"]["conference_book_series"]}


def classify(work: dict[str, Any]) -> str | None:
    work_type = work.get("type")
    source = (work.get("primary_location") or {}).get("source") or {}
    source_type = source.get("type")
    if work_type in CONFIG["build"]["conference_work_types"] or (work_type == "article" and source_type == "conference"):
        return "conference"
    # Proceedings published as book chapters (D-013).
    if work_type == "book-chapter" and (
        source_type == "conference"
        or (source_type == "book series" and (source.get("display_name") or "").lower() in CONFERENCE_BOOK_SERIES)
    ):
        return "conference"
    if work_type in CONFIG["build"]["journal_work_types"] and source_type == "journal":
        return "journal"
    return None


RorMatches = dict[str, dict[str, Any]]  # raw affiliation string -> OpenAlex institution (D-015)


def load_ror_matches() -> tuple[RorMatches, Path | None]:
    """Chosen ROR matches as {raw affiliation string: openalex_institution}, and the file used.
    Empty (feature off) when switched off, unset, or the file or its MANIFEST.json is missing."""
    settings = CONFIG.get("ror", {})
    if not settings.get("use_for_unlinked_coauthors") or not settings.get("matches_file"):
        return {}, None
    path = ROOT / settings["matches_file"]
    if not path.exists() or not (path.parent / MANIFEST_NAME).exists():
        print(f"ROR matches not used: {path.relative_to(ROOT)} or its {MANIFEST_NAME} is missing")
        return {}, None
    # Only matches a reviewer marked `yes` are used (reviews/ror_matches.csv, D-015).
    review = ROOT / settings.get("review_file", "")
    approved: set[tuple[str, str]] = set()
    if settings.get("review_file") and review.exists():
        with review.open(newline="") as handle:
            approved = {(row["affiliation"], row["openalex_id"]) for row in csv.DictReader(handle)
                        if row["decision"].strip().lower() == "yes"}
    matches = {
        record["affiliation"]: record["openalex_institution"]
        for record in read_jsonl(path)
        if record.get("status") == "matched" and record.get("openalex_institution")
        and (record["affiliation"], short_id(record["openalex_institution"].get("id"))) in approved
    }
    print(f"ROR matches used: {len(matches)} approved in {review.relative_to(ROOT) if settings.get('review_file') else '(no review file)'}")
    return matches, path


Rejections = dict[str, list[dict[str, str]]]  # work id -> rejected (author, assigned institution) links


def name_key(name: str) -> str:
    return re.sub(r"\s+", " ", INVISIBLE.sub("", html.unescape(name or ""))).strip().lower()


def load_affiliation_rejections() -> Rejections:
    """Rows a reviewer marked `no` in the affiliation review files (D-018): the author's
    affiliation on that paper is not the assigned institution."""
    names_to_ids = {name: openalex_id for openalex_id, name in TARGET_IDS.items()}
    rejections: Rejections = defaultdict(list)
    for name in CONFIG.get("reviews", {}).get("affiliation_files", []):
        path = ROOT / name
        if not path.exists():
            continue
        with path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                if row["decision"].strip().lower() == "no":
                    rejections[row["openalex_work_id"]].append({
                        "file": name, "author_id": row["openalex_author_id"].strip(), "author": row["author"],
                        "target": names_to_ids[row["institution"]], "applied": "",
                    })
    return rejections


def apply_rejections(authorships: list[dict[str, Any]], rejected: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Remove a rejected assigned-institution link from the matching authorship: its institutions
    inside that institution's lineage are dropped, so the link creates no row and counts nowhere.
    Other authors and the author's other institutions are kept (D-018)."""
    if not rejected:
        return authorships
    result = []
    for authorship in authorships or []:
        author = authorship.get("author") or {}
        targets = {
            item["target"] for item in rejected
            if (item["author_id"] and item["author_id"] == short_id(author.get("id")))
            or (not item["author_id"] and name_key(item["author"]) == name_key(author.get("display_name")))
        }
        if targets:
            kept = [inst for inst in authorship.get("institutions") or [] if not lineage_ids(inst) & targets]
            if len(kept) < len(authorship.get("institutions") or []):
                for item in rejected:
                    if item["target"] in targets:
                        item["applied"] = "yes"
            authorship = {**authorship, "institutions": kept}
        result.append(authorship)
    return result


def person_tokens(name: str) -> list[str]:
    """Name words, with "Family, Given" turned into "Given Family"."""
    name = name_key(name)
    if "," in name:
        family, given = name.split(",", 1)
        name = f"{given} {family}"
    return re.findall(r"[a-z]+", name)


def same_person(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Same author ID, or names that are variants of each other ("P. Yadav" / "Prasant Yadav",
    "Rahman, Hasibur" / "Hasibur Rahman", "Yashu Shanker" / "Yashu Shankar")."""
    if a["id"] and a["id"] == b["id"]:
        return True
    ta, tb = person_tokens(a["name"]), person_tokens(b["name"])
    if not ta or not tb:
        return False
    surname = SequenceMatcher(None, ta[-1], tb[-1]).ratio() >= 0.85 or (
        min(len(ta[-1]), len(tb[-1])) >= 4 and (ta[-1].startswith(tb[-1]) or tb[-1].startswith(ta[-1])))
    return (surname and ta[0][0] == tb[0][0]) or len(set(ta) & set(tb)) >= 2


def reviewed_title_duplicates(works: dict[str, dict[str, Any]], out_of_scope: set[str]) -> tuple[set[str], list[dict[str, Any]]]:
    """Groups a reviewer marked `yes` (same paper) in the title-duplicate review file (D-019).
    One work per group is kept: most assigned-institution authors, then the longest author list,
    then most citations, then not a repository copy, then the lowest work ID. Assigned-institution
    authors found only on a dropped copy are carried over to the kept work, so nobody is lost."""
    path = ROOT / CONFIG.get("reviews", {}).get("title_duplicates_file", "")
    if not CONFIG.get("reviews", {}).get("title_duplicates_file") or not path.exists():
        return set(), []
    groups: dict[str, set[str]] = defaultdict(set)
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row["decision"].strip().lower() == "yes" and row["openalex_work_id"] in works:
                groups[row["group"]].add(row["openalex_work_id"])
    dropped: set[str] = set()
    records: list[dict[str, Any]] = []
    for group, members in sorted(groups.items()):
        members = sorted(members - out_of_scope)
        if len(members) < 2:
            continue

        def rank(work_id: str) -> tuple:
            work = works[work_id]
            source = (work.get("primary_location") or {}).get("source") or {}
            return (-len(work["authorships"]["affiliated"]), -work["authorships"]["n_authorships"],
                    -(work.get("cited_by_count") or 0), source.get("type") == "repository", work_id)

        keep_id, *others = sorted(members, key=rank)
        kept = works[keep_id]["authorships"]
        for other_id in others:
            other = works[other_id]["authorships"]
            carried = []
            for author in other["affiliated"]:
                targets = [target for target in author["targets"] if not any(
                    target in mine["targets"] and same_person(author, mine) for mine in kept["affiliated"])]
                if targets:
                    carried.append({**author, "key": f"{other_id}:{author['key']}", "carried": True, "targets": targets,
                                    "via": {target: author["via"][target] for target in targets}})
            kept["affiliated"].extend(carried)
            known = {inst[0] for inst in kept["indian"]}
            kept["indian"].extend(inst for inst in other["indian"] if inst[0] not in known)
            dropped.add(other_id)
            records.append({"group": group, "kept_work_id": keep_id, "dropped_work_id": other_id,
                            "carried_authors": len(carried), "carried_names": "; ".join(a["name"] for a in carried)})
    return dropped, records


TECH_FILTER = CONFIG.get("technical_filter", {})
NON_UNIT = re.compile(TECH_FILTER["non_unit"]) if TECH_FILTER.get("enabled") else None
KEEP_WORDS = re.compile(TECH_FILTER["keep_words"]) if TECH_FILTER.get("enabled") else None
METHOD_WORDS = re.compile(TECH_FILTER["method_words"]) if TECH_FILTER.get("enabled") else None
OWN_NAME = {  # assigned institution id -> pattern naming it in an affiliation segment
    "I152429107": re.compile(CONFIG["audit"]["jnu_name"], re.I),
    "I36893310": re.compile(CONFIG["audit"]["uoh_name"], re.I),
    "I110166357": re.compile(TECH_FILTER.get("du_name", "$^")),
}


def check_doi_review(rows: list[dict[str, str]], snapshot_dois: dict[str, str]) -> tuple[dict[str, str], dict[str, str], list[str]]:
    """Reviewed Crossref title matches (D-024). `yes` fills a blank DOI; `copy` marks the work as a copy
    of `doi_conflict_work`, which already has that DOI. `snapshot_dois` maps every snapshot work to its
    lowercased DOI ("" when blank). Returns (fills {work: DOI URL}, copies {copy: holder}, errors).
    A fill is refused when the work already has a DOI or the DOI is on another snapshot work or on
    another fill, so the build never creates a shared DOI."""
    fills: dict[str, str] = {}
    copies: dict[str, str] = {}
    errors: list[str] = []
    holders = {doi: work_id for work_id, doi in sorted(snapshot_dois.items()) if doi}
    for row in rows:
        decision = row["decision"].strip().lower()
        work_id, doi = row["openalex_work_id"].strip(), row["candidate_doi"].strip().lower()
        if decision not in ("yes", "copy"):
            continue
        if work_id not in snapshot_dois:
            errors.append(f"{work_id}: not in the snapshot")
        elif snapshot_dois[work_id]:
            errors.append(f"{work_id}: already has DOI {snapshot_dois[work_id]}")
        elif work_id in fills or work_id in copies:
            errors.append(f"{work_id}: more than one `yes`/`copy` row")
        elif decision == "yes":
            if doi in holders:
                errors.append(f"{work_id}: DOI {doi} is already on {holders[doi]}")
            elif f"https://doi.org/{doi}" in fills.values():
                errors.append(f"{work_id}: DOI {doi} is filled for another work too")
            else:
                fills[work_id] = f"https://doi.org/{doi}"
        else:
            holder = row["doi_conflict_work"].strip()
            if snapshot_dois.get(holder) != doi:
                errors.append(f"{work_id}: `copy` but {holder or 'no work'} does not hold DOI {doi}")
            else:
                copies[work_id] = holder
    return fills, copies, errors


def reviewed_dois(works: dict[str, dict[str, Any]]) -> tuple[dict[str, str], dict[str, str], list[dict[str, Any]]]:
    """Fills and copies from `doi.review_file` (D-024); stops the build on any refused row. The copy
    records name the copy's assigned-institution authors not found on the kept work: they are not carried
    over (the one known case is an author OpenAlex wrongly linked on a repository copy)."""
    name = CONFIG.get("doi", {}).get("review_file")
    if not name or not (ROOT / name).exists():
        return {}, {}, []
    with (ROOT / name).open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    snapshot_dois = {work_id: clean_doi(work.get("doi") or "").lower().removeprefix("https://doi.org/")
                     for work_id, work in works.items()}
    fills, copies, errors = check_doi_review(rows, snapshot_dois)
    if errors:
        raise SystemExit(f"{name}: refused rows:\n  " + "\n  ".join(errors))
    records = []
    for copy_id, holder in sorted(copies.items()):
        kept = works[holder]["authorships"]["affiliated"]
        missing = [a["name"] for a in works[copy_id]["authorships"]["affiliated"]
                   if not any(same_person(a, mine) for mine in kept)]
        records.append({"copy_work_id": copy_id, "kept_work_id": holder, "doi": works[holder].get("doi") or "",
                        "authors_only_on_copy": "; ".join(missing)})
    return fills, copies, records


def reviewed_non_technical() -> set[str]:
    """Work IDs a reviewer judged non-technical by topic in the review file (D-023)."""
    name = CONFIG.get("reviews", {}).get("non_technical_file")
    if not name or not (ROOT / name).exists():
        return set()
    with (ROOT / name).open(newline="") as handle:
        return {row["openalex_work_id"].strip() for row in csv.DictReader(handle) if row["openalex_work_id"].strip()}


def non_technical_only(work: dict[str, Any]) -> bool:
    """True when the paper comes only from confirmed non-technical units (D-021): every author is
    from an assigned institution, every affiliation segment of every author names its own assigned
    university and a non-technical unit, and nothing technical or borderline, the primary field is in the Social Sciences domain,
    and the title names no computational or quantitative method. Anything uncertain is kept."""
    if NON_UNIT is None:
        return False
    compact = work["authorships"]
    own = [author for author in compact["affiliated"] if not author.get("carried")]
    if not own or len(own) < compact["n_authorships"]:
        return False  # an outside co-author, or an author with no assigned-institution link
    domain = (((work.get("primary_topic") or {}).get("domain")) or {}).get("display_name")
    if domain != "Social Sciences" or METHOD_WORDS.search(work.get("title") or ""):
        return False
    for author in compact["affiliated"]:
        segments = [segment for segment in author["raw_affiliation"].split(";") if segment.strip()]
        own_names = [OWN_NAME[target] for target in author["targets"]]
        if not segments or not all(NON_UNIT.search(seg) and not KEEP_WORDS.search(seg)
                                   and any(name.search(seg) for name in own_names) for seg in segments):
            return False
    return True


def person_ids(frame: pd.DataFrame) -> pd.Series:
    """`person_id` (D-020): the ORCID for author IDs a reviewer confirmed as the same person in the
    split-author review file, otherwise the OpenAlex author ID (blank when there is none)."""
    path = ROOT / CONFIG.get("reviews", {}).get("split_authors_file", "")
    yes_ids: dict[str, str] = {}
    yes_unidentified: dict[tuple[str, str, str], str] = {}
    if CONFIG.get("reviews", {}).get("split_authors_file") and path.exists():
        with path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                if row["decision"].strip().lower() != "yes":
                    continue
                if row["openalex_author_id"]:
                    yes_ids[row["openalex_author_id"]] = row["author_orcid"]
                else:
                    yes_unidentified[(row["author_orcid"], name_key(row["author"]), row["institution"])] = row["author_orcid"]

    def pick(row: pd.Series) -> str:
        author_id = row["openalex_author_id"] or ""
        if author_id:
            return yes_ids.get(author_id, author_id)
        return yes_unidentified.get((row["author_orcid"] or "", name_key(row["author"]), row["institution"]), "")

    return frame.apply(pick, axis=1) if not frame.empty else pd.Series(dtype=str)


def institutions_of(authorship: dict[str, Any], ror: RorMatches | None = None) -> tuple[list[dict[str, Any]], bool]:
    """The authorship's institutions, and whether they came from ROR. OpenAlex links come first;
    only an authorship with none is looked up by its raw affiliation strings (D-015)."""
    institutions = authorship.get("institutions") or []
    if institutions or not ror:
        return institutions, False
    found = {}
    for raw in authorship.get("raw_affiliation_strings") or []:
        if raw in ror:
            found[short_id(ror[raw].get("id"))] = ror[raw]
    return list(found.values()), bool(found)


def indian_affiliations(authorships: list[dict[str, Any]], ror: RorMatches | None = None) -> list[IndianInst]:
    """Distinct Indian (country code IN) institutions on a work."""
    found: dict[str, IndianInst] = {}
    for authorship in authorships or []:
        for inst in institutions_of(authorship, ror)[0]:
            if inst.get("country_code") == "IN":
                inst_id = short_id(inst.get("id"))
                found[inst_id] = (inst_id, inst.get("display_name") or inst_id, frozenset(lineage_ids(inst)))
    return list(found.values())


def indian_institutions(affiliations: list[IndianInst], exclude: str) -> dict[str, str]:
    """Indian institutions outside the lineage of `exclude`, as {id: display_name}."""
    return {inst_id: name for inst_id, name, lineage in affiliations if exclude not in lineage}


def coauthor_status(partners: dict[str, str], n_authors: int, n_unlinked: int, has_foreign: bool) -> str:
    """Why coauthor_institutes is filled or empty for a row (D-015); first rule that applies."""
    if partners:
        return "listed"
    if n_authors == 1:
        return "single_author"
    if n_unlinked:
        return "unknown_affiliation"  # an author has no institution, even after ROR
    if has_foreign:
        return "foreign_only"
    return "same_institution_only"  # every institution on the paper is inside the row's lineage


def load_ror_rows() -> set[tuple[str, str]]:
    """(OpenAlex author ID, raw affiliation) of reviewed ROR matches inside an assigned institution
    that were verified and approved to become rows (`ror.assigned_rows_file`, decision `yes`; D-022)."""
    name = CONFIG.get("ror", {}).get("assigned_rows_file")
    if not name or not (ROOT / name).exists():
        return set()
    with (ROOT / name).open(newline="") as handle:
        return {(row["openalex_author_id"], row["raw_affiliation"]) for row in csv.DictReader(handle)
                if row["decision"].strip().lower() == "yes"}


ROR_ROWS = load_ror_rows()


def compact_authorships(authorships: list[dict[str, Any]], ror: RorMatches | None = None) -> dict[str, Any]:
    """Keep only what the dataset needs, so the full corpus fits in memory.
    ROR matches feed the Indian-institution list and the status counts; they give an author a row
    only when listed and approved in `ror.assigned_rows_file` (D-022)."""
    n_unlinked, has_foreign, ror_resolved = 0, False, 0
    ror_assigned: list[tuple[str, str]] = []  # (raw affiliation, assigned institution id) found only by ROR
    for authorship in authorships or []:
        institutions, from_ror = institutions_of(authorship, ror)
        n_unlinked += not institutions
        has_foreign = has_foreign or any(inst.get("country_code") != "IN" for inst in institutions)
        ror_resolved += from_ror
        if from_ror:
            # Possibly one of our authors whom OpenAlex did not link: counted, never given a row.
            raw = "; ".join(authorship.get("raw_affiliation_strings") or [])
            targets = set().union(*(lineage_ids(inst) for inst in institutions)) & TARGET_IDS.keys()
            ror_assigned += [(raw, target_id) for target_id in sorted(targets)]
    affiliated = []
    for position, authorship in enumerate(authorships or []):
        hits = set()
        via: dict[str, set[str]] = defaultdict(set)  # target id -> affiliation ids that matched it
        linked = authorship.get("institutions") or []
        key = (short_id((authorship.get("author") or {}).get("id")), "; ".join(authorship.get("raw_affiliation_strings") or []))
        if not linked and ror and key in ROR_ROWS:
            linked = institutions_of(authorship, ror)[0]  # verified ROR match (D-022)
        for inst in linked:
            for target_id in lineage_ids(inst) & TARGET_IDS.keys():
                hits.add(target_id)
                via[target_id].add(short_id(inst.get("id")))
        if hits:
            author = authorship.get("author") or {}
            affiliated.append({
                "key": author.get("id") or f"pos{position}",
                "id": short_id(author.get("id")),
                "name": author.get("display_name") or "",
                "orcid": author.get("orcid") or "",
                "position": authorship.get("author_position") or "",
                "is_corresponding": authorship.get("is_corresponding"),
                "raw_affiliation": "; ".join(authorship.get("raw_affiliation_strings") or []),
                "targets": sorted(hits),
                "via": {target_id: sorted(ids) for target_id, ids in via.items()},
            })
    names = {
        inst.get("display_name")
        for authorship in authorships or []
        for inst in authorship.get("institutions") or []
        if inst.get("display_name")
    }
    return {
        "affiliated": affiliated,
        "indian": indian_affiliations(authorships, ror),
        "all_names": sorted(names),
        "n_authorships": len(authorships or []),
        "n_unlinked": n_unlinked,
        "has_foreign": has_foreign,
        "ror_resolved": ror_resolved,
        "ror_assigned": ror_assigned,
    }


def cites_flag(cites: bool, referenced_works: list[str]) -> str:
    """TRUE/FALSE, or blank when OpenAlex has no reference list and the config says so (D-008)."""
    if not referenced_works and CONFIG["flags"]["blank_cites_flag_without_references"]:
        return ""
    return "TRUE" if cites else "FALSE"


def load_scimago() -> tuple[dict[int, dict[str, str]], list[str]]:
    folder = ROOT / CONFIG["quartile"]["scimago_dir"]
    by_year: dict[int, dict[str, str]] = {}
    files = sorted(folder.glob("*.csv")) if folder.exists() else []
    for path in files:
        match = re.search(r"(20\d{2}|19\d{2})", path.name)
        if not match:
            continue
        frame = pd.read_csv(path, sep=";", dtype=str, keep_default_na=False)
        mapping: dict[str, str] = {}
        for issns, quartile in zip(frame["Issn"], frame["SJR Best Quartile"]):
            if quartile not in {"Q1", "Q2", "Q3", "Q4"}:
                continue
            for issn in str(issns).split(","):
                issn = issn.strip().replace("-", "").upper()
                if issn:
                    mapping[issn] = quartile
        by_year[int(match.group(1))] = mapping
    return by_year, [str(path.relative_to(ROOT)) for path in files]


def scimago_quartile(by_year: dict[int, dict[str, str]], issns: list[str], year: int) -> tuple[str, str]:
    if not by_year:
        return "", ""
    lookup_year: int | None = year if year in by_year else None
    if lookup_year is None and year > max(by_year) and CONFIG["quartile"]["use_latest_year_for_newer_papers"]:
        lookup_year = max(by_year)
    if lookup_year is None:
        return "", ""
    for issn in issns:
        quartile = by_year[lookup_year].get(issn.replace("-", "").upper())
        if quartile:
            return quartile, f"SCImago {lookup_year}"
    return "", ""


def normalise_venue(name: str) -> str:
    text = name.lower()
    text = re.sub(r"\b(19|20)\d{2}\b", " ", text)
    text = re.sub(r"\b\d+(st|nd|rd|th)\b", " ", text)
    text = re.sub(r"\b(proceedings of( the)?|ieee|acm|ieee/acm|annual)\b", " ", text)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_core() -> tuple[dict[str, tuple[str, str]], dict[str, tuple[str, str]]]:
    path = ROOT / CONFIG["quartile"]["core_file"]
    by_title: dict[str, tuple[str, str]] = {}
    by_acronym: dict[str, tuple[str, str]] = {}
    if not path.exists():
        return by_title, by_acronym
    with path.open(encoding="utf-8") as handle:
        for row in csv.reader(handle):
            if len(row) < 5:
                continue
            title, acronym, rank = row[1], row[2], row[4].strip()
            by_title.setdefault(normalise_venue(title), (rank, title))
            if acronym.strip():
                by_acronym.setdefault(acronym.strip().lower(), (rank, title))
    return by_title, by_acronym


TEXT_CLEANUP: dict[str, dict[str, int]] = {}  # file -> column -> cells changed (D-017)
IDENTIFIER_COLUMNS = {"doi", "orcid", "author_orcid"}
# Invisible characters removed by clean_text (D-017): C0/C1 control codes (after line breaks
# and tabs became spaces), zero-width space, word joiner, BOM, direction marks and
# embeddings, soft hyphen. Zero-width (non-)joiners U+200C/U+200D are kept: Indic scripts need them.
INVISIBLE = re.compile("[\x00-\x1f\x7f-\x9f\u200b\u2060\ufeff\u200e\u200f\u202a-\u202e\u2066-\u2069\u00ad]")


def clean_text(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    """Normalise text cells (D-017): decode HTML entities, collapse whitespace and line
    breaks to single spaces, trim the ends. Characters and wording are otherwise unchanged.
    How many cells changed per column is recorded in TEXT_CLEANUP under `name`."""
    def tidy(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        return re.sub(r"\s+", " ", INVISIBLE.sub("", re.sub(r"\s", " ", html.unescape(value)))).strip()

    def tidy_identifier(value: Any) -> Any:
        # DOIs and ORCIDs are not HTML: only remove whitespace (DOI repairs: repair_doi).
        return INVISIBLE.sub("", re.sub(r"\s+", "", value)) if isinstance(value, str) else value

    changed: dict[str, int] = {}
    for column in frame.columns:
        if frame[column].dtype == object:
            cleaned = frame[column].map(tidy_identifier if column in IDENTIFIER_COLUMNS else tidy)
            count = int((cleaned != frame[column]).sum() - (cleaned.isna() & frame[column].isna()).sum())
            if count:
                changed[column] = count
            frame[column] = cleaned
    TEXT_CLEANUP[name] = changed
    return frame


DOI_REPAIRS: list[dict[str, str]] = []  # every DOI changed by repair_doi, written per build


def clean_doi(doi: str) -> str:
    if not doi:
        return doi
    return re.sub(r"\.html?$", "", re.split(r"[\s\"<>&?#]", doi, maxsplit=1)[0])


def doi_duplicates(works: dict[str, dict[str, Any]]) -> tuple[set[str], list[dict[str, Any]]]:
    """In-scope works sharing a DOI (D-012). Keep the one with the most citations; on a tie,
    the one whose source is not a repository, then the lowest work ID. Return the IDs to drop
    and one record per work in a duplicate group."""
    groups: dict[str, list[str]] = defaultdict(list)
    for work_id, work in works.items():
        year = work.get("publication_year")
        if classify(work) and year is not None and START_YEAR <= year <= END_YEAR and work.get("doi"):
            groups[clean_doi(work["doi"]).lower()].append(work_id)
    drop: set[str] = set()
    records: list[dict[str, Any]] = []
    for doi, ids in sorted(groups.items()):
        if len(ids) < 2:
            continue

        def rank(work_id: str) -> tuple[int, bool, str]:
            source = (works[work_id].get("primary_location") or {}).get("source") or {}
            return -(works[work_id].get("cited_by_count") or 0), source.get("type") == "repository", work_id

        ordered = sorted(ids, key=rank)
        for position, work_id in enumerate(ordered):
            source = (works[work_id].get("primary_location") or {}).get("source") or {}
            records.append({"doi": doi, "openalex_work_id": work_id, "kept": position == 0,
                            "kept_work_id": ordered[0], "citations": works[work_id].get("cited_by_count"),
                            "source": source.get("display_name") or "", "source_type": source.get("type") or "",
                            "title": works[work_id].get("title") or ""})
            if position:
                drop.add(work_id)
    return drop, records


def repair_doi(doi: str, work_id: str) -> str:
    """Cut a malformed OpenAlex DOI at the first character that cannot end a DOI here
    (quote, <, &, ?, #, whitespace) and drop a trailing ".html" (D-017). Logged in DOI_REPAIRS."""
    repaired = clean_doi(doi)
    if repaired != doi:
        DOI_REPAIRS.append({"openalex_work_id": work_id, "doi_in_openalex": doi, "doi_used": repaired})
    return repaired


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 22), b""):
            digest.update(chunk)
    return digest.hexdigest()


def diff_report(previous: pd.DataFrame | None, current: pd.DataFrame) -> str:
    """Markdown summary of what changed between the previous and the new deliverable."""
    if previous is None:
        return "No previous deliverable found; nothing to compare.\n"
    previous = previous.astype(str).replace({"nan": ""})
    current = current.astype(str).replace({"nan": ""})
    lines = ["| | previous | new |", "|---|---|---|", f"| rows | {len(previous)} | {len(current)} |"]
    for name in sorted(set(previous["institution"]) | set(current["institution"])):
        lines.append(f"| rows: {name} | {(previous['institution'] == name).sum()} | {(current['institution'] == name).sum()} |")
    for column in RAW_COLUMNS:
        if column in previous.columns:
            lines.append(f"| filled `{column}` | {(previous[column] != '').sum()} | {(current[column] != '').sum()} |")
    old_rows = Counter(map(tuple, previous[list(RAW_COLUMNS)].itertuples(index=False)))
    new_rows = Counter(map(tuple, current[list(RAW_COLUMNS)].itertuples(index=False)))
    removed = sum((old_rows - new_rows).values())
    added = sum((new_rows - old_rows).values())
    lines += ["", f"Rows only in previous build: {removed}", "", f"Rows only in new build: {added}", ""]
    if not removed and not added:
        lines.append("Identical deliverable.")
    return "\n".join(lines) + "\n"


def build() -> Path:
    """Build the deliverable; return the new build folder, or the latest one when nothing changed."""
    snapshot_id = CONFIG["build"]["snapshot_id"]
    cache = snapshot_dir(snapshot_id)
    manifest_path = cache / MANIFEST_NAME
    if not manifest_path.exists():
        raise SystemExit(f"snapshot {snapshot_id} is not sealed ({manifest_path} missing); run collect_openalex manifest")
    manifest = json.loads(manifest_path.read_text())

    # ROR matches apply to the corpus works' own authorships only, not to referenced or citing works (D-015).
    ror, ror_file = load_ror_matches()
    # Reviewed wrong affiliation links are removed before anything else reads the authorships (D-018).
    rejections = load_affiliation_rejections()
    full_authorships: dict[str, dict[str, Any]] = {}
    for record in read_jsonl(cache / "full_authorships.jsonl"):
        record_id = short_id(record["id"])
        full_authorships[record_id] = compact_authorships(
            apply_rejections(record.get("authorships"), rejections.get(record_id, [])), ror)

    works: dict[str, dict[str, Any]] = {}
    for work in read_jsonl(cache / "works.jsonl"):
        work_id = short_id(work["id"])
        work["authorships"] = full_authorships.get(work_id) or compact_authorships(
            apply_rejections(work.get("authorships"), rejections.get(work_id, [])), ror)
        work["referenced_works"] = [short_id(ref) for ref in work.get("referenced_works") or []]
        works[work_id] = work
    del full_authorships
    expected_works = manifest["files"]["works.jsonl"]["unique_ids"]
    if len(works) != expected_works:
        raise SystemExit(f"works.jsonl has {len(works)} unique works but the manifest records {expected_works}")
    still_truncated = sum(1 for work in works.values() if work["authorships"]["n_authorships"] == 100)

    indian_ref_insts: dict[str, list[IndianInst]] = {}
    for ref in read_jsonl(cache / "indian_refs.jsonl"):
        indian_ref_insts[short_id(ref["id"])] = indian_affiliations(ref.get("authorships"))
    # For each corpus work: citing works that carry an Indian affiliation.
    citers_of: dict[str, dict[str, list[IndianInst]]] = defaultdict(dict)
    for citer in read_jsonl(cache / "indian_citers.jsonl"):
        citer_id = short_id(citer["id"])
        affiliations = indian_affiliations(citer.get("authorships"))
        for ref in citer.get("referenced_works") or []:
            ref_id = short_id(ref)
            if ref_id in works:
                citers_of[ref_id][citer_id] = affiliations

    scimago, scimago_files = load_scimago()
    core_by_title, core_by_acronym = load_core()
    hyper_threshold = CONFIG["hyperauthor"]["flag_threshold"]

    doi_dropped, doi_duplicate_records = doi_duplicates(works)
    if not CONFIG["dedup"]["drop_doi_duplicates"]:
        doi_dropped = set()
    out_of_scope = {work_id for work_id, work in works.items()
                    if classify(work) is None or not START_YEAR <= (work.get("publication_year") or 0) <= END_YEAR}
    title_dropped, title_duplicate_records = reviewed_title_duplicates(works, out_of_scope | doi_dropped)
    # Reviewed Crossref title matches: blank DOIs filled, DOI-less copies of other works dropped (D-024).
    doi_fills, doi_copies, doi_copy_records = reviewed_dois(works)
    doi_filled: list[dict[str, str]] = []

    rows: list[dict[str, Any]] = []
    enriched: list[dict[str, Any]] = []
    non_technical: list[dict[str, Any]] = []  # papers dropped by the technical filter (D-021, D-023)
    reviewed_dropped = reviewed_non_technical()
    excluded = Counter()
    unmatched: list[str] = []  # in scope, but no author carries an assigned-institution affiliation
    ror_resolved = 0  # authorships of included works linked to an institution only by ROR (D-015)
    ror_assigned: list[dict[str, str]] = []  # of those, matches inside an assigned institution
    for work_id, work in works.items():
        year = work.get("publication_year")
        kind = classify(work)
        source = (work.get("primary_location") or {}).get("source") or {}
        if kind is None or year is None or not START_YEAR <= year <= END_YEAR:
            excluded[(work.get("type"), source.get("type"), "out of year range" if kind else "type")] += 1
            continue
        if work_id in doi_dropped:
            excluded[(work.get("type"), source.get("type"), "duplicate DOI")] += 1
            continue
        if work_id in title_dropped:
            excluded[(work.get("type"), source.get("type"), "reviewed title duplicate")] += 1
            continue
        if work_id in doi_copies:
            excluded[(work.get("type"), source.get("type"), "reviewed copy of a work with a DOI")] += 1
            continue
        reviewed = work_id in reviewed_dropped
        if reviewed or non_technical_only(work):
            excluded[(work.get("type"), source.get("type"),
                      "reviewed non-technical" if reviewed else "non-technical units only")] += 1
            non_technical.append({"openalex_work_id": work_id, "reason": "reviewed" if reviewed else "units",
                                  "title": work.get("title") or "", "year": year,
                                  "primary_field": ((work.get("primary_topic") or {}).get("field") or {}).get("display_name", ""),
                                  "institutions": "; ".join(sorted({TARGET_IDS[t] for a in work["authorships"]["affiliated"] for t in a["targets"]})),
                                  "affiliations": " | ".join(a["raw_affiliation"] for a in work["authorships"]["affiliated"])})
            continue
        issns = [source.get("issn_l")] if source.get("issn_l") else []
        issns += [issn for issn in source.get("issn") or [] if issn not in issns]
        quartile, quartile_source = "", ""
        if kind == "journal":
            quartile, quartile_source = scimago_quartile(scimago, issns, year)
        elif source.get("display_name"):
            name = source["display_name"]
            match = core_by_title.get(normalise_venue(name)) or core_by_acronym.get(name.strip().lower())
            if match and match[0] in CORE_RANKS:
                quartile, quartile_source = match[0], f"CORE {CONFIG['quartile']['core_edition']}: {match[1]}"
        topic = work.get("primary_topic") or {}
        doi = repair_doi(work.get("doi") or "", work_id)
        if not doi and work_id in doi_fills:
            doi = doi_fills[work_id]
            doi_filled.append({"openalex_work_id": work_id, "doi": doi})
        compact = work["authorships"]
        rows_before = len(rows)
        seen: set[tuple[str, str]] = set()
        for author in compact["affiliated"]:
            for target_id in author["targets"]:
                if (author["key"], target_id) in seen:
                    continue
                seen.add((author["key"], target_id))
                partners = indian_institutions(compact["indian"], target_id)
                cites = any(
                    indian_institutions(indian_ref_insts[ref], target_id)
                    for ref in work["referenced_works"]
                    if ref in indian_ref_insts
                )
                indian_citing = sum(
                    1 for citer_affiliations in citers_of.get(work_id, {}).values()
                    if indian_institutions(citer_affiliations, target_id)
                )
                row = {
                    "group": GROUP_NUMBER,
                    "institution": TARGET_IDS[target_id],
                    "author": author["name"],
                    "title": work.get("title") or "",
                    "year": year,
                    "type": kind,
                    "journal_name": source.get("display_name") or "",
                    "issn": (source.get("issn_l") or "") if kind == "journal" else "",
                    "doi": doi,
                    "citations": work.get("cited_by_count"),
                    "quartile": quartile,
                    "coauthor_institutes": "; ".join(sorted(set(partners.values()))),
                    "cites_indian_inst": cites_flag(cites, work["referenced_works"]),
                    "cited_by_indian_inst": "TRUE" if indian_citing else "FALSE",
                }
                rows.append(row)
                enriched.append({
                    **row,
                    "openalex_work_id": work_id,
                    "openalex_author_id": author["id"],
                    "author_orcid": author["orcid"],
                    "author_position": author["position"],
                    "is_corresponding": author["is_corresponding"],
                    "raw_affiliation": author["raw_affiliation"],
                    "affiliation_institution_ids": "; ".join(author["via"][target_id]),
                    "openalex_work_type": work.get("type"),
                    "source_type": source.get("type") or "",
                    "source_id": short_id(source.get("id")),
                    "all_issns": "; ".join(issns),
                    "quartile_source": quartile_source,
                    "coauthor_institute_ids": "; ".join(sorted(partners)),
                    "coauthor_institutes_status": coauthor_status(
                        partners, compact["n_authorships"], compact["n_unlinked"], compact["has_foreign"]),
                    "all_paper_institutions": "; ".join(compact["all_names"]),
                    "n_authors": compact["n_authorships"],
                    "is_hyperauthor": compact["n_authorships"] >= hyper_threshold,
                    "indian_citing_works": indian_citing,
                    "referenced_works_count": len(work["referenced_works"]),
                    "primary_domain": (topic.get("domain") or {}).get("display_name", ""),
                    "primary_field": (topic.get("field") or {}).get("display_name", ""),
                    "primary_subfield": (topic.get("subfield") or {}).get("display_name", ""),
                    "primary_topic": topic.get("display_name", ""),
                })
        if len(rows) == rows_before:
            unmatched.append(work_id)
        else:
            ror_resolved += compact["ror_resolved"]
            ror_assigned += [{"openalex_work_id": work_id, "institution": TARGET_IDS[target_id],
                              "raw_affiliation": raw} for raw, target_id in compact["ror_assigned"]]

    # Free the in-memory corpus before building tables, so peak memory stays low.
    n_works = len(works)
    del works, citers_of, indian_ref_insts, ror
    frame = clean_text(pd.DataFrame(rows, columns=list(RAW_COLUMNS)), DATASET.name)
    del rows
    enriched_frame = clean_text(pd.DataFrame(enriched), ENRICHED.name)
    del enriched
    # Rows identical in every deliverable column (D-005). Always listed for audit; dropped
    # only when dedup.drop_identical_rows is true (the first copy of each group is kept).
    duplicate_mask = frame.astype(str).duplicated(keep=False)
    identical_audit = enriched_frame[duplicate_mask.values].assign(
        duplicate_group=frame[duplicate_mask].astype(str).apply("|".join, axis=1).factorize()[0],
        dropped=(frame[duplicate_mask].astype(str).duplicated() & CONFIG["dedup"]["drop_identical_rows"]).values,
    )
    identical_dropped = int(identical_audit["dropped"].sum())
    if CONFIG["dedup"]["drop_identical_rows"]:
        keep = ~frame.astype(str).duplicated()
        frame, enriched_frame = frame[keep], enriched_frame[keep.values]

    if not enriched_frame.empty:
        enriched_frame.insert(enriched_frame.columns.get_loc("openalex_author_id") + 1, "person_id",
                              person_ids(enriched_frame).values)

    errors = validate_raw_data(frame)
    included_works = enriched_frame["openalex_work_id"].nunique() if not enriched_frame.empty else 0
    if included_works + sum(excluded.values()) + len(unmatched) != n_works:
        errors.append(f"reconciliation: included + excluded + unmatched works != {n_works} works in snapshot")
    if errors:
        raise SystemExit("validation FAILED; deliverable not overwritten:\n  " + "\n  ".join(errors))

    author_rows = []
    for author in read_jsonl(cache / "authors.jsonl"):
        stats = author.get("summary_stats") or {}
        author_rows.append({
            "openalex_author_id": short_id(author["id"]),
            "display_name": author.get("display_name"),
            "orcid": author.get("orcid") or "",
            "h_index_all_time": stats.get("h_index"),
            "i10_index_all_time": stats.get("i10_index"),
            "works_count_all_time": author.get("works_count"),
            "cited_by_count_all_time": author.get("cited_by_count"),
            "last_known_institutions": "; ".join(
                inst.get("display_name") or "" for inst in author.get("last_known_institutions") or []
            ),
        })
    PROCESSED.mkdir(parents=True, exist_ok=True)
    clean_text(pd.DataFrame(author_rows), "authors.csv").drop_duplicates("openalex_author_id").to_csv(
        PROCESSED / "authors.csv", index=False)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    PROCESSED.mkdir(parents=True, exist_ok=True)
    new_dataset, new_enriched = DATASET.with_suffix(".new.csv"), ENRICHED.with_suffix(".new.csv")
    frame.to_csv(new_dataset, index=False)
    enriched_frame.to_csv(new_enriched, index=False)
    output_hashes = {DATASET: sha256_file(new_dataset), ENRICHED: sha256_file(new_enriched)}
    environment = {"python": platform.python_version(), "pandas": pd.__version__, "python_executable": sys.executable}
    code_hashes = {path.name: sha256_file(path) for path in sorted(Path(__file__).parent.glob("*.py"))}

    latest_dir = BUILDS / (BUILDS / "LATEST").read_text().strip() if (BUILDS / "LATEST").exists() else None
    if latest_dir and (latest_dir / "build_manifest.json").exists() and all(path.exists() for path in output_hashes):
        latest_outputs = json.loads((latest_dir / "build_manifest.json").read_text())["outputs"]
        if all(latest_outputs.get(str(path.relative_to(ROOT)), {}).get("sha256") == digest
               for path, digest in output_hashes.items()):
            # Same outputs as the latest build: record the rerun there instead of a new build folder.
            new_dataset.unlink()
            new_enriched.unlink()
            with (latest_dir / "reproduced.log").open("a") as handle:
                handle.write(json.dumps({"rerun_at": stamp, "config_sha256": sha256_file(CONFIG_FILE),
                                         "code_sha256": code_hashes, "environment": environment}) + "\n")
            if not (latest_dir / "text_cleanup.json").exists():
                # Builds made before cleanup counts were recorded: the outputs are identical,
                # so this run's counts describe that build too.
                (latest_dir / "text_cleanup.json").write_text(json.dumps(TEXT_CLEANUP, indent=2))
            print(f"no change: outputs identical to build {latest_dir.name}; rerun logged in "
                  f"{(latest_dir / 'reproduced.log').relative_to(ROOT)}, no new build folder")
            return latest_dir

    build_dir = BUILDS / stamp
    build_dir.mkdir(parents=True, exist_ok=True)
    LISTS.mkdir(parents=True, exist_ok=True)
    previous = pd.read_csv(DATASET, dtype=str, keep_default_na=False) if DATASET.exists() else None
    (build_dir / "diff.md").write_text(f"# Build {stamp} vs previous deliverable\n\n" + diff_report(previous, frame))
    new_dataset.replace(DATASET)
    new_enriched.replace(ENRICHED)
    pd.DataFrame(
        [{"openalex_work_type": t, "source_type": s, "reason": r, "works": n} for (t, s, r), n in excluded.most_common()]
    ).to_csv(LISTS / "excluded_works_summary.csv", index=False)
    (LISTS / "unmatched_works.txt").write_text("\n".join(unmatched))
    identical_audit[["duplicate_group", "dropped", "institution", "author", "openalex_author_id", "author_position",
                     "raw_affiliation", "openalex_work_id", "doi", "title", "year"]].sort_values(
        ["duplicate_group", "author_position"]).to_csv(LISTS / "identical_rows_audit.csv", index=False)


    hyper = enriched_frame["is_hyperauthor"] if not enriched_frame.empty else pd.Series(dtype=bool)
    coverage = {
        "works_in_snapshot": n_works,
        "works_included": int(included_works),
        "works_excluded": int(sum(excluded.values())),
        "works_in_scope_without_affiliated_author": len(unmatched),
        "rows": len(frame),
        "identical_rows": int(duplicate_mask.sum()),
        "identical_rows_dropped": identical_dropped,
        "rows_per_institution": frame["institution"].value_counts().to_dict(),
        "unique_authors": int(enriched_frame["openalex_author_id"].nunique()) if not enriched_frame.empty else 0,
        "rows_by_type": frame["type"].value_counts().to_dict(),
        "rows_missing_doi": int((frame["doi"] == "").sum()),
        "journal_rows_missing_issn": int(((frame["type"] == "journal") & (frame["issn"] == "")).sum()),
        "journal_rows_with_quartile": int(((frame["type"] == "journal") & (frame["quartile"] != "")).sum()),
        "conference_rows_with_core_rank": int(((frame["type"] == "conference") & (frame["quartile"] != "")).sum()),
        f"works_with_at_least_{hyper_threshold}_authors": int(enriched_frame.loc[hyper, "openalex_work_id"].nunique())
        if not enriched_frame.empty else 0,
        "works_with_possibly_truncated_authors": still_truncated,
        "ror_matches_used": ror_file is not None,
        "ror_authorships_resolved": ror_resolved,
        "non_technical_dropped": len(non_technical),
        "title_duplicates_dropped": len(title_dropped),
        "title_duplicates_authors_carried": sum(r["carried_authors"] for r in title_duplicate_records),
        "affiliation_rejections": {"listed": sum(len(v) for v in rejections.values()),
                                   "applied": sum(item["applied"] == "yes" for v in rejections.values() for item in v)},
        "ror_authorships_inside_assigned_institution": len(ror_assigned),
        "dois_filled_from_review": len(doi_filled),
        "doi_copies_dropped": len(doi_copies),
    }
    (build_dir / "coverage_report.json").write_text(json.dumps(coverage, indent=2))
    (build_dir / "text_cleanup.json").write_text(json.dumps(TEXT_CLEANUP, indent=2))
    pd.DataFrame(DOI_REPAIRS, columns=["openalex_work_id", "doi_in_openalex", "doi_used"]).to_csv(
        LISTS / "doi_repairs.csv", index=False)
    pd.DataFrame(doi_filled, columns=["openalex_work_id", "doi"]).to_csv(LISTS / "doi_filled.csv", index=False)
    pd.DataFrame(doi_copy_records, columns=["copy_work_id", "kept_work_id", "doi", "authors_only_on_copy"]).to_csv(
        LISTS / "doi_copies_dropped.csv", index=False)
    pd.DataFrame(doi_duplicate_records, columns=["doi", "openalex_work_id", "kept", "kept_work_id", "citations",
                                                 "source", "source_type", "title"]).to_csv(
        LISTS / "doi_duplicates.csv", index=False)
    pd.DataFrame(ror_assigned, columns=["openalex_work_id", "institution", "raw_affiliation"]).to_csv(
        LISTS / "ror_assigned_institution_matches.csv", index=False)
    pd.DataFrame(non_technical, columns=["openalex_work_id", "reason", "title", "year", "primary_field", "institutions",
                                         "affiliations"]).to_csv(LISTS / "non_technical_dropped.csv", index=False)
    pd.DataFrame(title_duplicate_records, columns=["group", "kept_work_id", "dropped_work_id", "carried_authors",
                                                   "carried_names"]).to_csv(LISTS / "title_duplicates_applied.csv", index=False)
    pd.DataFrame([{"openalex_work_id": work_id, **item} for work_id, items in rejections.items() for item in items],
                 columns=["openalex_work_id", "file", "author_id", "author", "target", "applied"]).to_csv(
        LISTS / "affiliation_rejections_applied.csv", index=False)

    external = [*(ROOT / CONFIG["quartile"]["scimago_dir"]).glob("*.csv"), ROOT / CONFIG["quartile"]["core_file"]]
    if ror_file is not None:
        external += [ror_file, ror_file.parent / MANIFEST_NAME]
        if CONFIG["ror"].get("review_file"):
            external.append(ROOT / CONFIG["ror"]["review_file"])
    external += [ROOT / name for name in CONFIG.get("reviews", {}).get("affiliation_files", [])]
    external += [ROOT / CONFIG["reviews"][key] for key in ("title_duplicates_file", "split_authors_file", "non_technical_file")
                 if CONFIG.get("reviews", {}).get(key)]
    if CONFIG.get("doi", {}).get("review_file"):
        external.append(ROOT / CONFIG["doi"]["review_file"])
    lists_written = sorted(path for path in LISTS.iterdir() if path.suffix in (".csv", ".txt"))
    build_manifest = {
        "build_id": stamp,
        "snapshot_id": snapshot_id,
        "snapshot_manifest_sha256": sha256_file(manifest_path),
        "config_file": str(CONFIG_FILE.relative_to(ROOT)),
        "config_sha256": sha256_file(CONFIG_FILE),
        "config": CONFIG,
        "code_sha256": code_hashes,
        "lists_dir": str(LISTS.relative_to(ROOT)),
        "lists_sha256": {path.name: sha256_file(path) for path in lists_written},
        "external_files_sha256": {str(path.relative_to(ROOT)): sha256_file(path) for path in external if path.exists()},
        "scimago_files_used": scimago_files,
        "outputs": {
            str(DATASET.relative_to(ROOT)): {"rows": len(frame), "sha256": output_hashes[DATASET]},
            str(ENRICHED.relative_to(ROOT)): {"rows": len(enriched_frame), "sha256": output_hashes[ENRICHED]},
        },
        "validation": "passed",
        "environment": environment,
    }
    (build_dir / "build_manifest.json").write_text(json.dumps(build_manifest, indent=2))
    (BUILDS / "LATEST").write_text(stamp + "\n")
    print(json.dumps(coverage, indent=2))
    print(f"build {stamp}: validation passed; see {build_dir.relative_to(ROOT)}/")
    return build_dir


def main() -> None:
    build_dir = build()  # build's large in-memory corpus is freed before the audit starts
    from .audit import run_audit  # imported here: audit imports helpers from this module
    run_audit(build_dir)


if __name__ == "__main__":
    main()
