"""
oracle.py -- per-bay packing oracle (design Part V, stages 2-3 as A's oracle).

T2 taken literally: project entry = release, exit = entry + proc (Exit-ASAP
dominance, valid in conservative mode) and treat the bay as placement-only.
Per block, in release order (ties: larger area first):

  1. raster search over every entry day in the zero-tardiness window
     [release, due - proc] -- one vectorized feasibility map per
     (entry, orientation);
  2. tier-1 rescue (rescue.py): exact-polygon re-search of the same window
     before any delay is accepted -- the raster never gets the tardiness
     verdict (III.1);
  3. minimal delay: first entry day > window with a raster fit.  Termination
     is guaranteed: once entry passes every committed exit the bay is empty
     and any bay-fitting stamp places.

Deadline discipline (WATCHDOG: deadline threading / safety factor): the
oracle polls the shared Deadline against a caller-supplied `reserve` margin
(time the caller still needs for auditing/emission after packing).  When the
margin is hit the oracle degrades to *rushed mode* -- single orientation, no
rescue -- which stays sound (every placement still goes through the raster)
but bounds per-block cost, so the pass always terminates well before the
budget instead of overrunning it.  Cost is also bounded in normal mode: past
the first delay days, the orientation set shrinks to the most compact stamps.

Tiers 2 (tuck.py) and 3 (cluster.py) hook in behind the same interface when
implemented; repair.py consumes the returned bay state (occupancy + exact
footprints) for cross-bay tardiness repair.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from shapely import affinity

from . import rescue
from .budget import Deadline
from .candidates import first_fit
from .model import BayInfo, Instance
from .occupancy import BayOccupancy

_FULL_ORIENT_DELAY_DAYS = 5   # delay days searched with every orientation
                              # before shrinking to the compact subset


@dataclass(frozen=True)
class Placement:
    block_id: int
    bay_id: int
    x: int
    y: int
    orient_idx: int
    entry: int
    exit: int
    via: str          # "raster" | "rescue"


@dataclass
class BayPacking:
    bay_id: int
    placements: list
    delayed_ids: list          # blocks that left their zero-tardiness window
    occ: BayOccupancy | None = None
    exact_fps: list = field(default_factory=list)   # (entry, exit, footprint)


def _compact_order(stamps) -> list:
    """Orientations by raster cell count: densest-first placement attempts."""
    return sorted(stamps, key=lambda s: int(s.grid.sum()))


def plan_entries(inst: Instance, bay: BayInfo, block_ids) -> dict:
    """Queue-aware entry projection (O3/F3) for wide-slack instances.

    Greedy per-layer area leveling over each block's zero-tardiness window:
    tightest blocks (smallest slack) commit first at their least-congested
    entry day; later blocks price each candidate entry by (overload beyond
    bay capacity, then total overlap) against the accumulating profile.
    Pure area relaxation -- geometry stays the oracle's job; this only picks
    *target* entry days so insertion starts near a good temporal ordering
    instead of the blind entry = release projection.
    """
    blocks = [(i, inst.blocks[i]) for i in block_ids]
    if not blocks:
        return {}
    horizon = inst.horizon + max(b.proc for _, b in blocks) + 1
    load = np.zeros(horizon)
    cap = float(bay.area)
    prefs: dict = {}

    def demand(b):
        # What packing actually consumes is the conservative union footprint
        # (F2/F4: tail congestion is geometric -- overhangs -- so per-layer
        # polygon areas systematically under-price it).
        R2 = float(b.stamps[0].resolution ** 2)
        return min(float(s.grid.sum()) / R2 for s in b.stamps)

    order = sorted(blocks, key=lambda ib: (ib[1].slack, -demand(ib[1])))
    for bid, b in order:
        a = demand(b)
        lo = b.release
        hi = max(b.release, b.zero_window_last_entry)
        best_entry, best_cost = lo, None
        for entry in range(lo, hi + 1):
            seg = load[entry:entry + b.proc]
            overload = float(np.maximum(seg + a - cap, 0.0).sum())
            cost = (overload, float(seg.sum()))
            if best_cost is None or cost < best_cost:
                best_cost, best_entry = cost, entry
        prefs[bid] = best_entry
        load[best_entry:best_entry + b.proc] += a
    return prefs


def _candidate_entries(placements, lo: int, hi: int | None) -> list:
    """Entry days worth testing in [lo, hi] (hi=None -> unbounded).

    For any fixed position, a blocked placement stays blocked until some
    committed block exits, so the minimal feasible entry is either `lo` or a
    committed exit day -- scanning only those is exact, and turns O(days)
    delay scans into O(bay blocks).  Beyond the last committed exit the bay
    is empty, so the list is finite and always terminates the search.
    """
    exits = {p.exit for p in placements if p.exit > lo}
    if hi is not None:
        exits = {e for e in exits if e <= hi}
    return [lo] + sorted(exits)


def pack_bay(inst: Instance, bay: BayInfo, block_ids,
             deadline: Deadline, use_rescue: bool = True,
             reserve: float = 0.0,
             abort_on_expire: bool = False,
             preferred: dict | None = None) -> BayPacking | None:
    """Pack one bay.  Two budget-exhaustion semantics:

    * abort_on_expire=False ("complete", the seed pass): degrade to rushed
      mode (single orientation, no rescue, compact scans) but always finish
      -- the -1 containment story depends on this pass existing.
    * abort_on_expire=True (the full pass): return None at the reserve margin
      -- an audited incumbent already exists, and a rushed completion of a
      re-pack is measurably worse than keeping that incumbent.
    """
    occ = BayOccupancy(bay.width, bay.height, inst.horizon)
    exact_fps: list = []
    placements: list = []
    delayed: list = []

    # Insertion stays in release order even with a queue-aware plan: measured
    # on prob_40, ordering insertion by planned entry fragments early space
    # and costs ~700 tardy days; the plan's value is in *where inside the
    # window* each block aims (candidate ordering below), not in reshuffling
    # who packs first.
    order = sorted(
        block_ids,
        key=lambda i: (inst.blocks[i].release,
                       -max(s.max_layer_area for s in inst.blocks[i].stamps)),
    )

    for bid in order:
        blk = inst.blocks[bid]
        stamps = _compact_order(blk.stamps_fitting(bay) or list(blk.stamps))
        rushed = deadline.expired(margin=reserve)
        if rushed and abort_on_expire:
            return None
        window_stamps = stamps[:1] if rushed else stamps
        placed = None

        # -- tier 0: raster over the zero-tardiness window --------------------
        # With a queue-aware plan the planned entry is tried first, then the
        # rest of the window by distance from it; otherwise ascending.
        window_cands = _candidate_entries(placements, blk.release,
                                          blk.zero_window_last_entry)
        if preferred is not None and bid in preferred:
            pref_e = preferred[bid]
            window_cands = sorted(set(window_cands) | {pref_e},
                                  key=lambda e: (abs(e - pref_e), e))
        for entry in window_cands:
            if entry > blk.zero_window_last_entry:
                continue
            e1 = entry + blk.proc
            occ2d = occ.window(entry, e1)
            for st in window_stamps:
                pos = first_fit(occ2d, st)
                if pos is not None:
                    placed = (entry, st, pos[0], pos[1], "raster")
                    break
            if placed:
                break

        # -- tier 1: exact-polygon rescue inside the same window --------------
        # Budgeted per block (III.1): at most 2 entry attempts, ~1 s each, so
        # a string of hopeless blocks cannot starve the rest of the pass.
        if (placed is None and use_rescue and not rushed
                and blk.zero_window_last_entry >= blk.release):
            for entry in _candidate_entries(placements, blk.release,
                                            blk.zero_window_last_entry)[:2]:
                if deadline.expired(margin=reserve + 0.5):
                    break
                r = rescue.exact_search(bay, blk, exact_fps,
                                        entry, entry + blk.proc, deadline,
                                        margin=reserve)
                if r is not None:
                    x, y, st = r
                    placed = (entry, st, x, y, "rescue")
                    break

        # -- last resort: minimal raster delay (tardiness accepted) -----------
        if placed is None and stamps:
            first_delay_day = max(blk.release, blk.zero_window_last_entry + 1)
            while placed is None:
                cands = _candidate_entries(placements, first_delay_day, None)
                interrupted = False
                for entry in cands:
                    if not rushed and deadline.expired(margin=reserve):
                        if abort_on_expire:
                            return None
                        rushed = True        # single-orientation scans from here
                        interrupted = True
                        break
                    # Past the first days of delay, drop to the compact subset.
                    if rushed or entry - first_delay_day >= _FULL_ORIENT_DELAY_DAYS:
                        tries = stamps[:1]
                    else:
                        tries = window_stamps
                    e1 = entry + blk.proc
                    occ2d = occ.window(entry, e1)
                    for st in tries:
                        pos = first_fit(occ2d, st)
                        if pos is not None:
                            placed = (entry, st, pos[0], pos[1], "raster")
                            break
                    if placed:
                        break
                if placed is None and not interrupted:
                    break   # unplaceable in this bay: degenerate path below
            if placed is not None and placed[0] > blk.zero_window_last_entry:
                delayed.append(bid)

        if placed is None:
            # Degenerate: no integer placement of any orientation exists in
            # this bay (assignment should have prevented it).  Emit a
            # best-effort placement WITHOUT committing to the grid -- the
            # utils gate renders the verdict; crashing here would be a -1.
            st = stamps[0] if stamps else blk.stamps[0]
            xr, yr = st.x_range(bay.width), st.y_range(bay.height)
            x0 = xr[0] if xr[0] <= xr[1] else max(0, xr[0])
            y0 = yr[0] if yr[0] <= yr[1] else max(0, yr[0])
            delayed.append(bid)
            placements.append(Placement(
                block_id=bid, bay_id=bay.id, x=x0, y=y0,
                orient_idx=st.orient_idx, entry=blk.release,
                exit=blk.release + blk.proc, via="degenerate",
            ))
            continue

        entry, st, x, y, via = placed
        e1 = entry + blk.proc
        occ.commit(st, x, y, entry, e1)
        exact_fps.append((entry, e1,
                          affinity.translate(st.footprint, xoff=x, yoff=y)))
        placements.append(Placement(
            block_id=bid, bay_id=bay.id, x=x, y=y,
            orient_idx=st.orient_idx, entry=entry, exit=e1, via=via,
        ))

    return BayPacking(bay_id=bay.id, placements=placements,
                      delayed_ids=delayed, occ=occ, exact_fps=exact_fps)
