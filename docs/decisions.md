# Decision log

Each analytic choice behind the dataset gets one entry: context, decision, consequences.
Settings live in `config/build.toml`. When a decision changes, mark the old entry
"Superseded by D-xxx" and add a new one. Never delete an entry.

Status values: Accepted, Pending (current config keeps the default noted), Superseded.

---

## D-001 Data source and institution identifiers
- **Status:** Accepted (2026-10-08)
- **Context:** The instruction note allows OpenAlex, IRINS or Scopus and recommends ROR IDs.
  IRINS and SCImago block scripted access (HTTP 403). Scopus needs institutional access.
- **Decision:** Use the OpenAlex REST API as the primary source. Resolve institutions through
  ROR (`/institutions/ror:<ror>`): JNU I152429107 (ror 0567v8t28), University of Hyderabad
  I36893310 (04a7rxb17), University of Delhi I110166357 (04gzb2213). Match works with
  `authorships.institutions.lineage`, which includes child institutions.
- **Consequences:** Faculty status and department are not available (see D-007).

## D-002 Immutable dated snapshots
- **Status:** Accepted (2026-10-08)
- **Context:** OpenAlex changes continuously, and incremental sync filters
  (`from_updated_date`) need a paid plan. Good practice (Cookiecutter Data Science, the
  medallion pattern, Wilson et al. 2017, Sandve et al. 2013) treats raw data as immutable.
- **Decision:** Raw API responses go to `data/raw/openalex/<YYYY-MM-DD>/`. `MANIFEST.json`
  is written last and marks the snapshot complete, after which its files are read-only.
  Re-collecting means a new dated snapshot. The build overwrites derived files only.
- **Consequences:** Results are reproducible from (snapshot, config, code). Each snapshot is
  about 10 GB and must be backed up outside the laptop.

## D-003 Publication types kept
- **Status:** Superseded by D-013 (2026-10-08)
- **Context:** The CSV `type` column allows only "journal" or "conference".
- **Decision:** journal = work type article/review/letter in a journal source. conference =
  work type conference-paper, or an article in a conference source. Book chapters, books,
  preprints, datasets, errata, editorials and other types are excluded and counted in
  each build's `excluded_works_summary.csv`.
- **Consequences:** Book-heavy fields (JNU social sciences and humanities) look smaller.
  The report must state this.

## D-004 Scope of University of Delhi (medical and constituent colleges)
- **Status:** Pending. The current config includes them, which is the OpenAlex lineage default.
- **Context:** OpenAlex lineage counts Maulana Azad Medical College (I39190216), University
  College of Medical Sciences (I172982924), Lady Hardinge Medical College (I114546181) and
  constituent colleges (Deen Dayal Upadhyaya, St. Stephen's, Indraprastha College for
  Women, P.G.D.A.V. College (Evening)) as part of DU. "Medical" means affiliated through
  one of the three medical-college OpenAlex IDs above; paper subject plays no part.
  Counted over all snapshot works before the type filter: 36,580 DU authorships come only
  through a medical-college ID, 3,493 through a medical college and another DU unit, and
  105,442 through other DU units only. 13,177 works have only medical-college DU authors.
  In the deliverable, 32,708 DU rows come only through a medical-college ID. All of these
  counts are recomputed by `dpcn_mapping.audit` for every build (`audit.md`, section C and
  snapshot checks). (An earlier estimate of about 33k rows came from keyword matching on raw
  affiliation text and is superseded by these ID-based counts.)
- **Options:** keep all; exclude the medical colleges; exclude all child institutions.
  Set `scope.exclude_institution_ids`. Excluded institutions then count as separate
  Indian institutions in `coauthor_institutes` and the citation flags.

## D-005 Duplicate rows and duplicate works
- **Status:** Accepted (2026-10-08): identical rows are dropped (`dedup.drop_identical_rows = true`).
  Title duplicates: resolved by D-019.
- **Context:** 322 rows are identical in every deliverable column. They come from authors
  with no OpenAlex author ID who appear twice on one paper. No DOI is shared by two works.
  859 works share a normalised title and year (422 groups). Some are true duplicates, some
  are generic titles.
- **Rule (reproducible):** two rows are identical when all 14 deliverable columns match
  as text. When dropping, the first row of each group (in snapshot order) is kept. Every
  build lists all identical rows, dropped or not, in
  `data/builds/latest/identical_rows_audit.csv`.
- **Decision:** Drop the 322 extra copies, keeping the first row of each group.
- **Consequences:** Some groups pair a row that has an OpenAlex author ID with a row that has
  none, e.g. "V. Sharma" on W2184278756. If those were two different people with the same
  name, one is lost; the deliverable cannot tell them apart because it has no author ID
  column. The audit file lists every affected row so this can be reviewed. Title duplicates
  need a manual review list before any rule is applied.

## D-006 Hyperauthor papers
- **Status:** Accepted for flagging (2026-10-08). Network and statistics treatment pending.
- **Context:** 945 included works have 1,000 or more authors, mostly DU physics
  collaborations. There is no single standard: Clarivate ISI (Adams et al. 2019) removes
  papers with more than 100 authors from institutional analysis; THE gives fractional
  credit above 1,000 authors; Leiden Ranking and Nature Index use fractional counting with
  no cap. For co-authorship networks, Newman (2001) proposes 1/(n-1) edge weights, and
  Dinh et al. (2023) show these papers distort centrality.
- **Decision so far:** The deliverable CSV keeps every paper. The enriched file has
  `n_authors` and `is_hyperauthor` (threshold `hyperauthor.flag_threshold` = 100).
- **Proposed (not yet accepted):** report full and fractional counts; build the
  co-authorship network without papers over 100 authors and with 1/(n-1) weights, with a
  sensitivity check at 25, 100 and no cap; keep every paper in the citation network.

## D-007 Authors are "affiliated authors", not verified faculty
- **Status:** Accepted (2026-10-08) until a faculty roster is available.
- **Context:** OpenAlex cannot tell faculty from students, postdocs or visitors. IRINS
  blocked scripted access.
- **Decision:** One row per affiliated author per paper. The report says "affiliated
  authors". A roster, when available, will be joined as a new input and logged here.

## D-008 Indian-connection definitions
- **Status:** Accepted (2026-10-08)
- **Decision:** "Another Indian institution" means any institution with country code IN
  that is outside the row's institution lineage (after D-004 exclusions). Co-authors'
  institutions and the other two assigned institutions count.
- **Update (2026-10-08):** `cites_indian_inst` is left blank when OpenAlex has no reference
  list for the paper (`referenced_works_count` = 0), because FALSE would claim something
  the data cannot show (`flags.blank_cites_flag_without_references = true`). About 19k rows
  (10.9k papers) are affected. `cited_by_indian_inst` stays TRUE/FALSE, because the
  citing-works search covers every paper.

## D-009 Journal quartile and conference rank
- **Status:** Accepted (2026-10-08). SCImago exports for 2016–2025 were downloaded by hand
  from scimagojr.com and saved as `data/external/scimago/scimagojr_YYYY.csv`; each build
  records their sha256. 2026 papers use the 2025 quartiles.
- **Decision:** Quartile is the SCImago "SJR Best Quartile" for the publication year,
  matched on ISSN-L, then on any ISSN. Papers newer than the latest SCImago year use the
  latest year. Conference rank comes from CORE ICORE2026, using exact matching only on the
  normalised venue name or acronym. Fuzzy matches are never applied without manual review.
- **Consequences:** CORE matches only 144 of 8,853 conference rows, because most venues
  are not computer science or are listed only by publisher series.

## D-010 OpenAlex 100-author truncation
- **Status:** Accepted (2026-10-08)
- **Context:** OpenAlex list responses truncate `authorships` to 100.
- **Decision:** Works with 100 or more authorships are refetched one by one (single-work
  lookups cost no credits). A check on our data showed that the institution filter matches
  authors beyond position 100: in 1,120 of the 1,345 refetched works, the first assigned
  author was past position 100, and the filter still returned them. The audit recomputes
  this check for every build (`snapshot_checks` in `audit.md`). No re-collection is
  needed for this.
- **Consequences:** 7 works return exactly 5,000 authorships and may still be incomplete
  (listed in the snapshot manifest as a known gap).

## D-011 Paper counting and non-faculty rows
- **Status:** Accepted (2026-10-08) for paper counting. Faculty filter pending (D-007).
- **Context:** The CSV has one row per (paper, institution, affiliated author), so papers repeat
  (about 2.3 rows per paper). 54% of (institution, paper) pairs have two or more authors from
  the same institution.
- **Decision:**
  - Count papers by deduplicating on `openalex_work_id` (not `doi`; some rows lack one): per
    institution on (`institution`, `openalex_work_id`), group-wide on `openalex_work_id` alone,
    since about 1,400 papers are shared between the assigned institutions. Use it for trend,
    Q1 fraction, top journals, most-cited papers and research areas.
  - Never deduplicate the dataset itself: it would keep the first author and drop co-authors
    such as supervisors.
  - Person-level outputs (faculty list, h-index, performance table, authorship network) will
    use a faculty flag when one exists (roster, ORCID or heuristic, logged here).
- **Consequences:** Build-report row counts are not paper counts. Until a faculty flag exists,
  person-level outputs are labelled "affiliated authors".

## D-012 Works sharing a DOI
- **Status:** Accepted (2026-10-08)
- **Context:** After the DOI repair (D-017), two DOIs were each carried by two OpenAlex works:
  a published record and a repository copy of the same paper. W7212241212 (Jyväskylä
  University Digital Archive) copies W7172483139 (EPJ Web of Conferences); W7138911362
  (ScholarWorks GVSU) copies W2944150340. Small differences in title spacing and author-name
  format kept them out of the identical-row and title checks.
- **Decision:** When in-scope works share a DOI, keep only the one with the most citations;
  on a tie, the record whose source is not a repository, then the lowest work ID
  (`dedup.drop_doi_duplicates = true`). Dropped works are counted as excluded ("duplicate
  DOI") and every group is listed in `data/builds/latest/doi_duplicates.csv`.
- **Consequences:** W7212241212 and W7138911362 are dropped (4 University of Delhi rows).

## D-013 Publication types kept (revised)
- **Status:** Accepted (2026-10-08). Supersedes D-003.
- **Context:** OpenAlex labels some journal and conference papers with other types: book
  chapters in journals (298 works), data and software papers (27), and conference papers
  published as proceedings-series chapters (about 570).
- **Decision:** journal = article, review, letter, book-chapter, data-paper or software-paper in
  a journal source. conference = conference-paper, an article in a conference source, or a book
  chapter in a conference or a proceedings series listed in `build.conference_book_series`.
  Everything else stays excluded. Index-source and no-source articles, conference abstracts,
  other book-series chapters, "other" and preprints in journals await a group decision.
- **Consequences:** 894 papers added; no earlier row changed. Book-heavy fields remain understated.

## D-014 Affiliation is taken from each paper, not from the author's profile
- **Status:** Accepted (2026-10-08). States the rule used since D-001.
- **Decision:** A row exists only when the author's affiliation on that paper
  (`authorships[].institutions`) is inside an assigned institution's lineage. The author
  profile is never used to select papers; it only supplies h-index and ORCID. Co-authors
  from other institutions get no row; their Indian institutions go in `coauthor_institutes`.
  Example: W2952965410 has one row, Raju Surampudi Bapi (UoH); his IIIT Hyderabad and NBRC
  co-authors appear only in `coauthor_institutes`.
- **Printed text that is not a current affiliation (2026-10-09):** some publishers print an
  author biography as the affiliation. "Professor Emeritus" of an assigned institution counts
  (a lifetime title the university confers). A degree only ("PhD from JNU") does not count.
  "Former" or "retired" professor is undecided. Rows are removed through the review files (D-018).
- **Consequences:**
  - Papers from before joining or from another employer are not counted.
  - Papers by students and visitors are counted, even after they leave (see D-007).
  - An author listing two assigned institutions on one paper gets a row for each, so the
    paper counts for both (312 author-paper pairs, mostly JNU + DU). Group-wide figures
    deduplicate papers on `openalex_work_id` and people on `openalex_author_id`.
  - Wrong matches from confusable names (JNU/JNCASR/JNTU, UoH/Osmania/IIT Hyderabad) are
    listed for review by the audit (#19, #20).

## D-015 Co-author institutions: ROR matches and empty values
- **Status:** Accepted (2026-10-09). Extends D-008 and D-014. "Never new rows" amended by D-022.
- **Context:** 47.7% of (paper, institution) pairs have an empty `coauthor_institutes`; 9% of
  those have co-authors that OpenAlex linked to no institution. ROR's affiliation matcher can
  resolve some, but its chosen match is often a generic name inside a longer one ("Institute of
  Medical Sciences" for "Kalinga Institute of Medical Sciences"; about 500 of 1,253).
- **Decision:**
  - Only ROR matches where a comma-separated part of the affiliation equals a ROR name, and that
    a reviewer marked `yes` in `reviews/ror_matches.csv` (204 candidates), are used, as for
    fuzzy CORE matches (D-009).
  - They fill only `coauthor_institutes` for unlinked co-authors: never new rows, never the
    citation flags, never an OpenAlex link. Matches inside an assigned institution are listed
    for a later decision (`ror_assigned_institution_matches.csv`).
  - The enriched file's `coauthor_institutes_status` says why each value is empty
    (codebook). The deliverable keeps empty cells; foreign institutions are not stored.
- **Consequences:** Until the review is done, the deliverable is unchanged.

## D-016 Author IDs are taken as OpenAlex assigns them
- **Status:** Accepted (2026-10-09).
- **Context:** OpenAlex may merge namesakes into one author ID, which its single name and ORCID
  per ID cannot reveal. IDs publishing from unrelated departments suggest about 150–250 merged
  IDs of 38,001, mostly common names (`scripts/estimate_merged_authors.py`).
- **Decision:** Use IDs as published; do not split them. State it as a limitation.
- **Consequences:** Paper counts are unaffected (D-011). Person-level outputs may show a merged
  ID as one unusually productive or bridging author.

## D-017 Text normalisation and DOI repair
- **Status:** Accepted (2026-10-08). Moved here from the second D-011 entry (2026-10-09).
- **Context:** Some OpenAlex text had stray whitespace, line breaks, HTML entities (`&amp;`) or
  invisible characters (e.g. `\x98The \x9ccryosphere`); line breaks inside a cell break simple
  CSV readers. Three DOIs carried junk after the DOI (e.g. `….html?utm_source=repec…`).
- **Decision:**
  - Every text cell in the three output files: decode HTML entities, collapse whitespace to
    one space, trim, remove control codes and invisible characters (zero-width joiners kept
    for Indic scripts). DOIs and ORCIDs: whitespace only.
  - DOIs are cut at the first quote, `<`, `>`, `&`, `?`, `#` or space; a trailing `.html` is dropped.
  - Validation rejects untidy whitespace and junk DOIs. Each build logs changes
    (`text_cleanup.json`, `doi_repairs.csv`); the audit reports leftovers.
- **Consequences:** `raw_affiliation` is not byte-for-byte OpenAlex; the original is in the snapshot.

## D-018 Reviewed affiliation links
- **Status:** Accepted (2026-10-09).
- **Context:** OpenAlex links some authors to UoH or JNU that their affiliation text does not
  support: Osmania ("OU, Hyderabad"), Malla Reddy, GRIET, DRDO's CHESS, JNTU, or a biography
  ("holds a PhD from JNU").
- **Decision:**
  - `python -m dpcn_mapping.affiliation_review` lists rows whose text does not name the
    institution, reads like a biography, or (JNU) names a confusable one, in
    `reviews/review_affiliation_{uoh,jnu}.csv`. A reviewer marks each `yes` or `no`.
  - A `no` removes only that author's link to that institution on that paper, before the build
    reads the authors: no row, and the wrong institution counts nowhere else. Other authors and
    the author's other institutions stay. A paper leaves an institution only when no genuine
    author of it remains.
- **Consequences:** First review: 49 links removed (45 UoH, 4 JNU); 29 papers left the dataset
  (27 UoH, 2 JNU), each checked to have no other UoH/JNU author. Every build lists the applied
  rejections in `affiliation_rejections_applied.csv`.

## D-019 Reviewed title duplicates
- **Status:** Accepted (2026-10-09). Resolves the title-duplicate part of D-005.
- **Context:** 420 groups of works share a normalised title and year. A reviewer marked 405
  groups as the same paper (provisional and final DOIs, Zenodo copies, Angewandte German and
  international editions) and 15 as different papers (`reviews/review_title_duplicates.csv`).
- **Decision:**
  - In each `yes` group one work is kept: the most assigned-institution authors, then the
    longest author list, then the most citations, then not a repository copy, then the lowest
    work ID. The other copies are excluded ("reviewed title duplicate").
  - An assigned-institution author found only on a dropped copy is carried over to the kept
    work. Name variants ("P. Yadav" / "Prasant Yadav", "Rahman, Hasibur") count as the same
    person, so nobody is counted twice.
- **Consequences:** 420 works dropped, 12 authors carried over, no author lost; every other row
  unchanged. Each build lists the result in `title_duplicates_applied.csv`.

## D-020 Reviewed split authors
- **Status:** Accepted (2026-10-09). Complements D-016.
- **Context:** 692 ORCIDs are carried by 1,480 OpenAlex author IDs or ID-less rows. A reviewer
  marked 1,364 as the ORCID holder and 116 as a different person
  (`reviews/review_split_authors.csv`).
- **Decision:** The enriched file gets `person_id`: the ORCID for confirmed IDs, otherwise the
  OpenAlex author ID (blank when there is none). Person-level outputs group by `person_id`.
  `openalex_author_id` and `author_orcid` stay as OpenAlex published them.
- **Consequences:** 37,926 author IDs become 37,632 people. The deliverable is unchanged (it has
  no author ID column). Merges of namesakes under one ID (D-016) are not affected.

## D-021 Papers only from non-technical units are dropped
- **Status:** Accepted (2026-10-12). Part of the technical-research scope; the rest is open
  (`handoffs/todo.md`).
- **Context:** The group keeps research with a technical aspect, in the sense of IIIT Hyderabad's
  HSRC and CCNSB. `docs/uni.md` classifies every unit of the three universities from their
  official websites; units confirmed as non-technical are struck through there.
- **Decision:** A paper is dropped only when every author is from an assigned institution, every
  affiliation segment of every author names both its own university and a confirmed
  non-technical unit and nothing technical or borderline (economics, geography, psychology,
  linguistics, library science, education technology, colleges teaching maths or science), its
  primary field is in the Social Sciences domain, and its title names no computational or
  quantitative method. Any outside co-author, unnamed unit or doubt keeps the paper. Patterns:
  `[technical_filter]` in `config/build.toml`.
- **Consequences:** 2,861 papers and 3,481 rows dropped (DU 1,714, JNU 876, UoH 259, 12 shared);
  rows of kept papers unchanged. Each build lists them in `non_technical_dropped.csv`. Mixed
  collaborations and Sci, Med and Mixed units are not filtered yet.

## D-022 Verified ROR matches inside an assigned institution become rows
- **Status:** Accepted (2026-10-12). Amends D-015, which let ROR matches create no rows.
- **Context:** 20 authors had no OpenAlex institution although their printed affiliation names
  DU or UoH (e.g. "Delhi University, Bharati College"); their reviewed ROR match pointed to it.
  All 20 papers were already in the dataset through other authors.
- **Decision:** Each case was checked against Crossref (`python -m dpcn_mapping.verify_ror_rows`),
  the paper's publication page and the official university or college website. A row is created
  only when the printed affiliation (publication page or Crossref deposit) names the university
  or one of its units and the official site confirms the person or the unit, and nothing
  contradicts it. Decisions and evidence: `reviews/ror_assigned_rows.csv` (`yes` = row).
- **Consequences:** 16 rows added (15 people), no new papers. 2 cases are likely (official site
  only: Aisha Sultana, Archna Pandey) and 2 unverified (Amit Kumar Ranjan, Merry Pegu); they get
  no row until decided. Update 2026-10-12: the reviewer confirmed all 4, so 20 rows in total.

## D-023 Papers reviewed as non-technical by topic are dropped
- **Status:** Accepted (2026-10-12). Extends D-021 to papers the unit rule cannot reach.
- **Context:** Many rows in the affiliation review files print a biography ("Professor Emeritus,
  JNU") or no unit, so D-021 keeps them, although the paper is plainly history, literature,
  politics, law, sociology, economics or management. Deciding their affiliation was wasted work.
- **Decision:** Papers whose title and venue are clearly non-technical are listed in
  `reviews/non_technical_papers.csv` and dropped whole, whatever their affiliations. Economics
  and management count as non-technical here. Doubtful topics (linguistics, education technology,
  health policy, history of science, geography) are not listed. Listed papers are removed from
  the affiliation review files and `affiliation_review` never lists them again.
- **Consequences:** 87 papers listed (10 UoH, 77 JNU), from 88 review rows. Each build lists them
  in `non_technical_dropped.csv` with `reason` = `reviewed` (D-021 drops have `units`). Build
  20261012T121911Z: 80 rows removed (JNU 66, UoH 12, DU 2); 19 of the papers were already
  dropped by D-021.

## D-024 Blank DOIs: Crossref title search with review
- **Status:** Accepted (2026-10-12). Gap #3.
- **Context:** 1,034 papers (1,567 rows) had no OpenAlex DOI. Only Crossref was used (anonymous,
  no email or personal data sent).
- **Decision:**
  - `python -m dpcn_mapping.collect_doi` sends one search per paper: `query.bibliographic=<title>`,
    `query.author=<first author>`, `filter=from-pub-date:<year-1>,until-pub-date:<year+1>`, `rows=5`.
    The raw responses and each paper's metadata go to `data/external/crossref/2026-10-12/`.
    `MANIFEST.json` is written last. `--check` rebuilds every output from the raw file with no
    network calls.
  - Each item is scored against the paper:
    - `title_ok`: titles are normalised (NFKD to ASCII, lowercase, letters and digits only) and
      the difflib ratio must be at least 0.95. The Crossref title is tried alone and with its
      subtitle.
    - `year_ok`: the Crossref `issued` year is within one year of the paper's year.
    - `venue_ok`: the ISSNs overlap, or the normalised container title equals the journal name.
    - `author_ok`: at least one surname is shared. On the OpenAlex side the surname is the last
      letter-only token of each display name; on the Crossref side it is any token of `family`.
    - `type_ok`: `journal-article` for journal papers, `proceedings-article` for conference papers.
  - A candidate is **strong** only when all five checks pass and none of these applies:
    - it is a repository or preprint DOI (`doi.repository_prefixes`, or a Crossref type such as
      `posted-content`);
    - another snapshot work already holds the DOI (the holding work is shown);
    - another paper's strong candidate has the same DOI.
  - If a paper has two near-strong candidates with different DOIs, it is marked `ambiguous`, not
    strong. Near-strong means the title passes and at most one other check fails.
  - The review file `reviews/review_doi_matches.csv` lists, for each paper whose best item reaches
    title similarity 0.80, the item with the highest title similarity, plus any other near-strong
    item. Papers below 0.80 are listed in `doi_no_candidate.csv`. Papers in
    `reviews/non_technical_papers.csv` get no review row.
  - Decisions:
    - `yes`: the build fills the blank DOI.
    - `copy`: the paper is a DOI-less copy of `doi_conflict_work`. The build drops the copy and
      keeps the holder. No authors are carried over; this differs from D-019, whose ranking kept
      the DOI-less copy in 2 of these pairs.
    - The build refuses a `yes` whose DOI is already on another snapshot work or on another fill,
      so it never creates a shared DOI.
  - Filled DOIs pass the D-017 validation. `citation_network.csv` will key on them; it is not
    built yet (header only).
- **Consequences:**
  - The search filled no DOIs, because most of these venues never register them. 1,007 papers had
    no item with title similarity of at least 0.80. Of the 27 papers with a plausible match:
    - 1 was strong (a *Cultura* literature paper, listed as non-technical);
    - 10 were DOI-less copies of works already in the build (8 marked `copy`; the other 2 are
      non-technical and dropped);
    - 16 were weak (the same title in another venue, or mismatches).
  - At the same review, 373 DOI-less papers with plainly non-technical topics (humanities, social
    sciences, education, economics, management) were added to `reviews/non_technical_papers.csv`
    under the D-023 rule. This also covers the DOI records of the 2 non-technical copies.
    Psychology, linguistics, library science, history of science and doubtful titles were kept.
  - Build 20261012T134558Z: 437 rows removed (381 papers: DU 262, JNU 86, UoH 33). Every
    remaining row is byte-identical in both the deliverable and the enriched file, and the D-005
    identical-row counts are unchanged (628 rows, 321 dropped). 651 papers (1,128 rows) still have
    no DOI. The files `doi_filled.csv` and `doi_copies_dropped.csv` are written for every build.

## D-025 Impact factor on the dashboard comes from OpenAlex
- **Status:** Accepted (2026-11-15).
- **Context:** The dashboard shows Q1 papers in journals with an impact factor above 5 and above 10,
  and each author's top 10 papers by journal impact factor. The source is
  listed in `collector/SOURCES.md`.
- **Decision:** Impact factor is OpenAlex `summary_stats.2yr_mean_citedness` of the paper's journal
  (column `oa_2yr_mean_citedness`), collected with the venues. Quartiles stay the SCImago quartiles
  (D-009). The value is one current figure per journal, not the value for the paper's year.
  `python -m collector dashboard-data` writes it to
  `dashboard/public/data/impact.json`.
- **Consequences:** Every journal paper has a value (32,517 of 32,517). Thresholds are strict (> 5, > 10).
  Papers with 10 or more authors are counted separately from papers with fewer. The author top 10 is
  shown for authors with more than 10 journal papers; ties are broken by citations, then by year.
