"""One-group Event-Point Retiming with fixed assignments and integer minutes.

Adapted from the supplied event_interval.py / boundary_abl.py. For a mobile
interval [T+a,T+b) and a fixed interval [u,v), forbidden integers are
[u-b+1,v-a-1]. Feasible windows contain their endpoints and every OIDT knot.
This solves only the fixed-assignment, fixed-other-groups subproblem.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
from pathlib import Path
from time import perf_counter

import pandas as pd

from bakery.checker import verify_schedule
from bakery.decoder import oidt_union


def _integer(value, label: str) -> int:
    if isinstance(value, (str, bool)) or pd.isna(value):
        raise ValueError(f"{label} must be a finite integer: {value!r}")
    try:
        integer = int(value)
        valid = math.isfinite(value) and integer == value
    except (TypeError, ValueError, OverflowError):
        valid = False
    if not valid:
        raise ValueError(f"{label} must be a finite integer: {value!r}")
    return integer


def _optional_integer(value, label: str) -> int | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, str) and value.strip().upper() in ("", "NONE", "NAN"):
        return None
    return _integer(value, label)


@dataclass(frozen=True)
class _Operation:
    key: tuple[int, int, int]
    st: int
    ct: int
    a: int
    b: int
    resource: tuple[str, int] | None

    @property
    def g(self) -> int:
        return self.key[0]


@dataclass(frozen=True)
class GroupSearch:
    g: int
    intervals: tuple[tuple[int, int], ...]
    candidates: tuple[int, ...]
    # (makespan, OIDT, T_g), including the optimum when no move is accepted.
    best: tuple[int, int, int]


@dataclass(frozen=True)
class SearchResult:
    # (OIDT, makespan, g, T_g); None means no strict Pareto improvement.
    move: tuple[int, int, int, int] | None
    groups: tuple[GroupSearch, ...]
    seconds: float

    @property
    def candidate_count(self) -> int:
        return sum(len(group.candidates) for group in self.groups)


@dataclass
class RetimingResult:
    schedule: pd.DataFrame
    makespan: int
    oidt: int
    moved: bool
    moved_group: int | None
    old_tg: int | None
    new_tg: int | None
    delta: int
    checker: dict
    invariants: dict
    search: SearchResult
    timings: dict[str, float]


def verify_retiming_invariants(before: pd.DataFrame, after: pd.DataFrame,
                               moved_group: int | None, delta: int) -> dict:
    """Compare full rows by (g,p,s); every non-time field must be unchanged.

    Unlike the feasibility checker, this checks the relation to the baseline.
    Row ordering is immaterial. A no-move result must retain all original times.
    """
    errors = []
    try:
        delta = _integer(delta, "delta")
        if moved_group is None and delta != 0:
            raise ValueError("nonzero delta without a moved group")
        for frame in (before, after):
            if frame.duplicated(["g", "p", "s"]).any():
                raise ValueError("duplicate operation keys")
        expected = before.copy(deep=True)
        if moved_group is not None:
            selected = expected["g"] == moved_group
            if not selected.any():
                raise ValueError("unknown moved group")
            expected.loc[selected, ["ST", "CT"]] += delta
        expected = expected.sort_values(["g", "p", "s"]).reset_index(drop=True)
        actual = after.sort_values(["g", "p", "s"]).reset_index(drop=True)
        pd.testing.assert_frame_equal(expected, actual, check_like=True)
    except (AssertionError, KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    return {"is_valid": not errors, "total_violations": len(errors), "violations": errors}


class RetimingContext:
    """Validated snapshot, reusable for all/boundary and order ablations.

    The JSON is required so the existing independent checker remains the final
    authority. Invalid/incomplete input raises ValueError; an internal mismatch
    in an accepted result raises RuntimeError instead of hiding a failed audit.
    """

    def __init__(self, instance: dict, schedule_df: pd.DataFrame, json_path: str | Path):
        started = perf_counter()
        required = {"g", "p", "s", "ST", "CT", "assigned_k", "assigned_l"}
        if not isinstance(schedule_df, pd.DataFrame) or schedule_df.empty:
            raise ValueError("schedule_df must be a nonempty DataFrame")
        if schedule_df.columns.duplicated().any() or not required <= set(schedule_df):
            raise ValueError("missing or duplicate schedule columns")
        if not isinstance(instance, dict) or not {"machines", "employees", "ops_by_group", "group_ids"} <= instance.keys():
            raise ValueError("incomplete HNFSM instance")
        self._schedule = schedule_df.copy(deep=True)
        self._json_path = Path(json_path)
        self._machines = instance["machines"]
        self._employees = instance["employees"]
        metadata = {}
        for g, entries in instance["ops_by_group"].items():
            for op, a, b, _ in entries:
                key = (op["g"], op["p"], op["s"])
                if key in metadata or key[0] != g or a < 0 or b - a != op["PT"] or b <= a:
                    raise ValueError("invalid instance operation offsets/keys")
                metadata[key] = (op, a, b)
        seen = set()
        self._groups = defaultdict(list)
        self._resources = defaultdict(list)
        starts = defaultdict(set)
        for row in self._schedule.to_dict("records"):
            key = tuple(_integer(row[c], c) for c in ("g", "p", "s"))
            if key in seen or key not in metadata:
                raise ValueError(f"duplicate or undefined operation: {key}")
            seen.add(key)
            op, a, b = metadata[key]
            st, ct = (_integer(row[c], c) for c in ("ST", "CT"))
            if st < 0 or ct - st != op["PT"]:
                raise ValueError(f"invalid duration or negative time: {key}")
            if "PT" in row and _integer(row["PT"], "PT") != op["PT"]:
                raise ValueError(f"schedule PT differs from instance: {key}")
            k = _optional_integer(row["assigned_k"], "assigned_k")
            l = _optional_integer(row["assigned_l"], "assigned_l")
            rt = op["resource_type"]
            resource = None
            if rt == "EMPLOYEE":
                if k is not None or l not in op["eligible_l"] or l not in self._employees:
                    raise ValueError(f"invalid employee assignment: {key}")
                resource = ("l", l)
            elif rt in ("MACHINE", "OVEN"):
                if l is not None or k not in op["eligible_k"] or k not in self._machines:
                    raise ValueError(f"invalid machine assignment: {key}")
                machine_type = self._machines[k]["machine_type"]
                allowed = ("OVEN",) if rt == "OVEN" else ("SINGLE", "UNLIMITED")
                if machine_type not in allowed:
                    raise ValueError(f"inconsistent resource type: {key}")
                if machine_type != "UNLIMITED":
                    resource = ("k", k)
            elif rt != "NONE" or k is not None or l is not None:
                raise ValueError(f"invalid resource type/assignment: {key}")
            rec = _Operation(key, st, ct, a, b, resource)
            self._groups[key[0]].append(rec)
            starts[key[0]].add(st - a)
            if resource is not None:
                self._resources[resource].append(rec)
        if seen != set(metadata) or set(self._groups) != set(instance["group_ids"]):
            raise ValueError("incomplete operation/group coverage")
        if any(len(times) != 1 or min(times) < 0 for times in starts.values()):
            raise ValueError("group WT/no-wait offsets are inconsistent")
        self.group_ids = tuple(sorted(self._groups))
        self.group_starts = {g: next(iter(starts[g])) for g in self.group_ids}
        self._spans = {g: max(o.b for o in ops) for g, ops in self._groups.items()}
        self._ends = {g: max(o.ct for o in ops) for g, ops in self._groups.items()}
        self.makespan = max(self._ends.values())
        self._ovens = {k: self._resources[("k", k)] for k, m in self._machines.items()
                       if m["machine_type"] == "OVEN"}
        self.oidt = oidt_union({k: [(o.st, o.ct) for o in ops] for k, ops in self._ovens.items()})
        check_started = perf_counter()
        self.baseline_checker = verify_schedule(self._json_path, self._schedule,
                                                self.makespan, self.oidt)
        self.baseline_checker_seconds = perf_counter() - check_started
        if not self.baseline_checker["is_valid"]:
            raise ValueError(f"invalid baseline schedule: {self.baseline_checker['violations_by_rule']}")
        # Candidate evaluation changes only the exterior spans of affected ovens.
        # Busy-union length stays constant on the feasible set.
        self._profiles = {}
        for g in self.group_ids:
            profiles = []
            for ops in self._ovens.values():
                mobile = [o for o in ops if o.g == g]
                fixed = [o for o in ops if o.g != g]
                if mobile and fixed:
                    profiles.append((min(o.a for o in mobile), max(o.b for o in mobile),
                                     min(o.st for o in fixed), max(o.ct for o in fixed),
                                     max(o.ct for o in ops) - min(o.st for o in ops)))
            self._profiles[g] = tuple(profiles)
        self.setup_seconds = perf_counter() - started

    def boundary_groups(self) -> tuple[int, ...]:
        """Include every group tied at an oven's first start or last end."""
        selected = set()
        for ops in self._ovens.values():
            if ops:
                first, last = min(o.st for o in ops), max(o.ct for o in ops)
                selected.update(o.g for o in ops if o.st == first or o.ct == last)
        return tuple(sorted(selected))

    def feasible_intervals(self, g: int, *, preserve_order: bool = False) -> tuple[tuple[int, int], ...]:
        """Disjoint closed integer windows; touching processing intervals are legal.

        preserve_order retains each original cross-group precedence on finite
        resources, including ovens and employees. UNLIMITED has no such order.
        """
        if g not in self._groups:
            raise ValueError(f"unknown group: {g}")
        lo, hi = 0, self.makespan - self._spans[g]
        forbidden = []
        for op in self._groups[g]:
            if op.resource is None:
                continue
            kind, index = op.resource
            if kind == "l":
                employee = self._employees[index]
                lo = max(lo, employee["start_l"] - op.a)
                hi = min(hi, employee["end_l"] - op.b)
            for other in self._resources[op.resource]:
                if other.g == g:
                    continue
                if preserve_order:
                    if op.ct <= other.st:
                        hi = min(hi, other.st - op.b)
                    elif other.ct <= op.st:
                        lo = max(lo, other.ct - op.a)
                    else:
                        raise RuntimeError("baseline has a cross-group resource conflict")
                low, high = other.st - op.b + 1, other.ct - op.a - 1
                if low <= high:
                    forbidden.append((low, high))
        if lo > hi:
            return ()
        blocked = sorted((max(a, lo), min(b, hi)) for a, b in forbidden if a <= hi and b >= lo)
        windows, start = [], lo
        for a, b in blocked:
            if a > start:
                windows.append((start, a - 1))
            start = max(start, b + 1)
            if start > hi:
                break
        if start <= hi:
            windows.append((start, hi))
        return tuple(windows)

    def group_search(self, g: int, *, preserve_order: bool = False) -> GroupSearch:
        intervals = self.feasible_intervals(g, preserve_order=preserve_order)
        knots = {t for a, b, first, last, _ in self._profiles[g] for t in (first - a, last - b)}
        candidates = tuple(sorted({t for lo, hi in intervals
                                   for t in (lo, hi, *(k for k in knots if lo <= k <= hi))}))
        fixed_end = max((end for other, end in self._ends.items() if other != g), default=0)
        values = []
        for t in candidates:
            ms = max(fixed_end, t + self._spans[g])
            oi = self.oidt + sum(max(last, t + b) - min(first, t + a) - old_span
                                 for a, b, first, last, old_span in self._profiles[g])
            values.append((ms, oi, t))
        if not values:
            raise RuntimeError("validated baseline disappeared from the feasible set")
        best = min(values, key=lambda v: (v[1], v[0], v[2]))
        return GroupSearch(g, intervals, candidates, best)

    def search(self, *, boundary_only: bool = True, preserve_order: bool = False) -> SearchResult:
        started = perf_counter()
        groups = tuple(self.group_search(g, preserve_order=preserve_order)
                       for g in (self.boundary_groups() if boundary_only else self.group_ids))
        moves = [(r.best[1], r.best[0], r.g, r.best[2]) for r in groups
                 if r.best[0] <= self.makespan and r.best[1] <= self.oidt
                 and (r.best[0] < self.makespan or r.best[1] < self.oidt)]
        return SearchResult(min(moves, default=None), groups, perf_counter() - started)

    def retime(self, *, boundary_only: bool = True, preserve_order: bool = False) -> RetimingResult:
        started = perf_counter()
        search = self.search(boundary_only=boundary_only, preserve_order=preserve_order)
        schedule = self._schedule.copy(deep=True)
        ms, oi, g, old, new, delta = self.makespan, self.oidt, None, None, None, 0
        checker, checker_seconds = self.baseline_checker, 0.0
        if search.move is not None:
            oi, ms, g, new = search.move
            old = self.group_starts[g]
            delta = new - old
            schedule.loc[schedule["g"] == g, ["ST", "CT"]] += delta
            # Recompute from the actual modified schedule, never re-decode order.
            direct_ms = int(schedule["CT"].max())
            ovens = {k: [(int(row.ST), int(row.CT)) for row in schedule.itertuples()
                         if _optional_integer(row.assigned_k, "assigned_k") == k]
                     for k in self._ovens}
            if (direct_ms, oidt_union(ovens)) != (ms, oi):
                raise RuntimeError("incremental objective differs from the modified schedule")
            check_started = perf_counter()
            checker = verify_schedule(self._json_path, schedule, ms, oi)
            checker_seconds = perf_counter() - check_started
            if not checker["is_valid"]:
                raise RuntimeError(f"retimed schedule failed checker: {checker}")
        invariants = verify_retiming_invariants(self._schedule, schedule, g, delta)
        if not invariants["is_valid"]:
            raise RuntimeError(f"retiming invariant failure: {invariants}")
        return RetimingResult(schedule, ms, oi, g is not None, g, old, new, delta,
                             checker, invariants, search,
                             {"setup_seconds": self.setup_seconds,
                              "baseline_checker_seconds": self.baseline_checker_seconds,
                              "search_seconds": search.seconds,
                              "final_checker_seconds": checker_seconds,
                              "retime_seconds": perf_counter() - started})


def retime_schedule(instance: dict, schedule_df: pd.DataFrame, json_path: str | Path,
                    *, boundary_only: bool = True, preserve_order: bool = False) -> RetimingResult:
    """Return a new schedule after at most one best strict Pareto-improving move.

    Boundary selection preserves the best OIDT, but may omit makespan-only moves.
    Failure penalties remain the caller's policy; invalid input is not repaired.
    """
    return RetimingContext(instance, schedule_df, json_path).retime(
        boundary_only=boundary_only, preserve_order=preserve_order)
