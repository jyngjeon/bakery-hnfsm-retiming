"""Hand-checked values for the paper's front indicators (Eqs. 2-6)."""

import pytest

from bakery.metrics import dpf, hv2d, msf, pareto_front, pds, rha


def test_pareto_front_filters_and_sorts():
    pts = [(3, 1), (1, 3), (2, 2), (2, 3), (1, 3), (4, 4)]
    assert pareto_front(pts) == [(1, 3), (2, 2), (3, 1)]


def test_pds_eq2():
    star = [(1, 3), (2, 2), (3, 1)]
    assert pds(star, star) == pytest.approx(-1 / 3)  # all in PF*: (0 - 3) / (3 * 3)
    assert pds([(5, 5)], star) == pytest.approx(1 / 3)  # none in PF*
    assert pds([(1, 3), (2, 4)], star) == 0.0


def test_msf_eq3():
    star = [(0, 10), (10, 0)]
    assert msf(star, star) == pytest.approx(1.0)
    # candidate covers half of PF* range in both objectives
    assert msf([(0, 5), (5, 0)], star) == pytest.approx(1.0)  # denominator is the candidate range
    assert msf([(0, 0)], star) == 0.0  # zero candidate range -> 0 term


def test_dpf_eq4():
    star = [(0, 1), (1, 0)]
    assert dpf(star, star) == 0.0
    assert dpf([(0, 0)], star) == pytest.approx(1.0)


def test_hv_and_rha():
    assert hv2d([(0, 1), (1, 0)], (2, 2)) == pytest.approx(3.0)
    assert hv2d([(3, 3)], (2, 2)) == 0.0  # beyond the reference vector
    assert rha([(1, 1)], [(0, 1), (1, 0)], (2, 2)) == pytest.approx(100 / 3)
