"""Directions for a general-mode sheet: what a game needs to play one effect from any side or heading.

A sheet is drawn facing one way and the JSON says how the engine gets the other ways:

    side view, 1 direction:   drawn facing east; the engine flips it for west and uses mirror_pivot and
                              mirror_target (x becomes w - x). When the drawing is not symmetric under a flip
                              (text, a light from one side), mirror is False and a second sheet faces west.
    top-down or 3/4, n rows:  row k faces tau * k / n radians, y down: 0 east, n/4 south, n/2 west, 3n/4 north.
                              The engine picks row = round(atan2(dy, dx) / tau * n) mod n. Never rotated at runtime.

    import facing as fc
    rows = fc.rows(lambda a, f: draw(a, f), 8, N)          # rows[k][f] (h, w, 4) uint8
    ex.write(OUT, NAME, rows, FPS, PIVOT, LOOP, extra=...)  # export.py: heading k after k - 1, a tag per row
    meta.update(fc.meta("top-down", W, H, PIVOT, directions=8))
    meta.update(fc.meta("side", W, H, PIVOT, target=TGT))   # facing east, mirror True
    west = fc.mirror(frames)                                # the flipped sheet when mirror is False

An effect that goes from a caster to a target is exported as parts, so the engine places each at the real spot
and the distance is not baked in: cast (at the caster's pivot), travel (a loop the engine moves at speed px/s,
with its own direction rows) and impact (at the target's pivot). fc.part builds each entry, fc.check validates.
"""
import math
from pathlib import Path

import numpy as np
from PIL import Image

TAU = math.tau
VIEWS = ("side", "top-down", "3/4")
NAMES8 = ("east", "south-east", "south", "south-west", "west", "north-west", "north", "north-east")


def headings(n):
    """The angle of each row, radians, y down: row 0 east, n/4 south."""
    return [TAU * k / n for k in range(n)]


def row_of(dx, dy, n):
    """The row an engine plays for a move of (dx, dy), y down."""
    return round(math.atan2(dy, dx) / TAU * n) % n


def rows(draw, n, frames):
    """rows[k][f] = draw(a, f) for each heading a; draw returns an (h, w, 4) uint8 frame."""
    return [[draw(a, f) for f in range(frames)] for a in headings(n)]


def sheet(rows, path):
    """One row per heading, frames left to right."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img = np.concatenate([np.concatenate(list(r), axis=1) for r in rows], axis=0)
    Image.fromarray(img, "RGBA").save(path)


def mirror(frames):
    """The frames flipped left to right (the west-facing copy of an east-facing side sheet)."""
    return [np.ascontiguousarray(f[:, ::-1]) for f in frames]


def flip(p, w):
    """A point in the flipped sheet: x becomes w - x (pixel edges, so a centred pivot stays put)."""
    return [w - p[0], p[1]]


def meta(view, w, h, pivot, directions=1, facing="east", mirror=True, target=None):
    """The direction fields of the sheet's JSON."""
    if view not in VIEWS:
        raise ValueError(f"view {view!r} not in {VIEWS}")
    m = dict(view=view, directions=directions)
    if directions == 1:
        m.update(facing=facing, mirror=mirror)
        if mirror:
            m["mirror_pivot"] = flip(pivot, w)
            if target is not None:
                m["mirror_target"] = flip(target, w)
    else:
        m["row_rule"] = "row k faces tau * k / n, y down: 0 east, n/4 south, n/2 west, 3n/4 north"
        m["row_of"] = "round(atan2(dy, dx) / tau * n) mod n"
        if directions == 8:
            m["row_names"] = list(NAMES8)
    return m


def offset(rng, directions=None):
    """Where a cast lands: the [dx, dy] from the caster's pivot to the effect's pivot, rng px along the facing
    (screen px, y down). directions: names from NAMES8 (one pair each), or None for a side view (one pair facing
    east; the engine flips dx with the mirror)."""
    def at(name):
        a = math.tau * NAMES8.index(name) / 8
        return [round(rng * math.cos(a)), round(rng * math.sin(a))]
    return at("east") if directions is None else {d: at(d) for d in directions}


def part(sheet_file, w, h, frames, fps, pivot, loop, anchor, **extra):
    """One part of a split effect. anchor: caster, target or travel; a travel part also gives speed (px/s)."""
    return dict(sheet=sheet_file, w=w, h=h, frames=frames, fps=fps, pivot=list(pivot), loop=loop, anchor=anchor,
                **extra)


def check(m):
    """Raise ValueError when the direction fields do not hold together; return m."""
    for k in ("view", "directions"):
        if k not in m:
            raise ValueError(f"missing {k}")
    if m["directions"] == 1:
        if m.get("facing") not in ("east", "west"):
            raise ValueError("a 1-direction sheet needs facing east or west")
        if m.get("mirror") and "mirror_pivot" not in m:
            raise ValueError("mirror True needs mirror_pivot")
        if not m.get("mirror") and "west" not in m.get("sheets", {}):
            raise ValueError("mirror False needs a west sheet in sheets")
    elif m["directions"] not in (4, 8, 16):
        raise ValueError("directions is 1, 4, 8 or 16")
    for name, p in m.get("parts", {}).items():
        if p.get("anchor") not in ("caster", "target", "travel"):
            raise ValueError(f"part {name}: anchor caster, target or travel")
        if p["anchor"] == "travel" and not p.get("speed"):
            raise ValueError(f"part {name}: a travel part needs speed px/s")
        if "view" in p:
            check(p)
    return m
