"""
occupancy.py -- per-bay spatio-temporal occupancy grid (design Part II).

One boolean array of shape (T, H*R, W*R) per bay at R subcells per unit
(F1): subcell (t, sy, sx) is True iff some committed block's conservative
stamp covers it during day t (half-open presence [entry, exit)).  All
placement tests are numpy AND/ANY or FFT correlations over day-window
slices -- never Shapely, never utils (T6).

The public API works in *block reference coordinates* (the integer (x, y)
that goes into the solution); stamps carry the subcell offsets and the
conversion happens here, in one place.

Soundness invariant: a placement accepted against this grid has a stamp
disjoint from every co-present stamp, hence (rasters.py) polygon-disjoint
conservative footprints, hence (T5) collision-free layers and unobstructed
crane entry/exit at any operation order.  Rescue-tier commits (exact geometry
that the raster over-rejects) OR their stamp in anyway; the grid then
over-approximates occupancy, which keeps later raster accepts sound.
F6 note: when tuck.py lands, tucked placements must additionally set a
parallel dirty mask here; clean subcells => the bitmap is truth, dirty
subcells => exact crane check mandatory.

The day axis auto-extends (F7): delayed blocks can push past the initial
horizon, and an index crash on a tardy tail instance would itself be a -1.
"""

from __future__ import annotations

import numpy as np

from .rasters import RESOLUTION, Stamp


class BayOccupancy:
    """Mutable occupancy state of one bay. Cheap to fork via copy()."""

    def __init__(self, width: int, height: int, horizon: int,
                 resolution: int = RESOLUTION):
        self.width = width
        self.height = height
        self.R = resolution
        self.grid = np.zeros((horizon, height * resolution, width * resolution),
                             dtype=bool)

    def copy(self) -> "BayOccupancy":
        out = BayOccupancy(self.width, self.height, 1, self.R)
        out.grid = self.grid.copy()
        return out

    def _ensure(self, t_end: int) -> None:
        cur = self.grid.shape[0]
        if t_end > cur:
            extra = np.zeros((t_end - cur + 8,) + self.grid.shape[1:], bool)
            self.grid = np.concatenate([self.grid, extra], axis=0)

    def _sub(self, stamp: Stamp, x: int, y: int) -> tuple[int, int]:
        """Subcell origin of a stamp placed at block coords (x, y)."""
        return x * self.R + stamp.off_x, y * self.R + stamp.off_y

    def window(self, e0: int, e1: int) -> np.ndarray:
        """OR of the day slices [e0, e1) -- the 2-D free/occupied view a
        placement over that interval must be tested against."""
        self._ensure(e1)
        return self.grid[e0:e1].any(axis=0)

    def fits(self, stamp: Stamp, x: int, y: int, e0: int, e1: int) -> bool:
        """True iff the stamp at block coords (x, y) is disjoint from all
        committed stamps over [e0, e1) and inside the bay grid."""
        sx, sy = self._sub(stamp, x, y)
        if (sx < 0 or sy < 0 or sx + stamp.w > self.grid.shape[2]
                or sy + stamp.h > self.grid.shape[1]):
            return False
        self._ensure(e1)
        occ = self.grid[e0:e1, sy:sy + stamp.h, sx:sx + stamp.w]
        return not np.any(occ & stamp.grid)

    def commit(self, stamp: Stamp, x: int, y: int, e0: int, e1: int) -> None:
        sx, sy = self._sub(stamp, x, y)
        self._ensure(e1)
        self.grid[e0:e1, sy:sy + stamp.h, sx:sx + stamp.w] |= stamp.grid

    def remove(self, stamp: Stamp, x: int, y: int, e0: int, e1: int) -> None:
        """Clear a previously committed stamp.

        Only valid while committed stamps are pairwise disjoint (pure-raster
        pipeline).  After a rescue-tier commit the grid may hold overlapping
        stamps and removal must rebuild from the placement list instead --
        callers that use rescue must not call remove().
        """
        sx, sy = self._sub(stamp, x, y)
        self.grid[e0:e1, sy:sy + stamp.h, sx:sx + stamp.w] &= ~stamp.grid
