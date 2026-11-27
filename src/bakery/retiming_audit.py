"""Validation-only oracle and strict adapter for the supplied BK15 pilot.

No imports from bakery.retiming: enumerate integer starts, inspect actual
shifted intervals, and recompute oven busy minutes with sets. This intentionally
slower implementation shares neither feasible windows nor event candidates nor
incremental objective calculations with the production search.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import gzip
import json
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class ExhaustiveGroup:
    g: int
    feasible_times: tuple[int, ...]
    best: tuple[int, int, int]
    time_checks: int


class ExhaustiveOracle:
    """Direct exhaustive audit of an independently validated baseline schedule."""

    def __init__(self, instance: dict, schedule: pd.DataFrame):
        self.machines = instance["machines"]
        self.employees = instance["employees"]
        self.metadata = {(o["g"], o["p"], o["s"]): o
                         for entries in instance["ops_by_group"].values() for o, *_ in entries}
        self.rows = []
        self.groups = defaultdict(list)
        self.resources = defaultdict(list)
        self.starts = {}
        for raw in schedule.to_dict("records"):
            key = tuple(int(raw[c]) for c in ("g", "p", "s"))
            k = None if pd.isna(raw["assigned_k"]) else int(raw["assigned_k"])
            l = None if pd.isna(raw["assigned_l"]) else int(raw["assigned_l"])
            row = {"key": key, "g": key[0], "st": int(raw["ST"]), "ct": int(raw["CT"]),
                   "k": k, "l": l, "resource": ("l", l) if l is not None else
                   (("k", k) if k is not None else None)}
            self.rows.append(row)
            self.groups[key[0]].append(row)
            if row["resource"] is not None:
                self.resources[row["resource"]].append(row)
            if key[1:] == (1, 1):
                self.starts[key[0]] = row["st"] - self.metadata[key]["WT"]
        self.group_ids = tuple(sorted(self.groups))
        if set(self.starts) != set(self.groups):
            raise ValueError("oracle requires a baseline operation (g,1,1) for each group")
        self.makespan, self.oidt = self.objectives(None, 0)

    def _finite(self, resource):
        return resource is not None and (resource[0] == "l" or
               self.machines[resource[1]]["machine_type"] != "UNLIMITED")

    def feasible(self, g: int, t: int, *, preserve_order: bool = False) -> bool:
        if t < 0:
            return False
        delta = t - self.starts[g]
        for row in self.groups[g]:
            st, ct = row["st"] + delta, row["ct"] + delta
            if st < 0 or ct > self.makespan:
                return False
            if row["l"] is not None:
                employee = self.employees[row["l"]]
                if st < employee["start_l"] or ct > employee["end_l"]:
                    return False
            resource = row["resource"]
            if not self._finite(resource):
                continue
            # Same-group relations are unchanged by a common translation.
            # Every potentially changed cross-group conflict is inspected.
            for other in self.resources[resource]:
                if other["g"] == g:
                    continue
                if max(st, other["st"]) < min(ct, other["ct"]):
                    return False
                if preserve_order:
                    if row["ct"] <= other["st"] and ct > other["st"]:
                        return False
                    if other["ct"] <= row["st"] and st < other["ct"]:
                        return False
        return True

    def objectives(self, g: int | None, t: int) -> tuple[int, int]:
        delta = 0 if g is None else t - self.starts[g]
        occupied = defaultdict(set)
        makespan = 0
        for row in self.rows:
            d = delta if row["g"] == g else 0
            st, ct = row["st"] + d, row["ct"] + d
            makespan = max(makespan, ct)
            if row["k"] is not None and self.machines[row["k"]]["machine_type"] == "OVEN":
                occupied[row["k"]].update(range(st, ct))
        oidt = sum(max(minutes) - min(minutes) + 1 - len(minutes)
                   for minutes in occupied.values() if minutes)
        return makespan, oidt

    def scan_group(self, g: int, *, preserve_order: bool = False) -> ExhaustiveGroup:
        feasible_times, values = [], []
        # Deliberately no offset-derived upper bound or interval subtraction.
        for t in range(self.makespan + 1):
            if self.feasible(g, t, preserve_order=preserve_order):
                feasible_times.append(t)
                ms, oi = self.objectives(g, t)
                values.append((ms, oi, t))
        if not values:
            raise ValueError("oracle baseline not feasible")
        return ExhaustiveGroup(g, tuple(feasible_times),
                               min(values, key=lambda v: (v[1], v[0], v[2])), self.makespan + 1)

    def boundary_groups(self) -> tuple[int, ...]:
        groups = set()
        for (kind, index), rows in self.resources.items():
            if kind != "k" or self.machines[index]["machine_type"] != "OVEN":
                continue
            first = min(row["st"] for row in rows)
            last = max(row["ct"] for row in rows)
            groups.update(row["g"] for row in rows if row["st"] == first or row["ct"] == last)
        return tuple(sorted(groups))


def legacy_compatibility(pilot_root: Path, instance: dict) -> dict:
    """Derive mappings from metadata and reject semantic differences; no guesses."""
    parsed = json.loads((pilot_root / "frozen/hnfsm_stage1/bakery_BK15_parsed.json").read_text(encoding="utf-8"))
    machines = instance["machines"]
    machine_map = {str(m["orig_machine_id"]): k for k, m in machines.items()}
    if set(machine_map) != {str(m["id"]) for m in parsed["machines"]}:
        raise ValueError("legacy machine IDs differ")
    for m in parsed["machines"]:
        current = machines[machine_map[str(m["id"])]]
        if (m["name"], m["category"]) != (current["machine_name"], current["machine_category"]):
            raise ValueError(f"legacy machine metadata differs: {m}")
    employee_map = {e["employee_name"]: l for l, e in instance["employees"].items()}
    if set(employee_map) != {e["id"] for e in parsed["employees"]}:
        raise ValueError("legacy employees differ")
    for e in parsed["employees"]:
        current = instance["employees"][employee_map[e["id"]]]
        if (e["start"], e["end"]) != (current["start_l"], current["end_l"]):
            raise ValueError("legacy employee shifts differ")
    group_map, current_ops = {}, {}
    for g, entries in instance["ops_by_group"].items():
        for op, a, b, _ in entries:
            old_key = f"{op['orig_pr_group']}.{op['batch_no']}"
            if old_key in group_map and group_map[old_key] != g:
                raise ValueError("ambiguous legacy group mapping")
            group_map[old_key] = g
            identity = (old_key, op["p"], op["s"] - 1)
            if identity in current_ops:
                raise ValueError("ambiguous operation mapping")
            current_ops[identity] = (op, a, b)
    expected, source_rows = set(), {}
    for group, data in parsed["groups"].items():
        for batch in range(1, data["batch_count"] + 1):
            key = f"{group}.{batch}"
            for product in data["products"]:
                offset = product["wt"]
                for index, old in enumerate(product["ops"]):
                    identity = (key, product["id"], index)
                    expected.add(identity)
                    if identity not in current_ops:
                        raise ValueError(f"missing mapped operation: {identity}")
                    op, a, b = current_ops[identity]
                    category = None if op["resource_type"] == "NONE" else op["resource_category"]
                    if (old["pt"], offset, offset + old["pt"], old["type"], old["stage"].casefold()) != (
                            op["PT"], a, b, category, op["stage_name"].casefold()):
                        raise ValueError(f"legacy PT/WT/resource/stage differs: {identity}")
                    eligible = (sorted(employee_map) if old["type"] == "Manual" else
                                sorted(str(m["id"]) for m in parsed["machines"]
                                       if m["category"] == old["type"]))
                    mapped = sorted(employee_map[e] for e in eligible) if old["type"] == "Manual" else sorted(machine_map[k] for k in eligible)
                    if mapped != sorted(op["eligible_l"] if old["type"] == "Manual" else op["eligible_k"]):
                        raise ValueError(f"legacy eligibility differs: {identity}")
                    source_rows[identity] = old["source_row"]
                    offset += old["pt"]
    if expected != set(current_ops):
        raise ValueError("legacy/current operation coverage differs")
    return {"group_map": group_map, "machine_map": machine_map, "employee_map": employee_map,
            "operations_compared": len(expected), "current_ops": current_ops, "source_rows": source_rows}


def legacy_to_frame(schedule: dict, compatibility: dict) -> pd.DataFrame:
    if not schedule.get("ok") or schedule.get("policy") != "shared_batch":
        raise ValueError("expected a complete shared_batch pilot schedule")
    records = []
    for old in schedule["operations"]:
        identity = (old["key"], old["product"], old["index"])
        op, a, _ = compatibility["current_ops"][identity]
        if old["key"] != f"{old['group']}.{old['batch']}" or old["pt"] != op["PT"]:
            raise ValueError("legacy operation identity/duration differs")
        if old["row"] != compatibility["source_rows"][identity]:
            raise ValueError("legacy source row differs")
        if old["start"] - a != schedule["group_starts"][old["key"]]:
            raise ValueError("legacy relative time differs")
        resource = old["resource"]
        l = compatibility["employee_map"].get(resource)
        k = None if resource is None or l is not None else compatibility["machine_map"][resource]
        records.append({"g": op["g"], "orig_group": op["orig_pr_group"], "batch": op["batch_no"],
                        "p": op["p"], "product_name": op["product_name"], "s": op["s"],
                        "stage_name": op["stage_name"], "ST": old["start"], "CT": old["end"],
                        "PT": op["PT"], "assigned_k": k, "assigned_l": l,
                        "assigned_resource": "NONE" if resource is None else resource})
    return pd.DataFrame(records)


def load_legacy_schedules(pilot_root: Path) -> list[tuple[str, int, dict]]:
    rows = []
    for path in sorted(pilot_root.glob("*_pareto_schedules.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            rows.extend((path.stem, i, row) for i, row in enumerate(json.load(stream)))
    if not rows:
        raise FileNotFoundError(f"no pilot schedules in {pilot_root}")
    return rows
