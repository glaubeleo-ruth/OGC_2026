"""
_parity_test.py -- milestone 1 soundness property test (design Part VIII.1).

Property: engine-feasible => utils-feasible, 100%.  For random pairs of
(block, orientation, integer position) in a random bay:

  if the conservative raster says "contained and disjoint", then
  utils.check_entry must report no obstruction for either insertion order,
  and utils.check_collisions must report no overlap.

Any violation is a soundness bug (kill criterion).  The converse direction
(utils-feasible but raster-rejected) is *expected* -- that lost capacity is
what rescue.py wins back -- and is reported as a rate, not a failure.

Run from baseline/:  python -m solver._parity_test [N_trials] [prob_path]
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

_BASE = Path(__file__).resolve().parents[1]
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))
import utils

from solver.model import Instance
from solver.occupancy import BayOccupancy


def run(n_trials: int = 5000, prob_path: str | None = None, seed: int = 0) -> bool:
    root = Path(__file__).resolve().parents[3]
    path = Path(prob_path) if prob_path else root / "train" / "prob_1.json"
    prob = json.loads(path.read_text())
    inst = Instance.from_prob_info(prob)
    rng = random.Random(seed)

    violations = 0
    engine_ok = 0
    conservative_rejects = 0

    for _ in range(n_trials):
        bay = rng.choice(inst.bays)
        b1, b2 = rng.sample(list(inst.blocks), 2)
        s1 = rng.choice(b1.stamps)
        s2 = rng.choice(b2.stamps)
        if not (s1.fits_bay(bay.width, bay.height) and s2.fits_bay(bay.width, bay.height)):
            continue
        ranges = [s1.x_range(bay.width), s1.y_range(bay.height),
                  s2.x_range(bay.width), s2.y_range(bay.height)]
        if any(lo > hi for lo, hi in ranges):
            continue
        p1 = (rng.randint(*ranges[0]), rng.randint(*ranges[1]))
        p2 = (rng.randint(*ranges[2]), rng.randint(*ranges[3]))

        occ = BayOccupancy(bay.width, bay.height, 4)
        occ.commit(s1, p1[0], p1[1], 0, 2)
        engine_says_fits = occ.fits(s2, p2[0], p2[1], 0, 2)

        ubay = utils.Bay(width=bay.width, height=bay.height, id=bay.id)
        ub1 = utils.Block(block_id=b1.id, block_data=b1.raw,
                          x=p1[0], y=p1[1], orient_idx=s1.orient_idx)
        ub2 = utils.Block(block_id=b2.id, block_data=b2.raw,
                          x=p2[0], y=p2[1], orient_idx=s2.orient_idx)

        if engine_says_fits:
            engine_ok += 1
            problems = []
            problems += utils.check_entry(ubay, [ub1], ub2)
            problems += utils.check_entry(ubay, [ub2], ub1)
            problems += utils.check_collisions(ubay, [ub1, ub2])
            if problems:
                violations += 1
                if violations <= 5:
                    print(f"SOUNDNESS VIOLATION: bay={bay.id} "
                          f"b1={b1.id}/o{s1.orient_idx}@{(ub1.x, ub1.y)} "
                          f"b2={b2.id}/o{s2.orient_idx}@{(ub2.x, ub2.y)}: "
                          f"{problems[0]}")
        else:
            # Track how often utils would have accepted what the raster
            # rejected: the capacity conceded to conservatism (informational).
            if not utils.check_entry(ubay, [ub1], ub2):
                conservative_rejects += 1

    print(f"trials with engine-accept: {engine_ok}, "
          f"soundness violations: {violations} (must be 0)")
    print(f"conservative over-rejects (capacity conceded, informational): "
          f"{conservative_rejects}")
    ok = violations == 0
    print("PARITY:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    p = sys.argv[2] if len(sys.argv) > 2 else None
    sys.exit(0 if run(n, p) else 1)
