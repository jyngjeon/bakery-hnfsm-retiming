"""CP-SAT min-makespan under modelling variants for docs/TODO.md A4 and A5.

A4 (co-baking): same-group overlap on one compartment is "any" (current),
"same_start", or "same_start_end" (Fig. 3 form).
A5 (batches): "expanded" (current), "no_batch" (drop batch >= 2 groups),
"g18_once" (BK50 only: Dough C of Group 18 is not repeated in its batch-2 copy).

The question is which variant still reaches the paper's E1 makespan
(BK15 ~471, BK50 ~940-960, Fig. 7, p.9).

Usage: uv run python experiments/a-decisions-cpsat.py [BK15|BK50]
Output: results/a-decisions-cpsat/{summary-<inst>.json, instances/*.json}
"""

import json
import sys

from bakery.checker import verify_schedule
from bakery.cpsat import solve_min_makespan
from bakery.io import save_json
from bakery.paths import results_dir
from bakery.variants import write_batch_variant

CONFIG = {
    "BK15": {"horizon": 1000, "time_limit": 120.0, "workers": 8, "seed": 0,
             "cases": [("expanded", "any"), ("expanded", "same_start"),
                       ("expanded", "same_start_end"), ("no_batch", "any")]},
    "BK50": {"horizon": 2500, "time_limit": 600.0, "workers": 8, "seed": 0,
             "cases": [("expanded", "any"), ("g18_once", "any"), ("no_batch", "any")]},
}


def cobake_violations(sched, data, cobake):
    """Count same-group overlapping bakes that break the co-bake rule."""
    if cobake == "any":
        return 0
    oven_k = {m["k"] for m in data["machines"] if m["machine_type"] == "OVEN"}
    rows = sched[sched["assigned_k"].isin(oven_k)].to_dict("records")
    bad = 0
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if a["assigned_k"] == b["assigned_k"] and a["g"] == b["g"] \
                    and a["ST"] < b["CT"] and b["ST"] < a["CT"]:
                if a["ST"] != b["ST"] or (cobake == "same_start_end" and a["CT"] != b["CT"]):
                    bad += 1
    return bad


inst = sys.argv[1] if len(sys.argv) > 1 else "BK15"
cfg = CONFIG[inst]
out = results_dir("a-decisions-cpsat")
rows = []
for batch, cobake in cfg["cases"]:
    path = write_batch_variant(inst, batch, out)
    data = json.loads(path.read_text(encoding="utf-8"))
    res = solve_min_makespan(path, horizon=cfg["horizon"], time_limit=cfg["time_limit"],
                             workers=cfg["workers"], seed=cfg["seed"], cobake=cobake)
    row = {"batch": batch, "cobake": cobake, "groups": len({o["g"] for o in data["operations"]}),
           "operations": len(data["operations"]), "status": res["status"],
           "elapsed_s": round(res["elapsed_s"], 1)}
    if "schedule" in res:
        rep = verify_schedule(path, res["schedule"], reported_makespan=res["makespan"])
        row.update({"makespan": res["makespan"], "best_bound": res["best_bound"],
                    "oidt_union": res["oidt_union"], "oidt_m2": res["oidt_m2"],
                    "checker_valid": rep["is_valid"],
                    "cobake_violations": cobake_violations(res["schedule"], data, cobake)})
    print(row, flush=True)
    rows.append(row)

save_json(out / f"summary-{inst.lower()}.json", {"instance": inst, "config": cfg, "results": rows})
print(f"saved -> {out}")
