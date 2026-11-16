"""ai-excited-01 — 'Jellyfish Over the Terraces'

A colossal glowing jellyfish drifts low over flooded rice terraces at dusk,
its tentacles trailing down toward tiny farmers with lanterns below.

Why this image: the winning pattern on the board is ONE impossible subject
in the wrong place, one hero silhouette, a tiny human for scale, dramatic
dusk light. A sea creature the size of a hill, hovering over rice fields
it could never live in, is that pattern with a subject no top-10 entry
used (no whale, no teacup, no lighthouse, no neon city).

Pure Python 3 stdlib (no Pillow, no network): a small rasterizer plus a
hand-built PNG encoder. Deterministic: one fixed RNG seed, so both grader
runs write byte-identical files.
"""

import math
import os
import random
import struct
import zlib

W = 1024
H = 1024
RNG = random.Random(20261116)


class Canvas:
    """1024x1024 RGB canvas with the few primitives the scene needs."""

    def __init__(self, w=W, h=H):
        self.w = w
        self.h = h
        self.buf = bytearray(w * h * 3)

    def set(self, x, y, r, g, b):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.buf[i] = r
            self.buf[i + 1] = g
            self.buf[i + 2] = b

    def blend(self, x, y, r, g, b, a):
        """Alpha-blend a colour over pixel (x, y); a in 0..1."""
        if 0 <= x < self.w and 0 <= y < self.h and a > 0.0:
            i = (y * self.w + x) * 3
            buf = self.buf
            if a >= 1.0:
                buf[i] = r
                buf[i + 1] = g
                buf[i + 2] = b
            else:
                ia = 1.0 - a
                buf[i] = int(r * a + buf[i] * ia)
                buf[i + 1] = int(g * a + buf[i + 1] * ia)
                buf[i + 2] = int(b * a + buf[i + 2] * ia)

    def hline(self, x0, x1, y, r, g, b):
        if y < 0 or y >= self.h:
            return
        if x0 > x1:
            x0, x1 = x1, x0
        x0 = max(0, x0)
        x1 = min(self.w - 1, x1)
        if x0 > x1:
            return
        i = (y * self.w + x0) * 3
        n = x1 - x0 + 1
        self.buf[i:i + n * 3] = bytes((r, g, b)) * n

    def vgrad(self, y0, y1, stops):
        """Vertical gradient; stops = [(t, (r, g, b)), ...] sorted by t."""
        for y in range(max(0, y0), min(self.h, y1 + 1)):
            t = (y - y0) / max(1, (y1 - y0))
            self.hline(0, self.w - 1, y, *grad_color(stops, t))

    def disc(self, cx, cy, rad, r, g, b, a=1.0):
        rad = int(math.ceil(rad))
        r2 = rad * rad
        for y in range(max(0, int(cy) - rad), min(self.h, int(cy) + rad) + 1):
            dy = y - cy
            dx = int(math.sqrt(max(0, r2 - dy * dy)))
            for x in range(max(0, int(cx) - dx), min(self.w - 1, int(cx) + dx) + 1):
                self.blend(x, y, r, g, b, a)

    def glow(self, cx, cy, rad, r, g, b, peak=0.9):
        """Soft radial glow with quadratic falloff."""
        rad = int(rad)
        if rad <= 0:
            return
        for y in range(max(0, int(cy) - rad), min(self.h, int(cy) + rad) + 1):
            dy = (y - cy) / rad
            for x in range(max(0, int(cx) - rad), min(self.w - 1, int(cx) + rad) + 1):
                dx = (x - cx) / rad
                d2 = dx * dx + dy * dy
                if d2 < 1.0:
                    a = peak * (1.0 - d2) * (1.0 - d2)
                    self.blend(x, y, r, g, b, a)

    def poly(self, pts, r, g, b, a=1.0):
        """Scanline fill of a polygon."""
        if len(pts) < 3:
            return
        ys = [p[1] for p in pts]
        y0 = max(0, int(math.ceil(min(ys))))
        y1 = min(self.h - 1, int(math.floor(max(ys))))
        n = len(pts)
        for y in range(y0, y1 + 1):
            xs = []
            for i in range(n):
                x0, ya = pts[i]
                x1, yb = pts[(i + 1) % n]
                if (ya <= y < yb) or (yb <= y < ya):
                    t = (y - ya) / (yb - ya)
                    xs.append(x0 + t * (x1 - x0))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                xa = int(math.ceil(xs[k]))
                xb = int(math.floor(xs[k + 1]))
                if a >= 1.0:
                    self.hline(xa, xb, y, r, g, b)
                else:
                    for x in range(max(0, xa), min(self.w - 1, xb) + 1):
                        self.blend(x, y, r, g, b, a)

    def thick_polyline(self, pts, w0, w1, r, g, b, a=1.0, step=3):
        """Tapered polyline drawn as stamped discs along the path."""
        n = len(pts)
        if n < 2:
            return
        total = 0.0
        for i in range(n - 1):
            total += math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        dist = 0.0
        for i in range(n - 1):
            x0, y0 = pts[i]
            x1, y1 = pts[i + 1]
            seg = math.hypot(x1 - x0, y1 - y0)
            if seg == 0:
                continue
            steps = max(1, int(seg / step))
            for s in range(steps + 1):
                t = s / steps
                px = x0 + (x1 - x0) * t
                py = y0 + (y1 - y0) * t
                frac = (dist + seg * t) / max(1.0, total)
                rad = w0 + (w1 - w0) * frac
                if rad > 0.4:
                    self.disc(px, py, rad, r, g, b, a)
            dist += seg

    def ellipse_shade(self, cx, cy, rx, ry, fn):
        """Fill an ellipse; fn(u, v, r, g, b) -> (r, g, b) per pixel."""
        x0 = max(0, int(cx - rx))
        x1 = min(self.w - 1, int(cx + rx))
        y0 = max(0, int(cy - ry))
        y1 = min(self.h - 1, int(cy + ry))
        for y in range(y0, y1 + 1):
            v = (y - cy) / ry
            rem = 1.0 - v * v
            if rem < 0:
                continue
            dx = rx * math.sqrt(rem)
            for x in range(x0, x1 + 1):
                u = (x - cx) / rx
                if u * u + v * v <= 1.0:
                    i = (y * self.w + x) * 3
                    r, g, b = fn(u, v, self.buf[i], self.buf[i + 1], self.buf[i + 2])
                    self.buf[i] = r
                    self.buf[i + 1] = g
                    self.buf[i + 2] = b


def grad_color(stops, t):
    if t <= stops[0][0]:
        return stops[0][1]
    if t >= stops[-1][0]:
        return stops[-1][1]
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if t0 <= t <= t1:
            f = (t - t0) / (t1 - t0)
            return (int(c0[0] + (c1[0] - c0[0]) * f),
                    int(c0[1] + (c1[1] - c0[1]) * f),
                    int(c0[2] + (c1[2] - c0[2]) * f))
    return stops[-1][1]


def lerp(a, b, f):
    return a + (b - a) * f


def clamp(v, lo=0, hi=255):
    return max(lo, min(hi, int(v)))


def write_png(cv, path):
    """Encode the canvas as a PNG (filter 0, zlib level 9)."""
    raw = bytearray()
    stride = cv.w * 3
    for y in range(cv.h):
        raw.append(0)
        raw += cv.buf[y * stride:(y + 1) * stride]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        return c + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", cv.w, cv.h, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", comp) + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


def draw():
    cv = Canvas()

    # ---- dusk sky: deep indigo -> violet -> magenta -> burning orange
    cv.vgrad(0, 660, [
        (0.00, (16, 12, 52)),
        (0.35, (58, 32, 96)),
        (0.60, (146, 58, 110)),
        (0.82, (232, 110, 72)),
        (1.00, (255, 158, 66)),
    ])
    # stars in the upper sky
    for _ in range(90):
        x = RNG.uniform(0, W)
        y = RNG.uniform(0, 300)
        cv.disc(x, y, RNG.uniform(0.6, 1.6), 255, 240, 220, RNG.uniform(0.25, 0.9))

    # ---- low sun, left of centre, huge warm halo
    sx, sy = 255, 565
    cv.glow(sx, sy, 260, 255, 150, 60, 0.55)
    cv.glow(sx, sy, 130, 255, 190, 90, 0.8)
    cv.disc(sx, sy, 44, 255, 226, 150)
    cv.disc(sx, sy, 34, 255, 244, 200)

    # ---- far mountain ridges, two layers
    for base, amp, col in [(600, 42, (64, 34, 88)), (628, 30, (44, 24, 66))]:
        pts = [(0, 660)]
        for x in range(0, W + 33, 32):
            y = base + amp * math.sin(x * 0.006 + base) + amp * 0.5 * math.sin(x * 0.017 + 2.0)
            pts.append((x, y))
        pts.append((W, 660))
        cv.poly(pts, *col)

    # ---- mist band at the horizon (translucent)
    for y in range(600, 668):
        a = 0.10 * math.sin((y - 600) / 68.0 * math.pi)
        for x in range(0, W, 2):
            cv.blend(x, y, 255, 170, 120, a)

    # ---- rice terraces: sweeping curved bands, y 640..1024
    def terrace_top(x, base, amp, ph):
        return base + amp * math.sin(x * 0.0042 + ph) + amp * 0.45 * math.sin(x * 0.011 + ph * 2.3)

    bands = []
    yb = 648
    for i in range(9):
        bands.append((yb, 16 + i * 7, 0.9 + i * 0.55))
        yb += 42 + i * 6
    for i, (base, amp, ph) in enumerate(bands):
        top = [(x, terrace_top(x, base, amp, ph)) for x in range(0, W + 1, 8)]
        if i + 1 < len(bands):
            bot = [(x, terrace_top(x, bands[i + 1][0], bands[i + 1][1], bands[i + 1][2]))
                   for x in range(W, -1, -8)]
        else:
            bot = [(W, H), (0, H)]
        water = (i % 2 == 0)
        f = i / max(1, len(bands) - 1)
        if water:
            # mirror of the dusk sky: orange near the horizon, violet below
            col = (int(lerp(238, 96, f)), int(lerp(120, 62, f)), int(lerp(70, 110, f)))
        else:
            col = (int(lerp(52, 26, f)), int(lerp(118, 66, f)), int(lerp(58, 44, f)))
        cv.poly(top + bot, *col)
        # terrace wall: dark rim along the top edge
        for x in range(0, W, 4):
            y = int(terrace_top(x, base, amp, ph))
            cv.set(x, y, 30, 20, 44)
            cv.set(x, y + 1, 40, 26, 54)
        if water:
            # sun shimmer on the water near the sun's x
            for _ in range(26):
                x = RNG.gauss(sx, 90)
                y = RNG.uniform(base + 6, min(H - 4, base + 40 + i * 5))
                ln = RNG.uniform(14, 60)
                a = RNG.uniform(0.25, 0.6)
                for dx in range(int(ln)):
                    cv.blend(int(x) + dx, int(y), 255, 200, 120, a * (1 - dx / ln))
        else:
            # rice sprout speckles
            for _ in range(160):
                x = RNG.uniform(0, W)
                y = RNG.uniform(base + 4, min(H - 2, base + 42 + i * 5))
                cv.blend(int(x), int(y), 150, 220, 110, RNG.uniform(0.2, 0.55))

    # ---- the jellyfish's reflection shimmering on the water below it
    for _ in range(40):
        x = RNG.gauss(570, 130)
        y = RNG.uniform(670, 1000)
        ln = RNG.uniform(20, 90)
        a = RNG.uniform(0.10, 0.30)
        for dx in range(int(ln)):
            cv.blend(int(x) + dx, int(y), 255, 170, 220, a * (1 - dx / ln))

    # ---- THE JELLYFISH: one colossal bell, centred (570, 300)
    cx, cy, rx, ry = 570, 300, 305, 215

    def bell_shade(u, v, r0, g0, b0):
        d = math.sqrt(u * u + v * v)
        core = max(0.0, 1.0 - d * 1.15)
        top = max(0.0, -v)
        r = int(lerp(lerp(120, 235, core), 235, top * 0.25))
        g = int(lerp(lerp(70, 200, core), 245, top * 0.25))
        b = int(lerp(lerp(150, 245, core), 255, top * 0.2))
        # violet rim at the edge
        edge = max(0.0, (d - 0.82) / 0.18)
        r = int(lerp(r, 168, edge * 0.7))
        g = int(lerp(g, 90, edge * 0.7))
        b = int(lerp(b, 205, edge * 0.7))
        # translucent fade toward the lower rim
        low = max(0.0, (v - 0.45) / 0.55)
        r = int(lerp(r, 214, low * 0.35))
        g = int(lerp(g, 130, low * 0.35))
        b = int(lerp(b, 200, low * 0.35))
        return clamp(r), clamp(g), clamp(b)

    cv.ellipse_shade(cx, cy, rx, ry, bell_shade)

    # dome ribs fanning from a spread apex (no single bright spike)
    for k in range(-7, 8):
        t = k / 7.0
        ax = cx + t * 46
        pts = []
        for s in range(0, 17):
            f = s / 16.0
            ang = t * 1.05
            px = ax + math.sin(ang) * rx * f * 0.92
            py = cy - ry * 0.55 + (ry * 1.05) * f
            pts.append((px, py))
        cv.thick_polyline(pts, 1.6, 0.8, 255, 235, 255, 0.16, step=4)

    # frilly oral skirt: wavy translucent band under the bell
    skirt = []
    for x in range(int(cx - rx * 0.98), int(cx + rx * 0.98) + 1, 6):
        u = (x - cx) / rx
        yb = cy + ry * math.sqrt(max(0.0, 1 - u * u)) * 0.96
        skirt.append((x, yb))
    for x in range(int(cx + rx * 0.98), int(cx - rx * 0.98) - 1, -6):
        u = (x - cx) / rx
        yb = cy + ry * math.sqrt(max(0.0, 1 - u * u)) * 0.96 + 26 + 10 * math.sin(x * 0.09)
        skirt.append((x, yb))
    cv.poly(skirt, 226, 170, 235, a=0.38)

    # soft glow just under the lower rim
    for k in range(80):
        t = k / 79.0
        ang = math.pi * t
        px = cx + math.cos(ang) * rx * 0.99
        py = cy + math.sin(ang) * ry * 0.99 * 0.55 + ry * 0.42
        cv.glow(px, py, 5, 255, 170, 230, 0.35)

    # luminous spots inside the bell
    for _ in range(26):
        a = RNG.uniform(0, 2 * math.pi)
        rr = RNG.uniform(0.15, 0.8)
        px = cx + math.cos(a) * rx * rr * 0.9
        py = cy + math.sin(a) * ry * rr * 0.75 - 10
        cv.glow(px, py, RNG.uniform(4, 10), 190, 240, 255, RNG.uniform(0.35, 0.7))

    # ---- tentacles: long glowing ribbons flowing down from the rim
    for k in range(34):
        t = k / 33.0
        x0 = cx - rx * 0.92 + t * rx * 1.84
        y0 = cy + ry * 0.55 * math.sqrt(max(0.0, 1 - ((x0 - cx) / rx) ** 2)) + 8
        length = RNG.uniform(180, 330)
        sway = RNG.uniform(18, 55) * (1 if k % 2 else -1)
        phase = RNG.uniform(0, 6.28)
        pts = []
        for s in range(0, 25):
            f = s / 24.0
            px = x0 + sway * math.sin(f * 2.4 + phase) * f
            py = y0 + length * f
            pts.append((px, py))
        col = [(255, 150, 210), (140, 220, 255), (255, 210, 130)][k % 3]
        cv.thick_polyline(pts, RNG.uniform(2.6, 5.0), 0.8, *col, a=0.85, step=3)
        cv.glow(pts[-1][0], pts[-1][1], 8, *col, peak=0.6)

    # a few thick oral arms hanging from the bell's centre-bottom
    for k, xo in enumerate([-140, -60, 20, 100, 170]):
        pts = []
        for s in range(0, 21):
            f = s / 20.0
            px = cx + xo + 38 * math.sin(f * 3.0 + k * 1.7) * f
            py = cy + ry * 0.55 + 250 * f
            pts.append((px, py))
        cv.thick_polyline(pts, 10, 3, 255, 190, 225, 0.8, step=3)

    # ---- tiny farmers with lanterns (the scale cue)
    def farmer(x, y, s=1.0):
        cv.disc(x, y - 13 * s, 3.2 * s, 24, 16, 40)
        cv.poly([(x - 4 * s, y - 10 * s), (x + 4 * s, y - 10 * s),
                 (x + 3 * s, y + 2 * s), (x - 3 * s, y + 2 * s)], 24, 16, 40)
        cv.poly([(x - 7 * s, y - 9 * s), (x + 7 * s, y - 9 * s), (x, y - 16 * s)], 200, 170, 90)
        cv.thick_polyline([(x - 2 * s, y + 2 * s), (x - 2 * s, y + 10 * s)],
                          1.6, 1.6, 24, 16, 40, step=2)
        cv.thick_polyline([(x + 2 * s, y + 2 * s), (x + 2 * s, y + 10 * s)],
                          1.6, 1.6, 24, 16, 40, step=2)
        cv.thick_polyline([(x + 5 * s, y - 8 * s), (x + 11 * s, y - 14 * s)],
                          1.2, 1.2, 60, 40, 30, step=2)
        cv.glow(x + 12 * s, y - 15 * s, 12, 255, 190, 90, 0.85)
        cv.disc(x + 12 * s, y - 15 * s, 2.6, 255, 220, 140)

    farmer(210, 905, 1.15)
    farmer(300, 968, 1.0)
    farmer(830, 890, 1.05)

    # small hut with a warm window on a right terrace
    cv.poly([(820, 800), (880, 800), (895, 828), (805, 828)], 30, 20, 48)
    cv.poly([(812, 802), (888, 802), (850, 776)], 52, 30, 60)
    cv.disc(852, 814, 4, 255, 200, 110)
    cv.glow(852, 814, 14, 255, 190, 100, 0.7)

    # ---- fireflies / drifting spores
    for _ in range(70):
        x = RNG.uniform(0, W)
        y = RNG.uniform(500, 1000)
        c = RNG.choice([(190, 255, 200), (255, 220, 140), (170, 220, 255)])
        cv.glow(x, y, RNG.uniform(3, 7), *c, peak=RNG.uniform(0.3, 0.7))

    return cv


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "entry.png")
    cv = draw()
    n = write_png(cv, path)
    print(f"wrote {path} ({n} bytes)")


if __name__ == "__main__":
    main()
