"""Stage 1 baseline: natural order (1..NG) and one random SPV vector per instance,
decoded with the HNFSM decoder and verified by the independent checker.

Reproduces notebook cells 13 and 28 (rng seed 42, BK15 then BK50 from the same rng).
Usage: uv run python experiments/stage1-baseline.py
Output: results/stage1-baseline/{summary.json, <inst>-natural-schedule.csv}
"""

import numpy as np

from bakery.checker import format_report, verify_schedule
from bakery.decoder import hnfsm_decode, load_hnfsm_instance, spv_to_group_order
from bakery.io import save_csv, save_json
from bakery.paths import processed_json, results_dir

SEED = 42
out = results_dir("stage1-baseline")
rng = np.random.default_rng(SEED)
summary = {"config": {"seed": SEED, "oidt": "union"}, "instances": {}}

for name in ("BK15", "BK50"):
    path = processed_json(name)
    inst = load_hnfsm_instance(path)
    ms_nat, oidt_nat, df_nat = hnfsm_decode(inst, inst["group_ids"], return_schedule=True)
    report = verify_schedule(path, df_nat, reported_makespan=ms_nat, reported_oidt=oidt_nat)
    print(format_report(report, f"{name} natural order"))

    vec = rng.uniform(0.0, 1.0, size=len(inst["group_ids"]))
    order = spv_to_group_order(vec, inst["group_ids"])
    ms_rnd, oidt_rnd, _ = hnfsm_decode(inst, order)
    print(f"[{name}] natural -> makespan={ms_nat}, OIDT={oidt_nat} | random SPV -> makespan={ms_rnd}, OIDT={oidt_rnd}")

    save_csv(out / f"{name.lower()}-natural-schedule.csv", df_nat)
    summary["instances"][name] = {
        "n_groups": len(inst["group_ids"]),
        "natural": {"order": inst["group_ids"], "makespan": ms_nat, "oidt": oidt_nat,
                    "checker_valid": report["is_valid"], "oven_breakdown": report["oven_breakdown"]},
        "random_spv": {"order": order, "makespan": ms_rnd, "oidt": oidt_rnd},
    }

save_json(out / "summary.json", summary)
print(f"saved -> {out}")
