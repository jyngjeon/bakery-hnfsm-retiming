"""Independent schedule checker for the HNFSM model (paper M1-M19).

Ported from the original stage-1 checker.py (notebook cell 26). Logic is
unchanged; messages and comments were translated to English.

Same-group oven overlap is allowed (same interpretation as the decoder), and
OIDT is recomputed on the union of busy intervals per compartment.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def _to_optional_int(val):
    """NaN/None -> None, integer-valued numbers -> int."""
    if val is None or pd.isna(val):
        return None
    if isinstance(val, str) and val.strip().upper() in ("", "NONE", "NAN"):
        return None
    if isinstance(val, (int, np.integer)):
        return int(val)
    if isinstance(val, (float, np.floating)) and float(val).is_integer():
        return int(val)
    raise ValueError(f"non-integer resource index: {val!r}")


def _merge_intervals(intervals):
    """Union of [(st, ct), ...] as a sorted list of disjoint intervals."""
    if not intervals:
        return []
    sorted_ivs = sorted(intervals, key=lambda x: (x[0], x[1]))
    merged = [[sorted_ivs[0][0], sorted_ivs[0][1]]]
    for st, ct in sorted_ivs[1:]:
        if st <= merged[-1][1]:
            if ct > merged[-1][1]:
                merged[-1][1] = ct
        else:
            merged.append([st, ct])
    return [(s, e) for s, e in merged]


def verify_schedule(json_path: str | Path, schedule_df: pd.DataFrame,
                    reported_makespan=None, reported_oidt=None) -> dict:
    """Check a schedule against M1-M19.

    schedule_df needs columns ['g', 'p', 's', 'ST', 'CT', 'assigned_k', 'assigned_l'].
    Returns dict(is_valid, total_violations, violations_by_rule, makespan, oidt, oven_breakdown).
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    machines = {int(m["k"]): m for m in data["machines"]}
    employees = {int(e["l"]): e for e in data["employees"]}
    ops_meta = {(int(op["g"]), int(op["p"]), int(op["s"])): op for op in data["operations"]}

    violations = {
        "completeness": [],            # missing / duplicate / undefined operations
        "duration_M7_M8": [],          # ST < 0 or CT - ST != PT
        "bowl_time_M6": [],            # first-stage offset of derived products
        "no_wait_M9": [],              # consecutive stages
        "eligibility_M10_M15_M19": [], # resource type and eligible lists
        "machine_overlap_M11": [],     # single-capacity machines
        "oven_overlap_M12": [],        # oven compartment, different groups
        "employee_shift_M17_M18": [],  # employee shifts
        "employee_overlap_M16": [],    # employee double booking
        "objective_mismatch": [],      # reported vs recomputed objectives
    }

    required_cols = {"g", "p", "s", "ST", "CT", "assigned_k", "assigned_l"}
    missing_cols = required_cols - set(schedule_df.columns)
    if missing_cols:
        raise KeyError(f"schedule_df is missing columns: {sorted(missing_cols)}")

    # [1] completeness
    sched_map = {}
    for idx, row in schedule_df.iterrows():
        key = (int(row["g"]), int(row["p"]), int(row["s"]))
        if key not in ops_meta:
            violations["completeness"].append(f"undefined operation: {key} (row={idx})")
            continue
        if key in sched_map:
            violations["completeness"].append(f"duplicate operation: {key} (row={idx})")
            continue

        st_raw, ct_raw = row["ST"], row["CT"]
        if pd.isna(st_raw) or pd.isna(ct_raw):
            violations["duration_M7_M8"].append(f"op {key}: ST or CT missing")
            continue
        if not float(st_raw).is_integer() or not float(ct_raw).is_integer():
            violations["duration_M7_M8"].append(f"op {key}: non-integer time ST={st_raw}, CT={ct_raw}")

        st, ct = int(round(float(st_raw))), int(round(float(ct_raw)))
        try:
            ak = _to_optional_int(row["assigned_k"])
            al = _to_optional_int(row["assigned_l"])
        except ValueError as e:
            violations["eligibility_M10_M15_M19"].append(f"op {key}: {e}")
            ak, al = None, None

        sched_map[key] = {"ST": st, "CT": ct, "assigned_k": ak, "assigned_l": al}

    for key in sorted(set(ops_meta) - set(sched_map)):
        violations["completeness"].append(f"missing operation: {key}")

    # [2] duration (M7, M8), eligibility (M10, M15, M19), shifts (M17, M18)
    machine_usage = {k: [] for k in machines}
    employee_usage = {l: [] for l in employees}

    for key, rec in sorted(sched_map.items()):
        meta = ops_meta[key]
        st, ct = rec["ST"], rec["CT"]
        ak, al = rec["assigned_k"], rec["assigned_l"]
        pt = int(meta["PT"])
        rt = meta["resource_type"]

        if st < 0:
            violations["duration_M7_M8"].append(f"op {key}: negative ST={st}")
        if ct - st != pt:
            violations["duration_M7_M8"].append(f"op {key}: CT-ST({ct - st}) != PT({pt}) [ST={st}, CT={ct}]")

        if rt == "NONE":
            if ak is not None or al is not None:
                violations["eligibility_M10_M15_M19"].append(f"op {key} (NONE): resource assigned (k={ak}, l={al})")
        elif rt in ("MACHINE", "OVEN"):
            if al is not None:
                violations["eligibility_M10_M15_M19"].append(f"op {key} ({rt}): employee l={al} assigned")
            if ak is None or ak not in meta["eligible_k"]:
                violations["eligibility_M10_M15_M19"].append(
                    f"op {key} ({rt}): ineligible machine k={ak} (allowed={meta['eligible_k']})")
            else:
                machine_usage[ak].append((st, ct, key))
        elif rt == "EMPLOYEE":
            if ak is not None:
                violations["eligibility_M10_M15_M19"].append(f"op {key} (EMPLOYEE): machine k={ak} assigned")
            if al is None or al not in meta["eligible_l"]:
                violations["eligibility_M10_M15_M19"].append(
                    f"op {key} (EMPLOYEE): ineligible employee l={al} (allowed={meta['eligible_l']})")
            else:
                employee_usage[al].append((st, ct, key))
                emp = employees[al]
                if st < emp["start_l"] or ct > emp["end_l"]:
                    violations["employee_shift_M17_M18"].append(
                        f"op {key}: {emp['employee_name']}(l={al}) shift "
                        f"[{emp['start_l']}, {emp['end_l']}] violated -> [{st}, {ct}]")

    # [3] bowl time (M6) and no-wait (M9)
    for key, rec in sorted(sched_map.items()):
        g, p, s = key
        meta = ops_meta[key]
        if s == 1 and p > 1:
            base_key = (g, 1, 1)
            if base_key in sched_map:
                expected_st = sched_map[base_key]["ST"] + int(meta["WT"])
                if rec["ST"] != expected_st:
                    violations["bowl_time_M6"].append(
                        f"op {key}: ST={rec['ST']} != ST({base_key})+{meta['WT']}({expected_st})")
        if s > 1:
            prev_key = (g, p, s - 1)
            if prev_key in sched_map:
                prev_ct = sched_map[prev_key]["CT"]
                if rec["ST"] != prev_ct:
                    violations["no_wait_M9"].append(
                        f"op {key}: ST={rec['ST']} != previous {prev_key} CT={prev_ct} (gap={rec['ST'] - prev_ct})")

    # [4] single machines (M11), ovens (M12), OIDT
    oven_breakdown = {}
    total_oidt = 0
    for k, m in sorted(machines.items()):
        mtype = m["machine_type"]
        usages = sorted(machine_usage[k], key=lambda x: (x[0], x[1]))

        if mtype == "SINGLE":
            max_ct, max_key = -1, None
            for st, ct, key in usages:
                if st < max_ct:
                    violations["machine_overlap_M11"].append(
                        f"{m['machine_name']}(k={k}) conflict: {max_key}(~{max_ct}) vs {key}({st}~{ct})")
                if ct > max_ct:
                    max_ct, max_key = ct, key

        elif mtype == "OVEN":
            n_u = len(usages)
            for i in range(n_u):
                st_i, ct_i, key_i = usages[i]
                for j in range(i + 1, n_u):
                    st_j, ct_j, key_j = usages[j]
                    if st_j >= ct_i:
                        break
                    if key_i[0] != key_j[0]:
                        violations["oven_overlap_M12"].append(
                            f"{m['machine_name']}(k={k}) different-group conflict: "
                            f"{key_i}[{st_i},{ct_i}] vs {key_j}[{st_j},{ct_j}]")

            merged = _merge_intervals([(st, ct) for st, ct, _ in usages])
            if merged:
                first_st, last_ct = merged[0][0], merged[-1][1]
                busy = sum(e - s for s, e in merged)
                idle = (last_ct - first_st) - busy
            else:
                first_st, last_ct, busy, idle = None, None, 0, 0
            total_oidt += idle
            oven_breakdown[k] = {"machine_name": m["machine_name"], "first_st": first_st,
                                 "last_ct": last_ct, "busy": busy, "idle": idle}
        # UNLIMITED (M13): no overlap check

    # [5] employee overlap (M16)
    for l, emp in sorted(employees.items()):
        usages = sorted(employee_usage[l], key=lambda x: (x[0], x[1]))
        max_ct, max_key = -1, None
        for st, ct, key in usages:
            if st < max_ct:
                violations["employee_overlap_M16"].append(
                    f"{emp['employee_name']}(l={l}) conflict: {max_key}(~{max_ct}) vs {key}({st}~{ct})")
            if ct > max_ct:
                max_ct, max_key = ct, key

    # [6] objectives
    calc_makespan = max((r["CT"] for r in sched_map.values()), default=0)
    if reported_makespan is not None and int(reported_makespan) != calc_makespan:
        violations["objective_mismatch"].append(
            f"makespan mismatch: reported={reported_makespan} vs recomputed={calc_makespan}")
    if reported_oidt is not None and int(reported_oidt) != total_oidt:
        violations["objective_mismatch"].append(
            f"OIDT mismatch: reported={reported_oidt} vs recomputed={total_oidt}")

    total_violations = sum(len(v) for v in violations.values())
    return {
        "is_valid": total_violations == 0,
        "total_violations": total_violations,
        "violations_by_rule": violations,
        "makespan": calc_makespan,
        "oidt": total_oidt,
        "oven_breakdown": oven_breakdown,
    }


def format_report(report: dict, title: str = "schedule check") -> str:
    status = "PASS (0 violations)" if report["is_valid"] else f"FAIL ({report['total_violations']} violations)"
    lines = [f"=== [{title}] {status} ===",
             f"recomputed makespan = {report['makespan']} | recomputed OIDT = {report['oidt']}"]
    for rule, msgs in report["violations_by_rule"].items():
        if msgs:
            lines.append(f"  - [{rule}] {len(msgs)} (e.g. {msgs[0]})")
    return "\n".join(lines)
