# DPCN A2 [Group 16]

- Jawaharlal Nehru University (JNU)
- University of Hyderabad (Hyderabad Central University)
- University of Delhi

## setting up

download the folders data/ and external/ from [this link](https://iiithydresearch-my.sharepoint.com/:f:/g/personal/farzana_s_research_iiit_ac_in/IgCGbhDTSF6oQKHt3uExTr9SAYgu_BHG45v0vsJsEmWeEeo?e=sk9h2T) and place them both in collector/ so you have collector/data/ and collector/external/ respectively.

each time you pull changes from the repo, please run:

```bash
python -m collector build
python -m collector clean
python -m collector networks
```

The required submission CSVs are in `collector/data/output/`: `group16_data.csv` is there, and `citation_network.csv`, `authorship_network.csv`, and `indian_connections.csv` are in `collector/data/output/networks/`.

## dashboard

### view locally

requires node.js 20 or newer.

```bash
cd dashboard
npm install
npm run dev
```

open http://localhost:5173 in your browser.

### update dashboard data (after build / clean / networks)

```bash
pip install -r collector/requirements.txt
python -m collector dashboard-data
```

