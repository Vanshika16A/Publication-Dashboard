"""Find DOIs for papers OpenAlex gives none, by Crossref title search (gap #3, D-024).

    python -m dpcn_mapping.collect_doi           # fetch (resumable), write candidates and review file
    python -m dpcn_mapping.collect_doi --check   # rebuild every output from the saved responses, no network

Scope: papers of the latest enriched file with a blank `doi`, fixed at the first fetch. For each
paper one Crossref search is sent (anonymous; no email or personal data):
`api.crossref.org/works?query.bibliographic=<title>&query.author=<first author>
&filter=from-pub-date:<year-1>,until-pub-date:<year+1>&rows=5`. Each raw line stores the paper's
own metadata next to the response, so --check needs neither the network nor the current build.

Every returned item is scored against the paper (title, year, venue, author, type, repository,
DOI conflict). A paper's best candidate, and any other near-strong one, go to the review file,
except papers listed in `reviews.non_technical_file` (dropped by the build anyway, D-023). A
reviewer marks `decision`: `yes` (the build fills the DOI), `no`, or `copy` (the paper is a copy of
`doi_conflict_work`, the work already holding that DOI; the build drops the copy). Only the review
file is read by the build (config `doi.review_file`); nothing here changes the dataset.

Output in data/external/crossref/<RUN_DATE>/: doi_search.jsonl (raw), doi_candidates.csv (every
item, scored), doi_no_candidate.csv (papers with no plausible item), MANIFEST.json (written last,
sha256 of each). Review file: reviews/review_doi_matches.csv (earlier decisions kept).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import duckdb
import pandas as pd
import requests

from .config import CONFIG, ENRICHED, ROOT

RUN_DATE = "2026-10-12"
OUT = ROOT / "data" / "external" / "crossref" / RUN_DATE
RAW = OUT / "doi_search.jsonl"
CANDIDATES = OUT / "doi_candidates.csv"
NO_CANDIDATE = OUT / "doi_no_candidate.csv"
MANIFEST = OUT / "MANIFEST.json"
OUR_FILES = (RAW, CANDIDATES, NO_CANDIDATE)
REVIEW = ROOT / CONFIG["doi"]["review_file"]
WORKS = ROOT / "data" / "parquet" / CONFIG["build"]["snapshot_id"] / "works.parquet"
FULL_AUTHORSHIPS = ROOT / "data" / "parquet" / CONFIG["build"]["snapshot_id"] / "full_authorships.parquet"
ENDPOINT = "https://api.crossref.org/works"
ROWS = 5
PAUSE_SECONDS = 1.0

TITLE_THRESHOLD = CONFIG["doi"]["title_threshold"]
REVIEW_MIN_SIMILARITY = CONFIG["doi"]["review_min_similarity"]
REPOSITORY_PREFIXES = tuple(prefix.lower() for prefix in CONFIG["doi"]["repository_prefixes"])
REPOSITORY_TYPES = {"posted-content", "component", "dataset", "peer-review", "report", "other"}
TYPE_MATCH = {"journal": {"journal-article"}, "conference": {"proceedings-article"}}
CHECKS = ("title_ok", "year_ok", "venue_ok", "author_ok", "type_ok")
REVIEW_COLUMNS = [
    "decision", "note", "status", "match_score", "openalex_work_id", "institutions", "year", "type",
    "title", "crossref_title", "title_similarity", "title_ok", "crossref_year", "year_ok",
    "journal_name", "crossref_container", "issns", "crossref_issns", "venue_ok",
    "authors_sample", "crossref_authors_sample", "shared_surnames", "author_ok",
    "crossref_type", "type_ok", "candidate_doi", "repository_doi", "doi_conflict", "doi_conflict_work",
]


def norm(text: str) -> str:
    """Lowercase ASCII letters and digits, single spaces (titles, venues)."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    text = re.sub(r"<[^>]+>", " ", text)  # Crossref titles may carry JATS/MathML tags
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def surname_tokens(text: str) -> set[str]:
    """Letter-only ASCII tokens of a name part, at least 2 letters."""
    return {token for token in norm(re.sub(r"\d", " ", text)).split() if len(token) >= 2}


def our_surname(name: str) -> str:
    """Last letter-only token of an OpenAlex display name ("R. K. Sharma" -> "sharma")."""
    tokens = norm(re.sub(r"\d", " ", name)).split()
    return tokens[-1] if tokens and len(tokens[-1]) >= 2 else ""


def issn_key(issn: str) -> str:
    return re.sub(r"[^0-9X]", "", (issn or "").upper())


# ---------------------------------------------------------------- scope and fetch

def scope() -> list[dict]:
    """Blank-DOI papers of the latest build with the metadata used for the query and the evidence."""
    frame = pd.read_csv(ENRICHED, dtype=str, keep_default_na=False)
    blank = frame[frame["doi"] == ""]
    papers = blank.groupby("openalex_work_id", sort=True).agg(
        title=("title", "first"), year=("year", "first"), type=("type", "first"),
        journal_name=("journal_name", "first"), all_issns=("all_issns", "first"),
        source_type=("source_type", "first"), institutions=("institution", lambda s: "; ".join(sorted(set(s)))),
    ).reset_index()
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    con.register("p", papers[["openalex_work_id"]])
    authors = con.sql(f"""
        WITH a AS (
            SELECT replace(f.id, 'https://openalex.org/', '') AS openalex_work_id, unnest(f.authorships) AS au
            FROM read_parquet('{FULL_AUTHORSHIPS}') f JOIN p ON replace(f.id, 'https://openalex.org/', '') = p.openalex_work_id
            UNION ALL
            SELECT replace(w.id, 'https://openalex.org/', ''), unnest(w.authorships)
            FROM read_parquet('{WORKS}') w JOIN p ON replace(w.id, 'https://openalex.org/', '') = p.openalex_work_id
              AND replace(w.id, 'https://openalex.org/', '') NOT IN
                  (SELECT replace(id, 'https://openalex.org/', '') FROM read_parquet('{FULL_AUTHORSHIPS}'))
        )
        SELECT openalex_work_id, list(au.author.display_name) AS authors,
               first(au.author.display_name) FILTER (WHERE au.author_position = 'first') AS first_author
        FROM a GROUP BY openalex_work_id
    """).df()
    papers = papers.merge(authors, on="openalex_work_id", how="left")
    papers["authors"] = papers["authors"].apply(lambda names: [] if not hasattr(names, "__len__") else [n for n in names if n])
    papers["first_author"] = papers["first_author"].fillna("")
    columns = ["openalex_work_id", "title", "year", "type", "journal_name", "all_issns", "source_type", "institutions",
               "first_author", "authors"]
    return papers[columns].to_dict("records")


def read_raw() -> dict[str, dict]:
    records = {}
    if RAW.exists():
        for line in RAW.open():
            record = json.loads(line)
            records[record["paper"]["openalex_work_id"]] = record  # the last record per paper wins
    return records


def query_params(paper: dict) -> dict[str, str]:
    year = int(paper["year"])
    params = {"query.bibliographic": paper["title"], "rows": str(ROWS),
              "filter": f"from-pub-date:{year - 1},until-pub-date:{year + 1}"}
    if paper["first_author"]:
        params["query.author"] = paper["first_author"]
    return params


def fetch(papers: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    done = read_raw()
    todo = [p for p in papers if p["openalex_work_id"] not in done or done[p["openalex_work_id"]]["http_status"] != 200]
    session = requests.Session()
    session.headers["User-Agent"] = "DPCN-Group16/1.0"
    with RAW.open("a") as handle:
        for index, paper in enumerate(todo, 1):
            params = query_params(paper)
            for attempt in range(5):
                try:
                    response = session.get(ENDPOINT, params=params, timeout=60)
                except requests.RequestException as error:
                    status, body = None, str(error)
                else:
                    status = response.status_code
                    body = response.json() if status == 200 else response.text[:500]
                if status in (200, 400, 404):
                    break
                time.sleep(10 * (attempt + 1))
            handle.write(json.dumps({"paper": {**paper, "authors": list(paper["authors"])}, "params": params, "url": ENDPOINT,
                                     "requested_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                                     "http_status": status, "response": body}) + "\n")
            handle.flush()
            print(f"crossref: {index}/{len(todo)} {paper['openalex_work_id']} -> {status}", flush=True)
            time.sleep(PAUSE_SECONDS)


# ---------------------------------------------------------------- scoring

def snapshot_dois() -> dict[str, str]:
    """Lowercased DOI -> work ID for every work in the sealed snapshot that has one."""
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    rows = con.sql(f"""SELECT replace(id, 'https://openalex.org/', '') AS id, lower(doi) AS doi
                          FROM read_parquet('{WORKS}') WHERE doi IS NOT NULL ORDER BY id""").fetchall()
    out: dict[str, str] = {}
    for work_id, doi in rows:
        out.setdefault(doi.removeprefix("https://doi.org/"), work_id)
    return out


def item_year(item: dict) -> int | None:
    parts = ((item.get("issued") or {}).get("date-parts") or [[None]])[0]
    return parts[0] if parts and parts[0] else None


def plain(text: str) -> str:
    """Crossref text without JATS/MathML tags and line breaks, for display."""
    return " ".join(re.sub(r"<[^>]+>", " ", text or "").split())


def item_title(item: dict) -> tuple[str, list[str]]:
    title = plain(" ".join((item.get("title") or [""])[:1]))
    subtitle = plain(" ".join((item.get("subtitle") or [""])[:1]))
    variants = [title] + ([f"{title}: {subtitle}"] if subtitle else [])
    return (variants[-1], variants)


def score(paper: dict, item: dict, holders: dict[str, str]) -> dict:
    title_shown, variants = item_title(item)
    similarity = max(SequenceMatcher(None, norm(paper["title"]), norm(v)).ratio() for v in variants)
    year = item_year(item)
    issns = sorted({issn_key(i) for i in item.get("ISSN") or []} - {""})
    ours = {issn_key(i) for i in paper["all_issns"].split(";")} - {""}
    container = " | ".join(plain(c) for c in item.get("container-title") or [])
    containers = {norm(c) for c in item.get("container-title") or []} - {""}
    crossref_surnames = set()
    for author in item.get("author") or []:
        family = author.get("family") or (author.get("name") or "").split(" ")[-1]
        crossref_surnames |= surname_tokens(family)
    our_surnames = {our_surname(name) for name in paper["authors"]} - {""}
    shared = sorted(our_surnames & crossref_surnames)
    doi = (item.get("DOI") or "").lower()
    holder = holders.get(doi, "")
    result = {
        "title_similarity": round(similarity, 4),
        "title_ok": similarity >= TITLE_THRESHOLD,
        "crossref_title": title_shown,
        "crossref_year": year or "",
        "year_ok": year is not None and abs(year - int(paper["year"])) <= 1,
        "crossref_container": container,
        "crossref_issns": "; ".join(issns),
        "venue_ok": bool(ours & set(issns)) or (norm(paper["journal_name"]) != "" and norm(paper["journal_name"]) in containers),
        "crossref_authors_sample": "; ".join(f"{a.get('given', '')} {a.get('family', a.get('name', ''))}".strip()
                                            for a in (item.get("author") or [])[:5]),
        "shared_surnames": "; ".join(shared),
        "author_ok": bool(shared),
        "crossref_type": item.get("type") or "",
        "type_ok": (item.get("type") or "") in TYPE_MATCH[paper["type"]],
        "candidate_doi": doi,
        "repository_doi": doi.startswith(REPOSITORY_PREFIXES) or (item.get("type") or "") in REPOSITORY_TYPES,
        "doi_conflict": bool(holder) and holder != paper["openalex_work_id"],
        "doi_conflict_work": holder if holder != paper["openalex_work_id"] else "",
        "crossref_score": item.get("score"),
    }
    passed = sum(result[check] for check in CHECKS)
    result["checks_passed"] = passed
    result["match_score"] = round(50 * similarity + 12.5 * sum(result[c] for c in CHECKS[1:]), 1)
    result["strong"] = passed == len(CHECKS) and not result["repository_doi"] and not result["doi_conflict"]
    # Near-strong: title matches and at most one other check fails; used only to detect ambiguity.
    result["near_strong"] = result["title_ok"] and passed >= len(CHECKS) - 1 and not result["repository_doi"]
    return result


def candidates(records: dict[str, dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    holders = snapshot_dois()
    rows, missing = [], []
    for work_id in sorted(records):
        record = records[work_id]
        paper = record["paper"]
        items = (record["response"] or {}).get("message", {}).get("items", []) if record["http_status"] == 200 else []
        base = {"openalex_work_id": work_id, "institutions": paper["institutions"], "year": paper["year"],
                "type": paper["type"], "title": paper["title"], "journal_name": paper["journal_name"],
                "issns": paper["all_issns"], "authors_sample": "; ".join(paper["authors"][:5])}
        scored = [{**base, "rank": rank, **score(paper, item, holders)} for rank, item in enumerate(items, 1)]
        best = max((s["title_similarity"] for s in scored), default=0.0)
        if record["http_status"] != 200 or best < REVIEW_MIN_SIMILARITY:
            missing.append({"openalex_work_id": work_id, "http_status": record["http_status"], "items": len(items),
                            "best_title_similarity": round(best, 4), "title": paper["title"], "year": paper["year"],
                            "journal_name": paper["journal_name"]})
        rows += scored
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame, pd.DataFrame(missing)
    # Two papers proposing the same DOI: neither is strong.
    strong_dois = frame[frame["strong"]].groupby("candidate_doi")["openalex_work_id"].nunique()
    shared = frame["candidate_doi"].isin(strong_dois[strong_dois > 1].index) & frame["strong"]
    frame.loc[shared, "doi_conflict"] = True
    frame.loc[shared, "doi_conflict_work"] = "another candidate paper"
    frame.loc[shared, "strong"] = False
    # Near-strong candidates with different DOIs for one paper: ambiguous, not strong.
    near = frame[frame["near_strong"]].groupby("openalex_work_id")["candidate_doi"].nunique()
    ambiguous = frame["openalex_work_id"].isin(near[near > 1].index)
    frame["status"] = "weak"
    frame.loc[frame["strong"], "status"] = "strong"
    frame.loc[ambiguous & frame["near_strong"], "status"] = "ambiguous"
    frame.loc[ambiguous, "strong"] = False
    return frame, pd.DataFrame(missing, columns=["openalex_work_id", "http_status", "items", "best_title_similarity",
                                                 "title", "year", "journal_name"])


def review_rows(frame: pd.DataFrame, missing: pd.DataFrame) -> pd.DataFrame:
    """Per paper with a plausible item: the best candidate, plus every other near-strong one."""
    frame = frame[~frame["openalex_work_id"].isin(missing["openalex_work_id"])]
    frame = frame.sort_values(["openalex_work_id", "strong", "title_similarity", "match_score", "rank"],
                              ascending=[True, False, False, False, True])
    best = frame.groupby("openalex_work_id").head(1)
    keep = pd.concat([best, frame[frame["near_strong"]]]).drop_duplicates(["openalex_work_id", "candidate_doi"])
    order = {"strong": 0, "ambiguous": 1, "weak": 2}
    keep = keep.assign(_order=keep["status"].map(order)).sort_values(
        ["_order", "match_score", "openalex_work_id"], ascending=[True, False, True])
    keep = keep.assign(decision="", note="")
    return keep[REVIEW_COLUMNS]


def write_review(new: pd.DataFrame) -> None:
    """Write the review file, keeping earlier decisions and notes per (work, candidate DOI)."""
    if REVIEW.exists():
        old = pd.read_csv(REVIEW, dtype=str, keep_default_na=False)
        kept = old.set_index(["openalex_work_id", "candidate_doi"])[["decision", "note"]]
        key = list(zip(new["openalex_work_id"], new["candidate_doi"]))
        new["decision"] = [kept["decision"].get(k, "") for k in key]
        new["note"] = [kept["note"].get(k, "") for k in key]
        dropped = set(zip(old["openalex_work_id"], old["candidate_doi"])) - set(key)
        decided = [k for k in dropped if kept.loc[k, "decision"] != ""]
        if decided:
            raise SystemExit(f"{len(decided)} reviewed rows would disappear from {REVIEW.name}: {decided[:5]}")
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    new.to_csv(REVIEW, index=False)


def non_technical_ids() -> set[str]:
    """Papers listed as non-technical (D-023); they get no review row."""
    name = CONFIG.get("reviews", {}).get("non_technical_file")
    if not name or not (ROOT / name).exists():
        return set()
    return set(pd.read_csv(ROOT / name, dtype=str)["openalex_work_id"])


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="rebuild outputs from saved responses only, no network")
    parser.add_argument("--no-review", action="store_true", help="do not write the review file")
    args = parser.parse_args(argv)
    if not args.check:
        # Until the first complete fetch writes MANIFEST.json the scope is read from the enriched file
        # (an interrupted fetch resumes); after that it is fixed, and reruns only retry failed requests.
        papers = [r["paper"] for r in read_raw().values()] if MANIFEST.exists() else scope()
        fetch(papers)
    records = read_raw()
    if not records:
        raise SystemExit(f"no saved responses in {RAW.relative_to(ROOT)}")
    frame, missing = candidates(records)
    OUT.mkdir(parents=True, exist_ok=True)
    frame.to_csv(CANDIDATES, index=False)
    missing.to_csv(NO_CANDIDATE, index=False)
    non_technical = non_technical_ids()
    review = review_rows(frame[~frame["openalex_work_id"].isin(non_technical)], missing)
    if not args.no_review:
        write_review(review)
    statuses = review["status"].value_counts().to_dict()
    manifest = {
        "module": "dpcn_mapping.collect_doi", "run_date": RUN_DATE, "endpoint": ENDPOINT, "anonymous": True,
        "query": "query.bibliographic=<title>, query.author=<first author>, filter=from-pub-date:<year-1>,"
                 f"until-pub-date:<year+1>, rows={ROWS}",
        "scope": "papers with a blank doi in the enriched file when first fetched",
        "papers": len(records), "http_status": pd.Series([r["http_status"] for r in records.values()]).value_counts().to_dict(),
        "items_scored": len(frame), "papers_without_candidate": len(missing),
        "review_rows": len(review), "review_papers": int(review["openalex_work_id"].nunique()), "review_status": statuses,
        "review_papers_excluded_non_technical": len(
            (set(frame["openalex_work_id"]) - set(missing["openalex_work_id"])) & non_technical),
        "title_threshold": TITLE_THRESHOLD, "review_min_similarity": REVIEW_MIN_SIMILARITY,
        "files_sha256": {path.name: sha256(path) for path in OUR_FILES if path.exists()},
        "note": "covers only the files named here; ror_rows_* in this folder belong to verify_ror_rows",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    print(json.dumps({k: manifest[k] for k in ("papers", "http_status", "items_scored", "papers_without_candidate",
                                                 "review_rows", "review_papers", "review_status")}, default=str))


if __name__ == "__main__":
    main(sys.argv[1:])
