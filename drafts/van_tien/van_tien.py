"""Arrow Storm: a volley of about 120 arrows flashes high in the sky, a shadow sweeps the field, then the arrows
rain down on a slant, stick in the ground quivering with dust and sparks, and the dust settles over a field of
arrows. General mode, 320x200, 120 frames at 24 fps, one-shot, soft style, glow medium, side view.

States (frames, 24 fps):
  signal  0-11   the first arrows come in from afar as glints high at the upper left, the shadow spreads
  rain    0-84   three overlapping volleys, each arrow flies one path from a far glint to the ground, speeding up
                 (launch 0-72, flight 11-13 frames, about 30 px a frame at the end)
  hit    12-86   each arrow sticks, quivers, throws dust and a few sparks
  settle 86-119  dust settles, the stuck arrows stay
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent / "kit"))
import pfx  # noqa: E402

NAME = "van_tien"
W, H, N, FPS = 320, 200, 120, 24
OUT = Path(__file__).parent / "out"

SIGNAL0, SIGNAL_N = 0, 12
RAIN0, RAIN_N = SIGNAL0 + SIGNAL_N, 80
LAUNCH_LAST = 72
WAVES = 3
SETTLE0 = 86

GROUND_Y = 172.0
FIELD = (128.0, 298.0)                # x range the arrows land in
APEX_Y = 26.0                        # where each arrow comes into view
SLANT = math.radians(58)             # fall angle below the horizontal
NA = 220

WOOD = ["#3a2414", "#6e4826", "#a8783c"]
STEEL = ["#2c3444", "#7c8aa0", "#e8f0ff"]
FLETCH = ["#8a7a68", "#c83828", "#e8dccb"]
DUST = ["#4a3c34", "#7a6656", "#a89480"]
LIGHT_RAMP = ["#1c2a48", "#7c9ad0", "#e0ecff", "#ffffff"]
SPARK = "#fff2c8"

YY, XX = np.mgrid[0:H, 0:W].astype(float)
rng = np.random.default_rng(7)


def hexf(s):
    return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], float) / 255.0


def ease_io(s):
    s = np.clip(s, 0, 1)
    return s * s * (3 - 2 * s)


def eout(s):
    s = min(max(s, 0.0), 1.0)
    return 1 - (1 - s) ** 3


def _win(x0, x1, y0, y1):
    xa, xb = max(int(x0), 0), min(int(x1) + 2, W)
    ya, yb = max(int(y0), 0), min(int(y1) + 2, H)
    return slice(ya, max(yb, ya)), slice(xa, max(xb, xa))


def seg_d(X, Y, a, b):
    ex, ey = b[0] - a[0], b[1] - a[1]
    h = np.clip(((X - a[0]) * ex + (Y - a[1]) * ey) / (ex * ex + ey * ey or 1e-9), 0, 1)
    return np.hypot(X - a[0] - ex * h, Y - a[1] - ey * h)


class Frame:
    def __init__(self):
        self.rgb = np.zeros((H, W, 3))
        self.a = np.zeros((H, W))
        self.L = np.zeros((H, W))

    def over(self, ys, xs, rgb, a):
        ys, xs = np.asarray(ys, int), np.asarray(xs, int)
        ok = (ys >= 0) & (ys < H) & (xs >= 0) & (xs < W)
        a = np.broadcast_to(np.asarray(a, float), ok.shape)[ok]
        rgb = np.broadcast_to(np.asarray(rgb, float), (*ok.shape, 3))[ok]
        ys, xs = ys[ok], xs[ok]
        a0 = self.a[ys, xs]
        na = a + a0 * (1 - a)
        self.rgb[ys, xs] = (rgb * a[:, None] + self.rgb[ys, xs] * (a0 * (1 - a))[:, None]) / np.maximum(na, 1e-6)[:, None]
        self.a[ys, xs] = na

    def dot(self, x, y, col, a=1.0):
        self.over(np.array([int(round(y))]), np.array([int(round(x))]), hexf(col) if isinstance(col, str) else col, a)

    def glow(self, x, y, r, k, flat=1.0):
        if k <= 0:
            return
        sy, sx = _win(x - r, x + r, y - r * flat, y + r * flat)
        d = np.hypot(XX[sy, sx] - x, (YY[sy, sx] - y) / flat) / r
        self.L[sy, sx] += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)

    def glow_line(self, p0, p1, r, k):
        if k <= 0:
            return
        sy, sx = _win(min(p0[0], p1[0]) - r, max(p0[0], p1[0]) + r, min(p0[1], p1[1]) - r, max(p0[1], p1[1]) + r)
        d = seg_d(XX[sy, sx], YY[sy, sx], p0, p1) / r
        self.L[sy, sx] += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)

    def rgba(self):
        return np.dstack([self.rgb, self.a])


def line(fr, p0, p1, c0, c1, a0, a1):
    c0 = hexf(c0) if isinstance(c0, str) else np.asarray(c0, float)
    c1 = hexf(c1) if isinstance(c1, str) else np.asarray(c1, float)
    n = int(max(abs(p1[0] - p0[0]), abs(p1[1] - p0[1]))) + 1
    t = np.linspace(0, 1, n)
    xs = np.round(p0[0] + (p1[0] - p0[0]) * t).astype(int)
    ys = np.round(p0[1] + (p1[1] - p0[1]) * t).astype(int)
    fr.over(ys, xs, c0[None] * (1 - t[:, None]) + c1[None] * t[:, None], a0 + (a1 - a0) * t)


def puff(fr, x, y, r, a):
    sy, sx = _win(x - r, x + r, y - r, y + r)
    X, Y = XX[sy, sx], YY[sy, sx]
    m = np.hypot(X - x, (Y - y) * 1.25) <= r * (1 + 0.15 * np.sin(np.arctan2(Y - y, X - x) * 4 + x))
    s = (X - x) + (Y - y)
    tone = np.where(s < -r * 0.35, 2, np.where(s > r * 0.4, 0, 1))
    ys, xs = np.nonzero(m)
    fr.over(ys + sy.start, xs + sx.start, np.stack([hexf(c) for c in DUST])[tone[ys, xs]], a)


# ---- the volley ----
ARROWS = []
launch = SIGNAL0 - 1 + (LAUNCH_LAST - SIGNAL0 + 1) * np.sort((np.arange(NA) % WAVES + rng.beta(1.6, 2.2, NA) * 1.3) / (WAVES + 0.3))
for n in range(NA):
    gy = GROUND_Y + rng.uniform(-10, 12)                      # depth on the field: lower is nearer
    gx = rng.uniform(*FIELD)
    ang = SLANT + rng.uniform(-0.08, 0.08)
    fly = rng.uniform(11, 13)
    sy0 = APEX_Y + rng.uniform(-4, 8)
    dx = (gy - sy0) / math.tan(ang)
    if gx - dx < 14:                                          # enter the cell inside its left margin
        sy0 += (14 - (gx - dx)) * math.tan(ang)
        dx = gx - 14
    ARROWS.append(dict(t0=float(launch[n]), fly=fly * (gy - sy0) / (gy - APEX_Y), start=(gx - dx, sy0), end=(gx, gy),
                       ang=ang, depth=(gy - GROUND_Y + 10) / 22, sink=rng.uniform(2.5, 5.0),
                       spark=rng.random() < 0.45, dust=rng.random() < 0.6, ph=rng.uniform(0, 6.28),
                       dseed=rng.uniform(-2, 2, 4), appear=float(rng.uniform(-1.5, 10))))
ARROWS.sort(key=lambda a: a["end"][1])                       # far first
ALEN = 14.0


def arrow(fr, tip, ang, scale, a=1.0, sink=0.0, wob=0.0):
    """An arrow, tip at `tip`, pointing along ang (y down). sink hides the first px in the ground; wob bends the tail."""
    ux, uy = math.cos(ang), math.sin(ang)
    px, py = -uy, ux
    ln = ALEN * scale
    tail = (tip[0] - ux * ln + px * wob, tip[1] - uy * ln + py * wob)
    n = int(ln) + 2
    t = np.linspace(0, 1, n)
    xs = tip[0] + (tail[0] - tip[0]) * t
    ys = tip[1] + (tail[1] - tip[1]) * t
    seg = t * ln
    keep = seg >= sink
    tone = np.where(seg < 2.2, 3, np.where(seg > ln - 3.2, 6, 0))     # 3 head, 0 shaft, 6 fletch
    cols = []
    for s_, tn in zip(seg, tone):
        if tn == 3:
            cols.append(hexf(STEEL[2] if s_ < 0.8 else STEEL[1]))
        elif tn == 6:
            cols.append(hexf(FLETCH[1] if s_ > ln - 1.5 else FLETCH[2]))
        else:
            cols.append(hexf(WOOD[2] if s_ < ln * 0.5 else WOOD[1]))
    cols = np.array(cols)
    shade = 0.75 + 0.25 * scale
    fr.over(np.round(ys[keep]), np.round(xs[keep]), cols[keep] * shade, a)
    # the fletching: two barbs off the tail
    for sgn in (-1, 1):
        b0 = (tail[0] + ux * 1.2, tail[1] + uy * 1.2)
        b1 = (b0[0] - ux * 2.0 * scale + px * sgn * 1.0 * scale, b0[1] - uy * 2.0 * scale + py * sgn * 1.0 * scale)
        line(fr, b0, b1, FLETCH[2] if sgn < 0 else FLETCH[0], FLETCH[2], a * 0.9, a * 0.6)
    return tail


def arrow_state(ar, f):
    t = (f - ar["t0"]) / ar["fly"]
    if t < 0:
        return None
    if t < 1:
        u = t * t                                             # far away it crawls, close up it streaks
        p = (ar["start"][0] + (ar["end"][0] - ar["start"][0]) * u, ar["start"][1] + (ar["end"][1] - ar["start"][1]) * u)
        return "fly", p, u
    return "stuck", ar["end"], f - ar["t0"] - ar["fly"]


def draw(f):
    fr = Frame()
    sig = ease_io((f - SIGNAL0 + 2) / 6.0) * (1 - ease_io((f - RAIN0 - 6) / 10.0))

    # the shadow of the rain sweeping over the field, then fading as the arrows land
    shade = ease_io((f - 2) / 14.0) * (1 - ease_io((f - LAUNCH_LAST) / 18.0))
    if shade > 0.01:
        cx = FIELD[0] + (FIELD[1] - FIELD[0]) * (0.25 + 0.25 * ease_io((f - 2) / 70.0))
        sy, sx = _win(FIELD[0] - 10, FIELD[1] + 6, GROUND_Y - 14, GROUND_Y + 14)
        d = np.hypot((XX[sy, sx] - cx) / ((FIELD[1] - FIELD[0]) * 0.55), (YY[sy, sx] - GROUND_Y) / 12)
        m = d < 1
        ys, xs = np.nonzero(m)
        fr.over(ys + sy.start, xs + sx.start, hexf("#141822"), 0.4 * shade * (1 - d[m] ** 2))

    far = 0
    stuck_lit = 0
    for ar in ARROWS:
        st = arrow_state(ar, f)
        if st is None:
            continue
        kind, p, t = st
        sc = 0.85 + 0.15 * ar["depth"]
        if kind == "fly":
            u = t
            fade = min(1.0, (f - ar["t0"] + 1) / 2.0)
            ux, uy = math.cos(ar["ang"]), math.sin(ar["ang"])
            if u < 0.2:
                far += 1
                tw = 0.5 + 0.5 * math.sin(f * 1.3 + ar["ph"] * 5)
                line(fr, (p[0] - ux * 3, p[1] - uy * 3), p, STEEL[1], STEEL[2], 0.0, fade)
                fr.dot(*p, "#ffffff", fade * (0.6 + 0.4 * tw))
                fr.glow(*p, 3, (0.2 + 0.2 * tw) * fade)
                continue
            asc = sc * (0.45 + 0.55 * u)
            sl = max(min(6 + 34 * u, (p[1] - 9) / uy, (p[0] - 9) / ux), ALEN * asc)
            tl = (p[0] - ux * sl, p[1] - uy * sl)
            line(fr, tl, (p[0] - ux * ALEN * asc, p[1] - uy * ALEN * asc), STEEL[0], "#c8d4ea", 0.0, 0.6 * fade)
            arrow(fr, p, ar["ang"], asc, fade)
            fr.glow(*p, 4, 0.45 * fade)
            fr.glow_line(tl, p, 5, 0.14 * fade)
        else:
            age = t
            wob = 1.6 * math.exp(-age / 4.0) * math.sin(age * 2.4 + ar["ph"]) if age < 14 else 0.0
            dim = 1 - 0.25 * ease_io((f - SETTLE0) / 20.0)
            arrow(fr, p, ar["ang"], sc, dim, sink=ar["sink"], wob=wob)
            if age < 5:
                rr = 2 + age * 1.4
                th = np.linspace(0, 2 * math.pi, 18, endpoint=False)
                fr.over(np.round(p[1] + rr * 0.3 * np.sin(th)), np.round(p[0] + rr * np.cos(th)), hexf("#dfe8f6"),
                        0.6 * (1 - age / 5))
            if age < 3:
                fr.glow(p[0], p[1] - 1, 7, 0.35 * (1 - age / 3))
                stuck_lit += 1
            if ar["spark"] and age < 6:
                for j in range(3):
                    a_ = math.pi + 0.4 + j * 0.9 + ar["dseed"][j]
                    rr = 2 + age * 1.6
                    sx_, sy_ = p[0] + math.cos(a_) * rr, p[1] - 2 + math.sin(a_) * rr * 0.6 + 0.2 * age * age
                    fr.dot(sx_, sy_, SPARK, 1 - age / 6)
                    fr.glow(sx_, sy_, 3, 0.3 * (1 - age / 6))
            if ar["dust"] and age < 26:
                k = (1 - ease_io(age / 26.0))
                r = 1.5 + 3.5 * eout(age / 12.0)
                puff(fr, p[0] - 2 + age * 0.12 + ar["dseed"][0], p[1] - 1 - age * 0.25, r, 0.4 * k)
                if age < 8:
                    for j in range(2):
                        gx = p[0] + ar["dseed"][j + 1] * 2 + (age * 0.8) * (1 if j else -1)
                        gy = p[1] - 1 - 3 * math.sin(min(age / 8.0, 1) * math.pi)
                        fr.dot(gx, gy, DUST[1], 1 - age / 8)

    # the field pool: swells with the number of fresh hits, keeps a faint glint on the stuck heads
    rain = ease_io((f - RAIN0) / 10.0) * (1 - 0.6 * ease_io((f - SETTLE0) / 20.0))
    fr.glow((FIELD[0] + FIELD[1]) / 2, GROUND_Y - 30, 130, 0.22 * rain + min(0.2, 0.02 * stuck_lit), flat=0.45)
    fr.glow((FIELD[0] + FIELD[1]) / 2 - 40, 98, 170, 0.1 * rain, flat=0.55)
    fr.glow(110, 34, 110, 0.18 * min(1.0, far / 25) + 0.06 * rain, flat=0.3)
    return fr


def main():
    OUT.mkdir(exist_ok=True)
    cols, lights, comps, ok = [], [], [], True
    covers, means = [], []
    for f in range(N):
        fr = draw(f)
        col = (np.clip(fr.rgba(), 0, 1) * 255).round().astype(np.uint8)
        Lc = np.clip(fr.L, 0, 1)
        light = pfx.tint(np.repeat(Lc[..., None], 3, -1), LIGHT_RAMP)
        cols.append(col)
        lights.append(light)
        comps.append(pfx.composite(col, light))
        a = col[..., 3] > 0
        if not a.any():
            print(f"frame {f}: empty colour")
            ok = False
            continue
        edge = np.zeros_like(a)
        edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
        if (a & edge).any() or ((Lc > 0.02) & edge).any():
            print(f"frame {f}: touches the cell edge")
            ok = False
        ys, xs = np.nonzero(a)
        box = Lc[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        covers.append((box > 0.03).mean())
        means.append(box[box > 0.03].mean() if (box > 0.03).any() else 0)
    cv, mn = np.median(covers), np.median(means)
    print(f"light cover {cv:.0%}  mean {mn:.3f}  (medium: 50-80%, 0.08-0.12)")
    if not (0.5 <= cv <= 0.8 and 0.08 <= mn <= 0.12):
        print("light outside the medium row")
        ok = False

    ncol = 12

    def grid(frames, path, idx=None, n=ncol, scale=1):
        idx = list(range(len(frames))) if idx is None else idx
        rows = math.ceil(len(idx) / n)
        img = np.zeros((rows * H, n * W, 4), np.uint8)
        for k, i in enumerate(idx):
            r, cc = divmod(k, n)
            img[r * H:(r + 1) * H, cc * W:(cc + 1) * W] = frames[i]
        im = Image.fromarray(img, "RGBA")
        if scale != 1:
            im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
        im.save(path)

    grid(comps, OUT / f"{NAME}.png")
    grid(cols, OUT / f"{NAME}_color.png")
    grid([pfx.composite(np.zeros((H, W, 4), np.uint8), l) for l in lights], OUT / f"{NAME}_light.png")
    pfx.strip(comps, OUT / f"{NAME}_strip_1x.png")
    pick = [4, 10, 18, 26, 36, 46, 56, 66, 76, 86, 100, 119]
    for bg, tag in (("#101018", "dark"), ("#5a6070", "mid")):
        flat = [pfx.composite(cols[i], lights[i], bg) for i in range(N)]
        grid(flat, OUT / f"{NAME}_contact4x_{tag}.png", pick, n=4, scale=4)
    for i in (6, 40, 70, 119):
        Image.fromarray(pfx.composite(cols[i], lights[i], "#101018"), "RGBA").resize(
            (W * 4, H * 4), Image.NEAREST).save(OUT / f"{NAME}_f{i:03d}_x4.png")
    pfx.gif(comps, OUT / f"{NAME}.gif", FPS, scale=2)
    meta = dict(name=NAME, w=W, h=H, frames=N, fps=FPS, cols=ncol, loop=False, pivot=[W / 2, GROUND_Y],
                glow="medium", light_gain=1.0,
                states=dict(signal=[SIGNAL0, RAIN0 - 1], rain=[SIGNAL0, 84], hit=[12, 86],
                            settle=[SETTLE0, N - 1]),
                sheets=dict(composite=f"{NAME}.png", color=f"{NAME}_color.png", light=f"{NAME}_light.png"))
    (OUT / f"{NAME}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
