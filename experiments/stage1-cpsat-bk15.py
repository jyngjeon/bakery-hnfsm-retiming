"""CP-SAT min-makespan reference for BK15 (notebook cell 8).

Usage: uv run python experiments/stage1-cpsat-bk15.py
Output: results/stage1-cpsat-bk15/{summary.json, schedule.csv}
"""

from bakery.checker import format_report, verify_schedule
from bakery.cpsat import solve_min_makespan
from bakery.io import save_csv, save_json
from bakery.paths import processed_json, results_dir

CONFIG = {"instance": "BK15", "horizon": 1000, "time_limit": 30.0, "workers": 8, "seed": 0}

out = results_dir("stage1-cpsat-bk15")
path = processed_json(CONFIG["instance"])
res = solve_min_makespan(path, horizon=CONFIG["horizon"], time_limit=CONFIG["time_limit"],
                         workers=CONFIG["workers"], seed=CONFIG["seed"])
print(f"status={res['status']} elapsed={res['elapsed_s']:.2f}s")
payload = {"config": CONFIG, "status": res["status"], "elapsed_s": res["elapsed_s"]}

if "schedule" in res:
    report = verify_schedule(path, res["schedule"], reported_makespan=res["makespan"])
    print(format_report(report, "CP-SAT BK15"))
    print(f"min makespan={res['makespan']}, OIDT(union) of that schedule={res['oidt_union']} (not optimised)")
    save_csv(out / "schedule.csv", res["schedule"])
    payload.update({"makespan": res["makespan"], "oidt_union": res["oidt_union"],
                    "checker_valid": report["is_valid"]})

save_json(out / "summary.json", payload)
print(f"saved -> {out}")
