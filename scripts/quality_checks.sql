-- Data-quality checks for the DuckDB UI (scripts/duckdb_ui.sh). Paste one query per cell.
-- Tables: data (deliverable CSV), enriched (adds OpenAlex IDs, affiliations, topics).

-- 1. Null % and distinct count for every column
SELECT column_name, column_type, null_percentage, approx_unique, min, max
FROM (SUMMARIZE data);

-- 2. Null % per institution for the gappy columns
SELECT institution,
       round(100 * avg((doi IS NULL)::int), 1)                       AS doi_null_pct,
       round(100 * avg((journal_name IS NULL)::int), 1)              AS journal_null_pct,
       round(100 * avg((issn IS NULL AND type = 'journal')::int), 1) AS issn_null_pct,
       round(100 * avg((quartile IS NULL)::int), 1)                  AS quartile_null_pct,
       round(100 * avg((cites_indian_inst IS NULL)::int), 1)         AS cites_flag_null_pct
FROM data
GROUP BY institution
ORDER BY institution;

-- 3. Missing quartile split by paper type (journal: SCImago, conference: CORE)
SELECT type, institution,
       count(DISTINCT doi) FILTER (WHERE quartile IS NULL) AS papers_without_rank,
       count(DISTINCT doi)                                 AS papers
FROM data
GROUP BY ALL
ORDER BY ALL;

-- 4. Blank strings that are not NULL
SELECT count(*) FILTER (WHERE trim(title) = '')        AS blank_title,
       count(*) FILTER (WHERE trim(journal_name) = '') AS blank_journal,
       count(*) FILTER (WHERE trim(author) = '')       AS blank_author,
       count(*) FILTER (WHERE trim(doi) = '')          AS blank_doi
FROM data;

-- 5. Rule violations against the instruction note (all should be 0)
SELECT count(*) FILTER (WHERE year NOT BETWEEN 2016 AND 2026)                              AS bad_year,
       count(*) FILTER (WHERE citations < 0)                                               AS negative_citations,
       count(*) FILTER (WHERE type NOT IN ('journal', 'conference'))                       AS bad_type,
       count(*) FILTER (WHERE quartile NOT IN ('Q1','Q2','Q3','Q4','A*','A','B','C'))     AS bad_quartile,
       count(*) FILTER (WHERE doi NOT LIKE 'https://doi.org/10.%')                         AS bad_doi,
       count(*) FILTER (WHERE "group" <> 16)                                               AS bad_group
FROM data;

-- 6. Same author twice on one paper for the SAME institution (double counting; should be 0).
--    One author with two assigned institutions on a paper gets one row per institution (D-014);
--    that case is expected and not listed here.
SELECT doi, author, institution, count(*) AS n_rows
FROM data
WHERE doi IS NOT NULL
GROUP BY ALL
HAVING n_rows > 1
ORDER BY n_rows DESC;

-- 7. Papers per year per institution (look for sudden drops = collection gaps)
PIVOT (SELECT institution, year, doi FROM data)
ON institution USING count(DISTINCT doi)
GROUP BY year
ORDER BY year;

-- 8. Citation outliers (check that the top papers are real and correctly attributed)
SELECT title, year, journal_name, citations, doi
FROM data
GROUP BY ALL
ORDER BY citations DESC
LIMIT 20;

-- 9. Journal names spelled several ways
SELECT lower(regexp_replace(journal_name, '[^a-zA-Z]', '', 'g')) AS name_key,
       list(DISTINCT journal_name)                                AS spellings
FROM data
WHERE journal_name IS NOT NULL
GROUP BY name_key
HAVING count(DISTINCT journal_name) > 1;

-- 10. Rows without an OpenAlex author ID (no h-index, weak network nodes)
SELECT institution, count(*) AS rows_without_author_id
FROM enriched
WHERE openalex_author_id IS NULL
GROUP BY institution;

-- 11. Suspect affiliations (JNU vs JNCASR/JNTU, UoH vs Osmania/IIT Hyderabad)
SELECT institution, author, title, raw_affiliation
FROM enriched
WHERE (institution = 'Jawaharlal Nehru University'
       AND regexp_matches(raw_affiliation, 'JNCASR|Centre for Advanced Scientific|JNTU|Technological', 'i'))
   OR (institution = 'University of Hyderabad'
       AND regexp_matches(raw_affiliation, 'Osmania|IIT|Indian Institute of Technology', 'i'));
