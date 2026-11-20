"""Crossref check of reviewed ROR matches that point inside an assigned institution (D-022).

    python -m dpcn_mapping.verify_ror_rows          # fetch (resumable) and write the check file
    python -m dpcn_mapping.verify_ror_rows --check  # rewrite the check file, no network

Input: `data/builds/latest/ror_assigned_institution_matches.csv` (authorships OpenAlex linked to
no institution whose reviewed ROR match is JNU, UoH or DU). For each one, the author and DOI are
read from the snapshot, the Crossref record is fetched once per DOI (anonymous) and stored raw,
and the check file lists the affiliation the publisher deposited for that author. Nothing here
changes the dataset; the decision is recorded by hand in `reviews/ror_assigned_rows.csv`.

Output in data/external/crossref/<RUN_DATE>/: ror_rows_works.jsonl (raw), ror_rows_check.csv.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from urllib.parse import quote

import duckdb
import pandas as pd
import requests

from .collect_crossref import doi_key, find_author
from .config import CONFIG, LISTS, ROOT

RUN_DATE = "2026-10-12"
OUT = ROOT / "data" / "external" / "crossref" / RUN_DATE
RAW = OUT / "ror_rows_works.jsonl"
CHECK = OUT / "ror_rows_check.csv"


def candidates() -> pd.DataFrame:
    matches = pd.read_csv(LISTS / "ror_assigned_institution_matches.csv", dtype=str)
    works = ROOT / "data" / "parquet" / CONFIG["build"]["snapshot_id"] / "works.parquet"
    con = duckdb.connect()
    con.register("m", matches)
    return con.sql(f"""
        SELECT m.openalex_work_id, m.institution, a.author.display_name AS author,
               replace(a.author.id, 'https://openalex.org/', '') AS openalex_author_id,
               coalesce(w.doi, '') AS doi, w.primary_location.landing_page_url AS landing_page, m.raw_affiliation
        FROM m JOIN read_parquet('{works}') w ON replace(w.id, 'https://openalex.org/', '') = m.openalex_work_id,
             unnest(w.authorships) t(a)
        WHERE len(a.institutions) = 0 AND array_to_string(a.raw_affiliation_strings, '; ') = m.raw_affiliation
    """).df()


def fetch(dois: list[str]) -> dict[str, dict]:
    OUT.mkdir(parents=True, exist_ok=True)
    records = {}
    if RAW.exists():
        records = {json.loads(line)["doi"]: json.loads(line) for line in RAW.open()}
    session = requests.Session()
    session.headers["User-Agent"] = "DPCN-Group16/1.0"
    with RAW.open("a") as handle:
        for doi in dois:
            if doi in records and records[doi]["http_status"] in (200, 404):
                continue
            response = session.get(f"https://api.crossref.org/works/{quote(doi, safe='/')}", timeout=60)
            record = {"doi": doi, "requested_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                      "http_status": response.status_code,
                      "response": response.json() if response.status_code == 200 else response.text[:500]}
            handle.write(json.dumps(record) + "\n")
            records[doi] = record
            print(f"crossref: {doi} -> {response.status_code}", flush=True)
            time.sleep(1.0)
    return records


def main(argv: list[str]) -> None:
    rows = candidates()
    dois = sorted({doi_key(doi) for doi in rows["doi"] if doi})
    records = fetch(dois) if "--check" not in argv else {
        json.loads(line)["doi"]: json.loads(line) for line in RAW.open()}
    out = []
    for row in rows.to_dict("records"):
        record = records.get(doi_key(row["doi"])) if row["doi"] else None
        if not row["doi"]:
            result, deposited = "no DOI", ""
        elif record is None or record["http_status"] != 200:
            result, deposited = f"not in Crossref ({record and record['http_status']})", ""
        else:
            author = find_author(record["response"]["message"].get("author") or [], row["author"])
            names = [item.get("name", "") for item in (author or {}).get("affiliation") or []]
            result = ("author not found" if author is None else
                      "affiliation deposited" if names else "no affiliation deposited")
            deposited = " | ".join(names)
        out.append({**row, "crossref_result": result, "crossref_affiliation": deposited})
    pd.DataFrame(out).to_csv(CHECK, index=False)
    print(f"{CHECK.relative_to(ROOT)}: {len(out)} rows; {pd.DataFrame(out)['crossref_result'].value_counts().to_dict()}")


if __name__ == "__main__":
    main(sys.argv[1:])
