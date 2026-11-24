"""Demo: 100-step swap local search on BK15 (notebook cell 17). Not an experiment.

Usage: uv run python experiments/stage1-local-search-demo.py
Output: results/stage1-local-search-demo/summary.json
"""

import numpy as np

from bakery.decoder import hnfsm_decode, load_hnfsm_instance, spv_to_group_order
from bakery.io import save_json
from bakery.paths import processed_json, results_dir

CONFIG = {"instance": "BK15", "steps": 100, "seed": 42}

inst = load_hnfsm_instance(processed_json(CONFIG["instance"]))
n = len(inst["group_ids"])
rng = np.random.default_rng(CONFIG["seed"])

x_cur = rng.uniform(0.0, 1.0, size=n)
ms_cur, oidt_cur, _ = hnfsm_decode(inst, spv_to_group_order(x_cur, inst["group_ids"]))
start = (ms_cur, oidt_cur)
history = [{"step": 0, "makespan": ms_cur, "oidt": oidt_cur}]

for step in range(1, CONFIG["steps"] + 1):
    x_new = x_cur.copy()
    i, j = rng.choice(n, size=2, replace=False)
    x_new[i], x_new[j] = x_new[j], x_new[i]
    ms_new, oidt_new, _ = hnfsm_decode(inst, spv_to_group_order(x_new, inst["group_ids"]))
    if ms_new <= ms_cur and oidt_new <= oidt_cur and (ms_new < ms_cur or oidt_new < oidt_cur):
        x_cur, ms_cur, oidt_cur = x_new, ms_new, oidt_new
        history.append({"step": step, "makespan": ms_cur, "oidt": oidt_cur})

print(f"start={start} -> after {CONFIG['steps']} steps: makespan={ms_cur}, OIDT={oidt_cur}")
out = results_dir("stage1-local-search-demo")
save_json(out / "summary.json", {"config": CONFIG, "start": start,
                                 "final": {"makespan": ms_cur, "oidt": oidt_cur,
                                           "order": spv_to_group_order(x_cur, inst["group_ids"])},
                                 "improvements": history})
print(f"saved -> {out}")
