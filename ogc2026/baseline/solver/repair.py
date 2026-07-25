"""
repair.py -- greedy cross-bay tardiness repair (design Part IV, oracle
neighborhood steps (a)/(b) lite; the Z1-first layer beneath cluster.py).

The oracle packs bays independently and in release order, so a block can end
tardy in its assigned bay while another bay (or a later-freed slot in its own
bay) could host it inside its zero-tardiness window -- exactly the myopia the
milestone-2 gap KPI certified (Z1 > 0 with LB = 0).  Since w1 dwarfs w2/w3
(T2), moving one block out of tardiness beats almost any Z2/Z3 cost; the move
is still priced exactly (utils-identical deltas) before acceptance.

Loop until no improving move or the deadline reserve is hit:

  for each tardy block, worst first:
    for each bay (own bay = re-placement without itself):
      find the earliest raster-feasible entry in [release, entry-1],
      preferring the zero-tardiness window;
    accept the best strictly-improving move of
      w1*dZ1 + w2*dZ2 + w3*dZ3.

Raster-only (sound by construction); rescue/tuck-tier moves and joint
multi-block moves belong to cluster.py (III.1 tier 3).  Bay states are
rebuilt from placement lists on every accepted move -- O(bay blocks) numpy
ORs, microseconds -- which also keeps the exact-footprint lists consistent
for any later rescue pass.
"""

from __future__ import annotations

import math

from shapely import affinity

from .budget import Deadline
from .candidates import first_fit
from .model import Instance
from .occupancy import BayOccupancy
from .oracle import Placement

_MAX_REDUCTION_SCAN = 40   # delay-entry days scanned past the zero window
                           # when full de-tardying is not achievable


def _rebuild(inst: Instance, bay, placements) -> tuple:
    occ = BayOccupancy(bay.width, bay.height, inst.horizon)
    fps = []
    for p in placements:
        if p.via == "degenerate":     # never committed by the oracle either
            continue
        st = inst.blocks[p.block_id].stamp_for_orient(p.orient_idx)
        occ.commit(st, p.x, p.y, p.entry, p.exit)
        fps.append((p.entry, p.exit,
                    affinity.translate(st.footprint, xoff=p.x, yoff=p.y)))
    return occ, fps


def _z2(inst: Instance, loads) -> float:
    m = len(inst.bays)
    if m < 2:
        return 0.0
    return float(math.floor(max(
        abs(inst.u[j1] * loads[j1] - inst.u[j2] * loads[j2])
        for j1 in range(m) for j2 in range(m) if j1 != j2
    )))


def repair_tardiness(inst: Instance, by_bay: dict, deadline: Deadline,
                     reserve: float = 0.0) -> dict:
    """by_bay: bay_id -> list[Placement]; mutated to the repaired packing.

    Returns stats {"moves": int, "z1_before": float, "z1_after": float}.
    """
    occs = {}
    for bay in inst.bays:
        occs[bay.id], _ = _rebuild(inst, bay, by_bay[bay.id])
    loads = [0.0] * len(inst.bays)
    for j, ps in by_bay.items():
        loads[j] = float(sum(inst.blocks[p.block_id].workload for p in ps))

    def tardy_list():
        out = []
        for ps in by_bay.values():
            for p in ps:
                t = p.exit - inst.blocks[p.block_id].due
                if t > 0:
                    out.append((t, p))
        out.sort(key=lambda tp: -tp[0])
        return out

    z1_before = sum(t for t, _ in tardy_list())
    moves = 0

    improved = True
    while improved and not deadline.expired(margin=reserve):
        improved = False
        for tardy_days, p in tardy_list():
            if deadline.expired(margin=reserve):
                break
            blk = inst.blocks[p.block_id]
            best = None   # (net_delta, bay_id, entry, st, gx, gy)

            for bay in inst.bays:
                own = bay.id == p.bay_id
                stamps = blk.stamps_fitting(bay)
                if not stamps:
                    continue
                if own:
                    occ, _ = _rebuild(inst, bay,
                                      [q for q in by_bay[bay.id] if q is not p])
                else:
                    occ = occs[bay.id]

                # Earliest feasible entry that strictly improves the exit:
                # zero window first, then a bounded reduction scan.
                last_zero = min(blk.zero_window_last_entry, p.entry - 1)
                scan_end = min(p.entry - 1,
                               blk.zero_window_last_entry + _MAX_REDUCTION_SCAN)
                found = None
                entry = blk.release
                while entry <= scan_end:
                    e1 = entry + blk.proc
                    occ2d = occ.window(entry, e1)
                    for st in stamps:
                        pos = first_fit(occ2d, st)
                        if pos is not None:
                            found = (entry, st, pos[0], pos[1])
                            break
                    if found:
                        break
                    entry += 1
                    if entry > last_zero and tardy_days <= (entry - 1 - blk.zero_window_last_entry):
                        break  # cannot strictly improve any more from here
                if found is None:
                    continue

                entry, st, px, py = found
                new_exit = entry + blk.proc
                d_z1 = max(0, new_exit - blk.due) - tardy_days
                if own:
                    d_z2 = 0.0
                    d_z3 = 0.0
                else:
                    new_loads = loads.copy()
                    new_loads[p.bay_id] -= blk.workload
                    new_loads[bay.id] += blk.workload
                    d_z2 = _z2(inst, new_loads) - _z2(inst, loads)
                    d_z3 = float(blk.prefs[p.bay_id] - blk.prefs[bay.id])
                net = inst.w1 * d_z1 + inst.w2 * d_z2 + inst.w3 * d_z3
                if net < -1e-9 and (best is None or net < best[0]):
                    best = (net, bay.id, entry, st, px, py)

            if best is None:
                continue

            _, new_bay, entry, st, px, py = best
            old_bay = p.bay_id
            by_bay[old_bay].remove(p)
            by_bay[new_bay].append(Placement(
                block_id=p.block_id, bay_id=new_bay,
                x=px, y=py,
                orient_idx=st.orient_idx,
                entry=entry, exit=entry + blk.proc, via="repair",
            ))
            loads[old_bay] -= blk.workload
            loads[new_bay] += blk.workload
            for j in {old_bay, new_bay}:
                occs[j], _ = _rebuild(inst, inst.bays[j], by_bay[j])
            moves += 1
            improved = True

    z1_after = sum(t for t, _ in tardy_list())
    return {"moves": moves, "z1_before": float(z1_before),
            "z1_after": float(z1_after)}


def polish_assignment(inst: Instance, by_bay: dict, deadline: Deadline,
                      reserve: float = 0.0) -> dict:
    """O6 polish: improving Z2/Z3 moves that can never create tardiness.

    After packing and tardiness repair, the realized assignment usually sits
    above the master's certified (Z2*, Z3*) optimum -- packing constraints
    and Z1-first moves both trade Z2/Z3 away.  This pass walks non-tardy
    blocks (largest preference deficit first) and moves one to another bay
    when (a) the exact priced delta w2*dZ2 + w3*dZ3 is strictly negative and
    (b) a raster placement exists inside the block's zero-tardiness window,
    so Z1 is untouched by construction.  Anytime and exact-priced, like
    repair_tardiness; by_bay is mutated in place.
    """
    occs = {}
    for bay in inst.bays:
        occs[bay.id], _ = _rebuild(inst, bay, by_bay[bay.id])
    loads = [0.0] * len(inst.bays)
    for j, ps in by_bay.items():
        loads[j] = float(sum(inst.blocks[p.block_id].workload for p in ps))

    moves = 0
    improved = True
    while improved and not deadline.expired(margin=reserve):
        improved = False
        everyone = [(p, inst.blocks[p.block_id])
                    for ps in by_bay.values() for p in ps]
        everyone.sort(key=lambda pb: -(pb[1].pref_max - pb[1].prefs[pb[0].bay_id]))
        for p, blk in everyone:
            if deadline.expired(margin=reserve):
                break
            if p.via == "degenerate" or p.exit > blk.due:
                continue   # tardy blocks belong to repair_tardiness
            best = None    # (net_delta, bay_id, entry, st, x, y)
            for bay in inst.bays:
                if bay.id == p.bay_id:
                    continue
                stamps = blk.stamps_fitting(bay)
                if not stamps:
                    continue
                # Exact price first; geometry only for strictly improving bays.
                new_loads = loads.copy()
                new_loads[p.bay_id] -= blk.workload
                new_loads[bay.id] += blk.workload
                net = (inst.w2 * (_z2(inst, new_loads) - _z2(inst, loads))
                       + inst.w3 * float(blk.prefs[p.bay_id] - blk.prefs[bay.id]))
                if net >= -1e-9 or (best is not None and net >= best[0]):
                    continue
                occ = occs[bay.id]
                found = None
                for entry in range(blk.release, blk.zero_window_last_entry + 1):
                    occ2d = occ.window(entry, entry + blk.proc)
                    for st in stamps:
                        pos = first_fit(occ2d, st)
                        if pos is not None:
                            found = (entry, st, pos[0], pos[1])
                            break
                    if found:
                        break
                if found is not None:
                    entry, st, px, py = found
                    best = (net, bay.id, entry, st, px, py)
            if best is None:
                continue
            _, new_bay, entry, st, px, py = best
            old_bay = p.bay_id
            by_bay[old_bay].remove(p)
            by_bay[new_bay].append(Placement(
                block_id=p.block_id, bay_id=new_bay, x=px, y=py,
                orient_idx=st.orient_idx,
                entry=entry, exit=entry + blk.proc, via="polish",
            ))
            loads[old_bay] -= blk.workload
            loads[new_bay] += blk.workload
            for j in {old_bay, new_bay}:
                occs[j], _ = _rebuild(inst, inst.bays[j], by_bay[j])
            moves += 1
            improved = True

    return {"polish_moves": moves}
