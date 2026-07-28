"""
alns/bayassign.py -- bay-assignment MIP (portfolio strategy "A-Assign").

Solves the ASSIGNMENT layer exactly: which bay each block goes to, minimizing
w2*Z2 (unfloored max normalized workload imbalance -- exact at assignment
level) + w3*Z3 (preference penalty), under a fluid capacity surrogate per bay
(sum area_i*proc_i <= CAP_FRAC * W_j*H_j*max_due).  Z1 is NOT modeled -- the
map is consumed by the greedy as a preference REWRITE (steering, not a hard
constraint), and the portfolio's best-verified-TRUE-total selection keeps the
whole thing no-loss: if following the map hurts obj1 more than it saves
Z2/Z3, another strategy wins the seed.

Targets: the easy-half obj2 outliers (prob_29 ~2.5-8.5k, prob_10/17 ~6-7k,
prob_30 ~4-6k) where obj1 is ~0 either way and ranking is decided by Z2/Z3.
"""

import math
import os

try:
    from ortools.sat.python import cp_model
    _HAS = True
except Exception:  # noqa: BLE001
    _HAS = False

_SCALE = 1000
_CAP_FRAC = float(os.environ.get("OGC_BA_CAP", "0.8"))
_STEER = int(os.environ.get("OGC_BA_STEER", "100"))  # pref boost for mapped bay


def _poly_area(pts):
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _block_area(blk):
    """Footprint approx: max layer area of orientation 0."""
    try:
        return max(_poly_area(l) for l in blk["shape"][0]["layers"])
    except Exception:  # noqa: BLE001
        return 1.0


def solve_map(prob_info, time_cap=2.0):
    """Return {block_id: bay_id} or None (failure / trivial instance)."""
    if not _HAS:
        return None
    blocks = prob_info["blocks"]
    bays = prob_info["bays"]
    n, m_n = len(blocks), len(bays)
    if m_n < 2:
        return None
    w = prob_info.get("weights", {})
    w2 = int(round(w.get("w2", 1.0)))
    w3 = int(round(w.get("w3", 0.0)))

    areas = [b["width"] * b["height"] for b in bays]
    avg = sum(areas) / m_n
    u_int = [max(1, int(round(avg / a * _SCALE))) for a in areas]
    max_due = max(b["due_date"] for b in blocks)
    caps = [int(_CAP_FRAC * a * max_due) for a in areas]
    vols = [max(1, int(round(_block_area(b) * b["processing_time"])))
            for b in blocks]

    m = cp_model.CpModel()
    x = [[m.NewBoolVar(f"x{i}_{j}") for j in range(m_n)] for i in range(n)]
    for i in range(n):
        m.AddExactlyOne(x[i])
    for j in range(m_n):
        m.Add(sum(vols[i] * x[i][j] for i in range(n)) <= caps[j])

    tot_wl = sum(int(b.get("workload", 0)) for b in blocks)
    ub = max(u_int) * max(1, tot_wl)
    lw = [m.NewIntVar(0, max(1, ub), f"L{j}") for j in range(m_n)]
    for j in range(m_n):
        m.Add(lw[j] == sum(u_int[j] * int(blocks[i].get("workload", 0)) * x[i][j]
                           for i in range(n)))
    imb = m.NewIntVar(0, max(1, ub), "imb")
    for j in range(m_n):
        for k in range(m_n):
            if j != k:
                m.Add(imb >= lw[j] - lw[k])

    pref_terms = []
    for i, b in enumerate(blocks):
        prefs = b.get("bay_preferences", [0] * m_n)
        s_max = max(prefs)
        for j in range(m_n):
            pen = s_max - prefs[j]
            if pen:
                pref_terms.append(pen * x[i][j])

    m.Minimize(w2 * imb + w3 * _SCALE * sum(pref_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.3, time_cap)
    solver.parameters.num_search_workers = 1
    st = solver.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    out = {}
    for i in range(n):
        for j in range(m_n):
            if solver.Value(x[i][j]):
                out[i] = j
                break
    return out


def rewrite_prefs(prob_info, amap):
    """Shallow-copied prob_info whose bay_preferences steer the greedy toward
    the map: mapped bay gets Smax + _STEER (strictly first in preference-desc
    bay order, and w3*(_STEER..) dominates marginal tie-breaks).  True-weight
    verification happens in the parent against the ORIGINAL prob_info."""
    p2 = dict(prob_info)
    blocks2 = []
    for i, b in enumerate(prob_info["blocks"]):
        if i in amap:
            b2 = dict(b)
            prefs = list(b.get("bay_preferences", []))
            if prefs:
                prefs[amap[i]] = max(prefs) + _STEER
                b2["bay_preferences"] = prefs
            blocks2.append(b2)
        else:
            blocks2.append(b)
    p2["blocks"] = blocks2
    return p2
