"""Estimate how many OpenAlex author IDs may merge several people (gap #16, D-016).

    .venv/bin/python scripts/estimate_merged_authors.py

OpenAlex gives each author ID one name and one ORCID, so a merge of namesakes is invisible in
those fields. The signal used here: an ID that publishes from departments unrelated to its main
one. The department is taken from the raw affiliation text ("Department/School/Centre of X");
departments are related when they share a content word after removing spelling variants
(paediatrics/pediatrics, sciences/science). Hyperauthor papers are left out. This only counts
candidates; it changes no data. Reads the enriched file of the latest build.
"""

import re

import duckdb

ENRICHED = "data/processed/group16_data_enriched.csv"
STOP = {"and", "of", "for", "the", "in", "science", "sciences", "studies", "study", "applied",
        "advanced", "school", "centre", "center", "department", "medical", "lady", "hardinge", "institute"}


def words(department: str) -> set[str]:
    department = department.replace("ae", "e").replace("enviromental", "environmental")
    return {re.sub(r"s$", "", w) for w in re.findall(r"[a-z]+", department) if w not in STOP and len(w) > 3}


def main() -> None:
    con = duckdb.connect()
    rows = con.sql(rf"""
        WITH d AS (
            SELECT openalex_author_id AS aid, openalex_work_id AS wid,
                   trim(regexp_replace(regexp_replace(lower(regexp_extract(raw_affiliation,
                       '(?i)(?:department|dept\.?|school|centre|center) (?:of|for) ([a-z ,&]+?)(?:,|$| and technology| university| college| jawaharlal| delhi)', 1)),
                       '&', 'and', 'g'), '\s+', ' ', 'g')) AS dept
            FROM read_csv_auto('{ENRICHED}', sample_size=-1)
            WHERE openalex_author_id IS NOT NULL AND NOT is_hyperauthor),
        a AS (SELECT aid, dept, count(DISTINCT wid) AS papers FROM d WHERE dept <> '' GROUP BY ALL)
        SELECT aid, list(dept ORDER BY papers DESC, dept), list(papers ORDER BY papers DESC, dept)
        FROM a GROUP BY aid""").fetchall()
    unrelated = []
    for _, depts, papers in rows:
        main_words = words(depts[0])
        unrelated.append(sum(n for d, n in zip(depts[1:], papers[1:]) if words(d) and not words(d) & main_words))
    print(f"author IDs with department text: {len(rows)}")
    for threshold in (2, 3, 5):
        print(f"IDs with >= {threshold} papers in unrelated departments: {sum(u >= threshold for u in unrelated)}")


if __name__ == "__main__":
    main()
