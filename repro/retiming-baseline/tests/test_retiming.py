"""Boundary cases plus a separately implemented integer-time oracle."""

import json

import numpy as np
import pandas as pd
import pytest

from bakery.checker import verify_schedule
from bakery.decoder import hnfsm_decode, load_hnfsm_instance
from bakery.paths import processed_json
from bakery.retiming import RetimingContext, retime_schedule, verify_retiming_invariants
from bakery.retiming_audit import ExhaustiveOracle


def case(tmp_path, rows, *, machine_types=None, shifts=None):
    """Rows: (g,p,s,ST,PT,k,l,WT); build explicit source and detailed schedule."""
    machine_types = machine_types or {1: "OVEN", 2: "SINGLE", 3: "UNLIMITED"}
    shifts = shifts or {1: (0, 1000)}
    machines = [{"k": k, "orig_machine_id": k, "machine_name": f"K{k}",
                 "machine_category": kind, "machine_type": kind}
                for k, kind in machine_types.items()]
    employees = [{"l": l, "employee_name": f"L{l}", "start_l": start, "end_l": end}
                 for l, (start, end) in shifts.items()]
    operations, schedules = [], []
    for g, p, s, st, pt, k, l, wt in rows:
        rt = "EMPLOYEE" if l is not None else (
            "OVEN" if k is not None and machine_types[k] == "OVEN" else
            ("MACHINE" if k is not None else "NONE"))
        op = {"g": g, "p": p, "s": s, "PT": pt, "WT": wt, "resource_type": rt,
              "eligible_k": [] if k is None else [k], "eligible_l": [] if l is None else [l],
              "orig_pr_group": g, "batch_no": 1, "product_name": f"P{g}-{p}",
              "stage_name": "Baking" if rt == "OVEN" else "Other", "resource_category": rt}
        operations.append(op)
        schedules.append({"g": g, "p": p, "s": s, "ST": st, "CT": st + pt,
                          "PT": pt, "assigned_k": k, "assigned_l": l, "note": "retained"})
    path = tmp_path / f"case-{len(list(tmp_path.glob('case-*.json')))}.json"
    path.write_text(json.dumps({"machines": machines, "employees": employees,
                                "operations": operations}), encoding="utf-8")
    instance, frame = load_hnfsm_instance(path), pd.DataFrame(schedules)
    assert verify_schedule(path, frame)["is_valid"]
    return instance, frame, path


def assert_oracle(instance, frame, path):
    ctx = RetimingContext(instance, frame, path)
    oracle = ExhaustiveOracle(instance, frame)
    assert (ctx.makespan, ctx.oidt) == (oracle.makespan, oracle.oidt)
    assert ctx.boundary_groups() == oracle.boundary_groups()
    for preserve in (False, True):
        for g in ctx.group_ids:
            events = ctx.group_search(g, preserve_order=preserve)
            exhaustive = oracle.scan_group(g, preserve_order=preserve)
            expanded = tuple(t for lo, hi in events.intervals for t in range(lo, hi + 1))
            assert expanded == exhaustive.feasible_times
            assert events.best == exhaustive.best
        full = ctx.retime(boundary_only=False, preserve_order=preserve)
        boundary = ctx.retime(preserve_order=preserve)
        assert full.oidt == boundary.oidt
        for result in (full, boundary):
            assert result.checker["is_valid"] and result.invariants["is_valid"]
            assert result.makespan <= ctx.makespan and result.oidt <= ctx.oidt
    return ctx


def test_touching_boundaries_and_disjoint_feasible_windows(tmp_path):
    args = case(tmp_path, [(1, 1, 1, 0, 2, 1, None, 0), (2, 1, 1, 4, 2, 1, None, 0),
                           (3, 1, 1, 8, 2, 1, None, 0), (4, 1, 1, 0, 12, None, None, 0)])
    ctx = assert_oracle(*args)
    assert ctx.feasible_intervals(1) == ((0, 2), (6, 6), (10, 10))
    assert ctx.feasible_intervals(1, preserve_order=True) == ((0, 2),)


def test_employee_shift_end_is_inclusive(tmp_path):
    args = case(tmp_path, [(1, 1, 1, 5, 2, None, 1, 0), (2, 1, 1, 0, 15, None, None, 0)],
                shifts={1: (5, 10)})
    assert assert_oracle(*args).feasible_intervals(1) == ((5, 8),)


def test_partial_same_group_cobaking_uses_union(tmp_path):
    args = case(tmp_path, [(1, 1, 1, 0, 4, 1, None, 0), (1, 2, 1, 1, 4, 1, None, 1),
                           (2, 1, 1, 10, 2, 1, None, 0)])
    ctx = assert_oracle(*args)
    assert ctx.oidt == 5
    result = ctx.retime()
    assert (result.makespan, result.oidt) == (7, 0)
    assert ctx.feasible_intervals(1) == ((0, 5),)


def test_unlimited_resource_has_neither_collision_nor_order_limit(tmp_path):
    args = case(tmp_path, [(1, 1, 1, 0, 4, 3, None, 0), (2, 1, 1, 5, 4, 3, None, 0),
                           (3, 1, 1, 0, 12, None, None, 0)])
    ctx = assert_oracle(*args)
    assert ctx.feasible_intervals(1) == ((0, 8),)
    assert ctx.feasible_intervals(1, preserve_order=True) == ((0, 8),)


def test_no_oven_group_and_makespan_only_boundary_limitation(tmp_path):
    instance, frame, path = case(tmp_path, [(1, 1, 1, 10, 2, None, None, 0),
                                           (2, 1, 1, 0, 4, None, None, 0)])
    ctx = assert_oracle(instance, frame, path)
    assert ctx.boundary_groups() == ()
    assert not ctx.retime().moved
    assert ctx.retime(boundary_only=False).makespan == 4


def test_multiple_oven_compartments_and_knots(tmp_path):
    args = case(tmp_path, [(1, 1, 1, 0, 3, 1, None, 0), (1, 2, 1, 5, 2, 2, None, 5),
                           (2, 1, 1, 10, 2, 1, None, 0), (3, 1, 1, 12, 3, 2, None, 0),
                           (4, 1, 1, 0, 20, None, None, 0)],
                machine_types={1: "OVEN", 2: "OVEN"})
    assert_oracle(*args)


def test_tied_oven_boundaries_include_all_compartments(tmp_path):
    args = case(tmp_path, [(1, 1, 1, 0, 2, 1, None, 0), (1, 2, 1, 0, 2, 1, None, 0),
                           (2, 1, 1, 0, 2, 2, None, 0), (3, 1, 1, 8, 2, 1, None, 0),
                           (4, 1, 1, 8, 2, 2, None, 0)], machine_types={1: "OVEN", 2: "OVEN"})
    assert assert_oracle(*args).boundary_groups() == (1, 2, 3, 4)


def test_resource_order_change_improves_more_than_fixed_order(tmp_path):
    args = case(tmp_path, [(1, 1, 1, 0, 2, 1, None, 0), (2, 1, 1, 5, 2, 1, None, 0),
                           (3, 1, 1, 10, 2, 1, None, 0)])
    ctx = assert_oracle(*args)
    allowed, fixed = ctx.retime(), ctx.retime(preserve_order=True)
    assert allowed.oidt == 1 < fixed.oidt == 3
    assert (allowed.moved_group, allowed.new_tg) == (3, 2)
    assert list(allowed.schedule.sort_values("ST")["g"]) == [1, 3, 2]


def test_unchanged_no_improvement_and_input_is_never_modified(tmp_path):
    instance, frame, path = case(tmp_path, [(1, 1, 1, 0, 2, 1, None, 0),
                                           (2, 1, 1, 2, 2, 1, None, 0)])
    before = frame.copy(deep=True)
    result = retime_schedule(instance, frame, path)
    assert not result.moved and result.delta == 0
    assert result.moved_group is None and result.search.move is None
    pd.testing.assert_frame_equal(before, frame)
    pd.testing.assert_frame_equal(before, result.schedule)
    result.schedule.loc[0, "ST"] = 99
    pd.testing.assert_frame_equal(before, frame)


def test_makespan_increasing_start_excluded(tmp_path):
    args = case(tmp_path, [(1, 1, 1, 0, 2, 1, None, 0), (2, 1, 1, 10, 2, 1, None, 0)])
    ctx = assert_oracle(*args)
    # T=12 would fill a gap by placing group 1 after group 2, but ends after C0.
    assert 12 not in ctx.group_search(1).candidates
    assert all(hi <= 10 for _, hi in ctx.feasible_intervals(1))


def test_oidt_increasing_candidate_is_rejected(tmp_path):
    instance, frame, path = case(tmp_path, [(1, 1, 1, 5, 2, 1, None, 0),
                                           (2, 1, 1, 9, 2, 1, None, 0),
                                           (3, 1, 1, 0, 20, None, None, 0)])
    oracle = ExhaustiveOracle(instance, frame)
    assert oracle.feasible(1, 0)
    assert oracle.objectives(1, 0)[1] > oracle.oidt
    result = retime_schedule(instance, frame, path)
    assert result.oidt == 0 < oracle.oidt


def test_numeric_group_then_start_tiebreak_and_determinism(tmp_path):
    instance, frame, path = case(tmp_path, [(2, 1, 1, 10, 2, 1, None, 0),
                                           (1, 1, 1, 0, 2, 1, None, 0),
                                           (3, 1, 1, 0, 20, None, None, 0)])
    baseline = frame.copy(deep=True)
    results = [retime_schedule(instance, frame, path) for _ in range(3)]
    for result in results:
        assert (result.oidt, result.makespan, result.moved_group, result.new_tg) == (0, 20, 1, 8)
        pd.testing.assert_frame_equal(result.schedule, results[0].schedule)
    pd.testing.assert_frame_equal(frame, baseline)


def test_all_stages_shift_and_invariant_audit_detects_partial_shift(tmp_path):
    instance, frame, path = case(tmp_path, [(1, 1, 1, 0, 2, None, None, 0),
                                           (1, 1, 2, 2, 2, 1, None, 0),
                                           (2, 1, 1, 10, 2, 1, None, 0),
                                           (3, 1, 1, 0, 20, None, None, 0)])
    before = frame.copy(deep=True)
    result = retime_schedule(instance, frame, path)
    assert result.moved and result.invariants["is_valid"]
    changed = result.schedule.copy()
    changed.loc[changed.index[0], "ST"] += 1
    assert not verify_retiming_invariants(before, changed, result.moved_group, result.delta)["is_valid"]
    changed = result.schedule.copy()
    changed.loc[changed.index[0], "assigned_k"] = 2
    assert not verify_retiming_invariants(before, changed, result.moved_group, result.delta)["is_valid"]
    pd.testing.assert_frame_equal(before, frame)


@pytest.mark.parametrize("damage", ["missing-column", "missing-row", "duplicate", "undefined", "fractional",
                                    "infinite", "negative", "resource", "no-wait", "oven-conflict", "PT"])
def test_invalid_or_incomplete_input_is_rejected(tmp_path, damage):
    instance, frame, path = case(tmp_path, [(1, 1, 1, 0, 2, None, None, 0),
                                           (1, 1, 2, 2, 2, 1, None, 0),
                                           (2, 1, 1, 10, 2, 1, None, 0)])
    if damage == "missing-column":
        frame = frame.drop(columns="CT")
    elif damage == "missing-row":
        frame = frame.iloc[1:]
    elif damage == "duplicate":
        frame = pd.concat([frame, frame.iloc[:1]], ignore_index=True)
    elif damage == "undefined":
        frame.loc[0, "g"] = 999
    elif damage in ("fractional", "infinite", "negative"):
        frame = frame.astype({"ST": float})
        frame.loc[0, "ST"] = {"fractional": 0.5, "infinite": np.inf, "negative": -1}[damage]
    elif damage == "resource":
        frame.loc[1, "assigned_k"] = 999
    elif damage == "no-wait":
        frame.loc[1, ["ST", "CT"]] += 1
    elif damage == "PT":
        frame.loc[0, "PT"] += 1
    else:
        frame.loc[2, ["ST", "CT"]] = [3, 5]
    with pytest.raises(ValueError):
        retime_schedule(instance, frame, path)


def test_none_empty_unknown_group_and_fractional_resource(tmp_path):
    instance, frame, path = case(tmp_path, [(1, 1, 1, 0, 2, 1, None, 0)])
    for bad in (None, pd.DataFrame(), frame.assign(assigned_k=1.5)):
        with pytest.raises(ValueError):
            retime_schedule(instance, bad, path)
    with pytest.raises(ValueError):
        RetimingContext(instance, frame, path).feasible_intervals(999)
    for bad_instance in (None, {}, {"machines": {}}):
        with pytest.raises(ValueError):
            RetimingContext(bad_instance, frame, path)


@pytest.mark.parametrize("seed", range(12))
def test_small_random_instances_against_independent_enumeration(tmp_path, seed):
    rng = np.random.default_rng(seed)
    rows, time = [], 0
    for g in range(1, 6):
        pt = int(rng.integers(1, 5))
        resource = int(rng.integers(0, 5))
        k, l = (resource if 1 <= resource <= 3 else None), (1 if resource == 4 else None)
        rows.append((g, 1, 1, time, pt, k, l, 0))
        time += pt + int(rng.integers(0, 4))
    assert_oracle(*case(tmp_path, rows, shifts={1: (0, time + 2)}))


@pytest.mark.parametrize("name, expected", [("BK15", (519, 272)), ("BK50", (1202, 2357))])
def test_current_natural_schedules(name, expected):
    path = processed_json(name)
    instance = load_hnfsm_instance(path)
    _, _, frame = hnfsm_decode(instance, instance["group_ids"], return_schedule=True)
    before = frame.copy(deep=True)
    result = retime_schedule(instance, frame, path)
    assert (result.makespan, result.oidt) == expected
    assert result.checker["is_valid"] and result.invariants["is_valid"]
    pd.testing.assert_frame_equal(before, frame)
