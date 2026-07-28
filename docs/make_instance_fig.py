"""Render docs/instance_prob1.png for the README from train/prob_1.json.

Run from the repo root (python docs/make_instance_fig.py) in the ogc2026
conda env. Needs the local-only train/ directory (not in this repo).
"""
import json
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon, Rectangle

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#9a988f"
BLUE = "#2a78d6"
BLUE_LIGHT = "#a9c8ec"
ORANGE = "#eb6834"

d = json.load(open("train/prob_1.json"))
bays, blocks = d["bays"], d["blocks"]

fig = plt.figure(figsize=(12, 4.6), dpi=160, facecolor=SURFACE)
gs = fig.add_gridspec(1, 3, width_ratios=[1.05, 1.5, 1.35], wspace=0.32,
                      left=0.045, right=0.985, top=0.84, bottom=0.12)

# --- Panel 1: bays to scale -------------------------------------------------
ax = fig.add_subplot(gs[0])
ax.set_facecolor(SURFACE)
y = 0.0
for j, b in enumerate(bays):
    ax.add_patch(Rectangle((0, y), b["width"], b["height"], fill=True,
                           facecolor="#eef3fa", edgecolor=BLUE, lw=1.6))
    ax.text(b["width"] / 2, y + b["height"] / 2, f"Bay {j}",
            ha="center", va="center", color=INK2, fontsize=10)
    ax.text(b["width"] - 1, y + 1.2, f'{b["width"]} × {b["height"]}',
            ha="right", va="bottom", color=MUTED, fontsize=7.5)
    y += b["height"] + 6
ax.set_xlim(-2, max(b["width"] for b in bays) + 2)
ax.set_ylim(-3, y - 3)
ax.set_aspect("equal")
ax.axis("off")
ax.set_title("Bays (to scale)", color=INK, fontsize=11, loc="left", pad=10)

# --- Panel 2: gallery of block footprints (orientation 0) -------------------
ax = fig.add_subplot(gs[1])
ax.set_facecolor(SURFACE)
picks = blocks[::9][:12]  # 12 spread across the instance
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
                                closed=True, facecolor=BLUE, alpha=shade,
                                edgecolor=SURFACE, lw=0.8))
ax.set_xlim(-cell * 0.6, cell * (cols - 0.4))
ax.set_ylim(-cell * 2.6, cell * 0.6)
ax.set_aspect("equal")
ax.axis("off")
ax.set_title("Block footprints (darker = upper layer)",
             color=INK, fontsize=11, loc="left", pad=16)

# --- Panel 3: temporal windows ----------------------------------------------
ax = fig.add_subplot(gs[2])
ax.set_facecolor(SURFACE)
order = sorted(range(len(blocks)), key=lambda i: (blocks[i]["release_time"],
                                                  blocks[i]["due_date"]))
for row, i in enumerate(order):
    b = blocks[i]
    r, due, p = b["release_time"], b["due_date"], b["processing_time"]
    ax.hlines(row, r, due, color=BLUE_LIGHT, lw=1.1)
    ax.hlines(row, r, r + p, color=BLUE, lw=1.1)
    if r + p > due:
        ax.hlines(row, due, r + p, color=ORANGE, lw=1.1)
n = len(blocks)
ax.set_ylim(n, -1)
ax.set_xlabel("day", color=INK2, fontsize=9)
ax.set_ylabel(f"{n} blocks", color=INK2, fontsize=9)
ax.tick_params(colors=INK2, labelsize=8)
for s in ax.spines.values():
    s.set_visible(False)
ax.grid(axis="x", color="#e7e6e1", lw=0.7)
ax.set_axisbelow(True)
ax.set_title("Release → due windows", color=INK, fontsize=11, loc="left", pad=18)
ax.text(0, 1.035, "dark = processing time · orange = exceeds due date",
        transform=ax.transAxes, color=INK2, fontsize=8.5)

fig.suptitle("OGC 2026 training instance prob_1 — 2 bays, 100 blocks",
             color=INK, fontsize=13, x=0.045, ha="left")
fig.savefig("docs/instance_prob1.png", facecolor=SURFACE)
print("written docs/instance_prob1.png")
