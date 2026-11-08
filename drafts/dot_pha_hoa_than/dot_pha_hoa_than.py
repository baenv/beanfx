"""dot_pha_hoa_than: a cultivator breaks through to the Hoa Than (Deity Transformation) stage. General mode.

256x256, 24 fps, 120 frames (5 s), one-shot, soft style, glow strong, pivot at the caster's feet on the ground.

| state    | frames  | s   | what moves                                                   | carrier              |
|----------|---------|-----|--------------------------------------------------------------|----------------------|
| gather   | 0-35    | 1.5 | qi motes spiral in, ground array lights, the caster lifts    | motes, array, caster |
| crack    | 36-45   | 0.4 | motes compress, the caster dips, two tribulation strikes     | lightning            |
| burst    | 46-83   | 1.6 | white peak 46-47, pillar of light, deity avatar forms, hover | pillar, avatar       |
| dissolve | 84-119  | 1.5 | ring shockwave, embers rise, pillar and avatar fade, landing | rings, embers        |
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "kit"))
import caster as cs  # noqa: E402
import pfx  # noqa: E402

NAME = "dot_pha_hoa_than"
W = H = 256
FPS = 24
GATHER, GATHER_LEN = 0, 36
CRACK, CRACK_LEN = GATHER + GATHER_LEN, 10
BURST, BURST_LEN = CRACK + CRACK_LEN, 38
DISSOLVE, DISSOLVE_LEN = BURST + BURST_LEN, 36
FRAMES = DISSOLVE + DISSOLVE_LEN
STATES = {"gather": [GATHER, CRACK - 1], "crack": [CRACK, BURST - 1], "burst": [BURST, DISSOLVE - 1],
          "dissolve": [DISSOLVE, FRAMES - 1]}

GROUND = 204.0
CX = 128.0
SC = 0.44            # caster ~34 px
AV_SC = 1.2          # deity avatar ~94 px

GHOST = ["#6a3010", "#c07020", "#ffb040", "#ffe8a0", "#ffffff"]
GOLD = ["#5a2a0a", "#b0601a", "#e8a830", "#ffe080", "#fff8e0"]
AZURE = ["#10204a", "#2a5ab0", "#4aa0e8", "#a8e4ff", "#ffffff"]
VIOLET = ["#2a1060", "#6a3ad0", "#b090ff", "#ece0ff", "#ffffff"]
R_GOLD = ["#3a1a08", "#c07818", "#ffd060", "#ffffff"]
R_AZURE = ["#0a1a40", "#2a70d0", "#90d8ff", "#ffffff"]
R_VIOLET = ["#1a0a40", "#6a40e0", "#c8b0ff", "#ffffff"]


def hx(s):
    return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], float) / 255.0


def ease_out(t):
    t = np.clip(t, 0, 1)
    return 1 - (1 - t) ** 3


def ease_in(t):
    t = np.clip(t, 0, 1)
    return t * t


def smooth(t):
    return cs.ease_io(t)


def hsh(i, salt=0):
    return (math.sin(i * 127.1 + salt * 311.7) * 43758.5453) % 1.0


class Frame:
    def __init__(self):
        self.P = np.zeros((H, W, 3))
        self.A = np.zeros((H, W))
        self.Lg = np.zeros((H, W))
        self.Lq = np.zeros((H, W))
        self.Lt = np.zeros((H, W))

    def over(self, ys, xs, rgb, a):
        ys = np.asarray(ys).astype(int)
        xs = np.asarray(xs).astype(int)
        ok = (ys >= 0) & (ys < H) & (xs >= 0) & (xs < W)
        rgb = np.broadcast_to(np.asarray(rgb, float), (len(ys), 3))[ok] if np.ndim(rgb) > 1 else np.asarray(rgb, float)
        a = np.broadcast_to(np.asarray(a, float), ys.shape)[ok]
        ys, xs = ys[ok], xs[ok]
        if len(ys) == 0:
            return
        self.P[ys, xs] = self.P[ys, xs] * (1 - a[:, None]) + rgb * a[:, None]
        self.A[ys, xs] = self.A[ys, xs] * (1 - a) + a

    def pts(self, pts, rgb, a):
        if len(pts):
            p = np.unique(np.round(np.asarray(pts)).astype(int), axis=0)
            self.over(p[:, 1], p[:, 0], rgb, a)

    def color(self):
        a = np.clip(self.A, 0, 1)
        rgb = self.P / np.maximum(a, 1e-6)[..., None]
        return (np.dstack([np.clip(rgb, 0, 1), a]) * 255).round().astype(np.uint8)

    def light(self):
        out = np.zeros((H, W, 3))
        for L, ramp in ((self.Lg, R_GOLD), (self.Lq, R_AZURE), (self.Lt, R_VIOLET)):
            c = np.clip(L, 0, 1)
            out += pfx.tint(np.repeat(c[..., None], 3, -1), ramp)
        return np.clip(out, 0, 1)


def seg_pts(a, b, step=0.5):
    n = max(int(math.hypot(b[0] - a[0], b[1] - a[1]) / step), 1)
    t = np.linspace(0, 1, n + 1)
    return np.stack([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t], 1)


YY, XX = np.mgrid[0:H, 0:W].astype(float)


# ---- caster path ----
def foot_at(f):
    if f < CRACK:
        y = GROUND - 16 * smooth((f - 8) / (GATHER_LEN - 8))
    elif f < BURST:
        y = GROUND - 16 + 3 * math.sin(math.pi * (f - CRACK) / CRACK_LEN)
    elif f < DISSOLVE + 8:
        y = GROUND - 16 - 18 * ease_out((f - BURST) / 10) + 2 * math.sin((f - BURST) * 0.35)
    else:
        y = GROUND - 34 + 34 * smooth((f - DISSOLVE - 8) / (DISSOLVE_LEN - 14))
    return (CX, y)


def speed_at(f):
    return abs(foot_at(f + 1)[1] - foot_at(f - 1)[1]) / 2


# ---- parts ----
def ground_array(fr, f):
    """A two-ring formation on the ground that lights in the gather and fades after the burst."""
    k = smooth(f / 20) * (1 - smooth((f - DISSOLVE) / 24))
    if k <= 0.01:
        return
    rot = f * 0.06
    for rx, dash, tone in ((46, 9, 3), (32, 0, 2)):
        ry = rx * 0.28
        cs.ellipse_line(fr.over, CX, GROUND, rx, ry, AZURE[tone], 0.75 * k, phase=rot * (1 if dash else -1),
                        dash=dash or None)
    for j in range(8):                                   # rune ticks between the rings
        a = rot + j * math.tau / 8
        p0 = (CX + 34 * math.cos(a), GROUND + 34 * 0.28 * math.sin(a))
        p1 = (CX + 44 * math.cos(a), GROUND + 44 * 0.28 * math.sin(a))
        fr.pts(seg_pts(p0, p1), hx(AZURE[4]), 0.8 * k)
        fr.Lq += 0
        cs.glow(fr.Lq, *p1, 4, 0.25 * k)
    cs.glow_ring(fr.Lq, CX, GROUND, 46, 5, 0.3 * k, flat=0.28)
    cs.glow(fr.Lq, CX, GROUND, 60, 0.12 * k, flat=0.35)


N_MOTES = 60
MOTES = [dict(r0=70 + 45 * hsh(i, 1), a0=math.tau * hsh(i, 2), d=int(22 * hsh(i, 3)), dur=20 + int(12 * hsh(i, 4)),
              spin=2.2 + 1.6 * hsh(i, 5), flat=0.3 + 0.2 * hsh(i, 6)) for i in range(N_MOTES)]


def mote_pos(m, t, core):
    r = m["r0"] * (1 - ease_in(t) * 0.92)
    a = m["a0"] + m["spin"] * t
    return core[0] + r * math.cos(a), core[1] + r * (math.sin(a) * m["flat"] - 0.45), a


def motes(fr, f, core, front):
    """Qi motes that spiral in toward the dantian; each streaks 1 px with a hot head, lit by a core and pool."""
    for i, m in enumerate(MOTES):
        t = (f - m["d"]) / m["dur"]
        if t < 0 or t > 1.05:
            continue
        x, y, a = mote_pos(m, min(t, 1), core)
        if (math.sin(a) > 0) != front:
            continue
        trail = [mote_pos(m, max(t - s * 0.035, 0), core)[:2] for s in range(1, 5)]
        fade = 1 - smooth((t - 0.9) / 0.15)
        for s, p in enumerate(trail):
            fr.pts([p], hx(AZURE[3 - min(s, 2)]), (0.75 - 0.16 * s) * fade)
        fr.pts([(x, y)], hx(AZURE[4]), fade)
        cs.glow(fr.Lq, x, y, 3, 0.4 * fade)
        cs.glow(fr.Lq, x, y, 9, 0.16 * fade)


def bolt_path(seed, top, target):
    pts = [top]
    n = 12
    for k in range(1, n):
        t = k / n
        jit = (hsh(k, seed) - 0.5) * 16 * (1 - t * 0.7)
        pts.append((top[0] + (target[0] - top[0]) * t + jit, top[1] + (target[1] - top[1]) * t))
    pts.append(target)
    branches = []
    for b in range(3):
        k = 2 + int(hsh(b, seed + 7) * (n - 5))
        s = 1 if hsh(b, seed + 9) > 0.5 else -1
        p = pts[k]
        br = [p]
        for j in range(4):
            p = (p[0] + s * (4 + 3 * hsh(j, seed + b)), p[1] + 3 + 3 * hsh(j + 5, seed + b))
            br.append(p)
        branches.append(br)
    return pts, branches


def lightning(fr, f, head):
    """Tribulation strikes: two short ones in the crack, the last lands on the head right before the peak."""
    for f0, seed, k, dx in ((CRACK + 1, 3, 0.7, -14), (CRACK + 5, 8, 0.8, 10), (BURST - 1, 13, 1.0, 0)):
        age = f - f0
        if age < 0 or age > 2:
            continue
        a = (1.0, 0.6, 0.3)[age]
        target = (head[0] + dx, head[1] - 4) if dx else head
        main, branches = bolt_path(seed, (CX + dx * 0.4 + (hsh(seed) - 0.5) * 20, 20), target)
        for line, w in [(main, 1.0)] + [(b, 0.6) for b in branches]:
            core = np.concatenate([seg_pts(p, q) for p, q in zip(line, line[1:])])
            edge = np.concatenate([core + (1, 0), core + (-1, 0)])
            fr.pts(edge, hx(VIOLET[2]), 0.7 * a * k * w)
            fr.pts(core, hx(VIOLET[4] if w == 1 else VIOLET[3]), a * k)
            for p, q in zip(line, line[1:]):
                cs.glow_line(fr.Lt, p, q, 5, 0.45 * a * k * w)
                cs.glow_line(fr.Lt, p, q, 15, 0.2 * a * k * w)
        cs.glow(fr.Lt, *target, 16, 0.6 * a * k)
        cs.glow(fr.Lt, CX, 120, 110, 0.15 * a * k)   # the sky flash


def pillar_k(f):
    if f < BURST:
        return 0.0
    return ease_out((f - BURST) / 4) * (1 - smooth((f - DISSOLVE + 6) / 24))


def pillar(fr, f, foot):
    """A translucent column of gold light from the ground up the sky: white core, 1 px rims, rising dashes."""
    k = pillar_k(f)
    if k <= 0.01:
        return
    top = 10
    hw0 = (15 - 8 * smooth((f - BURST - 2) / 16)) * (0.4 + 0.6 * k)
    wob = 0.8 * np.sin(YY * 0.09 + f * 0.6)
    base = foot[1] - 30 * SC * 2.6                   # the crown: the column rises out of the head
    hw = hw0 * (0.8 + 0.2 * smooth((YY - top) / 60)) * (0.3 + 0.7 * smooth((base - YY) / 22))
    dx = np.abs(XX - CX - wob)
    inside = (dx <= hw) & (YY >= top) & (YY <= base)
    vfade = smooth((YY - top) / 70) * k * (0.4 + 0.6 * smooth((base - YY) / 10))
    ys, xs = np.nonzero(inside)
    d = dx[ys, xs] / hw[ys, xs]
    v = vfade[ys, xs]
    rim = dx[ys, xs] > hw[ys, xs] - 1
    core = dx[ys, xs] < 1.2
    tone = np.where(core, 4, np.where(d < 0.5, 3, 2))
    tone = np.where(rim, 3, tone)
    rgb = np.stack([hx(c) for c in GOLD])[tone]
    a = np.where(rim, 0.7, np.where(core, 0.9, 0.2 - 0.1 * d)) * v
    fr.over(ys, xs, rgb, a)
    for j in range(14):                                   # rising streaks inside the column
        x = CX + (hsh(j, 21) - 0.5) * 1.6 * hw0
        y = base - ((f - BURST) * (7 + 5 * hsh(j, 22)) + 200 * hsh(j, 23)) % (base - top)
        ln = 5 + 7 * hsh(j, 24)
        seg = seg_pts((x, y), (x, y + ln))
        fv = float(smooth((y - top) / 40)) * k
        fr.pts(seg, hx(GOLD[4]), 0.9 * fv)
    cs.glow_line(fr.Lg, (CX, base), (CX, 70), hw0 * 0.9, 0.5 * k)
    cs.glow_line(fr.Lg, (CX, base + 10), (CX, 64), hw0 * 3.0, 0.24 * k)
    cs.glow(fr.Lg, CX, GROUND, 40, 0.3 * k, flat=0.4)
    cs.glow_line(fr.Lg, (CX, base + 20), (CX, 80), 70, 0.12 * k)       # wide low pool along the column


def flash(fr, f, core):
    """The peak: a white-hot disc and tapered rays for two frames, then a quick fade."""
    age = f - BURST
    if age < 0 or age > 5:
        return
    a = (1.0, 0.9, 0.55, 0.3, 0.15, 0.05)[age]
    r = 9 + age * 3
    disc = np.hypot(XX - core[0], YY - core[1]) <= r
    ys, xs = np.nonzero(disc)
    fr.over(ys, xs, hx(GOLD[4]), a * 0.9)
    for j in range(14):
        ang = j * math.tau / 14 + hsh(j, 31) * 0.3
        ln = (22 + 30 * hsh(j, 32)) * (0.8 + 0.08 * age)
        p0 = (core[0] + r * math.cos(ang), core[1] + r * math.sin(ang))
        p1 = (core[0] + (r + ln) * math.cos(ang), core[1] + (r + ln) * math.sin(ang))
        seg = seg_pts(p0, p1)
        tt = np.linspace(1, 0.2, len(seg))
        fr.over(np.round(seg[:, 1]), np.round(seg[:, 0]), hx(GOLD[4]), a * tt)
        cs.glow_line(fr.Lg, p0, p1, 4, 0.3 * a)
    cs.glow(fr.Lg, *core, 22, 0.7 * a)


def shockwaves(fr, f, core):
    """A sphere ring round the body and a flat ground ring, thrown at the start of the dissolve."""
    for f0, R1, ground, k in ((DISSOLVE - 4, 82, False, 1.0), (DISSOLVE, 108, True, 0.9), (DISSOLVE + 8, 62, False, 0.6)):
        t = (f - f0) / 26
        if t < 0 or t > 1:
            continue
        R = 8 + (R1 - 8) * ease_out(t)
        a = (1 - smooth(t)) * k
        cy = GROUND if ground else foot_at(f0)[1] - 40 * SC
        flat = 0.28 if ground else 1.0
        cs.ellipse_line(fr.over, CX, cy, R, R * flat, GOLD[4], 0.9 * a)
        cs.ellipse_line(fr.over, CX, cy, R - 1.2, (R - 1.2) * flat, GOLD[3], 0.55 * a)
        cs.ellipse_line(fr.over, CX, cy, R - 3, (R - 3) * flat, GOLD[2], 0.25 * a)
        cs.glow_ring(fr.Lg, CX, cy, R, 4, 0.45 * a, flat=flat)
        cs.glow_ring(fr.Lg, CX, cy, R - 4, 12, 0.18 * a, flat=flat)
        cs.glow(fr.Lg, CX, cy, R + 6, 0.1 * a, flat=flat)           # the air inside the wave


N_EMB = 46
EMBERS = [dict(b=BURST + int(50 * hsh(i, 41)), x=CX + (hsh(i, 42) - 0.5) * 50, y=GROUND - 60 * hsh(i, 43),
               vy=1.0 + 1.8 * hsh(i, 44), life=18 + int(18 * hsh(i, 45)), ph=math.tau * hsh(i, 46),
               big=hsh(i, 47) > 0.7) for i in range(N_EMB)]


def embers(fr, f):
    """Gold motes thrown up by the burst; they drift, cool from white to dark orange, and wink out."""
    for e in EMBERS:
        t = (f - e["b"]) / e["life"]
        if t < 0 or t > 1:
            continue
        age = f - e["b"]
        x = e["x"] + 4 * math.sin(age * 0.25 + e["ph"]) + (e["x"] - CX) * 0.04 * age
        y = e["y"] - e["vy"] * age
        tone = 4 - min(int(t * 4), 3)
        a = 1 - smooth((t - 0.7) / 0.3)
        p = [(x, y)] + ([(x + 1, y), (x, y + 1)] if e["big"] and t < 0.5 else [])
        fr.pts(p, hx(GOLD[tone]), a)
        cs.glow(fr.Lg, x, y, 3, 0.35 * a * (1 - t * 0.5))
        cs.glow(fr.Lg, x, y, 8, 0.12 * a)


def avatar_k(f):
    if f < BURST:
        return 0.0
    return smooth((f - BURST - 2) / 18) * (1 - smooth((f - DISSOLVE - 2) / 26))


def caster_pose(f, aim):
    return cs.pose_at(f, [(0, "rest"), (10, "chest"), (DISSOLVE + 14, "chest"), (FRAMES - 6, "rest")],
                      [(0, "rest"), (FRAMES - 1, "rest")], aim)


def draw_frame(f):
    fr = Frame()
    foot = foot_at(f)
    sp = speed_at(f)
    wind = pillar_k(f)
    lift = min(0.75, 0.15 + 0.2 * smooth(f / GATHER_LEN) + 0.3 * wind + 0.15 * sp)
    flut = min(0.7, 0.2 + 0.2 * smooth(f / GATHER_LEN) + 0.25 * wind + 0.1 * sp)
    core = (CX, foot[1] - 40 * SC)        # dantian, where the qi gathers
    pose = caster_pose(f, None)

    # scene pool: rises in the gather, swells hard on the peak, cools in the dissolve
    gk = 0.26 * smooth(f / GATHER_LEN) * (f < BURST + 4)
    pk = 0.0
    if f >= BURST:
        pk = 0.45 * math.exp(-(f - BURST) / 6) + 0.3 * (1 - smooth((f - DISSOLVE - 10) / 26))
    cs.glow(fr.Lq, core[0], core[1] - 30, 125, gk + 0.08 * (CRACK <= f < BURST), flat=0.6)
    cs.glow(fr.Lg, CX, core[1] - 20, 115, pk, flat=0.62)

    ground_array(fr, f)
    pillar(fr, f, foot)
    k = avatar_k(f)
    if k > 0.01:                           # the deity form, behind everything
        gfoot = (CX - 4, foot[1] + 14)
        gpose = cs.pose_at(f, [(0, "raise")], [(0, "out")])
        gg = cs.draw(fr.over, (H, W), gfoot, AV_SC, gpose, f * 0.7, lift * 0.6, flut * 0.7, hair="loose", ghost=1.3 * k,
                     palette=GHOST)
        cs.ghost_light(fr.over, fr.Lg, gg, k, f, 1.0)
        msy, msx, inner = gg["mask"]
        fr.Lg[msy, msx] += inner * 0.12 * k            # lit from inside, so it reads gold and not grey
    if f < BURST:
        motes(fr, f, core, front=False)
    g = cs.draw(fr.over, (H, W), foot, SC, pose, f, lift, flut, hair="loose")
    charge = smooth(f / GATHER_LEN) * 0.6 + 0.4 * wind
    cs.body_light(fr.Lg, g, charge)
    if f < BURST:
        motes(fr, f, core, front=True)
    lightning(fr, f, g["head"])
    flash(fr, f, core)
    shockwaves(fr, f, core)
    embers(fr, f)
    return fr


def sheet(frames, cols):
    rows = math.ceil(len(frames) / cols)
    out = np.zeros((rows * H, cols * W, frames[0].shape[2]), frames[0].dtype)
    for i, im in enumerate(frames):
        r, c = divmod(i, cols)
        out[r * H:(r + 1) * H, c * W:(c + 1) * W] = im
    return out


def main():
    out = Path(__file__).resolve().parent / "out"
    out.mkdir(exist_ok=True)
    finals, colors, lights, covers, means, bad = [], [], [], [], [], []
    for f in range(FRAMES):
        fr = draw_frame(f)
        col, L = fr.color(), fr.light()
        Ls = np.clip(fr.Lg + fr.Lq + fr.Lt, 0, None)
        if col[..., 3].max() == 0:
            bad.append(f"frame {f}: empty colour")
        else:
            edge = np.zeros((H, W), bool)
            edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
            if (col[..., 3][edge] > 0).any() or (Ls[edge] > 0.02).any():
                side = [n for n, sl in (("top", np.s_[0, :]), ("bottom", np.s_[-1, :]), ("left", np.s_[:, 0]),
                                         ("right", np.s_[:, -1])) if (col[..., 3][sl] > 0).any() or (Ls[sl] > 0.02).any()]
                bad.append(f"frame {f}: touches the cell edge {side}")
            ys, xs = np.nonzero(col[..., 3])
            box = np.clip(Ls[ys.min():ys.max() + 1, xs.min():xs.max() + 1], 0, 1)
            covers.append((box > 0.03).mean())
            means.append(box[box > 0.03].mean() if (box > 0.03).any() else 0)
        colors.append(col)
        lights.append(L)
        finals.append(pfx.composite(col, L))
    cols = 12
    Image.fromarray(sheet(finals, cols), "RGBA").save(out / f"{NAME}.png")
    Image.fromarray(sheet(colors, cols), "RGBA").save(out / f"{NAME}_color.png")
    lsheet = (sheet([l for l in lights], cols) * 255).round().astype(np.uint8)
    Image.fromarray(lsheet, "RGB").save(out / f"{NAME}_light.png")
    pfx.strip(finals, out / f"{NAME}_1x.png")
    keys = list(range(0, FRAMES, 8)) + [BURST, BURST + 1]
    keys = sorted(set(keys))
    for bg, tag in (("#101018", "dark"), ("#5a6a7a", "mid")):
        ims = []
        for i in keys:
            im = pfx.composite(colors[i], lights[i], bg)
            ims.append(np.asarray(Image.fromarray(im).resize((W * 4, H * 4), Image.NEAREST)))
        pfx.strip(ims, out / f"{NAME}_4x_{tag}.png")
    pfx.gif(finals, out / f"{NAME}.gif", FPS, scale=4)
    meta = dict(name=NAME, w=W, h=H, frames=FRAMES, cols=cols, rows=math.ceil(FRAMES / cols), fps=FPS,
                pivot=[int(CX), int(GROUND)], loop=False, glow="strong", light_gain=1.0, states=STATES,
                sheets=dict(final=f"{NAME}.png", color=f"{NAME}_color.png", light=f"{NAME}_light.png"))
    (out / f"{NAME}.json").write_text(json.dumps(meta, indent=2))
    print(f"frames {FRAMES} at {FPS} fps, glow strong; cover median {np.median(covers):.2f} "
          f"(target 0.75-0.95), mean median {np.median(means):.3f} (target 0.12-0.18)")
    for s, (a, b) in STATES.items():
        print(f"  {s:9s} cover {np.median(covers[a:b + 1]):.2f} mean {np.median(means[a:b + 1]):.3f}")
    if bad:
        print("\n".join(bad[:20]))
        sys.exit(1)
    print("check ok")


if __name__ == "__main__":
    main()
