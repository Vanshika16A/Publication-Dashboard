## DPCN Research Mapping Project

## Instruction Note for All Groups · 2026

| Instructor | Issued | Groups | Institutions |
| --- | --- | --- | --- |
| ---- | Academic Year 2026 | 30 Independent Groups | 43+ Covered |

## 1. Overview

This course project maps the research output of 43+ Indian institutions spanning IITs, IIITs, NITs, Central Universities, IISERs, CSIR labs, and DAE institutes over 2016–2026. Each of the 30 independent groups is responsible for four deliverables: a raw dataset, a statistics report, an interactive dashboard, and network analysis files.

⚠ Key Rule: All groups work fully independently. No data sharing between groups. The professor collects every output at the end. If two or three groups wish to collaborate, please inform the instructor immediately.

## 2. Four Core Tasks

- 1. Data Collection: Fetch all faculty publications (2016–2026) for your 2–3 assigned institutions using OpenAlex, IRINS, or Scopus. Export to CSV with the column structure specified in Section 5.

- 2. Statistics Report: Analyse the dataset and compute key metrics at faculty, department, and institution level (publication trend, Q1 fraction, h-index distribution, top journals, citation counts, etc.).

- 3. Interactive Dashboard: Build and submit an interactive dashboard that displays all results for your assigned institutions. Required panels are listed in Section 4.

- 4. Network Analysis: Build and submit citation and authorship network files for your assigned institutions. Details in Section 6.

New in 2026: Citation Networks and Authorship Networks are now required deliverables (Week 2). See Sections 6 and 7 for full specifications.

## 3. Group Assignments

Each group is assigned 2–3 institutions from the same cluster. We are group 16.

| Groups | Cluster | Institutions Covered |
| --- | --- | --- |
| Groups 16 | Central Universities | JNU, Hyderabad Central University, University of Delhi |

Newer IITs: Cross-check institute website for faculty who joined before 2018 — OpenAlex coverage may be thin. 
ISI / IMSc / HRI (Groups 21–23): Use the ROR ID directly (e.g. ror.org/01an7q238 for ISI) to avoid wrong-institution matches.

## 4. Dashboard — Required Panels

Your interactive dashboard must include at least these panels for each assigned institution:

- Publication trend chart: Line or bar chart — papers per year, 2016–2026

- Faculty list: Name, department, h-index, total papers

- Journal quartile distribution: Stacked or pie chart — Q1 / Q2 / Q3 / Q4 share

- Faculty performance table: Sortable — papers, citations, top journal, h-index

- Top journals: Top 5 journals per institution by paper count

- h-index distribution: Histogram of faculty h-index values

- Research area breakdown: Publication share by domain / field

- Most-cited papers: Top 10 — title, journal, year, citation count, DOI

- Conference rank (where applicable): CORE A* / A / B / C breakdown

- Citation network visualisation: Interactive directed graph — nodes = papers, edges = citations (NEW)

- Authorship network visualisation: Interactive undirected graph — nodes = authors, edges = co-authorship (NEW)

## 5. Dataset — CSV Column Structure

Submit one CSV file per group, named groupN_data.csv (e.g. group12_data.csv). The file must include all of the following columns:

| Column Name | Description |
| --- | --- |
| group | Your group number |
| institution | Assigned institution name |
| author | Faculty / author full name |
| title | Paper / article title |
| year | Publication year (2016–2026) |
| type | journal or conference |


| journal_name Journal or conference name issn ISSN (journals only) doi DOI URL citations Citation count at collection date quartile Q1 / Q2 / Q3 / Q4 or CORE A*/A/B/C coauthor_institutes Semicolon-separated list of co-author institutions (for Indian connections) cites_indian_inst TRUE if paper cites a paper from another Indian institution cited_by_indian_inst TRUE if paper is cited by another Indian institution |   |
| --- | --- |

Indian connection note: The three new columns (coauthor_institutes, cites_indian_inst, cited_by_indian_inst) capture cross-institute links in your raw data. Your statistical analysis must remain within your assigned institutions only.

## 6. Citation Networks & Authorship Networks (Task 4)

Every group must now build and submit two network files alongside the main dataset. Both are due in Week 2.

## 6a. Citation Network

A directed graph where each node is a paper and each edge means "paper A cites paper B". Build it from your dataset's DOIs and citation data.

- Extract paper-cites-paper pairs from OpenAlex (referenced_works field) or Scopus

- Compute in-degree per paper: = cited-by count within your institution's corpus

- Compute PageRank: to find the most influential papers in your cluster

- Map citation flow: into and out of your assigned institutions from/to other Indian institutes

- Identify cross-institute citation edges: flag them in your raw CSV (cites_indian_inst column)

- Export as edge-list CSV: columns: source_doi, target_doi, source_inst, target_inst, year

- Visualise: directed network graph using Gephi, NetworkX, or D3.js

## 6b. Authorship Network

An undirected graph where each node is a faculty member and each edge means "these two people co-authored a paper". Extract from your paper data.

- Extract co-author pairs from every paper in your dataset

- Build an undirected graph: nodes = authors, edges = co-authorship events

- Compute degree centrality: = most collaborative faculty at your institutions

- Compute betweenness centrality: = faculty who bridge otherwise disconnected groups

- Apply community detection: Louvain or Leiden algorithm to find collaboration clusters

- Flag cross-institution edges: these are the Indian inter-institute connections

- Export as edge-list CSV: columns: author_a, author_b, paper_doi, inst_a, inst_b, year

- Visualise: collaboration clusters using Gephi or NetworkX


## 7. Indian Connectivity: Citation Flow & Raw Data

This section captures how your institutions are embedded in the broader Indian research network — who cites you, who you cite, and who your faculty collaborate with.

## 7a. Citation Flow

- Count citations received from other Indian institutes (in-flow)

- Count citations given to other Indian institutes (out-flow)

- Identify the top 10 Indian institutes citing your institution's work

- Compute citation impact ratio: In-cites / Out-cites per institution

- Produce a year-wise citation flow chart (2016–2026)

## 7b. Connectivity Map

- List every Indian institution your faculty co-author with

- Rank partner institutions by number of shared papers

- Show co-authorship strength: number of joint papers per partner institution

- Flag cross-cluster links: IIT ↔ CSIR, IIT ↔ IISER, CSIR ↔ DAE, etc.

- Compute Jaccard similarity of research topics between your institutes and partners

## 7c. Network Files to Submit

Submit these three additional files with your Week 2 dataset delivery:

| Filename Required Columns Description citation_network.csv source_doi, target_doi, source_inst, target_inst, Directed edges — paper A cites paper B year authorship_network.csv author_a, author_b, paper_doi, inst_a, inst_b, Undirected co-authorship edges year indian_connections.csv your_inst, partner_inst, shared_papers, Aggregated cross-institute links total_citations |   |
| --- | --- |

Scope reminder: Build and analyse networks WITHIN your assigned institutions. Include cross-institute edges in the raw files only. Do not merge your data with another group's data.

## 8. Statistics Report

Submit a short report — maximum 10 slides or 5 pages — covering your assigned institutions at faculty, department, and institution level. It must address:

- Publication trend (2016–2026): total and per-year breakdown

- Q1 fraction per institution: percentage of papers in Q1 journals

- h-index distribution of faculty

- Top 5 journals for each institution

- Most-cited papers (top 10)

- Research area breakdown


- Citation network summary: PageRank top-10, in-degree distribution, cross-institute flow (NEW)

- Authorship network summary: degree & betweenness centrality, community structure (NEW)

## 9. Recommended Tools & Sources

- OpenAlex: Primary source for publications & cited_by data (API: openalex.org)

- IRINS: Indian Research Information Network — useful for institutional coverage

- Scopus: Secondary source for quartile and citation data

- ROR IDs: Use institution ROR IDs for accurate OpenAlex queries (esp. ISI, TIFR, CSIR)

- Scimago / JCR: Journal quartile (Q1–Q4) lookup

- CORE Portal: Conference rank (A* / A / B / C)

- NetworkX (Python): Build, analyse, and export citation & authorship networks

- Gephi: Desktop network visualisation and community detection (Louvain)

- D3.js / Cytoscape.js: Interactive network visualisation for the dashboard

## 10. Submission Timeline

| Deadline | Deliverable | Details |
| --- | --- | --- |
| Week1-2 | 📁 Dataset + Network | groupN_data.csv + citation_network.csv + |
|   | Files | authorship_network.csv + indian_connections.csv |
| Week 3 | 📊 Report + 🖥 | Statistics report (≤10 slides / ≤5 pages) + interactive |
|   | Dashboard | dashboard including network visualisations |

## 11. Submission Checklist

Before submitting, verify each item:

- groupN_data.csv named correctly and contains all required columns including three new network columns

- Data covers years 2016 to 2026 only

- All assigned institutions are included in the dataset

- citation_network.csv submitted (source_doi, target_doi, source_inst, target_inst, year)

- authorship_network.csv submitted (author_a, author_b, paper_doi, inst_a, inst_b, year)

- indian_connections.csv submitted (your_inst, partner_inst, shared_papers, total_citations)

- Statistics report does not exceed 10 slides or 5 pages (use dahborad)

- Report covers all required metrics + citation & authorship network summaries

- Dashboard includes network visualisation panels (citation graph + co-authorship graph)

- All deliverables submitted to the professor — no sharing with other groups

- If collaborating with another group — instructor has been notified in advance
