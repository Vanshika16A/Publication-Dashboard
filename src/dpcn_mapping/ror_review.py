"""Write the manual review list of ROR matches (D-015).

    python -m dpcn_mapping.ror_review

ROR's `chosen` flag alone is not precise enough: it often picks a generic name contained in a
longer one ("Institute of Medical Sciences" for "Kalinga Institute of Medical Sciences"). A
match becomes a review candidate only when one comma- or semicolon-separated part of the raw
affiliation string equals one of the chosen organisation's ROR names (any name type except
acronyms), ignoring case and punctuation, and the organisation's name does not start with
"Department of" or "Ministry of" (such names are usually a unit of a university, not the
national body ROR has).

Candidates go to reviews/ror_matches.csv with an empty `decision` column. A reviewer writes
`yes` or `no` there; the build uses only `yes` rows (ror.review_file). Rerunning keeps every
existing decision and note, adds new candidates, and drops candidates that no longer qualify.
Inputs are the raw files written by collect_ror; nothing is downloaded.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .config import CONFIG, ROOT

REVIEW_COLUMNS = ["decision", "note", "affiliation", "ror_name", "ror_city", "ror_country",
                  "ror_id", "openalex_id", "openalex_name"]
GENERIC_PREFIXES = ("department of", "dept of", "ministry of")


def normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def is_candidate(affiliation: str, organisation: dict[str, Any]) -> bool:
    names = [n["value"] for n in organisation.get("names", []) if "acronym" not in n.get("types", [])]
    display = next((n["value"] for n in organisation.get("names", []) if "ror_display" in n.get("types", [])), "")
    if not names or normalise(display).startswith(GENERIC_PREFIXES):
        return False
    parts = {normalise(part) for part in re.split(r"[,;]", affiliation) if part.strip()}
    return any(normalise(name) in parts for name in names)


def candidates(ror_dir: Path) -> list[dict[str, str]]:
    institutions = {}
    for line in (ror_dir / "openalex_institutions.jsonl").open():
        record = json.loads(line)
        if isinstance(record.get("response"), dict):
            institutions[record["ror_id"]] = record["response"]
    rows: dict[str, dict[str, str]] = {}
    for line in (ror_dir / "ror_responses.jsonl").open():
        record = json.loads(line)  # the last record per string wins, as in collect_ror
        response = record.get("response")
        items = response.get("items", []) if isinstance(response, dict) else []
        chosen = next((item for item in items if item.get("chosen")), None)
        rows.pop(record["affiliation"], None)
        if chosen is None or not is_candidate(record["affiliation"], chosen["organization"]):
            continue
        organisation = chosen["organization"]
        location = ((organisation.get("locations") or [{}])[0].get("geonames_details") or {})
        openalex = institutions.get(organisation["id"]) or {}
        rows[record["affiliation"]] = {
            "decision": "", "note": "",
            "affiliation": record["affiliation"],
            "ror_name": next((n["value"] for n in organisation["names"] if "ror_display" in n.get("types", [])), ""),
            "ror_city": location.get("name", ""),
            "ror_country": location.get("country_code", ""),
            "ror_id": organisation["id"],
            "openalex_id": (openalex.get("id") or "").rsplit("/", 1)[-1],
            "openalex_name": openalex.get("display_name", ""),
        }
    return sorted(rows.values(), key=lambda row: (row["ror_name"].lower(), row["affiliation"]))


def main() -> None:
    settings = CONFIG["ror"]
    ror_dir = (ROOT / settings["matches_file"]).parent
    review_path = ROOT / settings["review_file"]
    previous: dict[tuple[str, str], dict[str, str]] = {}
    if review_path.exists():
        with review_path.open(newline="") as handle:
            previous = {(row["affiliation"], row["ror_id"]): row for row in csv.DictReader(handle)}
    rows = candidates(ror_dir)
    for row in rows:
        old = previous.get((row["affiliation"], row["ror_id"]))
        if old:
            row["decision"], row["note"] = old["decision"], old["note"]
    review_path.parent.mkdir(parents=True, exist_ok=True)
    with review_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    decided = sum(1 for row in rows if row["decision"].strip())
    print(f"{review_path.relative_to(ROOT)}: {len(rows)} candidates, {decided} decided, "
          f"{len(rows) - decided} to review")


if __name__ == "__main__":
    main()
