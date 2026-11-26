"""HNFSM decoder: SPV rule + greedy group-by-group placement (Babor et al. 2023).

Ported from the original stage-1 notebook (cell 13). Behaviour is unchanged
except for one bug fix: operations on UNLIMITED machines (M13) no longer raise
KeyError; they take the first eligible machine without a capacity check.

Rules not specified by the paper (see docs/paper-conformance.md):
- T_g search: minute by minute from 0, earliest T_g where every constrained
  operation of the group finds a free resource.
- Resource tie-break: first-fit, lowest index.
- Oven (M12): different groups may not overlap; same-group overlap is allowed.
- OIDT: per-compartment idle time on the union of busy intervals.
- Infeasible group (cannot fit within employee shifts): returns (INFEASIBLE, INFEASIBLE).

Variants for sensitivity runs (docs/TODO.md A1, A3, A4); defaults reproduce the
behaviour above exactly:
- oven_rule: "first_fit" (default) | "used_first" (prefer an already-used
  compartment, smallest gap to its busy time) | "min_idle" (smallest increase
  of the compartment's union idle time).
- cobake: "any" (default) | "same_start" | "same_start_end" (Fig. 3 form).
- oidt: "union" (default) | "m2" (paper M2 as written, PT summed per product).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

INFEASIBLE = 10**9


# ----------------------------------------------------------------------------
# SPV rule (paper Table 3)
# ----------------------------------------------------------------------------
def spv_to_group_order(vector, group_ids):
    """Sort indices of a real vector ascending -> product-group priority order."""
    order_idx = np.argsort(vector, kind="mergesort")
    return [group_ids[i] for i in order_idx]


# ----------------------------------------------------------------------------
# Instance loading and precomputation
# ----------------------------------------------------------------------------
def load_hnfsm_instance(json_path: str | Path) -> dict:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    machines = {m["k"]: m for m in data["machines"]}
    employees = {e["l"]: e for e in data["employees"]}
    ops = data["operations"]

    single_k = sorted(k for k, m in machines.items() if m["machine_type"] == "SINGLE")
    oven_k = sorted(k for k, m in machines.items() if m["machine_type"] == "OVEN")
    unlimited_k = sorted(k for k, m in machines.items() if m["machine_type"] == "UNLIMITED")
    emp_l = sorted(employees.keys())

    # M6, M8, M9: fixed interval [rel_s, rel_e) of every operation relative to T_g
    wt_first = {(op["g"], op["p"]): op["WT"] for op in ops if op["s"] == 1}
    ops_by_group: dict[int, list] = {}
    cum_pt = {}
    for op in sorted(ops, key=lambda x: (x["g"], x["p"], x["s"])):
        g, p, s, pt = op["g"], op["p"], op["s"], op["PT"]
        if s == 1:
            cum_pt[(g, p)] = wt_first[(g, p)]
        rel_s = cum_pt[(g, p)]
        rel_e = rel_s + pt
        cum_pt[(g, p)] = rel_e
        base_mask = ((1 << pt) - 1) << rel_s  # bitmask of [rel_s, rel_e)
        ops_by_group.setdefault(g, []).append((op, rel_s, rel_e, base_mask))

    group_ids = sorted(ops_by_group.keys())
    max_emp_end = max(e["end_l"] for e in employees.values())
    max_span = max(max(re for _, _, re, _ in gops) for gops in ops_by_group.values())
    horizon = max_emp_end + max_span + 100

    # Upper bound of T_g (latest employee shift end) and constrained ops per group
    group_max_tg, group_span, group_constrained = {}, {}, {}
    for g, gops in ops_by_group.items():
        group_span[g] = max(re for _, _, re, _ in gops)
        emp_rel_ends = [re for op, _, re, _ in gops if op["resource_type"] == "EMPLOYEE"]
        group_max_tg[g] = (max_emp_end - max(emp_rel_ends)) if emp_rel_ends else (horizon - group_span[g])
        group_constrained[g] = [item for item in gops if item[0]["resource_type"] != "NONE"]

    # M17-M18: off-shift time is pre-blocked
    full_mask = (1 << (horizon + 1)) - 1
    emp_init_mask = {}
    for l, e in employees.items():
        avail_mask = ((1 << (e["end_l"] - e["start_l"])) - 1) << e["start_l"]
        emp_init_mask[l] = full_mask ^ avail_mask

    return {
        "machines": machines,
        "employees": employees,
        "ops_by_group": ops_by_group,
        "group_constrained": group_constrained,
        "group_ids": group_ids,
        "group_max_tg": group_max_tg,
        "group_span": group_span,
        "single_k": single_k,
        "oven_k": oven_k,
        "unlimited_k": unlimited_k,
        "emp_l": emp_l,
        "emp_init_mask": emp_init_mask,
        "wt_first": wt_first,
    }


# ----------------------------------------------------------------------------
# OIDT
# ----------------------------------------------------------------------------
def oidt_union(oven_intervals: dict[int, list[tuple[int, int]]]) -> int:
    """Sum over compartments of (last CT - first ST) - |union of busy intervals|."""
    total = 0
    for ivs in oven_intervals.values():
        if not ivs:
            continue
        ivs = sorted(ivs)
        cur_s, cur_e = ivs[0]
        first_s = cur_s
        busy = 0
        for s_t, e_t in ivs[1:]:
            if s_t <= cur_e:
                if e_t > cur_e:
                    cur_e = e_t
            else:
                busy += cur_e - cur_s
                cur_s, cur_e = s_t, e_t
        busy += cur_e - cur_s
        total += (cur_e - first_s) - busy
    return total


def oidt_m2(oven_intervals: dict[int, list[tuple[int, int]]]) -> int:
    """Paper M2 as written: sum over compartments of (end_k - start_k - sum PT)."""
    total = 0
    for ivs in oven_intervals.values():
        if ivs:
            total += max(e for _, e in ivs) - min(s for s, _ in ivs) - sum(e - s for s, e in ivs)
    return total


OIDT_FUNCS = {"union": oidt_union, "m2": oidt_m2}


def _cobake_ok(st: int, ct: int, same_group_ivs, cobake: str) -> bool:
    """Same-group co-baking check on one compartment (M12 variants)."""
    if cobake == "any":
        return True
    for s2, e2 in same_group_ivs:
        if st < e2 and s2 < ct:  # overlap
            if st != s2 or (cobake == "same_start_end" and ct != e2):
                return False
    return True


def _oven_score(k: int, st: int, ct: int, ivs, rule: str):
    """Lower is better; ties fall back to the lowest index."""
    if rule == "used_first":
        if not ivs:
            return (1, 0)
        gap = min(max(0, s2 - ct, st - e2) for s2, e2 in ivs)
        return (0, gap)
    # min_idle: increase of union idle time on this compartment
    return (oidt_union({k: ivs + [(st, ct)]}) - oidt_union({k: ivs}),)


# ----------------------------------------------------------------------------
# Decoder
# ----------------------------------------------------------------------------
def hnfsm_decode(instance: dict, group_order, return_schedule: bool = False,
                 oven_rule: str = "first_fit", cobake: str = "any", oidt: str = "union"):
    """Decode a group priority order into a schedule.

    Returns (makespan, oidt, sched_df). sched_df is None unless return_schedule.
    If some group cannot be placed: (INFEASIBLE, INFEASIBLE, None).
    """
    machines = instance["machines"]
    employees = instance["employees"]
    ops_by_group = instance["ops_by_group"]
    group_constrained = instance["group_constrained"]
    group_max_tg = instance["group_max_tg"]
    group_span = instance["group_span"]
    oven_k = instance["oven_k"]
    unlimited_k = set(instance.get("unlimited_k", ()))

    mach_mask = {k: 0 for k in instance["single_k"]}
    oven_mask = {k: 0 for k in oven_k}
    emp_mask = dict(instance["emp_init_mask"])

    oven_intervals = {k: [] for k in oven_k}
    schedule_rows = [] if return_schedule else None
    makespan = 0

    for g in group_order:
        c_ops = group_constrained[g]
        placed = False

        for tg in range(group_max_tg[g] + 1):
            ok = True
            chosen_m, chosen_e, chosen_o = [], [], []
            loc_m, loc_e = {}, {}  # within-group occupancy of single machines / employees
            loc_o: dict[int, list] = {}  # within-group oven intervals per compartment

            for op, rel_s, rel_e, base_mask in c_ops:
                m = base_mask << tg
                rt = op["resource_type"]

                if rt == "EMPLOYEE":
                    pl = None
                    for l in op["eligible_l"]:
                        if ((emp_mask[l] | loc_e.get(l, 0)) & m) == 0:
                            pl = l
                            break
                    if pl is None:
                        ok = False
                        break
                    loc_e[pl] = loc_e.get(pl, 0) | m
                    chosen_e.append((op, tg + rel_s, tg + rel_e, pl, m))

                elif rt == "MACHINE":
                    pk = None
                    for k in op["eligible_k"]:
                        if k in unlimited_k:  # M13: no capacity limit
                            pk = k
                            break
                        if ((mach_mask[k] | loc_m.get(k, 0)) & m) == 0:
                            pk = k
                            break
                    if pk is None:
                        ok = False
                        break
                    if pk not in unlimited_k:
                        loc_m[pk] = loc_m.get(pk, 0) | m
                    chosen_m.append((op, tg + rel_s, tg + rel_e, pk, m))

                else:  # OVEN: only other groups' occupancy blocks (M12)
                    st, ct = tg + rel_s, tg + rel_e
                    pk = None
                    if oven_rule == "first_fit":
                        for k in op["eligible_k"]:
                            if (oven_mask[k] & m) == 0 and _cobake_ok(st, ct, loc_o.get(k, ()), cobake):
                                pk = k
                                break
                    else:
                        best = None
                        for k in op["eligible_k"]:
                            if (oven_mask[k] & m) == 0 and _cobake_ok(st, ct, loc_o.get(k, ()), cobake):
                                score = _oven_score(k, st, ct, oven_intervals[k] + loc_o.get(k, []), oven_rule)
                                if best is None or score < best:
                                    best, pk = score, k
                    if pk is None:
                        ok = False
                        break
                    loc_o.setdefault(pk, []).append((st, ct))
                    chosen_o.append((op, st, ct, pk, m))

            if not ok:
                continue

            for op, st, ct, pk, m in chosen_m:
                if pk not in unlimited_k:
                    mach_mask[pk] |= m
            for op, st, ct, pl, m in chosen_e:
                emp_mask[pl] |= m
            for op, st, ct, pk, m in chosen_o:
                oven_mask[pk] |= m
                oven_intervals[pk].append((st, ct))

            makespan = max(makespan, tg + group_span[g])

            if return_schedule:
                assign = {}
                for op, _, _, pk, _ in chosen_m + chosen_o:
                    assign[(op["g"], op["p"], op["s"])] = (pk, None)
                for op, _, _, pl, _ in chosen_e:
                    assign[(op["g"], op["p"], op["s"])] = (None, pl)
                for op, rel_s, rel_e, _ in ops_by_group[g]:
                    pk, pl = assign.get((op["g"], op["p"], op["s"]), (None, None))
                    if pk is not None:
                        label = f"{machines[pk]['machine_name']} (k={pk})"
                    elif pl is not None:
                        label = f"{employees[pl]['employee_name']} (l={pl})"
                    else:
                        label = "NONE"
                    schedule_rows.append({
                        "g": op["g"],
                        "orig_group": op["orig_pr_group"],
                        "batch": op["batch_no"],
                        "p": op["p"],
                        "product_name": op["product_name"],
                        "s": op["s"],
                        "stage_name": op["stage_name"],
                        "ST": tg + rel_s,
                        "CT": tg + rel_e,
                        "PT": op["PT"],
                        "assigned_k": pk,
                        "assigned_l": pl,
                        "assigned_resource": label,
                    })
            placed = True
            break

        if not placed:
            return INFEASIBLE, INFEASIBLE, None

    total_oidt = OIDT_FUNCS[oidt](oven_intervals)
    sched_df = (
        pd.DataFrame(schedule_rows).sort_values(["ST", "g", "p", "s"]).reset_index(drop=True)
        if return_schedule else None
    )
    return makespan, total_oidt, sched_df
