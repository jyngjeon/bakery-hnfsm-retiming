"""Exact single-objective model (min makespan) with OR-Tools CP-SAT.

Ported from the original stage-1 notebook (cell 8). Used as a makespan
reference for BK15. OIDT is only evaluated afterwards, not optimised.

Bug fix vs the notebook: operations on UNLIMITED machines (M13) no longer get a
NoOverlap constraint.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
from ortools.sat.python import cp_model

from bakery.decoder import oidt_union


def solve_min_makespan(json_path: str | Path, horizon: int = 1000, time_limit: float = 30.0,
                       workers: int = 8, seed: int | None = None) -> dict:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    machines = {m["k"]: m for m in data["machines"]}
    employees = {e["l"]: e for e in data["employees"]}
    ops = data["operations"]

    model = cp_model.CpModel()
    ST, CT, O_m, O_e = {}, {}, {}, {}
    machine_intervals = {k: [] for k, m in machines.items() if m["machine_type"] == "SINGLE"}
    employee_intervals = {l: [] for l in employees}
    oven_ops_by_k = {k: [] for k, m in machines.items() if m["machine_type"] == "OVEN"}

    for op in ops:
        g, p, s, pt = op["g"], op["p"], op["s"], op["PT"]
        key = (g, p, s)
        ST[key] = model.NewIntVar(0, horizon, f"ST_{g}_{p}_{s}")
        CT[key] = model.NewIntVar(0, horizon, f"CT_{g}_{p}_{s}")
        model.Add(CT[key] == ST[key] + pt)  # M8

        if op["resource_type"] in ("MACHINE", "OVEN"):  # M10
            assign_vars = []
            for k in op["eligible_k"]:
                v = model.NewBoolVar(f"Om_{g}_{p}_{s}_{k}")
                O_m[g, p, s, k] = v
                assign_vars.append(v)
                mtype = machines[k]["machine_type"]
                if mtype == "SINGLE":
                    iv = model.NewOptionalFixedSizeIntervalVar(ST[key], pt, v, f"iv_m_{g}_{p}_{s}_{k}")
                    machine_intervals[k].append(iv)
                elif mtype == "OVEN":
                    oven_ops_by_k[k].append((op, v))
                # UNLIMITED (M13): no capacity constraint
            model.Add(sum(assign_vars) == 1)

        elif op["resource_type"] == "EMPLOYEE":  # M15, M17, M18
            assign_vars = []
            for l in op["eligible_l"]:
                v = model.NewBoolVar(f"Oe_{g}_{p}_{s}_{l}")
                O_e[g, p, s, l] = v
                assign_vars.append(v)
                iv = model.NewOptionalFixedSizeIntervalVar(ST[key], pt, v, f"iv_e_{g}_{p}_{s}_{l}")
                employee_intervals[l].append(iv)
                model.Add(ST[key] >= employees[l]["start_l"]).OnlyEnforceIf(v)
                model.Add(CT[key] <= employees[l]["end_l"]).OnlyEnforceIf(v)
            model.Add(sum(assign_vars) == 1)

    for op in ops:  # M6 bowl time, M9 no-wait
        g, p, s, wt = op["g"], op["p"], op["s"], op["WT"]
        if s == 1 and p > 1:
            model.Add(ST[g, p, 1] == ST[g, 1, 1] + wt)
        if s > 1:
            model.Add(ST[g, p, s] == CT[g, p, s - 1])

    for ivs in machine_intervals.values():  # M11
        if ivs:
            model.AddNoOverlap(ivs)
    for ivs in employee_intervals.values():  # M16
        if ivs:
            model.AddNoOverlap(ivs)

    for k, op_list in oven_ops_by_k.items():  # M12: same group may share, different groups may not
        n = len(op_list)
        for i in range(n):
            op_i, v_i = op_list[i]
            key_i = (op_i["g"], op_i["p"], op_i["s"])
            for j in range(i + 1, n):
                op_j, v_j = op_list[j]
                if op_i["g"] == op_j["g"]:
                    continue
                key_j = (op_j["g"], op_j["p"], op_j["s"])
                b_ij = model.NewBoolVar(f"oven_{k}_{key_i}_before_{key_j}")
                model.Add(CT[key_i] <= ST[key_j]).OnlyEnforceIf([v_i, v_j, b_ij])
                model.Add(CT[key_j] <= ST[key_i]).OnlyEnforceIf([v_i, v_j, b_ij.Not()])

    makespan = model.NewIntVar(0, horizon, "makespan")  # M1, M3
    model.AddMaxEquality(makespan, list(CT.values()))
    model.Minimize(makespan)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = workers
    if seed is not None:
        solver.parameters.random_seed = seed

    t0 = time.time()
    status = solver.Solve(model)
    elapsed = time.time() - t0
    status_name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": status_name, "elapsed_s": elapsed}

    rows = []
    oven_intervals = {k: [] for k in oven_ops_by_k}
    for op in ops:
        g, p, s = op["g"], op["p"], op["s"]
        key = (g, p, s)
        st_val, ct_val = solver.Value(ST[key]), solver.Value(CT[key])
        ak = al = None
        if op["resource_type"] in ("MACHINE", "OVEN"):
            ak = next(k for k in op["eligible_k"] if solver.Value(O_m[g, p, s, k]) == 1)
            if op["resource_type"] == "OVEN":
                oven_intervals[ak].append((st_val, ct_val))
        elif op["resource_type"] == "EMPLOYEE":
            al = next(l for l in op["eligible_l"] if solver.Value(O_e[g, p, s, l]) == 1)
        rows.append({
            "g": g, "orig_group": op["orig_pr_group"], "batch": op["batch_no"], "p": p,
            "product_name": op["product_name"], "s": s, "stage_name": op["stage_name"],
            "ST": st_val, "CT": ct_val, "PT": op["PT"], "assigned_k": ak, "assigned_l": al,
        })
    sched_df = pd.DataFrame(rows).sort_values(["ST", "g", "p", "s"]).reset_index(drop=True)

    return {
        "status": status_name,
        "elapsed_s": elapsed,
        "makespan": int(solver.Value(makespan)),
        "oidt_union": oidt_union(oven_intervals),
        "schedule": sched_df,
    }
