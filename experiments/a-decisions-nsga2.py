"""NSGA-II (Table 5 settings) under modelling variants for docs/TODO.md A1, A3, A4, A5.

One factor is changed at a time from the base setting (plus three combinations)
(OIDT union, oven first-fit, co-bake "any", batches expanded):
- A1 oidt:      "m2" (paper M2 as written, optimised instead of union)
- A3 oven_rule: "used_first", "min_idle"
- A4 cobake:    "same_start", "same_start_end"
- A5 batch:     "no_batch", "g18_once" (BK50 only)

Each run: population 50, SBX rate 1 (distribution index 20, jMetalPy default;
Table 5 gives none), polynomial mutation 1/NG (index 20), binary tournament,
300 generations = 15,000 evaluations. Infeasible orders keep (1e9, 1e9) (A2 open).
The pooled front over seeds is compared with the paper's PF* (Fig. 7, p.9):
BK15 E1 ~ (471, 93), E2 ~ (480, 72); BK50 E2 OIDT 1243, E1 makespan ~940-960.

Usage: uv run python experiments/a-decisions-nsga2.py [BK15|BK50]
Output: results/a-decisions-nsga2/summary-<inst>.json, fronts-<inst>.csv
"""

import random
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd
from jmetal.algorithm.multiobjective import NSGAII
from jmetal.operator.crossover import SBXCrossover
from jmetal.operator.mutation import PolynomialMutation
from jmetal.util.solution import get_non_dominated_solutions
from jmetal.util.termination_criterion import StoppingByEvaluations

from bakery.checker import verify_schedule
from bakery.decoder import INFEASIBLE, hnfsm_decode
from bakery.io import save_csv, save_json
from bakery.paths import results_dir
from bakery.problem import BakerySchedulingProblem
from bakery.variants import write_batch_variant

BASE = {"oidt": "union", "oven_rule": "first_fit", "cobake": "any", "batch": "expanded"}
VARIANTS = {
    "base": {},
    "A1-oidt-m2": {"oidt": "m2"},
    "A3-used-first": {"oven_rule": "used_first"},
    "A3-min-idle": {"oven_rule": "min_idle"},
    "A4-same-start": {"cobake": "same_start"},
    "A4-same-start-end": {"cobake": "same_start_end"},
    "A5-no-batch": {"batch": "no_batch"},
    "A5-g18-once": {"batch": "g18_once"},
    # combinations with the A3 rule that came closest to PF* in the one-factor runs
    "A3uf+A4sse": {"oven_rule": "used_first", "cobake": "same_start_end"},
    "A3uf+A5nb": {"oven_rule": "used_first", "batch": "no_batch"},
    "A3uf+A4sse+A5nb": {"oven_rule": "used_first", "cobake": "same_start_end", "batch": "no_batch"},
}
CONFIG = {
    "algorithm": "NSGA-II",
    "population_size": 50, "offspring_population_size": 50,
    "sbx_probability": 1.0, "sbx_distribution_index": 20,
    "mutation_probability": "1/NG", "mutation_distribution_index": 20,
    "selection": "binary tournament (jMetalPy default)",
    "generations": 300, "max_evaluations": 15000,
    "infeasible": "(1e9, 1e9) penalty",
    "BK15": {"seeds": list(range(1, 11)),
             "variants": [v for v in VARIANTS if v != "A5-g18-once"]},
    "BK50": {"seeds": [1, 2, 3],
             "variants": ["base", "A1-oidt-m2", "A3-used-first", "A3-min-idle",
                          "A4-same-start-end", "A5-no-batch", "A5-g18-once"]},
    "processes": 8,
}
PAPER = {"BK15": {"E1": (471, 93), "E2": (480, 72)},
         "BK50": {"E2_oidt": 1243, "E1_makespan": "940-960 (figure reading)"}}


class CountingProblem(BakerySchedulingProblem):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.infeasible_count = 0

    def evaluate(self, solution):
        solution = super().evaluate(solution)
        if solution.objectives[0] >= INFEASIBLE:
            self.infeasible_count += 1
        return solution


def run_one(args):
    inst, vname, seed, path = args
    opts = {**BASE, **VARIANTS[vname]}
    decode_kw = {k: opts[k] for k in ("oidt", "oven_rule", "cobake")}
    random.seed(seed)
    np.random.seed(seed)
    problem = CountingProblem(path, **decode_kw)
    algo = NSGAII(
        problem=problem,
        population_size=CONFIG["population_size"],
        offspring_population_size=CONFIG["offspring_population_size"],
        mutation=PolynomialMutation(probability=1.0 / problem.number_of_variables(),
                                    distribution_index=CONFIG["mutation_distribution_index"]),
        crossover=SBXCrossover(probability=CONFIG["sbx_probability"],
                               distribution_index=CONFIG["sbx_distribution_index"]),
        termination_criterion=StoppingByEvaluations(max_evaluations=CONFIG["max_evaluations"]),
    )
    t0 = time.time()
    algo.run()
    elapsed = time.time() - t0

    rows, seen = [], set()
    other = "m2" if opts["oidt"] == "union" else "union"
    for sol in get_non_dominated_solutions(algo.result()):
        ms, oi = int(sol.objectives[0]), int(sol.objectives[1])
        if ms >= INFEASIBLE or (ms, oi) in seen:
            continue
        seen.add((ms, oi))
        order = problem.decode(sol.variables)
        _, oi_other, sched = hnfsm_decode(problem.inst, order, return_schedule=True,
                                          **{**decode_kw, "oidt": other})
        rep = verify_schedule(path, sched, reported_makespan=ms)
        oi_union = oi if opts["oidt"] == "union" else oi_other
        rows.append({"instance": inst, "variant": vname, "seed": seed, "makespan": ms,
                     "oidt_union": oi_union, "oidt_m2": oi if opts["oidt"] == "m2" else oi_other,
                     "checker_valid": rep["is_valid"] and rep["oidt"] == oi_union,
                     "order": " ".join(map(str, order))})
    return {"variant": vname, "seed": seed, "elapsed_s": round(elapsed, 1),
            "evaluations": problem.eval_count, "infeasible": problem.infeasible_count,
            "rows": rows}


def pareto(points):
    pts = sorted(set(points))
    front, best = [], None
    for a, b in pts:
        if best is None or b < best:
            front.append((a, b))
            best = b
    return front


if __name__ == "__main__":
    inst = sys.argv[1] if len(sys.argv) > 1 else "BK15"
    icfg = CONFIG[inst]
    out = results_dir("a-decisions-nsga2")
    paths = {v: write_batch_variant(inst, {**BASE, **VARIANTS[v]}["batch"], out) for v in icfg["variants"]}
    jobs = [(inst, v, s, paths[v]) for v in icfg["variants"] for s in icfg["seeds"]]
    with Pool(CONFIG["processes"]) as pool:
        runs = pool.map(run_one, jobs)

    all_rows = [r for run in runs for r in run["rows"]]
    df = pd.DataFrame(all_rows)
    summary = []
    for v in icfg["variants"]:
        sub = df[df["variant"] == v]
        rs = [r for r in runs if r["variant"] == v]
        key = "oidt_m2" if VARIANTS[v].get("oidt") == "m2" else "oidt_union"
        front = pareto(zip(sub["makespan"], sub[key]))
        summary.append({
            "variant": v, "options": {**BASE, **VARIANTS[v]}, "objective_oidt": key,
            "pooled_front": front,
            "min_makespan": int(sub["makespan"].min()), "min_oidt": int(sub[key].min()),
            "per_seed_min_makespan": [int(df[(df.variant == v) & (df.seed == s)]["makespan"].min())
                                      for s in icfg["seeds"]],
            "per_seed_min_oidt": [int(df[(df.variant == v) & (df.seed == s)][key].min())
                                  for s in icfg["seeds"]],
            "infeasible_rate": round(sum(r["infeasible"] for r in rs) / sum(r["evaluations"] for r in rs), 4),
            "mean_elapsed_s": round(np.mean([r["elapsed_s"] for r in rs]), 1),
            "all_front_checker_valid": bool(sub["checker_valid"].all()),
        })
        print(f"{v:20s} front={front} infeasible={summary[-1]['infeasible_rate']} "
              f"valid={summary[-1]['all_front_checker_valid']}", flush=True)

    save_csv(out / f"fronts-{inst.lower()}.csv", df)
    save_json(out / f"summary-{inst.lower()}.json",
              {"instance": inst, "config": CONFIG, "paper_pf_star": PAPER[inst],
               "variants": summary,
               "runs": [{k: r[k] for k in ("variant", "seed", "elapsed_s", "evaluations", "infeasible")}
                        for r in runs]})
    print(f"saved -> {out}")
