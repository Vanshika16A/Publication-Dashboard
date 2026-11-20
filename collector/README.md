# Group 16 data collector

Downloads the science and engineering publications (2016–2026) of **JNU, University of Hyderabad
and University of Delhi** from OpenAlex and builds the files the instruction note asks for:
`group16_data.csv`, the three network files, and an author table for the dashboard. Anyone can
run it; it only needs Python 3.11+ and an internet connection.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r collector/requirements.txt

# 1. Journal quartiles need SCImago files (a few downloads in your browser, see "Quartiles")

# 2. (optional) a free OpenAlex key avoids the daily request limit
echo "OPENALEX_API_KEY=your-key" >> .env        # https://openalex.org/settings/api

python -m collector run          # collect (resumable) + build + clean
python -m collector networks     # network files, from the cleaned data
```

If the run stops (laptop sleep, request limit), run the same command again: it continues where
it stopped. `python -m collector status` shows progress. Expect roughly 40,000 papers and a few
hours for the full run (most of it is the citation look-ups; they are what fill
`cites_indian_inst` / `cited_by_indian_inst`). Try `--years 2024-2024` first to test everything
on one year.

Results appear in `collector/data/output/` (gitignored). Downloaded data is cached in
`collector/data/raw/`. `python -m collector build` and then `python -m collector clean` rebuild the
CSVs from it in a few minutes without internet, so you can change `config.toml` and rebuild freely.

The pipeline has three stages: `build` turns the download into a first dataset
(`output/build/`), `clean` produces the final dataset (`output/`), and `networks` builds the
network files from the cleaned data (`output/networks/`).

## What is downloaded (and what is not)

Only works whose OpenAlex *primary topic* is in the science/engineering fields listed in
`config.toml → scope.include_fields`, of type article / conference paper (letters and reviews are left out), by
authors at the three institutions (OpenAlex ROR-checked ids). Medicine, Nursing, Dentistry,
Health Professions, Veterinary, Arts & Humanities, Social Sciences, Business, Economics,
Psychology and Decision Sciences are filtered **at the API**, so they are never downloaded.
Every response is reduced to the needed fields before saving. Also fetched: author profiles
(h-index), journal-level OpenAlex numbers, the Indian works your papers cite / are cited by
(institutions only; any year, field or type, because the flags are about any other Indian
institution), and the CORE conference ranking.

## Outputs

| File | Content |
|---|---|
| `group16_data.csv` | The required 14 columns, one row per (paper, institution, author): **the deliverable** |
| `group16_data_extended.csv` | Same rows plus ids, raw affiliation, quartile source, SJR, cites/doc, JIF, field, ... |
| `authors.csv` | One row per (institution, person): papers, citations, top journal, h-index, i10 |
| `cleaning_report.md/json` | What `clean` removed or changed, with counts |
| `build/` | The uncleaned first dataset, with `build_report.md` and its own `review/` (duplicates, affiliations, venues without quartile) |
| `networks/citation_network.csv` | `source_doi, target_doi, source_inst, target_inst, year` (+ flags, OpenAlex ids) |
| `networks/authorship_network.csv` | `author_a, author_b, paper_doi, inst_a, inst_b, year` (+ ids, 1/(n-1) weight) |
| `networks/indian_connections.csv` | `your_inst, partner_inst, shared_papers, total_citations` (+ citations given / received) |
| `networks/citation_flow.csv` | Citations in / out per partner institution and year (instruction note 7a) |
| `review/` | Every paper or row `clean` dropped and every value it changed, with the rule |

`journal_name`, `issn`, `quartile`: journals get a SCImago quartile; conferences get a CORE rank
(A*/A/B/C), or a SCImago quartile when the venue is an indexed proceedings series.
`cites_indian_inst` is blank when OpenAlex has no reference list for the paper, because FALSE
would claim something the data cannot show. "Another Indian institution" means any Indian
institution outside the row's institution; the other two assigned institutions count, and a
college of the same university is not "another" institution.

## Quartiles and impact factor

SCImago, Scopus and Clarivate all block scripted downloads (HTTP 403), so the collector reads
files you download once in a browser. Commit them so teammates do not repeat this.

1. **SCImago (required for journal quartiles).** On <https://www.scimagojr.com/journalrank.php>
   choose a year, then "Download data" (the CSV, semicolon separated). Save it as
   `collector/external/scimago/scimagojr_YYYY.csv`. Do this for 2016–2025 (2026 papers use the
   nearest year). The quartile is "SJR Best Quartile" for the paper's year, matched on any ISSN,
   then on the exact journal title. If the paper's year has no quartile for a journal, the nearest
   year is used and `quartile_source` in the extended file says so (`SCImago 2019 (nearest year)`).
2. **Clarivate JCR (optional, needs your university's subscription).** In JCR choose
   Journals → Export → CSV with the JIF columns and save in `collector/external/jcr/`. This adds
   the true Clarivate `jif`, `jif_quartile` and `jif_year` to the extended file. The reader finds
   columns by name, but it was written without access to a real export: check the first rows.
3. **Impact factor without JCR.** The Clarivate impact factor is not free. The extended file
   therefore carries labelled substitutes, none of which is the Clarivate JIF:
   `sjr` and `cites_per_doc_2y` (SCImago, Scopus-based, matched to the paper's year) and
   `oa_2yr_mean_citedness` (OpenAlex, current).
   The dashboard's impact factor (Publications and Authors pages) uses the OpenAlex value only; see D-025
   in `docs/decisions.md`.
4. **Venues still without a quartile.** `output/build/review/venues_without_quartile.csv` lists them, most
   papers first. Look the top ones up in the [Scopus source list](https://www.scopus.com/sources)
   or the [Clarivate Master Journal List](https://mjl.clarivate.com/home) (it shows only whether a
   journal is indexed, not a quartile). Do not fill quartiles from memory or from an AI model.

## Affiliation, duplicates, scope: how problems are handled

* **Authors who wrote no affiliation.** OpenAlex sometimes places an author at an institution
  with no affiliation text on that paper behind it. That link comes from OpenAlex's own inference,
  not from the author. Default (`affiliation.unstated = "drop"`): a row is kept only if the author's
  own affiliation text for that paper names the institution. Dropped rows are in
  `review/dropped_affiliation.csv` with the text OpenAlex had. Use `"flag"` to keep them and
  mark `affiliation_status = unstated`.
* **Look-alike institutions.** Text naming JNCASR / JNTU (for JNU) or Osmania / IIT / Reddy ...
  (for UoH) without naming the right university is not accepted. Patterns are in `config.toml`.
* **Duplicates.** Same DOI → keep the most cited record (`review/doi_duplicates.csv`). Same
  title and year *and* a shared author → keep the most cited (`review/title_duplicates.csv`
  lists every candidate group, including those left alone because no author is shared). Author
  ids carrying the same ORCID are merged (`review/merged_authors.csv`). Identical rows are
  dropped. Two different people merged under one OpenAlex id cannot be detected: state it as a
  limitation.
* **Science and engineering only.** Change `scope.include_fields` and re-run `collect` (the
  cache refuses to mix scopes: delete `collector/data/raw/<years>` first).
  Borderline fields (Pharmacology, Neuroscience) are noted in the config.
* **Hyperauthor papers** (100+ authors) stay in the dataset and the citation network and are flagged
  (`is_hyperauthor`), but are left out of the authorship network.

The review files above are in `output/build/review/`. The `clean` step then does the following,
configured in the `[clean]` section of `config.toml` and listed in `output/review/`:

* **Venue check.** A paper is dropped when SCImago lists its venue and none of the venue's
  subject areas is a science/engineering field. OpenAlex tags some clinical papers as biology, so
  pediatrics, oncology or dermatology journals would otherwise stay in.
* **Not research.** Retracted or withdrawn papers, errata, prefaces, editorials and similar
  notices (matched on the title), and abstract digests or meeting-abstract books
  (`exclude_venues`, e.g. ChemInform).
* **Non-person authors.** Rows such as "on behalf of the CMS collaboration" are dropped.
* **Tidier values.** Footnote digits, ORCID text, symbols, honorifics ("Dr.", "Prof.") and
  repeated names are removed from author names, and ALL-CAPS names are put in normal case
  (initials such as "MS" stay). One trailing full stop is removed from titles.

## Known limits

* Authors are "affiliated authors", not verified faculty; there is no department column.
* OpenAlex changes continuously: citation counts and author ids are as of the collection date
  (`collection_info.json` in the cache). Share the cache folder or the output CSVs if the team must
  use identical data.
* h-index is OpenAlex's all-time value, not restricted to 2016–2026.
* Works with exactly 5,000 authorships may have an incomplete author list (OpenAlex limit).

## Tests

```bash
python -m pytest collector/tests
```
