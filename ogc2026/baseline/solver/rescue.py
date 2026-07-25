"""
rescue.py -- exact-polygon rescue, tier 1 of the false-tardiness ladder (III.1).

The raster is conservative: a placement that exactly fits can be
raster-rejected (diagonal edges, fractional vertices).  Before the oracle is
allowed to delay a block past its zero-tardiness window, this tier re-searches
the same window with the *true* Shapely footprints at integer anchor
positions.  The raster filters for speed; it is never the verdict on
tardiness.

Acceptance test mirrors utils exactly: conservative footprints must have
zero-area intersection (shared edges allowed).  Union-footprint disjointness
implies per-layer disjointness at every level, so a rescue placement is still
crane-safe under T5 -- no exact-layer reasoning needed at this tier (that is
tuck.py, tier 2).
"""

from __future__ import annotations

import math
import time

import shapely
from shapely import affinity

from .budget import Deadline
from .model import BayInfo, BlockInfo
from .rasters import Stamp

_CHECK_EVERY = 64  # deadline poll granularity inside the position scan


def exact_search(bay: BayInfo, block: BlockInfo,
                 co_present, e0: int, e1: int,
                 deadline: Deadline, margin: float = 0.05,
                 time_cap: float = 1.0) -> tuple[int, int, Stamp] | None:
    """Search integer (x, y, orientation) with exact geometry.

    co_present: iterable of (entry, exit, world_footprint) for blocks already
    placed in the bay; only those overlapping [e0, e1) constrain the search.

    Budgeted (III.1): gives up at the caller's deadline margin or after
    time_cap seconds of scan, whichever first -- one rescue may never starve
    the rest of the pipeline.

    Returns (x, y, stamp) in *block reference* coordinates, or None.
    """
    t0 = time.monotonic()
    neighbors = [fp for (a, e, fp) in co_present if a < e1 and e0 < e]
    tree = shapely.STRtree(neighbors) if neighbors else None

    tested = 0
    for stamp in block.stamps:
        minx, miny, maxx, maxy = stamp.footprint.bounds
        # Integer x range keeping the exact footprint inside [0, W] x [0, H].
        x_lo, x_hi = math.ceil(-minx), math.floor(bay.width - maxx)
        y_lo, y_hi = math.ceil(-miny), math.floor(bay.height - maxy)
        for y in range(y_lo, y_hi + 1):
            for x in range(x_lo, x_hi + 1):
                tested += 1
                if tested % _CHECK_EVERY == 0 and (
                        deadline.expired(margin=margin)
                        or time.monotonic() - t0 > time_cap):
                    return None
                fp = affinity.translate(stamp.footprint, xoff=x, yoff=y)
                if tree is not None:
                    hit = False
                    for idx in tree.query(fp):
                        inter = fp.intersection(neighbors[idx])
                        if not inter.is_empty and inter.area > 0:
                            hit = True
                            break
                    if hit:
                        continue
                return x, y, stamp
    return None
