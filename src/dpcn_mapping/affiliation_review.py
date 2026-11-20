"""Write the affiliation review lists for UoH and JNU (D-018).

    python -m dpcn_mapping.affiliation_review

OpenAlex sometimes links an author to an assigned institution that the affiliation text does
not support (e.g. "OU, Hyderabad" = Osmania University linked to UoH). A row of the latest
enriched file becomes a review candidate when its raw affiliation does not name the institution
(`audit.uoh_name`, `audit.jnu_name`), reads like a biography (`audit.biography`: alumni,
former, retired or emeritus), or, for JNU, names a confusable one (`audit.jnu_confusable`). Candidates go to the files in `reviews.affiliation_files` with an empty
`decision`; a reviewer writes `yes` (keep) or `no` (remove that author's link to the institution
on that paper). Rerunning keeps every existing row and decision, so rows already removed by a
`no` stay listed, and adds new candidates. Papers in `reviews.non_technical_file` are dropped
from the dataset (D-023) and never listed.
"""

from __future__ import annotations

import csv
import re

import pandas as pd

from .config import CONFIG, ENRICHED, ROOT

COLUMNS = ["decision", "note", "openalex_work_id", "openalex_author_id", "author", "institution",
           "affiliation_institution_ids", "raw_affiliation", "title", "year"]
RULES = {  # institution -> (file suffix, name pattern, confusable pattern or None)
    # uoh_other is not used alone: it matches many genuine UoH rows ("School of Engineering").
    "University of Hyderabad": ("uoh", "uoh_name", None),
    "Jawaharlal Nehru University": ("jnu", "jnu_name", "jnu_confusable"),
}

def key(row: dict[str, str]) -> tuple[str, str, str]:
    return row["openalex_work_id"], row["openalex_author_id"] or row["author"], row["institution"]


def main() -> None:
    audit = CONFIG["audit"]
    enriched = pd.read_csv(ENRICHED, dtype=str, keep_default_na=False)
    non_technical = ROOT / CONFIG["reviews"].get("non_technical_file", "")
    if CONFIG["reviews"].get("non_technical_file") and non_technical.exists():
        dropped = set(pd.read_csv(non_technical, dtype=str)["openalex_work_id"])
        enriched = enriched[~enriched["openalex_work_id"].isin(dropped)]
    files = {suffix: name for name in CONFIG["reviews"]["affiliation_files"]
             for suffix in ("uoh", "jnu") if name.endswith(f"_{suffix}.csv")}
    for institution, (suffix, name_rule, confusable_rule) in RULES.items():
        path = ROOT / files[suffix]
        existing: dict[tuple[str, str, str], dict[str, str]] = {}
        if path.exists():
            with path.open(newline="") as handle:
                existing = {key(row): row for row in csv.DictReader(handle)}
        rows = enriched[enriched["institution"] == institution]
        names = rows["raw_affiliation"].str.contains(audit[name_rule], flags=re.I, regex=True)
        confusable = (rows["raw_affiliation"].str.contains(audit[confusable_rule], flags=re.I, regex=True)
                      if confusable_rule else False)
        biography = rows["raw_affiliation"].str.contains(audit["biography"], flags=re.I, regex=True)
        candidates = rows[~names | confusable | biography]
        added = 0
        for record in candidates[COLUMNS[2:]].to_dict("records"):
            if key(record) not in existing:
                existing[key(record)] = {"decision": "", "note": "", **record}
                added += 1
        ordered = sorted(existing.values(), key=lambda row: (row["decision"] != "", row["openalex_work_id"], row["author"]))
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows({column: row.get(column, "") for column in COLUMNS} for row in ordered)
        open_rows = sum(1 for row in existing.values() if not row["decision"].strip())
        print(f"{path.relative_to(ROOT)}: {len(existing)} rows, {added} new, {open_rows} to review")


if __name__ == "__main__":
    main()
