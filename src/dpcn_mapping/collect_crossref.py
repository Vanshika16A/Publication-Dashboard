"""Check biography-style UoH/JNU affiliations against the publisher's Crossref record.

    python -m dpcn_mapping.collect_crossref           # fetch (resumable) and write the check file
    python -m dpcn_mapping.collect_crossref --check   # rewrite the check file, no network

Some OpenAlex affiliations are "about the author" notes ("holds a PhD from JNU", "Former
Professor, JNU"), so the named institution may not be the affiliation reported on the paper.
Rows in scope: UoH/JNU rows of the latest enriched file whose raw affiliation matches
`audit.biography`, plus the rows of the authors in EXTRA_AUTHORS. For each DOI the Crossref
work record is fetched once (`api.crossref.org/works/<doi>`, anonymous; no email or personal
data sent) and stored raw. The check file lists, per row, the affiliation(s) the publisher
deposited for that author, so a person can compare. Nothing here changes the dataset.

Output in data/external/crossref/<RUN_DATE>/: crossref_works.jsonl (raw responses),
affiliation_check.csv (derived), MANIFEST.json (written last, with sha256 of both).
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
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

from .config import CONFIG, ENRICHED, ROOT

RUN_DATE = "2026-10-09"
OUT = ROOT / "data" / "external" / "crossref" / RUN_DATE
RAW = OUT / "crossref_works.jsonl"
CHECK = OUT / "affiliation_check.csv"
EXTRA_AUTHORS = {"A5062398960"}  # Veerendra Kumar: CHESS (DRDO) linked to UoH
INSTITUTIONS = ("University of Hyderabad", "Jawaharlal Nehru University")
PAUSE_SECONDS = 1.0


def rows_in_scope() -> pd.DataFrame:
    frame = pd.read_csv(ENRICHED, dtype=str, keep_default_na=False)
    frame = frame[frame["institution"].isin(INSTITUTIONS)]
    biography = frame["raw_affiliation"].str.contains(CONFIG["audit"]["biography"], flags=re.I, regex=True)
    return frame[biography | frame["openalex_author_id"].isin(EXTRA_AUTHORS)]


def doi_key(doi: str) -> str:
    return doi.lower().removeprefix("https://doi.org/")


def fetched() -> dict[str, dict]:
    records = {}
    if RAW.exists():
        for line in RAW.open():
            record = json.loads(line)
            records[record["doi"]] = record  # the last record per DOI wins
    return records


def fetch(dois: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    done = fetched()
    todo = [doi for doi in dois if doi not in done or done[doi]["http_status"] not in (200, 404)]
    session = requests.Session()
    session.headers["User-Agent"] = "DPCN-Group16/1.0"
    with RAW.open("a") as handle:
        for index, doi in enumerate(todo, 1):
            for attempt in range(4):
                try:
                    response = session.get(f"https://api.crossref.org/works/{quote(doi, safe='/')}", timeout=60)
                except requests.RequestException as error:
                    status, body = None, str(error)
                else:
                    status = response.status_code
                    body = response.json() if status == 200 else response.text[:500]
                if status in (200, 404):
                    break
                time.sleep(5 * (attempt + 1))
            handle.write(json.dumps({"doi": doi, "requested_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                                     "http_status": status, "response": body}) + "\n")
            handle.flush()
            print(f"crossref: {index}/{len(todo)} {doi} -> {status}", flush=True)
            time.sleep(PAUSE_SECONDS)


def fold(text: str) -> str:
    return re.sub(r"[^a-z ]", "", unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower())


def find_author(authors: list[dict], name: str) -> dict | None:
    """The Crossref author whose family name is the row author's last name, preferring a matching first initial."""
    parts = fold(name).split()
    if not parts:
        return None
    family = [a for a in authors if fold(a.get("family", "")).replace(" ", "") == parts[-1]
              or parts[-1] in fold(a.get("family", "")).split()]
    initial = [a for a in family if fold(a.get("given", ""))[:1] == parts[0][:1]]
    return (initial or family or [None])[0]


def write_check(scope: pd.DataFrame) -> None:
    records = fetched()
    out = []
    for row in scope.to_dict("records"):
        record = records.get(doi_key(row["doi"])) if row["doi"] else None
        if not row["doi"]:
            result, deposited, matched = "no DOI", "", ""
        elif record is None or record["http_status"] != 200:
            result, deposited, matched = f"not fetched ({record and record['http_status']})", "", ""
        else:
            author = find_author(record["response"]["message"].get("author") or [], row["author"])
            if author is None:
                result, deposited, matched = "author not found in Crossref", "", ""
            else:
                names = [item.get("name", "") for item in author.get("affiliation") or []]
                matched = f"{author.get('given', '')} {author.get('family', '')}".strip()
                deposited = " | ".join(names)
                result = "affiliation deposited" if names else "no affiliation deposited"
        out.append({"openalex_work_id": row["openalex_work_id"], "doi": row["doi"], "institution": row["institution"],
                    "author": row["author"], "openalex_raw_affiliation": row["raw_affiliation"],
                    "crossref_author": matched, "crossref_result": result, "crossref_affiliation": deposited})
    pd.DataFrame(out).to_csv(CHECK, index=False)
    counts = pd.DataFrame(out)["crossref_result"].value_counts().to_dict()
    manifest = {
        "run_date": RUN_DATE, "endpoint": "https://api.crossref.org/works/<doi>", "anonymous": True,
        "scope": "UoH/JNU rows matching audit.biography, plus EXTRA_AUTHORS", "rows": len(out),
        "dois": scope["doi"].replace("", pd.NA).dropna().nunique(), "results": counts,
        "files_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (RAW, CHECK) if path.exists()},
    }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{CHECK.relative_to(ROOT)}: {len(out)} rows; {counts}")


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="only rewrite the check file from saved responses")
    args = parser.parse_args(argv)
    scope = rows_in_scope()
    if not args.check:
        fetch(sorted({doi_key(doi) for doi in scope["doi"] if doi}))
    OUT.mkdir(parents=True, exist_ok=True)
    write_check(scope)


if __name__ == "__main__":
    main(sys.argv[1:])
