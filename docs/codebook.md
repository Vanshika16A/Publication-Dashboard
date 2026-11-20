# Codebook

How every column is derived. "OpenAlex" fields refer to the work record in the sealed
snapshot named by `build.snapshot_id`. Blank means the value could not be collected;
nothing is imputed. Decision IDs (D-xxx) refer to `docs/decisions.md`.

## data/processed/group16_data.csv (deliverable)

One row per (paper, assigned institution, affiliated author).

| Column | Type | Source / derivation |
|---|---|---|
| group | int | Constant 16 |
| institution | text | Assigned institution whose OpenAlex lineage contains one of the author's affiliations on this paper (D-001, D-004) |
| author | text | `authorships[].author.display_name` |
| title | text | `title` |
| year | int | `publication_year`, 2016–2026 |
| type | text | journal or conference (D-013) |
| journal_name | text | `primary_location.source.display_name` |
| issn | text | `primary_location.source.issn_l`, journals only |
| doi | text | `doi` (https://doi.org/ URL), repaired when OpenAlex adds junk after it (D-017); when OpenAlex has none, a Crossref DOI reviewed `yes` in `reviews/review_doi_matches.csv` (D-024) |
| citations | int | `cited_by_count` on the snapshot date |
| quartile | text | SCImago Q1–Q4 for journals, CORE A*/A/B/C for conferences (D-009) |
| coauthor_institutes | text | `; `-joined names of Indian institutions on the paper outside the row's institution (D-008); co-authors OpenAlex links to no institution count through their ROR match when enabled (D-015). Empty when none; why is in `coauthor_institutes_status` (enriched file) |
| cites_indian_inst | TRUE/FALSE/blank | A referenced work has an Indian institution outside the row's institution; blank when OpenAlex has no reference list (D-008) |
| cited_by_indian_inst | TRUE/FALSE | A citing work has an Indian institution outside the row's institution (D-008) |

## data/processed/group16_data_enriched.csv (gitignored)

Same rows and columns as the deliverable, plus:

| Column | Source / derivation |
|---|---|
| openalex_work_id, openalex_author_id | Short OpenAlex IDs (W…, A…) |
| person_id | Person key for person-level outputs (D-020): the ORCID when a reviewer confirmed this author ID as the ORCID holder, otherwise `openalex_author_id`; blank when there is none |
| author_orcid, author_position, is_corresponding | From `authorships[]` |
| raw_affiliation | `authorships[].raw_affiliation_strings`, `; `-joined |
| affiliation_institution_ids | OpenAlex IDs of the author's affiliations that placed the row in its institution (e.g. I39190216 for a Maulana Azad Medical College affiliation counted as DU) |
| openalex_work_type, source_type, source_id | `type`, `primary_location.source.type`, `.id` |
| all_issns | ISSN-L followed by every other ISSN of the source |
| oa_2yr_mean_citedness | OpenAlex `summary_stats.2yr_mean_citedness` of the venue at collection time; the impact factor shown on the dashboard (D-025) |
| quartile_source | e.g. "SCImago 2021" or "CORE ICORE2026: <title>" |
| coauthor_institute_ids | OpenAlex IDs behind `coauthor_institutes` |
| coauthor_institutes_status | Why `coauthor_institutes` is filled or empty (D-015). The first that applies: `listed` (not empty); `single_author` (the paper has one authorship); `unknown_affiliation` (some author on the paper has no institution, even after ROR matching, so the empty value may be wrong); `foreign_only` (every author has an institution and at least one institution on the paper has a country code other than IN, or none); `same_institution_only` (every institution on the paper is inside the row's institution lineage). Uses the full author list and every author's institutions, including the row author's other affiliations, as `coauthor_institutes` does, so it is the same for every row of a (paper, institution) pair |
| all_paper_institutions | Every institution on the paper, any country |
| n_authors, is_hyperauthor | Number of authorships (full list); `n_authors >= hyperauthor.flag_threshold` (D-006) |
| indian_citing_works | Number of citing works with an Indian institution outside the row's institution |
| referenced_works_count | Length of `referenced_works` (0 means OpenAlex has no reference list) |
| primary_domain / field / subfield / topic | `primary_topic` hierarchy |

## data/external/ror/<date>/affiliation_matches.jsonl (input, optional)

Named by `ror.matches_file`; used only with its `MANIFEST.json` and when
`ror.use_for_unlinked_coauthors` is true. One JSON object per distinct raw affiliation string
(exact, uncleaned): `affiliation`, `status` (matched / no_match / error), `ror` (ROR ID, name,
country, score, matching type) and `openalex_institution` (ID, display name, country code,
lineage). The build uses only `matched` entries with an `openalex_institution`, and only for
authorships OpenAlex links to no institution; they feed `coauthor_institutes`,
`coauthor_institute_ids` and `coauthor_institutes_status`, never rows, `all_paper_institutions`
or the citation flags (D-015). Origin is in `data/external/SOURCES.md`.

## reviews/review_affiliation_uoh.csv, reviews/review_affiliation_jnu.csv (input, committed, filled by hand)

Named by `reviews.affiliation_files`; written by `python -m dpcn_mapping.affiliation_review`, which
keeps earlier rows and decisions. Columns: `decision` (`yes` keep / `no` remove the link, blank =
not reviewed), `note`, then the row's work ID, author ID, author, institution, affiliation IDs,
raw affiliation, title and year. Each build lists the `no` rows it applied in
`affiliation_rejections_applied.csv` (D-018).

## reviews/review_title_duplicates.csv, reviews/review_split_authors.csv (input, committed, filled by hand)

Named by `reviews.title_duplicates_file` and `reviews.split_authors_file`. Title duplicates: one
row per (work, institution) with `decision` (`yes` = same paper as the rest of its `group`, `no` =
different paper), applied as in D-019 and listed per build in `title_duplicates_applied.csv` (kept
work, dropped work, authors carried over). Split authors: one row per (ORCID, author ID or name,
institution) with `decision` (`yes` = the ORCID holder), applied as `person_id` (D-020).

## reviews/ror_assigned_rows.csv (input, committed)

Named by `ror.assigned_rows_file`. One row per authorship whose reviewed ROR match lies inside an
assigned institution: `decision` (`yes` = give the author a row), `note`, work ID, author ID,
author, institution, raw affiliation, `verdict` (confirmed / likely / unverified), and the
evidence from Crossref (`data/external/crossref/<date>/ror_rows_check.csv`), the publication page
and the official site (D-022).

## reviews/review_doi_matches.csv (input, committed, filled by hand)

Named by `doi.review_file`; written by `python -m dpcn_mapping.collect_doi`, which keeps earlier
decisions. One row per (DOI-less paper, Crossref candidate): the best candidate of each paper whose
best title similarity is at least `doi.review_min_similarity`, plus any other near-strong one;
papers in `reviews.non_technical_file` are left out. Columns: `decision` (`yes` = fill the DOI,
`no`, `copy` = the paper is a copy of `doi_conflict_work` and is dropped; blank = not reviewed),
`note`, `status` (strong / ambiguous / weak), `match_score` (0–100: 50 × title similarity + 12.5 per
passed year, venue, author and type check), the paper's work ID, institutions, year, type, title,
journal name, ISSNs and first five authors, the Crossref title, year, container, ISSNs, first five
authors and type, `title_similarity`, the checks `title_ok`, `year_ok`, `venue_ok`, `author_ok`,
`type_ok`, `shared_surnames`, `candidate_doi`, `repository_doi`, `doi_conflict` and
`doi_conflict_work` (the snapshot work already holding the DOI). Rules in D-024.

## data/external/crossref/2026-10-12/doi_* (input to the review file, from collect_doi)

`doi_search.jsonl` (raw: one line per paper with its metadata, the query parameters, HTTP status
and the full Crossref response), `doi_candidates.csv` (every returned item scored, with `rank`,
`crossref_score`, `checks_passed`, `strong`, `near_strong`), `doi_no_candidate.csv` (papers with no
item reaching `doi.review_min_similarity`: work ID, HTTP status, items returned, best similarity,
title, year, journal) and `MANIFEST.json` (query, counts, thresholds, sha256 of the three files).

## reviews/ror_matches.csv (input, committed, filled by hand)

Named by `ror.review_file`; written by `python -m dpcn_mapping.ror_review`, which keeps earlier
decisions. One row per candidate match: `decision` (`yes`/`no`, blank = not reviewed), `note`,
`affiliation` (exact raw string), `ror_name`, `ror_city`, `ror_country`, `ror_id`,
`openalex_id`, `openalex_name`. The build uses a match only when its row says `yes` (D-015).

## data/processed/authors.csv (gitignored)

`/authors` records for every author affiliated with an assigned institution on at least
one snapshot work. `h_index_all_time`, `i10_index_all_time`, `works_count_all_time` and
`cited_by_count_all_time` come from OpenAlex `summary_stats` and cover the author's whole
career, not only 2016–2026.

## data/builds/<build_id>/ (one folder per build, small summaries)

| File | Content |
|---|---|
| build_manifest.json | Snapshot, config and its hash, code hashes, external file hashes, output rows and hashes |
| coverage_report.json | Counts and fill rates |
| diff.md | Comparison with the previous deliverable |
| audit.json / audit.md | Every gap, duplicate and affiliation count (#1–#21 in handoffs/gaps.md), `coauthor_institutes_status` per (paper, institution) pair (#22) and ROR match counts (#23), from `dpcn_mapping.audit` |
| text_cleanup.json | Cells changed by text cleanup (D-017), per output file and column |
| reproduced.log | One JSON line per later rerun that produced byte-identical outputs (time, config and code hashes, environment) |
| build_manifest.json → `lists_sha256` | sha256 of each list file the build wrote to `data/builds/latest/` |

## data/builds/latest/ (list files of the latest build, overwritten by every build)

| File | Content |
|---|---|
| excluded_works_summary.csv | Works excluded by type or year |
| unmatched_works.txt | In-scope works with no affiliated author (should be empty) |
| ror_assigned_institution_matches.csv | Authorships OpenAlex links to no institution whose ROR match is inside an assigned institution (D-015): work ID, institution, raw affiliation. They have no row |
| review_title_duplicates.csv | Works sharing a normalised title and year, grouped (D-005) |
| review_split_authors.csv | ORCIDs carried by more than one OpenAlex author ID |
| review_affiliation_uoh.csv / review_affiliation_jnu.csv | Rows whose raw affiliation suggests a different institution |
| doi_duplicates.csv | In-scope works sharing a DOI (D-012): every member of each group, which one was kept and why (citations, source type) |
| doi_repairs.csv | DOIs changed by the DOI repair rule (D-017): work ID, DOI as in OpenAlex, DOI used |
| doi_filled.csv | Blank DOIs filled from `yes` rows of the DOI review file (D-024): work ID, DOI |
| doi_copies_dropped.csv | DOI-less works dropped as `copy` in the DOI review file (D-024): copy, kept work, its DOI, assigned-institution authors only on the copy (not carried over) |
| affiliation_rejections_applied.csv | Reviewed `no` affiliation links and whether each was applied (D-018) |
| title_duplicates_applied.csv | Reviewed title duplicates: kept work, dropped work, authors carried over (D-019) |
| non_technical_dropped.csv | Papers dropped as coming only from non-technical units: title, year, field, institutions, affiliations (D-021) |
| identical_rows_audit.csv | Every row that is identical to another in all deliverable columns (D-005): group number, whether this build dropped it, and the OpenAlex work/author IDs, author position and raw affiliation that show why the copies exist |
