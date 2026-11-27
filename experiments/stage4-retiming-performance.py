"""Profile, compare, and benchmark Retiming without changing the search model."""

CONFIG = {
    "baseline": "repro/retiming-baseline",
    "reference_results": "results/stage4-retiming-validation-20261126T105021665036Z",
    "legacy_pilot": "external/retiming-source/pilot/optimization_pilot",
    "corpus": "all",
    "archive": None,
    "seed": 20261128,
    "warmup_passes": 1,
    "repetitions": 5,
    "profile_schedules_per_instance": 10,
    "policies": [False, True],
    "boundary_modes": [False, True],
    "oidt": "per-compartment busy-union",
}

import argparse
import ast
import cProfile
from collections import defaultdict
from datetime import datetime, timezone
import importlib.util
import hashlib
import difflib
import json
from pathlib import Path
import platform
import pstats
import re
import statistics
import sys
import subprocess
from time import perf_counter
import types
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np
import pandas as pd

from bakery.decoder import hnfsm_decode, load_hnfsm_instance
from bakery.io import save_json
from bakery.paths import REPO_ROOT, RESULTS, processed_json
from bakery.retiming_audit import ExhaustiveOracle, legacy_compatibility, legacy_to_frame, load_legacy_schedules


def reference_module(name="_retiming_baseline"):
    verify_baseline()
    path = REPO_ROOT / CONFIG["baseline"] / "src/bakery/retiming.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def verify_baseline():
    root = REPO_ROOT / CONFIG["baseline"]
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    expected_files = manifest.get("sha256") or {name: manifest["protected_sha256"][name]
        for name in ("src/bakery/retiming.py", "tests/test_retiming.py")}
    for name, expected in expected_files.items():
        path = root / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Archived baseline SHA-256 mismatch: {path}")
    return manifest


def evidence_preflight(pilot):
    manifest = json.loads((REPO_ROOT / "repro/retiming-evidence.json").read_text(encoding="utf-8"))
    for name in manifest["profiles"]["corpus"]:
        path = pilot / Path(name).relative_to("pilot/optimization_pilot")
        if not path.is_file():
            raise FileNotFoundError(f"Missing historical corpus: {path}. See docs/retiming.md; use --corpus current for the repository-only 200 schedules.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["sha256"][name]:
            raise ValueError(f"Historical corpus SHA-256 mismatch: {path}")


def corpus():
    instances = {name: load_hnfsm_instance(processed_json(name)) for name in ("BK15", "BK50")}
    rows = []
    pilot = REPO_ROOT / CONFIG["legacy_pilot"]
    if CONFIG["corpus"] == "all":
        evidence_preflight(pilot)
        mapping = legacy_compatibility(pilot, instances["BK15"])
        for name, i, row in load_legacy_schedules(pilot):
            rows.append({"id": f"legacy/{name}/{i}", "instance": "BK15", "kind": "legacy",
                         "frame": legacy_to_frame(row["result"]["schedule"], mapping),
                         "order": [mapping["group_map"][g] for g in row["order"]]})
    for name in ("BK15", "BK50"):
        saved = json.loads((REPO_ROOT / CONFIG["reference_results"] / f"{name.lower()}-details.json").read_text(encoding="utf-8"))
        for row in saved["records"]:
            ms, oi, frame = hnfsm_decode(instances[name], row["order"], return_schedule=True)
            if (ms, oi) != (row["base_makespan"], row["base_oidt"]):
                raise RuntimeError("reference corpus differs")
            rows.append({"id": f"{name}/{row['sample_index']}", "instance": name, "kind": "new",
                         "frame": frame, "order": row["order"]})
    expected = 266 if CONFIG["corpus"] == "all" else 200
    if len(rows) != expected:
        raise RuntimeError(f"expected {expected} schedules, got {len(rows)}")
    return instances, rows


def distribution(values):
    return {"n": len(values), "mean_ms": statistics.mean(values) * 1000,
            "median_ms": statistics.median(values) * 1000,
            "p95_ms": float(np.percentile(values, 95)) * 1000}


def instrumented_reference():
    """Insert coarse timing boundaries into a memory-only copy of reference code.

    No loop contents, candidate generation, checks, or data are changed. These
    timings have instrumentation overhead; speed comparisons use uninstrumented
    implementations. Feasible-window time is a nested part of total search.
    """
    reference = reference_module("_retiming_profile_original")
    source = Path(reference.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    totals, state = defaultdict(float), [None, None]

    def mark(label):
        now = perf_counter()
        if state[0] is not None:
            totals[state[0]] += now - state[1]
        state[:] = [label, now]

    def probe(label):
        return ast.Expr(ast.Call(ast.Name("_perf_mark", ast.Load()), [ast.Constant(label)], []))

    def init_label(text, current):
        for prefix, label in (
            ("self._schedule =", "input_dataframe_copy"),
            ("self._json_path =", "instance_metadata"),
            ("seen =", "dataframe_conversion_and_validation"),
            ("self.group_ids =", "resource_lists_and_base_objectives"),
            ("check_started =", "baseline_checker"),
            ("self.baseline_checker_seconds =", "baseline_checker_guard"),
            ("self._profiles =", "oven_profiles"),
            ("self.setup_seconds =", "setup_finish")):
            if text.startswith(prefix):
                return label
        return current

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name not in ("__init__", "retime"):
            continue
        current = "input_shape_validation" if node.name == "__init__" else "event_search_total"
        statements = [probe(current)]
        for statement in node.body:
            text = ast.unparse(statement)
            label = init_label(text, current) if node.name == "__init__" else current
            if node.name == "retime":
                if text.startswith("schedule ="):
                    label = "result_dataframe_generation"
                elif text.startswith("invariants ="):
                    label = "invariants"
                elif isinstance(statement, ast.Return):
                    label = "result_finish"
                if isinstance(statement, ast.If) and text.startswith("if search.move is not None"):
                    body = []
                    for nested in statement.body:
                        nested_text = ast.unparse(nested)
                        if nested_text.startswith("direct_ms ="):
                            body.append(probe("direct_objectives"))
                        if nested_text.startswith("check_started ="):
                            body.append(probe("final_checker"))
                        if nested_text.startswith("checker_seconds ="):
                            body.append(probe("final_checker_guard"))
                        body.append(nested)
                    statement.body = body
            if label != current:
                statements.append(probe(label))
                current = label
            statements.append(statement)
        node.body = statements
    module = types.ModuleType("_retiming_profile_instrumented")
    module.__file__ = reference.__file__
    module.__dict__["_perf_mark"] = mark
    sys.modules[module.__name__] = module
    exec(compile(ast.fix_missing_locations(tree), reference.__file__, "exec"), module.__dict__)
    # Observe JSON/metadata preparation without changing the checker on disk.
    from bakery import checker
    checker_tree = ast.parse(Path(checker.__file__).read_text(encoding="utf-8"))
    checker_state = [None, None]

    def checker_mark(label):
        now = perf_counter()
        if checker_state[0] is not None:
            totals[checker_state[0]] += now - checker_state[1]
        checker_state[:] = [label, now]

    for node in ast.walk(checker_tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "verify_schedule":
            continue
        body = []
        for statement in node.body:
            text = ast.unparse(statement)
            label = None
            if isinstance(statement, ast.With):
                label = "checker_json_loading_nested"
            elif text.startswith("machines ="):
                label = "checker_metadata_nested"
            elif text.startswith("violations ="):
                label = "checker_rules_nested"
            elif isinstance(statement, ast.Return):
                label = None
                body.append(ast.Expr(ast.Call(ast.Name("_checker_mark", ast.Load()), [ast.Constant(None)], [])))
            if label:
                body.append(ast.Expr(ast.Call(ast.Name("_checker_mark", ast.Load()), [ast.Constant(label)], [])))
            body.append(statement)
        node.body = body
    checker_module = types.ModuleType("_checker_profile_instrumented")
    checker_module.__dict__["_checker_mark"] = checker_mark
    exec(compile(ast.fix_missing_locations(checker_tree), checker.__file__, "exec"), checker_module.__dict__)
    module.verify_schedule = checker_module.verify_schedule
    original = module.RetimingContext.feasible_intervals

    def measured_intervals(self, *args, **kwargs):
        started = perf_counter()
        result = original(self, *args, **kwargs)
        totals["feasible_intervals_nested"] += perf_counter() - started
        return result

    module.RetimingContext.feasible_intervals = measured_intervals
    return module, totals, mark


def baseline_profile(instances, rows, out):
    baseline = reference_module()
    report = {"config": CONFIG, "environment": {"python": platform.python_version(),
              "platform": platform.platform(), "processor": platform.processor()}, "instances": {}}
    for name in ("BK15", "BK50"):
        selected = [r for r in rows if r["kind"] == "new" and r["instance"] == name]
        path, instance = processed_json(name), instances[name]
        for row in selected:
            baseline.retime_schedule(instance, row["frame"], path)
        elapsed = []
        for _ in range(3):
            for row in selected:
                started = perf_counter()
                baseline.retime_schedule(instance, row["frame"], path)
                elapsed.append(perf_counter() - started)
        module, totals, mark = instrumented_reference()
        sampled = selected[:CONFIG["profile_schedules_per_instance"]]
        for row in sampled:
            module.retime_schedule(instance, row["frame"], path)
            mark(None)
        profiler = cProfile.Profile()
        profiler.enable()
        for row in sampled:
            baseline.retime_schedule(instance, row["frame"], path)
        profiler.disable()
        profiler.dump_stats(str(out / f"baseline-{name.lower()}.prof"))
        stats = pstats.Stats(profiler)
        entries = [{"file": key[0], "line": key[1], "function": key[2],
                    "calls": values[1], "self_seconds": values[2], "cumulative_seconds": values[3]}
                   for key, values in stats.stats.items()]
        top = sorted(entries, key=lambda e: e["cumulative_seconds"], reverse=True)[:30]
        json_loading = sum(e["cumulative_seconds"] for e in entries if e["function"] == "load" and e["file"].replace("\\", "/").endswith("json/__init__.py"))
        checker_metadata = sum(e["cumulative_seconds"] for e in entries if e["function"] == "<dictcomp>" and e["file"].endswith("checker.py"))
        report["instances"][name] = {"uninstrumented_total": distribution(elapsed),
            "instrumented_stage_mean_ms": {k: v / len(sampled) * 1000 for k, v in totals.items()},
            "cprofile_json_mean_ms": json_loading / len(sampled) * 1000,
            "cprofile_checker_metadata_mean_ms": checker_metadata / len(sampled) * 1000,
            "cprofile_top": top}
        print(name, json.dumps(report["instances"][name]["uninstrumented_total"]),
              json.dumps(report["instances"][name]["instrumented_stage_mean_ms"]), flush=True)
    save_json(out / "baseline-profile.json", report)
    return report


def signature(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=int).encode()).hexdigest()


def stage_profile(instances, rows, out):
    """Coarse paired attribution on the same first ten new schedules per instance.

    The checker receives memory-only timing probes in both versions. These
    instrumented values explain costs; benchmark.json holds the uninstrumented
    performance comparisons. Nested checker/window times must not be summed
    again with their parent stages.
    """
    from bakery import retiming as optimized
    report = {"config": CONFIG, "instrumented": True, "nested_times_not_additive": True, "instances": {}}
    for name, instance in instances.items():
        selected = [r for r in rows if r["instance"] == name and r["kind"] == "new"][:CONFIG["profile_schedules_per_instance"]]
        module, totals, mark = instrumented_reference()
        prepared = optimized.PreparedRetimingInstance(processed_json(name))
        for row in selected:
            module.retime_schedule(instance, row["frame"], processed_json(name))
            mark(None)
            prepared.retime(row["frame"])
        totals.clear()
        for _ in range(CONFIG["repetitions"]):
            for row in selected:
                module.retime_schedule(instance, row["frame"], processed_json(name))
                mark(None)
        n = len(selected) * CONFIG["repetitions"]
        old = {k: v/n*1000 for k, v in totals.items()}
        totals.clear()
        new_stages = defaultdict(list)
        original_checker = optimized.verify_schedule
        original_intervals = optimized.RetimingContext.feasible_intervals

        def intervals(self, *args, **kwargs):
            started = perf_counter()
            result = original_intervals(self, *args, **kwargs)
            totals["feasible_intervals_nested"] += perf_counter()-started
            return result

        optimized.verify_schedule = module.verify_schedule
        optimized.RetimingContext.feasible_intervals = intervals
        try:
            for _ in range(CONFIG["repetitions"]):
                for row in selected:
                    result = prepared.retime(row["frame"])
                    for key, value in result.timings.items():
                        new_stages[key].append(value)
        finally:
            optimized.verify_schedule = original_checker
            optimized.RetimingContext.feasible_intervals = original_intervals
        report["instances"][name] = {"n": n, "baseline_mean_ms": old,
            "optimized_prepared_mean_ms": {k: statistics.mean(v)*1000 for k,v in new_stages.items()},
            "optimized_nested_mean_ms": {k: v/n*1000 for k,v in totals.items()}}
    save_json(out / "stage-profile.json", report)
    return report


def equivalence(instances, rows, out):
    from bakery import retiming as optimized
    baseline = reference_module()
    prepared = {name: optimized.PreparedRetimingInstance(processed_json(name)) for name in instances}
    records, errors = [], []
    result_checks, checker_calls = 0, {"baseline": 0, "optimized": 0}
    interval_groups, feasible_points = 0, 0
    core_ast = {}
    for name in ("boundary_groups", "feasible_intervals", "group_search", "search"):
        import inspect
        import textwrap
        core_ast[name] = ast.dump(ast.parse(textwrap.dedent(inspect.getsource(getattr(baseline.RetimingContext, name))))) == ast.dump(ast.parse(textwrap.dedent(inspect.getsource(getattr(optimized.RetimingContext, name)))))
    for index, row in enumerate(rows):
        frame, name = row["frame"], row["instance"]
        original = frame.copy(deep=True)
        old = baseline.RetimingContext(instances[name], frame, processed_json(name))
        new = prepared[name].context(frame)
        checker_calls["baseline"] += 1
        checker_calls["optimized"] += 1
        checks = {"id": row["id"], "instance": name, "group_signatures": {}, "results": []}
        if old.baseline_checker != new.baseline_checker:
            errors.append([row["id"], "baseline checker report"])
        for preserve in CONFIG["policies"]:
            groups = []
            for g in old.group_ids:
                a, b = old.group_search(g, preserve_order=preserve), new.group_search(g, preserve_order=preserve)
                fa = tuple(t for lo, hi in a.intervals for t in range(lo, hi + 1))
                fb = tuple(t for lo, hi in b.intervals for t in range(lo, hi + 1))
                interval_groups += 1
                feasible_points += len(fa)
                if (a.intervals, a.candidates, a.best, fa) != (b.intervals, b.candidates, b.best, fb):
                    errors.append([row["id"], preserve, g, "group search"])
                groups.append([g, a.intervals, a.candidates, a.best])
            checks["group_signatures"][str(preserve)] = signature(groups)
            for boundary in CONFIG["boundary_modes"]:
                a = old.retime(boundary_only=boundary, preserve_order=preserve)
                b = new.retime(boundary_only=boundary, preserve_order=preserve)
                fields = ("makespan", "oidt", "moved", "moved_group", "old_tg", "new_tg", "delta")
                if any(getattr(a, field) != getattr(b, field) for field in fields):
                    errors.append([row["id"], preserve, boundary, "selected move"])
                try:
                    pd.testing.assert_frame_equal(a.schedule.sort_values(["g", "p", "s"]).reset_index(drop=True),
                                                  b.schedule.sort_values(["g", "p", "s"]).reset_index(drop=True), check_exact=True)
                except AssertionError as exc:
                    errors.append([row["id"], preserve, boundary, "schedule", str(exc)])
                if a.checker != b.checker or not b.checker["is_valid"]:
                    errors.append([row["id"], preserve, boundary, "checker"])
                if not a.invariants["is_valid"] or not b.invariants["is_valid"]:
                    errors.append([row["id"], preserve, boundary, "invariants"])
                if b.makespan > new.makespan or b.oidt > new.oidt:
                    errors.append([row["id"], preserve, boundary, "Pareto"])
                checks["results"].append({"preserve_order": preserve, "boundary_only": boundary,
                    **{field: getattr(b, field) for field in fields},
                    "event_candidates": b.search.candidate_count, "checker_violations": b.checker["total_violations"],
                    "invariant_violations": b.invariants["total_violations"]})
                checker_calls["baseline"] += int(a.moved)
                checker_calls["optimized"] += int(b.moved)
                result_checks += 1
        pd.testing.assert_frame_equal(frame, original, check_exact=True)
        records.append(checks)
        if (index + 1) % 25 == 0:
            print(f"equivalence {index + 1}/{len(rows)} errors={len(errors)}", flush=True)
    report = {"config": CONFIG, "schedules": len(rows), "result_combinations": result_checks,
              "group_policy_comparisons": interval_groups, "feasible_integer_times_compared": feasible_points,
              "search_method_ast_unchanged": core_ast, "checker_calls": checker_calls,
              "mismatches": errors, "records": records}
    save_json(out / "equivalence.json", report)
    if errors or not all(core_ast.values()):
        raise RuntimeError("baseline equivalence failed")
    return report


def exhaustive(instances, rows, out):
    from bakery.retiming import PreparedRetimingInstance
    prepared = {name: PreparedRetimingInstance(processed_json(name)) for name in instances}
    records, errors = [], []
    started = perf_counter()
    for index, row in enumerate(rows):
        name, frame = row["instance"], row["frame"]
        context = prepared[name].context(frame)
        oracle = ExhaustiveOracle(instances[name], frame)
        record = {"id": row["id"], "instance": name, "policies": {}}
        for preserve in CONFIG["policies"]:
            search = context.search(boundary_only=False, preserve_order=preserve)
            scans = {g: oracle.scan_group(g, preserve_order=preserve) for g in oracle.group_ids}
            for group in search.groups:
                scan = scans[group.g]
                feasible = tuple(t for lo, hi in group.intervals for t in range(lo, hi + 1))
                if feasible != scan.feasible_times or group.best != scan.best:
                    errors.append([row["id"], preserve, group.g])
            minima = []
            for boundary in CONFIG["boundary_modes"]:
                selected = oracle.boundary_groups() if boundary else oracle.group_ids
                moves = [(scans[g].best[1], scans[g].best[0], g, scans[g].best[2]) for g in selected
                         if scans[g].best[0] <= oracle.makespan and scans[g].best[1] <= oracle.oidt
                         and (scans[g].best[0] < oracle.makespan or scans[g].best[1] < oracle.oidt)]
                expected = min(moves, default=None)
                actual = context.search(boundary_only=boundary, preserve_order=preserve).move
                if expected != actual:
                    errors.append([row["id"], preserve, boundary, "global move"])
                minima.append(oracle.oidt if expected is None else expected[0])
            if len(set(minima)) != 1:
                errors.append([row["id"], preserve, "boundary minimum OIDT"])
            record["policies"][str(preserve)] = {"groups": len(scans),
                "time_checks": sum(s.time_checks for s in scans.values()),
                "feasible_times": sum(len(s.feasible_times) for s in scans.values()),
                "event_candidates": search.candidate_count}
        records.append(record)
        if (index + 1) % 25 == 0:
            print(f"oracle {index + 1}/{len(rows)} elapsed={perf_counter()-started:.1f}s errors={len(errors)}", flush=True)
    report = {"config": CONFIG, "schedules": len(rows), "scope": {"legacy_BK15": sum(r["kind"] == "legacy" for r in rows), "new_BK15": 100, "new_BK50": 100},
              "policies_per_schedule": 2, "seconds": perf_counter() - started,
              "group_policy_subproblems": sum(p["groups"] for r in records for p in r["policies"].values()),
              "integer_time_checks": sum(p["time_checks"] for r in records for p in r["policies"].values()),
              "feasible_times": sum(p["feasible_times"] for r in records for p in r["policies"].values()),
              "mismatches": errors, "records": records}
    save_json(out / "exhaustive.json", report)
    if errors:
        raise RuntimeError("independent enumeration failed")
    return report


def benchmark(instances, rows, out):
    from bakery import retiming as optimized
    baseline = reference_module()
    prepared = {name: optimized.PreparedRetimingInstance(processed_json(name)) for name in instances}
    values = {name: defaultdict(list) for name in instances}
    stages = {name: defaultdict(lambda: defaultdict(list)) for name in instances}
    counts = {name: defaultdict(int) for name in instances}
    expected_counts = {name: defaultdict(int) for name in instances}
    active = [None, None]
    original_old, original_new = baseline.verify_schedule, optimized.verify_schedule

    def counted_original(path, frame, *args, **kwargs):
        if active[0] is not None:
            counts[active[0]][active[1]] += 1
        return original_old(path, frame, *args, **kwargs)

    baseline.verify_schedule = counted_original
    optimized.verify_schedule = counted_original
    methods = ("baseline", "optimized_direct", "optimized_prepared")
    try:
        for _ in range(CONFIG["warmup_passes"]):
            for row in rows:
                name, frame = row["instance"], row["frame"]
                baseline.retime_schedule(instances[name], frame, processed_json(name))
                optimized.retime_schedule(instances[name], frame, processed_json(name))
                prepared[name].retime(frame)
        for repetition in range(CONFIG["repetitions"]):
            for i, row in enumerate(rows):
                name, frame = row["instance"], row["frame"]
                offset = (repetition + i) % len(methods)
                ordered = methods[offset:] + methods[:offset]
                for method in ordered:
                    active[:] = [name, method]
                    started = perf_counter()
                    if method == "baseline":
                        result = baseline.retime_schedule(instances[name], frame, processed_json(name))
                    elif method == "optimized_direct":
                        result = optimized.retime_schedule(instances[name], frame, processed_json(name))
                    else:
                        result = prepared[name].retime(frame)
                    elapsed = perf_counter() - started
                    active[:] = [None, None]
                    values[name][method].append(elapsed)
                    expected_counts[name][method] += 1 + int(result.moved)
                    for key, seconds in result.timings.items():
                        stages[name][method][key].append(seconds)
            print(f"benchmark repetition {repetition+1}/{CONFIG['repetitions']}", flush=True)
    finally:
        baseline.verify_schedule, optimized.verify_schedule = original_old, original_new
    if counts != expected_counts:
        raise RuntimeError("Checker call count differs from required validation scope")
    report = {"config": CONFIG, "environment": {"python": platform.python_version(), "platform": platform.platform(),
              "processor": platform.processor()}, "instances": {}, "checker_scope": "same unchanged verify_schedule function: baseline and every moved result"}
    for name in instances:
        selected = [r for r in rows if r["instance"] == name]
        decoder_times = {False: [], True: []}
        for row in selected:
            hnfsm_decode(instances[name], row["order"], return_schedule=False)
            hnfsm_decode(instances[name], row["order"], return_schedule=True)
        for repetition in range(CONFIG["repetitions"]):
            for i, row in enumerate(selected):
                pairs = {}
                for flag in ((False, True) if (repetition + i) % 2 else (True, False)):
                    started = perf_counter()
                    ms, oi, frame = hnfsm_decode(instances[name], row["order"], return_schedule=flag)
                    decoder_times[flag].append(perf_counter() - started)
                    pairs[flag] = (ms, oi)
                if pairs[False] != pairs[True]:
                    raise RuntimeError("decoder return_schedule modes differ in objectives")
        pipeline = {"baseline": [], "optimized_prepared": []}

        def pipeline_run(method, row):
            _, _, generated = hnfsm_decode(instances[name], row["order"], return_schedule=True)
            if method == "baseline":
                return baseline.retime_schedule(instances[name], generated, processed_json(name))
            return prepared[name].retime(generated)

        # Actual decode+Retiming wall times, with a separate pipeline warm-up.
        for row in selected:
            for method in pipeline:
                pipeline_run(method, row)
        baseline.verify_schedule = counted_original
        optimized.verify_schedule = counted_original
        try:
            for repetition in range(CONFIG["repetitions"]):
                for i, row in enumerate(selected):
                    methods_pipeline = ("baseline", "optimized_prepared") if (repetition+i)%2 else ("optimized_prepared", "baseline")
                    for method in methods_pipeline:
                        key = "pipeline_" + method
                        active[:] = [name, key]
                        started = perf_counter()
                        result = pipeline_run(method, row)
                        pipeline[method].append(perf_counter() - started)
                        active[:] = [None, None]
                        expected_counts[name][key] += 1 + int(result.moved)
                print(f"{name} pipeline repetition {repetition+1}/{CONFIG['repetitions']}", flush=True)
        finally:
            baseline.verify_schedule, optimized.verify_schedule = original_old, original_new
        if counts[name] != expected_counts[name]:
            raise RuntimeError("pipeline Checker call count differs")
        # Sum matched per-input measurements; the two components were measured
        # separately to avoid presenting a decode+retime pipelined wall time.
        data = {"schedules": len(selected), "measurements_per_method": len(selected)*CONFIG["repetitions"],
                "retiming": {m: distribution(v) for m, v in values[name].items()},
                "stage_timings": {m: {k: distribution(v) for k, v in groups.items()} for m, groups in stages[name].items()},
                "checker_calls": dict(counts[name]), "expected_checker_calls": dict(expected_counts[name]),
                "hnfsm": {str(flag): distribution(v) for flag, v in decoder_times.items()},
                "hnfsm_true_plus_retiming_actual_wall": {m: distribution(v) for m,v in pipeline.items()},
                "hnfsm_true_plus_retiming_component_sum": {m: distribution([a+b for a,b in zip(decoder_times[True],v)]) for m,v in values[name].items()},
                "one_time_preparation": prepared[name].timings}
        old_mean = data["retiming"]["baseline"]["mean_ms"]
        data["improvement"] = {m: {"speedup": old_mean/data["retiming"][m]["mean_ms"],
                                    "reduction_percent": 100*(1-data["retiming"][m]["mean_ms"]/old_mean)}
                               for m in ("optimized_direct", "optimized_prepared")}
        report["instances"][name] = data
    save_json(out / "benchmark.json", report)
    return report


def repository_snapshot():
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top.returncode or Path(top.stdout.strip()).resolve() != REPO_ROOT.resolve():
        return {"available": False, "head": None, "branch": None}
    return {"available": True,
            "branch": subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True, check=True).stdout.strip(),
            "head": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()}


def capture_run_inputs(out):
    """Bind each new run to its source/data bytes, not to an old working tree."""
    paths = [REPO_ROOT / p for p in ("src/bakery/retiming.py", "src/bakery/retiming_audit.py", "src/bakery/checker.py",
             "src/bakery/decoder.py", "tests/test_retiming.py", "experiments/stage4-retiming-validation.py",
             "experiments/stage4-retiming-performance.py")]
    paths += [processed_json(name) for name in ("BK15", "BK50")]
    paths += [REPO_ROOT / CONFIG["reference_results"] / f"{name}-details.json" for name in ("bk15", "bk50")]
    baseline_root = REPO_ROOT / CONFIG["baseline"]
    paths += [baseline_root / name for name in ("manifest.json", "src/bakery/retiming.py", "tests/test_retiming.py")]
    evidence_path = REPO_ROOT / "repro/retiming-evidence.json"
    paths.append(evidence_path)
    if CONFIG["corpus"] == "all":
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        pilot = REPO_ROOT / CONFIG["legacy_pilot"]
        paths += [pilot / Path(name).relative_to("pilot/optimization_pilot") for name in evidence["profiles"]["corpus"]]
    path = out / "run-inputs.json"
    current = {(p.relative_to(REPO_ROOT).as_posix() if p.is_relative_to(REPO_ROOT) else p.as_posix()):
               hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if previous["sha256"] != current or previous["config"] != CONFIG:
            raise ValueError("run inputs/config changed; use a new output directory")
    else:
        save_json(path, {"config": CONFIG.copy(), "repository": repository_snapshot(), "sha256": current,
                         "baseline": verify_baseline()})


def finalize(out):
    """Verify run input hashes; preserve recorded revisions without pinning HEAD."""
    backup = REPO_ROOT / CONFIG["baseline"]
    manifest = verify_baseline()
    if not (out / "run-inputs.json").is_file():
        raise ValueError("No run-inputs.json: historical results are read-only; start a new run")
    capture_run_inputs(out)
    sources = ["src/bakery/retiming.py", "src/bakery/retiming_audit.py", "tests/test_retiming.py",
               "experiments/stage4-retiming-validation.py", "experiments/stage4-retiming-performance.py"]
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    equivalence_report = json.loads((out / "equivalence.json").read_text(encoding="utf-8"))
    oracle = json.loads((out / "exhaustive.json").read_text(encoding="utf-8"))
    performance = json.loads((out / "benchmark.json").read_text(encoding="utf-8"))
    expected = 266 if CONFIG["corpus"] == "all" else 200
    if equivalence_report["schedules"] != expected or oracle["schedules"] != expected:
        raise ValueError("result corpus scope differs from requested config")
    if equivalence_report["mismatches"] or oracle["mismatches"]:
        raise RuntimeError("cannot finalize failed validation")
    if not (out / "pytest-output.txt").exists():
        test = subprocess.run([sys.executable, "-m", "pytest"], capture_output=True, text=True)
        (out / "pytest-output.txt").write_text(test.stdout + test.stderr, encoding="utf-8")
        if test.returncode:
            raise RuntimeError("pytest failed")
    test_text = (out / "pytest-output.txt").read_text(encoding="utf-8")
    match = re.search(r"(\d+) passed", test_text)
    if not match or " failed" in test_text:
        raise RuntimeError("no successful pytest evidence")
    old_tests = ast.parse((backup / "tests/test_retiming.py").read_text(encoding="utf-8"))
    new_tests = ast.parse((REPO_ROOT / "tests/test_retiming.py").read_text(encoding="utf-8"))
    functions = lambda tree: {node.name: ast.dump(node) for node in tree.body if isinstance(node, ast.FunctionDef)}
    old_functions, new_functions = functions(old_tests), functions(new_tests)
    if not all(new_functions.get(key) == value for key, value in old_functions.items()):
        raise RuntimeError("an original test function was modified")
    for name in ("summary.json", "source-comparison.patch", "baseline-manifest.json"):
        if (out / name).exists():
            raise FileExistsError(out / name)
    changes = []
    for name in sources:
        before = (backup / name).read_text(encoding="utf-8") if (backup / name).exists() else ""
        after = (REPO_ROOT / name).read_text(encoding="utf-8")
        changes.extend(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                           fromfile="baseline/" + name if before else "/dev/null", tofile=name))
    (out / "source-comparison.patch").write_text("".join(changes), encoding="utf-8")
    (out / "baseline-manifest.json").write_bytes((backup / "manifest.json").read_bytes())
    summary = {"config": CONFIG, "repository": repository_snapshot(),
        "pytest_passed": int(match.group(1)), "old_test_functions_unchanged": True,
        "integrity": {"run_input_hashes_verified": True, "archived_baseline": manifest},
        "source_sha256": {name: digest(REPO_ROOT / name) for name in sources},
        "equivalence": {k: v for k,v in equivalence_report.items() if k not in ("records", "config", "meta")},
        "independent_exhaustive": {k: v for k,v in oracle.items() if k not in ("records", "config", "meta")},
        "performance": {name: {k:v for k,v in data.items() if k != "stage_timings"} for name,data in performance["instances"].items()},
        "row_order_contract": "evaluation preserves input row/index/column order; schedule_for_export sorts ST,g,p,s explicitly",
        "interface_contract": "legacy instance must equal JSON data; PreparedRetimingInstance owns source metadata and rejects content changes by SHA-256",
        "checker_contract": "unchanged bakery.checker.verify_schedule executes every rule through a row mapping adapter; no checker or JSON parse is skipped"}
    save_json(out / "summary.json", summary)
    if CONFIG["archive"] is None:
        print(json.dumps({"output": str(out), "archive": "not_requested", "pytest_passed": int(match.group(1))}), flush=True)
        return
    archive_path = REPO_ROOT / CONFIG["archive"]
    entries = [(REPO_ROOT / name, name) for name in sources]
    entries += [(path, path.relative_to(REPO_ROOT).as_posix()) for path in sorted(out.rglob("*")) if path.is_file()]
    entries += [(backup / name, "baseline/" + name) for name in ("src/bakery/retiming.py", "tests/test_retiming.py")]
    entries.append((backup / "manifest.json", "baseline/manifest.json"))
    with ZipFile(archive_path, "x", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path, name in entries:
            archive.write(path, name)
    with ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("archive CRC failed")
        for path, name in entries:
            if hashlib.sha256(archive.read(name)).hexdigest() != digest(path):
                raise RuntimeError(f"archive byte mismatch: {name}")
    print(json.dumps({"output": str(out), "archive": str(archive_path), "files": len(entries),
                      "bytes": archive_path.stat().st_size, "sha256": digest(archive_path),
                      "pytest_passed": int(match.group(1))}, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("inputs", "baseline", "stages", "equivalence", "exhaustive", "benchmark", "finalize", "all"), default="all")
    parser.add_argument("--output")
    parser.add_argument("--baseline")
    parser.add_argument("--legacy-pilot", default=CONFIG["legacy_pilot"])
    parser.add_argument("--corpus", choices=("all", "current"), default=CONFIG["corpus"])
    parser.add_argument("--archive", help="optional new ZIP path; never overwrites an existing archive")
    args = parser.parse_args()
    if args.baseline:
        CONFIG["baseline"] = args.baseline
    CONFIG["legacy_pilot"] = args.legacy_pilot
    CONFIG["corpus"] = args.corpus
    CONFIG["archive"] = args.archive
    out = REPO_ROOT / args.output if args.output else RESULTS / ("stage4-retiming-performance-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    out.mkdir(parents=True, exist_ok=args.output is not None)
    if args.phase == "finalize":
        finalize(out)
        return
    instances, rows = corpus()
    capture_run_inputs(out)
    if args.phase == "inputs":
        report = {"config": CONFIG.copy(), "scope": args.corpus, "schedules_loaded": len(rows),
                  "historical_schedules_loaded": sum(r["kind"] == "legacy" for r in rows),
                  "validation_executed": False, "baseline_sha256_verified": True}
        if (out / "inputs.json").exists():
            raise FileExistsError(out / "inputs.json")
        save_json(out / "inputs.json", report)
        print(json.dumps(report), flush=True)
        return
    phases = {"baseline": baseline_profile, "stages": stage_profile, "equivalence": equivalence, "exhaustive": exhaustive, "benchmark": benchmark}
    for phase, function in phases.items():
        if args.phase in (phase, "all"):
            filename = {"baseline": "baseline-profile.json", "stages": "stage-profile.json"}.get(phase, phase + ".json")
            if (out / filename).exists():
                raise FileExistsError(out / filename)
            function(instances, rows, out)
    if args.phase == "all":
        finalize(out)
    print("OUTPUT", out, flush=True)


if __name__ == "__main__":
    main()
