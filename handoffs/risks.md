# Risks and definitions for the report

## Matching
- SCImago "Best Quartile" is the best across a journal's categories, so it can look better than
  the quartile in its main field.
- OpenAlex can split one person into several author IDs (gap #15) or merge namesakes into one
  ID (gap #16). Grouping by `openalex_author_id` (enriched file) avoids name clashes but cannot
  undo a merge: OpenAlex gives one name and ORCID per ID, so merges are invisible in those
  fields. Estimated 150–250 merged IDs of 38,001 (D-016, `scripts/estimate_merged_authors.py`);
  taken as published and stated as a limitation.
- Confusable names (JNU/JNCASR/JNTU, UoH/Osmania/IIT Hyderabad) affect a few hundred rows at most.

## Definitions to state
- One row per (paper, institution, affiliated author); affiliation is the one on the paper (D-014).
  Printed "Professor Emeritus" counts; a degree only ("PhD from") does not; "former" is undecided.
  Deduplicate on `openalex_work_id` to count papers (D-011).
- An author with two assigned institutions on a paper counts for both; group-wide totals
  deduplicate papers and people (D-014).
- "Another Indian institution" includes the other two assigned institutions (D-008).
  `cites_indian_inst` blank = no reference list. Empty `coauthor_institutes` is explained by
  `coauthor_institutes_status` (D-015).
- Quartile blank mostly means "not indexed in Scopus", not missing data; show it as its own category.
- h-index is OpenAlex all-time, not 2016–2026. Citations as of 2026-10-08. 2026 is a partial year.
- Books, most book chapters and preprints are excluded (D-013), understating book-heavy fields
  (JNU humanities).
