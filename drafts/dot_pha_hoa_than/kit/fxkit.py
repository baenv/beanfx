"""Drawing kit for blows, flames, bolts and smoke (principles learnt from reference effect packs; no shape of them is
copied). Every helper works on world px grids X, Y (fxlib.wgrid) and paints shade indices into a shade map m of
the cell.

  layered heat   a fire or energy core read as bands: white, pale, body, deep, dark edge (heat_bands)
  lumpy          a round shape with a lobed, moving rim, never one smooth teardrop (lumpy)
  trail puffs    puffs behind a head that shrink, cool and break apart, looping seamlessly by a phase (trail_puffs)
  streaks        radial tapered streaks of mixed length round a blow (streaks)
  puffs          clumped round smoke or spirit puffs in 3 tones, lit top left, edges that break into dots (puff)
  facets         a faceted rock or crystal: lit faces, a shadow face, a hard highlight on the lit rim (facets)
  twinkle        a 4-point star (twinkle)
  ground impact  dust that slides out along the ground, debris that arcs, bounces and rests, cracks for heavy hits
                 (ground_impact, sized by the hit's weight)
"""
import math

import numpy as np

from fxlib import outline, stroke

TAU = math.tau
BAYER = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) + 0.5) / 16.0
LIGHT = (-math.sqrt(0.5), -math.sqrt(0.5))  # the one light, from the top left


def hsh(i, salt=0):
    return (math.sin(i * 12.9898 + salt * 78.233) * 43758.5453) % 1.0


def rot(x, y, a):
    """u along angle a, v across it (left of travel < 0)."""
    c, s = math.cos(a), math.sin(a)
    return x * c + y * s, -x * s + y * c


def bayer(m):
    h, w = m.shape
    return np.tile(BAYER, (h // 4 + 1, w // 4 + 1))[:h, :w]


def fade(m, amount):
    """Ordered-dither dissolve of shade map m: 0 keeps all, 1 clears all."""
    if amount <= 0:
        return m
    out = m.copy()
    out[bayer(m) < amount] = -1
    return out


def blit(dst, src):
    dst[src >= 0] = src[src >= 0]


def rim(m, s):
    """m with a 1 px rim of shade s round its pixels."""
    return outline(m, s)


def lumpy(x, y, cx, cy, r, amp=0.16, seed=0.0, ph=0.0, lobes=5):
    """Normalised distance to a lobed round rim (< 1 inside); the lobes turn with ph."""
    dx, dy = x - cx, y - cy
    a = np.arctan2(dy, dx)
    k = 1 + amp * (0.6 * np.sin(lobes * a + seed + ph) + 0.4 * np.sin((lobes + 3) * a - 1.7 * seed - 1.3 * ph))
    return np.hypot(dx, dy) / np.maximum(r * k, 0.01)


def heat_bands(m, d, shades, cuts):
    """Paints d < 1 into m as bands: shades[i] where d < cuts[i] (cuts rising, the last 1.0), the hottest first."""
    inside = d < 1.0
    for s, c in sorted(zip(shades, cuts), key=lambda p: -p[1]):
        m[inside & (d < c)] = s
    return inside


def lit_offset(r, k=0.35):
    """The offset of a highlight centre toward the light, k of radius r."""
    return LIGHT[0] * r * k, LIGHT[1] * r * k


def ball(m, x, y, cx, cy, r, shades, amp=0.0, ph=0.0, seed=0.0):
    """A lit sphere (or lumpy one with amp): shades (deep, body, light, core) from the far side to the highlight."""
    ox, oy = lit_offset(r)
    d = lumpy(x, y, cx, cy, r, amp, seed, ph) if amp else np.hypot(x - cx, y - cy) / r
    on = d < 1.0
    h = np.hypot(x - cx - ox, y - cy - oy) / r
    m[on] = shades[0]
    m[on & (h < 1.05)] = shades[1]
    m[on & (h < 0.62)] = shades[2]
    m[on & (h < 0.28)] = shades[3]
    return on


def trail_puffs(m, x, y, u, v, head_u, r0, phase, n=4, gap=1.05, shrink=0.78, tones=None, wob=0.6, amp=0.2, seed=0):
    """Puffs behind a head at head_u along u: puff i sits at s = i + phase (phase 0..1 loops seamlessly), r0 * shrink^s
    across, tones[min(int(s), len - 1)] its (core, rim) shades so it cools, broken into dots as it ages."""
    tones = tones or [(3, 2), (2, 1), (1, 0), (0, 0)]
    for i in range(n + 1):
        s = i + phase
        if s <= 0.15 or s >= n:
            continue
        r = r0 * shrink ** s
        cu = head_u - r0 * gap * s - 0.4 * s * s
        cv = wob * math.sin(1.9 * s + seed) * min(1.0, s)
        d = lumpy(u, v, cu, cv, r, amp, seed + i, phase * TAU)
        core, edge = tones[min(int(s), len(tones) - 1)]
        on = d < 1.0
        piece = np.full(m.shape, -1, np.int8)
        piece[on] = edge
        piece[on & (d < 0.6)] = core
        brk = max(0.0, (s - 1.2) / (n - 1.2))
        piece[on & (d > 1 - 0.7 * brk) & (bayer(m) < 0.5 + 0.5 * brk)] = -1
        piece[on & (bayer(m) < 0.55 * brk * brk)] = -1
        blit(m, piece)


def streaks(m, x, y, cx, cy, n, r0, r1, w, shades, seed=0, flat=1.0, short=0.55, spin=0.0, hot=0.35):
    """n radial tapered streaks from radius r0 out to r1 (every other one short of it), w wide at the root:
    shades (outer, mid, hot) along the length, the root hottest. flat < 1 lies them on the ground."""
    best = np.full(m.shape, np.inf)
    tt = np.zeros(m.shape)
    for j in range(n):
        a = TAU * j / n + spin + 0.35 * (hsh(j, seed) - 0.5)
        L = r1 if j % 2 == 0 else r0 + (r1 - r0) * short
        L *= 0.88 + 0.24 * hsh(j, seed + 3)
        c, s = math.cos(a), math.sin(a)
        d, t, _ = stroke(x - cx, (y - cy) / max(flat, 0.05), [(r0 * c, r0 * s), (L * c, L * s)], w, 0.0)
        better = d < best
        best[better] = d[better]
        tt[better] = t[better]
    on = best < 0
    m[on] = shades[0]
    m[on & (tt < 0.7)] = shades[1]
    m[on & (tt < hot)] = shades[2]
    return on


def ring(x, y, cx, cy, r, w, flat=1.0):
    q = np.hypot(x - cx, (y - cy) / flat)
    return (q <= r) & (q > r - w)


def puff(m, x, y, cx, cy, r, tones, brk=0.0, seed=0.0, ph=0.0):
    """A round puff in 3 tones (shadow, mid, light) lit from the top left, its edge breaking into dots by brk (0..1)."""
    d = lumpy(x, y, cx, cy, r, 0.14, seed, ph, 4)
    on = d < 1.0
    ox, oy = lit_offset(r, 0.38)
    h = np.hypot(x - cx - ox, y - cy - oy) / r
    piece = np.full(m.shape, -1, np.int8)
    piece[on] = tones[0]
    piece[on & (h < 0.95)] = tones[1]
    piece[on & (h < 0.5)] = tones[2]
    if brk > 0:
        b = bayer(m)
        piece[on & (d > 1 - 0.8 * brk) & (b < 0.45 + 0.55 * brk)] = -1
        piece[on & (b < 0.6 * brk * brk)] = -1
    blit(m, piece)
    return on


def polygon(cx, cy, r, n, seed, ph=0.0, jit=0.22):
    pts = []
    for i in range(n):
        a = ph + TAU * i / n + 0.3 * (hsh(i, seed) - 0.5)
        rr = r * (1 - jit + 2 * jit * hsh(i, seed + 5))
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def facets(m, x, y, pts, shades, top=True):
    """A convex faceted solid inside polygon pts: each face (centre to edge) shaded by how it faces the light, shades
    (shadow, mid, lit, highlight); top adds a flat lit top face and a hard highlight on the lit rim."""
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    n = len(pts)
    inside = np.ones(m.shape, bool)
    for i in range(n):
        (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
        inside &= ((bx - ax) * (y - ay) - (by - ay) * (x - ax)) >= 0
    if not inside.any():  # the other winding
        inside = np.ones(m.shape, bool)
        for i in range(n):
            (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
            inside &= ((bx - ax) * (y - ay) - (by - ay) * (x - ax)) <= 0
    ang = np.arctan2(y - cy, x - cx)
    for i in range(n):
        (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
        a0, a1 = math.atan2(ay - cy, ax - cx), math.atan2(by - cy, bx - cx)
        span = (a1 - a0) % TAU
        sel = inside & (((ang - a0) % TAU) <= span)
        mid = a0 + span / 2
        lit = math.cos(mid) * LIGHT[0] + math.sin(mid) * LIGHT[1]
        m[sel] = shades[2] if lit > 0.45 else shades[1] if lit > -0.35 else shades[0]
        if top and lit > 0.45:  # the hard highlight along the lit edge
            ex, ey = bx - ax, by - ay
            el = max(math.hypot(ex, ey), 1e-6)
            dist = ((x - ax) * ey - (y - ay) * ex) / el
            m[sel & (np.abs(dist) < 0.55)] = shades[3]
    if top:
        r = max(math.hypot(p[0] - cx, p[1] - cy) for p in pts)
        ox, oy = lit_offset(r, 0.2)
        m[inside & (np.hypot(x - cx - ox, y - cy - oy) < r * 0.34)] = shades[2]
    return inside


def twinkle(m, px, py, size, hot, mid):
    """A 4-point star at sheet px (px, py): arms size px long, the centre hot."""
    h, w = m.shape
    for k in range(-size, size + 1):
        for (xx, yy) in ((px + k, py), (px, py + k)):
            xi, yi = int(round(xx)), int(round(yy))
            if 0 <= xi < w and 0 <= yi < h:
                m[yi, xi] = hot if abs(k) <= size // 2 else mid


def to_px(m, X, Y, wx, wy):
    """Sheet px of world point (wx, wy) on grids X, Y (the nearest cell centre)."""
    j = int(np.argmin(np.abs(Y[:, 0] - wy)))
    i = int(np.argmin(np.abs(X[0, :] - wx)))
    return i, j


# ----- claws -----
# One claw read per strike: tapered claw strokes sweep along their tracks, and the gash they leave is the after-image of
# those same strokes, laid only behind the claw's tail (never under the claws, never a second set of marks at once).

def claw_tracks(span, n=3, gap=3.4, bow=3.0, tilt=0.3, u0=0.0, sgn=1.0, steps=14, spread=0.0):
    """n parallel claw tracks across the aim as local (u ahead, v right) polylines in world px: each runs from v = -span
    to +span (sgn -1 mirrors it, the other hand), bowed ahead by bow, slanted by tilt so they read as a slash, spaced
    gap apart across their normal; spread opens the outer tracks apart toward the far end."""
    base = []
    for q in np.linspace(0, 1, steps):
        v = span * (2 * q - 1)
        base.append((u0 + bow * math.sin(math.pi * q) + tilt * v, v))
    out = []
    for k in range(n):
        o = (k - (n - 1) / 2) * gap
        line = []
        for i, (u, v) in enumerate(base):
            a, b = base[max(i - 1, 0)], base[min(i + 1, len(base) - 1)]
            du, dv = b[0] - a[0], b[1] - a[1]
            ln = max(math.hypot(du, dv), 1e-6)
            nu, nv = -dv / ln, du / ln  # the normal, ahead of the stroke
            if nu < 0:
                nu, nv = -nu, -nv
            q = i / (len(base) - 1)
            line.append((u + o * nu + (k - (n - 1) / 2) * spread * q, sgn * (v + o * nv)))
        out.append(line)
    return out


def to_world(tracks, a):
    """Local (u, v) tracks turned to heading a (u along it, v to its right) as world (x, y)."""
    c, s = math.cos(a), math.sin(a)
    return [[(u * c - v * s, u * s + v * c) for u, v in t] for t in tracks]


def claw_marks(m, x, y, tracks, head, claw_len, claw, scar, w_claw=3.2, w_scar=2.0, scar_fade=0.0, stagger=0.05,
               flash=0.0, hot=None):
    """Paints one sweep frame of claw tracks (world px polylines) into shade map m.
    head: how far the claws' tips have run (0 at the start of a track, 1 at its end, past 1 they leave it);
    claw: shades (body, lit, pale, white tip), scar: shades (deep gash, wet lip, specular);
    the claw is the stretch of claw_len behind its tip, the scar the track behind the claw's tail only.
    flash: radius of a white-hot disc on the middle claw's tip. Returns the middle track's tip point or None."""
    n = len(tracks)
    tip_pt = None
    for i, pts in enumerate(tracks):
        h = head - stagger * abs(i - (n - 1) / 2)
        d, t, sd = stroke(x, y, pts, 0.0, 0.0)
        scar_to = min(1.0, max(0.0, h - claw_len * 0.9))
        if scar_to > 0.02:
            wt = w_scar * np.sin(np.clip(t / max(scar_to, 0.05), 0, 1) * math.pi) ** 0.7 * min(1.0, 0.5 + scar_to)
            on = (d < wt / 2) & (t <= scar_to)
            if scar_fade > 0:
                on &= bayer(m) >= scar_fade
            m[on] = scar[0]
            m[on & (sd < 0) & (d > wt / 2 - 0.75)] = scar[1]
            for q in (0.3, 0.62):
                if q < scar_to:
                    m[on & (np.abs(t - q) < 0.035) & (sd < 0) & (d < 0.4)] = scar[2]
        lo, hi = h - claw_len, h
        if hi > 0.0 and lo < 1.0:
            s = (t - lo) / claw_len
            prof = np.where(s < 0.8, 0.3 + 0.7 * (np.clip(s, 0, 0.8) / 0.8) ** 0.9, (1 - s) / 0.2)
            on = (d < w_claw * np.clip(prof, 0, 1) / 2) & (s >= 0) & (s <= 1) & (t <= 1)
            m[on] = claw[0]
            m[on & (sd < 0)] = claw[1]
            m[on & (d < w_claw * prof * 0.18) & (s > 0.25)] = claw[2]
            m[on & (s > 0.84)] = claw[3]
        if i == (n - 1) // 2 and hi > 0.0 and lo < 1.0:
            k = min(1.0, max(0.0, hi)) * (len(pts) - 1)
            j = int(k)
            j2 = min(j + 1, len(pts) - 1)
            f = k - j
            tip_pt = (pts[j][0] + (pts[j2][0] - pts[j][0]) * f, pts[j][1] + (pts[j2][1] - pts[j][1]) * f)
    if flash > 0 and tip_pt is not None and hot is not None:
        m[np.hypot(x - tip_pt[0], y - tip_pt[1]) < flash] = hot
    return tip_pt


def drop(m, x, y, cx, cy, r, shades, tail=None):
    """A thick glossy blood drop (shades deep, body, light, specular) with a short streak behind it along tail (dx, dy)."""
    if tail is not None:
        d, t, _ = stroke(x - cx, y - cy, [(0, 0), tail], r * 1.5, 0.0)
        m[d < 0] = shades[0]
    ball(m, x, y, cx, cy, r, shades)


def claw_drops(m, x, y, tracks, f, seed, shades, r=1.1, n=5, fly=3.2, grav=0.8, start=1, lim=19.0):
    """Blood drops flung off the far ends of the claw tracks along their last tangent (frame f counted from start): a
    thick glossy drop with a dark edge and a short streak behind it while it flies, fewer and lower as it falls."""
    if f < start:
        return
    k = f - start
    for j in range(n):
        pts = tracks[j % len(tracks)]
        (ax, ay), (bx, by) = pts[-2], pts[-1]
        ln = max(math.hypot(bx - ax, by - ay), 1e-6)
        dx, dy = (bx - ax) / ln, (by - ay) / ln
        sp = 0.45 * (hsh(j, seed) - 0.5)  # spread about the tangent
        c, s = math.cos(sp), math.sin(sp)
        ddx, ddy = dx * c - dy * s, dx * s + dy * c
        dist = fly * (0.7 + 0.8 * hsh(j, seed + 1)) * (k + 1) ** 0.8
        cx, cy = bx + ddx * dist, by + ddy * dist + grav * k * k
        if (k >= 2 and j % 2) or abs(cx) > lim or abs(cy) > lim:
            continue
        rr = r * (0.85 + 0.35 * hsh(j, seed + 2)) * (1.0 if k < 3 else 0.8)
        drop(m, x, y, cx, cy, rr, shades, tail=(-ddx * 2.6, -ddy * 2.6) if k < 2 else None)


# ----- thematic hits: one flash disc, tapered streaks and debris true to what was struck -----

def hit_cell(X, Y, f, big, th, seed=0):
    """One cell of a blow's hit on a body (frames 6, the peak at frame 1): a white-hot flash disc
    with tapered streaks round it, the debris of the theme thrown out (th kind: drop, shard, chip, ember, spike) and mist
    puffs that break into dots. th: rim, streak (outer, mid, hot), disc (lit, hot), deb (4 shades, shadow to highlight),
    drop (4 shades) the drop debris, drops (4 shades) extra flung drops or None, mist (3 tones) or None."""
    m = np.full(X.shape, -1, np.int8)
    s = 1.35 if big else 1.0
    turn = 0.4 * hsh(seed, 3)
    p = max(0.0, (f - 0.5) / 4.5)
    out = 1 - (1 - p) ** 2
    if f == 1:
        streaks(m, X, Y, 0, 0, 12 if big else 8, 1.5, 12.8 * s, 2.3 * s, th["streak"], seed=seed, spin=turn)
    elif f == 2:
        streaks(m, X, Y, 0, 0, 12 if big else 8, 5.5 * s, 13.4 * s, 1.3 * s, th["streak"], seed=seed + 1, spin=turn,
                short=0.5)
    elif f == 3:
        streaks(m, X, Y, 0, 0, 8 if big else 5, 9.5 * s, 13.0 * s, 0.9, (th["streak"][0], th["streak"][0], th["streak"][1]),
                seed=seed + 2, spin=turn, short=0.5)
    r = np.hypot(X, Y)
    disc = {0: 1.6, 1: 5.2 * s, 2: 3.2 * s}.get(f, 0.0)
    if disc:
        m[r < disc] = th["disc"][0]
        m[r < disc * 0.62] = th["disc"][1]
    n = 9 if big else 6
    kind = th["kind"]
    for j in range(n):
        a = turn + math.tau * j / n + 0.5 * (hsh(j, seed) - 0.5)
        dist = (2.5 + 8.0 * (0.6 + 0.4 * hsh(j, seed + 4))) * s * out
        cx, cy = dist * math.cos(a), dist * math.sin(a) + 1.6 * max(0, f - 2) ** 2 * 0.5
        if f == 0 or (f >= 4 and j % 2) or (f == 5 and j % 3):
            continue
        size = (1.2 + 1.3 * hsh(j, seed + 6)) * (1.15 if big else 1.0) * (1.0 if f < 4 else 0.75)
        if kind in ("shard", "chip") and f >= 1:
            pts = polygon(cx, cy, size * 1.5, 4 if kind == "shard" else 5, seed + j, ph=a, jit=0.3)
            facets(m, X, Y, pts, th["deb"], top=False)
        elif kind == "spike":
            tip = (cx + math.cos(a) * size * 2.6, cy + math.sin(a) * size * 2.6)
            d, t, sd = stroke(X, Y, [(cx, cy), tip], size * 1.1, 0.0)
            m[d < 0] = th["deb"][1]
            m[(d < 0) & (sd < 0)] = th["deb"][2]
            m[(d < 0) & (t > 0.7)] = th["deb"][3]
        elif kind == "ember":
            ball(m, X, Y, cx, cy, size * 0.8, (th["deb"][0], th["deb"][1], th["deb"][2], th["deb"][3]))
        else:  # drop
            dd = th.get("drop") or th["deb"]
            drop(m, X, Y, cx, cy, size * 0.85, dd, tail=(-math.cos(a) * 2.4, -math.sin(a) * 2.4) if f < 3 else None)
    if th.get("drops") and kind != "drop" and f >= 1:  # blood or water flung beside the debris
        for j in range(5 if big else 3):
            a = turn + 0.5 + math.tau * (j + 0.5) / (5 if big else 3) + 0.4 * (hsh(j, seed + 12) - 0.5)
            dist = (4.0 + 8.0 * hsh(j, seed + 13)) * s * out
            if f >= 4 and j % 2:
                continue
            drop(m, X, Y, dist * math.cos(a), dist * math.sin(a) + 1.4 * max(0, f - 2) ** 2 * 0.5, 1.0 * (1.2 if big else 1.0),
                 th["drops"], tail=(-math.cos(a) * 2.2, -math.sin(a) * 2.2) if f < 3 else None)
    if th.get("mist") and f >= 2:
        k = f - 1
        for j in range(5 if big else 3):
            a = turn + 0.7 + math.tau * j / (5 if big else 3) + hsh(j, seed + 9)
            dd = (2.5 + 2.2 * k) * s * (0.6 + 0.5 * hsh(j, seed + 10))
            puff(m, X, Y, dd * math.cos(a), dd * math.sin(a) - 0.6 * k, (2.0 + 0.5 * k) * s * 0.8, th["mist"],
                 brk=min(1.0, (f - 1.5) / 3.5), seed=j + seed, ph=0.3 * f)
    if f >= 4:
        m = fade(m, (f - 3) * 0.3)
    return rim(m, th["rim"]) if f <= 2 else m


def at(m, X, Y, a, du, dv):
    """Sheet px (i, j) of the point du along and dv across heading a (world px), for a mote or twinkle on a bolt."""
    return to_px(m, X, Y, du * math.cos(a) - dv * math.sin(a), du * math.sin(a) + dv * math.cos(a))


def kite(m, X, Y, cx, cy, ang, L, w, shades, tail=0.3):
    """A faceted shard (kite) of length L and width w at (cx, cy) pointing ang: shades (deep, mid, light, highlight),
    the lit half and a ridge line pale, a hard highlight near the tip."""
    u, v = rot(X - cx, Y - cy, ang)
    t = np.clip((u + tail * L) / ((1 + tail) * L), 0, 1)
    half = w / 2 * np.where(t < 0.55, t / 0.55, (1 - t) / 0.45)
    on = (u > -tail * L) & (u < L) & (np.abs(v) <= half)
    m[on] = shades[1]
    m[on & (v < -0.05 * w)] = shades[2]
    m[on & (v > 0.18 * w)] = shades[0]
    m[on & (np.abs(v) < 0.09 * w) & (t > 0.25)] = shades[3]
    return on


def hit_burst(m, X, Y, f, tones, smoke, rim, cx=0.0, cy=0.0, r=12.0, flat=1.0, seed=0, shards=None, rise=1.0):
    """One blow in six frames (frame 1 is the peak, name it impact_peak): 0 a core disc, 1 flash disc with mixed
    streaks and a ring, 2 a hollow lumpy burst with longer streaks, 3 to 5 three-tone puffs that rise and break up into
    dots with embers falling out. tones (deep, mid, light, hot), smoke (shadow, mid, light), shards (deep, mid, light,
    highlight) adds flying kites. flat < 1 squashes the blow onto the ground."""
    Yf = cy + (Y - cy) / flat
    hot = tones[3]
    if f == 0:
        q = np.hypot(X - cx, Yf - cy)
        m[q < 0.22 * r] = tones[2]
        m[q < 0.12 * r] = hot
    elif f in (1, 2):
        k = f - 1
        streaks(m, X, Yf, cx, cy, 10 + 2 * k, r * (0.34 + 0.22 * k), r * (0.9 + 0.2 * k), 2.6 - 0.9 * k,
                (tones[1 + k], tones[2 + k] if 2 + k < 4 else hot, hot), seed=seed + 2, spin=0.2 * k)
        ring_on = ring(X, Yf, cx, cy, r * (0.72 + 0.14 * k), 0.8)
        m[ring_on] = tones[2 - k]
        d = lumpy(X, Yf, cx, cy, r * (0.55 + 0.1 * k), 0.16, seed, 0.4 + k, 6)
        on = d < 1.0
        m[on] = tones[1]
        m[on & (d < 0.8)] = tones[2]
        if k == 0:
            m[on & (d < 0.5)] = hot
        else:
            m[on & (d < 0.42)] = tones[1]
    else:
        k = f - 3
        for j in range(5):
            aj = TAU * j / 5 - math.pi / 2 + 0.3 + 0.4 * hsh(j, seed)
            rr = r * (0.3 + 0.1 * k)
            puff(m, X, Y, cx + rr * math.cos(aj), cy - rise * r * (0.12 + 0.2 * k) + rr * 0.7 * flat * math.sin(aj),
                 r * (0.24 + 0.04 * k + 0.03 * (j % 2)), smoke, brk=(0.0, 0.45, 0.8)[min(k, 2)], seed=j + seed, ph=f)
        for j in range(8):
            aj = TAU * j / 8 + 0.2
            rr = r * (1.05 + 0.1 * k)
            if (j + f) % 3:
                i, jj = to_px(m, X, Y, cx + rr * math.cos(aj), cy + rr * flat * 0.8 * math.sin(aj) + 1.5 * k * k)
                m[jj, i] = (tones[3], tones[2], tones[1])[min(k, 2)]
    if shards and f in (1, 2, 3, 4):
        for j in range(6):
            aj = TAU * j / 6 + 0.5 * hsh(j, seed + 9)
            rr = r * (0.55 + 0.32 * (f - 1)) * (0.8 + 0.4 * hsh(j, seed + 4))
            kite(m, X, Y, cx + rr * math.cos(aj), cy + rr * flat * math.sin(aj) + 0.6 * (f - 1) ** 2, aj,
                 r * 0.26 * (1.0 - 0.12 * (f - 1)), r * 0.13, shards, tail=0.35)
    return rim_if(m, rim, f <= 3)


# ----- ground reaction: what the ground does when a blow lands on it -----
# A hit sells its weight through what it leaves: dust kicked out along the ground, debris thrown up that falls,
# bounces once and stays where it lands (permanence), and for heavy blows cracks that stay too. Counts follow the hit's
# weight (export.WEIGHTS): a light hit throws a few pixels, a finisher a spray.

GROUND = {
    "light":    dict(debris=4, dust=2, crack=0, fly=1.0),
    "heavy":    dict(debris=10, dust=4, crack=3, fly=1.4),
    "finisher": dict(debris=18, dust=6, crack=6, fly=1.9),
    "blast":    dict(debris=16, dust=6, crack=5, fly=1.7),
}


def debris_at(j, t, cx, cy, r, fly, flat, seed):
    """World (x, y) and resting flag of debris chunk j at t s after contact: an arc up and out under gravity, one
    bounce at a third of the height, then at rest on its own spot of the ground plane."""
    h0, h1, h2 = hsh(j, seed + 11), hsh(j, seed + 12), hsh(j, seed + 13)
    side = -1 if j % 2 else 1
    spread = 0.25 + 0.95 * h0                       # radians off vertical
    v0 = r * fly * (2.6 + 2.2 * h1)                 # px/s
    g = r * 18.0 * fly                              # px/s^2: a harder blow throws higher, never longer
    vx, vy = side * v0 * math.sin(spread), v0 * math.cos(spread)
    gy = cy + flat * r * 0.5 * (h2 - 0.5)           # its own depth on the ground plane
    t1 = 2 * vy / g
    if t < t1:
        return cx + vx * t, gy - (vy * t - 0.5 * g * t * t), False
    x1, vx2, vy2 = cx + vx * t1, 0.45 * vx, 0.3 * vy
    t2 = 2 * vy2 / g
    u = t - t1
    if u < t2:
        return x1 + vx2 * u, gy - (vy2 * u - 0.5 * g * u * u), False
    return x1 + vx2 * t2, gy, True


def ground_impact(m, X, Y, f, fps, tones, dust, cx=0.0, cy=0.0, r=12.0, weight="heavy", flat=0.35, life=1.2, seed=0):
    """The ground's reaction to a blow landing at (cx, cy) on it, frame f counted from the contact frame (nothing
    before it): dust puffs that slide out both ways, rise a little and break into dots; debris chunks (tones deep,
    mid, light) that arc, bounce once and rest; and for heavy, finisher and blast weights cracks in tones[0] that
    grow over two frames and stay. What rests on the ground dissolves over the last 40 % of life s, so the one-shot
    ends empty. flat squashes the ground plane (1 top-down, 0.35 side or 3/4). Paints into m, returns m."""
    if f < 0:
        return m
    g = GROUND[weight]
    t = f / fps
    piece = np.full(m.shape, -1, np.int8)
    for j in range(g["crack"]):                     # cracks under everything else
        a = TAU * (j + 0.5 * hsh(j, seed + 21)) / g["crack"]
        ln = r * (0.6 + 0.6 * hsh(j, seed + 22)) * min(1.0, (f + 1) / 2)
        pts, px, py = [(cx, cy)], cx, cy
        for k in range(3):
            aj = a + 0.6 * (hsh(j * 3 + k, seed + 23) - 0.5)
            px, py = px + ln / 3 * math.cos(aj), py + ln / 3 * flat * math.sin(aj)
            pts.append((px, py))
        d, _, _ = stroke(X, Y, pts, 1.1, 0.4)
        piece[d < 0] = tones[0]
    for j in range(g["dust"]):
        side = -1 if j % 2 else 1
        out = r * (0.35 + 0.25 * (j // 2)) + r * 1.4 * (1 - math.exp(-t * 6)) * (0.7 + 0.5 * hsh(j, seed + 31))
        rr = r * (0.16 + 0.05 * (j // 2)) * (1 + 1.2 * (1 - math.exp(-t * 5))) * g["fly"] ** 0.5
        brk = min(1.0, t / (0.5 * life))
        if brk < 1.0:
            puff(piece, X, Y, cx + side * out, cy - r * 0.15 - r * 0.5 * t - rr * 0.4, rr, dust, brk=brk, seed=j + seed,
                 ph=f * 0.3)
    for j in range(g["debris"]):
        x, y, rest = debris_at(j, t, cx, cy, r, g["fly"], flat, seed)
        size = 0.6 if j % 3 else 1.1
        on = (np.abs(X - x) < size) & (np.abs(Y - y) < size)
        piece[on] = tones[1]
        if not rest:
            piece[on & (Y < y)] = tones[2]           # lit top while it flies
    if t > 0.6 * life:
        piece = fade(piece, min(1.0, (t - 0.6 * life) / (0.4 * life)))
    blit(m, piece)
    return m


def rim_if(m, s, on):
    return outline(m, s) if on else m


def leaf(m, X, Y, cx, cy, ang, L, w, shades, roll=1.0, bend=0.0):
    """A lens-shaped leaf or petal from its base at (cx, cy) along ang: shades (deep, mid, light, vein); roll < 1
    narrows it as it turns edge on, bend curls its tip; the lit half is lighter and a thin midrib runs down it."""
    u, v = rot(X - cx, Y - cy, ang)
    t = np.clip(u / L, 0, 1)
    vv = v - bend * L * t * t
    half = 0.5 * w * max(roll, 0.12) * np.sin(math.pi * t) ** 0.75
    on = (u >= 0) & (u <= L) & (np.abs(vv) <= half)
    m[on] = shades[1]
    m[on & (vv < -0.18 * half)] = shades[2]
    m[on & (vv > 0.45 * half)] = shades[0]
    m[on & (np.abs(vv) < 0.12 * np.maximum(half, 0.8)) & (t > 0.1) & (t < 0.85)] = shades[3]
    return on
