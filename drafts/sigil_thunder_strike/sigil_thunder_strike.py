"""sigil_thunder_strike: an arm goes up, a sigil lights under the target, and on the downswing a thick bolt comes
down on it; the target jolts through the aftershocks.

Side view, 1 direction facing east plus mirror. 160x240 cell, pivot on the target's foot, 30 fps, 90 frames (3 s),
one-shot. Painterly HD (more tones, no outline, soft volumes), strong glow, storm violet ramp.

States (frames at 30 fps):
| state       | frames   | s    | what moves                                                         |
|-------------|----------|------|--------------------------------------------------------------------|
| raise       | 0 to 35  | 1.2  | caster arm up, hand charge; sigil draws in and turns; storm knot   |
| hold        | 36 to 40 | 0.17 | sigil at full, motes rise                                          |
| strike      | 41 to 48 | 0.27 | leader (41), return stroke white peak (42, 43), flash, sparks, ring |
| aftershocks | 49 to 74 | 0.87 | restrikes down the same channel at 51, 59, 67, each weaker, last forks |
| fade        | 75 to 89 | 0.5  | channel embers, smoke rises, the sigil breaks into motes           |

The sheet is the effect alone and anchors at the target (part `impact`); `cast` is a small hand-charge sheet that
anchors at the caster's hand. The caster and the dummy are drawn in the previews only.

Run: ../../.venv/bin/python sigil_thunder_strike.py [--peak]   (writes out/, exits 1 on a check)
"""
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "kit"))
import caster as cs  # noqa: E402
import export as ex  # noqa: E402
import facing as fc  # noqa: E402
import fxlib as fl  # noqa: E402
import pfx  # noqa: E402
import target as tg  # noqa: E402

NAME = "sigil_thunder_strike"
OUT = Path(__file__).parent / "out"
W, H = 160, 240
PIVOT = (80, 214)                       # target foot, ground line
FPS, N = 30, 90
SEED = 11

RAISE, HOLD, STRIKE, AFTER, FADE = (0, 35), (36, 40), (41, 48), (49, 74), (75, 89)
LEADER = STRIKE[0]
PEAK = LEADER + 1
RESTRIKES = [(51, 0.72), (59, 0.56), (67, 0.44)]     # frame, strength
STATES = {"raise": list(RAISE), "hold": list(HOLD), "strike": list(STRIKE), "aftershocks": list(AFTER),
          "fade": list(FADE)}

# storm violet, painterly: 9 tones shadow to white core
TONES = ["#140d33", "#22185a", "#33267e", "#4a38b4", "#6f5cff", "#8f8cff", "#b8c4ff", "#e2e6ff", "#ffffff"]
RGB = np.stack([pfx._hex(c) / 255.0 for c in TONES])
SMOKE = [pfx._hex(c) / 255.0 for c in ("#1c1630", "#2c2450", "#3f3772", "#5c5596")]
LIGHT_RAMP = ["#2a1a70", "#6f5cff", "#b8c4ff", "#ffffff"]

GX, GY = PIVOT
TOP = 26                                # where the bolt leaves the storm knot
SX, SRX, SRY = GX, 58.0, 13.0           # sigil centre x, radii (side view: flattened ellipse)
FLAT = SRY / SRX

YY, XX = np.mgrid[0:H, 0:W].astype(float)


def ease(s):
    s = min(max(s, 0.0), 1.0)
    return s * s * (3 - 2 * s)


def span(f, a, b):
    return min(max((f - a) / max(b - a, 1e-6), 0.0), 1.0)


class Canvas:
    """Float RGBA canvas with straight-alpha 'over' compositing, plus the light buffer."""

    def __init__(self, h=H, w=W):
        self.rgb = np.zeros((h, w, 3))
        self.a = np.zeros((h, w))
        self.L = np.zeros((h, w))

    def over(self, alpha, rgb):
        alpha = np.clip(alpha, 0, 1)
        if np.ndim(rgb) == 1:
            rgb = np.broadcast_to(rgb, self.rgb.shape)
        na = alpha + self.a * (1 - alpha)
        self.rgb = (rgb * alpha[..., None] + self.rgb * (self.a * (1 - alpha))[..., None]) / np.maximum(na, 1e-6)[..., None]
        self.a = na

    def tones(self, t, alpha):
        """Paint a tone map (float index into TONES, -1 empty) with per-pixel alpha."""
        on = t >= 0
        ti = np.clip(np.round(t), 0, len(TONES) - 1).astype(int)
        self.over(np.where(on, alpha, 0.0), RGB[ti])

    def u8(self):
        a = np.where(self.a > 0.02, self.a, 0.0)
        return (np.concatenate([self.rgb, a[..., None]], -1).clip(0, 1) * 255).round().astype(np.uint8)


def glow(L, x, y, r, k, flat=1.0):
    d = np.hypot(XX[:L.shape[0], :L.shape[1]] - x, (YY[:L.shape[0], :L.shape[1]] - y) / flat) / r
    L += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)


def glow_poly(L, pts, r, k, fade_top=True):
    """Light along a polyline; the light dims toward the storm knot so it never reaches the top edge."""
    pts = np.asarray(pts, float)
    best = np.full(L.shape, np.inf)
    for a, b in zip(pts[:-1], pts[1:]):
        best = np.minimum(best, cs.seg_d(XX, YY, tuple(a), tuple(b)))
    d = best / r
    v = np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)
    if fade_top:
        v *= np.clip((YY - 4) / 40.0, 0, 1)
    v *= np.clip((H - 3 - YY) / 22.0, 0, 1)
    L += v


def ell_d(cx, cy, rx, ry):
    """Approximate pixel distance to an ellipse outline, and the angle of each pixel on it."""
    dx, dy = XX + 0.5 - cx, YY + 0.5 - cy
    g = np.hypot(dx / rx, dy / ry)
    gx, gy = dx / rx ** 2, dy / ry ** 2
    grad = np.hypot(gx, gy) / np.maximum(g, 1e-6)
    return (g - 1) / np.maximum(grad, 1e-6), np.arctan2(dy / ry, dx / rx), g


# ---------------------------------------------------------------- bolt path
def bolt_path(rng, x0, y0, x1, y1, n, amp):
    """Jagged channel: a random walk across, pulled back to the line, with a sharp kink at every node."""
    pts = []
    off = 0.0
    for i in range(n + 1):
        t = i / n
        if 0 < i < n:
            off = off * 0.55 + rng.uniform(-1, 1) * amp * math.sin(math.pi * t) ** 0.5
        else:
            off = 0.0
        pts.append((x0 + (x1 - x0) * t + off, y0 + (y1 - y0) * t + rng.uniform(-1.5, 1.5) * (0 < i < n)))
    return np.array(pts)


def jag(rng, pts, k, amp):
    """Fine zigzag: each segment split into k pieces, the new nodes pushed across it, so a run reads crackling."""
    out = [pts[0]]
    for p, q in zip(pts[:-1], pts[1:]):
        d = q - p
        n = np.array([-d[1], d[0]]) / (np.hypot(*d) or 1)
        for j in range(1, k):
            out.append(p + d * j / k + n * rng.uniform(-amp, amp))
        out.append(q)
    return np.array(out)


def make_channel(seed):
    rng = np.random.default_rng(seed + 101)
    coarse = bolt_path(rng, GX + 4, TOP, GX, GY - 4, 15, 11)
    main = jag(rng, coarse, 3, 2.0)
    branches = []
    for n_, i in enumerate(sorted(rng.choice(np.arange(2, 12), 7, replace=False))):
        a = coarse[i]
        side = 1 if (n_ + (rng.random() < 0.2)) % 2 else -1
        ln = rng.uniform(22, 50) * (1.15 - i / 15)
        ang = math.radians(90 - side * rng.uniform(35, 62))
        end = (min(max(a[0] + math.cos(ang) * ln, 12), W - 12), min(a[1] + math.sin(ang) * ln, GY - 8))
        pts = jag(rng, bolt_path(rng, a[0], a[1], end[0], end[1], 5, 3.5), 2, 1.4)
        branches.append((pts, i))
        # a twig off the branch, splitting again
        m = pts[len(pts) // 2]
        ang2 = ang + side * rng.uniform(-0.2, 0.6)
        ln2 = ln * rng.uniform(0.35, 0.55)
        end2 = (min(max(m[0] + math.cos(ang2) * ln2, 12), W - 12), min(m[1] + math.sin(ang2) * ln2 + 4, GY - 8))
        branches.append((jag(rng, bolt_path(rng, m[0], m[1], end2[0], end2[1], 3, 2.5), 2, 1.0), i))
    # the last restrike forks off the channel halfway down
    k = 8 * 3
    fork = np.vstack([main[:k + 1], jag(rng, bolt_path(rng, *main[k], GX - 22, GY - 2, 7, 8), 3, 1.8)[1:]])
    return main, branches, fork


# ---------------------------------------------------------------- bolt drawing
def draw_bolt(c, pts, w, heat, alpha=1.0, light=1.0, tip=None, top_fade=True):
    """Thick bolt: white core, pale and violet bands, a soft translucent fringe. heat 0..1 cools the core tone.
    tip clips the channel at that y (the leader on its way down)."""
    pts = np.asarray(pts, float)
    if tip is not None:
        keep = [p for p in pts if p[1] <= tip]
        j = len(keep)
        if j < len(pts) and j > 0:
            a, b = pts[j - 1], pts[j]
            s = (tip - a[1]) / max(b[1] - a[1], 1e-6)
            keep.append(a + (b - a) * s)
        pts = np.array(keep)
        if len(pts) < 2:
            return
    d, t, sd = fl.stroke(XX + 0.5, YY + 0.5, pts, w * 0.8, w)
    hw = w / 2
    q = -d / max(hw, 0.5)                                      # 0 at the edge, 1 on the centre line
    top = 8 * heat
    tone = np.where(q > 0.62, top, np.where(q > 0.35, top - 1.2, np.where(q > 0.1, top - 2.4, top - 3.4)))
    tone = np.where(sd < -0.3, tone + 0.6, tone)               # the side to the top-left a step lighter
    tone = np.where(d < 0, np.clip(tone, 2, 8), -1)
    fr1 = (d >= 0) & (d < 1.3)
    fr2 = (d >= 1.3) & (d < 2.8)
    tone = np.where(fr1, max(top - 4.2, 2), tone)
    tone = np.where(fr2, max(top - 5.5, 1), tone)
    al = np.where(d < 0, 1.0, np.where(fr1, 0.75, np.where(fr2, 0.32, 0.0))) * alpha
    if top_fade:
        al = al * np.clip((YY - TOP + 6) / 10.0, 0, 1)
    c.tones(tone, al)
    if light > 0:
        glow_poly(c.L, pts, max(4, w * 0.9), 0.45 * light)          # tight core
        glow_poly(c.L, pts, max(12, w * 3.0), 0.2 * light)        # pool along the stroke


def draw_residue(c, pts, k, f, seed):
    """Ember line left in the channel between strokes: broken, dim, a faint light."""
    if k <= 0.02:
        return
    d, t, sd = fl.stroke(XX + 0.5, YY + 0.5, pts, 1.6, 2.0)
    n = fl.noise(XX, YY + f * 1.5, 7, seed + 7)
    on = (d < 0) & (n > 0.62 - 0.4 * k)
    tone = np.where(on, 3 + 3 * k + (n > 0.8), -1)
    c.tones(tone, np.where(on, 0.9 * min(1, k * 1.5), 0) * np.clip((YY - TOP + 6) / 10.0, 0, 1))
    glow_poly(c.L, pts, 6, 0.18 * k)


# ---------------------------------------------------------------- storm knot at the top
def draw_knot(c, f, seed, lit):
    """A small churning storm cloud the bolt tears out of: translucent puffs, lit from inside on the strike."""
    grow = ease(span(f, 18, 38))
    gone = ease(span(f, 70, 88))
    vis = grow * (1 - gone)
    if vis <= 0.01:
        return
    rng = np.random.default_rng(seed + 31)
    sm = np.stack(SMOKE)
    # back puffs first (wide, dark), then a front row (smaller, lighter): one churning mass, flatter than tall
    for j in range(16):
        row = j // 8
        a = (j % 8) / 8 * math.tau + f * 0.035 * (1 if row else -1) + rng.uniform(-0.3, 0.3)
        rx = (30 - 10 * row) * (0.55 + 0.45 * grow)
        px = GX + 4 + math.cos(a) * rx + rng.uniform(-2, 2)
        py = 20 + math.sin(a) * (4 + 2 * row) + 2 * row - 3 * gone
        r = (8 + 4 * rng.random() - 2 * row) * (0.5 + 0.5 * grow) * (1 + 0.3 * gone)
        dx, dy = XX + 0.5 - px, YY + 0.5 - py
        dd = np.hypot(dx, dy * 1.3) / r
        inside = dd < 1
        lightness = np.clip(0.35 + 0.2 * row - (dx + dy) / (3.0 * r), 0, 1)   # lit top-left, soft volume
        t = lightness * 3
        i0 = np.clip(t.astype(int), 0, 2)
        fr = (t - i0)[..., None]
        col = sm[i0] * (1 - fr) + sm[i0 + 1] * fr
        glowin = lit * np.clip(1 - np.hypot(XX - GX - 4, (YY - 24) * 2) / 34, 0, 1)[..., None]
        col = col * (1 - glowin) + RGB[6] * glowin
        al = np.where(inside, np.clip((1 - dd) * 2.5, 0, 1) * 0.8 * vis, 0)
        al *= np.clip((YY - 5) / 4.0, 0, 1) * np.clip((W - 5 - XX) / 4.0, 0, 1) * np.clip((XX - 4) / 4.0, 0, 1)
        c.over(al, col)
    if lit > 0:
        glow(c.L, GX + 4, 22, 22, 0.35 * lit)


# ---------------------------------------------------------------- sigil
def sigil_maps(f):
    """Tone and alpha of the sigil at frame f, split into the back half (behind the target) and the front."""
    draw_in = span(f, 0, 32)
    spin = f * 0.035
    tone = np.full((H, W), -1.0)
    al = np.zeros((H, W))
    d0, th, g = ell_d(SX, GY, SRX, SRY)
    d1, _, _ = ell_d(SX, GY, SRX - 8, SRY - 1.9)
    d2, _, _ = ell_d(SX, GY, 34, 34 * FLAT)
    d3, _, _ = ell_d(SX, GY, 7, 7 * FLAT)
    front = np.sin(th) > 0                                   # the near half of the ground circle
    depth = np.where(front, 0.0, -1.0)

    def sweep(start, length, ph):
        s = ((th - ph) % math.tau) / math.tau
        return s <= np.clip((draw_in - start) / length, 0, 1)

    def put(m, t, a):
        nonlocal tone, al
        tone = np.where(m, np.maximum(tone, t + depth), tone)
        al = np.where(m, np.maximum(al, a), al)

    put((np.abs(d0) < 0.85) & sweep(0.0, 0.55, -spin), 6, 1.0)
    put((np.abs(d0) < 1.8) & (np.abs(d0) >= 0.85) & sweep(0.0, 0.55, -spin), 4, 0.55)
    put((np.abs(d1) < 0.6) & sweep(0.15, 0.55, spin + 1), 5, 0.9)
    # runic notches between the two outer rings, every third one long
    ang = (th + spin) % (math.tau / 24)
    notch = (np.abs(ang - math.tau / 48) < 0.045) & (d0 < -1.2) & (d1 > 0.6)
    longn = ((np.floor((th + spin) / (math.tau / 24)) % 3) == 0)
    put(notch & (longn | (d1 > 2.5)) & sweep(0.25, 0.5, -spin), 5, 0.9)
    put((np.abs(d2) < 0.6) & sweep(0.3, 0.5, spin), 5, 0.85)
    put((np.abs(d3) < 0.7) & (draw_in > 0.8), 6, 1.0)
    # hexagram on the inner ring, turning the other way, drawn edge by edge
    for tri in range(2):
        vs = []
        for k in range(3):
            a = -spin * 1.4 + tri * math.pi / 3 + k * math.tau / 3
            vs.append((SX + math.cos(a) * 34, GY + math.sin(a) * 34 * FLAT))
        for k in range(3):
            e = tri * 3 + k
            p = np.clip((draw_in - 0.45 - e * 0.07) / 0.12, 0, 1)
            if p <= 0:
                continue
            a, b = vs[k], vs[(k + 1) % 3]
            b = (a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p)
            m = cs.seg_d(XX + 0.5, YY + 0.5, a, b) < 0.6
            put(m, 5, 0.85)
    return tone, al, front, d0, th


def draw_sigil(c, f, seed):
    if f > FADE[1]:
        return
    tone, al, front, d0, th = sigil_maps(f)
    draw_in = span(f, 0, 32)
    # brightness: builds through raise, pulses on hold, white flash on the strike and each restrike
    b = 0.45 + 0.4 * draw_in + 0.1 * math.sin(f * 0.9) * (f >= HOLD[0])
    for fr, s in [(PEAK, 1.0)] + RESTRIKES:
        dt = f - fr
        if dt >= 0:
            b += 1.2 * s * math.exp(-dt * 0.5)
    # the fade breaks the sigil apart by angle, from noise
    brk = ease(span(f, FADE[0] - 4, FADE[1] - 1))
    if brk > 0:
        n = fl.noise(XX, YY * 4, 10, seed + 3)
        al = np.where(n < 1.05 - 1.15 * brk, al, 0) * (1 - 0.6 * brk)
    t = np.where(tone >= 0, np.clip(tone + (b - 1) * 2.0, 1, 8), -1)
    c.tones(t, al)
    # light: core along the rings, a pool, a tall ground pool that swells on the strike
    k = (0.25 + 0.3 * draw_in) * min(b, 2.2) * (1 - brk)
    glow_ring_flat(c.L, SRX, 3.0, 0.32 * k)
    glow_ring_flat(c.L, SRX, 9.0, 0.14 * k)
    glow_ring_flat(c.L, 34, 3.0, 0.16 * k)
    # the drawing head: a hot spark travelling round the outer ring while it draws in
    if draw_in < 0.55:
        a = (draw_in / 0.55) * math.tau - f * 0.035
        hx, hy = SX + math.cos(a) * SRX, GY + math.sin(a) * SRY
        twinkle(c, hx, hy, 2, 1.0)


def glow_ring_flat(L, R, r, k):
    d = np.abs(ell_d(SX, GY, R, R * FLAT)[0]) / r
    L += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)


def twinkle(c, x, y, size, k):
    xi, yi = int(round(x)), int(round(y))
    for dx, dy, t in [(0, 0, 8)] + [(s * i, 0, 7 - i) for s in (-1, 1) for i in range(1, size + 1)] + \
            [(0, s * i, 7 - i) for s in (-1, 1) for i in range(1, size + 1)]:
        if 1 <= xi + dx < W - 1 and 1 <= yi + dy < H - 1:
            m = np.zeros((H, W), bool)
            m[yi + dy, xi + dx] = True
            c.tones(np.where(m, t, -1), m * 1.0)
    glow(c.L, x, y, 4, 0.45 * k)
    glow(c.L, x, y, 11, 0.2 * k)


# ---------------------------------------------------------------- particles
def sparks(seed, f0, n, power):
    rng = np.random.default_rng(seed + 500 + f0)
    out = []
    for i in range(n):
        ang = math.radians(rng.uniform(200, 340))
        sp = rng.uniform(1.4, 4.2) * power
        out.append(dict(x=GX + rng.uniform(-4, 4), y=GY - 3, vx=math.cos(ang) * sp * 1.1, vy=math.sin(ang) * sp,
                        life=rng.integers(6, 15), f0=f0 + rng.integers(0, 2)))
    return out


def draw_sparks(c, f, seed):
    for f0, s in [(PEAK, 1.0)] + RESTRIKES:
        for p in sparks(seed, f0, int(22 * s), 0.6 + 0.4 * s):
            t = f - p["f0"]
            if t < 0 or t > p["life"]:
                continue
            x = p["x"] + p["vx"] * t
            y = p["y"] + p["vy"] * t + 0.18 * t * t
            if y > GY + 1 or not (6 < x < W - 6):
                continue
            vx, vy = p["vx"], p["vy"] + 0.36 * t
            ln = min(4, math.hypot(vx, vy) * 0.9)
            nv = math.hypot(vx, vy) or 1
            tail = (x - vx / nv * ln, y - vy / nv * ln)
            life = 1 - t / p["life"]
            m = cs.seg_d(XX + 0.5, YY + 0.5, (x, y), tail) < 0.55
            c.tones(np.where(m, 3 + 5 * life, -1), m * (0.5 + 0.5 * life))
            glow(c.L, x, y, 3, 0.3 * life)
            glow(c.L, x, y, 8, 0.12 * life)


def draw_motes(c, f, seed):
    """Motes rise off the sigil ring during hold and as it breaks apart."""
    rng = np.random.default_rng(seed + 900)
    for i in range(34):
        a = rng.uniform(0, math.tau)
        f0 = rng.uniform(26, 84)
        life = rng.uniform(10, 22)
        t = f - f0
        if t < 0 or t > life or f0 > FADE[1] - 3:
            continue
        if FADE[0] - 30 > f0 > HOLD[1] + 2 and rng.random() < 0.6:
            continue
        r = SRX * rng.uniform(0.55, 1.0)
        x = SX + math.cos(a) * r + math.sin(t * 0.3 + i) * 1.5
        y = GY + math.sin(a) * r * FLAT - t * rng.uniform(0.8, 1.6)
        k = math.sin(math.pi * t / life)
        xi, yi = int(x), int(y)
        if 2 < xi < W - 2 and 2 < yi < H - 2:
            m = np.zeros((H, W), bool)
            m[yi, xi] = True
            c.tones(np.where(m, 5 + 3 * k, -1), m * k)
            glow(c.L, x, y, 4, 0.3 * k)


def draw_flash(c, f):
    """Ground contact: a white disc on the strike, then a shock ring along the ground 3 frames later."""
    for fr, s in [(PEAK, 1.0)] + RESTRIKES:
        dt = f - fr
        if 0 <= dt <= 3:
            rx = (14 + 10 * dt) * (0.6 + 0.4 * s)
            d, _, g = ell_d(GX, GY - 2, rx, rx * 0.32)
            q = np.clip(1 - g, 0, 1)
            inner = 1 - dt / 3
            tone = np.where(g < 1, 4 + 4 * q * inner + 1.5 * inner, -1)
            al = np.where(g < 1, (0.35 + 0.65 * q) * inner + 0.15, 0) * (1 if dt < 3 else 0.4)
            c.tones(tone, al)
            glow(c.L, GX, GY - 4, 22 * (0.6 + 0.4 * s), 0.42 * s * inner)
        dt = f - fr - 2
        if 0 <= dt <= 9:
            R = (18 + 52 * ease(dt / 9) ** 0.7) * (0.55 + 0.45 * s)
            d, th, _ = ell_d(GX, GY, R, R * 0.24)
            life = 1 - dt / 9
            m = np.abs(d) < 0.7 + 0.8 * life
            c.tones(np.where(m, 4 + 3 * life, -1), m * (0.85 * life))
            glow_ring_flat(c.L, R, 4, 0.22 * life * s)


def draw_smoke(c, f, seed):
    rng = np.random.default_rng(seed + 700)
    for i in range(10):
        f0 = PEAK + 1 + rng.integers(0, 6) + (i >= 7) * rng.integers(10, 26)
        t = f - f0
        life = rng.uniform(26, 40)
        if t < 0 or t > life:
            continue
        s = t / life
        px = GX + rng.uniform(-32, 32) + rng.uniform(-0.25, 0.25) * t
        py = GY - 4 - t * rng.uniform(0.35, 0.7)
        r = (4 + rng.uniform(2, 5)) * (0.6 + 0.9 * math.sqrt(s))
        dx, dy = XX + 0.5 - px, YY + 0.5 - py
        dd = np.hypot(dx, dy) / r
        lightness = np.clip(0.5 - (dx + dy) / (2.4 * r), 0, 1)
        ti = np.clip((lightness * 3.2).astype(int), 0, 3)
        n = fl.noise(XX + px * 3, YY + f * 0.6, 5, seed + i)
        al = np.where(dd < 1, (1 - dd ** 2) * 0.55 * (1 - s) ** 1.3, 0) * (1 - ease(span(f, 78, FADE[1]))) * np.where(n > 0.25 + 0.5 * s, 1, 0.35)
        c.over(al, np.stack(SMOKE)[ti])


# ---------------------------------------------------------------- frame
def bolt_state(f):
    """(width, heat, alpha) of the main channel at frame f, or None."""
    table = {PEAK: (8.5, 1.0, 1), PEAK + 1: (7.5, 0.98, 1), PEAK + 2: (6, 0.85, 1), PEAK + 3: (4, 0.72, 0.9),
             PEAK + 4: (2.6, 0.6, 0.7), PEAK + 5: (1.8, 0.52, 0.45)}
    return table.get(f)


def render(f, seed=SEED, parts=False):
    """The effect alone at frame f: (rgba uint8, light float map, colour-only uint8)."""
    c = Canvas()
    main, branches, fork = make_channel(seed)
    lit = 0.0
    for fr, s in [(PEAK, 1.0)] + RESTRIKES:
        if 0 <= f - fr <= 2:
            lit = max(lit, s * (1 - (f - fr) / 3))
    draw_knot(c, f, seed, lit)
    draw_sigil(c, f, seed)
    draw_smoke(c, f, seed)
    # scene pools: one on the ground that grows with the sigil, a column that grows with the storm knot (the
    # charged air between them), and a swell low at the contact on each strike
    out = 1 - ease(span(f, FADE[0], FADE[1] + 2))
    kg = (0.12 + 0.36 * ease(span(f, 0, 32))) * out
    kc = 0.42 * ease(span(f, 16, 40)) * out
    kp = sum(0.3 * s * math.exp(-(f - fr) * 0.35) for fr, s in [(PEAK, 1.0)] + RESTRIKES if f >= fr) * out
    for cx, cy, rx, ry, k in ((GX, GY - 26, 76, 46, kg), (GX, 120, 80, 112, kc), (GX, GY - 34, 76, 74, kp)):
        if k > 0:
            d = np.hypot((XX - cx) / rx, (YY - cy) / ry)
            c.L += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)
    # leader: thin, dim, branchy, on its way down
    if f == LEADER:
        draw_bolt(c, main, 2.4, 0.72, tip=TOP + (GY - TOP) * 0.62, light=0.5)
        for pts, i in branches[:3]:
            if pts[0][1] < TOP + (GY - TOP) * 0.62:
                draw_bolt(c, pts, 1.2, 0.6, light=0.25)
    st = bolt_state(f)
    if st:
        w, heat, a = st
        for pts, i in branches:
            draw_bolt(c, pts, max(1.1, w * 0.24), heat * 0.92, alpha=a, light=0.4 * a)
        draw_bolt(c, main, w, heat, alpha=a, light=a)
    # restrikes: thinner, unbranched, the last forks
    for j, (fr, s) in enumerate(RESTRIKES):
        dt = f - fr
        path = fork if j == len(RESTRIKES) - 1 else main
        if dt == -1:
            draw_bolt(c, path, 1.6, 0.6, tip=TOP + (GY - TOP) * 0.5, light=0.3)
        elif 0 <= dt <= 2:
            draw_bolt(c, path, (8.5 - 2.6 * dt) * s, (1.0 - 0.15 * dt) * (0.85 + 0.15 * s), light=s * (1 - dt / 3))
    # ember residue along the channel between strokes
    last = max([fr for fr, _ in [(PEAK, 1)] + RESTRIKES if fr <= f], default=None)
    if last is not None and f - last >= 3 and f > PEAK + 4:
        k = math.exp(-(f - last - 3) * 0.12) * (1 - ease(span(f, 68, FADE[1] - 4)))
        draw_residue(c, fork if last == RESTRIKES[-1][0] else main, k, f, seed)
    draw_flash(c, f)
    draw_sparks(c, f, seed)
    draw_motes(c, f, seed)
    col = c.u8()
    L = np.clip(c.L, 0, 1)
    light = pfx.tint(np.repeat(L[..., None], 3, -1), LIGHT_RAMP)
    return pfx.composite(col, light), light, col, L


# ---------------------------------------------------------------- cast part: the charge on the caster's hand
CW = CH = 48


def render_cast(f, seed=SEED):
    """A charge orb on the sword-sign hand: builds through raise, flares on the downswing, out by frame 46."""
    yy, xx = np.mgrid[0:CH, 0:CW].astype(float)
    cx = cy = 24.0
    grow = ease(span(f, 4, 34))
    flare = math.exp(-max(f - LEADER, 0) * 0.6) if f >= LEADER - 1 else 0.0
    out = 1 - ease(span(f, LEADER + 1, 46))
    k = (grow * 0.8 + flare * 0.6) * out + (0.02 if f < 47 else 0)
    r = (2 + 2.5 * grow + 2 * flare) * (0.3 + 0.7 * out)
    d = np.hypot(xx + 0.5 - cx, yy + 0.5 - cy) / max(r, 0.5)
    tone = np.where(d < 1, np.clip(5 + 3.5 * (1 - d) * min(1, k * 1.4), 2, 8), -1)
    rgb = RGB[np.clip(np.round(tone), 0, 8).astype(int)]
    a = np.where(d < 1, np.clip(k * 1.3, 0, 1) * (1 - d ** 4), 0)
    L = np.zeros((CH, CW))
    m = np.hypot(xx - cx, yy - cy)
    L += np.where(m < 5, (1 - m / 5) ** 2 * 0.6 * k, 0) + np.where(m < 15, (1 - m / 15) ** 2 * 0.27 * k, 0)
    rng = np.random.default_rng(seed + 40 + f)
    for i in range(int(3 * k) + (f % 3 == 0) * (k > 0.3)):          # little arcs crackling off the orb
        a0 = rng.uniform(0, math.tau)
        p = [(cx + math.cos(a0) * r, cy + math.sin(a0) * r)]
        for s in range(3):
            a0 += rng.uniform(-0.8, 0.8)
            p.append((p[-1][0] + math.cos(a0) * 3, p[-1][1] + math.sin(a0) * 3))
        for q0, q1 in zip(p, p[1:]):
            mm = cs.seg_d(xx + 0.5, yy + 0.5, q0, q1) < 0.55
            rgb = np.where(mm[..., None], RGB[7], rgb)
            a = np.where(mm, 1.0, a)
    col = (np.concatenate([rgb, a[..., None]], -1).clip(0, 1) * 255).round().astype(np.uint8)
    col[col[..., 3] < 6] = 0
    light = pfx.tint(np.repeat(np.clip(L, 0, 1)[..., None], 3, -1), LIGHT_RAMP)
    return pfx.composite(col, light), light, col


# ---------------------------------------------------------------- preview with caster and dummy
PW = 260
OX = PW - W                                    # the effect cell sits on the right
CFOOT = (34.0, float(GY))
HITS = [ex.hit(PEAK, FPS, freeze=0.12, shake=4, push=3, react="stagger")] + \
       [ex.hit(fr, FPS, freeze=0.06, shake=2 if s > 0.5 else 1, push=2, react="flinch") for fr, s in RESTRIKES]


def caster_pose(f):
    front = [(0, "rest"), (10, "chest"), (30, "raise"), (39, "raise"), (LEADER, "point"), (60, "point"),
             (78, "rest")]
    aim = cs.aim_from(CFOOT, 0.44, (OX + GX, GY - 10))
    return cs.pose_at(f, front, [(0, "rest")], aim, 0.0)


def preview(f, seed=SEED):
    rgba, light, col, L = render(f, seed)
    c = Canvas(H, PW)
    # the caster
    g = cs.draw(lambda ys, xs, rgb, a: _over_px(c, ys, xs, rgb, a), (H, PW), CFOOT, 0.44, caster_pose(f), f,
                0.3 + 0.4 * span(f, 10, 40), 0.3 + 0.3 * span(f, 10, 40), hair="loose")
    Lc = np.zeros((H, PW))
    cs.body_light(Lc, g, 0.5 + 0.5 * span(f, 0, 36))
    crgba, clight, ccol = render_cast(f, seed)
    fx_, fy_ = g["finger"]
    x0, y0 = int(round(fx_)) - CW // 2, int(round(fy_)) - CH // 2
    sub = slice(max(y0, 0), min(y0 + CH, H)), slice(max(x0, 0), min(x0 + CW, PW))
    cy0, cx0 = sub[0].start - y0, sub[1].start - x0
    ch, cw = sub[0].stop - sub[0].start, sub[1].stop - sub[1].start
    ca = ccol[cy0:cy0 + ch, cx0:cx0 + cw]
    rgb0 = c.rgb[sub]
    a0 = c.a[sub]
    aa = ca[..., 3] / 255.0
    na = aa + a0 * (1 - aa)
    c.rgb[sub] = (ca[..., :3] / 255.0 * aa[..., None] + rgb0 * (a0 * (1 - aa))[..., None]) / np.maximum(na, 1e-6)[..., None]
    c.a[sub] = na
    cl = clight[cy0:cy0 + ch, cx0:cx0 + cw].max(-1)
    Lc[sub] += cl
    base = c.u8()
    dummy = tg.draw((H, W), (GX, GY), f, HITS, FPS, facing=-1)
    eff = tg.under(col, dummy)
    full = np.zeros((H, PW, 4), np.uint8)
    full[:, OX:] = eff
    full = tg.under(full, base)
    Lall = np.clip(Lc, 0, 1)
    Lall[:, OX:] = np.clip(Lall[:, OX:] + L, 0, 1)
    tl = pfx.tint(np.repeat(Lall[..., None], 3, -1), LIGHT_RAMP)
    return full, tl


def _over_px(c, ys, xs, rgb, a):
    ok = (ys >= 0) & (ys < c.a.shape[0]) & (xs >= 0) & (xs < c.a.shape[1])
    ys, xs = ys[ok], xs[ok]
    rgb = np.broadcast_to(rgb, (len(ok), 3))[ok] if np.ndim(rgb) > 1 else rgb
    a = np.broadcast_to(a, ok.shape)[ok] if np.ndim(a) else a
    a0 = c.a[ys, xs]
    na = a + a0 * (1 - a)
    c.rgb[ys, xs] = (rgb * np.reshape(a, (-1, 1)) + c.rgb[ys, xs] * np.reshape(a0 * (1 - a), (-1, 1))) / \
        np.maximum(na, 1e-6)[:, None]
    c.a[ys, xs] = na


def on_ground(full, tl, bg):
    return pfx.composite(full, tl, bg)


def grid4(frames, path, cols, scale=4):
    h, w = frames[0].shape[:2]
    rows = math.ceil(len(frames) / cols)
    img = np.zeros((rows * h, cols * w, 3), np.uint8)
    for i, fr in enumerate(frames):
        r, q = divmod(i, cols)
        img[r * h:(r + 1) * h, q * w:(q + 1) * w] = fr[..., :3]
    Image.fromarray(img).resize((cols * w * scale, rows * h * scale), Image.NEAREST).save(path)


def light_measure(cols, Ls):
    cov, mean = [], []
    for col, L in zip(cols, Ls):
        ys, xs = np.nonzero(col[..., 3])
        if not len(ys):
            continue
        box = L[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        cov.append((box > 0.03).mean())
        if (box > 0.03).any():
            mean.append(box[box > 0.03].mean())
    return float(np.median(cov)), float(np.median(mean))


def main():
    OUT.mkdir(exist_ok=True)
    if "--peak" in sys.argv:
        fs = [38, LEADER, PEAK, PEAK + 2, RESTRIKES[0][0], RESTRIKES[2][0], 80]
        pv = [preview(f) for f in fs]
        grid4([on_ground(a, b, "#101018") for a, b in pv], OUT / "peak_dark.png", len(fs))
        grid4([on_ground(a, b, "#6a6a78") for a, b in pv], OUT / "peak_mid.png", len(fs))
        Image.fromarray(np.concatenate([on_ground(a, b, "#101018")[..., :3] for a, b in pv], 1)).save(OUT / "peak_1x.png")
        return 0
    frames, lights, cols, Ls = [], [], [], []
    for f in range(N):
        a, b, c_, L = render(f)
        frames.append(a), lights.append(b), cols.append(c_), Ls.append(L)
    cast = [render_cast(f) for f in range(47)]
    bad = ex.check(cols, lights, False, src=__file__)
    bad += [f"cast {b}" for b in ex.check([x[2] for x in cast], [x[1] for x in cast], False)]
    bad += ex.check_seeds(lambda f, sd: render(f, seed=sd)[2], N)
    cov, mean = light_measure(cols, Ls)
    print(f"light: cover {100 * cov:.0f} %, mean {mean:.3f} (strong: 75 to 95 %, 0.12 to 0.18)")

    parts = {"cast": fc.part(f"{NAME}_cast.png", CW, CH, len(cast), FPS, (24, 24), False, "caster",
                             note="pivot on the caster's sword-sign fingertip; starts with the effect at frame 0"),
             "impact": fc.part(f"{NAME}.png", W, H, N, FPS, PIVOT, False, "target",
                               note="pivot on the target's foot; the bolt falls straight down, so there is no travel "
                                    "part and the caster to target range is free")}
    poses = [ex.pose(0.0, "windup"), ex.pose(1.0, "channel"), ex.pose(LEADER / FPS, "release", "snap"),
             ex.pose(1.6, "follow"), ex.pose(2.6, "recover")]
    extra = dict(fc.meta("side", W, H, PIVOT), glow="strong", parts=parts)
    fc.check(extra)
    meta = ex.write(OUT, NAME, frames, FPS, PIVOT, False, light=lights, color=cols, states=STATES, hits=HITS,
                    poses=poses, target={"x": 0, "react": "stagger"}, extra=extra)
    ex.write(OUT, f"{NAME}_cast", [x[0] for x in cast], FPS, (24, 24), False, light=[x[1] for x in cast],
             color=[x[2] for x in cast], extra=dict(fc.meta("side", CW, CH, (24, 24)), glow="strong"))
    bad += ex.check_act(meta["meta"]["beanfx"].get("act", {}), N, FPS, False)

    pv = [preview(f) for f in range(N)]
    dark = [on_ground(a, b, "#101018") for a, b in pv]
    mid = [on_ground(a, b, "#6a6a78") for a, b in pv]
    pfx.strip(frames, OUT / f"{NAME}_1x.png")
    grid4(dark[::3], OUT / f"{NAME}_4x_dark.png", 10)
    grid4(mid[::3], OUT / f"{NAME}_4x_mid.png", 10)
    pfx.gif(ex.hitstop(dark, HITS, FPS), OUT / f"{NAME}.gif", FPS, scale=3)
    for b in bad:
        print(b)
    print("ok" if not bad else f"{len(bad)} problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
