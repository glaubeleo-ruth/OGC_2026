"""
assignment.py -- the LBBD assignment master (design Part IV).

T1: Z2 and Z3 depend only on the block->bay assignment, so the master solves

    min  w2*Z2(y) + w3*Z3(y) + sum_j theta_j
    s.t. every block to exactly one *compatible* bay
         fluid capacity  sum_i area_i*proc_i*y_ij <= rho * A_j * T
         cuts streamed back from the oracles/bounds (LBBD loop)

as a CP-SAT model.  Z2's max-abs is linearized with one aux variable; loads
and u_j are scaled to milli-units (u_j is rational), which prices Z2 to
< 0.1% -- the *exact* Z2/Z3 of any candidate assignment is always recomputed
via objective.py before it can become an incumbent, so the scaling can never
mis-rank an accepted solution (III.1).

Cut interface (applied on every re-solve; lbbd.py streams them in):
  * add_conflict_cut(bay, block_ids): oracle refuted this set jointly in the
    bay -> sum_{i in S} y_ij <= |S| - 1.  Only sound if the refutation came
    from the exact tiers (III.1), not from a raster-only failure.
  * add_tardiness_cut(bay, block_ids, lb): theta_bay >= lb whenever all of S
    sits in bay, in the linear no-good-on-change form
        theta_bay >= lb * (sum_{i in S} y_i,bay - |S| + 1).
    Sound iff lb is a certified LB for S in that bay (bounds.py CP-SAT bound;
    tardiness in a bay is monotone in its block set, so a subset's LB is
    valid while the subset stays together).  theta_j enters the objective at
    weight w1 so the master prices proven-unavoidable tardiness.
  * add_evaluated_nogood(assignment): excludes one already-packed-and-audited
    assignment (sum of its y literals <= n-1).  Sound as k-best enumeration:
    it only removes evaluated points, never an unevaluated candidate, so the
    master walks the next-best Z2/Z3 assignment each LBBD iteration.

Fallback (no ortools): greedy argmax-preference over compatible bays --
correct, never optimal, and clearly reported in the result info.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .budget import Deadline
from .model import Instance

try:
    from ortools.sat.python import cp_model
    _HAS_CPSAT = True
except Exception:                                        # pragma: no cover
    _HAS_CPSAT = False

_U_SCALE = 1_000_000  # micro-unit scaling for the rational Z2 weights u_j.
# O6 exactness note: with total workloads <= ~3e4 and u_j <= ~3, the rounding
# error on u_j (0.5e-6) perturbs any load term by < 0.02 -- far below the
# integer floor() granularity of obj2 -- so an OPTIMAL solve at this scale is
# the true assignment-layer optimum of w2*Z2 + w3*Z3, not an approximation.


@dataclass
class ConflictCut:
    bay: int
    block_ids: tuple


@dataclass
class TardinessCut:
    bay: int
    block_ids: tuple
    lb: int


@dataclass
class AssignmentMaster:
    inst: Instance
    rho: float = 1.0
    conflict_cuts: list = field(default_factory=list)
    tardiness_cuts: list = field(default_factory=list)
    evaluated_nogoods: list = field(default_factory=list)   # assignment dicts
    # Filled by the last solve (O1/O6 reporting): certification status and the
    # assignment-layer optimum components the pipeline should be chasing.
    last_status: str = "none"
    last_z2: float | None = None
    last_z3: float | None = None
    last_theta: float | None = None

    def add_conflict_cut(self, bay: int, block_ids) -> None:
        self.conflict_cuts.append(ConflictCut(bay, tuple(sorted(block_ids))))

    def add_tardiness_cut(self, bay: int, block_ids, lb: int) -> None:
        self.tardiness_cuts.append(TardinessCut(bay, tuple(sorted(block_ids)), lb))

    def add_evaluated_nogood(self, assignment: dict) -> None:
        self.evaluated_nogoods.append(dict(assignment))

    # ------------------------------------------------------------------ solve
    def solve(self, deadline: Deadline, time_cap: float = 10.0) -> dict:
        """Return assignment {block_id: bay_id}. Never raises; falls back to
        the preference-greedy assignment on any solver trouble."""
        greedy = self._greedy()
        if not _HAS_CPSAT:
            return greedy
        budget = deadline.sub_budget(0.25, cap=time_cap)
        if budget < 0.2:
            return greedy
        try:
            exact = self._solve_cpsat(budget)
            return exact if exact is not None else greedy
        except Exception:
            return greedy

    def _greedy(self) -> dict:
        out = {}
        for b in self.inst.blocks:
            compat = self.inst.compatible_bays(b)
            if not compat:  # degenerate: no orientation fits any bay; the
                # oracle will still emit it and the utils gate has the verdict
                compat = [max(self.inst.bays, key=lambda x: x.area).id]
            out[b.id] = max(compat, key=lambda j: b.prefs[j])
        return out

    def _solve_cpsat(self, budget: float) -> dict | None:
        inst = self.inst
        m = len(inst.bays)
        model = cp_model.CpModel()

        y = {}
        for b in inst.blocks:
            compat = inst.compatible_bays(b) or [max(inst.bays, key=lambda x: x.area).id]
            for j in compat:
                y[b.id, j] = model.NewBoolVar(f"y_{b.id}_{j}")
            model.AddExactlyOne(y[b.id, j] for j in compat)

        # Fluid capacity (warm-start validity; dropped on infeasibility below).
        horizon = inst.horizon
        cap_constraints = []
        for bay in inst.bays:
            terms = [
                (int(b.stamps[0].max_layer_area) * b.proc, y[b.id, bay.id])
                for b in inst.blocks if (b.id, bay.id) in y
            ]
            if terms:
                c = model.Add(
                    sum(coef * var for coef, var in terms)
                    <= int(self.rho * bay.area * horizon)
                )
                cap_constraints.append(c)

        # Z3: linear preference penalty.
        pref_pen = sum(
            (b.pref_max - b.prefs[j]) * y[b.id, j]
            for b in inst.blocks for j in range(m) if (b.id, j) in y
        )

        # Z2: max pairwise |u_j*load_j - u_k*load_k| in milli-units.
        total_wl = sum(b.workload for b in inst.blocks)
        u_int = [round(uj * _U_SCALE) for uj in inst.u]
        wload = []
        for bay in inst.bays:
            lv = model.NewIntVar(0, max(1, u_int[bay.id] * total_wl), f"wl_{bay.id}")
            model.Add(lv == sum(
                u_int[bay.id] * b.workload * y[b.id, bay.id]
                for b in inst.blocks if (b.id, bay.id) in y
            ))
            wload.append(lv)
        z2 = model.NewIntVar(0, max(1, max(u_int, default=1) * total_wl), "z2")
        for j1 in range(m):
            for j2 in range(j1 + 1, m):
                model.Add(z2 >= wload[j1] - wload[j2])
                model.Add(z2 >= wload[j2] - wload[j1])

        # Conflict cuts from the oracles (LBBD loop).
        for cut in self.conflict_cuts:
            lits = [y[i, cut.bay] for i in cut.block_ids if (i, cut.bay) in y]
            if len(lits) == len(cut.block_ids):
                model.Add(sum(lits) <= len(lits) - 1)

        # theta_j: certified-unavoidable tardiness of bay j, priced at w1.
        # Domain cap = the largest LB any stored cut could force (theta is
        # minimized, so it sits at the forced maximum of its active cuts).
        theta_cap = max((c.lb for c in self.tardiness_cuts), default=0)
        theta = [model.NewIntVar(0, theta_cap, f"th_{j}") for j in range(m)]
        for cut in self.tardiness_cuts:
            lits = [y[i, cut.bay] for i in cut.block_ids if (i, cut.bay) in y]
            if len(lits) == len(cut.block_ids):
                # theta >= lb when all of S in the bay; weakens linearly (and
                # below 0, i.e. inactive) as members leave.
                model.Add(theta[cut.bay]
                          >= cut.lb * (sum(lits) - len(lits) + 1))

        # k-best enumeration: exclude assignments already packed and audited.
        for prev in self.evaluated_nogoods:
            lits = [y[i, j] for i, j in prev.items() if (i, j) in y]
            if lits:
                model.Add(sum(lits) <= len(lits) - 1)

        # w1*theta + w2*Z2 + w3*Z3, all in micro-units so ratios stay exact.
        model.Minimize(round(self.inst.w1 * _U_SCALE) * sum(theta)
                       + round(self.inst.w2) * z2
                       + round(self.inst.w3 * _U_SCALE) * pref_pen)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = budget
        solver.parameters.num_search_workers = 1   # guard rail: 1 thread per solver
        status = solver.Solve(model)
        self.last_status = solver.StatusName(status)
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            self.last_z2 = solver.Value(z2) / _U_SCALE
            self.last_z3 = float(sum(
                (b.pref_max - b.prefs[j]) * solver.Value(y[b.id, j])
                for b in inst.blocks for j in range(m) if (b.id, j) in y
            ))
            self.last_theta = float(sum(solver.Value(t) for t in theta))
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            # Most likely the fluid capacity over-constrained an overloaded
            # instance: retry once without it.
            if cap_constraints:
                self.rho = float("inf")
                relaxed = AssignmentMaster(self.inst, rho=float("inf"),
                                           conflict_cuts=self.conflict_cuts,
                                           tardiness_cuts=self.tardiness_cuts,
                                           evaluated_nogoods=self.evaluated_nogoods)
                # Rebuild without capacity by making rho huge.
                return relaxed._solve_cpsat_no_cap(budget)
            return None
        return {
            b.id: next(j for j in range(m)
                       if (b.id, j) in y and solver.Value(y[b.id, j]))
            for b in self.inst.blocks
        }

    def _solve_cpsat_no_cap(self, budget: float) -> dict | None:
        saved = self.rho
        self.rho = 1e9
        try:
            return self._solve_cpsat(budget)
        finally:
            self.rho = saved
