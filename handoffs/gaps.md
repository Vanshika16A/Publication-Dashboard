# Remaining gaps and duplicates

Counts from build 20261012T134558Z (162,361 rows, 67,529 papers). Every number is computed by
`python -m dpcn_mapping.audit` (runs with each build); latest values are in the newest
`data/builds/<build_id>/audit.md`, review lists in `data/builds/latest/`. Statuses are kept by
hand here.

✅ done or settled (incl. accepted limitations) · 🟡 partly done · ❌ not done or not fixable

## A. Missing values

| | # | Gap | Rows | Papers | Fixable? |
|---|---|---|---|---|---|
| ❌ | 1 | Journal `quartile` blank | 31,553 | 15,626 | Mostly no: 12,212 in journals SCImago never indexes, 1,831 "-" that year, 127 no ISSN. 1,456 in SCImago in other years only (keep blank). |
| ❌ | 2 | Conference CORE rank blank | 9,789 | 4,623 | Partly: only 1,580 computer science papers can have one. |
| 🟡 | 3 | `doi` blank | 1,128 | 651 | Crossref title search done (D-024): 0 filled; most of these venues register no DOIs. 8 DOI-less copies and 373 non-technical papers dropped; 11 weak candidates unreviewed. |
| ❌ | 4 | `journal_name` blank | 1,090 | 587 | Possibly, other OpenAlex locations or Crossref. |
| ❌ | 5 | `issn` blank (journals) | 319 | 134 | Possibly, journal-name lookup. |
| ❌ | 6 | `title` blank | 1 | 1 | By hand. |
| ✅ | 7 | `cites_indian_inst` without reference list | 16,738 | 9,064 | Done: blank = unknown (D-008). |
| ❌ | 8 | No OpenAlex author ID | 11,836 | – | No; no h-index. |
| ❌ | 9 | Author IDs without a profile | 340 IDs | – | Needs a new snapshot. |
| ❌ | 10 | No research area | – | 65 | No. |
| ❌ | 11 | Author list capped at 5,000 | – | 6 | No (OpenAlex limit). |
| ❌ | 12 | No department; no faculty flag | all | – | Faculty rosters (D-007). |
| 🟡 | 22 | `coauthor_institutes` empty | 45.3% of (paper, institution) pairs | – | Partly: 90% truly empty (same institution, single author, foreign only); 3,069 pairs `unknown_affiliation`. Reviewed ROR matches applied (D-015). |

## B. Duplicates

| | # | Issue | Size | Status |
|---|---|---|---|---|
| ✅ | 13 | Identical rows | 321 | Done: dropped (D-005) |
| ✅ | 14 | Same title and year | 15 groups left | Done: 420 copies dropped, 12 authors carried over (D-019); the 15 left are different papers. 8 more DOI-less copies found by Crossref dropped (D-024) |
| ✅ | 15 | One person, several author IDs | 674 ORCIDs on 1,444 IDs | Done: `person_id` in enriched file (D-020) |
| ✅ | 16 | Namesakes merged under one ID | est. 150–250 IDs | Limitation, taken as published (D-016) |
| ✅ | 17 | Same DOI on two works | 0 left | Done (D-012) |

## C. Scope and ror

| | # | Issue | Size | Status |
|---|---|---|---|---|
| ❌ | 18 | DU medical colleges | 32,577 DU rows | Decision open (D-004) |
| 🟡 | 19 | UoH affiliation review | 145 rows | Partly: 137 removed, 7 kept, 1 open (D-018); 10 rows moved to the non-technical list (D-023) |
| 🟡 | 20 | JNU affiliation review | 92 rows | Partly: 34 removed, 45 kept, 13 open (D-018); 78 rows moved to the non-technical list (D-023); 29 rows still mention a confusable name |
| 🟡 | 21 | Hyperauthor papers | 1,147 with 100+ authors, 945 with 1,000+ | Flagged, all kept; network treatment pending (D-006) |
| ✅ | 23 | ROR matches inside DU/UoH | 20 authorships | Done: all 20 rows added after verification and reviewer confirmation (D-022) |
| 🟡 | 24 | Non-technical scope | 3,302 papers dropped | Partly: 2,842 wholly from non-technical units (D-021), 460 reviewed by topic (D-023: 87, plus 373 without a DOI, D-024); rest of scope open (todo.md) |
| 🟡 | 25 | Biography-style affiliations | 111 rows checked with Crossref | Partly: emeritus kept, alumni to drop; former/retired undecided (todo.md) |
