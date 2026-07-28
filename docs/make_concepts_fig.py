"""Render the plain-language concept figures for the README:

  docs/concepts_block{,_dark}.png  — anatomy of a block: layers + orientations
  docs/concepts_alns{,_dark}.png   — ALNS destroy & repair, illustrated

Run from the repo root (python docs/make_concepts_fig.py) in the ogc2026
conda env. Needs the local-only train/ directory (real geometry from
train/prob_1.json). The ALNS triptych is a conceptual illustration: real
block shapes, hand-placed to show the destroy/repair move — not a solver
trace. Shapes are placed inside disjoint boxes, so no two blocks overlap.
"""
import json
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon, Rectangle

THEMES = {
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e",
                  muted="#9a988f", grid="#e7e6e1", bay="#2a78d6",
                  bay_fill="#eef3fa", block="#2a78d6", accent="#eb6834",
                  ghost="#b7b5ab", suffix=""),
    "dark": dict(surface="#1a1a19", ink="#ffffff", ink2="#c3c2b7",
                 muted="#8a887e", grid="#2e2d2b", bay="#3987e5",
                 bay_fill="#20262e", block="#3987e5", accent="#d95926",
                 ghost="#55534c", suffix="_dark"),
}

FONT = ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"]

d = json.load(open("train/prob_1.json"))
blocks = d["blocks"]
FEATURE = 2  # 2 layers, 8 orientations


def poly_bounds(layers):
    xs = [p[0] for lay in layers for p in lay]
    ys = [p[1] for lay in layers for p in lay]
    return min(xs), min(ys), max(xs), max(ys)


def fit_in_box(layers, bx, by, bw, bh):
    """Scale/translate layers to fit inside the (bx,by,bw,bh) box, centered."""
    x0, y0, x1, y1 = poly_bounds(layers)
    s = min(bw / (x1 - x0), bh / (y1 - y0))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    tx, ty = bx + bw / 2, by + bh / 2
    return [[((x - cx) * s + tx, (y - cy) * s + ty) for x, y in lay]
            for lay in layers]


def draw_block(ax, layers, color, surface, alpha0=0.45, lw=0.8, ls="-",
               fill=True):
    n = len(layers)
    for li, lay in enumerate(layers):
        shade = alpha0 + (1 - alpha0) * (li + 1) / n
        ax.add_patch(MplPolygon(lay, closed=True,
                                facecolor=color if fill else "none",
                                alpha=shade if fill else 1.0,
                                edgecolor=surface if fill else color,
                                lw=lw, linestyle=ls))


# ---------------------------------------------------------------------------
# Figure 1 — anatomy of a block
# ---------------------------------------------------------------------------
def render_block_fig(t):
    blk = blocks[FEATURE]
    fig = plt.figure(figsize=(12, 4.6), dpi=160, facecolor=t["surface"])
    gs = fig.add_gridspec(1, 2, width_ratios=[1, 1.9], wspace=0.14,
                          left=0.03, right=0.99, top=0.80, bottom=0.06)

    # left: exploded layers
    ax = fig.add_subplot(gs[0])
    ax.set_facecolor(t["surface"])
    layers = blk["shape"][0]["layers"]
    base = fit_in_box(layers, 0, 0, 10, 10)
    n = len(base)
    lift = 8.0
    for li in range(n):
        dy = li * lift
        lay = [(x, y + dy) for x, y in base[li]]
        shade = 0.45 + 0.55 * (li + 1) / n
        ax.add_patch(MplPolygon(lay, closed=True, facecolor=t["block"],
                                alpha=shade, edgecolor=t["surface"], lw=0.9))
        x1 = max(p[0] for p in lay)
        ymid = sum(p[1] for p in lay) / len(lay)
        label = "upper layer" if li else "base layer (footprint)"
        ax.text(x1 + 0.7, ymid, label, color=t["ink2"], fontsize=9,
                va="center", family=FONT)
    ax.set_xlim(-1.5, 16)
    ax.set_ylim(-1.5, 10 + lift * (n - 1))
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("A block = stacked polygonal layers",
                 color=t["ink"], fontsize=11, loc="left", pad=12, family=FONT)

    # right: the 8 orientations
    ax = fig.add_subplot(gs[1])
    ax.set_facecolor(t["surface"])
    n_or = len(blk["shape"])
    cell = 11.0
    for oi in range(n_or):
        col, row = oi % 4, oi // 4
        bx, by = col * cell, -(row) * cell
        lays = fit_in_box(blk["shape"][oi]["layers"], bx, by, 8.6, 8.6)
        draw_block(ax, lays, t["block"], t["surface"])
        ax.text(bx + 4.3, by - 1.4, f"orientation {oi}", ha="center",
                color=t["muted"], fontsize=8, family=FONT)
    ax.set_xlim(-1, cell * 4 - 1)
    ax.set_ylim(-cell - 2.6, 9.6)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("…that can be placed in any of its allowed orientations "
                 "(block 2 of prob_1, all 8 shown)",
                 color=t["ink"], fontsize=11, loc="left", pad=12, family=FONT)

    out = f"docs/concepts_block{t['suffix']}.png"
    fig.savefig(out, facecolor=t["surface"])
    plt.close(fig)
    print("written", out)


# ---------------------------------------------------------------------------
# Figure 2 — ALNS destroy & repair triptych
# ---------------------------------------------------------------------------
BAY_W, BAY_H = 24, 10
PICKS = [0, 9, 27, 45, 63, 81, 36, 99]  # real shapes, varied silhouettes

# (block, box) placements per panel; boxes are disjoint within each panel
PANEL1 = {0: (0.6, 0.6, 7.0, 4.6), 1: (9.0, 0.8, 5.6, 3.8),
          2: (16.4, 0.6, 4.6, 5.6), 3: (0.8, 6.0, 4.6, 3.4),
          4: (6.6, 5.9, 4.0, 3.6), 5: (12.4, 5.6, 3.4, 3.8)}
WAITING = [6, 7]  # can't fit -> late
DESTROYED = [1, 3, 4]
PANEL3 = {0: (0.4, 0.4, 7.0, 4.6), 2: (17.6, 0.4, 4.4, 5.4),
          5: (0.5, 5.6, 3.2, 3.8), 1: (4.4, 5.6, 5.4, 3.6),
          3: (10.4, 5.8, 4.4, 3.4), 4: (15.4, 6.0, 3.8, 3.6),
          6: (8.0, 0.5, 4.4, 4.2), 7: (13.0, 0.6, 3.8, 4.0)}


def draw_bay(ax, t):
    ax.add_patch(Rectangle((0, 0), BAY_W, BAY_H, facecolor=t["bay_fill"],
                           edgecolor=t["bay"], lw=1.5))


def render_alns_fig(t):
    fig = plt.figure(figsize=(12, 3.3), dpi=160, facecolor=t["surface"])
    gs = fig.add_gridspec(1, 3, wspace=0.06, left=0.015, right=0.985,
                          top=0.64, bottom=0.09)
    titles = ["1 · current schedule\ntwo blocks don't fit — they run late",
              "2 · destroy\nremove a few placements at random",
              "3 · repair\nreinsert everything, better"]

    for p in range(3):
        ax = fig.add_subplot(gs[p])
        ax.set_facecolor(t["surface"])
        draw_bay(ax, t)
        if p in (0, 1):
            for k, box in PANEL1.items():
                destroyed = (p == 1 and k in DESTROYED)
                lays = fit_in_box(blocks[PICKS[k]]["shape"][0]["layers"], *box)
                if destroyed:
                    draw_block(ax, lays, t["ghost"], t["surface"],
                               ls=(0, (3, 2)), fill=False, lw=1.1)
                else:
                    draw_block(ax, lays, t["block"], t["surface"])
            for j, k in enumerate(WAITING):
                lays = fit_in_box(blocks[PICKS[k]]["shape"][0]["layers"],
                                  25.6, 0.6 + 5.0 * j, 3.6, 3.6)
                draw_block(ax, lays, t["accent"], t["surface"])
            ax.text(27.4, 9.6, "waiting\n(late)", ha="center", va="top",
                    color=t["accent"], fontsize=8, family=FONT)
        else:
            for k, box in PANEL3.items():
                lays = fit_in_box(blocks[PICKS[k]]["shape"][0]["layers"], *box)
                color = t["accent"] if k in WAITING else t["block"]
                draw_block(ax, lays, color, t["surface"])
        ax.set_xlim(-0.5, 29.5)
        ax.set_ylim(-0.8, 10.8)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title(titles[p], color=t["ink"], fontsize=10, loc="left",
                     pad=10, family=FONT, linespacing=1.4)

    fig.suptitle("ALNS in one move: destroy part of a solution, repair it "
                 "into a better one — thousands of times per minute",
                 color=t["ink"], fontsize=12, x=0.015, ha="left", family=FONT)
    fig.text(0.015, 0.015, "conceptual illustration with real prob_1 block "
                           "shapes — not a solver trace",
             color=t["muted"], fontsize=7.5, family=FONT)
    out = f"docs/concepts_alns{t['suffix']}.png"
    fig.savefig(out, facecolor=t["surface"])
    plt.close(fig)
    print("written", out)


for theme in THEMES.values():
    render_block_fig(theme)
    render_alns_fig(theme)
