"""Download only what the dataset needs from OpenAlex, resumably.

Steps (each saves its progress, so a stopped run simply continues):

    works         science/engineering works of the 3 institutions, reduced to the needed fields
    full-authors  complete author lists for works whose list response was cut at 100 authors
    linked        Indian works cited by our works (refs) and Indian works citing ours (citers)
    authors       author profiles (h-index, ORCID) for authors affiliated with an institution
    sources       journal-level OpenAlex numbers (2-year mean citedness) for impact-factor proxy
    core          CORE conference ranking export

Every response is reduced before it is written, so the cache stays small (hundreds of MB
rather than the ~10 GB a raw copy needs).
"""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

from .client import BudgetExhausted, OpenAlexClient, short_id
from .config import CONFIG, END_YEAR, INSTITUTIONS, RAW_DIR, START_YEAR, TARGET_IDS, resolve

LIST_AUTHORSHIP_LIMIT = 100  # OpenAlex list responses cut `authorships` at 100
WORK_FIELDS = "id,doi,title,publication_year,type,primary_location,authorships,cited_by_count,referenced_works,primary_topic"
LINKED_FIELDS = "id,publication_year,authorships"
CITER_FIELDS = "id,publication_year,authorships,referenced_works"
AUTHOR_FIELDS = "id,display_name,orcid,works_count,cited_by_count,summary_stats"
SOURCE_FIELDS = "id,display_name,issn_l,issn,type,summary_stats"
CORE_URL = "https://portal.core.edu.au/conf-ranks/?search=&by=all&source={source}&sort=arank&page=1&do=Export"
STEPS = ("works", "full-authors", "linked", "authors", "sources", "core")


@dataclass
class Run:
    """One collection: a year range and the folder holding its cache."""
    start_year: int = START_YEAR
    end_year: int = END_YEAR
    raw_dir: Path | None = None

    def __post_init__(self) -> None:
        if self.raw_dir is None:
            self.raw_dir = RAW_DIR / f"{self.start_year}-{self.end_year}"
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        return self.raw_dir / name


# ---------------------------------------------------------------- cache helpers

def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)


def append_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def load_state(run: Run, step: str) -> dict[str, Any]:
    path = run.path(f"{step}.state.json")
    return json.loads(path.read_text()) if path.exists() else {}


def save_state(run: Run, step: str, state: dict[str, Any]) -> None:
    path = run.path(f"{step}.state.json")
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(path)


def batches(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


# ---------------------------------------------------------------- reducing responses

def reduce_authorships(authorships: list[dict[str, Any]] | None) -> tuple[list[dict], dict[str, list]]:
    """Keep only authors affiliated with an assigned institution, and Indian institutions.

    Returns (authors, institutions). Each author carries, per assigned institution, the OpenAlex
    institution ids that placed them there (`via`) and the raw affiliation strings the author
    wrote that name one of those institutions (`strings`). An empty `strings` list means OpenAlex
    inferred the affiliation without any text on this paper backing it.
    """
    institutions: dict[str, list] = {}  # id -> [name, country, [lineage ids]]
    authors: list[dict] = []
    for position, authorship in enumerate(authorships or []):
        lineage_of: dict[str, set[str]] = {}
        for inst in authorship.get("institutions") or []:
            inst_id = short_id(inst.get("id"))
            lineage = {short_id(item) for item in inst.get("lineage") or []} | {inst_id}
            lineage_of[inst_id] = lineage
            if inst.get("country_code") == "IN" or lineage & TARGET_IDS:
                institutions[inst_id] = [inst.get("display_name") or "", inst.get("country_code") or "", sorted(lineage)]
        targets: dict[str, dict[str, list[str]]] = {}
        for inst_id, lineage in lineage_of.items():
            for target in lineage & TARGET_IDS:
                targets.setdefault(target, {"via": [], "strings": []})["via"].append(inst_id)
        if not targets:
            continue
        raw_strings = [s.strip() for s in authorship.get("raw_affiliation_strings") or [] if s and s.strip()]
        affiliations = authorship.get("affiliations")
        if affiliations is not None:
            for affiliation in affiliations:
                text = (affiliation.get("raw_affiliation_string") or "").strip()
                if not text:
                    continue
                for inst_id in affiliation.get("institution_ids") or []:
                    for target in lineage_of.get(short_id(inst_id), set()) & TARGET_IDS:
                        if text not in targets[target]["strings"]:
                            targets[target]["strings"].append(text)
        else:  # older record shape: strings are not linked to institutions
            for target in targets:
                targets[target]["strings"] = list(raw_strings)
        author = authorship.get("author") or {}
        authors.append({
            "id": short_id(author.get("id")),
            "name": author.get("display_name") or authorship.get("raw_author_name") or "",
            "orcid": author.get("orcid") or authorship.get("raw_orcid") or "",
            "pos": authorship.get("author_position") or "",
            "corr": bool(authorship.get("is_corresponding")),
            "raw": "; ".join(raw_strings),
            "t": targets,
            "idx": position,
        })
    return authors, institutions


def reduce_work(work: dict[str, Any]) -> dict[str, Any]:
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    topic = work.get("primary_topic") or {}
    authorships = work.get("authorships") or []
    authors, institutions = reduce_authorships(authorships)
    return {
        "id": short_id(work.get("id")),
        "doi": work.get("doi") or "",
        "title": work.get("title") or "",
        "year": work.get("publication_year"),
        "type": work.get("type") or "",
        "cited_by_count": work.get("cited_by_count") or 0,
        "source": {
            "id": short_id(source.get("id")), "name": source.get("display_name") or "",
            "type": source.get("type") or "", "issn_l": source.get("issn_l") or "",
            "issn": source.get("issn") or [],
        },
        "field": (topic.get("field") or {}).get("display_name") or "",
        "domain": (topic.get("domain") or {}).get("display_name") or "",
        "subfield": (topic.get("subfield") or {}).get("display_name") or "",
        "topic": topic.get("display_name") or "",
        "refs": [short_id(ref) for ref in work.get("referenced_works") or []],
        "n_auth": len(authorships),
        "truncated": len(authorships) >= LIST_AUTHORSHIP_LIMIT,
        "authors": authors,
        "insts": institutions,
    }


def reduce_linked(work: dict[str, Any], corpus: set[str] | None) -> dict[str, Any]:
    """An Indian work cited by / citing ours: id, year, its Indian institutions, and for citers
    which of our works it cites."""
    institutions: dict[str, list] = {}
    for authorship in work.get("authorships") or []:
        for inst in authorship.get("institutions") or []:
            if inst.get("country_code") == "IN":
                inst_id = short_id(inst.get("id"))
                lineage = sorted({short_id(item) for item in inst.get("lineage") or []} | {inst_id})
                institutions[inst_id] = [inst.get("display_name") or "", lineage]
    record: dict[str, Any] = {"id": short_id(work.get("id")), "year": work.get("publication_year"),
                              "i": [[inst_id, *rest] for inst_id, rest in institutions.items()]}
    if corpus is not None:
        record["c"] = [short_id(ref) for ref in work.get("referenced_works") or [] if short_id(ref) in corpus]
    return record


# ---------------------------------------------------------------- steps

def resolve_field_ids(client: OpenAlexClient, run: Run | None = None) -> dict[str, str]:
    """Names in config [scope] include_fields -> OpenAlex field ids (saved as fields.json in the cache)."""
    wanted = CONFIG["scope"]["include_fields"]
    data = client.get("/fields", {"per-page": 50, "select": "id,display_name"})
    ids = {item["display_name"]: short_id(item["id"]) for item in data["results"]}
    missing = [name for name in wanted if name not in ids]
    if missing:
        raise SystemExit(f"config scope.include_fields has unknown OpenAlex field names: {missing}\nvalid: {sorted(ids)}")
    resolved = {name: ids[name] for name in wanted}
    if run is not None:
        run.path("fields.json").write_text(json.dumps(resolved, indent=2))
    return resolved


def scope_filter(field_ids: Iterable[str], start_year: int, end_year: int) -> str:
    """The filters our own papers must pass (years, science/engineering field, paper type)."""
    fields = "|".join(sorted(field_ids, key=int))
    types = "|".join(CONFIG["collection"]["work_types"])
    return f"publication_year:{start_year}-{end_year},primary_topic.field.id:{fields},type:{types}"


def run_scope(client: OpenAlexClient, run: Run) -> str:
    return scope_filter(resolve_field_ids(client, run).values(), run.start_year, run.end_year)


def works_filter(client: OpenAlexClient, run: Run) -> str:
    return f"authorships.institutions.lineage:{'|'.join(TARGET_IDS)},{run_scope(client, run)}"


def step_works(client: OpenAlexClient, run: Run) -> None:
    state = load_state(run, "works")
    if state.get("done"):
        print("works: already complete", state)
        return
    filter_ = works_filter(client, run)
    if state and state.get("filter") != filter_:
        raise SystemExit("works: config/years changed since this cache was started. Delete "
                         f"{run.raw_dir} or pass a different --cache-dir.")
    cursor, pages, fetched = state.get("cursor", "*"), state.get("pages", 0), state.get("records", 0)
    for results, next_cursor, total in client.paginate("/works", {"filter": filter_, "select": WORK_FIELDS}, cursor):
        append_jsonl(run.path("works.jsonl"), (reduce_work(work) for work in results))
        pages += 1
        fetched += len(results)
        state = {"filter": filter_, "cursor": next_cursor, "pages": pages, "records": fetched,
                 "expected": total, "done": not next_cursor}
        save_state(run, "works", state)
        print(f"works: {fetched}/{total}", flush=True)
    state["done"] = True
    save_state(run, "works", state)


def corpus_works(run: Run) -> dict[str, dict[str, Any]]:
    works = {}
    for record in read_jsonl(run.path("works.jsonl")):
        works[record["id"]] = record  # a repeated id (after a resumed page) simply overwrites
    return works


def need(run: Run, step: str) -> None:
    if not load_state(run, step).get("done"):
        raise SystemExit(f"run the '{step}' step first")


def step_full_authors(client: OpenAlexClient, run: Run) -> None:
    need(run, "works")
    truncated = sorted(work_id for work_id, work in corpus_works(run).items() if work["truncated"])
    out = run.path("full_authors.jsonl")
    done = {record["id"] for record in read_jsonl(out)}
    todo = [work_id for work_id in truncated if work_id not in done]
    print(f"full-authors: {len(truncated)} works with {LIST_AUTHORSHIP_LIMIT}+ authors, {len(todo)} to fetch")
    for count, work_id in enumerate(todo, 1):
        work = client.get(f"/works/{work_id}", {"select": "id,authorships"})
        authors, institutions = reduce_authorships(work.get("authorships"))
        append_jsonl(out, [{"id": work_id, "n_auth": len(work.get("authorships") or []),
                            "authors": authors, "insts": institutions}])
        if count % 25 == 0 or count == len(todo):
            print(f"full-authors: {len(done) + count}/{len(truncated)}", flush=True)
    save_state(run, "full-authors", {"works": len(truncated), "done": True})


def step_linked(client: OpenAlexClient, run: Run) -> None:
    """Indian works cited by ours (`cited_by:` filter) and Indian works citing ours (`cites:`).

    Deliberately not limited to our years, fields or paper types: `cites_indian_inst` and
    `cited_by_indian_inst` are about any paper from another Indian institution."""
    need(run, "works")
    types = set(CONFIG["collection"]["work_types"])
    ids = sorted(work_id for work_id, work in corpus_works(run).items() if work["type"] in types)
    corpus_set = set(ids)
    chunks = batches(ids, CONFIG["collection"]["batch_size"])
    for kind, filter_name, fields in (("refs", "cited_by", LINKED_FIELDS), ("citers", "cites", CITER_FIELDS)):
        step = f"linked-{kind}"
        state = load_state(run, step)
        if state.get("done"):
            print(f"{step}: already complete")
            continue
        out = run.path(f"{kind}.jsonl")
        for index in range(state.get("next_batch", 0), len(chunks)):
            params = {"filter": f"{filter_name}:{'|'.join(chunks[index])},authorships.institutions.country_code:IN",
                      "select": fields}
            records = []
            for results, _, _ in client.paginate("/works", params):
                records += [reduce_linked(work, corpus_set if kind == "citers" else None) for work in results]
            append_jsonl(out, records)
            save_state(run, step, {"next_batch": index + 1, "batches": len(chunks), "done": False})
            if (index + 1) % 10 == 0 or index + 1 == len(chunks):
                print(f"{step}: batch {index + 1}/{len(chunks)}", flush=True)
        save_state(run, step, {"next_batch": len(chunks), "batches": len(chunks), "done": True})
    save_state(run, "linked", {"done": True})


def affiliated_author_ids(run: Run) -> list[str]:
    ids: set[str] = set()
    full = {record["id"]: record for record in read_jsonl(run.path("full_authors.jsonl"))}
    for work_id, work in corpus_works(run).items():
        for author in (full[work_id]["authors"] if work_id in full else work["authors"]):
            if author["id"]:
                ids.add(author["id"])
    return sorted(ids)


def step_authors(client: OpenAlexClient, run: Run) -> None:
    need(run, "works")
    ids = affiliated_author_ids(run)
    chunks = batches(ids, CONFIG["collection"]["batch_size"])
    state = load_state(run, "authors")
    if state.get("done"):
        print("authors: already complete")
        return
    for index in range(state.get("next_batch", 0), len(chunks)):
        data = client.get("/authors", {"filter": f"ids.openalex:{'|'.join(chunks[index])}",
                                       "select": AUTHOR_FIELDS, "per_page": 200})
        append_jsonl(run.path("authors.jsonl"), ({
            "id": short_id(a.get("id")), "name": a.get("display_name") or "", "orcid": a.get("orcid") or "",
            "works_count": a.get("works_count") or 0, "cited_by_count": a.get("cited_by_count") or 0,
            "h_index": (a.get("summary_stats") or {}).get("h_index"),
            "i10_index": (a.get("summary_stats") or {}).get("i10_index"),
        } for a in data["results"]))
        save_state(run, "authors", {"next_batch": index + 1, "batches": len(chunks), "done": False})
        if (index + 1) % 10 == 0 or index + 1 == len(chunks):
            print(f"authors: batch {index + 1}/{len(chunks)}", flush=True)
    save_state(run, "authors", {"next_batch": len(chunks), "batches": len(chunks), "done": True})


def step_sources(client: OpenAlexClient, run: Run) -> None:
    need(run, "works")
    ids = sorted({work["source"]["id"] for work in corpus_works(run).values() if work["source"]["id"]})
    chunks = batches(ids, CONFIG["collection"]["batch_size"])
    state = load_state(run, "sources")
    if state.get("done"):
        print("sources: already complete")
        return
    for index in range(state.get("next_batch", 0), len(chunks)):
        data = client.get("/sources", {"filter": f"ids.openalex:{'|'.join(chunks[index])}",
                                       "select": SOURCE_FIELDS, "per_page": 200})
        append_jsonl(run.path("sources.jsonl"), ({
            "id": short_id(s.get("id")), "name": s.get("display_name") or "", "issn_l": s.get("issn_l") or "",
            "issn": s.get("issn") or [], "type": s.get("type") or "",
            "mean_citedness_2y": (s.get("summary_stats") or {}).get("2yr_mean_citedness"),
        } for s in data["results"]))
        save_state(run, "sources", {"next_batch": index + 1, "batches": len(chunks), "done": False})
    save_state(run, "sources", {"next_batch": len(chunks), "batches": len(chunks), "done": True})
    print(f"sources: {len(ids)} journals/venues")


def step_core(run: Run | None = None) -> None:
    target = resolve(CONFIG["quartile"]["core_file"])
    if target.exists() and target.stat().st_size > 0:
        print(f"core: {target} already present")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    url = CORE_URL.format(source=CONFIG["quartile"]["core_source"])
    try:
        response = requests.get(url, timeout=60, headers={"User-Agent": "DPCN-Group16-collector/1.0"})
        response.raise_for_status()
    except requests.RequestException as error:
        print(f"core: download failed ({error}). Conference ranks will be blank. Download the CSV by hand from "
              f"{url} and save it as {target}")
        return
    if "csv" not in response.headers.get("content-type", ""):
        print(f"core: unexpected response type {response.headers.get('content-type')}; conference ranks will be blank")
        return
    target.write_bytes(response.content)
    rows = sum(1 for _ in csv.reader(response.text.splitlines()))
    print(f"core: saved {rows} ranked conferences to {target}")


def write_info(run: Run, client: OpenAlexClient) -> None:
    info = {
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "years": f"{run.start_year}-{run.end_year}",
        "institutions": {name: s["openalex_id"] for name, s in INSTITUTIONS.items()},
        "include_fields": CONFIG["scope"]["include_fields"],
        "work_types": CONFIG["collection"]["work_types"],
        "works_filter": load_state(run, "works").get("filter"),
        "api_key_used": bool(client.api_key),
        "note": "Citation counts and author ids are as of collected_at_utc; OpenAlex changes continuously.",
    }
    run.path("collection_info.json").write_text(json.dumps(info, indent=2))


def collect(run: Run, steps: Iterable[str] = STEPS) -> int:
    """Run the requested steps in order. Returns 0, or 2 when the OpenAlex budget ran out."""
    client = OpenAlexClient()
    print(f"OpenAlex API key {'found' if client.api_key else 'not set (works, but slower daily limit)'}; cache: {run.raw_dir}")
    started = time.monotonic()
    try:
        for step in steps:
            if step == "works":
                step_works(client, run)
            elif step == "full-authors":
                step_full_authors(client, run)
            elif step == "linked":
                step_linked(client, run)
            elif step == "authors":
                step_authors(client, run)
            elif step == "sources":
                step_sources(client, run)
            elif step == "core":
                step_core(run)
    except BudgetExhausted as error:
        print(f"\nSTOPPED: OpenAlex request budget used up after {client.requests_made} requests. Progress is saved; "
              f"run the same command again later, or set OPENALEX_API_KEY (free). Detail: {error}")
        return 2
    write_info(run, client)
    print(f"collection finished: {client.requests_made} requests in {time.monotonic() - started:.0f}s")
    return 0
