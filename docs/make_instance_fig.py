"""Render docs/instance_prob1{,_dark}.png for the README from train/prob_1.json.

Run from the repo root (python docs/make_instance_fig.py) in the ogc2026
conda env. Needs the local-only train/ directory (not in this repo).
Emits a light and a dark variant; the README swaps them via <picture>.
"""
import json
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon, Rectangle

THEMES = {
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e",
                  muted="#9a988f", grid="#e7e6e1", blue="#2a78d6",
                  blue_light="#a9c8ec", orange="#eb6834", bay_fill="#eef3fa",
                  layer_note="darker = upper layer",
                  window_note="dark = processing time · orange = exceeds due date",
                  suffix=""),
    "dark": dict(surface="#1a1a19", ink="#ffffff", ink2="#c3c2b7",
                 muted="#8a887e", grid="#2e2d2b", blue="#3987e5",
                 blue_light="#2c4a6e", orange="#d95926", bay_fill="#20262e",
                 layer_note="brighter = upper layer",
                 window_note="bright = processing time · orange = exceeds due date",
                 suffix="_dark"),
}

d = json.load(open("train/prob_1.json"))
bays, blocks = d["bays"], d["blocks"]


def render(t):
    fig = plt.figure(figsize=(12, 4.6), dpi=160, facecolor=t["surface"])
    gs = fig.add_gridspec(1, 3, width_ratios=[1.05, 1.5, 1.35], wspace=0.32,
                          left=0.045, right=0.985, top=0.84, bottom=0.12)

    # --- Panel 1: bays to scale ---------------------------------------------
    ax = fig.add_subplot(gs[0])
    ax.set_facecolor(t["surface"])
    y = 0.0
    for j, b in enumerate(bays):
        ax.add_patch(Rectangle((0, y), b["width"], b["height"], fill=True,
                               facecolor=t["bay_fill"], edgecolor=t["blue"],
                               lw=1.6))
        ax.text(b["width"] / 2, y + b["height"] / 2, f"Bay {j}",
                ha="center", va="center", color=t["ink2"], fontsize=10)
        ax.text(b["width"] - 1, y + 1.2, f'{b["width"]} × {b["height"]}',
                ha="right", va="bottom", color=t["muted"], fontsize=7.5)
        y += b["height"] + 6
    ax.set_xlim(-2, max(b["width"] for b in bays) + 2)
    ax.set_ylim(-3, y - 3)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("Bays (to scale)", color=t["ink"], fontsize=11, loc="left",
                 pad=10)

    # --- Panel 2: gallery of block footprints (orientation 0) ---------------
    ax = fig.add_subplot(gs[1])
    ax.set_facecolor(t["surface"])
    picks = blocks[::9][:12]
    cols = 4
    cell = 22.0
    for k, blk in enumerate(picks):
        cx = (k % cols) * cell
        cy = -(k // cols) * cell
        layers = blk["shape"][0]["layers"]
        xs = [p[0] for lay in layers for p in lay]
        ys = [p[1] for lay in layers for p in lay]
        ox = cx - (min(xs) + max(xs)) / 2
        oy = cy - (min(ys) + max(ys)) / 2
        for li, lay in enumerate(layers):
            shade = 0.35 + 0.55 * (li + 1) / len(layers)
            ax.add_patch(MplPolygon([(x + ox, yy + oy) for x, yy in lay],
                                    closed=True, facecolor=t["blue"],
                                    alpha=shade, edgecolor=t["surface"],
                                    lw=0.8))
    ax.set_xlim(-cell * 0.6, cell * (cols - 0.4))
    ax.set_ylim(-cell * 2.6, cell * 0.6)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"Block footprints ({t['layer_note']})",
                 color=t["ink"], fontsize=11, loc="left", pad=16)

    # --- Panel 3: temporal windows ------------------------------------------
    ax = fig.add_subplot(gs[2])
    ax.set_facecolor(t["surface"])
    order = sorted(range(len(blocks)),
                   key=lambda i: (blocks[i]["release_time"],
                                  blocks[i]["due_date"]))
    for row, i in enumerate(order):
        b = blocks[i]
        r, due, p = b["release_time"], b["due_date"], b["processing_time"]
        ax.hlines(row, r, due, color=t["blue_light"], lw=1.1)
        ax.hlines(row, r, r + p, color=t["blue"], lw=1.1)
        if r + p > due:
            ax.hlines(row, due, r + p, color=t["orange"], lw=1.1)
    n = len(blocks)
    ax.set_ylim(n, -1)
    ax.set_xlabel("day", color=t["ink2"], fontsize=9)
    ax.set_ylabel(f"{n} blocks", color=t["ink2"], fontsize=9)
    ax.tick_params(colors=t["ink2"], labelsize=8)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.grid(axis="x", color=t["grid"], lw=0.7)
    ax.set_axisbelow(True)
    ax.set_title("Release → due windows", color=t["ink"], fontsize=11,
                 loc="left", pad=18)
    ax.text(0, 1.035, t["window_note"],
            transform=ax.transAxes, color=t["ink2"], fontsize=8.5)

    fig.suptitle("OGC 2026 training instance prob_1 — 2 bays, 100 blocks",
                 color=t["ink"], fontsize=13, x=0.045, ha="left")
    out = f"docs/instance_prob1{t['suffix']}.png"
    fig.savefig(out, facecolor=t["surface"])
    plt.close(fig)
    print("written", out)


for theme in THEMES.values():
    render(theme)
