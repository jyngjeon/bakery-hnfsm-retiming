"""Repository-relative paths. Everything resolves from the repo root, so scripts
and notebooks work regardless of the current working directory."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = REPO_ROOT / "data" / "raw"
DATA_PROCESSED = REPO_ROOT / "data" / "processed"
RESULTS = REPO_ROOT / "results"

RAW_FILES = {
    "BK15": DATA_RAW / "Babor M-Hitzmann B-2022-Small and medium-sized bakery production data for scheduling-BK15.xlsx",
    "BK50": DATA_RAW / "Babor M-Hitzmann B-2022-Small and medium-sized bakery production data for scheduling-BK50.xlsx",
    "BK20": DATA_RAW / "BK20.xlsx",
}


def processed_json(name: str) -> Path:
    """Cleaned instance JSON, e.g. processed_json("BK15") -> data/processed/bk15-clean.json."""
    return DATA_PROCESSED / f"{name.lower()}-clean.json"


def processed_xlsx(name: str) -> Path:
    return DATA_PROCESSED / f"{name.lower()}-clean.xlsx"


def results_dir(experiment: str) -> Path:
    d = RESULTS / experiment
    d.mkdir(parents=True, exist_ok=True)
    return d
