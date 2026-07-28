"""
alns/nfp.py -- raster NFP candidate enumeration (v21 groundwork).

Enumerates ALL crane-entry-feasible integer reference positions for a block
in a bay with given residents, on a unit-cell raster.  This replaces the
contact-corner heuristic's 3-4 candidates with the full feasible region
(deep pockets included).

Accuracy contract: the raster is a PROPOSAL heuristic only.  False
positives cost a wasted exact check downstream (fno computes exact pairwise
flags per candidate; the greedy validates slots through utils); false
negatives only lose an opportunity.  Nothing here affects soundness.

Semantics rastered (mirrors utils):
  * coexistence: same-index layer interiors must not intersect;
  * crane ENTRY: the entering block's layer l1 must be collision-free vs
    residents' layers l2 >= l1  ==>  candidate layer l vs suffix-union
    occ_ge[l] of resident layers >= l.
Entry feasibility implies coexistence (l2 = l1 is included in the suffix).

Deps: numpy + scipy + shapely (all pinned in the server conda env; utils
itself imports shapely).  Any import/runtime failure -> callers fall back
to contact candidates.
"""

import math

try:
    import numpy as _np
    from scipy.signal import correlate as _corr
    import shapely as _sh
    from shapely.geometry import Polygon as _Poly, box as _box
    _OK = True
except Exception:  # noqa: BLE001
    _OK = False

_KERN = {}   # (bid, oi, layer) -> (bitmap[u,v], kx0, ky0)


def _raster_layer(poly_pts):
    """Rasterize one layer polygon (ref-relative coords) -> (bitmap, kx0, ky0).
    Cell (u, v) covers [kx0+u, kx0+u+1) x [ky0+v, ky0+v+1); marked iff the
    polygon intersects the cell box."""
    poly = _Poly(poly_pts)
    if not poly.is_valid:
        poly = poly.buffer(0)
    x0, y0, x1, y1 = poly.bounds
    kx0, ky0 = math.floor(x0), math.floor(y0)
    nu, nv = math.ceil(x1) - kx0, math.ceil(y1) - ky0
    nu, nv = max(1, nu), max(1, nv)
    boxes = [_box(kx0 + u, ky0 + v, kx0 + u + 1, ky0 + v + 1)
             for u in range(nu) for v in range(nv)]
    hits = _sh.intersects(poly, _np.array(boxes, dtype=object))
    bm = _np.asarray(hits, dtype=_np.float32).reshape(nu, nv)
    return bm, kx0, ky0


def _kern(bid, oi, blk_data):
    """Per-layer kernels for (block, orientation), cached."""
    layers = blk_data["shape"][oi]["layers"]
    out = []
    for l, pts in enumerate(layers):
        key = (bid, oi, l)
        if key not in _KERN:
            _KERN[key] = _raster_layer(pts)
        out.append(_KERN[key])
    return out


def positions(bay_w, bay_h, residents, bid, blk_data, oi, C, spread=True):
    """Entry-feasible integer reference positions.

    residents: list of (rbid, r_blk_data, r_oi, rx, ry).
    Returns up to C (x, y) ints sorted bottom-left-first with optional
    spatial spreading, or None on any failure (caller falls back).
    """
    if not _OK:
        return None
    try:
        kerns = _kern(bid, oi, blk_data)
        n_lay = len(kerns)
        # reference-point domain from exact layer bounds
        xs, ys = [], []
        for pts in blk_data["shape"][oi]["layers"]:
            for (px, py) in pts:
                xs.append(px)
                ys.append(py)
        lx0, ly0, lx1, ly1 = min(xs), min(ys), max(xs), max(ys)
        x_lo, x_hi = math.ceil(-lx0), math.floor(bay_w - lx1)
        y_lo, y_hi = math.ceil(-ly0), math.floor(bay_h - ly1)
        if x_hi < x_lo or y_hi < y_lo:
            return []
        # occupancy per layer level (bay grid), then suffix-union occ_ge
        max_rl = max([n_lay] + [len(r[1]["shape"][r[2]]["layers"])
                                for r in residents])
        # MEMORY GUARD (review 2026-07-28, "raster NFP OOM bomb"): an
        # adversarial instance with inflated bay dimensions makes this
        # occupancy tensor and the full-mode FFT correlations below allocate
        # multi-GB intermediates on the 16 GB server.  Above the cap decline
        # the NFP path (return None) — the caller's contract already handles
        # None with a non-NFP fallback, so this degrades quality, never
        # feasibility.
        _CELL_CAP = 4_000_000            # cells per layer (~2000x2000)
        if bay_w * bay_h > _CELL_CAP or max_rl * bay_w * bay_h > 4 * _CELL_CAP:
            return None
        occ = _np.zeros((max_rl, bay_w, bay_h), dtype=_np.float32)
        for (rbid, rdata, roi, rx, ry) in residents:
            for l, (bm, kx0, ky0) in enumerate(_kern(rbid, roi, rdata)):
                gx0, gy0 = int(rx) + kx0, int(ry) + ky0
                sx0, sy0 = max(0, gx0), max(0, gy0)
                sx1 = min(bay_w, gx0 + bm.shape[0])
                sy1 = min(bay_h, gy0 + bm.shape[1])
                if sx1 > sx0 and sy1 > sy0:
                    occ[l, sx0:sx1, sy0:sy1] = _np.maximum(
                        occ[l, sx0:sx1, sy0:sy1],
                        bm[sx0 - gx0:sx1 - gx0, sy0 - gy0:sy1 - gy0])
        for l in range(max_rl - 2, -1, -1):        # occ_ge[l] = union of >= l
            occ[l] = _np.maximum(occ[l], occ[l + 1])
        # overlap counts on the position lattice via cross-correlation
        bad = None
        for l in range(min(n_lay, max_rl)):
            bm, kx0, ky0 = kerns[l]
            full = _corr(occ[l], bm, mode="full", method="auto")
            # Overlap(x,y) = full[x + kx0 + Ku - 1, y + ky0 + Kv - 1]
            Ku, Kv = bm.shape
            ix0 = x_lo + kx0 + Ku - 1
            iy0 = y_lo + ky0 + Kv - 1
            sub = full[ix0:ix0 + (x_hi - x_lo + 1), iy0:iy0 + (y_hi - y_lo + 1)]
            bad = sub if bad is None else bad + sub
        if bad is None:                              # no residents' layers
            bad = _np.zeros((x_hi - x_lo + 1, y_hi - y_lo + 1), dtype=_np.float32)
        feas = _np.argwhere(bad < 0.5)
        if feas.size == 0:
            return []
        pts = [(int(px) + x_lo, int(py) + y_lo) for px, py in feas]
        pts.sort(key=lambda p: (p[0] + p[1], p[1], p[0]))
        if not spread or len(pts) <= C:
            return pts[:C]
        # bottom-left first, then greedy max-min-distance spread for diversity
        chosen = [pts[0]]
        rest = pts[1:]
        while len(chosen) < C and rest:
            best_i, best_d = 0, -1.0
            for i, p in enumerate(rest):
                d = min((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 for q in chosen)
                if d > best_d:
                    best_i, best_d = i, d
            chosen.append(rest.pop(best_i))
        return chosen
    except Exception:  # noqa: BLE001
        return None
