# ai-excited-01 — "Jellyfish Over the Terraces"
# Pure Python 3 stdlib: procedural rasterizer + hand-rolled PNG encoder.
# No Pillow, no network, no clock, no randomness (fixed math only).
# Writes one 1024x1024 image to $MAKEFUN_OUTPUT_DIR/entry.png (default /output).
# SCENE=A|B|C picks one of three compositions (default A = winner).
import math
import os
import struct
import zlib

W = 1024
H = 1024


# ---------------------------------------------------------------- framebuffer
class Canvas:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.px = [bytearray(w * 3) for _ in range(h)]

    def blend(self, x, y, r, g, b, a):
        """Alpha-blend src colour over dst pixel. a in 0..1."""
        if x < 0 or y < 0 or x >= self.w or y >= self.h:
            return
        row = self.px[y]
        i = x * 3
        ia = 1.0 - a
        row[i] = int(r * a + row[i] * ia + 0.5)
        row[i + 1] = int(g * a + row[i + 1] * ia + 0.5)
        row[i + 2] = int(b * a + row[i + 2] * ia + 0.5)

    def set(self, x, y, r, g, b):
        if 0 <= x < self.w and 0 <= y < self.h:
            row = self.px[y]
            i = x * 3
            row[i] = r
            row[i + 1] = g
            row[i + 2] = b

    def hspan(self, y, x0, x1, r, g, b, a=1.0):
        """Blend a horizontal span on one row (fast path for a==1)."""
        if y < 0 or y >= self.h:
            return
        x0 = max(0, int(math.ceil(x0)))
        x1 = min(self.w - 1, int(math.floor(x1)))
        if x1 < x0:
            return
        row = self.px[y]
        if a >= 1.0:
            span = bytes((r, g, b)) * (x1 - x0 + 1)
            row[x0 * 3:(x1 + 1) * 3] = span
        else:
            ia = 1.0 - a
            for x in range(x0, x1 + 1):
                i = x * 3
                row[i] = int(r * a + row[i] * ia + 0.5)
                row[i + 1] = int(g * a + row[i + 1] * ia + 0.5)
                row[i + 2] = int(b * a + row[i + 2] * ia + 0.5)

    def vgrad(self, y0, y1, stops):
        """Vertical gradient between (y, (r,g,b)) stops, blended over rows."""
        for y in range(max(0, y0), min(self.h, y1 + 1)):
            for k in range(len(stops) - 1):
                ya, ca = stops[k]
                yb, cb = stops[k + 1]
                if ya <= y <= yb and yb > ya:
                    t = (y - ya) / (yb - ya)
                    r = int(ca[0] + (cb[0] - ca[0]) * t + 0.5)
                    g = int(ca[1] + (cb[1] - ca[1]) * t + 0.5)
                    b = int(ca[2] + (cb[2] - ca[2]) * t + 0.5)
                    self.hspan(y, 0, self.w - 1, r, g, b)
                    break

    def glow(self, cx, cy, rad, r, g, b, peak):
        """Soft radial glow, additive-ish blend inside bounding box."""
        x0 = max(0, int(cx - rad))
        x1 = min(self.w - 1, int(cx + rad))
        y0 = max(0, int(cy - rad))
        y1 = min(self.h - 1, int(cy + rad))
        for y in range(y0, y1 + 1):
            dy = (y - cy) / rad
            for x in range(x0, x1 + 1):
                dx = (x - cx) / rad
                d2 = dx * dx + dy * dy
                if d2 >= 1.0:
                    continue
                f = (1.0 - d2)
                a = peak * f * f
                if a < 0.004:
                    continue
                self.blend(x, y, r, g, b, a)

    def disc(self, cx, cy, rad, r, g, b, a=1.0):
        y0 = max(0, int(cy - rad))
        y1 = min(self.h - 1, int(cy + rad))
        for y in range(y0, y1 + 1):
            dy = (y - cy) / rad
            s = math.sqrt(max(0.0, 1.0 - dy * dy))
            self.hspan(y, cx - rad * s, cx + rad * s, r, g, b, a)

    def ellipse(self, cx, cy, rx, ry, r, g, b, a=1.0):
        y0 = max(0, int(cy - ry))
        y1 = min(self.h - 1, int(cy + ry))
        for y in range(y0, y1 + 1):
            dy = (y - cy) / ry
            s = math.sqrt(max(0.0, 1.0 - dy * dy))
            self.hspan(y, cx - rx * s, cx + rx * s, r, g, b, a)

    def poly(self, pts, r, g, b, a=1.0):
        """Scanline polygon fill."""
        if len(pts) < 3:
            return
        ys = [p[1] for p in pts]
        y0 = max(0, int(math.ceil(min(ys))))
        y1 = min(self.h - 1, int(math.floor(max(ys))))
        n = len(pts)
        for y in range(y0, y1 + 1):
            xs = []
            for i in range(n):
                x1, y1p = pts[i]
                x2, y2p = pts[(i + 1) % n]
                if (y1p <= y < y2p) or (y2p <= y < y1p):
                    t = (y - y1p) / (y2p - y1p)
                    xs.append(x1 + t * (x2 - x1))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                self.hspan(y, xs[k], xs[k + 1], r, g, b, a)

    def thick_line(self, x0, y0, x1, y1, wdt, r, g, b, a=1.0):
        """Thick segment drawn as a chain of small discs (step = wdt/2)."""
        dx = x1 - x0
        dy = y1 - y0
        dist = math.hypot(dx, dy)
        steps = max(1, int(dist / max(1.0, wdt * 0.45)))
        rad = wdt / 2.0
        for s in range(steps + 1):
            t = s / steps
            self.disc(x0 + dx * t, y0 + dy * t, rad, r, g, b, a)

    def curve(self, pts, wdt, r, g, b, a=1.0):
        for i in range(len(pts) - 1):
            self.thick_line(pts[i][0], pts[i][1], pts[i + 1][0],
                            pts[i + 1][1], wdt, r, g, b, a)


def lerp(c1, c2, t):
    return (int(c1[0] + (c2[0] - c1[0]) * t + 0.5),
            int(c1[1] + (c2[1] - c1[1]) * t + 0.5),
            int(c1[2] + (c2[2] - c1[2]) * t + 0.5))


def wave_path(x0, y0, x1, y1, amp, waves, phase, steps=48):
    """A gently waving vertical ribbon centreline from (x0,y0) to (x1,y1)."""
    pts = []
    for s in range(steps + 1):
        t = s / steps
        x = x0 + (x1 - x0) * t + math.sin(t * waves * math.pi * 2 + phase) * amp * t
        y = y0 + (y1 - y0) * t
        pts.append((x, y))
    return pts


# ------------------------------------------------------------------- scenes
# Variant parameters: dome centre/radii, sun, horizon, farmer, palette lean.
PARAMS = {
    # A: classic centred hero, dome high, terraces below, farmer left-centre.
    "A": dict(cx=512, apex=118, rx=300, ry=215, sun=(790, 600), sun_r=52,
              horizon=648, farmer=430, lean=0.0, tent_len=1.0, dome_a=0.92),
    # B: jellyfish low-left, diagonal sweep, sun right, farmer right.
    "B": dict(cx=392, apex=205, rx=330, ry=235, sun=(830, 585), sun_r=46,
              horizon=660, farmer=700, lean=1.0, tent_len=1.15, dome_a=0.90),
    # C: huge dome cropped by the top edge, tentacles long, farmer centre.
    "C": dict(cx=512, apex=-30, rx=430, ry=300, sun=(210, 610), sun_r=48,
              horizon=640, farmer=512, lean=0.0, tent_len=1.3, dome_a=0.94),
}


def draw_sky(cv, p):
    cv.vgrad(0, p["horizon"], [
        (0, (22, 14, 58)),
        (210, (58, 26, 96)),
        (400, (132, 52, 118)),
        (540, (226, 96, 92)),
        (p["horizon"], (255, 176, 96)),
    ])
    # stars fading in near the top
    for i in range(90):
        sx = (i * 137.5 + 61) % 1024
        sy = (i * 89.3 + 17) % 190
        a = 0.55 - sy / 420.0
        if a > 0.4:
            cv.set(int(sx), int(sy), 235, 225, 255)
    # sun glow + disc
    sx, sy = p["sun"]
    cv.glow(sx, sy, 260, 255, 150, 70, 0.55)
    cv.glow(sx, sy, 120, 255, 210, 120, 0.7)
    cv.disc(sx, sy, p["sun_r"], 255, 226, 160, 1.0)
    cv.disc(sx, sy, p["sun_r"] * 0.62, 255, 244, 205, 1.0)


def draw_mountains(cv, p):
    hz = p["horizon"]
    pts = [(0, hz)]
    x = 0
    i = 0
    while x < 1024:
        x += 90 + (i * 53) % 70
        y = hz - 55 - ((i * 37) % 60)
        pts.append((min(x, 1024), y))
        i += 1
    pts.append((1024, hz))
    cv.poly(pts, 52, 28, 78, 1.0)
    # hazy far ridge, lighter
    pts2 = [(0, hz)]
    x = 0
    i = 0
    while x < 1024:
        x += 120 + (i * 41) % 60
        y = hz - 26 - ((i * 29) % 34)
        pts2.append((min(x, 1024), y))
        i += 1
    pts2.append((1024, hz))
    cv.poly(pts2, 96, 52, 104, 1.0)


def _arc_edge(y_base, sag, step=32):
    """Points along a terrace edge that sags downward toward the centre."""
    pts = []
    x = 0
    while x <= 1024:
        dx = (x - 512) / 512.0
        pts.append((x, y_base + sag * (1.0 - dx * dx)))
        x += step
    return pts


def draw_terraces(cv, p):
    """Curved terrace bands from horizon to the bottom, with water glints."""
    hz = p["horizon"]
    bands = 9
    greens = [(26, 74, 46), (34, 92, 52), (44, 108, 58), (30, 82, 50),
              (52, 118, 62), (38, 96, 54), (58, 124, 64), (46, 106, 58),
              (64, 128, 66)]
    # base fill so sagging band edges never expose the bare canvas
    for y in range(hz, H):
        cv.hspan(y, 0, W - 1, greens[0][0], greens[0][1], greens[0][2], 1.0)
    for b in range(bands):
        t0 = b / bands
        t1 = (b + 1) / bands
        y_top = hz + (H - hz) * t0 * t0
        y_bot = hz + (H - hz) * t1 * t1
        sag_top = 10 + 46 * t0
        sag_bot = 10 + 46 * t1
        top = _arc_edge(y_top, sag_top)
        bot = _arc_edge(y_bot, sag_bot)
        col = lerp(greens[b], (214, 150, 84), 0.18)
        cv.poly(top + list(reversed(bot)), col[0], col[1], col[2], 1.0)
        # bright water line along the band's lower edge
        cv.curve(bot, 3.0, 255, 196, 130, 0.55)
        # a planted green strip just above the water line, for depth
        inner = _arc_edge(y_bot - 6, sag_bot)
        cv.curve(inner, 2.0, 30, 90, 50, 0.5)
    # jellyfish shimmer: vertical glow streaks on the water below the dome
    cx = p["cx"]
    for k in range(7):
        off = (k - 3) * 52
        x = cx + off
        cv.glow(x, hz + 150, 90, 190, 140, 255, 0.16)
        cv.glow(x, hz + 260, 70, 255, 150, 120, 0.12)


def draw_jellyfish(cv, p):
    cx = p["cx"]
    apex = p["apex"]
    rx = p["rx"]
    ry = p["ry"]
    cy = apex + ry  # dome base line
    dome_a = p["dome_a"]
    # halo behind the dome
    cv.glow(cx, cy - ry * 0.35, rx * 1.25, 150, 100, 255, 0.30)
    cv.glow(cx, cy - ry * 0.2, rx * 0.9, 255, 130, 190, 0.22)
    # dome body: TOP half-ellipse only (a bell, not a disc), one smooth
    # row-wise gradient from bright apex to pink rim — no stacked rings.
    y0 = max(0, int(apex))
    y1 = min(cy, H - 1)
    for y in range(y0, y1 + 1):
        dy = (y - cy) / ry
        s = math.sqrt(max(0.0, 1.0 - dy * dy))
        t = (y - apex) / max(1.0, ry)
        col = lerp((250, 248, 255), (205, 150, 235), t)
        a = 0.92 - 0.25 * t
        cv.hspan(y, cx - rx * s, cx + rx * s, col[0], col[1], col[2], a)
    # bright core near the apex
    cv.glow(cx, apex + ry * 0.22, rx * 0.55, 255, 250, 255, 0.55)
    cv.ellipse(cx, apex + ry * 0.30, rx * 0.52, ry * 0.42,
               245, 250, 255, 0.5)
    # dome ribs: radial canals fanning from INSIDE the bell to the rim
    ox, oy = cx, apex + ry * 0.38
    for k in range(-4, 5):
        ang = k * 0.30
        ex = cx + math.sin(ang) * rx * 0.97
        ey = cy - 4 - abs(math.cos(ang)) * 6
        pts = []
        for s in range(21):
            t = s / 20.0
            mx = ox + (ex - ox) * t
            my = oy + (ey - oy) * t
            # bow outward so the rib arcs like a real radial canal
            bow = math.sin(t * math.pi) * 14 * (1 if ang >= 0 else -1)
            pts.append((mx + bow * t, my))
        cv.curve(pts, 3.5, 255, 190, 220, 0.45)
    # rim: glowing band along the bell's lower edge, slightly wavy
    rim = []
    for s in range(65):
        t = s / 64.0
        x = cx - rx * 0.99 + 2 * rx * 0.99 * t
        y = cy + math.sin(t * math.pi * 5 + 0.4) * 5
        rim.append((x, y))
    cv.curve(rim, 16.0, 255, 150, 200, 0.4)
    cv.curve(rim, 6.0, 255, 205, 230, 0.65)
    # oral skirt: wavy translucent band under the dome
    skirt = []
    for s in range(65):
        t = s / 64.0
        x = cx - rx * 0.92 + 2 * rx * 0.92 * t
        y = cy + 8 + math.sin(t * math.pi * 7 + 0.6) * 13
        skirt.append((x, y))
    skirt_top = [(cx - rx * 0.92, cy - 4), (cx + rx * 0.92, cy - 4)]
    cv.poly(skirt_top + list(reversed(skirt)), 255, 175, 215, 0.45)
    cv.curve(skirt, 4.0, 255, 210, 235, 0.6)
    # 5 thick oral arms, wavy ribbons hanging from the dome centre
    arm_cols = [(255, 190, 205), (255, 170, 190), (250, 200, 220),
                (255, 185, 200), (245, 195, 230)]
    tent_len = p["tent_len"]
    for k in range(5):
        x0 = cx + (k - 2) * rx * 0.26
        length = (150 + ((k * 53) % 70)) * tent_len
        path = wave_path(x0, cy + 14, x0 + (k - 2) * 26, cy + 14 + length,
                         22, 2.2, k * 1.3)
        cv.curve(path, 15 - abs(k - 2) * 2.0, *arm_cols[k], a=0.85)
        cv.curve(path, 6.0, 255, 235, 245, 0.5)
    # fine tentacles from the rim, long and faint
    for k in range(26):
        t = k / 25.0
        x0 = cx - rx * 0.95 + 2 * rx * 0.95 * t
        length = (120 + ((k * 47) % 110)) * tent_len
        path = wave_path(x0, cy + 6, x0 + math.sin(k * 2.1) * 30,
                         cy + 6 + length, 14, 2.6, k * 0.9)
        cv.curve(path, 2.5, 255, 200, 225, 0.5)
    # rim sparkle dots
    for k in range(14):
        t = k / 13.0
        x = cx - rx * 0.9 + 2 * rx * 0.9 * t
        y = cy + math.sin(t * math.pi * 7 + 0.6) * 13
        cv.disc(x, y, 3.0, 255, 230, 245, 0.8)


def draw_farmer(cv, p):
    fx = p["farmer"]
    fy = 948
    # tiny farmer silhouette with a conical hat, standing on a terrace edge
    cv.poly([(fx - 7, fy), (fx + 7, fy), (fx + 4, fy - 26),
             (fx - 4, fy - 26)], 24, 16, 34, 1.0)          # body
    cv.disc(fx, fy - 30, 4.5, 24, 16, 34, 1.0)              # head
    cv.poly([(fx - 13, fy - 32), (fx + 13, fy - 32), (fx, fy - 46)],
            214, 164, 92, 1.0)                               # conical hat
    cv.thick_line(fx - 5, fy - 12, fx - 16, fy + 2, 3.0, 24, 16, 34, 1.0)
    # warm lanterns on poles nearby
    for lx, lh in ((fx - 74, 30), (fx + 66, 38), (fx + 132, 26)):
        cv.thick_line(lx, fy + 4, lx, fy - lh, 3.0, 30, 20, 40, 1.0)
        cv.glow(lx, fy - lh - 4, 26, 255, 180, 90, 0.75)
        cv.disc(lx, fy - lh - 4, 5.0, 255, 205, 120, 1.0)
    # second tiny figure far side for depth
    gx = 880 if p["farmer"] < 600 else 180
    cv.poly([(gx - 5, 992), (gx + 5, 992), (gx + 3, 972), (gx - 3, 972)],
            24, 16, 34, 1.0)
    cv.disc(gx, 969, 3.5, 24, 16, 34, 1.0)


def draw_birds(cv, p):
    for bx, by, s in ((180, 210, 14), (240, 180, 11), (840, 160, 13),
                      (880, 200, 10), (700, 130, 9)):
        cv.thick_line(bx - s, by, bx, by - 5, 2.5, 30, 20, 50, 0.9)
        cv.thick_line(bx, by - 5, bx + s, by, 2.5, 30, 20, 50, 0.9)


def render(scene):
    p = PARAMS[scene]
    cv = Canvas(W, H)
    draw_sky(cv, p)
    draw_mountains(cv, p)
    draw_terraces(cv, p)
    draw_jellyfish(cv, p)
    draw_farmer(cv, p)
    draw_birds(cv, p)
    # gentle deterministic grain to kill banding
    for y in range(0, H, 2):
        row = cv.px[y]
        for x in range(0, W, 3):
            n = ((x * 374761393 + y * 668265263) ^ 0x5DEECE66D) & 7
            if n == 0:
                i = x * 3
                row[i] = max(0, row[i] - 2)
                row[i + 1] = max(0, row[i + 1] - 2)
                row[i + 2] = max(0, row[i + 2] - 2)
    return cv


# --------------------------------------------------------------------- PNG
def encode_png(cv):
    raw = bytearray()
    for y in range(cv.h):
        raw.append(0)
        raw += cv.px[y]
    comp = zlib.compress(bytes(raw), 6)

    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        c += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        return c

    ihdr = struct.pack(">IIBBBBB", cv.w, cv.h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", comp) + chunk(b"IEND", b""))


def main():
    scene = os.environ.get("SCENE", "A").upper()
    if scene not in PARAMS:
        scene = "A"
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(outdir, exist_ok=True)
    data = encode_png(render(scene))
    with open(os.path.join(outdir, "entry.png"), "wb") as f:
        f.write(data)


if __name__ == "__main__":
    main()
