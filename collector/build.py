"""Turn the collected cache into the Group 16 dataset (no API calls).

Order of work: choose the works (type, year, science/engineering), remove duplicate works,
decide which author-institution links are backed by the author's own affiliation text, merge
split author ids, attach quartile / rank / impact-factor columns, then write the CSVs, the
review lists and a report that counts every row dropped and why.
"""

from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .collect import Run, corpus_works, read_jsonl
from .config import CONFIG, END_YEAR, GROUP, INSTITUTIONS, START_YEAR, TARGET_IDS, TARGET_NAMES
from .quartiles import (CoreTable, QUARTILES, core_lookup, jcr_lookup, load_core, load_jcr, load_scimago,
                        scimago_lookup)

RAW_COLUMNS = ["group", "institution", "author", "title", "year", "type", "journal_name", "issn", "doi",
               "citations", "quartile", "coauthor_institutes", "cites_indian_inst", "cited_by_indian_inst"]
EXTRA_COLUMNS = ["openalex_work_id", "openalex_author_id", "author_orcid", "author_position", "is_corresponding",
                 "raw_affiliation", "affiliation_status", "quartile_source", "sjr", "cites_per_doc_2y", "jif",
                 "jif_quartile", "jif_year", "oa_2yr_mean_citedness", "all_issns", "source_id", "primary_domain",
                 "primary_field", "primary_subfield", "primary_topic", "n_authors", "is_hyperauthor",
                 "indian_citing_works"]
JOURNAL_TYPES = {"article"}  # letters and reviews are excluded (also never downloaded, see config.toml)
NAME_TO_ID = {name: s["openalex_id"] for name, s in INSTITUTIONS.items()}


# ---------------------------------------------------------------- small helpers

INVISIBLE = re.compile("[\x00-\x1f\x7f-\x9f​⁠﻿‎‏‪-‮⁦-⁩­]")


def tidy(value: Any) -> Any:
    """Decode HTML entities, drop invisible characters, collapse whitespace."""
    if not isinstance(value, str):
        return value
    return re.sub(r"\s+", " ", INVISIBLE.sub("", re.sub(r"\s", " ", html.unescape(value)))).strip()


def clean_doi(doi: str) -> str:
    """OpenAlex sometimes appends junk to a DOI; cut at the first character that cannot end one."""
    if not doi:
        return ""
    return re.sub(r"\.html?$", "", re.split(r"[\s\"<>&?#]", doi, maxsplit=1)[0])


def norm_orcid(value: str) -> str:
    match = re.search(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", value or "")
    return match.group() if match else ""


def name_key(name: str) -> str:
    return "name:" + re.sub(r"[^a-z]+", " ", name.lower()).strip()


def classify(work: dict[str, Any]) -> str:
    """'journal', 'conference' or '' (excluded)."""
    source_type = work["source"]["type"]
    if work["type"] == "conference-paper":
        return "conference"
    if work["type"] in JOURNAL_TYPES:
        if source_type == "journal":
            return "journal"
        if source_type == "conference":
            return "conference"
    return ""


def canonical_institutions(insts: dict[str, list], target: str) -> list[tuple[str, str]]:
    """(id, name) of Indian institutions on a work outside `target`. An institution that belongs to
    another assigned institution (e.g. a DU college seen from JNU) is shown as that institution."""
    found: dict[str, str] = {}
    for inst_id, (name, country, lineage) in insts.items():
        if country != "IN" or target in lineage:
            continue
        other = next((t for t in lineage if t in TARGET_IDS), None)
        found[other or inst_id] = TARGET_NAMES[other] if other else name
    return sorted(found.items(), key=lambda item: item[1])


def mapped_partner(inst_id: str, name: str, lineage: list[str], target: str) -> tuple[str, str] | None:
    if target in lineage:
        return None
    other = next((t for t in lineage if t in TARGET_IDS), None)
    return (other, TARGET_NAMES[other]) if other else (inst_id, name)


# ---------------------------------------------------------------- loading

@dataclass
class Cache:
    works: dict[str, dict[str, Any]]
    profiles: dict[str, dict[str, Any]]
    sources: dict[str, dict[str, Any]]
    ref_insts: dict[str, list[list]]          # Indian work cited by ours -> [[inst id, name, lineage]]
    citers: dict[str, dict[str, Any]]         # Indian work citing ours
    citers_of: dict[str, list[str]]           # our work -> citing work ids


def load_cache(run: Run) -> Cache:
    works = corpus_works(run)
    for record in read_jsonl(run.path("full_authors.jsonl")):
        if record["id"] in works:
            works[record["id"]].update(authors=record["authors"], insts=record["insts"], n_auth=record["n_auth"])
    profiles = {r["id"]: r for r in read_jsonl(run.path("authors.jsonl"))}
    sources = {r["id"]: r for r in read_jsonl(run.path("sources.jsonl"))}
    ref_insts = {r["id"]: r["i"] for r in read_jsonl(run.path("refs.jsonl"))}
    citers = {r["id"]: r for r in read_jsonl(run.path("citers.jsonl"))}
    citers_of: dict[str, list[str]] = defaultdict(list)
    for citer_id, record in citers.items():
        for cited in record.get("c", []):
            citers_of[cited].append(citer_id)
    return Cache(works, profiles, sources, ref_insts, citers, citers_of)


# ---------------------------------------------------------------- duplicates

def pick_best(works: dict[str, dict[str, Any]], ids: list[str]) -> list[str]:
    """Order work ids best-first: most citations, then not a repository record, then lowest id."""
    return sorted(ids, key=lambda i: (-works[i]["cited_by_count"], works[i]["source"]["type"] == "repository", i))


def find_doi_duplicates(works: dict[str, dict[str, Any]]) -> tuple[set[str], list[dict]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for work_id, work in works.items():
        if work["doi"]:
            groups[clean_doi(work["doi"]).lower()].append(work_id)
    drop: set[str] = set()
    review: list[dict] = []
    for doi, ids in sorted(groups.items()):
        if len(ids) < 2:
            continue
        ordered = pick_best(works, ids)
        drop.update(ordered[1:])
        for rank, work_id in enumerate(ordered):
            review.append({"doi": doi, "openalex_work_id": work_id, "kept": rank == 0, "kept_work_id": ordered[0],
                           "citations": works[work_id]["cited_by_count"], "source": works[work_id]["source"]["name"],
                           "title": works[work_id]["title"]})
    return drop, review


def find_title_duplicates(works: dict[str, dict[str, Any]], min_length: int) -> tuple[set[str], list[dict]]:
    """Works with the same normalised title and year are duplicates only when they also share an
    affiliated author id; otherwise they are listed for review and kept."""
    groups: dict[tuple[str, Any], list[str]] = defaultdict(list)
    for work_id, work in works.items():
        key = re.sub(r"[^a-z0-9]", "", work["title"].lower())
        if len(key) >= min_length:
            groups[(key, work["year"])].append(work_id)
    drop: set[str] = set()
    review: list[dict] = []
    for (_, year), ids in sorted(groups.items(), key=lambda item: item[1][0]):
        if len(ids) < 2:
            continue
        parent = {i: i for i in ids}

        def find(i: str) -> str:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        owner: dict[str, str] = {}
        for work_id in ids:
            for author in works[work_id]["authors"]:
                if author["id"]:
                    if author["id"] in owner:
                        parent[find(work_id)] = find(owner[author["id"]])
                    else:
                        owner[author["id"]] = work_id
        clusters: dict[str, list[str]] = defaultdict(list)
        for work_id in ids:
            clusters[find(work_id)].append(work_id)
        kept_of = {}
        for members in clusters.values():
            ordered = pick_best(works, members)
            drop.update(ordered[1:])
            for work_id in members:
                kept_of[work_id] = ordered[0]
        for work_id in ids:
            review.append({"title": works[work_id]["title"], "year": year, "openalex_work_id": work_id,
                           "doi": works[work_id]["doi"], "citations": works[work_id]["cited_by_count"],
                           "source": works[work_id]["source"]["name"], "kept_work_id": kept_of[work_id],
                           "action": "kept" if kept_of[work_id] == work_id else "dropped as duplicate",
                           "cluster_size": len(clusters[find(work_id)])})
    return drop, review


# ---------------------------------------------------------------- authors

def merge_author_ids(works: dict[str, dict[str, Any]], profiles: dict[str, dict], by_orcid: bool
                     ) -> tuple[dict[str, str], dict[str, str], list[dict]]:
    """canonical id per OpenAlex author id (ids sharing an ORCID are one person), display name per
    canonical id, and a review list of merged ids."""
    orcid_of: dict[str, str] = {}
    name_of: dict[str, Counter] = defaultdict(Counter)
    for work in works.values():
        for author in work["authors"]:
            if author["id"]:
                name_of[author["id"]][author["name"]] += 1
                if norm_orcid(author["orcid"]):
                    orcid_of[author["id"]] = norm_orcid(author["orcid"])
    for author_id, profile in profiles.items():
        if norm_orcid(profile.get("orcid", "")):
            orcid_of[author_id] = norm_orcid(profile["orcid"])
    ids_of_orcid: dict[str, list[str]] = defaultdict(list)
    for author_id in name_of:
        if by_orcid and author_id in orcid_of:
            ids_of_orcid[orcid_of[author_id]].append(author_id)
    canonical = {author_id: author_id for author_id in name_of}
    review: list[dict] = []
    for orcid, ids in sorted(ids_of_orcid.items()):
        if len(ids) < 2:
            continue
        best = min(ids, key=lambda i: (-(profiles.get(i, {}).get("works_count") or 0), i))
        for author_id in ids:
            canonical[author_id] = best
            review.append({"orcid": orcid, "openalex_author_id": author_id, "merged_into": best,
                           "names": "; ".join(sorted(name_of[author_id])),
                           "works_count": profiles.get(author_id, {}).get("works_count")})
    display = {}
    for author_id in name_of:
        if canonical[author_id] == author_id:
            profile_name = profiles.get(author_id, {}).get("name")
            display[author_id] = profile_name or name_of[author_id].most_common(1)[0][0]
    return canonical, display, review


# ---------------------------------------------------------------- affiliation policy

class AffiliationRules:
    def __init__(self) -> None:
        self.mode = CONFIG["affiliation"]["unstated"]
        self.check = CONFIG["affiliation"]["check_lookalikes"]
        if self.mode not in {"drop", "flag", "keep"}:
            raise SystemExit("config affiliation.unstated must be drop, flag or keep")
        self.own = {NAME_TO_ID[n]: re.compile(s["own"], re.I) if s["own"] else None for n, s in INSTITUTIONS.items()}
        self.confusable = {NAME_TO_ID[n]: re.compile(s["confusable"], re.I) if s["confusable"] else None
                           for n, s in INSTITUTIONS.items()}

    def judge(self, target: str, strings: list[str]) -> tuple[bool, str]:
        """(keep this author-institution link?, status/reason)."""
        if self.check and strings and self.confusable[target]:
            def lookalike(text: str) -> bool:
                own = self.own[target]
                return bool(self.confusable[target].search(text)) and not (own and own.search(text))
            usable = [s for s in strings if not lookalike(s)]
            if not usable:
                return False, "affiliation text names a look-alike institution"
            strings = usable
        if not strings:
            return (self.mode != "drop"), "unstated" if self.mode != "drop" else "no affiliation text on this paper"
        return True, "stated"


# ---------------------------------------------------------------- build

def build(run: Run, out_dir: Path, require_scimago: bool = True) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    review_dir = out_dir / "review"
    review_dir.mkdir(exist_ok=True)
    cache = load_cache(run)
    report: dict[str, Any] = {"works_collected": len(cache.works), "dropped": {}}

    scimago = load_scimago()
    if not scimago:
        message = ("No SCImago files found in collector/external/scimago. Journal quartiles need them: see the "
                   "'Quartiles' section of collector/README.md (a few downloads from scimagojr.com).")
        if require_scimago:
            raise SystemExit(message + "\nTo build without journal quartiles use: --no-scimago")
        print("WARNING:", message)
    jcr = load_jcr()
    core = load_core()
    if not core.by_title:
        print("WARNING: no CORE file; conference ranks will be blank")
    report["quartile_inputs"] = {"scimago_years": sorted(scimago), "jcr_journals": len(jcr), "core_venues": len(core.by_title)}

    # 1. choose works
    include_fields = set(CONFIG["scope"]["include_fields"])
    kept: dict[str, dict[str, Any]] = {}
    reasons: Counter = Counter()
    for work_id, work in cache.works.items():
        if not work["year"] or not (run.start_year <= work["year"] <= run.end_year):
            reasons["year outside range"] += 1
        elif work["field"] not in include_fields:
            reasons["field not science/engineering"] += 1
        elif not classify(work):
            reasons["not a journal article or conference paper"] += 1
        elif not work["authors"]:
            reasons["no author at an assigned institution"] += 1
        else:
            kept[work_id] = work
    report["dropped"].update({f"works: {k}": v for k, v in reasons.items()})

    # 2. duplicate works
    if CONFIG["dedup"]["doi"]:
        drop, review = find_doi_duplicates(kept)
        pd.DataFrame(review).to_csv(review_dir / "doi_duplicates.csv", index=False)
        for work_id in drop:
            kept.pop(work_id)
        report["dropped"]["works: duplicate DOI"] = len(drop)
    if CONFIG["dedup"]["title"]:
        drop, review = find_title_duplicates(kept, CONFIG["dedup"]["title_min_length"])
        pd.DataFrame(review).to_csv(review_dir / "title_duplicates.csv", index=False)
        for work_id in drop:
            kept.pop(work_id)
        report["dropped"]["works: duplicate title+year+author"] = len(drop)

    # 3. authors
    canonical, display, split_review = merge_author_ids(kept, cache.profiles, CONFIG["dedup"]["merge_authors_by_orcid"])
    pd.DataFrame(split_review).to_csv(review_dir / "merged_authors.csv", index=False)
    report["authors_merged_by_orcid"] = sum(1 for r in split_review if r["openalex_author_id"] != r["merged_into"])

    rules = AffiliationRules()
    settings = CONFIG["quartile"]
    venue_cache: dict[tuple, dict[str, Any]] = {}

    def venue_info(work: dict[str, Any], kind: str) -> dict[str, Any]:
        key = (work["source"]["id"] or work["source"]["name"], work["year"], kind)
        if key in venue_cache:
            return venue_cache[key]
        source = work["source"]
        issns = ([source["issn_l"]] if source["issn_l"] else []) + [i for i in source["issn"] if i != source["issn_l"]]
        no_jcr = {"jif": None, "jif_quartile": "", "jif_year": None}
        info = {"quartile": "", "quartile_source": "", "sjr": None, "cites_per_doc_2y": None,
                **(jcr_lookup(jcr, issns) if kind == "journal" else no_jcr), "issns": issns}
        if kind == "conference":
            rank, matched = core_lookup(core, source["name"])
            if rank:
                info.update(quartile=rank, quartile_source=f"CORE {settings['core_source']}: {matched}")
        if not info["quartile"] and (kind == "journal" or settings["scimago_for_conference_series"]):
            found = scimago_lookup(scimago, issns, source["name"], work["year"])
            info.update(sjr=found["sjr"], cites_per_doc_2y=found["cites_per_doc_2y"])
            if found["quartile"]:
                info.update(quartile=found["quartile"], quartile_source=found["source"])
        venue_cache[key] = info
        return info

    # 4. rows
    rows: list[dict[str, Any]] = []
    dropped_affiliation: list[dict[str, Any]] = []
    threshold = CONFIG["hyperauthor"]["threshold"]
    seen: set[tuple] = set()
    for work_id in sorted(kept):
        work = kept[work_id]
        kind = classify(work)
        info = venue_info(work, kind)
        ref_hits = [cache.ref_insts[r] for r in work["refs"] if r in cache.ref_insts]
        citer_records = [cache.citers[c] for c in cache.citers_of.get(work_id, [])]
        source = work["source"]
        doi = clean_doi(work["doi"])
        for author in work["authors"]:
            author_id = author["id"]
            person = canonical.get(author_id, "") if author_id else ""
            for target in sorted(author["t"], key=lambda t: TARGET_NAMES[t]):
                keep, status = rules.judge(target, author["t"][target]["strings"])
                if not keep:
                    dropped_affiliation.append({
                        "institution": TARGET_NAMES[target], "author": author["name"], "openalex_author_id": author_id,
                        "openalex_work_id": work_id, "year": work["year"], "title": work["title"], "reason": status,
                        "raw_affiliation_all": author["raw"],
                        "raw_affiliation_for_institution": "; ".join(author["t"][target]["strings"]),
                        "institutions_openalex_assigned": "; ".join(author["t"][target]["via"])})
                    continue
                row_key = (target, work_id, person or name_key(author["name"]))
                if row_key in seen:
                    continue
                seen.add(row_key)
                partners = canonical_institutions(work["insts"], target)
                cites = any(
                    mapped_partner(i[0], i[1], i[2], target) for insts in ref_hits for i in insts)
                cited_by_count = sum(
                    1 for record in citer_records if any(mapped_partner(i[0], i[1], i[2], target) for i in record["i"]))
                rows.append({
                    "group": GROUP, "institution": TARGET_NAMES[target],
                    "author": display.get(person, author["name"]), "title": work["title"], "year": work["year"],
                    "type": kind, "journal_name": source["name"],
                    "issn": (info["issns"][0] if info["issns"] else "") if kind == "journal" else "",
                    "doi": doi, "citations": work["cited_by_count"], "quartile": info["quartile"],
                    "coauthor_institutes": "; ".join(name for _, name in partners),
                    "cites_indian_inst": "" if not work["refs"] else ("TRUE" if cites else "FALSE"),
                    "cited_by_indian_inst": "TRUE" if cited_by_count else "FALSE",
                    "openalex_work_id": work_id, "openalex_author_id": person, "author_orcid": norm_orcid(author["orcid"]),
                    "author_position": author["pos"], "is_corresponding": author["corr"],
                    "raw_affiliation": "; ".join(author["t"][target]["strings"]) or author["raw"],
                    "affiliation_status": status, "quartile_source": info["quartile_source"],
                    "sjr": info["sjr"], "cites_per_doc_2y": info["cites_per_doc_2y"], "jif": info["jif"],
                    "jif_quartile": info["jif_quartile"], "jif_year": info["jif_year"],
                    "oa_2yr_mean_citedness": cache.sources.get(source["id"], {}).get("mean_citedness_2y"),
                    "all_issns": "; ".join(info["issns"]), "source_id": source["id"],
                    "primary_domain": work["domain"], "primary_field": work["field"],
                    "primary_subfield": work["subfield"], "primary_topic": work["topic"],
                    "n_authors": work["n_auth"], "is_hyperauthor": work["n_auth"] >= threshold,
                    "indian_citing_works": cited_by_count,
                    "_partners": partners, "_author_key": person or name_key(author["name"]),
                })
    if not rows:
        raise SystemExit("No rows were produced. Did the collection finish? (python -m collector status)")

    pd.DataFrame(dropped_affiliation).to_csv(review_dir / "dropped_affiliation.csv", index=False)
    report["dropped"]["rows: " + "affiliation not backed by text / look-alike"] = len(dropped_affiliation)
    report["dropped_affiliation_by_reason"] = dict(Counter(r["reason"] for r in dropped_affiliation))

    frame = pd.DataFrame(rows)
    hidden = frame[["_partners", "_author_key"]].copy()
    frame = frame.drop(columns=["_partners", "_author_key"])
    text_columns = [c for c in frame.columns if frame[c].dtype == object and c not in {"doi", "author_orcid"}]
    for column in text_columns:
        frame[column] = frame[column].map(tidy)

    # identical rows (can only come from authors without an id appearing twice under one name)
    before = len(frame)
    keep_mask = ~frame.duplicated(subset=RAW_COLUMNS, keep="first")
    frame, hidden = frame[keep_mask].reset_index(drop=True), hidden[keep_mask].reset_index(drop=True)
    report["dropped"]["rows: identical in every required column"] = before - len(frame)

    frame = frame.sort_values(["institution", "year", "openalex_work_id", "author"], kind="stable")
    hidden = hidden.loc[frame.index].reset_index(drop=True)
    frame = frame.reset_index(drop=True)
    validate(frame)

    frame[RAW_COLUMNS].to_csv(out_dir / f"group{GROUP}_data.csv", index=False)
    frame.to_csv(out_dir / f"group{GROUP}_data_extended.csv", index=False)
    write_authors(frame, hidden, cache, out_dir)
    write_venue_review(frame, review_dir)
    report.update(summary(frame))
    (out_dir / "build_report.json").write_text(json.dumps(report, indent=2, default=str))
    (out_dir / "build_report.md").write_text(report_markdown(report))
    print(report_markdown(report))
    return {"frame": frame, "hidden": hidden, "cache": cache, "works": kept, "report": report}


# ---------------------------------------------------------------- outputs

def validate(frame: pd.DataFrame) -> None:
    problems = []
    if list(frame[RAW_COLUMNS].columns) != RAW_COLUMNS:
        problems.append("columns")
    if not frame["year"].between(START_YEAR, END_YEAR).all():
        problems.append("year outside 2016-2026")
    if not set(frame["type"]) <= {"journal", "conference"}:
        problems.append("type not journal/conference")
    allowed = QUARTILES | {"A*", "A", "B", "C", ""}
    if not set(frame["quartile"]) <= allowed:
        problems.append("unexpected quartile value")
    if set(frame["institution"]) - set(INSTITUTIONS):
        problems.append("unknown institution")
    missing = set(INSTITUTIONS) - set(frame["institution"])
    if missing:
        problems.append(f"no rows for {sorted(missing)}")
    if frame.duplicated(subset=RAW_COLUMNS).any():
        problems.append("duplicate rows")
    if frame.duplicated(subset=["institution", "openalex_work_id", "openalex_author_id", "author"]).any():
        problems.append("same author twice on one paper")
    if problems:
        raise SystemExit("validation failed: " + "; ".join(problems))


def write_authors(frame: pd.DataFrame, hidden: pd.DataFrame, cache: Cache, out_dir: Path) -> None:
    """One row per (institution, person): faculty-list / h-index inputs for the dashboard."""
    data = frame.assign(author_key=hidden["_author_key"].values)
    records = []
    for (institution, key), group in data.groupby(["institution", "author_key"], sort=True):
        papers = group.drop_duplicates("openalex_work_id")
        profile = cache.profiles.get(group["openalex_author_id"].iloc[0], {})
        journals = papers[papers["type"] == "journal"]["journal_name"].replace("", pd.NA).dropna()
        records.append({
            "institution": institution, "author": group["author"].iloc[0],
            "openalex_author_id": group["openalex_author_id"].iloc[0],
            "orcid": next((o for o in group["author_orcid"] if o), ""),
            "papers_in_dataset": len(papers), "citations_in_dataset": int(papers["citations"].sum()),
            "top_journal": journals.value_counts().index[0] if len(journals) else "",
            "main_field": papers["primary_field"].value_counts().index[0],
            "h_index_all_time": profile.get("h_index"), "i10_index_all_time": profile.get("i10_index"),
            "works_count_all_time": profile.get("works_count"),
        })
    pd.DataFrame(records).to_csv(out_dir / "authors.csv", index=False)


def write_venue_review(frame: pd.DataFrame, review_dir: Path) -> None:
    """Venues with no quartile, most papers first: the list to look up by hand in Scopus / JCR."""
    papers = frame.drop_duplicates(["institution", "openalex_work_id"])
    blank = papers[(papers["quartile"] == "") & (papers["journal_name"] != "")]
    summary_ = (blank.groupby(["type", "journal_name", "all_issns"], dropna=False)
                .agg(papers=("openalex_work_id", "nunique")).reset_index().sort_values("papers", ascending=False))
    summary_.to_csv(review_dir / "venues_without_quartile.csv", index=False)


def summary(frame: pd.DataFrame) -> dict[str, Any]:
    papers = frame.drop_duplicates(["institution", "openalex_work_id"])
    journal = papers[papers["type"] == "journal"]
    conference = papers[papers["type"] == "conference"]
    return {
        "rows": len(frame), "unique_papers": int(frame["openalex_work_id"].nunique()),
        "rows_per_institution": frame["institution"].value_counts().to_dict(),
        "papers_per_institution": papers["institution"].value_counts().to_dict(),
        "papers_by_type": papers["type"].value_counts().to_dict(),
        "journal_papers_with_quartile": f"{(journal['quartile'] != '').sum()} of {len(journal)}",
        "conference_papers_with_rank": f"{(conference['quartile'] != '').sum()} of {len(conference)}",
        "quartile_share_journal_papers": journal[journal["quartile"] != ""]["quartile"].value_counts(normalize=True).round(3).to_dict(),
        "affiliation_status_rows": frame["affiliation_status"].value_counts().to_dict(),
        "papers_without_doi": int((papers["doi"] == "").sum()),
        "rows_without_author_id": int((frame["openalex_author_id"] == "").sum()),
        "hyperauthor_papers": int(papers.drop_duplicates("openalex_work_id")["is_hyperauthor"].sum()),
        "fields": papers["primary_field"].value_counts().to_dict(),
    }


def report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Build report", "", f"- rows: **{report['rows']}**, unique papers: **{report['unique_papers']}**",
             f"- papers per institution: {report['papers_per_institution']}",
             f"- journal papers with a quartile: {report['journal_papers_with_quartile']}",
             f"- conference papers with a CORE rank: {report['conference_papers_with_rank']}",
             f"- quartile inputs: {report['quartile_inputs']}",
             f"- authors merged by ORCID: {report['authors_merged_by_orcid']}",
             f"- papers without DOI: {report['papers_without_doi']}, rows without author id: {report['rows_without_author_id']}",
             "", "## Removed (and why)", ""]
    lines += [f"- {reason}: {count}" for reason, count in report["dropped"].items()]
    lines += ["", "Review lists for every removal are in `review/`.", ""]
    return "\n".join(lines)
