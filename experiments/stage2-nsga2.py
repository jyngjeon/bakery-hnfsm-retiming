"""Stage 2/3: NSGA-II with the Table 5 settings on BK15 and BK50 (docs/TODO.md B3, R1, R2).

Settings (paper Table 5, p.20; decisions in docs/PROGRESS.md section 5):
- population 50, SBX crossover rate 1, polynomial mutation rate 1/NG, binary tournament
- distribution index 20 for SBX and polynomial mutation (jMetalPy default; not in Table 5)
- iteration = generation (A6). One generation = 50 evaluations and the initial
  population counts as generation 1, so 300 generations = 15,000 evaluations
  (same budget as experiments/a-decisions-nsga2.py).
- snapshots of the population's nondominated front at 50/100/200/300 generations.
  A 50-generation run with the same seed is the 50-generation snapshot, so seed 1
  doubles as R1 (one run per iteration size, as in the paper) and seeds 1-10 are R2.
- OIDT: union definition (A1) is the objective; the paper's M2 value is reported too.
- oven first-fit (A3), co-bake any overlap (A4), batches expanded (A5),
  infeasible orders -> (1e9, 1e9) and the infeasible rate is reported (A2).

Indicators (paper Eqs. 2-6, bakery.metrics) per (seed, iteration) front against a
provisional PF* = nondominated union of every NSGA-II front of the instance
(all seeds and snapshots). The paper's PF* pools five algorithms, so these
numbers are recomputed once the other algorithms are connected.
HV / DPF use objectives scaled to [0, 1] by the min/max over all those fronts
and RV = (1.1, 1.1) (A6).

Usage: uv run python experiments/stage2-nsga2.py [BK15] [BK50]
Output: results/stage2-nsga2/{summary.json, fronts.csv, metrics.csv, trace.csv}
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
from bakery.metrics import dpf, msf, normalise, pareto_front, pds, rha
from bakery.paper_ref import PAPER
from bakery.paths import processed_json, results_dir
from bakery.problem import BakerySchedulingProblem

CONFIG = {
    "algorithm": "NSGA-II (jMetalPy 1.9.0)",
    "instances": ["BK15", "BK50"],
    "data_files": {"BK15": "data/processed/bk15-clean.json", "BK50": "data/processed/bk50-clean.json"},
    "seeds": list(range(1, 11)),
    "population_size": 50, "offspring_population_size": 50,
    "crossover": "SBX", "sbx_probability": 1.0, "sbx_distribution_index": 20,
    "mutation": "polynomial", "mutation_probability": "1/NG", "mutation_distribution_index": 20,
    "selection": "binary tournament (jMetalPy NSGAII default)",
    "iterations": [50, 100, 200, 300],
    "iteration_definition": "generation; evaluations = 50 * iteration (initial population = generation 1)",
    "max_evaluations": 15000,
    "decoder": {"oidt": "union", "oven_rule": "first_fit", "cobake": "any", "batch": "expanded"},
    "oidt_reported": ["union (objective)", "m2 (paper M2 as written)"],
    "infeasible": "(1e9, 1e9) penalty",
    "pf_star": "provisional: nondominated union of all NSGA-II fronts (seeds x iterations) per instance",
    "normalisation": "min/max of each objective over all NSGA-II fronts per instance",
    "hv_reference_vector": [1.1, 1.1],
    "processes": 8,
}

class SnapshotNSGAII(NSGAII):
    """NSGA-II that records the nondominated front at given generations and a per-generation trace."""

    def __init__(self, *a, snapshot_generations=(), **kw):
        super().__init__(*a, **kw)
        self.snap_evals = {g * self.population_size: g for g in snapshot_generations}
        self.snapshots, self.trace = {}, []
        self.t0 = None

    def init_progress(self):
        self.t0 = time.time()
        super().init_progress()
        self._record()

    def update_progress(self):
        super().update_progress()
        self._record()

    def _record(self):
        objs = np.array([s.objectives for s in self.solutions])
        feas = objs[objs[:, 0] < INFEASIBLE]
        gen = self.evaluations // self.population_size
        self.trace.append({"generation": gen, "evaluations": self.evaluations,
                           "elapsed_s": round(time.time() - self.t0, 2),
                           "min_makespan": float(feas[:, 0].min()) if len(feas) else None,
                           "min_oidt": float(feas[:, 1].min()) if len(feas) else None})
        if self.evaluations in self.snap_evals:
            front = [s for s in get_non_dominated_solutions(self.solutions) if s.objectives[0] < INFEASIBLE]
            self.snapshots[self.snap_evals[self.evaluations]] = {
                "elapsed_s": time.time() - self.t0,
                "evaluations": self.evaluations,
                "solutions": [(list(s.variables), s.objectives[0], s.objectives[1]) for s in front],
            }


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
    inst, seed = args
    random.seed(seed)
    np.random.seed(seed)
    path = processed_json(inst)
    problem = CountingProblem(path)  # decoder defaults = CONFIG["decoder"]
    algo = SnapshotNSGAII(
        problem=problem,
        population_size=CONFIG["population_size"],
        offspring_population_size=CONFIG["offspring_population_size"],
        mutation=PolynomialMutation(probability=1.0 / problem.number_of_variables(),
                                    distribution_index=CONFIG["mutation_distribution_index"]),
        crossover=SBXCrossover(probability=CONFIG["sbx_probability"],
                               distribution_index=CONFIG["sbx_distribution_index"]),
        termination_criterion=StoppingByEvaluations(max_evaluations=CONFIG["max_evaluations"]),
        snapshot_generations=CONFIG["iterations"],
    )
    algo.run()

    rows = []
    for it, snap in sorted(algo.snapshots.items()):
        seen = set()
        for x, ms, oi in snap["solutions"]:
            ms, oi = int(ms), int(oi)
            if (ms, oi) in seen:
                continue
            seen.add((ms, oi))
            order = problem.decode(x)
            _, oi_m2, sched = hnfsm_decode(problem.inst, order, return_schedule=True, oidt="m2")
            rep = verify_schedule(path, sched, reported_makespan=ms)
            rows.append({"instance": inst, "seed": seed, "iteration": it, "makespan": ms,
                         "oidt": oi, "oidt_m2": oi_m2,
                         "checker_valid": bool(rep["is_valid"] and rep["oidt"] == oi),
                         "order": " ".join(map(str, order))})
    snaps = [{"instance": inst, "seed": seed, "iteration": it, "evaluations": s["evaluations"],
              "elapsed_s": round(s["elapsed_s"], 1)} for it, s in sorted(algo.snapshots.items())]
    trace = [{"instance": inst, "seed": seed, **t} for t in algo.trace]
    print(f"{inst} seed {seed}: {snaps[-1]['elapsed_s']} s, "
          f"front@300 {sorted({(r['makespan'], r['oidt']) for r in rows if r['iteration'] == 300})}",
          flush=True)
    return {"instance": inst, "seed": seed, "evaluations": problem.eval_count,
            "infeasible": problem.infeasible_count, "rows": rows, "snapshots": snaps, "trace": trace}


def indicators(fronts: pd.DataFrame, inst: str) -> tuple[pd.DataFrame, dict]:
    sub = fronts[fronts.instance == inst]
    pf_star = pareto_front(zip(sub.makespan, sub.oidt))
    lo = [sub.makespan.min(), sub.oidt.min()]
    hi = [sub.makespan.max(), sub.oidt.max()]
    star_n = normalise(pf_star, lo, hi)
    ref = CONFIG["hv_reference_vector"]
    rows = []
    for (seed, it), g in sub.groupby(["seed", "iteration"]):
        pf = pareto_front(zip(g.makespan, g.oidt))
        pf_n = normalise(pf, lo, hi)
        rows.append({"instance": inst, "seed": seed, "iteration": it, "front_size": len(pf),
                     "min_makespan": pf[0][0], "min_oidt": pf[-1][1],
                     "n_in_pf_star": len(set(pf) & set(pf_star)),
                     "PDS": pds(pf, pf_star), "MSF": msf(pf, pf_star),
                     "DPF_norm": dpf(pf_n, star_n), "DPF_raw": dpf(pf, pf_star),
                     "RHA": rha(pf_n, star_n, ref)})
    info = {"pf_star": pf_star, "normalisation_lower": lo, "normalisation_upper": hi}
    return pd.DataFrame(rows), info


if __name__ == "__main__":
    insts = sys.argv[1:] or CONFIG["instances"]
    out = results_dir("stage2-nsga2")
    # BK50 jobs first: they are ~15x slower
    jobs = [(i, s) for i in sorted(insts, reverse=True) for s in CONFIG["seeds"]]
    with Pool(CONFIG["processes"]) as pool:
        runs = pool.map(run_one, jobs, chunksize=1)

    fronts = pd.DataFrame([r for run in runs for r in run["rows"]])
    trace = pd.DataFrame([t for run in runs for t in run["trace"]])
    snaps = pd.DataFrame([s for run in runs for s in run["snapshots"]])

    metric_tables, per_inst = [], {}
    for inst in insts:
        m, info = indicators(fronts, inst)
        m = m.merge(snaps, on=["instance", "seed", "iteration"])
        metric_tables.append(m)
        rs = [r for r in runs if r["instance"] == inst]
        sub = fronts[fronts.instance == inst]
        pooled300 = pareto_front(zip(sub[sub.iteration == 300].makespan, sub[sub.iteration == 300].oidt))
        per_inst[inst] = {
            **info,
            "pooled_front_300": pooled300,
            "infeasible_rate": sum(r["infeasible"] for r in rs) / sum(r["evaluations"] for r in rs),
            "evaluations_per_run": sorted({r["evaluations"] for r in rs}),
            "all_fronts_checker_valid": bool(sub.checker_valid.all()),
            "metrics_by_iteration": {
                int(it): {c: {"seed1": float(g[g.seed == 1][c].iloc[0]), "mean": float(g[c].mean()),
                              "median": float(g[c].median()), "std": float(g[c].std())}
                          for c in ("PDS", "MSF", "DPF_norm", "DPF_raw", "RHA", "front_size",
                                    "min_makespan", "min_oidt", "elapsed_s")}
                for it, g in m.groupby("iteration")},
            "paper": PAPER[inst],
        }
        print(f"{inst}: PF*={info['pf_star']} valid={per_inst[inst]['all_fronts_checker_valid']} "
              f"infeasible={per_inst[inst]['infeasible_rate']:.5f}", flush=True)

    metrics = pd.concat(metric_tables, ignore_index=True)
    save_csv(out / "fronts.csv", fronts)
    save_csv(out / "metrics.csv", metrics)
    save_csv(out / "trace.csv", trace)
    save_json(out / "summary.json", {"config": CONFIG, "instances": per_inst})
    print(f"saved -> {out}")
