#!/usr/bin/env python3
"""ai-excited-01 v5 — "Jellyfish Over the Terraces" (clean-room rebuild).

A giant translucent jellyfish drifts low over golden-hour rice terraces:
one colossal impossible subject in the wrong place, a tiny farmer with
lanterns below for scale, a visible sun, and a bowl-perspective terrace
foreground. Pure Python 3 stdlib, no network, no Pillow: a small software
rasterizer plus a hand-rolled PNG encoder. Deterministic: the same bytes
on every run.

Writes one image to $MAKEFUN_OUTPUT_DIR/entry.png (default /output).
1024x1024, well under the 1 MiB gate.
"""

import hashlib
import math
import os
import struct
import sys
import zlib

W = 1024
H = 1024

# ---------------------------------------------------------------- canvas
px = bytearray(W * H * 3)


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def set_px(x, y, r, g, b):
    if 0 <= x < W and 0 <= y < H:
        i = (y * W + x) * 3
        px[i] = r
        px[i + 1] = g
        px[i + 2] = b


def blend_px(x, y, r, g, b, a):
    """Blend color (r,g,b) over the pixel at (x,y) with alpha a in [0,1]."""
    if a <= 0.0 or not (0 <= x < W and 0 <= y < H):
        return
    i = (y * W + x) * 3
    if a >= 1.0:
        px[i] = r
        px[i + 1] = g
        px[i + 2] = b
        return
    ia = 1.0 - a
    px[i] = int(r * a + px[i] * ia + 0.5)
    px[i + 1] = int(g * a + px[i + 1] * ia + 0.5)
    px[i + 2] = int(b * a + px[i + 2] * ia + 0.5)


def hline(y, x0, x1, r, g, b):
    """Solid horizontal span, inclusive, clipped."""
    if y < 0 or y >= H:
        return
    if x0 < 0:
        x0 = 0
    if x1 >= W:
        x1 = W - 1
    if x1 < x0:
        return
    i = (y * W + x0) * 3
    n = x1 - x0 + 1
    px[i:i + n * 3] = bytes((r, g, b)) * n


def hline_a(y, x0, x1, r, g, b, a):
    """Alpha-blended horizontal span, inclusive, clipped."""
    if a <= 0.0 or y < 0 or y >= H:
        return
    if x0 < 0:
        x0 = 0
    if x1 >= W:
        x1 = W - 1
    if x1 < x0:
        return
    if a >= 1.0:
        hline(y, x0, x1, r, g, b)
        return
    ia = 1.0 - a
    base = (y * W + x0) * 3
    for x in range(x0, x1 + 1):
        i = base + (x - x0) * 3
        px[i] = int(r * a + px[i] * ia + 0.5)
        px[i + 1] = int(g * a + px[i + 1] * ia + 0.5)
        px[i + 2] = int(b * a + px[i + 2] * ia + 0.5)


def disc(cx, cy, rad, r, g, b, a=1.0):
    """Filled disc, solid or alpha-blended."""
    if rad <= 0:
        return
    for dy in range(-rad, rad + 1):
        y = cy + dy
        if 0 <= y < H:
            dx = int(math.sqrt(rad * rad - dy * dy))
            if a >= 1.0:
                hline(y, cx - dx, cx + dx, r, g, b)
            else:
                hline_a(y, cx - dx, cx + dx, r, g, b, a)


def line(x0, y0, x1, y1, r, g, b, width=1, a=1.0):
    """DDA line; width>1 plots a small disc at each step."""
    steps = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
    if steps <= 1:
        if width <= 1:
            blend_px(x0, y0, r, g, b, a)
        else:
            disc(x0, y0, width // 2, r, g, b, a)
        return
    rad = width // 2
    for i in range(steps + 1):
        t = i / steps
        x = int(x0 + (x1 - x0) * t + 0.5)
        y = int(y0 + (y1 - y0) * t + 0.5)
        if width <= 1:
            blend_px(x, y, r, g, b, a)
        else:
            disc(x, y, rad, r, g, b, a)


def polyfill(points, r, g, b):
    """Scanline fill of a simple polygon (list of (x, y))."""
    if len(points) < 3:
        return
    ys = [p[1] for p in points]
    ymin = max(0, min(ys))
    ymax = min(H - 1, max(ys))
    edges = []
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        if y1 != y2:
            edges.append((x1, y1, x2, y2))
    for y in range(ymin, ymax + 1):
        xs = []
        for (x1, y1, x2, y2) in edges:
            if (y1 <= y < y2) or (y2 <= y < y1):
                xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            hline(y, int(xs[i] + 0.5), int(xs[i + 1] + 0.5), r, g, b)


def radial_glow(cx, cy, rx, ry, r, g, b, peak, step=1):
    """Soft elliptical glow: alpha falls off quadratically to the edge.

    step=2 samples every other pixel (2x2 blocks) — invisible for a soft
    glow, much faster for large halos.
    """
    if peak <= 0.0:
        return
    for dy in range(-ry, ry + 1, step):
        y = cy + dy
        if y < 0 or y >= H:
            continue
        ny = dy / ry
        rem = 1.0 - ny * ny
        if rem <= 0.0:
            continue
        dxmax = int(rx * math.sqrt(rem))
        for dx in range(-dxmax, dxmax + 1, step):
            nx = dx / rx
            d2 = nx * nx + ny * ny
            if d2 >= 1.0:
                continue
            a = peak * (1.0 - d2)
            if step == 1:
                blend_px(cx + dx, y, r, g, b, a)
            else:
                for ox in range(step):
                    for oy in range(step):
                        blend_px(cx + dx + ox, y + oy, r, g, b, a)


def lerp_color(c1, c2, t):
    return (int(c1[0] + (c2[0] - c1[0]) * t + 0.5),
            int(c1[1] + (c2[1] - c1[1]) * t + 0.5),
            int(c1[2] + (c2[2] - c1[2]) * t + 0.5))


def gradient_row(stops, y, y0, y1):
    """Multi-stop vertical gradient color at row y in [y0, y1]."""
    t = (y - y0) / max(1, y1 - y0)
    t = _clamp(t, 0.0, 1.0)
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if t0 <= t <= t1:
            f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return lerp_color(c0, c1, f)
    return stops[-1][1]


# ------------------------------------------------------------- PNG output
def _chunk(typ, data):
    out = struct.pack(">I", len(data)) + typ + data
    out += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
    return out


def encode_png(w, h, buf):
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filter: none
        raw += buf[y * w * 3:(y + 1) * w * 3]
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 6))
            + _chunk(b"IEND", b""))


def main():
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(outdir, exist_ok=True)
    draw()
    data = encode_png(W, H, px)
    path = os.path.join(outdir, "entry.png")
    with open(path, "wb") as f:
        f.write(data)
    print("wrote %s (%d bytes, sha256 %s)"
          % (path, len(data), hashlib.sha256(data).hexdigest()))


# (draw() is defined below; the __main__ guard goes at the very end.)

# ------------------------------------------------------------------- sky
SKY_STOPS = [
    (0.00, (26, 14, 58)),     # deep violet night at the top
    (0.20, (58, 32, 96)),
    (0.42, (110, 52, 130)),   # magenta-purple
    (0.62, (168, 62, 118)),
    (0.80, (214, 92, 78)),    # orange-red
    (0.95, (238, 138, 60)),   # golden orange at the horizon
    (1.00, (244, 150, 66)),
]

HORIZON = 660  # where the sky meets the terraces


def draw_sky():
    for y in range(HORIZON + 1):
        r, g, b = gradient_row(SKY_STOPS, y, 0, HORIZON)
        hline(y, 0, W - 1, r, g, b)


def draw_stars():
    # Deterministic LCG — same sky on every run, no random module state.
    seed = 1234567
    for _ in range(90):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        x = seed % W
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        y = seed % 300
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        bright = 150 + seed % 105
        # Keep stars out of the bright dome halo area.
        if 180 < x < 845 and y < 130:
            continue
        set_px(x, y, bright, bright, min(255, bright + 20))
        if seed % 7 == 0:
            set_px(x + 1, y, bright - 40, bright - 40, bright - 20)


def draw_birds():
    # Tiny dark chevrons, far away, for scale and life in the sky.
    for (bx, by, s) in [(185, 195, 9), (255, 172, 7), (700, 118, 8),
                        (858, 193, 9), (742, 148, 6)]:
        line(bx - s, by, bx, by - 4, 30, 18, 48, width=2)
        line(bx, by - 4, bx + s, by, 30, 18, 48, width=2)


# ------------------------------------------------------------------- sun
def draw_sun():
    # Low golden sun at the right, mostly hidden behind the far ridge —
    # only its glowing cap peeks above the silhouette.
    sx, sy, sr = 768, 612, 48
    radial_glow(sx, sy, 110, 75, 255, 190, 110, 0.35, step=2)
    radial_glow(sx, sy, 70, 50, 255, 215, 140, 0.45, step=2)
    disc(sx, sy, sr, 255, 233, 168)
    disc(sx, sy, sr - 8, 255, 240, 190)


# -------------------------------------------------------------- mountains
def draw_mountains():
    # Far ridge: dark violet, jagged peaks.
    far = [(0, 665), (90, 625), (180, 640), (300, 595), (420, 620),
           (540, 585), (650, 610), (760, 600), (870, 570), (960, 600),
           (1024, 590), (1024, 668), (0, 668)]
    polyfill(far, 36, 22, 64)
    # Near ridge: a touch lighter, softer and lower.
    near = [(0, 668), (150, 645), (320, 655), (500, 635), (680, 650),
            (850, 640), (1024, 655), (1024, 672), (0, 672)]
    polyfill(near, 58, 42, 94)


# --------------------------------------------------------------- terraces
# Terrace boundary curves: each sags down toward the middle (bowl
# perspective). y(x) = edge + sag * (1 - ((x-512)/512)^2).
TERRACE_CURVES = [
    (652, 34), (688, 40), (726, 46), (766, 52),
    (810, 58), (856, 64), (904, 70), (954, 76),
]
TERRACE_GREENS = [(53, 112, 76), (90, 162, 79), (74, 143, 67),
                  (90, 162, 79), (74, 143, 67), (90, 162, 79),
                  (74, 143, 67), (90, 162, 79)]
TERRACE_BASE = (63, 122, 68)
TERRACE_GOLD = (232, 200, 122)


def terrace_y(edge, sag, x):
    t = (x - 512) / 512.0
    return edge + sag * (1.0 - t * t)


def draw_terraces():
    # Base fill closes any gap at the horizon line.
    for y in range(HORIZON, H):
        hline(y, 0, W - 1, *TERRACE_BASE)
    # Each band is the region between two curves. On a row y, band i
    # covers |t| in [u_top, u_bot): two symmetric horizontal spans.
    for i in range(len(TERRACE_CURVES)):
        et, st = TERRACE_CURVES[i]
        if i + 1 < len(TERRACE_CURVES):
            eb, sb = TERRACE_CURVES[i + 1]
        else:
            eb, sb = H + 40, 76  # last band runs off the bottom edge
        color = TERRACE_GREENS[i]
        y_lo = et
        y_hi = min(H - 1, int(eb + sb) + 1)
        for y in range(y_lo, y_hi + 1):
            # |t| >= u_top where the top curve is at or above this row.
            if y >= et + st:
                u_top = 0.0
            elif y <= et:
                u_top = 1.0
            else:
                u_top = math.sqrt(max(0.0, 1.0 - (y - et) / st))
            # |t| < u_bot where the bottom curve is below this row.
            if y <= eb:
                u_bot = 1.0
            elif y >= eb + sb:
                u_bot = 0.0
            else:
                u_bot = math.sqrt(max(0.0, 1.0 - (y - eb) / sb))
            if u_bot <= u_top:
                continue
            x_in0 = int(512 - 512 * u_bot)
            x_in1 = int(512 - 512 * u_top)
            x_out0 = int(512 + 512 * u_top)
            x_out1 = int(512 + 512 * u_bot)
            hline(y, x_in0, x_in1, *color)
            hline(y, x_out0, x_out1, *color)
    # Golden waterline along every curve.
    for (edge, sag) in TERRACE_CURVES:
        for x in range(0, W, 1):
            y = int(terrace_y(edge, sag, x) + 0.5)
            set_px(x, y, *TERRACE_GOLD)
            if y + 1 < H:
                blend_px(x, y + 1, 240, 214, 140, 0.7)
    # The jellyfish's glow shimmering on the flooded terraces.
    radial_glow(512, 800, 270, 55, 200, 180, 235, 0.22, step=2)

# -------------------------------------------------------------- jellyfish
# Bell: a true half-ellipse, smooth per-row gradient, darker and more
# saturated toward the rim edge. Center (512, 332), radii (335, 245).
DOME_CX = 512
DOME_CY = 332      # rim line
DOME_A = 335       # horizontal radius
DOME_B = 245       # vertical radius
DOME_TOP = (238, 228, 252)    # pale lavender-white at the crown
DOME_MID = (206, 176, 236)
DOME_LOW = (172, 138, 214)
DOME_EDGE = (118, 78, 176)    # saturated violet toward the edge


def dome_row_color(y):
    """Vertical gradient of the bell at row y (top -> rim)."""
    t = (y - (DOME_CY - DOME_B)) / DOME_B  # 0 at crown, 1 at rim
    if t < 0.5:
        return lerp_color(DOME_TOP, DOME_MID, t * 2.0)
    return lerp_color(DOME_MID, DOME_LOW, (t - 0.5) * 2.0)


def draw_dome():
    # Halo of light breathing above the bell, drawn first so the bell
    # sits inside it.
    radial_glow(512, 120, 400, 150, 190, 150, 235, 0.22, step=2)
    for y in range(DOME_CY - DOME_B, DOME_CY + 1):
        t = (y - DOME_CY) / DOME_B  # -1 at crown .. 0 at rim
        hw = DOME_A * math.sqrt(max(0.0, 1.0 - t * t))
        if hw < 1:
            continue
        base = dome_row_color(y)
        x0 = int(DOME_CX - hw)
        x1 = int(DOME_CX + hw)
        row = y * W
        for x in range(x0, x1 + 1):
            u = abs(x - DOME_CX) / hw  # 0 centre .. 1 edge
            e = u * u * 0.55
            i = (row + x) * 3
            px[i] = int(base[0] + (DOME_EDGE[0] - base[0]) * e + 0.5)
            px[i + 1] = int(base[1] + (DOME_EDGE[1] - base[1]) * e + 0.5)
            px[i + 2] = int(base[2] + (DOME_EDGE[2] - base[2]) * e + 0.5)
    # Bright core glowing inside the crown of the bell.
    radial_glow(512, 165, 170, 85, 250, 246, 255, 0.42, step=1)
    radial_glow(512, 165, 110, 55, 255, 255, 255, 0.30, step=1)


def draw_ribs():
    # Ribs radiate from a point inside the bell out to its rim, each
    # bowed slightly so they read as curved membrane ribs, not spokes.
    ax, ay = 512, 200
    for deg in (200, 220, 240, 260, 280, 300, 320, 340):
        th = math.radians(deg)
        rx = int(DOME_CX + DOME_A * math.cos(th) + 0.5)
        ry = int(DOME_CY + DOME_B * math.sin(th) + 0.5)
        mx = (ax + rx) // 2
        my = (ay + ry) // 2
        # Bow the midpoint sideways, away from the bell's centre line.
        bow = 14 if rx >= ax else -14
        line(ax, ay, mx + bow, my, 240, 170, 205, width=2, a=0.6)
        line(mx + bow, my, rx, ry, 240, 170, 205, width=2, a=0.6)


def draw_skirt():
    # Wavy translucent frill along the rim, with a bright rim line and
    # small pale dots studded along it.
    for x in range(DOME_CX - DOME_A, DOME_CX + DOME_A + 1, 2):
        y = int(DOME_CY + 6 + 5 * math.sin(x * 2 * math.pi / 48.0) + 0.5)
        disc(x, y, 3, 235, 150, 195, a=0.9)
    hline(DOME_CY, DOME_CX - DOME_A, DOME_CX + DOME_A, 250, 190, 215)
    hline_a(DOME_CY + 1, DOME_CX - DOME_A, DOME_CX + DOME_A,
            250, 190, 215, 0.6)
    for x in range(DOME_CX - DOME_A + 18, DOME_CX + DOME_A, 42):
        disc(x, DOME_CY - 4, 2, 255, 235, 245, a=0.85)


def draw_arms():
    # Five thick oral arms: wavy pink ribbons with a lighter core,
    # tapering gently toward the tip, hanging from the rim.
    for k, base_x in enumerate((335, 425, 512, 600, 690)):
        phase = k * 1.7
        length = 565 + (k % 2) * 22 + (18 if k == 2 else 0)
        y0 = DOME_CY + 12
        y = y0
        while y <= length:
            frac = (y - y0) / max(1, length - y0)
            outer = 11 - int(4 * frac)
            inner = max(3, outer - 6)
            x = int(base_x
                    + 14 * math.sin((y - DOME_CY) * 0.030 + phase)
                    + 6 * math.sin((y - DOME_CY) * 0.011 + phase * 0.5)
                    + 0.5)
            disc(x, y, outer, 244, 160, 198, a=0.92)
            disc(x, y, inner, 255, 205, 225, a=0.95)
            y += 2


def draw_tentacles():
    # Many thin, delicate tentacles between and beside the oral arms.
    seed = 987654
    for n in range(38):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        base_x = 200 + (seed % 630)
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        length = 520 + (seed % 85)
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        amp = 6 + (seed % 7)
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        phase = (seed % 628) / 100.0
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        drift = ((seed % 41) - 20) / 10.0
        y = DOME_CY + 8
        while y <= length:
            x = int(base_x + amp * math.sin((y - DOME_CY) * 0.045 + phase)
                    + drift * (y - DOME_CY) / 200.0 + 0.5)
            blend_px(x, y, 245, 200, 220, 0.85)
            if n % 5 == 0:
                blend_px(x + 1, y, 245, 200, 220, 0.6)
            y += 2

# ------------------------------------------------- farmer, lanterns, scale
DARK = (24, 14, 38)


def draw_lantern(x, base_y):
    # Thin dark post with a warm glowing orb on top.
    top_y = base_y - 26
    line(x, base_y, x, top_y, *DARK, width=2)
    radial_glow(x, top_y, 20, 20, 255, 184, 77, 0.55, step=1)
    disc(x, top_y, 6, 255, 210, 122)
    disc(x, top_y, 3, 255, 238, 190)


def draw_farmer(x, feet_y):
    # Tiny farmer in a conical hat, standing on a terrace line.
    # Hat (golden cone).
    polyfill([(x - 12, feet_y - 22), (x + 12, feet_y - 22),
              (x, feet_y - 34)], 216, 162, 74)
    # Body: dark robe.
    polyfill([(x - 5, feet_y - 22), (x + 5, feet_y - 22),
              (x + 4, feet_y), (x - 4, feet_y)], *DARK)
    # Legs.
    line(x - 2, feet_y - 1, x - 3, feet_y + 4, *DARK, width=2)
    line(x + 2, feet_y - 1, x + 3, feet_y + 4, *DARK, width=2)


def draw_scale_figures():
    # Farmer + three lanterns on the 6th terrace curve (edge 856, sag 64),
    # and a second tiny figure far down the field at bottom right.
    for lx in (355, 500, 560):
        draw_lantern(lx, int(terrace_y(856, 64, lx) + 0.5))
    draw_farmer(410, int(terrace_y(856, 64, 410) + 0.5))
    fx, fy = 880, 972
    polyfill([(fx - 5, fy - 16), (fx + 5, fy - 16),
              (fx + 4, fy), (fx - 4, fy)], *DARK)
    disc(fx, fy - 19, 3, *DARK)


# ------------------------------------------------------------------ draw
def draw():
    draw_sky()
    draw_stars()
    draw_sun()
    draw_mountains()
    draw_birds()
    draw_terraces()
    draw_dome()
    draw_ribs()
    draw_skirt()
    draw_arms()
    draw_tentacles()
    draw_scale_figures()


if __name__ == "__main__":
    main()
