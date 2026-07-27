"""
model.py -- parsed problem instance (ground truths T1-T4 made explicit).

Everything downstream works from this immutable view of prob_info:

  * BayInfo   : integer dimensions, area, and the Z2 weight u_j.
  * BlockInfo : timing (release/due/proc/slack), workload, preferences, and
                one conservative Stamp per orientation (rasters.py).
  * Instance  : the whole problem plus derived quantities -- horizon,
                compatibility (which bays an orientation of a block fits),
                and the exact objective weights.

Nothing here mutates during search; per-bay occupancy state lives in
occupancy.py so it can be forked copy-on-write by the conductor (T8).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .rasters import Stamp, build_stamp


@dataclass(frozen=True)
class BayInfo:
    id: int
    width: int
    height: int

    @property
    def area(self) -> int:
        return self.width * self.height


@dataclass(frozen=True)
class BlockInfo:
    id: int
    release: int
    due: int
    proc: int
    workload: int
    prefs: tuple           # bay_preferences, index by bay id
    stamps: tuple          # one Stamp per orientation (orient_idx order)
    raw: dict              # original prob_info["blocks"][id] entry

    @property
    def slack(self) -> int:
        """Days of freedom inside the zero-tardiness window (may be < 0)."""
        return self.due - self.release - self.proc

    @property
    def zero_window_last_entry(self) -> int:
        """Latest entry day that still finishes by the due date."""
        return self.due - self.proc

    @property
    def pref_max(self) -> int:
        return max(self.prefs)

    def stamps_fitting(self, bay: BayInfo) -> list[Stamp]:
        return [s for s in self.stamps if s.fits_bay(bay.width, bay.height)]

    def stamp_for_orient(self, orient_idx: int) -> Stamp:
        """Stamp by orientation id (stamps may be sparse if a degenerate
        orientation failed to rasterize, so index != orient_idx in general)."""
        for s in self.stamps:
            if s.orient_idx == orient_idx:
                return s
        raise KeyError(f"block {self.id}: no stamp for orientation {orient_idx}")


@dataclass(frozen=True)
class Instance:
    name: str
    bays: tuple
    blocks: tuple
    w1: float
    w2: float
    w3: float
    horizon: int                     # generous initial time axis; occupancy
                                     # auto-extends beyond it when delays push
    u: tuple = field(default=())     # Z2 bay weights u_j = avg_area / area_j

    @classmethod
    def from_prob_info(cls, prob_info: dict) -> "Instance":
        bays = tuple(
            BayInfo(id=j, width=int(b["width"]), height=int(b["height"]))
            for j, b in enumerate(prob_info["bays"])
        )
        blocks = []
        for i, b in enumerate(prob_info["blocks"]):
            stamps = []
            for oi, shape in enumerate(b["shape"]):
                s = build_stamp(oi, shape["layers"])
                if s is not None:
                    stamps.append(s)
            blocks.append(BlockInfo(
                id=i,
                release=int(b["release_time"]),
                due=int(b["due_date"]),
                proc=int(b["processing_time"]),
                workload=int(b["workload"]),
                prefs=tuple(b["bay_preferences"]),
                stamps=tuple(stamps),
                raw=b,
            ))
        weights = prob_info.get("weights", {})
        max_due = max((b.due for b in blocks), default=0)
        max_end = max((b.release + b.proc for b in blocks), default=0)
        avg_area = sum(b.area for b in bays) / len(bays)
        return cls(
            name=prob_info.get("name", "unnamed"),
            bays=bays,
            blocks=tuple(blocks),
            w1=weights.get("w1", 1.0),
            w2=weights.get("w2", 1.0),
            w3=weights.get("w3", 1.0),
            horizon=max(max_due, max_end) + 8,
            u=tuple(avg_area / b.area for b in bays),
        )

    def compatible_bays(self, block: BlockInfo) -> list[int]:
        """Bays where at least one orientation stamp fits (assignment domain)."""
        return [b.id for b in self.bays if block.stamps_fitting(b)]

    @property
    def slack_gt4_share(self) -> float:
        """Triage statistic (F3/O3): share of blocks with slack > 4.  Easy/mid
        instances sit near 0 (entry = release is the right skeleton); the
        wide-slack tail (prob_40: ~0.47) has real temporal freedom and gets
        the queue-aware construction instead of the blind projection."""
        if not self.blocks:
            return 0.0
        return sum(1 for b in self.blocks if b.slack > 4) / len(self.blocks)
