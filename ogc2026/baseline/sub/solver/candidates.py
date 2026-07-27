"""
candidates.py -- placement search over an occupancy window (Part II, F1).

At sub-cell resolution the sliding-window materialization used at unit cells
is 16-256x more work, so the whole feasibility map is computed as one FFT
cross-correlation: overlap_count(sy, sx) = (occ * stamp)(sy, sx); a placement
is feasible iff its overlap count is (numerically) zero.  A bay window is at
most ~680 x 120 subcells, so each map costs a few milliseconds regardless of
stamp size.

Placements must land on *integer* block coordinates: the correlation is
computed over all subcell shifts, then subsampled to the residue class
(off_x mod R, off_y mod R) that integer (x, y) placements occupy.

Position preference (v0): lowest-then-leftmost (bottom-left first fit).
The design's contact-perimeter surrogate can replace the argmax without
touching callers -- both consume the same feasibility map.
"""

from __future__ import annotations

import numpy as np

try:
    from scipy.signal import fftconvolve
    _HAS_SCIPY = True
except Exception:                                        # pragma: no cover
    _HAS_SCIPY = False

from .rasters import Stamp


def _correlate(occ2d: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """Overlap counts for every subcell shift ('valid' correlation)."""
    if _HAS_SCIPY:
        return fftconvolve(occ2d.astype(np.float32),
                           grid[::-1, ::-1].astype(np.float32), mode="valid")
    # Fallback: exact but slower windowed AND (unit-resolution scale only).
    from numpy.lib.stride_tricks import sliding_window_view
    windows = sliding_window_view(occ2d, grid.shape)
    return (windows & grid).sum(axis=(2, 3)).astype(np.float32)


def first_fit(occ2d: np.ndarray, stamp: Stamp) -> tuple[int, int] | None:
    """Bottom-left-most feasible *block coordinate* (x, y), or None."""
    H, W = occ2d.shape
    h, w = stamp.h, stamp.w
    if h > H or w > W:
        return None
    R = stamp.resolution
    counts = _correlate(occ2d, stamp.grid)               # (H-h+1, W-w+1)

    # Integer placements live on subcell residues (off mod R); x = k - off//R.
    row0 = stamp.off_y % R
    col0 = stamp.off_x % R
    feas = counts[row0::R, col0::R] < 0.5
    if not feas.any():
        return None
    flat = int(np.argmax(feas))                          # row-major: min y, then x
    ky, kx = divmod(flat, feas.shape[1])
    x = kx - (stamp.off_x - col0) // R
    y = ky - (stamp.off_y - row0) // R
    return x, y
