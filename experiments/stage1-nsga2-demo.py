"""Demo: NSGA-II <-> HNFSM wiring on BK15 with 200 evaluations (notebook cell 23).

These are NOT the paper's Table 5 settings (see docs/TODO.md B3); the demo only
checks that the pipeline runs. A seed is now fixed for reproducibility.

Usage: uv run python experiments/stage1-nsga2-demo.py
Output: results/stage1-nsga2-demo/{summary.json, best-schedule.csv}
"""

import random

import numpy as np
from jmetal.algorithm.multiobjective import NSGAII
from jmetal.operator.crossover import SBXCrossover
from jmetal.operator.mutation import PolynomialMutation
from jmetal.util.solution import get_non_dominated_solutions
from jmetal.util.termination_criterion import StoppingByEvaluations

from bakery.checker import format_report, verify_schedule
from bakery.decoder import INFEASIBLE, hnfsm_decode
from bakery.io import save_csv, save_json
from bakery.paths import processed_json, results_dir
from bakery.problem import BakerySchedulingProblem

CONFIG = {"instance": "BK15", "population_size": 20, "offspring_population_size": 20,
          "sbx_probability": 0.9, "sbx_distribution_index": 20,
          "mutation_distribution_index": 20, "max_evaluations": 200, "seed": 2001}

random.seed(CONFIG["seed"])
np.random.seed(CONFIG["seed"])

path = processed_json(CONFIG["instance"])
problem = BakerySchedulingProblem(path)
algorithm = NSGAII(
    problem=problem,
    population_size=CONFIG["population_size"],
    offspring_population_size=CONFIG["offspring_population_size"],
    mutation=PolynomialMutation(probability=1.0 / problem.number_of_variables(),
                                distribution_index=CONFIG["mutation_distribution_index"]),
    crossover=SBXCrossover(probability=CONFIG["sbx_probability"],
                           distribution_index=CONFIG["sbx_distribution_index"]),
    termination_criterion=StoppingByEvaluations(max_evaluations=CONFIG["max_evaluations"]),
)
algorithm.run()

front = {}
for sol in get_non_dominated_solutions(algorithm.result()):
    ms, oidt = int(sol.objectives[0]), int(sol.objectives[1])
    if ms < INFEASIBLE and (ms, oidt) not in front:
        front[(ms, oidt)] = problem.decode(sol.variables)
pairs = sorted(front)
print(f"front ({len(pairs)}): {pairs}")

out = results_dir("stage1-nsga2-demo")
best_order = front[pairs[0]]
ms, oidt, sched = hnfsm_decode(problem.inst, best_order, return_schedule=True)
report = verify_schedule(path, sched, reported_makespan=ms, reported_oidt=oidt)
print(format_report(report, "NSGA-II demo best-makespan solution"))
save_csv(out / "best-schedule.csv", sched)
save_json(out / "summary.json", {
    "config": CONFIG,
    "evaluations": problem.eval_count,
    "front": [{"makespan": a, "oidt": b, "order": front[(a, b)]} for a, b in pairs],
    "best_checker_valid": report["is_valid"],
})
print(f"saved -> {out}")
