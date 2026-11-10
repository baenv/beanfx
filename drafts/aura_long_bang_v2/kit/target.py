"""A straw training dummy for previews: it stands where a blow lands and reacts to the act's hits, so a strike can
be judged with a body taking it. Preview only; the exported sheet stays the effect alone.

    import target as tg
    img = tg.draw((H, W), foot, f, hits, FPS, facing=-1)   # (H, W, 4) uint8, the dummy alone at frame f
    frame = tg.under(effect_rgba, img)                      # the dummy behind the effect

foot is the dummy's base in px (x, y). facing -1 means the blow comes from the left and pushes it right. hits
are export.hit dicts; each reacts by its `react`: flinch (a short tilt), stagger (a wobble that rings down),
knockback (a slide back by `push` px with a tilt) or launch (lifted and dropped back). The contact frame flashes
it white for the hit's `flash` s (one frame without it), then one frame at half; `dir` turns the knockback.
"""
import math

import numpy as np

POST = ("#3a2416", "#6b4428", "#93653c")      # shadow, base, lit
STRAW = ("#7a5a24", "#b8913e", "#e3c46a")
ROPE = "#4a3418"
FLASH = (255, 250, 236)
HEIGHT = 38  # px, the stock size beside a 24 px wide body


def _hex(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def reaction(f, hits, fps):
    """(dx, dy, tilt radians, flash 0..1) of the dummy at frame f, summed over the hits so far."""
    dx = dy = tilt = flash = 0.0
    for h in hits or []:
        dt = (f - h["frame"]) / fps
        if dt < 0:
            continue
        push = h.get("push", 0) or 3.0
        kind = h.get("react", "flinch")
        lit = max(1, round(h["flash"] * fps)) if "flash" in h else 1  # frames fully white, then one at half
        k = f - h["frame"]
        if k <= lit:
            flash = max(flash, 1.0 if k < lit else 0.5)
        a = math.radians(h.get("dir", 0))
        ux, uy = abs(math.cos(a)), math.sin(a)  # away from the blow, and down (+) or up (-) along it
        if kind == "flinch":
            tilt += 0.18 * math.exp(-dt * 10)
        elif kind == "stagger":
            tilt += 0.25 * math.exp(-dt * 4) * math.cos(dt * 22)
        elif kind == "knockback":
            dx += push * ux * (1 - math.exp(-dt * 12))
            dy += min(0.0, push * uy * (1 - math.exp(-dt * 12)))  # a rising blow lifts; the ground stops a falling one
            tilt += 0.3 * math.exp(-dt * 6) * math.cos(dt * 14)
        elif kind == "launch":
            up = min(dt / 0.35, 1.0)
            dy -= push * 2.5 * math.sin(math.pi * up) if dt < 0.35 else 0.0
            tilt += 0.4 * math.exp(-dt * 5)
    return dx, dy, tilt, flash


def draw(shape, foot, f, hits, fps, facing=-1, height=HEIGHT):
    """The dummy alone at frame f as an (h, w, 4) uint8 frame."""
    H, W = shape
    dx, dy, tilt, flash = reaction(f, hits, fps)
    s = -facing  # pushed away from the blow
    bx, by = foot[0] + s * dx, foot[1] + dy
    ys, xs = np.mgrid[0:H, 0:W] + 0.5
    a = -s * tilt  # tilt the top away from the blow
    u = (xs - bx) * math.cos(a) + (ys - by) * math.sin(a)   # across
    v = -(xs - bx) * math.sin(a) + (ys - by) * math.cos(a)  # up is negative
    k = height / HEIGHT
    post = (np.abs(u) < 1.6 * k) & (v < 0) & (v > -height)
    base = (np.abs(u) < 5 * k) & (v < 0) & (v > -2.5 * k)
    arm = (np.abs(v + 25 * k) < 1.4 * k) & (np.abs(u) < 10 * k)
    body = ((u / (7.5 * k)) ** 2 + ((v + 19 * k) / (10 * k)) ** 2) < 1
    head = (u ** 2 + (v + 33 * k) ** 2) < (4.6 * k) ** 2
    rope = body & ((np.abs(v + 14 * k) < 0.7 * k) | (np.abs(v + 24 * k) < 0.7 * k))
    img = np.zeros((H, W, 4), np.uint8)
    lit = (u < -0.3 * k) & (v < -20 * k)

    def paint(mask, ramp, light_side=True):
        tone = np.where(lit & light_side, 2, np.where(u > 2 * k, 0, 1))
        for t in range(3):
            sel = mask & (tone == t)
            img[sel] = (*_hex(ramp[t]), 255)

    paint(post | base | arm, POST)
    paint(body | head, STRAW)
    img[rope] = (*_hex(ROPE), 255)
    if flash:
        on = img[..., 3] > 0
        img[on, :3] = (img[on, :3] * (1 - 0.7 * flash) + np.array(FLASH) * 0.7 * flash).astype(np.uint8)
    return img


def under(effect, dummy):
    """effect (h, w, 4) uint8 over the dummy: the blow reads in front of the body it hits."""
    a = effect[..., 3:4] / 255.0
    b = dummy[..., 3:4] / 255.0
    alpha = a + b * (1 - a)
    rgb = (effect[..., :3] * a + dummy[..., :3] * b * (1 - a)) / np.maximum(alpha, 1e-6)
    return np.concatenate([rgb, alpha * 255], -1).round().astype(np.uint8)
