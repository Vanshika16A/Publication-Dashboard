import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = ROOT / "config" / "build.toml"
CONFIG = tomllib.loads(CONFIG_FILE.read_text())

OPENALEX_ROOT = ROOT / "data" / "raw" / "openalex"
EXTERNAL = ROOT / "data" / "external"
METADATA = ROOT / "data" / "metadata"
PROCESSED = ROOT / "data" / "processed"
BUILDS = ROOT / "data" / "builds"
# List files (CSV/TXT) of the latest build only, overwritten by every build; build folders keep
# the small JSON/markdown summaries, whose manifest records each list file's sha256.
LISTS = BUILDS / "latest"

DATASET = PROCESSED / "group16_data.csv"
ENRICHED = PROCESSED / "group16_data_enriched.csv"
CITATION_NETWORK = ROOT / "data" / "networks" / "citation_network.csv"
AUTHORSHIP_NETWORK = ROOT / "data" / "networks" / "authorship_network.csv"
INDIAN_CONNECTIONS = ROOT / "data" / "networks" / "indian_connections.csv"

GROUP_NUMBER = 16
START_YEAR = CONFIG["build"]["start_year"]
END_YEAR = CONFIG["build"]["end_year"]
INSTITUTIONS = (
    "Jawaharlal Nehru University",
    "University of Hyderabad",
    "University of Delhi",
)
RAW_COLUMNS = (
    "group",
    "institution",
    "author",
    "title",
    "year",
    "type",
    "journal_name",
    "issn",
    "doi",
    "citations",
    "quartile",
    "coauthor_institutes",
    "cites_indian_inst",
    "cited_by_indian_inst",
)


def snapshot_dir(snapshot_id: str) -> Path:
    return OPENALEX_ROOT / snapshot_id
