"""Mockup caster for /beanfx (optional, asked in the brief): a glowing robed silhouette that performs the effect, with
an optional avatar (a translucent copy behind it with a halo). No face; it shows scale and the casting beats.

    import caster as cs
    pose = cs.pose_at(f, [(0, "chest"), (20, "raise"), (40, "point")], [(0, "rest"), (40, "behind")], aim)
    g = cs.draw(over, (H, W), foot, sc, pose, f, lift, flut, hair="loose")      # over(ys, xs, rgb, a) composites
    cs.body_light(L, g, charge)                                                  # glow on the body, hair and hip
    cs.finger_light(L, g, point, jab); over(...) a white dot at g["finger"] if wanted
    gg = cs.draw(over, (H, W), gfoot, sc * 1.3, gpose, f * 0.7, lift * 0.6, flut * 0.7, hair="loose", ghost=k)
    cs.ghost_light(over, L, gg, k, f, point)                                     # inner glow, halo, finger

Local units: feet at (0, 0), y down, the figure faces +x and is about 78 units tall; sc maps units to px (0.44 is
34 px). lift (0..1) raises hair and flaps into the wind, flut (0..1) is how hard cloth and hair flap. Learnt on
drafts/van_kiem_quy_tong_v2 and v3: keep the body core light low on a small figure (it burns white under the
pools), keep every strand at least 1 px wide (mw), and light the avatar from inside its mask with a bright
rim so it reads as luminous rather than a grey copy.
"""
import math

import numpy as np

BODY = ["#4a2208", "#9a5a10", "#d89a28", "#f6d266", "#fff4c8"]   # golden figure, dark to hot

FRONT = dict(rest=((7, -47), (8, -38)), chest=((9, -48), (6, -60)), raise_=((9, -66), (12, -78)),
             pull=((2, -50), (7, -61)))
BACK = dict(rest=((-6, -47), (-7, -38)), out=((-9, -50), (-14, -44)), behind=((-8, -48), (-3, -43)))
SHOULDER = (5.0, -56.0)

_grids = {}


def _hexf(s):
    return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], float) / 255.0


def _grid(shape):
    if shape not in _grids:
        yy, xx = np.mgrid[0:shape[0], 0:shape[1]].astype(float)
        _grids[shape] = (xx, yy)
    return _grids[shape]


def _win(shape, x0, x1, y0, y1):
    H, W = shape
    xa, xb = max(int(x0), 0), min(int(x1) + 2, W)
    ya, yb = max(int(y0), 0), min(int(y1) + 2, H)
    return slice(ya, max(yb, ya)), slice(xa, max(xb, xa))


def ease_io(s):
    s = np.clip(s, 0, 1)
    return s * s * (3 - 2 * s)


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def seg_d(X, Y, a, b):
    ex, ey = b[0] - a[0], b[1] - a[1]
    h = np.clip(((X - a[0]) * ex + (Y - a[1]) * ey) / (ex * ex + ey * ey or 1e-9), 0, 1)
    return np.hypot(X - a[0] - ex * h, Y - a[1] - ey * h)


# ---- light, same falloff as kit/light.py, windowed ----
def glow(L, x, y, r, k, flat=1.0):
    X, Y = _grid(L.shape)
    sy, sx = _win(L.shape, x - r, x + r, y - r * flat, y + r * flat)
    d = np.hypot(X[sy, sx] - x, (Y[sy, sx] - y) / flat) / r
    L[sy, sx] += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)


def glow_line(L, p0, p1, r, k):
    X, Y = _grid(L.shape)
    sy, sx = _win(L.shape, min(p0[0], p1[0]) - r, max(p0[0], p1[0]) + r, min(p0[1], p1[1]) - r,
                  max(p0[1], p1[1]) + r)
    d = seg_d(X[sy, sx], Y[sy, sx], p0, p1) / r
    L[sy, sx] += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)


def glow_ring(L, x, y, R, r, k, flat=1.0):
    X, Y = _grid(L.shape)
    sy, sx = _win(L.shape, x - R - r, x + R + r, y - (R + r) * flat, y + (R + r) * flat)
    d = np.abs(np.hypot(X[sy, sx] - x, (Y[sy, sx] - y) / flat) - R) / r
    L[sy, sx] += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)


# ---- shapes ----
def shade(m, base):
    """Tone map for one part: base, a step up where the top-left neighbour is empty, a step down bottom-right."""
    ul = np.zeros_like(m)
    ul[1:, 1:] = m[:-1, :-1]
    dr = np.zeros_like(m)
    dr[:-1, :-1] = m[1:, 1:]
    t = np.full(m.shape, base)
    t[m & ~ul] = min(base + 1, 4)
    t[m & ~dr & ul] = max(base - 1, 0)
    return t


def tri(X, Y, a, b, c):
    def side(p, q):
        return (X - q[0]) * (p[1] - q[1]) - (p[0] - q[0]) * (Y - q[1])
    d1, d2, d3 = side(a, b), side(b, c), side(c, a)
    return ~(((d1 < 0) | (d2 < 0) | (d3 < 0)) & ((d1 > 0) | (d2 > 0) | (d3 > 0)))


def strand(lx, ly, s0, a0, a1, length, w0, w1, wave, n=12, mw=0.0):
    """A hair lock, ribbon or cloth flap: a chain of capsules from s0, its angle turning from a0 to a1, waving."""
    m = np.zeros(lx.shape, bool)
    pts = [s0]
    x, y = s0
    for k in range(n):
        t = k / (n - 1)
        a = a0 + (a1 - a0) * t + wave(k) * t
        nx, ny = x + math.cos(a) * length / n, y + math.sin(a) * length / n
        r = max(w0 + (w1 - w0) * t, mw)
        m |= seg_d(lx, ly, (x, y), (nx, ny)) <= r
        x, y = nx, ny
        pts.append((x, y))
    return m, pts


def pose_at(f, front_keys, back_keys, aim=None, jab=0.0):
    """Front and back arm (elbow, hand) in local units from (frame, pose name) keys, eased between keys.
    Front poses: rest, chest (two-finger sign), raise (to the sky), pull, point (along unit vector aim, the hand
    pushed out by jab). Back poses: rest, out (balance while flying), behind (hand at the small of the back)."""
    front = dict(FRONT)
    if aim is not None:
        sh, d = SHOULDER, aim
        front["point"] = ((sh[0] + d[0] * 11.5, sh[1] + d[1] * 11.5),
                          (sh[0] + d[0] * (23.5 + jab), sh[1] + d[1] * (23.5 + jab)))

    def at(keys, poses):
        keys = [(k, "raise_" if p == "raise" else p) for k, p in keys]
        if f <= keys[0][0]:
            return poses[keys[0][1]]
        for (f0, a), (f1, b) in zip(keys, keys[1:]):
            if f0 <= f <= f1:
                t = ease_io((f - f0) / max(f1 - f0, 1e-6))
                return lerp(poses[a][0], poses[b][0], t), lerp(poses[a][1], poses[b][1], t)
        return poses[keys[-1][1]]
    return at(front_keys, front), at(back_keys, BACK)


def aim_from(foot, sc, target):
    """Unit vector from the caster's front shoulder to a world point, for pose_at(aim=...)."""
    d = (target[0] - (foot[0] + SHOULDER[0] * sc), target[1] - (foot[1] + SHOULDER[1] * sc))
    n = math.hypot(*d) or 1
    return d[0] / n, d[1] / n


def draw(over, shape, foot, sc, pose, f, lift=0.5, flut=0.5, hair="loose", ghost=0.0, palette=BODY):
    """Draw the figure with its feet at `foot`, scale sc, through over(ys, xs, rgb, a).
    hair: "loose" (a wild mane past the waist, two locks over the face) or "bun" (pinned bun, four nape locks).
    ghost > 0 draws the translucent avatar: faint fill, bright rim, fading out below the waist.
    Returns world key points (head, neck, hip, feet, finger, hair polylines) and, for a ghost, its inner mask."""
    rgbs = np.stack([_hexf(c) for c in palette])
    X, Y = _grid(shape)
    fx, fy = foot
    sy, sx = _win(shape, fx - 110 * sc, fx + 50 * sc, fy - 120 * sc, fy + 10 * sc)
    mw = 0.6 / sc                                   # thinnest part stays about one pixel
    lx = (X[sy, sx] - fx) / sc
    ly = (Y[sy, sx] - fy) / sc
    tone = np.full(lx.shape, -1)
    union = np.zeros(lx.shape, bool)

    def put(m, base):
        nonlocal tone
        if m.any():
            t = shade(m, base)
            tone = np.where(m, t, tone)
            union[m] = True

    hair_pts = []
    if hair == "loose":
        # a wild loose mane from crown to nape, past the waist, streaming back and up in the qi wind
        for j in range(7):
            a0 = math.radians(84 + j * 5)
            a1 = a0 + math.radians(55 + j * 9) * (0.35 + lift)
            m, pts = strand(lx, ly, (-1.5 - j * 0.6, -76 + j * 1.6), a0, a1, 50 + (j * 37) % 23 + 10 * lift,
                            3.2, 0.5, lambda k, j=j: flut * (0.4 * math.sin(k * 0.55 - f * 0.5 + j * 1.7)
                                                             + 0.15 * math.sin(k * 1.7 - f * 0.9 + j)), mw=mw)
            put(m, 1 if j % 2 else 2)
            hair_pts.append(pts)
    else:
        # four locks from the nape that fall down the back, then curl back as the wind lifts them
        for j in range(4):
            a0 = math.radians(92 + j * 7)
            a1 = a0 + math.radians(40 + j * 12) * (0.4 + lift)
            m, pts = strand(lx, ly, (-3.6 - j * 0.4, -70 + j * 1.3), a0, a1, 30 + j * 5 + 6 * lift, 2.4, 0.6,
                            lambda k, j=j: 0.35 * flut * math.sin(k * 0.6 - f * 0.45 + j * 1.3), mw=mw)
            put(m, 1 if j % 2 else 2)
            hair_pts.append(pts)
    # wide robe flaps from the hips and the hem, flapping behind
    for j, (sx0, sy0, ln, w0) in enumerate(((-5, -38, 30, 5.0), (-7, -22, 40, 6.0), (-9, -6, 34, 6.0))):
        a0 = math.radians(150 - j * 8)
        a1 = a0 + math.radians(25 + 15 * j) * (0.3 + lift)
        m, _ = strand(lx, ly, (sx0, sy0), a0, a1, ln * (0.8 + 0.4 * flut), w0, 1.2,
                      lambda k, j=j: 0.7 * flut * math.sin(k * 0.8 - f * 0.6 + j * 2.1), mw=mw)
        put(m, 2 if j != 1 else 3)

    (fe, fh), (be, bh) = pose

    def arm(sh, e, h, base):
        """Thin arm with a wide sleeve that drapes below the forearm and trails back."""
        put((seg_d(lx, ly, sh, e) <= max(1.9, mw)) | (seg_d(lx, ly, e, h) <= max(1.5, mw)), base)
        a, b = lerp(e, h, 0.1), lerp(e, h, 0.85)
        wv = math.sin(f * 0.7 + sh[0]) * flut
        tail = (lerp(e, h, 0.5)[0] - 9 - 10 * flut, lerp(e, h, 0.5)[1] + 13 - 6 * lift + 3 * wv)
        put(tri(lx, ly, a, b, tail) | (seg_d(lx, ly, a, b) <= 2.6) | (seg_d(lx, ly, b, tail) <= mw), base - 1)

    arm((-4.0, -55.0), be, bh, 2)

    # robe: rows from sloped shoulders to a fluttering hem that trails back when flying
    s = np.clip((ly + 60) / 60, 0, 1)
    hw = np.interp(s, [0, 0.05, 0.14, 0.36, 1], [3.5, 7.5, 8.5, 6.5, 16 + 5 * flut])
    cx = -(flut * 12 + lift * 4) * s ** 2 + 1.2 * np.sin(f * 0.5 + s * 4) * s * flut * 2
    hem = 2.4 * np.sin(lx * 0.5 + f * 0.8) * flut
    robe = (ly >= -60) & (ly <= hem) & (np.abs(lx - cx) <= hw)
    put(seg_d(lx, ly, (0.8, -64), (0.5, -58)) <= 2.2, 3)          # neck
    put(robe, 2)
    tone[robe & (ly >= -41) & (ly <= -39)] = 1                       # sash
    tone[robe & (seg_d(lx, ly, (-2, -58), (3.5, -43)) <= 0.5)] = 3   # lapel
    head = np.hypot((lx - 1.5) / 5.4, (ly + 69) / 6.6) <= 1
    put(head, 2)
    tone[head & (lx > 2.5) & (ly > -68)] = 3
    if hair == "loose":
        for j in range(2):                                           # two locks over the face
            m, _ = strand(lx, ly, (2.5 + j * 2.2, -75), math.radians(96 - j * 10), math.radians(100 + 30 * lift),
                          14 + 4 * j, 1.4, 0.4, lambda k, j=j: 0.3 * flut * math.sin(k - f * 0.6 + j), n=6, mw=mw)
            put(m, 2)
    else:
        put(np.hypot(lx + 1.5, ly + 76.5) <= 3.2, 2)                # bun
    # front arm, wide sleeve, two-finger sword sign
    arm((5.0, -55.0), fe, fh, 3)
    put(np.hypot(lx - fh[0], ly - fh[1]) <= 1.7, 3)
    dl = math.hypot(fh[0] - fe[0], fh[1] - fe[1]) or 1
    tipl = (fh[0] + (fh[0] - fe[0]) / dl * 4, fh[1] + (fh[1] - fe[1]) / dl * 4)
    finger = seg_d(lx, ly, fh, tipl) <= max(0.8, mw * 0.8)
    tone[finger] = 4
    union |= finger
    if hair == "bun":
        pin = seg_d(lx, ly, (-7.5, -78.5), (6, -75.2)) <= max(0.6, mw)   # hairpin through the bun
        tone[pin] = 4
        union |= pin

    ys, xs = np.nonzero(union & (tone >= 0))
    t = tone[ys, xs]
    mask = None
    if ghost > 0:
        er = union.copy()
        er[1:-1, 1:-1] = union[1:-1, 1:-1] & union[:-2, 1:-1] & union[2:, 1:-1] & union[1:-1, :-2] & union[1:-1, 2:]
        rim = (union & ~er)[ys, xs]
        fade = ease_io((-ly[ys, xs] - 12) / 26.0)
        a = np.where(rim, 0.75, 0.14) * fade * ghost
        over(ys + sy.start, xs + sx.start, rgbs[np.where(rim, 4, np.minimum(t + 1, 4))], a)
        inner = np.zeros(lx.shape)
        inner[ys, xs] = fade
        mask = (sy, sx, inner)
    else:
        over(ys + sy.start, xs + sx.start, rgbs[t], 1.0)

    def w(p):
        return (fx + p[0] * sc, fy + p[1] * sc)
    return dict(mask=mask, sc=sc, head=w((1.5, -69)), neck=w((0.5, -60)), hip=w((0, -40)), feet=w((0, -4)),
                finger=w(tipl), hair=[[w(p) for p in pts[::4]] for pts in hair_pts])


# ---- light, tuned at sc 0.44 (34 px) for glow max; radii follow the figure's size ----
def body_light(L, g, charge=1.0):
    """Core and pool along the body, the head, every hair lock, and a wide pool round the hip."""
    u = g["sc"] / 0.44
    glow_line(L, g["feet"], g["head"], 8 * u, 0.12)
    glow_line(L, g["feet"], g["head"], 26 * u, 0.08)
    glow(L, *g["head"], 6 * u, 0.12)
    for pts in g["hair"]:
        for a_, b_ in zip(pts, pts[1:]):
            glow_line(L, a_, b_, 4 * u, 0.08)
    glow(L, *g["hip"], 100 * u, 0.12 * (0.4 + 0.6 * charge), flat=0.85)


def finger_light(L, g, point, jab=0.0):
    """The sword-sign fingertip: a tight hot core and a pool, both pulsing with jab while it points."""
    u = g["sc"] / 0.44
    glow(L, *g["finger"], 7 * u, (0.4 + 0.3 * jab) * point)
    glow(L, *g["finger"], 20 * u, (0.15 + 0.15 * jab) * point)


def ellipse_line(over, cx, cy, rx, ry, col, a, phase=0.0, dash=None):
    n = max(int(2 * math.pi * max(rx, 1) * 1.6), 12)
    th = np.linspace(0, 2 * math.pi, n, endpoint=False)
    if dash:
        th = th[np.sin(th * dash + phase) > -0.2]
    pts = np.unique(np.stack([np.round(cy + ry * np.sin(th)), np.round(cx + rx * np.cos(th))], 1).astype(int), axis=0)
    over(pts[:, 0], pts[:, 1], _hexf(col), a)


def ghost_light(over, L, g, ghost, f, point=0.0):
    """The avatar: light inside its mask, a halo ring behind the head, a faint pool and spine, the finger."""
    u = g["sc"] / 0.56
    msy, msx, inner = g["mask"]
    L[msy, msx] += inner * 0.1 * ghost
    hx, hy = g["head"][0] - 2 * u, g["head"][1] - 1 * u
    R = (12 + math.sin(f * 0.2)) * u
    ellipse_line(over, hx, hy, R, R, BODY[4], 0.5 * ghost)
    glow_ring(L, hx, hy, R, 4 * u, 0.3 * ghost)
    glow(L, hx, hy, 50 * u, 0.07 * ghost)
    glow_line(L, g["hip"], g["head"], 30 * u, 0.04 * ghost)
    glow(L, *g["finger"], 12 * u, 0.25 * ghost * point)
