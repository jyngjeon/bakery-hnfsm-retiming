"""Reference values from Babor et al. (2023), paper/s41598-022-26866-9.pdf.

Numbers from tables and text are exact. Numbers marked "reading" were read off
the figure images (extracted at 300 dpi) and are approximate (about +-2 min on
makespan, +-10 min on OIDT for BK50, +-2 for BK15 / indicator values).
Iteration keys are generations (docs/TODO.md A6).
"""

PAPER = {
    "BK15": {
        # Fig. 7a (p.9), reading; E1/E2 deltas 9 min / 21 min are given in the text (p.9)
        "pf_star": [(471, 93), (478, 84), (480, 72)],
        "pf_star_size": 3,  # text, p.9
        # Table 4 (p.12), exact
        "nsga2_pds": {50: 0.33, 100: 0.33, 200: 0.20, 300: 0.00},
        "nsga2_msf": {50: 1.13, 100: 1.84, 200: 0.17, 300: 0.80},
        # Fig. 11a (p.12) and Fig. 12a (p.13), reading
        "nsga2_dpf": {50: 44, 100: 41, 200: 32, 300: 11},
        "nsga2_rha": {50: 67, 100: 71, 200: 82, 300: 97},
        # text p.14: computation time for 50 iterations, exact
        "nsga2_time_50_min": 13,
    },
    "BK50": {
        # Fig. 10a (p.11), reading; E2 OIDT 1243 and E1->E2 (+61, -1348) are exact (p.9)
        "pf_star": [(934, 2590), (940, 2050), (951, 1810), (952, 1765), (955, 1520),
                    (973, 1295), (995, 1243)],
        "pf_star_size": 7,  # text, p.9
        # Fig. 10a (p.11), NSGA-II candidate fronts per iteration, reading
        "nsga2_fronts": {
            50: [(955, 2555), (962, 2430), (976, 2375), (979, 2330), (980, 2295),
                 (1005, 2020), (1023, 1850)],
            100: [(948, 2350), (983, 1625)],
            200: [(943, 2160), (952, 2005), (959, 1650)],
            300: [(934, 2590), (940, 2050), (955, 1520), (973, 1295), (998, 1295)],
        },
        "nsga2_pds": {50: 0.10, 100: 0.14, 200: 0.05, 300: -0.09},
        "nsga2_msf": {50: 0.82, 100: 1.00, 200: 1.00, 300: 0.98},
        "nsga2_dpf": {50: 258, 100: 242, 200: 235, 300: 78},
        "nsga2_rha": {50: 66, 100: 78.5, 200: 79.5, 300: 97.5},
        "nsga2_time_50_min": 342,
    },
}
