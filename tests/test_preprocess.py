"""Preprocessing must reproduce the committed data/processed/*-clean.json exactly."""

import json

import pytest

from bakery.paths import processed_json
from bakery.preprocess import PIPELINES


@pytest.mark.parametrize("name", ["BK15", "BK50"])
def test_preprocess_matches_committed_json(name):
    tables = PIPELINES[name]()
    built = {k: json.loads(df.to_json(orient="records")) for k, df in tables.items()}
    with open(processed_json(name), encoding="utf-8") as f:
        committed = json.load(f)
    assert built == committed


def test_instance_sizes():
    bk15, bk50 = PIPELINES["BK15"](), PIPELINES["BK50"]()
    assert len(bk15["operations"]) == 164 and bk15["operations"]["g"].nunique() == 16
    assert len(bk50["operations"]) == 679 and bk50["operations"]["g"].nunique() == 62
    assert (bk50["machines"]["machine_type"] == "OVEN").sum() == 9
