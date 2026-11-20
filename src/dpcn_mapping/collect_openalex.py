"""Resumable OpenAlex collection for Group 16 (JNU, University of Hyderabad, University of Delhi).

Steps (run in order; each one resumes from its saved state if interrupted):

    python -m dpcn_mapping.collect_openalex works          # all works 2016-2026 for the 3 institutions
    python -m dpcn_mapping.collect_openalex full-authors   # full author lists for works truncated at 100
    python -m dpcn_mapping.collect_openalex indian-refs    # referenced works with an Indian affiliation
    python -m dpcn_mapping.collect_openalex indian-citers  # citing works with an Indian affiliation
    python -m dpcn_mapping.collect_openalex authors        # author profiles (h-index, ORCID)
    python -m dpcn_mapping.collect_openalex core           # CORE conference ranking export
    python -m dpcn_mapping.collect_openalex manifest       # seal the snapshot (MANIFEST.json, read-only)
    python -m dpcn_mapping.collect_openalex status         # progress of every step

Raw API responses are cached as JSON Lines in the snapshot folder
data/raw/openalex/<collection.snapshot_id>/ (set in config/build.toml). A snapshot
with a MANIFEST.json is complete and is never written to again. Nothing is derived
or guessed here; `build_dataset.py` turns a sealed snapshot into the CSV deliverable.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

from .config import CONFIG, END_YEAR, EXTERNAL, METADATA, START_YEAR, snapshot_dir
from .openalex_client import BASE_URL, BudgetExhausted, OpenAlexClient

SNAPSHOT_ID = CONFIG["collection"]["snapshot_id"]
CACHE = snapshot_dir(SNAPSHOT_ID)
SNAPSHOT_RECORDS = METADATA / "snapshots"  # committed copies of each MANIFEST.json
MANIFEST_NAME = "MANIFEST.json"
STEPS = ("works", "full_authorships", "indian_refs", "indian_citers", "authors")

# Verified on 2026-10-08 via https://api.openalex.org/institutions/ror:<ror>
OPENALEX_INSTITUTIONS = {
    "Jawaharlal Nehru University": ("I152429107", "https://ror.org/0567v8t28"),
    "University of Hyderabad": ("I36893310", "https://ror.org/04a7rxb17"),
    "University of Delhi": ("I110166357", "https://ror.org/04gzb2213"),
}
LINEAGE_FILTER = "|".join(openalex_id for openalex_id, _ in OPENALEX_INSTITUTIONS.values())
YEARS = f"{START_YEAR}-{END_YEAR}"
BATCH = 100
LIST_AUTHORSHIP_LIMIT = 100  # list endpoints truncate authorships at 100

WORK_FIELDS = (
    "id,doi,title,publication_year,type,primary_location,authorships,"
    "cited_by_count,referenced_works,primary_topic"
)
LINKED_WORK_FIELDS = "id,doi,publication_year,authorships"
CITER_FIELDS = "id,doi,publication_year,authorships,referenced_works"
AUTHOR_FIELDS = "id,display_name,orcid,works_count,cited_by_count,summary_stats,last_known_institutions"
CORE_EXPORT_URL = (
    "https://portal.core.edu.au/conf-ranks/?search=&by=all&source=ICORE2026&sort=arank&page=1&do=Export"
)


def _state_path(step: str, cache: Path | None = None) -> Path:
    return (cache or CACHE) / f"{step}.state.json"


def _load_state(step: str, cache: Path | None = None) -> dict[str, Any]:
    path = _state_path(step, cache)
    return json.loads(path.read_text()) if path.exists() else {}


def _save_state(step: str, state: dict[str, Any]) -> None:
    path = _state_path(step)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(path)


def _append(path: Path, records: Iterable[dict[str, Any]]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def corpus_ids() -> list[str]:
    """Sorted short OpenAlex ids (W...) of every collected work, deduplicated."""
    ids = {record["id"].rsplit("/", 1)[-1] for record in read_jsonl(CACHE / "works.jsonl")}
    return sorted(ids)


def step_works(client: OpenAlexClient) -> None:
    state = _load_state("works")
    if state.get("done"):
        print("works: already complete", state)
        return
    params = {"filter": f"authorships.institutions.lineage:{LINEAGE_FILTER},publication_year:{YEARS}", "select": WORK_FIELDS}
    cursor = state.get("cursor", "*")
    pages = state.get("pages", 0)
    fetched = state.get("records", 0)
    for results, next_cursor, total in client.paginate("/works", params, cursor):
        _append(CACHE / "works.jsonl", results)
        pages += 1
        fetched += len(results)
        state = {"cursor": next_cursor, "pages": pages, "records": fetched, "expected": total, "done": not next_cursor}
        _save_state("works", state)
        print(f"works: page {pages}, {fetched}/{total} records, budget remaining {client.remaining}", flush=True)
    state["done"] = True
    _save_state("works", state)


def _batched_linked_step(client: OpenAlexClient, step: str, filter_name: str, fields: str) -> None:
    works_state = _load_state("works")
    if not works_state.get("done"):
        raise SystemExit(f"{step}: run the 'works' step to completion first")
    ids = corpus_ids()
    batches = [ids[i : i + BATCH] for i in range(0, len(ids), BATCH)]
    state = _load_state(step)
    if state.get("done"):
        print(f"{step}: already complete", state)
        return
    start = state.get("next_batch", 0)
    cursor = state.get("cursor", "*")
    records = state.get("records", 0)
    out = CACHE / f"{step}.jsonl"
    for index in range(start, len(batches)):
        params = {
            "filter": f"{filter_name}:{'|'.join(batches[index])},authorships.institutions.country_code:IN",
            "select": fields,
        }
        for results, next_cursor, _ in client.paginate("/works", params, cursor):
            _append(out, results)
            records += len(results)
            cursor = next_cursor or "*"
            # Saving the in-batch cursor lets an interrupted batch resume mid-way.
            _save_state(step, {"next_batch": index, "cursor": next_cursor or "*", "records": records,
                               "batches": len(batches), "done": False})
        cursor = "*"
        _save_state(step, {"next_batch": index + 1, "cursor": "*", "records": records,
                           "batches": len(batches), "done": False})
        print(f"{step}: batch {index + 1}/{len(batches)}, {records} records, budget remaining {client.remaining}",
              flush=True)
    _save_state(step, {"next_batch": len(batches), "cursor": "*", "records": records,
                       "batches": len(batches), "done": True})


def step_full_authorships(client: OpenAlexClient) -> None:
    """List responses cut authorships at 100; refetch those works one by one (singleton calls are free)."""
    if not _load_state("works").get("done"):
        raise SystemExit("full-authors: run the 'works' step to completion first")
    truncated = sorted({
        work["id"].rsplit("/", 1)[-1]
        for work in read_jsonl(CACHE / "works.jsonl")
        if len(work.get("authorships") or []) >= LIST_AUTHORSHIP_LIMIT
    })
    out = CACHE / "full_authorships.jsonl"
    done = {record["id"].rsplit("/", 1)[-1] for record in read_jsonl(out)}
    todo = [work_id for work_id in truncated if work_id not in done]
    print(f"full-authors: {len(truncated)} works with >= {LIST_AUTHORSHIP_LIMIT} authorships, {len(todo)} left")
    _save_state("full_authorships", {"works": len(truncated), "fetched": len(done), "done": False})
    for count, work_id in enumerate(todo, 1):
        _append(out, [client.get(f"/works/{work_id}", {"select": "id,authorships"})])
        if count % 10 == 0 or count == len(todo):
            _save_state("full_authorships", {"works": len(truncated), "fetched": len(done) + count, "done": False})
            print(f"full-authors: {len(done) + count}/{len(truncated)}", flush=True)
    _save_state("full_authorships", {"works": len(truncated), "fetched": len(truncated), "done": True})


def step_authors(client: OpenAlexClient) -> None:
    if not _load_state("works").get("done"):
        raise SystemExit("authors: run the 'works' step to completion first")
    lineage = {openalex_id for openalex_id, _ in OPENALEX_INSTITUTIONS.values()}
    author_ids: set[str] = set()
    for work in read_jsonl(CACHE / "works.jsonl"):
        for authorship in work.get("authorships") or []:
            author = (authorship.get("author") or {}).get("id")
            if not author:
                continue
            for inst in authorship.get("institutions") or []:
                if lineage & {lin.rsplit("/", 1)[-1] for lin in inst.get("lineage") or []}:
                    author_ids.add(author.rsplit("/", 1)[-1])
    ids = sorted(author_ids)
    batches = [ids[i : i + BATCH] for i in range(0, len(ids), BATCH)]
    state = _load_state("authors")
    if state.get("done"):
        print("authors: already complete", state)
        return
    records = state.get("records", 0)
    for index in range(state.get("next_batch", 0), len(batches)):
        data = client.get("/authors", {"filter": f"ids.openalex:{'|'.join(batches[index])}",
                                       "select": AUTHOR_FIELDS, "per_page": 200})
        _append(CACHE / "authors.jsonl", data["results"])
        records += len(data["results"])
        _save_state("authors", {"next_batch": index + 1, "records": records, "requested": len(ids),
                                "batches": len(batches), "done": False})
        print(f"authors: batch {index + 1}/{len(batches)}, {records}/{len(ids)}, budget remaining {client.remaining}",
              flush=True)
    _save_state("authors", {"next_batch": len(batches), "records": records, "requested": len(ids),
                            "batches": len(batches), "done": True})


def step_core() -> None:
    target = EXTERNAL / "core" / "CORE_ICORE2026.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(CORE_EXPORT_URL, timeout=60)
    response.raise_for_status()
    if "text/csv" not in response.headers.get("content-type", ""):
        raise SystemExit(f"core: unexpected content type {response.headers.get('content-type')}")
    target.write_bytes(response.content)
    rows = sum(1 for _ in csv.reader(response.text.splitlines()))
    source = {"url": CORE_EXPORT_URL, "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
              "rows": rows, "sha256": hashlib.sha256(response.content).hexdigest()}
    target.with_suffix(".source.json").write_text(json.dumps(source, indent=2))
    print(f"core: saved {rows} rows to {target}; see data/external/SOURCES.md")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 22), b""):
            digest.update(chunk)
    return digest.hexdigest()


def step_manifest() -> None:
    """Seal a finished snapshot: write MANIFEST.json last and make every file read-only."""
    unfinished = [step for step in STEPS if not _load_state(step).get("done")]
    if unfinished:
        raise SystemExit(f"manifest: steps not finished: {', '.join(unfinished)}")
    files = {}
    for path in sorted(CACHE.iterdir()):
        if path.name == MANIFEST_NAME or not path.is_file():
            continue
        entry: dict[str, Any] = {"bytes": path.stat().st_size, "sha256": _sha256(path)}
        if path.suffix == ".jsonl":
            ids = set()
            lines = 0
            for record in read_jsonl(path):
                lines += 1
                ids.add(record.get("id"))
            entry.update({"records": lines, "unique_ids": len(ids)})
        files[path.name] = entry
        print(f"manifest: hashed {path.name}", flush=True)
    code = {name: _sha256(Path(__file__).with_name(name))
            for name in ("collect_openalex.py", "openalex_client.py", "config.py")}
    mtimes = [path.stat().st_mtime for path in CACHE.iterdir() if path.is_file()]
    manifest = {
        "snapshot_id": SNAPSHOT_ID,
        "mode": "api",
        "api_base_url": BASE_URL,
        "institutions": {name: {"openalex_id": oid, "ror": ror} for name, (oid, ror) in OPENALEX_INSTITUTIONS.items()},
        "years": YEARS,
        "queries": {
            "works": {"endpoint": "/works", "filter": f"authorships.institutions.lineage:{LINEAGE_FILTER},publication_year:{YEARS}",
                      "select": WORK_FIELDS, "paging": "cursor, per_page=200"},
            "full_authorships": {"endpoint": "/works/<id>", "select": "id,authorships",
                                 "applies_to": f"works whose list response had >= {LIST_AUTHORSHIP_LIMIT} authorships"},
            "indian_refs": {"endpoint": "/works", "filter": "cited_by:<100 corpus ids>,authorships.institutions.country_code:IN",
                            "select": LINKED_WORK_FIELDS},
            "indian_citers": {"endpoint": "/works", "filter": "cites:<100 corpus ids>,authorships.institutions.country_code:IN",
                              "select": CITER_FIELDS},
            "authors": {"endpoint": "/authors", "filter": "ids.openalex:<100 ids>", "select": AUTHOR_FIELDS},
        },
        "step_states": {step: _load_state(step) for step in STEPS},
        "files": files,
        "code_sha256": code,
        "file_mtime_first_utc": datetime.fromtimestamp(min(mtimes), timezone.utc).isoformat(),
        "file_mtime_last_utc": datetime.fromtimestamp(max(mtimes), timezone.utc).isoformat(),
        "sealed_at_utc": datetime.now(timezone.utc).isoformat(),
        "known_gaps": [
            "works with exactly 5000 authorships after the singleton refetch may still have incomplete author lists",
            "indian_refs / indian_citers contain duplicates across batches (deduplicated at build time)",
            "author ids that no longer resolve in OpenAlex are missing from authors.jsonl",
            "citation counts and author disambiguation are as of the collection date; OpenAlex changes continuously",
        ],
    }
    (CACHE / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2))
    # The snapshot folder is gitignored, so keep a committed copy of its manifest.
    SNAPSHOT_RECORDS.mkdir(parents=True, exist_ok=True)
    (SNAPSHOT_RECORDS / f"{SNAPSHOT_ID}.json").write_text(json.dumps(manifest, indent=2))
    for path in CACHE.iterdir():
        if path.is_file():
            path.chmod(path.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    print(f"manifest: snapshot {SNAPSHOT_ID} sealed ({len(files)} files, read-only)")


def _bar(done: float, total: float, width: int = 30) -> str:
    if not total:
        return "[" + " " * width + "]   ?"
    fraction = min(1.0, done / total)
    filled = int(fraction * width)
    return "[" + "#" * filled + "-" * (width - filled) + f"] {fraction:6.1%}"


def step_status() -> None:
    sealed = (CACHE / MANIFEST_NAME).exists()
    print(f"snapshot {SNAPSHOT_ID}: {'SEALED (MANIFEST.json present)' if sealed else 'collecting'}  [{CACHE}]")
    rows = [
        ("works", "pages", lambda st: (st.get("records", 0), st.get("expected", 0), "records")),
        ("full_authorships", "", lambda st: (st.get("fetched", 0), st.get("works", 0), "works")),
        ("indian_refs", "", lambda st: (st.get("next_batch", 0), st.get("batches", 0), "batches")),
        ("indian_citers", "", lambda st: (st.get("next_batch", 0), st.get("batches", 0), "batches")),
        ("authors", "", lambda st: (st.get("next_batch", 0), st.get("batches", 0), "batches")),
    ]
    for step, _, extract in rows:
        state = _load_state(step)
        if not state:
            print(f"{step:17s} {'not started':>40s}")
            continue
        done, total, unit = extract(state)
        label = "DONE" if state.get("done") else f"{done}/{total or '?'} {unit}"
        bar = _bar(1, 1) if state.get("done") else _bar(done, total)
        print(f"{step:17s} {bar}  {label}")
    for path in sorted(CACHE.glob("*.jsonl")):
        print(f"  cache {path.name:28s} {path.stat().st_size / 1e6:9.1f} MB")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["works", "full-authors", "indian-refs", "indian-citers", "authors", "core",
                                         "manifest", "status"])
    args = parser.parse_args(argv)
    if args.step == "status":
        step_status()
        return 0
    if (CACHE / MANIFEST_NAME).exists() and args.step != "core":
        print(f"snapshot {SNAPSHOT_ID} is sealed (MANIFEST.json present); set a new collection.snapshot_id "
              "in config/build.toml to collect again", file=sys.stderr)
        return 3 if args.step != "manifest" else 0
    CACHE.mkdir(parents=True, exist_ok=True)
    if args.step == "manifest":
        step_manifest()
        return 0
    if args.step == "core":
        step_core()
        return 0
    client = OpenAlexClient()
    print(f"OpenAlex API key {'found' if client.api_key else 'NOT set (free tier ~1000 requests/day)'}")
    try:
        if args.step == "works":
            step_works(client)
        elif args.step == "full-authors":
            step_full_authorships(client)
        elif args.step == "indian-refs":
            _batched_linked_step(client, "indian_refs", "cited_by", LINKED_WORK_FIELDS)
        elif args.step == "indian-citers":
            _batched_linked_step(client, "indian_citers", "cites", CITER_FIELDS)
        elif args.step == "authors":
            step_authors(client)
    except BudgetExhausted as error:
        print(f"STOPPED: OpenAlex daily budget exhausted after {client.requests_made} requests. "
              f"Progress saved; rerun the same step later or set OPENALEX_API_KEY. Detail: {error}", file=sys.stderr)
        return 2
    print(f"done; {client.requests_made} requests this run, budget remaining {client.remaining}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
