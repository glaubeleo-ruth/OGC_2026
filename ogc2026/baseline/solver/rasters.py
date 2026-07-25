"""
rasters.py -- conservative raster stamps (design Part II, F1 sub-cell).

For every (block, orientation) we precompute once:

  * footprint : Shapely union of all layer polygons in *local* coordinates
                (reference point -- first vertex of layer 0 -- at the origin).
                This is the conservative footprint of T5: if co-present
                footprints never interiorly overlap, every per-layer collision
                check and every crane j >= k check passes automatically.
  * grid      : boolean sub-cell raster at RESOLUTION subcells per unit
                (F1: measured 2026-07-25 on prob_1/14/40 contentious pairs --
                unit cells reject 10.8% of exact-accepted placements,
                1/2-cell 6.2%, 1/4-cell 3.7% < the 5% criterion; phantom-area
                tax 38% -> 9% median).  A subcell is marked iff the footprint
                *intersects* the closed cell -- boundary touches included --
                so the raster over-approximates the polygon (soundness:
                raster-disjoint implies polygon-disjoint; the converse may
                fail, costing only capacity, which rescue wins back).
  * off_x/off_y : subcell offset of the grid relative to the reference point.
                A block placed at integer (x, y) covers world subcells
                [x*R + off_x, ...+w) x [y*R + off_y, ...+h).  Because
                off = floor(min*R), grid containment in the bay implies
                exact-polygon containment.
  * layer_areas : per-layer-index polygon areas (rotation-invariant across
                orientations up to repair; bounds.py takes the min across
                orientations) -- the F5 per-layer cumulative demands.

Numerical note: layer vertices carry up to 4 fractional decimals.  The
closed-cell intersects() predicate dominates them -- no epsilon dilation is
needed on top.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import shapely
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.ops import unary_union

RESOLUTION = 4   # subcells per unit cell (F1 sweep: 1/4-cell passes < 5%)


def _poly(verts: list) -> ShapelyPolygon | None:
    """Shapely polygon from a vertex list, buffer(0)-repaired like utils."""
    if not verts or len(verts) < 3:
        return None
    try:
        p = ShapelyPolygon(verts)
        if not p.is_valid:
            p = p.buffer(0)
        return p if not p.is_empty else None
    except Exception:
        return None


@dataclass(frozen=True)
class Stamp:
    """Conservative sub-cell raster of one (block, orientation) footprint."""
    orient_idx: int
    footprint: object            # Shapely geometry, local coords
    grid: np.ndarray             # bool (h, w) in subcells
    off_x: int                   # world subcell x = block.x * R + off_x + col
    off_y: int                   # world subcell y = block.y * R + off_y + row
    layer_areas: tuple           # exact area per layer index (F5 demands)
    resolution: int = RESOLUTION

    @property
    def h(self) -> int:
        return self.grid.shape[0]

    @property
    def w(self) -> int:
        return self.grid.shape[1]

    @property
    def max_layer_area(self) -> float:
        return max(self.layer_areas)

    def fits_bay(self, bay_w: int, bay_h: int) -> bool:
        """True iff at least one *integer* placement keeps the grid in the
        bay.  Sub-cell subtlety: grid-fits (w <= W*R) is not enough -- integer
        placements live on one subcell residue class, which can be empty for
        boundary-tight stamps (e.g. a block exactly the bay's height with a
        fractional offset)."""
        xr = self.x_range(bay_w)
        yr = self.y_range(bay_h)
        return xr[0] <= xr[1] and yr[0] <= yr[1]

    def x_range(self, bay_w: int) -> tuple[int, int]:
        """Inclusive integer x range keeping the grid inside the bay."""
        R = self.resolution
        return (math.ceil(-self.off_x / R),
                (bay_w * R - self.w - self.off_x) // R)

    def y_range(self, bay_h: int) -> tuple[int, int]:
        R = self.resolution
        return (math.ceil(-self.off_y / R),
                (bay_h * R - self.h - self.off_y) // R)


def build_stamp(orient_idx: int, layers: list[list],
                resolution: int = RESOLUTION) -> Stamp | None:
    """Build the conservative sub-cell stamp for one orientation."""
    polys = [p for p in (_poly(l) for l in layers) if p is not None]
    if not polys:
        return None
    footprint = unary_union(polys)
    if footprint.is_empty:
        return None

    R = resolution
    minx, miny, maxx, maxy = footprint.bounds
    off_x = math.floor(minx * R)
    off_y = math.floor(miny * R)
    w = max(1, math.ceil(maxx * R) - off_x)
    h = max(1, math.ceil(maxy * R) - off_y)

    cols, rows = np.meshgrid(np.arange(w), np.arange(h))
    cx = (off_x + cols).ravel() / R
    cy = (off_y + rows).ravel() / R
    cells = shapely.box(cx, cy, cx + 1.0 / R, cy + 1.0 / R)
    shapely.prepare(footprint)
    grid = shapely.intersects(footprint, cells).reshape(h, w)

    return Stamp(orient_idx=orient_idx, footprint=footprint, grid=grid,
                 off_x=off_x, off_y=off_y,
                 layer_areas=tuple(p.area for p in polys),
                 resolution=R)
