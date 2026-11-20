"""Match unlinked raw affiliation strings to institutions with the ROR affiliation API.

    python -m dpcn_mapping.collect_ror                    # run or resume the collection
    python -m dpcn_mapping.collect_ror --retry-errors     # also refetch calls that failed
    python -m dpcn_mapping.collect_ror --rebuild-matches  # re-derive the matches, no network
    python -m dpcn_mapping.collect_ror --count            # only count the strings in scope

Some OpenAlex authorships have no institution (`institutions == []`) but keep their
`raw_affiliation_strings`. This step collects every distinct such string from the works
the build includes (classified journal/conference, start_year-end_year; full author lists
from full_authorships.jsonl where available) in the snapshot named by build.snapshot_id,
and sends each one, unchanged, to the ROR v2 affiliation matcher. A string is "matched"
only when ROR marks an item `chosen: true`; the unchosen top hit is never used. Each chosen
ROR id is resolved once to its OpenAlex institution (`/institutions/ror:<id>`).

Everything goes to data/external/ror/<RUN_DATE>/. The raw responses are appended as they
arrive and are the source of truth: ror_responses.jsonl (one line per string) and
openalex_institutions.jsonl (one line per ROR id). A rerun skips strings already in
ror_responses.jsonl. affiliation_matches.jsonl is derived from those two files alone
(--rebuild-matches), runs.jsonl logs each invocation, and MANIFEST.json is written last,
once every string in scope has a response. The sealed snapshot is only read. ROR is
called anonymously: no client ID and no personal data are sent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import requests

from .build_dataset import classify, short_id
from .collect_openalex import read_jsonl
from .config import CONFIG, END_YEAR, EXTERNAL, START_YEAR, snapshot_dir
from .openalex_client import OpenAlexClient

RUN_DATE = "2026-10-09"
OUT_DIR = EXTERNAL / "ror" / RUN_DATE
MATCHES = OUT_DIR / "affiliation_matches.jsonl"
ROR_RESPONSES = OUT_DIR / "ror_responses.jsonl"  # raw: one line per ROR call kept
OPENALEX_RESPONSES = OUT_DIR / "openalex_institutions.jsonl"  # raw: one line per OpenAlex lookup
RUNS = OUT_DIR / "runs.jsonl"
MANIFEST = OUT_DIR / "MANIFEST.json"
SNAPSHOT_ID = CONFIG["build"]["snapshot_id"]

ROR_URL = "https://api.ror.org/v2/organizations"
# https://ror.readme.io/docs/rest-api (checked 2026-10-09): 2000 requests per 5 minutes per
# IP. Client-ID registration is paused and no client-ID based limit is enforced. Responses
# carry no rate-limit headers, so we pace ourselves just under the limit.
ROR_LIMIT = "2000 requests per 5 minutes per IP (ror.readme.io/docs/rest-api); no rate-limit headers in responses"
ROR_MIN_INTERVAL = 0.16  # about 1875 requests per 5 minutes
ROR_MAX_RETRIES = 5
# ROR answers in about 0.7 s, so one connection gets only ~1.4 requests/s. A few
# connections in parallel reach the paced rate above (the limit is on the total rate).
ROR_WORKERS = 4
OPENALEX_SELECT = "id,display_name,country_code,lineage"

INDIAN_PLACES = (
    "India", "Delhi", "Hyderabad", "Mumbai", "Bombay", "Kolkata", "Calcutta", "Chennai", "Madras",
    "Bengaluru", "Bangalore", "Pune", "Ahmedabad", "Lucknow", "Kanpur", "Varanasi", "Allahabad",
    "Prayagraj", "Chandigarh", "Jaipur", "Bhopal", "Bhubaneswar", "Guwahati", "Patna", "Kharagpur",
    "Roorkee", "Noida", "Gurgaon", "Gurugram", "Thiruvananthapuram", "Trivandrum", "Kochi", "Cochin",
    "Mysore", "Mysuru", "Manipal", "Vellore", "Coimbatore", "Madurai", "Visakhapatnam", "Vijayawada",
    "Warangal", "Tirupati", "Nagpur", "Indore", "Srinagar", "Jammu", "Shimla", "Dehradun", "Aligarh",
    "Agra", "Amritsar", "Ludhiana", "Shillong", "Imphal", "Goa", "Mangalore", "Mangaluru",
    "Puducherry", "Pondicherry", "Raipur", "Ranchi", "Jodhpur", "Udaipur", "Gwalior", "Surat",
    "Vadodara", "Gandhinagar", "Silchar", "Tezpur", "Dibrugarh", "Cuttack", "Rourkela", "Dhanbad",
    "Gorakhpur", "Meerut", "Mohali", "Patiala", "Kurukshetra", "Rohtak", "Hisar", "Nainital",
    "Haridwar", "Secunderabad", "Gachibowli",
)
INDIA_PATTERN = re.compile(r"\b(" + "|".join(INDIAN_PLACES) + r")\b", re.IGNORECASE)


def mentions_india(text: str) -> bool:
    """Rough screen used only to order the run and to report a count."""
    return bool(INDIA_PATTERN.search(text))


def included_work_ids(cache: Path) -> set[str]:
    """Short ids of works the build keeps: a journal/conference type and a year in range."""
    ids = set()
    for work in read_jsonl(cache / "works.jsonl"):
        year = work.get("publication_year")
        if classify(work) and year is not None and START_YEAR <= year <= END_YEAR:
            ids.add(short_id(work["id"]))
    return ids


def _authorship_lists(cache: Path, ids: set[str]) -> Iterator[list[dict[str, Any]]]:
    """Authorships of every included work, using the full list when one was refetched."""
    full = set()
    with (cache / "full_authorships.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            # Read the id from the line prefix first, so out-of-scope 5,000-author records are not parsed.
            match = re.match(r'\{"id": "https://openalex.org/(W\d+)"', line)
            if match and match.group(1) not in ids:
                continue
            record = json.loads(line)
            work_id = short_id(record["id"])
            if work_id in ids and work_id not in full:
                full.add(work_id)
                yield record.get("authorships") or []
    for work in read_jsonl(cache / "works.jsonl"):
        work_id = short_id(work["id"])
        if work_id in ids and work_id not in full:
            yield work.get("authorships") or []


def unlinked_affiliations(cache: Path) -> list[str]:
    """Distinct raw affiliation strings of authorships with no institution, India-mentioning first."""
    ids = included_work_ids(cache)
    strings: set[str] = set()
    for authorships in _authorship_lists(cache, ids):
        for authorship in authorships:
            if not authorship.get("institutions"):
                strings.update(authorship.get("raw_affiliation_strings") or [])
    print(f"scope: {len(ids)} included works, {len(strings)} distinct unlinked affiliation strings", flush=True)
    return sorted(strings, key=lambda text: (not mentions_india(text), text))


class RorClient:
    """Thread-safe ROR client. Calls from all threads share one pacing slot, so the total
    rate stays under the limit while several calls wait on server latency at once."""

    def __init__(self) -> None:
        self._local = threading.local()
        self._lock = threading.Lock()
        self._next_slot = 0.0
        self.requests_made = 0
        self.throttled = 0

    def _session(self) -> requests.Session:
        if not hasattr(self._local, "session"):
            self._local.session = requests.Session()
            self._local.session.headers["User-Agent"] = "DPCN-Group16-research-mapping/1.0"
        return self._local.session

    def _wait_turn(self) -> None:
        with self._lock:
            slot = max(self._next_slot, time.monotonic())
            self._next_slot = slot + ROR_MIN_INTERVAL
        time.sleep(max(0.0, slot - time.monotonic()))

    def _pause_all(self, seconds: float) -> None:
        with self._lock:
            self.throttled += 1
            self._next_slot = max(self._next_slot, time.monotonic() + seconds)

    def match(self, affiliation: str) -> tuple[int | None, Any]:
        """(HTTP status, body) of the last attempt; status None when no response arrived."""
        status, body = None, None
        for attempt in range(ROR_MAX_RETRIES):
            self._wait_turn()
            try:
                response = self._session().get(ROR_URL, params={"affiliation": affiliation}, timeout=60)
            except requests.RequestException as error:
                status, body = None, {"exception": repr(error)}
                print(f"ror: {error!r}, retrying", flush=True)
                time.sleep(2 ** (attempt + 1))
                continue
            with self._lock:
                self.requests_made += 1
            status = response.status_code
            try:
                body = response.json()
            except ValueError:
                body = response.text
            if status == 200:
                break
            if status == 429:
                delay = int(response.headers.get("retry-after") or 60 * (attempt + 1))
                print(f"ror: HTTP 429, pausing all calls for {delay} s", flush=True)
                self._pause_all(delay)
                continue
            if status >= 500:
                time.sleep(2 ** (attempt + 1))
                continue
            print(f"ror: HTTP {status} for {affiliation[:80]!r}", flush=True)
            break
        return status, body


def fetch_openalex(client: OpenAlexClient, ror_id: str) -> dict[str, Any]:
    """Raw OpenAlex record for a ROR id. A 404 means OpenAlex has no institution for it."""
    path = f"/institutions/ror:{short_id(ror_id)}"
    record = {"ror_id": ror_id, "requested_at": now(), "path": path, "select": OPENALEX_SELECT}
    try:
        return {**record, "http_status": 200, "response": client.get(path, {"select": OPENALEX_SELECT})}
    except RuntimeError as error:
        found = re.search(r"HTTP (\d{3})", str(error))
        # The message never contains the API key (openalex_client strips it).
        return {**record, "http_status": int(found.group(1)) if found else None, "response": {"error": str(error)}}


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def latest(path: Path, key: str) -> dict[str, dict[str, Any]]:
    """Last raw record per key (a retry appends a newer record; older ones are kept)."""
    records: dict[str, dict[str, Any]] = {}
    for record in read_jsonl(path):
        records[record[key]] = record
    return records


def repair_tail(path: Path) -> None:
    """Remove a last line cut off by a crash, so the append-only files stay valid JSON Lines."""
    if not path.exists() or path.read_bytes().endswith(b"\n") or path.stat().st_size == 0:
        return
    lines = path.read_bytes().split(b"\n")
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(b"".join(line + b"\n" for line in lines[:-1]))
    tmp.replace(path)
    print(f"{path.name}: dropped a torn last line", flush=True)


def chosen_item(ror_response: dict[str, Any]) -> dict[str, Any] | None:
    if ror_response.get("http_status") != 200:
        return None
    return next((item for item in ror_response["response"].get("items") or [] if item.get("chosen")), None)


def ror_record(item: dict[str, Any]) -> dict[str, Any]:
    organization = item["organization"]
    names = organization.get("names") or []
    name = next((entry["value"] for entry in names if "ror_display" in entry.get("types", [])), None)
    locations = organization.get("locations") or [{}]
    return {
        "id": organization["id"],
        "name": name or (names[0]["value"] if names else None),
        "country_code": (locations[0].get("geonames_details") or {}).get("country_code"),
        "score": item.get("score"),
        "matching_type": item.get("matching_type"),
    }


def institution_record(raw: dict[str, Any]) -> dict[str, Any]:
    data = raw["response"]
    return {
        "id": short_id(data["id"]),
        "display_name": data.get("display_name"),
        "country_code": data.get("country_code"),
        "lineage": [short_id(item) for item in data.get("lineage") or []],
    }


def derive_matches() -> list[dict[str, Any]]:
    """affiliation_matches.jsonl rebuilt from the two raw files alone (no network)."""
    ror_raw = latest(ROR_RESPONSES, "affiliation")
    openalex_raw = latest(OPENALEX_RESPONSES, "ror_id")
    rows = []
    for text, raw in ror_raw.items():
        row = {"affiliation": text, "status": "error", "ror": None, "openalex_institution": None}
        if raw.get("http_status") == 200:
            item = chosen_item(raw)
            row["status"] = "no_match"
            if item:
                ror = ror_record(item)
                institution = openalex_raw.get(ror["id"])
                status = (institution or {}).get("http_status")
                if status in (200, 404):
                    row["status"] = "matched"
                    row["ror"] = ror
                    row["openalex_institution"] = institution_record(institution) if status == 200 else None
                else:
                    row["status"] = "error"  # OpenAlex lookup missing or failed; --retry-errors refetches it
        rows.append(row)
    tmp = MATCHES.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(MATCHES)
    print(f"{MATCHES.name}: {len(rows)} rows derived from raw responses", flush=True)
    return rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def line_count(path: Path) -> int:
    with path.open("rb") as handle:
        return sum(1 for _ in handle)


def write_manifest(strings: list[str], rows: list[dict[str, Any]]) -> None:
    runs = list(read_jsonl(RUNS))
    statuses: dict[str, int] = {}
    for row in rows:
        statuses[row["status"]] = statuses.get(row["status"], 0) + 1
    files = {
        path.name: {"lines": line_count(path), "sha256": sha256_file(path)}
        for path in (ROR_RESPONSES, OPENALEX_RESPONSES, MATCHES, RUNS)
    }
    manifest = {
        "date": RUN_DATE,
        "openalex_snapshot": SNAPSHOT_ID,
        "scope": f"raw_affiliation_strings of authorships with institutions == [] on works the build "
                 f"includes (classify() not None, {START_YEAR}-{END_YEAR}); full author lists from "
                 f"full_authorships.jsonl where available; strings used exactly as in the snapshot",
        "api_endpoint": f"{ROR_URL}?affiliation=<string>",
        "api_version": "ROR REST API v2, affiliation matching",
        "client_id": None,
        "acceptance_rule": "matched only when ROR marks an item chosen: true (that item is used); "
                           "no_match when no item is chosen; error when a call failed after retries",
        "openalex_resolution": f"/institutions/ror:<ror id> select={OPENALEX_SELECT}, once per ROR id",
        "derivation": "affiliation_matches.jsonl = python -m dpcn_mapping.collect_ror --rebuild-matches "
                      "(from ror_responses.jsonl and openalex_institutions.jsonl; last record per key)",
        "strings": len(rows),
        "strings_mentioning_india": sum(mentions_india(text) for text in strings),
        "status_counts": statuses,
        "matched_ror_country_IN": sum(1 for row in rows if (row["ror"] or {}).get("country_code") == "IN"),
        "matched_openalex_country_IN": sum(
            1 for row in rows if (row["openalex_institution"] or {}).get("country_code") == "IN"),
        "matched_without_openalex_institution": sum(
            1 for row in rows if row["status"] == "matched" and not row["openalex_institution"]),
        "rate_limit": ROR_LIMIT,
        "pacing_seconds_per_request": ROR_MIN_INTERVAL,
        "parallel_connections": ROR_WORKERS,
        "runs": runs,
        "run_duration_seconds": round(sum(run["seconds"] for run in runs), 1),
        "files": files,
        "written_at": now(),
    }
    tmp = MANIFEST.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(MANIFEST)
    print(f"manifest written: {MANIFEST}")


def scope() -> list[str]:
    strings = unlinked_affiliations(snapshot_dir(SNAPSHOT_ID))
    print(f"scope: {sum(mentions_india(text) for text in strings)} strings mention India or an Indian city", flush=True)
    return strings


def finish(strings: list[str]) -> None:
    rows = derive_matches()
    done = {row["affiliation"] for row in rows}
    missing = [text for text in strings if text not in done]
    if missing:
        print(f"{len(missing)} strings not fetched yet; rerun to resume (no manifest written)")
    else:
        write_manifest(strings, rows)


def append(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def run(retry_errors: bool = False) -> None:
    started, started_at = time.monotonic(), now()
    strings = scope()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in (ROR_RESPONSES, OPENALEX_RESPONSES):
        repair_tail(path)
    ror_raw = latest(ROR_RESPONSES, "affiliation")
    openalex_raw = latest(OPENALEX_RESPONSES, "ror_id")
    ok = lambda raw: raw is not None and raw.get("http_status") == 200
    todo = [text for text in strings if text not in ror_raw or (retry_errors and not ok(ror_raw[text]))]
    print(f"ror: {len(strings) - len(todo)} strings already fetched, {len(todo)} to fetch", flush=True)
    if MANIFEST.exists():
        MANIFEST.unlink()  # the files may change, so the old manifest may no longer describe them

    def resolve(ror_id: str) -> None:
        previous = openalex_raw.get(ror_id)
        if previous is None or (retry_errors and previous.get("http_status") not in (200, 404)):
            openalex_raw[ror_id] = fetch_openalex(openalex, ror_id)
            append(OPENALEX_RESPONSES, openalex_raw[ror_id])

    ror, openalex = RorClient(), OpenAlexClient()
    fetch_start = time.monotonic()
    # Chosen ROR ids from earlier runs whose OpenAlex lookup is missing (e.g. after a crash).
    for raw in list(ror_raw.values()):
        item = chosen_item(raw)
        if item:
            resolve(item["organization"]["id"])

    def query(text: str) -> dict[str, Any]:
        requested_at = now()
        status, body = ror.match(text)
        return {"affiliation": text, "requested_at": requested_at, "http_status": status, "response": body}

    # map() returns results in input order; only this thread writes files and calls OpenAlex.
    with ThreadPoolExecutor(ROR_WORKERS) as pool:
        for count, raw in enumerate(pool.map(query, todo), 1):
            append(ROR_RESPONSES, raw)
            item = chosen_item(raw)
            if item:
                resolve(item["organization"]["id"])
            if count % 100 == 0 or count == len(todo):
                rate = count / (time.monotonic() - fetch_start)
                print(f"ror: {count}/{len(todo)} ({rate:.1f}/s), {ror.throttled} throttled, "
                      f"{len(openalex_raw)} ROR ids resolved", flush=True)
    append(RUNS, {
        "started": started_at, "seconds": round(time.monotonic() - started, 1), "fetched": len(todo),
        "ror_requests": ror.requests_made, "ror_throttled": ror.throttled, "openalex_requests": openalex.requests_made,
    })
    finish(strings)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--retry-errors", action="store_true", help="refetch strings and ROR ids whose last call failed")
    parser.add_argument("--rebuild-matches", action="store_true", help="derive the matches from the raw files, no network")
    parser.add_argument("--count", action="store_true", help="only count the strings in scope")
    args = parser.parse_args()
    if args.count:
        scope()
    elif args.rebuild_matches:
        finish(scope())
    else:
        run(args.retry_errors)


if __name__ == "__main__":
    main()
