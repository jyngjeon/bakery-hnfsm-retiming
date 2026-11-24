"""Preprocessing of the Mendeley BK15 / BK50 raw Excel files into cleaned solver
input (JSON) and a human-readable Excel copy.

Ported from the original stage-1 notebook (cells 4 and 6) without changing the
logic. Every data fix is documented in docs/PROGRESS.md and in the teammate notes
under docs/notes/.

Output schema (operations):
    g, p, s, PT, WT, resource_type, eligible_k, eligible_l,
    orig_pr_group, batch_no, product_name, stage_name, resource_category
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from bakery.paths import RAW_FILES, processed_json, processed_xlsx

OPS_COLUMNS = [
    "g", "p", "s", "PT", "WT",
    "resource_type", "eligible_k", "eligible_l",
    "orig_pr_group", "batch_no", "product_name", "stage_name", "resource_category",
]

RAW_OPS_COLUMNS = [
    "pr_group", "product_id", "bowl_time_WT", "product_name",
    "batches", "stage_name", "duration_PT", "machines_ employees_ME",
]
OPS_RENAMED = [
    "orig_pr_group", "p", "WT", "product_name",
    "batches", "stage_name", "PT", "resource_category",
]


# ----------------------------------------------------------------------------
# Shared steps
# ----------------------------------------------------------------------------
def _read_raw(name: str) -> pd.DataFrame:
    raw = pd.read_excel(RAW_FILES[name], sheet_name=name)
    raw = raw.dropna(axis=1, how="all").dropna(axis=0, how="all")
    raw.columns = [c.strip() for c in raw.columns]
    return raw


def _machines_table(raw: pd.DataFrame) -> pd.DataFrame:
    """Physical machines only; the 'Manual' dummy row is dropped. k = 1..K."""
    machines = raw[["machine_id", "machine_name", "machine_category"]].dropna(how="all").copy()
    machines = machines.rename(columns={"machine_id": "orig_machine_id"})
    machines["machine_name"] = machines["machine_name"].astype(str).str.strip()
    machines["machine_category"] = machines["machine_category"].astype(str).str.strip()
    machines = machines[machines["machine_category"].str.lower() != "manual"].reset_index(drop=True)
    machines["orig_machine_id"] = machines["orig_machine_id"].astype(int)
    machines.insert(0, "k", range(1, len(machines) + 1))
    return machines


def _employees_table(raw: pd.DataFrame) -> pd.DataFrame:
    """Employees with shift [start_l, end_l]. l = 1..L."""
    employees = raw[["employee_id", "shift_start", "shift_end"]].dropna(how="all").copy()
    employees = employees.rename(columns={
        "employee_id": "employee_name",
        "shift_start": "start_l",
        "shift_end": "end_l",
    }).reset_index(drop=True)
    employees["employee_name"] = employees["employee_name"].astype(str).str.strip()
    employees["start_l"] = employees["start_l"].astype(int)
    employees["end_l"] = employees["end_l"].astype(int)
    employees.insert(0, "l", range(1, len(employees) + 1))
    return employees


def _raw_ops(raw: pd.DataFrame) -> pd.DataFrame:
    ops = raw[RAW_OPS_COLUMNS].copy()
    ops.columns = OPS_RENAMED
    for col in ["orig_pr_group", "p", "WT", "batches", "PT"]:
        ops[col] = ops[col].astype(int)
    ops["product_name"] = ops["product_name"].astype(str).str.strip()
    ops["stage_name"] = ops["stage_name"].astype(str).str.strip()
    return ops


def _expand_batches(ops: pd.DataFrame, batch_count) -> pd.DataFrame:
    """Batch b >= 2 of an original group becomes a new independent group appended
    after the existing numbers (batch 1 keeps its original group number).
    `batch_count(group_df) -> int` decides how many batches a group has."""
    ops = ops.copy()
    ops["g"] = ops["orig_pr_group"]
    ops["batch_no"] = 1
    extra = []
    next_g = ops["g"].max() + 1
    for _, grp in ops.groupby("orig_pr_group", sort=True):
        for b_no in range(2, batch_count(grp) + 1):
            dup = grp.copy()
            dup["g"] = next_g
            dup["batch_no"] = b_no
            extra.append(dup)
            next_g += 1
    if extra:
        ops = pd.concat([ops] + extra, ignore_index=True)
    return ops


def _resource_type(cat: str, oven_cats: set[str]) -> str:
    if cat == "NONE":
        return "NONE"       # no resource (M13, M19)
    if cat == "Manual":
        return "EMPLOYEE"   # employee (M15-M18)
    if cat in oven_cats:
        return "OVEN"       # oven compartment (M2, M12)
    return "MACHINE"        # machine category (M11; UNLIMITED handled by machine_type)


def _finalize_ops(ops: pd.DataFrame, machines: pd.DataFrame, employees: pd.DataFrame,
                  oven_cats: set[str]) -> pd.DataFrame:
    ops = ops.copy()
    ops["s"] = ops.groupby(["g", "p"], sort=False).cumcount() + 1
    ops["resource_type"] = ops["resource_category"].apply(lambda c: _resource_type(c, oven_cats))
    cat_to_k = machines.groupby("machine_category")["k"].apply(list).to_dict()
    all_l = employees["l"].tolist()
    ops["eligible_k"] = ops.apply(
        lambda r: cat_to_k.get(r["resource_category"], []) if r["resource_type"] in ("MACHINE", "OVEN") else [],
        axis=1,
    )
    ops["eligible_l"] = ops["resource_type"].apply(lambda t: list(all_l) if t == "EMPLOYEE" else [])
    return ops[OPS_COLUMNS]


def _validate(machines: pd.DataFrame, employees: pd.DataFrame, ops: pd.DataFrame) -> None:
    assert machines.isna().sum().sum() == 0
    assert employees.isna().sum().sum() == 0
    assert ops.isna().sum().sum() == 0
    assert (ops["PT"] > 0).all()                                   # M7
    assert (employees["start_l"] < employees["end_l"]).all()       # M14
    assert (ops["resource_type"].isin(["MACHINE", "OVEN"]) == ops["eligible_k"].apply(len).gt(0)).all()
    assert (ops["resource_type"].eq("EMPLOYEE") == ops["eligible_l"].apply(len).gt(0)).all()
    assert (ops.loc[ops["s"] >= 2, "WT"] == 0).all()               # WT only at s = 1 (M6)


# ----------------------------------------------------------------------------
# Instance-specific pipelines
# ----------------------------------------------------------------------------
BK15_OVEN_CATS = {"Stone oven", "Baking chamber"}
BK15_UNLIMITED_CATS = {"Proving chamber"}


def preprocess_bk15() -> dict[str, pd.DataFrame]:
    raw = _read_raw("BK15")
    machines = _machines_table(raw)

    def machine_type(cat):
        if cat in BK15_OVEN_CATS:
            return "OVEN"
        if cat in BK15_UNLIMITED_CATS:
            return "UNLIMITED"
        return "SINGLE"

    machines["machine_type"] = machines["machine_category"].apply(machine_type)
    employees = _employees_table(raw)

    ops = _raw_ops(raw)
    # (1) Unify product name: Group 1, p=1 'Product 1' (1 row) -> 'Product 1A'
    ops.loc[(ops["orig_pr_group"] == 1) & (ops["p"] == 1), "product_name"] = "Product 1A"
    # (2) Stage-name case
    ops["stage_name"] = ops["stage_name"].replace({"Load Baking": "Load baking", "packaging": "Packaging"})
    # (3) Blank resource -> NONE; typo and category-name fixes
    ops["resource_category"] = (
        ops["resource_category"].fillna("NONE").astype(str).str.strip()
        .replace({"Mnaual": "Manual", "Cutting Machine": "Cutter"})
    )
    # Batch expansion: Group 6 (batches = 2) -> new group g = 16
    ops = _expand_batches(ops, lambda grp: int(grp["batches"].iloc[0]))
    ops = _finalize_ops(ops, machines, employees, BK15_OVEN_CATS)
    _validate(machines, employees, ops)
    return {"machines": machines, "employees": employees, "operations": ops}


BK50_OVEN_CATS = {"Oven A", "Oven B", "Oven C"}


def preprocess_bk50() -> dict[str, pd.DataFrame]:
    raw = _read_raw("BK50")
    # Original machine_id 20 (Oven 7) is missing in the public file -> 9 oven compartments.
    machines = _machines_table(raw)
    machines["machine_type"] = machines["machine_category"].apply(
        lambda c: "OVEN" if c in BK50_OVEN_CATS else "SINGLE"
    )
    employees = _employees_table(raw)

    ops = _raw_ops(raw)
    # (1) Group 31, p=2 holds two 5-stage runs (WT=15 and WT=30). Split the second
    #     run (from the WT=30 row) into a derived product p=3 'Sourdough Bread-2'.
    g31_p2 = ops[(ops["orig_pr_group"] == 31) & (ops["p"] == 2)]
    split_start = g31_p2[g31_p2["WT"] == 30].index[0]
    second_run_idx = g31_p2.loc[split_start:].index
    ops.loc[second_run_idx, "p"] = 3
    ops.loc[second_run_idx, "product_name"] = "Sourdough Bread-2"
    # (2) Unify mixed product names within one product
    ops.loc[(ops["orig_pr_group"] == 5) & (ops["p"] == 1), "product_name"] = "Butter roll"
    ops.loc[(ops["orig_pr_group"] == 22) & (ops["p"] == 1), "product_name"] = "Small-round bread p-i"
    # (3) Stage-name case and typos
    ops["stage_name"] = ops["stage_name"].replace({
        "Load Baking": "Load baking",
        "Discharge Baking": "Discharge baking",
        "Discharge Kneading": "Discharge kneading",
        "DIviding": "Dividing",
        "Dough Rest": "Dough rest",
        "DoughRest": "Dough rest",
        "Doug rest": "Dough rest",
        "preparation": "Preparation",
        "Discharge refrigeretor": "Discharge refrigerator",
        "Moulding": "Molding",
    })
    # (4) Blank resource -> NONE
    ops["resource_category"] = (
        ops["resource_category"].fillna("NONE").astype(str).str.strip()
        .replace({"": "NONE", "nan": "NONE", "None": "NONE"})
    )
    # (5) WT at s >= 2 normalised to 0 (G5 p=2 drag-fill 34, G22 p=1 cumulative 206)
    stage_pos = ops.groupby(["orig_pr_group", "p"], sort=False).cumcount() + 1
    ops.loc[stage_pos >= 2, "WT"] = 0
    # Batch expansion: 17 groups -> g = 41..62. Group 18 has mixed batches
    # (p=1: 1, p=2..4: 2); the group max is used.
    ops = _expand_batches(ops, lambda grp: int(grp["batches"].max()))
    ops = _finalize_ops(ops, machines, employees, BK50_OVEN_CATS)
    _validate(machines, employees, ops)
    assert (ops.loc[(ops["p"] == 1) & (ops["s"] == 1), "WT"] == 0).all()
    return {"machines": machines, "employees": employees, "operations": ops}


PIPELINES = {"BK15": preprocess_bk15, "BK50": preprocess_bk50}


def save(name: str, tables: dict[str, pd.DataFrame], json_path: Path | None = None,
         xlsx_path: Path | None = None) -> tuple[Path, Path]:
    json_path = json_path or processed_json(name)
    xlsx_path = xlsx_path or processed_xlsx(name)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    solver_data = {key: df.to_dict(orient="records") for key, df in tables.items()}
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(solver_data, f, ensure_ascii=False, indent=2)

    ops_excel = tables["operations"].copy()
    for col in ("eligible_k", "eligible_l"):
        ops_excel[col] = ops_excel[col].apply(lambda x: ",".join(map(str, x)))
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        tables["machines"].to_excel(writer, sheet_name="machines", index=False)
        tables["employees"].to_excel(writer, sheet_name="employees", index=False)
        ops_excel.to_excel(writer, sheet_name="operations", index=False)
    return json_path, xlsx_path
