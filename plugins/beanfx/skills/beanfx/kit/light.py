"""The light pass of an effect: an additive glow drawn on its own sheet `<name>_light`, which the engine adds over
the colour sheet at the same frame and row (or drops). Learnt from the pixelfx light buffer (a falloff
(1 - d)^2 * k summed per pixel). Smooth light is the default in every style; `bands` cuts it into three hard steps only when the owner
asks for stepped light ("NES authentic", "no smooth glow"), so that sheet keeps hard alpha and stepped tones.

    L = buffer(c)                          # c: a canvas with world px grids x, y (wgrid)
    glow(L, c, x, y, r, k)                 # a round light, k at the centre
    glow_line(L, c, (x0, y0), (x1, y1), r, k)   # light round a segment: beams, bolts, trails
    glow_ring(L, c, x, y, R, r, k, flat)   # light hugging a ring: shock waves, ground seals
    m = bands(L, phase)                    # stepped light on request only: shade map 0 outer (dithered), 1 middle, 2 inner, -1 none
    cols = palette("#ff9a40")              # the three colours of those bands

    fl = Flashes()                         # short lights: a spark landing, a sword entering the cloud, a hit
    fl.add(x, y, r, k, life=6)             # life in frames; it starts at k and r, dims as (life left)^2, shrinks
    fl.draw(L, c); fl.step()               # each frame: draw, then age by one frame
    flash_at(L, c, f, f0, x, y, r, k, life)  # the same flash born at frame f0, drawn from f alone: pure, so
                                           # render(f, seed) stays per frame for check_seeds
    k * flicker(i, f, seed)                # 0..1 per spark i at frame f, seeded and out of step: the twinkle

Keep k at 0.2 to 0.5; light the hot core, eyes, bolt heads, the landing flash and embers, never the whole body.
Light that lives a few frames reads as sparkle; light that stays reads as haze.
"""
import math

import numpy as np

from fxlib import checker

LEVELS = (0.3, 0.55, 0.8)  # outer, middle and inner band of the hard steps
CUTS = (0.08, 0.2, 0.4)  # summed light where the outer, middle and inner band begin


def buffer(c):
    return np.zeros(c.x.shape)


def glow(L, c, x, y, r, k=0.4):
    d = np.hypot(c.x - x, c.y - y) / r
    L += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)


def glow_line(L, c, p0, p1, r, k=0.4):
    (ax, ay), (bx, by) = p0, p1
    ex, ey = bx - ax, by - ay
    h = np.clip(((c.x - ax) * ex + (c.y - ay) * ey) / (ex * ex + ey * ey or 1e-9), 0, 1)
    d = np.hypot(c.x - ax - ex * h, c.y - ay - ey * h) / r
    L += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)


def glow_ring(L, c, x, y, R, r, k=0.4, flat=1.0):
    d = np.abs(np.hypot(c.x - x, (c.y - y) / flat) - R) / r
    L += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)


def bands(L, phase=0):
    """The summed light as a shade map in three hard bands; the outer band is a checker so it fades by dither."""
    m = np.full(L.shape, -1, np.int8)
    ys, xs = np.mgrid[0:L.shape[0], 0:L.shape[1]]
    m[(L >= CUTS[0]) & checker(xs, ys, phase)] = 0
    m[L >= CUTS[1]] = 1
    m[L >= CUTS[2]] = 2
    return m


def palette(hue):
    """The light sheet's three colours: hue scaled by each band level (added, so darker means fainter)."""
    r, g, b = (int(hue[i:i + 2], 16) for i in (1, 3, 5))
    return ["#%02x%02x%02x" % (round(r * v), round(g * v), round(b * v)) for v in LEVELS]


class Flashes:
    """Lights that flare and die: each starts at k and radius r, dims as (life left / life) squared and shrinks to
    0.55 r, and is gone after life frames. Deterministic: add them from seeded choices."""

    def __init__(self):
        self.list = []

    def add(self, x, y, r, k, life=6):
        self.list.append([x, y, r, k, float(life), float(life)])

    def draw(self, L, c):
        for x, y, r, k, left, life in self.list:
            _flash(L, c, x, y, r, k, left / life)

    def step(self):
        for fl in self.list:
            fl[4] -= 1
        self.list = [fl for fl in self.list if fl[4] > 0]


def _flash(L, c, x, y, r, k, u):
    glow(L, c, x, y, r * (0.55 + 0.45 * u), k * u * u)


def flash_at(L, c, f, f0, x, y, r, k, life=6):
    """A Flashes light born at frame f0, drawn at frame f with no state: the same k, shrink and life. Use it in a
    render(f, seed) that computes each frame on its own."""
    age = f - f0
    if 0 <= age < life:
        _flash(L, c, x, y, r, k, (life - age) / life)


def _hash01(*n):
    h = 0x9E3779B97F4A7C15
    for v in n:
        h = ((h ^ (int(v) & 0xFFFFFFFF)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        h ^= h >> 31
    return (h & 0xFFFFFF) / 0xFFFFFF


def flicker(i, f, seed=0, rate=1.0):
    """Twinkle 0..1 for spark i at frame f: a fast wave with its own phase and speed plus a seeded jitter, so
    sparks blink out of step. rate 0 holds each spark still; 1 is a full twinkle. Multiply a spark's k by it."""
    ph = math.tau * _hash01(seed, i, 1)
    sp = 1.2 + 1.8 * _hash01(seed, i, 2)
    v = 0.5 + 0.5 * math.sin(ph + f * sp * rate)
    return min(1.0, max(0.0, v * (1 - 0.4 * rate) + 0.4 * rate * _hash01(seed, i, f, 3)))
