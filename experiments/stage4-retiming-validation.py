"""Reproducible standalone Retiming audit; never runs an optimizer.

Usage: uv run --locked python experiments/stage4-retiming-validation.py
Outputs go to a fresh results/stage4-retiming-validation-<UTC timestamp>/.
Legacy scripts run only in a fresh scratch copy; supplied evidence is read-only.
"""

CONFIG = {
    "instances": ["BK15", "BK50"],
    "seed": 20261126,
    "feasible_schedules_per_instance": 100,
    "max_attempts_per_instance": 1000,
    "oracle_sample_indices": [0, 1, 2],  # natural order, then first two feasible random orders
    "oracle_preserve_order_modes": [False, True],
    "oidt": "per-compartment busy-union",
    "retiming": "one best group move; fixed assignments; boundary groups by default",
    "scope": "current",
    "legacy_source": "external/retiming-source",
    "legacy_pilot": "external/retiming-source/pilot/optimization_pilot",
    "rerun_legacy_scripts": True,
    "output_prefix": "stage4-retiming-validation",
}

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import statistics
import subprocess
import sys
from time import perf_counter

import numpy as np
import pandas as pd
from openpyxl import load_workbook

from bakery.checker import verify_schedule
from bakery.decoder import INFEASIBLE, hnfsm_decode, load_hnfsm_instance
from bakery.io import save_csv, save_json
from bakery.paths import REPO_ROOT, RESULTS, RAW_FILES, processed_json
from bakery.retiming import RetimingContext, schedule_for_export
from bakery.retiming_audit import (ExhaustiveOracle, legacy_compatibility,
                                  legacy_to_frame, load_legacy_schedules)


def fingerprint(path):
    return {"path": str(path.relative_to(REPO_ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def evidence_preflight(source):
    manifest = json.loads((REPO_ROOT / "repro/retiming-evidence.json").read_text(encoding="utf-8"))
    profile = "legacy_rerun" if CONFIG["rerun_legacy_scripts"] else "legacy_validation"
    for name in manifest["profiles"][profile]:
        path = source / name
        if not path.is_file():
            raise FileNotFoundError(f"Missing external evidence: {path}. See docs/retiming.md; use --scope current for repository-only validation.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["sha256"][name]:
            raise ValueError(f"External evidence SHA-256 mismatch: {path}")
    return {"profile": profile, "files_verified": len(manifest["profiles"][profile])}


def objective_pair(context, search):
    return (context.makespan, context.oidt) if search.move is None else (search.move[1], search.move[0])


def oracle_audit(context, instance, frame):
    started = perf_counter()
    oracle = ExhaustiveOracle(instance, frame)
    result = {"policies": {}, "errors": []}
    if (context.makespan, context.oidt) != (oracle.makespan, oracle.oidt):
        result["errors"].append("baseline objectives differ from minute-set oracle")
    if context.boundary_groups() != oracle.boundary_groups():
        result["errors"].append("boundary group selection differs")
    for preserve in CONFIG["oracle_preserve_order_modes"]:
        events = context.search(boundary_only=False, preserve_order=preserve)
        scans = {g: oracle.scan_group(g, preserve_order=preserve) for g in oracle.group_ids}
        policy = {"groups": len(scans), "time_checks": sum(s.time_checks for s in scans.values()),
                  "feasible_times": sum(len(s.feasible_times) for s in scans.values()),
                  "event_candidates": events.candidate_count, "feasible_set_mismatches": 0,
                  "group_optimum_mismatches": 0, "deterministic_start_mismatches": 0,
                  "global_move_mismatches": 0}
        for group in events.groups:
            scan = scans[group.g]
            expanded = tuple(t for lo, hi in group.intervals for t in range(lo, hi + 1))
            if expanded != scan.feasible_times:
                policy["feasible_set_mismatches"] += 1
                result["errors"].append(f"feasible times: g={group.g}, preserve={preserve}")
            if group.best[:2] != scan.best[:2]:
                policy["group_optimum_mismatches"] += 1
                result["errors"].append(f"group optimum: g={group.g}, preserve={preserve}")
            if group.best != scan.best:
                policy["deterministic_start_mismatches"] += 1
        for boundary_only in (False, True):
            selected = oracle.boundary_groups() if boundary_only else oracle.group_ids
            moves = [(scans[g].best[1], scans[g].best[0], g, scans[g].best[2]) for g in selected
                     if scans[g].best[0] <= oracle.makespan and scans[g].best[1] <= oracle.oidt
                     and (scans[g].best[0] < oracle.makespan or scans[g].best[1] < oracle.oidt)]
            expected_move = min(moves, default=None)
            actual = context.search(boundary_only=boundary_only, preserve_order=preserve).move
            if expected_move != actual:
                policy["global_move_mismatches"] += 1
                result["errors"].append(f"global move: preserve={preserve}, boundary={boundary_only}")
        result["policies"][str(preserve)] = policy
    result["seconds"] = perf_counter() - started
    return result


def audit_schedule(instance, path, frame, *, enumerate_all=False):
    started = perf_counter()
    context = RetimingContext(instance, frame, path)
    result = context.retime()
    primary_seconds = perf_counter() - started
    full = context.search(boundary_only=False)
    full_ms, full_oi = objective_pair(context, full)
    record = {
        "base_makespan": context.makespan, "base_oidt": context.oidt,
        "makespan": result.makespan, "oidt": result.oidt, "oidt_reduction": context.oidt - result.oidt,
        "makespan_change": result.makespan - context.makespan, "moved": result.moved,
        "moved_group": result.moved_group, "old_tg": result.old_tg, "new_tg": result.new_tg,
        "delta": result.delta, "checker_violations": result.checker["total_violations"],
        "invariant_violations": result.invariants["total_violations"],
        "pareto_violation": result.makespan > context.makespan or result.oidt > context.oidt,
        "all_group_candidates": full.candidate_count,
        "boundary_candidates": result.search.candidate_count,
        "boundary_groups": len(result.search.groups),
        "boundary_oidt_mismatch": result.oidt != full_oi,
        "full_group_makespan": full_ms, "full_group_oidt": full_oi,
        "full_boundary_makespan_difference": full_ms != result.makespan,
        "retiming_total_seconds": primary_seconds, **result.timings,
    }
    if enumerate_all:
        record["oracle"] = oracle_audit(context, instance, frame)
    return context, result, record


def aggregate(records):
    gains = [r["oidt_reduction"] for r in records]
    timing_keys = ["hnfsm_seconds", "retiming_total_seconds", "search_seconds", "setup_seconds",
                   "baseline_checker_seconds", "final_checker_seconds"]
    return {"validated_schedules": len(records), "oidt_improved": sum(g > 0 for g in gains),
            "oidt_improved_ratio": sum(g > 0 for g in gains) / len(records) if records else None,
            "mean_oidt_reduction": statistics.mean(gains) if gains else None,
            "median_oidt_reduction": statistics.median(gains) if gains else None,
            "max_oidt_reduction": max(gains, default=None),
            "makespan_change_min": min((r["makespan_change"] for r in records), default=None),
            "makespan_change_max": max((r["makespan_change"] for r in records), default=None),
            "checker_violations": sum(r["checker_violations"] for r in records),
            "invariant_violations": sum(r["invariant_violations"] for r in records),
            "pareto_violations": sum(r["pareto_violation"] for r in records),
            "boundary_oidt_mismatches": sum(r["boundary_oidt_mismatch"] for r in records),
            "full_boundary_makespan_differences": sum(r["full_boundary_makespan_difference"] for r in records),
            "all_group_candidates": sum(r["all_group_candidates"] for r in records),
            "boundary_candidates": sum(r["boundary_candidates"] for r in records),
            "timings_total_seconds": {key: sum(r.get(key, 0) for r in records) for key in timing_keys},
            "oracle_schedules": sum("oracle" in r for r in records),
            "oracle_seconds": sum(r.get("oracle", {}).get("seconds", 0) for r in records),
            "oracle_errors": [e for r in records for e in r.get("oracle", {}).get("errors", [])],
            "oracle_totals": {key: sum(p[key] for r in records for p in r.get("oracle", {}).get("policies", {}).values())
                              for key in ("groups", "time_checks", "feasible_times", "event_candidates",
                                          "feasible_set_mismatches", "group_optimum_mismatches",
                                          "deterministic_start_mismatches", "global_move_mismatches")}}


def rerun_legacy(source, run_id):
    """Unmodified numerical algorithms, copied outputs, portable boundary harness."""
    dest = REPO_ROOT / "scratch" / f"retiming-legacy-rerun-{run_id}"
    shutil.copytree(source / "event-point", dest)
    shutil.copytree(source / "pilot/optimization_pilot", dest / "optimization_pilot")
    logs = []
    for script in ("retime_eval.py", "event_interval.py"):
        completed = subprocess.run([sys.executable, str(dest / script)], capture_output=True,
                                   text=True, encoding="utf-8", check=True)
        logs.append(completed.stdout)
    # boundary_abl.main() hardcodes /mnt/data/_event_review. Call its unchanged
    # solve() in a sibling script rather than modifying any supplied source.
    harness = dest / "audit-boundary.py"
    harness.write_text(
        'import gzip,json\nfrom pathlib import Path\nimport boundary_abl as B\nimport retime_eval as R\n'
        'rows=[]\n'
        'for path in sorted(R.ROOT.glob("*_pareto_schedules.json.gz")):\n'
        '    with gzip.open(path,"rt") as f: rows.extend(json.load(f))\n'
        'out={}\nfor preserve in (False,True):\n'
        '    results=[B.solve(r["result"]["schedule"],preserve) for r in rows]\n'
        '    expected=json.loads((Path(__file__).parent/f"retime_results_{preserve}.json").read_text(encoding="utf-8"))\n'
        '    out[str(preserve)]={"schedules":len(results),"candidates":sum(r[1] for r in results),'
        '"objective_mismatches":sum(tuple(r[0][:2])!=(e["best_oi"],e["best_cmax"]) for r,e in zip(results,expected))}\n'
        '(Path(__file__).parent/"boundary-rerun.json").write_text(json.dumps(out,indent=2))\n'
        'print(json.dumps(out))\n', encoding="utf-8")
    completed = subprocess.run([sys.executable, str(harness)], capture_output=True,
                               text=True, encoding="utf-8", check=True)
    logs.append(completed.stdout)
    (dest / "audit-log.txt").write_text("\n".join(logs), encoding="utf-8")
    comparisons = {}
    for name in ("retime_results_False.json", "retime_results_True.json", "event_interval_summary.json"):
        original = json.loads((source / "event-point" / name).read_text(encoding="utf-8"))
        rerun = json.loads((dest / name).read_text(encoding="utf-8"))
        comparisons[name] = original == rerun
    return {"path": str(dest.relative_to(REPO_ROOT)), "exact_saved_result_matches": comparisons,
            "retime_summary": json.loads((dest / "retime_summary.json").read_text(encoding="utf-8")),
            "boundary": json.loads((dest / "boundary-rerun.json").read_text(encoding="utf-8")),
            "boundary_main_portability_issue": "absolute /mnt/data/_event_review; solve() called unchanged"}


def validate_legacy(out, source):
    root = REPO_ROOT / CONFIG["legacy_pilot"]
    path = processed_json("BK15")
    instance = load_hnfsm_instance(path)
    compat = legacy_compatibility(root, instance)
    original_results = {str(p): {(r["name"], r["i"]): r for r in json.loads(
        (source / "event-point" / f"retime_results_{p}.json").read_text(encoding="utf-8"))} for p in (False, True)}
    records, errors = [], []
    for number, (name, i, row) in enumerate(load_legacy_schedules(root)):
        frame = legacy_to_frame(row["result"]["schedule"], compat)
        context, result, record = audit_schedule(instance, path, frame, enumerate_all=True)
        record.update({"name": name, "i": i, "policies": {}})
        for preserve in (False, True):
            checked_result = context.retime(boundary_only=False, preserve_order=preserve)
            full = checked_result.search
            boundary = context.search(preserve_order=preserve)
            ms, oi = objective_pair(context, full)
            old = original_results[str(preserve)][name, i]
            match = (ms, oi) == (old["best_cmax"], old["best_oi"])
            record["policies"][str(preserve)] = {"makespan": ms, "oidt": oi,
                "oidt_reduction": context.oidt - oi, "all_candidates": full.candidate_count,
                "boundary_candidates": boundary.candidate_count, "matches_old_objectives": match,
                "checker_violations": checked_result.checker["total_violations"],
                "invariant_violations": checked_result.invariants["total_violations"]}
            if not match:
                errors.append(f"legacy objectives differ: {name}/{i}, preserve={preserve}")
        # The old decoder uses assignment backtracking, the current one first-fit.
        order = [compat["group_map"][key] for key in row["order"]]
        ms, oi, decoded = hnfsm_decode(instance, order, return_schedule=True)
        record["current_decoder_failed"] = ms >= INFEASIBLE
        record["current_decoder_same_objectives"] = (ms, oi) == (context.makespan, context.oidt)
        core = ["g", "p", "s", "ST", "CT", "assigned_k", "assigned_l"]
        record["current_decoder_same_schedule"] = False
        if decoded is not None:
            try:
                pd.testing.assert_frame_equal(
                    frame[core].sort_values(["g", "p", "s"]).reset_index(drop=True).fillna(-1),
                    decoded[core].sort_values(["g", "p", "s"]).reset_index(drop=True).fillna(-1),
                    check_dtype=False)
                record["current_decoder_same_schedule"] = True
            except AssertionError:
                pass
        if decoded is not None and not verify_schedule(path, decoded, ms, oi)["is_valid"]:
            errors.append(f"current decoder invalid: {name}/{i}")
        records.append(record)
        if number % 10 == 0:
            print(f"legacy {number + 1}/66", flush=True)
    # Excel binary hashes differ: inspect actual A1:O160 values separately.
    old_book = load_workbook(root / "frozen/hnfsm_stage1/BK15.xlsx", read_only=True, data_only=True)
    new_book = load_workbook(RAW_FILES["BK15"], read_only=True, data_only=True)
    cell_differences = []
    old_cells = old_book["BK15"].iter_rows(min_row=1, max_row=160, min_col=1, max_col=15, values_only=True)
    new_cells = new_book["BK15"].iter_rows(min_row=1, max_row=160, min_col=1, max_col=15, values_only=True)
    for row, (old_row, new_row) in enumerate(zip(old_cells, new_cells), start=1):
        for col, (a, b) in enumerate(zip(old_row, new_row), start=1):
            if a != b:
                cell_differences.append({"row": row, "column": col, "old": a, "current": b})
    old_book.close()
    new_book.close()
    summary = aggregate(records)
    summary.update({"compatibility": {key: compat[key] for key in ("group_map", "machine_map", "employee_map", "operations_compared")},
                    "raw_xlsx_a1_o160_cell_differences": cell_differences,
                    "original_objective_errors": errors,
                    "current_decoder_failed": sum(r["current_decoder_failed"] for r in records),
                    "current_decoder_same_objectives": sum(r["current_decoder_same_objectives"] for r in records),
                    "current_decoder_same_schedule": sum(r["current_decoder_same_schedule"] for r in records),
                    "policies": {str(p): {"oidt_improved": sum(r["policies"][str(p)]["oidt_reduction"] > 0 for r in records),
                                          "mean_oidt_reduction": statistics.mean(r["policies"][str(p)]["oidt_reduction"] for r in records),
                                          "all_candidates": sum(r["policies"][str(p)]["all_candidates"] for r in records),
                                          "boundary_candidates": sum(r["policies"][str(p)]["boundary_candidates"] for r in records),
                                          "checker_violations": sum(r["policies"][str(p)]["checker_violations"] for r in records),
                                          "invariant_violations": sum(r["policies"][str(p)]["invariant_violations"] for r in records)}
                                 for p in (False, True)}})
    save_json(out / "legacy-details.json", {"config": CONFIG, "records": records})
    return summary


def validate_new(name, instance_seed, out):
    path = processed_json(name)
    instance = load_hnfsm_instance(path)
    rng = np.random.default_rng(instance_seed)
    records, failed, invalid, seen = [], [], [], set()
    attempts, duplicates = 0, 0
    while len(records) < CONFIG["feasible_schedules_per_instance"] and attempts < CONFIG["max_attempts_per_instance"]:
        order = list(instance["group_ids"]) if attempts == 0 else [int(g) for g in rng.permutation(instance["group_ids"])]
        attempts += 1
        if tuple(order) in seen:
            duplicates += 1
            continue
        seen.add(tuple(order))
        started = perf_counter()
        ms, oi, frame = hnfsm_decode(instance, order, return_schedule=True)
        decode_seconds = perf_counter() - started
        if ms >= INFEASIBLE or frame is None:
            failed.append({"attempt": attempts, "order": order, "hnfsm_seconds": decode_seconds})
            continue
        try:
            _, result, record = audit_schedule(instance, path, frame,
                enumerate_all=len(records) in CONFIG["oracle_sample_indices"])
        except (ValueError, RuntimeError) as exc:
            invalid.append({"attempt": attempts, "order": order, "error": str(exc)})
            continue
        record.update({"sample_index": len(records), "attempt": attempts, "order": order,
                       "hnfsm_seconds": decode_seconds})
        if not records:
            save_csv(out / f"{name.lower()}-natural-retimed-schedule.csv", schedule_for_export(result.schedule))
        records.append(record)
        if len(records) % 20 == 0:
            print(f"{name} {len(records)}/100, decoder failures={len(failed)}, invalid={len(invalid)}", flush=True)
    summary = aggregate(records)
    summary.update({"instance_seed": instance_seed, "attempts": attempts, "duplicate_orders": duplicates,
                    "decoder_failures": len(failed), "invalid_schedules": len(invalid),
                    "decoder_seconds_including_failures": sum(r["hnfsm_seconds"] for r in records + failed),
                    "target_reached": len(records) == CONFIG["feasible_schedules_per_instance"]})
    save_json(out / f"{name.lower()}-details.json", {"config": CONFIG, "records": records,
              "decoder_failures": failed, "invalid_schedules": invalid})
    save_csv(out / f"{name.lower()}-metrics.csv", pd.DataFrame([{k: v for k, v in r.items()
              if k not in ("order", "oracle")} for r in records]))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("current", "legacy", "all"), default=CONFIG["scope"])
    parser.add_argument("--legacy-source", default=CONFIG["legacy_source"])
    parser.add_argument("--output-prefix", default=CONFIG["output_prefix"])
    parser.add_argument("--skip-legacy-rerun", action="store_true", help="validate the 66 schedules without executing the old scripts; recorded explicitly")
    args = parser.parse_args()
    CONFIG["scope"] = args.scope
    CONFIG["legacy_source"] = args.legacy_source
    source = REPO_ROOT / args.legacy_source
    CONFIG["legacy_pilot"] = str(Path(args.legacy_source) / "pilot/optimization_pilot")
    CONFIG["output_prefix"] = args.output_prefix
    CONFIG["rerun_legacy_scripts"] = not args.skip_legacy_rerun
    evidence = evidence_preflight(source) if args.scope in ("legacy", "all") else None
    random.seed(CONFIG["seed"])
    np.random.seed(CONFIG["seed"])
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = RESULTS / f"{CONFIG['output_prefix']}-{run_id}"
    out.mkdir(parents=True, exist_ok=False)
    summary = {"config": CONFIG, "requested_scope": args.scope, "results": {}, "failures": [],
               "legacy": {"status": "not_requested", "schedules": 0}, "evidence": evidence}
    code = [REPO_ROOT / "src/bakery/retiming.py", REPO_ROOT / "src/bakery/retiming_audit.py",
            REPO_ROOT / "tests/test_retiming.py", Path(__file__).resolve()]
    summary["code_fingerprints"] = [fingerprint(path) for path in code]
    summary["data_fingerprints"] = [fingerprint(processed_json(name)) for name in CONFIG["instances"]]
    git_status = subprocess.run(["git", "status", "--porcelain=v1"], capture_output=True, text=True)
    summary["git_status"] = git_status.stdout.splitlines() if git_status.returncode == 0 else None
    summary["git_available"] = git_status.returncode == 0
    if args.scope in ("legacy", "all"):
        summary["legacy_source_fingerprints"] = [fingerprint(p) for p in sorted(source.glob("*.zip"))]
        if CONFIG["rerun_legacy_scripts"]:
            summary["legacy_rerun"] = rerun_legacy(source, run_id)
        summary["legacy"] = validate_legacy(out, source)
    if args.scope in ("current", "all"):
        for offset, name in enumerate(CONFIG["instances"]):
            summary["results"][name] = validate_new(name, CONFIG["seed"] + offset, out)
    all_summaries = list(summary["results"].values()) + ([summary["legacy"]] if "validated_schedules" in summary["legacy"] else [])
    for item in all_summaries:
        if any(item[key] for key in ("checker_violations", "invariant_violations", "pareto_violations", "boundary_oidt_mismatches")):
            summary["failures"].append("schedule audit violation")
        if item["oracle_errors"] or any(item["oracle_totals"][k] for k in (
                "feasible_set_mismatches", "group_optimum_mismatches", "deterministic_start_mismatches", "global_move_mismatches")):
            summary["failures"].append("independent oracle mismatch")
        if item.get("invalid_schedules", 0) or not item.get("target_reached", True) or item.get("original_objective_errors"):
            summary["failures"].append("invalid/incomplete schedules or legacy discrepancy")
    if "legacy_rerun" in summary:
        rerun = summary["legacy_rerun"]
        if not all(rerun["exact_saved_result_matches"].values()) or any(r["objective_mismatches"] for r in rerun["boundary"].values()):
            summary["failures"].append("legacy rerun discrepancy")
    summary["requested_scope_complete"] = not summary["failures"]
    save_json(out / "summary.json", summary)
    print(json.dumps({"output": str(out), "requested_scope": args.scope,
                      "legacy_status": "validated" if args.scope in ("legacy", "all") else "NOT REQUESTED: historical 66 were not checked",
                      "failures": summary["failures"],
                      "new": {name: {k: v for k, v in s.items() if k not in ("oracle_errors",)}
                              for name, s in summary["results"].items()}}, indent=2), flush=True)
    if summary["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
