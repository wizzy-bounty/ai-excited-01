"""ai-excited-01: one image to excite the AI judge.

The program draws the picture procedurally, pixel by pixel, with a
tiny pure-stdlib rasterizer (no Pillow, no network, no clock, no
randomness beyond fixed seeds), then encodes it as a PNG with a
hand-rolled stdlib encoder. Running it twice writes byte-identical
output, as the competition requires.

The picture (scene A, the chosen angle): "Jellyfish Over the
Terraces" -- one colossal glowing jellyfish drifting low over
terraced rice fields at dusk, a tiny farmer and lanterns below for
scale. It follows the winning template on this contest's board: one
impossible colossal subject in the wrong place, one hero silhouette
that reads in a single glance, a small human for scale, dramatic
dusk light, saturated palette. Two more angles (B: a sea turtle
carrying a glowing forest across a desert road; C: a giant paper
crane over an erupting volcano) live in this file for local
comparison; SCENE picks one, default A.

Python 3, standard library only.
"""

import math
import os
import random
import struct
import zlib

W = 1024
H = 1024
MAX_BYTES = 1048576


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def mix(c1, c2, t):
    """Linear blend of two RGB triples."""
    return (round(c1[0] + (c2[0] - c1[0]) * t),
            round(c1[1] + (c2[1] - c1[1]) * t),
            round(c1[2] + (c2[2] - c1[2]) * t))


class Canvas:
    """A flat RGB frame buffer with span-based drawing primitives."""

    def __init__(self):
        self.buf = bytearray(W * H * 3)

    def span(self, x0, x1, y, col, alpha=1.0):
        """Fill a horizontal run of pixels on row y."""
        if y < 0 or y >= H:
            return
        x0 = max(0, int(x0))
        x1 = min(W - 1, int(x1))
        if x1 < x0:
            return
        base = (y * W + x0) * 3
        n = x1 - x0 + 1
        if alpha >= 1.0:
            self.buf[base:base + 3 * n] = bytes(col) * n
            return
        r, g, b = col
        ia = 1.0 - alpha
        buf = self.buf
        for i in range(n):
            o = base + 3 * i
            buf[o] = round(buf[o] * ia + r * alpha)
            buf[o + 1] = round(buf[o + 1] * ia + g * alpha)
            buf[o + 2] = round(buf[o + 2] * ia + b * alpha)

    def vgrad(self, stops):
        """Vertical gradient; stops is [(pos 0..1, (r,g,b)), ...]."""
        for y in range(H):
            t = y / (H - 1)
            for i in range(len(stops) - 1):
                p0, c0 = stops[i]
                p1, c1 = stops[i + 1]
                if p0 <= t <= p1:
                    f = 0.0 if p1 == p0 else (t - p0) / (p1 - p0)
                    self.span(0, W - 1, y, mix(c0, c1, f))
                    break
            else:
                self.span(0, W - 1, y, stops[-1][1])

    def ellipse(self, cx, cy, rx, ry, col, alpha=1.0):
        if rx <= 0 or ry <= 0:
            return
        y0 = max(0, int(cy - ry))
        y1 = min(H - 1, int(cy + ry))
        for y in range(y0, y1 + 1):
            dy = (y - cy) / ry
            dx = rx * math.sqrt(max(0.0, 1.0 - dy * dy))
            self.span(cx - dx, cx + dx, y, col, alpha)

    def disc(self, cx, cy, r, col, alpha=1.0):
        self.ellipse(cx, cy, r, r, col, alpha)

    def poly(self, pts, col, alpha=1.0):
        """Scanline polygon fill."""
        ys = [p[1] for p in pts]
        y0 = max(0, int(math.ceil(min(ys))))
        y1 = min(H - 1, int(math.floor(max(ys))))
        n = len(pts)
        for y in range(y0, y1 + 1):
            xs = []
            for i in range(n):
                x0, y0p = pts[i]
                x1, y1p = pts[(i + 1) % n]
                if (y0p <= y < y1p) or (y1p <= y < y0p):
                    t = (y - y0p) / (y1p - y0p)
                    xs.append(x0 + t * (x1 - x0))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                self.span(xs[k], xs[k + 1], y, col, alpha)

    def line(self, x0, y0, x1, y1, w, col, alpha=1.0):
        """Thick line drawn as a chain of discs."""
        dx, dy = x1 - x0, y1 - y0
        dist = math.hypot(dx, dy)
        steps = max(1, int(dist / max(1.0, w * 0.4)))
        r = w / 2.0
        for i in range(steps + 1):
            t = i / steps
            self.disc(x0 + dx * t, y0 + dy * t, r, col, alpha)

    def radial(self, cx, cy, r, col, peak=0.55):
        """One soft radial glow, single pass over its bounding box."""
        x0 = max(0, int(cx - r))
        x1 = min(W - 1, int(cx + r))
        y0 = max(0, int(cy - r))
        y1 = min(H - 1, int(cy + r))
        cr, cg, cb = col
        buf = self.buf
        for y in range(y0, y1 + 1):
            dy = (y - cy) / r
            for x in range(x0, x1 + 1):
                dx = (x - cx) / r
                d2 = dx * dx + dy * dy
                if d2 >= 1.0:
                    continue
                a = peak * (1.0 - d2) * (1.0 - d2)
                o = (y * W + x) * 3
                ia = 1.0 - a
                buf[o] = round(buf[o] * ia + cr * a)
                buf[o + 1] = round(buf[o + 1] * ia + cg * a)
                buf[o + 2] = round(buf[o + 2] * ia + cb * a)

    def sun(self, cx, cy, r, core, halo, halo_r):
        self.radial(cx, cy, halo_r, halo, peak=0.5)
        self.disc(cx, cy, r, core)

    def birds(self, spots, col, scale=1.0):
        """Tiny distant birds: two-stroke 'v' marks."""
        for (x, y) in spots:
            s = 9.0 * scale
            self.line(x - s, y, x, y + s * 0.45, 3.0, col, 0.9)
            self.line(x, y + s * 0.45, x + s, y, 3.0, col, 0.9)


# ----------------------------------------------------------------------
# Scene A: "Jellyfish Over the Terraces"
# One colossal glowing jellyfish drifting low over terraced rice
# fields at dusk; a tiny farmer and lanterns below for scale.
# ----------------------------------------------------------------------

def scene_a(cv):
    cv.vgrad([(0.0, (24, 14, 62)), (0.42, (96, 38, 112)),
              (0.68, (214, 84, 96)), (1.0, (255, 168, 92))])
    # Low sun, left of centre, behind the terraces.
    cv.sun(300, 640, 46, (255, 216, 140), (255, 170, 90), 260)
    # Distant mountain ridge.
    ridge = []
    for x in range(0, W + 33, 32):
        ridge.append((x, 640 + 26 * math.sin(x * 0.011 + 1.2)
                      + 12 * math.sin(x * 0.031)))
    ridge += [(W, H), (0, H)]
    cv.poly(ridge, (52, 28, 74))
    # Terraces: stacked curved bands, bottom 40% of the frame.
    greens = [(36, 96, 58), (52, 122, 66), (30, 84, 54), (64, 132, 70)]
    top = 660
    for i in range(8):
        y_top = top + i * 46
        y_bot = y_top + 52
        pts = []
        for x in range(0, W + 33, 32):
            pts.append((x, y_top + 16 * math.sin(x * 0.008 + i * 1.7)))
        for x in range(W, -33, -32):
            pts.append((x, y_bot + 16 * math.sin(x * 0.008 + i * 1.7)))
        cv.poly(pts, greens[i % len(greens)])
        # Sunlit water line along the band's top edge.
        for x in range(0, W, 4):
            y = y_top + 16 * math.sin(x * 0.008 + i * 1.7)
            cv.span(x, x + 3, int(y), (255, 196, 120), 0.28)
    # Pink glow the bell casts down onto the terraces.
    cv.radial(540, 780, 320, (255, 130, 190), peak=0.10)
    # The jellyfish: halo, dome, inner glow, highlight.
    cv.radial(540, 330, 380, (255, 120, 200), peak=0.32)
    cv.ellipse(540, 344, 258, 172, (198, 82, 182), alpha=0.55)
    cv.ellipse(540, 330, 250, 165, (255, 150, 210), alpha=0.92)
    cv.ellipse(540, 322, 182, 116, (255, 200, 232), alpha=0.8)
    cv.ellipse(462, 268, 95, 46, (255, 238, 246), alpha=0.6)
    # Soft rim light under the bell so it reads as a dome, not a disc.
    cv.ellipse(540, 468, 240, 22, (255, 170, 215), alpha=0.35)
    # Dome ribs: curved seams following the bell's curve.
    for k in range(-2, 3):
        x0 = 540 + k * 62
        for s in range(0, 41):
            t = s / 40.0
            x = x0 + k * 14 * t * t - 8 * k * t * (1 - t)
            y = (196 + abs(k) * 24) + t * (462 - (196 + abs(k) * 24))
            cv.disc(x, y, 2.6, (255, 210, 235), alpha=0.3)
    # Oral arms: four broad wavy ribbons, smooth (overlapping stamps).
    for k, x0 in enumerate((430, 500, 580, 650)):
        phase = k * 1.3
        for s in range(0, 220, 4):
            t = s / 220.0
            x = x0 + 30 * math.sin(s * 0.045 + phase)
            y = 460 + s
            r = 14 - 8 * t
            cv.disc(x, y, r, (255, 188, 220), alpha=0.7)
    # Tentacles: seven long thin glowing threads, smooth.
    for k in range(7):
        x0 = 380 + k * 53
        phase = k * 0.9
        col = (255, 170, 215) if k % 2 == 0 else (196, 132, 255)
        for s in range(0, 300, 3):
            t = s / 300.0
            x = x0 + 26 * math.sin(s * 0.038 + phase)
            y = 468 + s
            cv.disc(x, y, 7.5 - 4.5 * t, col, alpha=0.8)
    # Drifting light motes around the bell.
    rng = random.Random(20261116)
    for _ in range(46):
        x = 300 + rng.random() * 480
        y = 180 + rng.random() * 560
        r = 2.0 + rng.random() * 3.5
        cv.disc(x, y, r, (255, 220, 240), alpha=0.55)
    # Tiny farmer with a conical hat on a terrace edge, + lanterns.
    fx, fy = 706, 812
    cv.poly([(fx - 9, fy + 26), (fx + 9, fy + 26), (fx + 4, fy + 2),
             (fx - 4, fy + 2)], (24, 16, 34))
    cv.poly([(fx - 16, fy + 2), (fx + 16, fy + 2), (fx, fy - 14)],
            (214, 164, 90))
    cv.radial(fx + 26, fy + 8, 34, (255, 196, 110), peak=0.7)
    cv.disc(fx + 26, fy + 8, 6, (255, 214, 130))
    cv.radial(316, 884, 30, (255, 196, 110), peak=0.6)
    cv.disc(316, 884, 5, (255, 214, 130))
    # Birds, high and small.
    cv.birds([(180, 150), (238, 128), (830, 180), (884, 150)],
             (40, 22, 60))
    # Dark grass silhouettes anchoring the bottom corners.
    for (gx, gh) in ((40, 90), (120, 64), (940, 84), (990, 58)):
        cv.poly([(gx - 22, H), (gx + 22, H), (gx + 6, H - gh),
                 (gx - 4, H - gh - 26)], (20, 26, 34))


# ----------------------------------------------------------------------
# Scene B: "The Turtle Carries the Forest"
# A colossal sea turtle crosses a desert road at sunset, a glowing
# forest growing on its shell; tiny cars below for scale.
# ----------------------------------------------------------------------

def _pine(cv, x, y, s, glow=True):
    """One small glowing pine: two stacked triangles + trunk."""
    cv.line(x, y, x, y - 6 * s, 3.0, (52, 40, 30))
    cv.poly([(x - 9 * s, y - 4 * s), (x + 9 * s, y - 4 * s),
             (x, y - 16 * s)], (46, 178, 104))
    cv.poly([(x - 7 * s, y - 12 * s), (x + 7 * s, y - 12 * s),
             (x, y - 22 * s)], (74, 214, 130))
    if glow:
        cv.disc(x - 4 * s, y - 10 * s, 2.2, (210, 255, 190), alpha=0.9)
        cv.disc(x + 5 * s, y - 16 * s, 2.0, (210, 255, 190), alpha=0.9)


def scene_b(cv):
    cv.vgrad([(0.0, (38, 20, 72)), (0.48, (150, 60, 92)),
              (0.74, (240, 120, 70)), (1.0, (255, 192, 112))])
    cv.sun(772, 420, 58, (255, 222, 150), (255, 170, 90), 300)
    # Dune layers, warm sand darkening toward the viewer.
    for i, (ybase, col) in enumerate(((600, (206, 128, 74)),
                                      (700, (168, 96, 62)),
                                      (820, (118, 66, 52)))):
        pts = []
        for x in range(0, W + 33, 32):
            pts.append((x, ybase + 22 * math.sin(x * 0.007 + i * 2.1)))
        pts += [(W, H), (0, H)]
        cv.poly(pts, col)
    # Desert road: perspective strip from the horizon to the bottom.
    cv.poly([(428, H), (596, H), (524, 690), (500, 690)], (42, 34, 42))
    cv.poly([(428, H), (452, H), (500, 690), (496, 690)], (255, 200, 120),
            alpha=0.7)
    cv.poly([(596, H), (572, H), (524, 690), (528, 690)], (255, 200, 120),
            alpha=0.7)
    for i in range(6):
        t0 = i / 6.0
        t1 = (i + 0.45) / 6.0
        y0 = 700 + (H - 700) * t0 * t0
        y1 = 700 + (H - 700) * t1 * t1
        xm0 = 512 + (512 - 512) * 0  # centre line stays at x=512
        w0 = 3 + 14 * t0
        cv.poly([(512 - w0, y0), (512 + w0, y0), (512 + w0 + 14 * t1, y1),
                 (512 - w0 - 14 * t1, y1)], (255, 220, 140), alpha=0.85)
    # The turtle: rim, shell, scutes, glowing forest, head, flippers.
    cv.ellipse(512, 576, 336, 208, (28, 54, 44))
    cv.ellipse(512, 562, 330, 200, (46, 86, 66))
    # Scutes: a row of hexagons across the shell.
    for (sx, sy, sr) in ((380, 520, 62), (512, 500, 70), (644, 520, 62),
                         (430, 610, 58), (580, 610, 58), (512, 580, 66)):
        hexpts = [(sx + sr * math.cos(a), sy + sr * 0.82 * math.sin(a))
                  for a in (0.0, 1.05, 2.09, 3.14, 4.19, 5.24)]
        cv.poly(hexpts, (74, 122, 88))
        cv.poly([(sx + sr * 0.55 * math.cos(a),
                  sy + sr * 0.45 * math.sin(a))
                 for a in (0.0, 1.05, 2.09, 3.14, 4.19, 5.24)],
                (96, 148, 106))
    # Glowing forest riding the shell.
    for (tx, ty, ts) in ((400, 500, 1.0), (452, 468, 1.25),
                         (512, 452, 1.45), (572, 468, 1.25),
                         (624, 500, 1.0), (480, 520, 0.9),
                         (548, 520, 0.9)):
        _pine(cv, tx, ty, ts)
    rng = random.Random(77)
    for _ in range(26):
        x = 380 + rng.random() * 264
        y = 440 + rng.random() * 110
        cv.disc(x, y, 2.0 + rng.random() * 2.0, (200, 255, 180),
                alpha=0.8)
    # Head, neck, eye; tail; flippers.
    cv.poly([(800, 520), (880, 540), (880, 600), (800, 600)],
            (40, 74, 58))
    cv.ellipse(896, 566, 56, 40, (46, 86, 66))
    cv.disc(912, 552, 9, (255, 244, 220))
    cv.disc(914, 552, 4.5, (16, 12, 20))
    cv.poly([(176, 580), (196, 560), (196, 606), (176, 600)],
            (40, 74, 58))
    for (lx, ly) in ((330, 748), (470, 762), (580, 762), (700, 748)):
        cv.ellipse(lx, ly, 52, 26, (40, 74, 58))
    # Two tiny cars on the road, dwarfed by the turtle.
    for (cx, cy, s) in ((486, 884, 1.0), (540, 786, 0.62)):
        cv.poly([(cx - 26 * s, cy), (cx + 26 * s, cy),
                 (cx + 20 * s, cy - 14 * s), (cx - 20 * s, cy - 14 * s)],
                (216, 216, 222))
        cv.poly([(cx - 14 * s, cy - 13 * s), (cx + 14 * s, cy - 13 * s),
                 (cx + 10 * s, cy - 24 * s), (cx - 10 * s, cy - 24 * s)],
                (120, 180, 220))
        cv.disc(cx + 24 * s, cy - 3 * s, 3.5 * s, (255, 230, 140))
    cv.birds([(200, 150), (260, 128), (880, 210)], (52, 28, 60))


# ----------------------------------------------------------------------
# Scene C: "Paper Crane Over the Volcano"
# A giant origami crane spreads its folded wings above an erupting
# volcano, embers rising, fold lines lit gold by the lava below.
# ----------------------------------------------------------------------

def scene_c(cv):
    cv.vgrad([(0.0, (22, 14, 44)), (0.5, (92, 40, 72)),
              (0.8, (200, 80, 50)), (1.0, (255, 142, 60))])
    # Drifting smoke, dark and soft.
    for (sx, sy, sr) in ((150, 180, 150), (880, 140, 170), (820, 300, 110)):
        cv.ellipse(sx, sy, sr, sr * 0.5, (40, 28, 52), alpha=0.5)
    # Volcano cone and glowing crater.
    cv.radial(512, 640, 280, (255, 120, 40), peak=0.5)
    cv.poly([(40, H), (984, H), (512, 610)], (54, 38, 46))
    cv.poly([(430, 640), (594, 640), (512, 610)], (70, 46, 52))
    cv.ellipse(512, 640, 118, 30, (255, 110, 30))
    cv.ellipse(512, 638, 78, 20, (255, 190, 70))
    # Lava streams down the slopes, bright core inside dark flow.
    for (lx0, lx1, steps) in ((470, 300, 5), (560, 730, 5), (512, 512, 4)):
        x, y = lx0, 650
        for _ in range(steps):
            nx = lx0 + (lx1 - lx0) * (_ + 1) / steps
            ny = 650 + 74 * (_ + 1)
            cv.line(x, y, nx, ny, 16, (200, 60, 20), alpha=0.9)
            cv.line(x, y, nx, ny, 6, (255, 180, 60), alpha=0.95)
            x, y = nx, ny
    # The crane: folded-paper facets, white lit gold from below.
    white = (246, 242, 234)
    shade = (188, 182, 198)
    gold = (255, 210, 130)
    # Tail feathers fanning down-left.
    for (tx, ty, tl) in ((380, 560, 150), (400, 590, 120), (420, 610, 95)):
        cv.poly([(430, 560), (tx - 14, ty + tl), (tx + 14, ty + tl)],
                shade)
    # Left wing: big folded triangle, shadow facet + gold rim.
    cv.poly([(512, 470), (180, 330), (300, 560)], white)
    cv.poly([(512, 470), (300, 560), (430, 540)], shade)
    cv.line(512, 470, 180, 330, 5.0, gold, alpha=0.9)
    cv.line(180, 330, 300, 560, 4.0, (220, 205, 190), alpha=0.6)
    # Right wing raised, catching the lava light.
    cv.poly([(512, 470), (852, 300), (700, 540)], white)
    cv.poly([(512, 470), (700, 540), (600, 520)], (232, 214, 190))
    cv.line(512, 470, 852, 300, 5.0, gold, alpha=0.9)
    cv.line(852, 300, 700, 540, 4.0, (220, 205, 190), alpha=0.6)
    # Body diamond, long neck, head, beak.
    cv.poly([(512, 470), (590, 540), (512, 600), (436, 540)], white)
    cv.poly([(512, 470), (590, 540), (512, 600)], shade, alpha=0.55)
    cv.line(560, 500, 700, 330, 26, white)
    cv.line(560, 500, 700, 330, 10, shade, alpha=0.5)
    cv.poly([(688, 312), (730, 330), (700, 352), (676, 340)], white)
    cv.poly([(730, 330), (772, 342), (730, 348)], (255, 190, 80))
    cv.disc(706, 330, 5, (20, 14, 18))
    # Fold creases across the wings.
    cv.line(512, 470, 330, 430, 3.0, shade, alpha=0.7)
    cv.line(512, 470, 690, 420, 3.0, shade, alpha=0.7)
    # Rising embers, deterministic.
    rng = random.Random(20261116)
    for _ in range(60):
        x = 240 + rng.random() * 544
        y = 620 - rng.random() * 420
        r = 2.0 + rng.random() * 3.5
        col = (255, 180, 60) if rng.random() < 0.6 else (255, 110, 40)
        cv.disc(x, y, r, col, alpha=0.85)
    cv.birds([(200, 150), (850, 180)], (40, 24, 44))


# ----------------------------------------------------------------------
# PNG encoder (pure stdlib) + entry point
# ----------------------------------------------------------------------

def _chunk(typ, data):
    out = struct.pack(">I", len(data)) + typ + data
    out += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
    return out


def encode_png(cv):
    raw = bytearray()
    for y in range(H):
        raw.append(0)
        raw += cv.buf[y * W * 3:(y + 1) * W * 3]
    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 6))
            + _chunk(b"IEND", b""))


SCENES = {"A": scene_a, "B": scene_b, "C": scene_c}


def main():
    scene = os.environ.get("SCENE", "A").upper()
    if scene not in SCENES:
        raise SystemExit("unknown SCENE %r (want A, B or C)" % scene)
    cv = Canvas()
    SCENES[scene](cv)
    data = encode_png(cv)
    if len(data) > MAX_BYTES:
        raise SystemExit("image is %d bytes, over the 1 MiB cap"
                         % len(data))
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "entry.png"), "wb") as fh:
        fh.write(data)


if __name__ == "__main__":
    main()
