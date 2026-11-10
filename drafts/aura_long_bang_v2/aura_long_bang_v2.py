"""Ice Dragon Aura v2, redrawn to the pixelfx bar: a clear, glassy ice dragon that circles a standing character,
trailing frost glints, over a frost ring at the feet with cold vapour curling off it. A seamless loop of 60 frames
at 30 fps (2 s, the same length as v1), front 3/4 view.

The orbit is a tilted ellipse round the chest with a slow rise and fall; z = sin(u) is the depth (front > 0).
The sheet comes in two layers, as an aura that passes behind a body must: `_back` (drawn under the character:
the half of the dragon behind, the ground ring, glints behind) and `_front` (drawn over it). Light is split the
same way. Glass look: a translucent body (alpha tones) under an opaque rim, a bright lit top edge, a white
specular streak and scattered scale glints. Light stays smooth (no bands): every hot part has a tight core and a
wide low-k pool, the glass body carries a faint cold sheen, and a pool round the body swells as the head passes in
front. The vapour is translucent, never dithered.

    ../../.venv/bin/python aura_long_bang_v2.py     # from drafts/aura_long_bang_v2; exits 1 if the check fails
"""
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE / "kit")]
import light  # noqa: E402
import pfx  # noqa: E402
from fxkit import TAU, blit, hsh, kite, rot, twinkle  # noqa: E402
from fxlib import outline, stroke  # noqa: E402

NAME = "aura_long_bang_v2"
W, H = 176, 192
FEET = (88, 170)  # pivot: between the feet
CX, CY = 88.0, 116.0  # orbit centre, about the chest
R, RY, RISE = 50.0, 15.0, 13.0  # orbit half width, half depth seen from above, rise and fall
SPAN = 0.62 * TAU  # body length along the orbit
FRAMES, FPS = 60, 30
HEAD = 1.15

# 0 rim, 1 deep (glass), 2 body (glass), 3 light (glass), 4 lit edge, 5 white; 6 ring frost (glass)
# 7 to 9: vapour, thin to dense (translucent)
PAL = ["#24508e", "#3a7cc8a0", "#6ab8ec80", "#a8e4f4b8", "#dcf8ff", "#ffffff", "#8cc8ec70",
       "#6ab4ec26", "#8ccff53c", "#b4e4ff58"]
LIGHT = ["#14306a", "#4aa8ec", "#bdeeff", "#ffffff"]  # light ramp, weak to strong

Y, X = np.mgrid[0:H, 0:W].astype(float)
GRID = SimpleNamespace(x=X, y=Y)


def empty():
    return np.full((H, W), -1, np.int8)


def orbit(u):
    u = np.asarray(u, float)
    x = CX + R * np.cos(u)
    y = CY + RY * np.sin(u) + RISE * np.sin(2 * u + 0.6)
    return np.stack([x, y], axis=-1), np.sin(u)


def head_u(f):
    return TAU * f / FRAMES


def runs(z):
    """Index runs of one depth sign along the spine, each grown by a point at both ends so the halves meet."""
    out, start = [], 0
    for i in range(1, len(z) + 1):
        if i == len(z) or (z[i] >= 0) != (z[start] >= 0):
            out.append((z[start] >= 0, max(0, start - 1), min(len(z), i + 1)))
            start = i
    return out


def glass_body(pts, w0, w1):
    """One run of the body: translucent glass, lit top edge, specular streak, scale glints, a clear fin."""
    m = empty()
    d, t, _ = stroke(X, Y, pts, w0, w1)
    half = (w0 + (w1 - w0) * t) / 2
    seg = np.hypot(*np.diff(pts, axis=0).T)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    along = t * cum[-1]
    cy = np.interp(along, cum, pts[:, 1])
    top = (cy - Y) / np.maximum(half, 0.5)  # +1 at the top edge on screen
    on = d < 0
    m[on] = 2
    m[on & (top > 0.2)] = 3
    m[on & (top > 0.6)] = 4
    m[on & (top < -0.55)] = 1
    m[on & (np.abs(top - 0.35) < 0.16) & ((along / 7.0) % 1.0 < 0.55)] = 5
    row = np.floor((top + 1) * 1.6)
    glint = ((along / 5.0 + 0.5 * row) % 1.0 < 0.18) & (((top + 1) * 1.6) % 1.0 < 0.3) & (top < 0.2)
    m[on & glint] = 4
    saw = 1 - ((along / 6.0) % 1.0)
    fin = ~on & (top > 0.3) & (d < saw * 4.0 * np.clip(t * 3, 0, 1) * np.clip((0.97 - t) * 10, 0, 1))
    m[fin] = 3
    m[fin & (saw > 0.8)] = 4
    return m


def head(hx, hy, tx, ty, f):
    """Glass head in profile along the screen tangent, kept upright whichever way it flies."""
    a = math.atan2(ty, tx)
    u, v = rot(X - hx, Y - hy, a)
    if tx < 0:
        v = -v
    u, v = u / HEAD, v / HEAD
    m = empty()

    def line(points, w0, w1, tone):
        d, _, _ = stroke(u, v, points, w0, w1)
        m[d < 0] = tone

    for j in range(3):
        line([(-3, -2 + 1.8 * j), (-11 - 2 * hsh(j, 2), -3 + 2.6 * j + 1.2 * math.sin(TAU * f / FRAMES * 2 + j))],
             2.6, 0.7, 3)
    skull = ((u + 0.5) / 6.0) ** 2 + ((v + 0.8) / 4.4) ** 2 < 1
    top = -3.8 + 0.2 * u
    upper = (u > 0) & (u < 12.5) & (v > top) & (v < 0.6) & ~((u > 11.5) & (v < -1.6))
    lo = v - (1.4 + 0.12 * u)
    lower = (u > 0.5) & (u < 10) & (lo > -0.4) & (lo < 2.2 - 0.14 * u)
    face = skull | upper
    m[face] = 2
    m[face & (v < -1.4)] = 3
    m[face & (v < -3.0 + 0.2 * u)] = 4
    m[lower] = 1
    m[(u > 1.5) & (u < 11.5) & (v >= 0.6) & (lo <= -0.4)] = 1
    line([(0, -3.4), (-6, -9), (-13, -10)], 2.4, 0.8, 4)
    line([(-5, -8.4), (-6, -12.5)], 1.4, 0.7, 4)
    m[((u - 4.4) / 1.5) ** 2 + ((v + 2.2) / 1.0) ** 2 < 1] = 5
    wob = 1.0 * math.sin(TAU * f / FRAMES * 2)
    line([(11.5, 0.2), (7, 3.6), (-1, 5.6 + wob), (-11, 5 - wob)], 1.2, 0.7, 4)
    return outline(m, 0)


def lit(L, x, y, r, k):
    """The pixelfx pair on one hot point: a tight core and a wide soft pool."""
    light.glow(L, GRID, x, y, r, k)
    light.glow(L, GRID, x, y, r * 2.8, k * 0.2)


def glints(layers, lights, f, hu):
    """Frost glints shed along the body: each is born on the orbit, drifts out and up and blinks once."""
    for i in range(22):
        ph = (f / FRAMES * 2 + hsh(i, 61)) % 1.0
        u = hu - SPAN * (0.1 + 0.9 * hsh(i, 63)) - 0.4 * ph
        (x, y), z = orbit(u)
        x += (x - CX) * 0.25 * ph
        y -= 14 * ph + 4 * hsh(i, 65)
        bright = max(0.0, 1 - abs(ph - 0.22) / 0.22) if ph < 0.6 else 0.0
        size = 3 if bright > 0.7 else 2 if bright > 0.35 else 1 if ph < 0.75 else 0
        if size == 0:
            continue
        k = 1 if z >= 0 else 0
        twinkle(layers[k], x, y, size, 5, 4 if size > 1 else 3)
        lit(lights[k], x, y, 4, 0.08 + 0.3 * bright)


def motes(layers, lights, f):
    """Snow motes rising round the body, 1 px, each with a faint light of its own."""
    for i in range(14):
        ph = (f / FRAMES + hsh(i, 71)) % 1.0
        a = TAU * hsh(i, 73) + TAU * ph * 0.5
        x = CX + 0.8 * R * math.cos(a)
        y = FEET[1] - 6 - 96 * ph
        k = 1 if math.sin(a) >= 0 else 0
        xi, yi = int(round(x)), int(round(y))
        if 2 <= xi < W - 2 and 2 <= yi < H - 2 and 0.1 < ph < 0.9:
            layers[k][yi, xi] = 4 if i % 3 else 5
            light.glow(lights[k], GRID, x, y, 3, 0.12 * math.sin(math.pi * ph))


def vapour(layers, lights, f):
    """Cold vapour off the ring. Cold air sinks, so the puffs roll outward along the ground, flat, densest at the
    core and thinning to a ragged edge as they swell and fade, lit faintly from inside; never dithered."""
    fx, fy = FEET
    for i in range(12):
        ph = (f / FRAMES * 1.5 + hsh(i, 81)) % 1.0
        if ph > 0.9:
            continue
        a = TAU * hsh(i, 83) + 0.6 * ph
        spread = 1 + 0.12 * ph
        x = fx + 40 * math.cos(a) * spread
        y = fy + 10 * math.sin(a) * spread - 2
        r = 4 + 6 * ph
        q = np.hypot((X - x) / r, (Y - y) / (r * 0.4))
        q = q * (1 + 0.2 * np.sin(np.arctan2(Y - y, X - x) * 4 + TAU * hsh(i, 85) + 3 * ph))
        thin = ph / 0.9  # older puffs lose their dense core first
        k = 1 if math.sin(a) > 0 else 0
        m = layers[k]
        for lim, tone in ((1.0, 7), (0.7 - 0.4 * thin, 8), (0.4 - 0.4 * thin, 9)):
            puff = (q < lim) & ((m < 0) | ((m >= 7) & (m < tone)))
            m[puff] = tone
        light.glow(lights[k], GRID, x, y, r * 1.4, 0.1 * (1 - thin))


def ring(layers, lights, f):
    """A frost ring under the feet: a translucent band with a 1 px lit near rim, small crystals standing on it
    that swell and settle, light hugging it."""
    fx, fy = FEET
    q = np.hypot((X - fx) / 46.0, (Y - fy) / 12.0)
    m = layers[0]
    m[(q < 1) & (q > 0.88)] = 6
    m[(q < 1.0) & (q > 0.95) & (Y > fy)] = 4
    m[(q < 0.9) & (q > 0.86) & (Y < fy)] = 3
    light.glow_ring(lights[0], GRID, fx, fy, 46, 4, 0.12, flat=12 / 46)
    light.glow_ring(lights[0], GRID, fx, fy, 46, 12, 0.05, flat=12 / 46)
    for i in range(7):
        a = TAU * i / 7 + 0.3
        bx, by = fx + 46 * math.cos(a), fy + 12 * math.sin(a)
        grow = 0.5 + 0.5 * math.sin(TAU * (f / FRAMES + i / 7))
        k = 1 if math.sin(a) > 0 else 0
        piece = empty()
        kite(piece, X, Y, bx, by, -math.pi / 2 + 0.25 * math.cos(a), 5 + 4 * grow, 4, (1, 3, 4, 5), 0.15)
        blit(layers[k], outline(piece, 0))
        lit(lights[k], bx, by - 5, 4, 0.1 + 0.2 * grow)


def frame(f):
    back, front = empty(), empty()
    lights = [light.buffer(GRID), light.buffer(GRID)]
    layers = [back, front]
    ring(layers, lights, f)
    vapour(layers, lights, f)
    hu = head_u(f)
    us = np.linspace(hu - SPAN, hu, 72)
    pts, z = orbit(us)
    widths = 2.0 + 9.0 * np.linspace(0, 1, len(us)) ** 0.7
    pieces = {False: empty(), True: empty()}
    for is_front, a, b in runs(z):
        blit(pieces[is_front], glass_body(pts[a:b], widths[a], widths[b - 1]))
        # a faint cold sheen along the glass, stronger toward the head
        for i in range(a, b - 1, 3):
            t = i / len(us)
            light.glow_line(lights[1 if is_front else 0], GRID, pts[i], pts[min(i + 3, b - 1)],
                            widths[i] * 0.9 + 3, 0.03 + 0.07 * t)
    (hx, hy), hz = orbit(hu)
    tx, ty = orbit(hu + 0.05)[0] - orbit(hu - 0.05)[0]
    # the head faces where the dragon is going next and tilts at most 40 degrees, so it never points straight
    # up or down at the sides of the orbit
    dirx = math.copysign(1, orbit(hu + 0.5)[0][0] - hx)
    a = float(np.clip(math.atan2(ty, abs(tx) + 1e-3), -0.7, 0.7))
    blit(pieces[hz >= 0], head(hx, hy, dirx * math.cos(a), math.sin(a), f))
    bk = outline(pieces[False], 0)
    fr = outline(pieces[True], 0)
    fr[(fr == 0) & (pieces[True] < 0) & (pieces[False] >= 0)] = -1  # no seam where the front half meets the back
    motes(layers, lights, f)
    glints(layers, lights, f, hu)
    blit(back, bk)
    tmp = front.copy()
    front[:] = fr
    blit(front, tmp)
    hl = lights[1 if hz >= 0 else 0]
    light.glow(hl, GRID, hx + 4 * dirx, hy - 2, 9, 0.45)  # the eye and brow, the focal point
    light.glow(hl, GRID, hx, hy, 30, 0.1)
    # the pool round the body, brighter while the head is in front
    light.glow(lights[1], GRID, CX, CY + 6, 70, 0.03 + 0.04 * max(hz, 0))
    return back, front, lights


def light_rgb(L):
    """Summed light kept smooth: weak light takes the deep cold hue, strong light goes white."""
    return pfx.tint(np.repeat(np.clip(L, 0, 1)[..., None], 3, -1), LIGHT)


def over(dst, src):
    """src RGBA over dst RGBA, uint8."""
    sa = src[..., 3:4] / 255.0
    da = dst[..., 3:4] / 255.0
    a = sa + da * (1 - sa)
    rgb = (src[..., :3] * sa + dst[..., :3] * da * (1 - sa)) / np.maximum(a, 1e-6)
    return np.concatenate([rgb, a * 255], axis=-1).round().astype(np.uint8)


def body_stand_in():
    """A grey stand-in character for previews only: legs, torso, head."""
    fx, fy = FEET
    m = np.zeros((H, W), bool)
    for d, _, _ in (stroke(X, Y, [(fx - 6, fy), (fx - 5, fy - 34)], 7, 8), stroke(X, Y, [(fx + 6, fy), (fx + 5, fy - 34)], 7, 8),
                    stroke(X, Y, [(fx, fy - 36), (fx, fy - 70)], 22, 18)):
        m |= d < 0
    m |= np.hypot(X - fx, Y - (fy - 80)) < 9
    img = np.zeros((H, W, 4), np.uint8)
    img[m] = (92, 96, 108, 255)
    return img


def check(layers, sums):
    """Colour alpha and light above a faint level must stay off the cell edge; no frame may be empty."""
    bad = []
    for i, ((cb, cf, _, _), L) in enumerate(zip(layers, sums)):
        on = (cb[..., 3] > 0) | (cf[..., 3] > 0) | (L > 0.02)
        if not ((cb[..., 3] > 0).any() or (cf[..., 3] > 0).any()):
            bad.append(f"frame {i}: empty colour")
        if on[0].any() or on[-1].any() or on[:, 0].any() or on[:, -1].any():
            bad.append(f"frame {i}: touches the cell edge")
    return bad


def main():
    out = HERE / "out"
    out.mkdir(exist_ok=True)
    layers, sums = [], []
    for f in range(FRAMES):
        back, front, (lb, lf) = frame(f)
        layers.append((pfx.paint(back, PAL), pfx.paint(front, PAL), light_rgb(lb), light_rgb(lf)))
        sums.append(lb + lf)
    zero = np.zeros((H, W, 3))
    lit_back = [pfx.composite(cb, lb) for cb, _, lb, _ in layers]
    lit_front = [pfx.composite(cf, lf) for _, cf, _, lf in layers]
    pfx.strip([over(b, fr) for b, fr in zip(lit_back, lit_front)], out / f"{NAME}.png")
    pfx.strip(lit_back, out / f"{NAME}_back.png")
    pfx.strip(lit_front, out / f"{NAME}_front.png")
    pfx.strip([cb for cb, _, _, _ in layers], out / f"{NAME}_back_color.png")
    pfx.strip([cf for _, cf, _, _ in layers], out / f"{NAME}_front_color.png")
    pfx.strip([pfx.composite(np.zeros((H, W, 4), np.uint8), lb) for _, _, lb, _ in layers], out / f"{NAME}_back_light.png")
    pfx.strip([pfx.composite(np.zeros((H, W, 4), np.uint8), lf) for _, _, _, lf in layers], out / f"{NAME}_front_light.png")
    stand = body_stand_in()
    for tag, bg in (("dark", (16, 16, 24, 255)), ("mid", (90, 100, 112, 255))):
        ground = np.zeros((H, W, 4), np.uint8)
        ground[:] = bg
        if tag == "mid":
            stand_c = stand.copy()
            stand_c[stand[..., 3] > 0] = (52, 56, 66, 255)
        else:
            stand_c = stand
        frames = [over(over(over(ground, b), stand_c), fr) for b, fr in zip(lit_back, lit_front)]
        im = np.concatenate(frames, axis=1)
        Image.fromarray(im[..., :3]).resize((im.shape[1] * 4, im.shape[0] * 4), Image.NEAREST).save(
            out / f"{NAME}_4x_{tag}.png")
        Image.fromarray(im[..., :3]).save(out / f"{NAME}_1x_{tag}.png")
        pfx.gif(frames, out / (f"{NAME}.gif" if tag == "dark" else f"{NAME}_mid.gif"), FPS, 4)
    meta = {"name": NAME, "w": W, "h": H, "frames": FRAMES, "fps": FPS, "pivot": list(FEET), "loop": True,
            "layers": {"back": f"{NAME}_back.png (under the character)", "front": f"{NAME}_front.png (over it)"},
            "light": "split as _back_light / _front_light (additive, smooth); _back and _front already include it",
            "light_ramp": LIGHT}
    (out / f"{NAME}.json").write_text(json.dumps(meta, indent=2) + "\n")
    bad = check(layers, sums)
    for b in bad:
        print("FAIL", b)
    print("ok" if not bad else f"{len(bad)} problems", "->", out)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
