# Data sources

Every source the Group 16 dataset was built from. Checksums of the downloaded reference
files are in [`external/SOURCES.md`](external/SOURCES.md).

## 1. OpenAlex: papers, authors, citations

- **Website / API:** https://openalex.org, `https://api.openalex.org`
- **Collected:** 2026-10-13, with `python -m collector collect`
- **Gives:** every paper (title, year, type, DOI, citation count, reference list, primary
  topic and field), its authors (OpenAlex author id, ORCID, position, raw affiliation text,
  institutions), its venue (name, ISSN, type), author profiles (h-index, i10-index, works
  count), venue 2-year mean citedness, and the Indian works that cite or are cited by our papers.
- **Queries:**
  - papers: `/works?filter=authorships.institutions.lineage:I152429107|I36893310|I110166357,publication_year:2016-2026,primary_topic.field.id:<14 science/engineering fields>,type:article|conference-paper`
    (field names in `config.toml` → `scope.include_fields`, resolved to ids via `/fields`)
  - complete author lists: `/works/<id>` for papers whose list response stops at 100 authors
  - Indian works cited by our papers: `/works?filter=cited_by:<ids>,authorships.institutions.country_code:IN`
  - Indian works citing our papers: `/works?filter=cites:<ids>,authorships.institutions.country_code:IN`
  - author profiles: `/authors?filter=ids.openalex:<ids>`
  - venues: `/sources?filter=ids.openalex:<ids>`

## 2. ROR: institution identifiers

- **Website:** https://ror.org
- **Gives:** the ROR id of each university. Each OpenAlex institution id was confirmed through
  `https://api.openalex.org/institutions/ror:<ror>`.

| Institution | ROR | OpenAlex |
|---|---|---|
| Jawaharlal Nehru University | `0567v8t28` | `I152429107` |
| University of Hyderabad | `04a7rxb17` | `I36893310` |
| University of Delhi | `04gzb2213` | `I110166357` |

## 3. SCImago Journal Rank: journal quartiles

- **Website:** https://www.scimagojr.com/journalrank.php
- **Files:** `external/scimago/scimagojr_2016.csv` … `scimagojr_2025.csv`, downloaded by hand
  on 2026-10-08
- **Gives:** quartile (`SJR Best Quartile`), SJR, citations per document (2 years) and subject
  areas of each journal, per year. Also used for conference papers in indexed proceedings
  series (e.g. Lecture Notes in Computer Science) that CORE does not rank.
- **Coverage:** 29,526 of 32,517 journal papers (90.8%) have a quartile.

## 4. CORE: conference ranks

- **Website:** https://portal.core.edu.au/conf-ranks/ (edition ICORE2026, 987 conferences)
- **File:** `external/core/CORE_ICORE2026.csv`, downloaded on 2026-10-08
- **Gives:** rank A*, A, B or C of a conference.
- **Coverage:** of 3,496 conference papers, 98 have a CORE rank, 1,081 have a SCImago quartile
  as a proceedings series, and 2,317 are unranked.

## 5. Journals and conferences

The venue of each paper (journal or conference name, ISSN) is the OpenAlex primary location of
that paper. The dataset holds 32,517 journal papers and 3,496 conference papers; the venue of
each one is in the `journal_name` column of `group16_data.csv`.

## Not used

- **Clarivate JCR:** the collector can read JCR exports from `external/jcr/`, but no
  subscription was available, so the folder is empty and the `jif` columns are blank. The dashboard's
  "impact factor" is therefore the OpenAlex 2-year mean citedness of the journal (source 1), not the
  Clarivate JIF.
