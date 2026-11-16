#!/usr/bin/env python3
"""ai-excited-01 v6 -- clean-room rebuild.

Draws "Jellyfish Over the Terraces": one colossal glowing jellyfish
drifting low over terraced rice fields at dusk, a tiny farmer and three
lanterns below for scale.

Pure Python 3 standard library. A small scanline rasterizer draws the
picture into an RGB buffer (sky gradient, sun, mountains, terraced
water, the jellyfish bell with ribs, wavy oral skirt, five oral arms
and trailing tentacles, shimmer reflections, farmer silhouette and
lanterns), then a hand-rolled encoder writes a PNG. No network, no
clock, no randomness: two runs write byte-identical files.

Usage:
    mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
Output: <MAKEFUN_OUTPUT_DIR>/entry.png (1024x1024, under 1 MiB).
"""

import math
import os
import struct
import zlib

W = 1024
H = 1024

buf = bytearray(W * H * 3)


# ---------------------------------------------------------------- helpers

def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return int(a + (b - a) * t)


def mix(c1, c2, t):
    """Blend two RGB triples, t in [0, 1]."""
    return (lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t))


def fill_span(y, x0, x1, rgb):
    """Opaque horizontal span (fast slice fill)."""
    if y < 0 or y >= H:
        return
    x0 = _clamp(x0, 0, W)
    x1 = _clamp(x1, 0, W)
    if x0 >= x1:
        return
    r, g, b = rgb
    row = y * W * 3
    buf[row + x0 * 3: row + x1 * 3] = bytes((r, g, b)) * (x1 - x0)


def blend_span(y, x0, x1, rgb, alpha):
    """Translucent horizontal span, alpha 0..255."""
    if y < 0 or y >= H or alpha <= 0:
        return
    if alpha >= 255:
        fill_span(y, x0, x1, rgb)
        return
    x0 = _clamp(x0, 0, W)
    x1 = _clamp(x1, 0, W)
    if x0 >= x1:
        return
    r, g, b = rgb
    ia = 255 - alpha
    base = (y * W + x0) * 3
    for i in range(x1 - x0):
        o = base + i * 3
        buf[o] = (r * alpha + buf[o] * ia) // 255
        buf[o + 1] = (g * alpha + buf[o + 1] * ia) // 255
        buf[o + 2] = (b * alpha + buf[o + 2] * ia) // 255


def fill_vspan(x, y0, y1, rgb):
    """Opaque vertical span."""
    if x < 0 or x >= W:
        return
    y0 = _clamp(y0, 0, H)
    y1 = _clamp(y1, 0, H)
    r, g, b = rgb
    for y in range(y0, y1):
        o = (y * W + x) * 3
        buf[o] = r
        buf[o + 1] = g
        buf[o + 2] = b


def disc(cx, cy, rad, rgb, alpha=255):
    """Filled circle (translucent when alpha < 255)."""
    if rad <= 0:
        return
    for y in range(cy - rad, cy + rad + 1):
        dy = y - cy
        rest = rad * rad - dy * dy
        if rest < 0:
            continue
        dx = math.isqrt(rest)
        if alpha >= 255:
            fill_span(y, cx - dx, cx + dx + 1, rgb)
        else:
            blend_span(y, cx - dx, cx + dx + 1, rgb, alpha)


def ellipse_rows(cx, cy, rx, ry):
    """Yield (y, x0, x1) spans of a filled ellipse."""
    for y in range(cy - ry, cy + ry + 1):
        t = (y - cy) / ry
        rest = 1.0 - t * t
        if rest < 0:
            continue
        hw = int(rx * math.sqrt(rest))
        yield y, cx - hw, cx + hw + 1


def polyline_disc(points, rad, rgb, alpha=255, step=3):
    """Thick wavy line: discs along a list of (x, y) points."""
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        dist = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(dist / step))
        for i in range(n + 1):
            t = i / n
            disc(int(lerp(x0, x1, t)), int(lerp(y0, y1, t)), rad, rgb, alpha)


# ------------------------------------------------------------------- sky

def draw_sky():
    """Dusk gradient: deep indigo top, magenta band, burning orange horizon."""
    stops = [
        (0.00, (24, 16, 62)),
        (0.22, (58, 26, 96)),
        (0.42, (128, 48, 118)),
        (0.58, (214, 84, 96)),
        (0.72, (255, 138, 62)),
        (0.82, (255, 186, 92)),
        (1.00, (255, 205, 120)),
    ]
    horizon = 560
    for y in range(horizon + 1):
        t = y / horizon
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1:
                f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
                fill_span(y, 0, W, mix(c0, c1, f))
                break


def draw_sun():
    """Low sun with a wide warm halo, right of the jellyfish."""
    cx, cy = 768, 330
    disc(cx, cy, 150, (255, 150, 70), 26)
    disc(cx, cy, 105, (255, 170, 80), 48)
    disc(cx, cy, 76, (255, 196, 100), 110)
    disc(cx, cy, 58, (255, 214, 130), 255)
    disc(cx, cy, 46, (255, 238, 190), 255)
    disc(cx, cy, 34, (255, 248, 220), 255)


def draw_clouds():
    """A few long dusk clouds, pink-lit underneath."""
    for (cx, cy, rx, ry, alpha) in [
        (210, 150, 190, 16, 70),
        (300, 132, 130, 11, 60),
        (820, 130, 170, 13, 66),
        (880, 210, 210, 15, 58),
        (150, 260, 150, 12, 52),
        (620, 120, 120, 10, 55),
    ]:
        for y, x0, x1 in ellipse_rows(cx, cy, rx, ry):
            blend_span(y, x0, x1, (255, 150, 130), alpha)
        for y, x0, x1 in ellipse_rows(cx, cy + ry // 2, rx, ry // 2):
            blend_span(y, x0, x1, (255, 110, 110), alpha // 2)


def draw_mountains():
    """Dark ridge silhouettes along the horizon."""
    for y in range(470, 562):
        for x0, x1 in _mountain_spans(y):
            fill_span(y, x0, x1, (52, 30, 84))


def _mountain_spans(y):
    """Two overlapping ridge profiles, returned as x-intervals per row."""
    spans = []
    # Far ridge: a slow sine silhouette.
    edge = 520 - int(46 * math.sin(y * 0.021) + 26 * math.sin(y * 0.047 + 2.0))
    if y >= edge:
        spans.append((0, W))
    # Near ridge: a lower, lumpier silhouette on the left and right.
    edge2 = 545 - int(20 * math.sin(y * 0.05 + 0.7) + 12 * math.sin(y * 0.11))
    if y >= edge2:
        spans.append((0, 300))
        spans.append((760, W))
    return spans


# --------------------------------------------------------------- terraces

TERRACE_TOP = 560

# (band height, water colour at top of band, water colour at bottom)
BANDS = [
    (46, (232, 128, 74), (196, 96, 66)),
    (50, (214, 108, 66), (150, 78, 70)),
    (56, (188, 92, 62), (112, 66, 76)),
    (62, (158, 80, 64), (84, 58, 82)),
    (70, (128, 70, 66), (62, 52, 84)),
    (78, (102, 62, 70), (46, 48, 84)),
    (102, (82, 56, 74), (34, 44, 82)),
]


def draw_terraces():
    """Stacked flooded paddies: water mirrors the sky, walls stay dark."""
    y = TERRACE_TOP
    for bi, (bh, wtop, wbot) in enumerate(BANDS):
        wall_h = max(6, bh // 4)
        water_h = bh - wall_h
        for yy in range(y, y + water_h):
            t = (yy - y) / max(1, water_h)
            fill_span(yy, 0, W, mix(wtop, wbot, t))
        for yy in range(y + water_h, y + bh):
            t = (yy - (y + water_h)) / max(1, wall_h)
            fill_span(yy, 0, W, mix((26, 44, 36), (16, 28, 26), t))
        # Thin bright rim where the water meets the wall.
        fill_span(y + water_h, 0, W, (255, 190, 120) if bi < 2 else (120, 90, 90))
        y += bh
    # Perspective divider curves: field edges fanning down the slope.
    for (x_top, x_bot, phase) in [(300, 180, 0.0), (700, 830, 1.3), (520, 470, 2.6)]:
        pts = []
        for i in range(25):
            t = i / 24
            xx = int(lerp(x_top, x_bot, t) + 14 * math.sin(t * 5.0 + phase))
            yy = int(lerp(TERRACE_TOP, H, t))
            pts.append((xx, yy))
        polyline_disc(pts, 3, (18, 30, 28), 255, step=4)


def draw_shimmer():
    """The jellyfish's pink shimmer, rippling down the flooded terraces."""
    for x in range(408, 620, 9):
        for y in range(TERRACE_TOP + 4, H - 4, 3):
            wob = int(7 * math.sin(y * 0.028 + x * 0.05))
            depth = (y - TERRACE_TOP) / (H - TERRACE_TOP)
            alpha = int(70 * (1.0 - depth * 0.75))
            blend_span(y, x + wob, x + wob + 3, (255, 170, 205), alpha)


# -------------------------------------------------------------- jellyfish

JX, JY = 512, 330          # bell centre
JRX, JRY = 238, 172        # bell radii
BELL_TOP = (255, 226, 242)
BELL_MID = (236, 118, 202)
BELL_EDGE = (150, 70, 206)


def draw_jellyfish_glow():
    """Wide soft halo so the bell reads as a light source."""
    disc(JX, JY, 330, (255, 120, 190), 18)
    disc(JX, JY, 290, (255, 140, 200), 26)
    disc(JX, JY + 40, 260, (200, 120, 235), 22)


def draw_bell():
    """The dome: bright apex fading to violet at the rim, translucent."""
    for y, x0, x1 in ellipse_rows(JX, JY, JRX, JRY):
        # Radial brightness: hottest near the apex, cooler toward the rim.
        ny = (y - (JY - JRY)) / (2 * JRY)          # 0 top .. 1 bottom
        cx_mid = (x0 + x1) // 2
        nx = abs(cx_mid - JX) / JRX
        heat = _clamp(1.0 - (ny * 0.55 + nx * 0.45), 0.15, 1.0)
        col = mix(BELL_EDGE, mix(BELL_MID, BELL_TOP, heat), heat)
        alpha = 235 if heat > 0.55 else 215
        blend_span(y, x0, x1, col, alpha)
    # Bright core just under the apex.
    disc(JX, JY - 58, 74, (255, 240, 250), 120)
    disc(JX, JY - 58, 44, (255, 250, 252), 150)


def draw_ribs():
    """Curved ribs fanning from the apex to the rim."""
    apex = (JX, JY - JRY + 8)
    for k in range(-5, 6):
        ang = k * 0.30
        ex = int(JX + math.sin(ang) * (JRX - 14))
        ey = int(JY + JRY * 0.55)
        mid = (int((apex[0] + ex) / 2 + k * 12), int((apex[1] + ey) / 2 - 30))
        pts = [apex, mid, (ex, ey)]
        polyline_disc(pts, 5, (255, 205, 235), 150, step=4)


def draw_skirt():
    """Wavy translucent oral skirt along the bell's lower rim."""
    for x in range(JX - JRX + 6, JX + JRX - 5):
        t = (x - (JX - JRX)) / (2 * JRX)
        rest = 1.0 - ((x - JX) / JRX) ** 2
        if rest < 0:
            continue
        edge = int(JY + JRY * math.sqrt(rest) * 0.92)
        wave = int(16 * math.sin(x * 0.055) + 8 * math.sin(x * 0.13 + 1.0))
        fill_vspan(x, edge - 6, edge + wave + 18, (226, 130, 205))
        blend_span(edge + wave + 10, x, x + 1, (255, 190, 225), 120)
    # Scalloped fringe: overlapping discs under the skirt edge.
    for x in range(JX - JRX + 10, JX + JRX - 9, 16):
        rest = 1.0 - ((x - JX) / JRX) ** 2
        if rest < 0:
            continue
        edge = int(JY + JRY * math.sqrt(rest) * 0.92)
        wave = int(16 * math.sin(x * 0.055) + 8 * math.sin(x * 0.13 + 1.0))
        disc(x, edge + wave + 12, 11, (240, 150, 215), 200)


def draw_oral_arms():
    """Five thick frilled oral arms hanging from the bell's centre."""
    for i, off in enumerate((-132, -66, 0, 66, 132)):
        phase = i * 1.15
        length = 150 + (i % 2) * 26
        pts = []
        for s in range(0, length + 1, 6):
            xx = int(JX + off + 20 * math.sin(s * 0.022 + phase))
            yy = JY + JRY - 30 + s
            pts.append((xx, yy))
        polyline_disc(pts, 14, (255, 128, 184), 235, step=4)
        polyline_disc(pts, 7, (255, 190, 220), 200, step=4)


def draw_tentacles():
    """Many fine tentacles trailing down, swaying as they fall."""
    for i in range(18):
        off = -215 + i * 25
        phase = i * 0.9
        length = 170 + int(90 * abs(math.sin(i * 1.7)))
        pts = []
        for s in range(0, length + 1, 5):
            xx = int(JX + off + 12 * math.sin(s * 0.03 + phase))
            yy = JY + JRY - 18 + s
            pts.append((xx, yy))
        polyline_disc(pts, 2, (255, 170, 215), 210, step=3)


# --------------------------------------------------------- farmer, lanterns

def draw_farmer():
    """Tiny farmer silhouette with a conical hat, for scale."""
    fx, fy = 318, 918
    dark = (14, 12, 22)
    # Conical hat.
    for i in range(12):
        w = 4 + i * 2
        fill_span(fy - 34 + i, fx - w // 2, fx + w // 2 + 1, dark)
    # Head, torso, legs.
    disc(fx, fy - 18, 6, dark)
    for i in range(16):
        w = 7 + (i // 4)
        fill_span(fy - 12 + i, fx - w, fx + w + 1, dark)
    fill_span(fy + 4, fx - 5, fx - 1, dark)
    fill_span(fy + 4, fx + 1, fx + 6, dark)
    for i in range(8):
        fill_span(fy + 5 + i, fx - 5, fx - 2, dark)
        fill_span(fy + 5 + i, fx + 2, fx + 5, dark)


def draw_lanterns():
    """Three warm lanterns glowing beside the farmer."""
    for (lx, ly, r) in [(272, 896, 7), (368, 902, 8), (412, 888, 6)]:
        disc(lx, ly, r + 16, (255, 150, 60), 46)
        disc(lx, ly, r + 8, (255, 180, 90), 90)
        disc(lx, ly, r, (255, 214, 140), 255)
        disc(lx, ly, max(2, r - 3), (255, 244, 200), 255)
        # Pole down to the ground.
        fill_vspan(lx, ly + r, ly + 26, (14, 12, 22))


# -------------------------------------------------------------------- png

def png_bytes():
    """Encode the RGB buffer as a deterministic PNG (filter 0 rows)."""
    raw = bytearray()
    stride = W * 3
    for y in range(H):
        raw.append(0)
        raw += buf[y * stride:(y + 1) * stride]
    data = zlib.compress(bytes(raw), 9)

    def chunk(kind, payload):
        c = struct.pack(">I", len(payload)) + kind + payload
        return c + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", data) + chunk(b"IEND", b""))


def main():
    draw_sky()
    draw_sun()
    draw_clouds()
    draw_mountains()
    draw_terraces()
    draw_shimmer()
    draw_jellyfish_glow()
    draw_bell()
    draw_ribs()
    draw_skirt()
    draw_oral_arms()
    draw_tentacles()
    draw_farmer()
    draw_lanterns()
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "entry.png")
    with open(path, "wb") as f:
        f.write(png_bytes())
    print("wrote", path)


if __name__ == "__main__":
    main()
