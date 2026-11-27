"""Front quality indicators of the paper (p.8-9, Eqs. 2-6) for two minimised objectives.

All functions take fronts as sequences of (makespan, OIDT) pairs.

- pareto_front: nondominated, deduplicated, sorted by the first objective
- pds   (Eq. 2): Pareto domination strength, lower is better
- msf   (Eq. 3): maximum spread of solutions, implemented as printed in the paper
                 (f from PF*, F from the candidate PF, denominator F_max - F_min)
- dpf   (Eq. 4): mean distance from each PF* point to the closest PF point
- hv2d  (Eq. 5): hypervolume (area) w.r.t. a reference vector RV
- rha   (Eq. 6): HV(PF) / HV(PF*) * 100

Objective-space normalisation for HV / DPF follows docs/TODO.md A6: objectives
are scaled to [0, 1] with given bounds and RV = (1.1, 1.1).
"""

from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np

Point = tuple[float, float]


def pareto_front(points: Iterable[Sequence[float]]) -> list[Point]:
    """Nondominated subset (minimisation), duplicates removed, sorted by objective 1."""
    pts = sorted({(float(a), float(b)) for a, b in points})
    front: list[Point] = []
    best = None
    for a, b in pts:
        if best is None or b < best:
            front.append((a, b))
            best = b
    return front


def pds(pf: Sequence[Point], pf_star: Sequence[Point]) -> float:
    """Eq. 2: (|PF \\ PF*| - |PF ∩ PF*|) / (|PF| * |PF*|)."""
    star = {tuple(map(float, p)) for p in pf_star}
    cand = {tuple(map(float, p)) for p in pf}
    inside = len(cand & star)
    return (len(cand) - 2 * inside) / (len(cand) * len(star))


def msf(pf: Sequence[Point], pf_star: Sequence[Point]) -> float:
    """Eq. 3 as printed. A term whose candidate range is zero (single point) counts as 0."""
    pf, star = np.asarray(pf, float), np.asarray(pf_star, float)
    terms = []
    for q in range(pf.shape[1]):
        f_max, f_min = star[:, q].max(), star[:, q].min()
        F_max, F_min = pf[:, q].max(), pf[:, q].min()
        if F_max == F_min:
            terms.append(0.0)
            continue
        terms.append(((min(f_max, F_max) - max(f_min, F_min)) / (F_max - F_min)) ** 2)
    return float(np.sqrt(np.mean(terms)))


def normalise(points: Sequence[Point], lower: Sequence[float], upper: Sequence[float]) -> np.ndarray:
    lo, hi = np.asarray(lower, float), np.asarray(upper, float)
    span = np.where(hi > lo, hi - lo, 1.0)
    return (np.asarray(points, float) - lo) / span


def dpf(pf: Sequence[Point], pf_star: Sequence[Point]) -> float:
    """Eq. 4: mean over a in PF* of min_b Ed(a, b). Pass normalised points if wanted."""
    pf, star = np.asarray(pf, float), np.asarray(pf_star, float)
    d = np.linalg.norm(star[:, None, :] - pf[None, :, :], axis=2)
    return float(d.min(axis=1).mean())


def hv2d(points: Sequence[Point], ref: Sequence[float]) -> float:
    """Eq. 5 for two minimised objectives; points not dominating ref contribute nothing."""
    front = [p for p in pareto_front(points) if p[0] < ref[0] and p[1] < ref[1]]
    area, prev_b = 0.0, float(ref[1])
    for a, b in front:  # sorted by a ascending, b descending
        area += (ref[0] - a) * (prev_b - b)
        prev_b = b
    return area


def rha(pf: Sequence[Point], pf_star: Sequence[Point], ref: Sequence[float]) -> float:
    """Eq. 6 in percent."""
    return 100.0 * hv2d(pf, ref) / hv2d(pf_star, ref)
