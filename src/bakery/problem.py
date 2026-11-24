"""jMetalPy problem wrapper: real vector -> SPV -> HNFSM decoder -> (makespan, OIDT).

Ported from the original stage-1 notebook (cell 23); the incomplete wrapper of
cell 20 was dropped.
"""

from __future__ import annotations

from pathlib import Path

from jmetal.core.problem import FloatProblem
from jmetal.core.solution import FloatSolution

from bakery.decoder import hnfsm_decode, load_hnfsm_instance, spv_to_group_order


class BakerySchedulingProblem(FloatProblem):
    def __init__(self, json_path: str | Path):
        super().__init__()
        self.inst = load_hnfsm_instance(json_path)
        n = len(self.inst["group_ids"])
        self.lower_bound = [0.0] * n
        self.upper_bound = [1.0] * n
        self.obj_directions = [self.MINIMIZE, self.MINIMIZE]
        self.obj_labels = ["Makespan", "OIDT"]
        self.eval_count = 0

    def number_of_variables(self) -> int:
        return len(self.lower_bound)

    def number_of_objectives(self) -> int:
        return 2

    def number_of_constraints(self) -> int:
        return 0

    def decode(self, variables):
        """Group order for a real vector."""
        return spv_to_group_order(variables, self.inst["group_ids"])

    def evaluate(self, solution: FloatSolution) -> FloatSolution:
        ms, oidt, _ = hnfsm_decode(self.inst, self.decode(solution.variables))
        solution.objectives[0] = float(ms)
        solution.objectives[1] = float(oidt)
        self.eval_count += 1
        return solution

    def name(self) -> str:
        return "BakeryHNFSM"
