"""Regression tests for the HNFSM decoder and the checker."""

import json
from pathlib import Path

import numpy as np
import pytest

from bakery.checker import verify_schedule
from bakery.decoder import hnfsm_decode, load_hnfsm_instance, spv_to_group_order
from bakery.paths import processed_json

DATA = Path(__file__).parent / "data"


@pytest.mark.parametrize("name, expected", [("BK15", (519, 273)), ("BK50", (1202, 2409))])
def test_natural_order_matches_stage1_notebook(name, expected):
    path = processed_json(name)
    inst = load_hnfsm_instance(path)
    ms, oidt, df = hnfsm_decode(inst, inst["group_ids"], return_schedule=True)
    assert (ms, oidt) == expected
    assert verify_schedule(path, df, ms, oidt)["is_valid"]


def test_random_spv_matches_stage1_notebook():
    rng = np.random.default_rng(42)
    got = []
    for name in ("BK15", "BK50"):
        inst = load_hnfsm_instance(processed_json(name))
        order = spv_to_group_order(rng.uniform(0.0, 1.0, size=len(inst["group_ids"])), inst["group_ids"])
        got.append(hnfsm_decode(inst, order)[:2])
    assert got == [(534, 221), (1259, 2866)]


def test_spv_paper_table3():
    # Paper Table 3: [1.22, -1.08, 1.90] -> {2, 1, 3}
    assert spv_to_group_order([1.22, -1.08, 1.90], [1, 2, 3]) == [2, 1, 3]


def test_paper_table1_worked_example():
    # Paper Table 1 / Fig. 2: makespan ~244, oven idle gap 53
    path = DATA / "paper-table1-example.json"
    inst = load_hnfsm_instance(path)
    ms, oidt, df = hnfsm_decode(inst, inst["group_ids"], return_schedule=True)
    assert (ms, oidt) == (244, 53)
    assert verify_schedule(path, df, ms, oidt)["is_valid"]


def test_unlimited_machine_has_no_capacity_limit(tmp_path):
    # Two groups proofing at the same time on one UNLIMITED machine must not block each other.
    ops = []
    for g in (1, 2):
        ops.append({"g": g, "p": 1, "s": 1, "PT": 30, "WT": 0, "resource_type": "MACHINE",
                    "eligible_k": [1], "eligible_l": [], "orig_pr_group": g, "batch_no": 1,
                    "product_name": f"P{g}", "stage_name": "Proofing", "resource_category": "Proving chamber"})
    data = {
        "machines": [{"k": 1, "orig_machine_id": 1, "machine_name": "Proving chamber",
                      "machine_category": "Proving chamber", "machine_type": "UNLIMITED"}],
        "employees": [{"l": 1, "employee_name": "E1", "start_l": 0, "end_l": 500}],
        "operations": ops,
    }
    path = tmp_path / "unlimited.json"
    path.write_text(json.dumps(data))
    inst = load_hnfsm_instance(path)
    ms, oidt, df = hnfsm_decode(inst, [1, 2], return_schedule=True)
    assert ms == 30 and (df["ST"] == 0).all()
    assert verify_schedule(path, df, ms, oidt)["is_valid"]


def test_oidt_m2_double_subtracts_overlap():
    from bakery.decoder import oidt_m2, oidt_union
    ivs = {1: [(0, 10), (0, 10), (20, 30)]}  # two products baked together, then one more
    assert oidt_union(ivs) == 10
    assert oidt_m2(ivs) == 0  # 30 - 0 - (10 + 10 + 10); overlap counted twice


@pytest.mark.parametrize("kw", [{"oven_rule": "used_first"}, {"oven_rule": "min_idle"},
                                {"cobake": "same_start"}, {"cobake": "same_start_end"}])
def test_decoder_variants_are_feasible(kw):
    path = processed_json("BK15")
    inst = load_hnfsm_instance(path)
    ms, oidt, df = hnfsm_decode(inst, inst["group_ids"], return_schedule=True, **kw)
    assert verify_schedule(path, df, ms, oidt)["is_valid"]
    if "cobake" in kw:
        oven = df[df["assigned_k"].isin(inst["oven_k"])]
        for (_, k), grp in oven.groupby(["g", "assigned_k"]):
            rows = grp.to_dict("records")
            for i, a in enumerate(rows):
                for b in rows[i + 1:]:
                    if a["ST"] < b["CT"] and b["ST"] < a["CT"]:
                        assert a["ST"] == b["ST"]
                        if kw["cobake"] == "same_start_end":
                            assert a["CT"] == b["CT"]
