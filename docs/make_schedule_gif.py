"""Render docs/schedule_prob1{,_dark}.gif — animated solved schedule.

Run from the repo root (python docs/make_schedule_gif.py) in the ogc2026
conda env. Needs the local-only train/ directory. Solves prob_1 with the
final submission's clean-slate solver line (certified optimal on this
instance, ~3 s), then animates the schedule day by day: blocks enter their
assigned bay at their placed position/orientation and exit when done.
"""
import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.patches import Polygon as MplPolygon, Rectangle

sys.path.insert(0, "ogc2026/SANDLE_FINAL_SUBMISSION")

THEMES = {
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e",
                  muted="#9a988f", bay="#2a78d6", bay_fill="#eef3fa",
                  block="#2a78d6", fresh="#eb6834", suffix=""),
    "dark": dict(surface="#1a1a19", ink="#ffffff", ink2="#c3c2b7",
                 muted="#8a887e", bay="#3987e5", bay_fill="#20262e",
                 block="#3987e5", fresh="#d95926", suffix="_dark"),
}


def solve():
    from solver import api
    import utils
    prob = json.load(open("train/prob_1.json"))
    sol = api.algorithm(prob, 15)
    chk = utils.check_feasibility(prob, sol)
    assert chk["feasible"], chk["violations"][:3]
    print(f"solved prob_1: objective {chk['objective']:.0f}")
    return prob, sol


def schedule_from(sol):
    """block_id -> (entry_t, exit_t, bay_id, x, y, orient_idx)"""
    entry, exit_ = {}, {}
    for t_str, ops in sol["operations"].items():
        for op in ops:
            if op["type"] == "ENTRY":
                entry[op["block_id"]] = (int(t_str), op["bay_id"],
                                         op["x"], op["y"], op["orient_idx"])
            else:
                exit_[op["block_id"]] = int(t_str)
    return {b: (t, exit_[b], bay, x, y, oi)
            for b, (t, bay, x, y, oi) in entry.items()}


def render(prob, sched, t):
    bays = prob["bays"]
    blocks = prob["blocks"]
    last_day = max(e for _, e, *_ in sched.values())

    fig = plt.figure(figsize=(7.6, 5.2), dpi=110, facecolor=t["surface"])
    ax = fig.add_axes([0.03, 0.10, 0.94, 0.80])

    def draw(day):
        ax.clear()
        ax.set_facecolor(t["surface"])
        y0 = 0.0
        offsets = []
        for j, b in enumerate(bays):
            ax.add_patch(Rectangle((0, y0), b["width"], b["height"],
                                   facecolor=t["bay_fill"],
                                   edgecolor=t["bay"], lw=1.5))
            ax.text(-1.2, y0 + b["height"] / 2, f"Bay {j}", rotation=90,
                    ha="center", va="center", color=t["ink2"], fontsize=9)
            offsets.append(y0)
            y0 += b["height"] + 4
        in_yard = 0
        for bid, (te, tx, bay, x, y, oi) in sched.items():
            if not (te <= day < tx):
                continue
            in_yard += 1
            color = t["fresh"] if te == day else t["block"]
            layers = blocks[bid]["shape"][oi]["layers"]
            n = len(layers)
            for li, lay in enumerate(layers):
                shade = 0.45 + 0.55 * (li + 1) / n
                ax.add_patch(MplPolygon(
                    [(x + px, offsets[bay] + y + py) for px, py in lay],
                    closed=True, facecolor=color, alpha=shade,
                    edgecolor=t["surface"], lw=0.7))
        ax.set_xlim(-3, max(b["width"] for b in bays) + 1)
        ax.set_ylim(-1.5, y0 - 2.5)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title(f"prob_1 · certified-optimal schedule · "
                     f"day {day:2d} / {last_day} · {in_yard} blocks in yard",
                     color=t["ink"], fontsize=10.5, loc="left", pad=8)
        ax.text(0, -0.06, "orange = entered today · schedule produced by the "
                          "LBBD solver line of the final submission",
                transform=ax.transAxes, color=t["muted"], fontsize=7.5)
        # timeline
        frac = day / last_day
        ax.plot([0, max(b["width"] for b in bays)], [-1.1, -1.1],
                color=t["bay_fill"], lw=3, solid_capstyle="butt", zorder=5)
        ax.plot([0, frac * max(b["width"] for b in bays)], [-1.1, -1.1],
                color=t["bay"], lw=3, solid_capstyle="butt", zorder=6)

    frames = list(range(last_day + 1)) + [last_day] * 4
    anim = FuncAnimation(fig, draw, frames=frames)
    out = f"docs/schedule_prob1{t['suffix']}.gif"
    anim.save(out, writer=PillowWriter(fps=5))
    plt.close(fig)
    print("written", out)


prob, sol = solve()
sched = schedule_from(sol)
for theme in THEMES.values():
    render(prob, sched, theme)
