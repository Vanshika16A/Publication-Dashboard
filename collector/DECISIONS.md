# Decisions

This file explains how the Group 16 dataset was made and why. Every setting named here is in
[`config.toml`](config.toml). Every paper or row the pipeline removes is listed with its
reason in a `review/` folder next to the output.

## 1. How authors were verified

An author row is kept for an institution only when all of these hold:

1. OpenAlex links the author to the institution. The author's institution on that paper is
   the university or one of its units (OpenAlex "lineage"), so departments and DU colleges count.
2. The author's own affiliation text backs the link. OpenAlex sometimes places an author at an
   institution with no affiliation text on that paper to support it. These links are dropped
   (`affiliation.unstated = "drop"`).
3. The text names the right institution. Text that matches a look-alike pattern and not the
   university's own pattern is rejected (`affiliation.check_lookalikes = true`):
   - JNU: rejects JNCASR, JNTU and other "technological" universities
   - UoH: rejects Osmania, IIT, IIIT, IISER, JNTU, NALSAR, ICRISAT, CCMB, IICT and others in Hyderabad
   - DU: no look-alike patterns
4. The author is a person. Rows such as "on behalf of the CMS collaboration" or
   "... consortium" are dropped (`clean.non_person_author`).

```text
author on a paper, placed by OpenAlex at an institution
      |
      v
institution, or its parent, is JNU, UoH or DU? ----- no  --> author not kept
      | yes
      v
author's own affiliation text on this paper? ------- no  --> dropped: unstated
      | yes
      v
all of that text names a look-alike? --------------- yes --> dropped: look-alike
      | no
      v
"author" is a group (collaboration, ...)? ---------- yes --> dropped: not a person
      | no
      v
row kept, name tidied
```

Author names are then tidied: footnote digits, ORCID text, symbols, honorifics ("Dr.",
"Prof.") and repeated names are removed, and ALL-CAPS names are put in normal case.

Rejected links are listed in `build/review/dropped_affiliation.csv` with the affiliation text
OpenAlex had.

## 2. Authors with identical names

- Each person is identified by an OpenAlex author id. Two authors with the same name but
  different OpenAlex ids stay two people in the dataset, in `authors.csv` and in the
  authorship network.
- One person split over several ids is merged by ORCID. Ids that carry the same ORCID become
  one person (`dedup.merge_authors_by_orcid = true`). The kept id is the one with the most
  works in OpenAlex, and the name shown is its OpenAlex profile name. Merges are listed in
  `build/review/merged_authors.csv`.
- Authors without an OpenAlex id are matched by name (lower case, letters only), so two such
  authors with the same name count as one person.
- One person appears once per paper and institution. Repeated rows are removed, including rows
  that become identical after name tidying.
- A shared title alone does not merge two papers. Two papers with the same title and year count
  as duplicates only when they also share an author id (`dedup.title`), so same-title papers
  by different people are kept.

```text
author on a paper
      |
      v
has an OpenAlex author id?
      |
      +-- no ---------------------------> person = name (lower case, letters only)
      |
      +-- yes, ORCID shared by ---------> person = the id with the most OpenAlex works
      |   several ids                     (build/review/merged_authors.csv)
      |
      +-- yes, otherwise ---------------> person = the author id

Then: one row per (paper, institution, person).
```

One limit remains: if OpenAlex has put two different people under one author id, the data
cannot show it.

## 3. Pipeline

Run `python -m collector run` (collect, build, clean), then `python -m collector networks`.

```text
OpenAlex API              SCImago CSVs              CORE CSV
api.openalex.org          external/scimago/         external/core/
      |                         |                        |
      v                         |                        |
+---------------------+         |                        |
| 1. collect          |         |                        |
|    (collect.py)     |         |                        |
+---------------------+         |                        |
      |  cache: data/raw/       |                        |
      |  38,761 papers          |                        |
      v                         v                        v
+--------------------------------------------------------------+
| 2. build  (build.py)                                         |
| select papers -> remove duplicates -> merge ids by ORCID     |
| -> verify authors -> rank venues                             |
| -> one row per (paper, institution, author)                  |
|                                                              |
| rank venues:                                                 |
|   paper        first try          if not found               |
|   -----------  -----------------  -------------------------  |
|   conference   CORE: A*, A, B, C  SCImago: Q1-Q4, else blank |
|   journal      SCImago: Q1-Q4     blank                      |
|                                                              |
|   CORE match: exact name or acronym                          |
|   SCImago match: ISSN, else exact title;                     |
|                  paper's year, else the nearest year         |
+--------------------------------------------------------------+
      |  38,105 papers                  removed -> build/review/
      v
+--------------------------------------------------------------+
| 3. clean  (clean.py)                                         |
| venue scope (SCImago areas) -> retracted, notices,           |
| excluded venues -> non-person authors -> tidy names          |
| -> remove duplicate rows                                     |
+--------------------------------------------------------------+
      |  36,013 papers, 92,219 rows     removed -> review/
      v
group16_data.csv   group16_data_extended.csv   authors.csv
      |
      v
+--------------------------------------------------------------+
| 4. networks  (networks.py)                                   |
| citation_network.csv      authorship_network.csv             |
| indian_connections.csv    citation_flow.csv                  |
+--------------------------------------------------------------+
```

### Collect (`collect.py`)

This step downloads from the OpenAlex API (queries in [`SOURCES.md`](SOURCES.md)). If it
stops, the next run continues where it left off. It fetches:

1. papers of the three universities, 2016-2026, of type article or conference paper, whose
   primary topic is in one of 14 science and engineering fields (`scope.include_fields`)
2. complete author lists for papers with 100 or more authors
3. Indian works cited by our papers and Indian works citing them, of any year, field or type
4. author profiles and venue details
5. the CORE ranking file

Only the needed fields are kept. Result: 38,761 papers.

### Build (`build.py`)

1. Select papers: year 2016-2026, science/engineering field, and a real venue. A conference
   paper is `conference`, an article in a journal is `journal`, and an article in a conference
   venue is `conference`. Anything else, such as a repository copy, is dropped.
2. Remove duplicate papers. Among papers with the same DOI, the most cited is kept
   (`dedup.doi`). Among papers with the same title and year and a shared author, the most
   cited is kept (`dedup.title`, titles of 21+ letters/digits).
3. Merge author ids by ORCID (section 2).
4. Verify authors (section 1).
5. Rank venues:
   - conference papers: CORE rank, by exact normalised name or acronym (no fuzzy matching)
   - journal papers, and proceedings series that CORE does not rank: SCImago quartile, by
     ISSN then exact title, for the paper's year, else the nearest year
     (`quartile.nearest_year_fallback`)
6. Write one row per (paper, institution, author), with:
   - `coauthor_institutes`: other Indian institutions on the paper
   - `cites_indian_inst`: the paper cites a work of another Indian institution (blank when
     OpenAlex has no reference list)
   - `cited_by_indian_inst`: a work of another Indian institution cites the paper
7. Remove identical rows and check the result (columns, years, types, quartile values).

Result: 38,105 papers.

### Clean (`clean.py`)

1. Drop papers whose venue's SCImago subject areas all lie outside science and engineering.
   This catches clinical journals that OpenAlex tags as biology. "Multidisciplinary" counts
   as in scope.
2. Drop retracted or withdrawn papers and notices (errata, editorials, prefaces ...).
3. Drop papers in abstract digests and similar venues (`clean.exclude_venues`).
4. Drop non-person authors and tidy names and titles (section 1).
5. Remove rows that became duplicates, check again and write the outputs.

Result: 36,013 papers, 92,219 rows, 21,659 authors.

| Institution | Papers |
|---|---|
| University of Delhi | 21,856 |
| Jawaharlal Nehru University | 7,895 |
| University of Hyderabad | 7,324 |

Papers shared by two universities count for both.

### Networks (`networks.py`)

- `citation_network.csv`: a dataset paper citing another dataset paper
- `authorship_network.csv`: two verified authors on the same paper, weight 1/(authors − 1).
  Papers with 100 or more authors are left out (`hyperauthor.threshold`) because they would
  link everyone to everyone.
- `indian_connections.csv`: shared papers and citations with each other Indian institution
- `citation_flow.csv`: citations given to and received from each partner, per year

A paper without a DOI is identified by its OpenAlex URL, so no edge is lost.

## 4. Known limits

- The authors are the affiliated authors on the papers. The dataset is not a verified faculty
  list.
- Citation counts and author ids are as of 2026-10-13, and OpenAlex changes continuously.
- h-index is the OpenAlex all-time value, so it is not limited to 2016-2026.
