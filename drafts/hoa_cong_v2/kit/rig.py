"""A game character as the caster: the owner's own sprite sheets, read through a rig.json.

The effect is drawn in the character's frame space: the effect's pivot is the character's pivot (the feet), its
frame k plays with the character's frame `start + k` at the character's fps, and a top-down effect has one row per
direction of the character. The sheet stays the effect alone; the character goes into the previews only, and the
JSON tells the engine which animation and frame the effect rides on (meta.beanfx.caster).

The sprites are the owner's licensed art and stay local: `casters/<name>/` in the project (gitignored), never
in the plugin. A later character that keeps the same rig.json (frame size, pivot, animations, frame counts,
contact frames, directions) works with every effect drawn on the first one.

casters/<name>/rig.json:
    {"name": "knight_side", "view": "side", "facing": "east", "fps": 10,
     "anims": {"attack1": {"frame": [96, 80], "frames": 8, "sheet": "attack01.png", "pivot": [50, 64],
                           "contact": [1, 5]}}}
    top-down: "view": "top-down", "directions": ["east", "south", "west", "north"] (or the 8 of facing.NAMES8),
    and each animation gives "sheets": {"east": "attack1_right.png", ...} in place of "sheet".
    side with its own west row (an asymmetric character, such as a sword in the right hand): "view": "side",
    "directions": ["east", "west"] and "sheets" by direction; the engine then picks the row and never mirrors.
Each animation may carry its own "fps" (a game row's rate), else the rig's "fps" holds.
Optional: "pixel_scale" (sheet pixels per art pixel, 1 for native art), "height" (the character's height in art
pixels), and per animation "swing": the sword strokes as [{"kind": "slash", "turn": "cw" | "ccw", "from": deg,
"to": deg, "sweep": deg, "frames": [...]}] in screen degrees (0 east, 90 south, y down), on top-down a dict of
those lists by direction. An effect's slash follows the stroke: same turn, from and to. "root" (with "move":
"root"): the body's travel per frame as [dx, dy] px from where the animation starts (a dict by direction on
top-down), for animations whose frames stay in place while the character moves, such as a dash; the engine moves
the character by it, and an effect on such an animation stays where the move began (place(travel=True) previews
that).
Also optional per animation, read by the engine and the effect author (rig.py passes them through untouched):
"thrust": [{"kind": "thrust", "frames": [...], "from": [dx, dy], "to": [dx, dy], "angle": deg}] the blade point
travelling from and to (px from the pivot) for a stab; "emit": {"frames": [...], "point": [dx, dy]} (a dict of
points by direction on top-down) where a cast art leaves the body; "hit": [frame] the frame a blow lands on a
hurt animation.
A missing pivot is measured from the sheet (`measure`): the centre of the feet in frame 0, on the lowest row any
frame reaches.
"""
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image

import facing

VIEWS = ("side", "top-down")
DIRS4 = ["east", "south", "west", "north"]  # export.row_names(4) and facing rows, in order


def project_root(start=None):
    """BEANFX_PROJECT, else the nearest folder up from start (cwd) holding casters/, else the git root."""
    if os.environ.get("BEANFX_PROJECT"):
        return Path(os.environ["BEANFX_PROJECT"])
    p = Path(start or Path.cwd()).resolve()
    for d in (p, *p.parents):
        if (d / "casters").is_dir() or (d / ".git").exists():
            return d
    return p


def _cells(path, w, h, n):
    img = np.array(Image.open(path).convert("RGBA"))
    if img.shape[0] < h or img.shape[1] < w * n:
        raise ValueError(f"{path.name}: {img.shape[1]}x{img.shape[0]} holds fewer than {n} frames of {w}x{h}")
    return [img[:h, k * w:(k + 1) * w].copy() for k in range(n)]


def measure(frames):
    """The feet on frame 0 (the neutral pose; later frames carry smears and lunges): y the row under its lowest
    pixel (pixel edges, so the sprite stands on y), x the mean of the opaque pixels in the legs (its lowest
    quarter), which stays on the body in a stride where the feet spread."""
    a = frames[0][..., 3] > 0
    rows = np.nonzero(a.any(1))[0]
    top, low = int(rows.min()), int(rows.max())
    legs = a[low - max((low - top) // 4, 1) + 1:low + 1]
    xs = np.nonzero(legs)[1]
    return [int(round(xs.mean() + 0.5)), low + 1]


class Rig:
    def __init__(self, folder):
        self.dir = Path(folder)
        self.spec = json.loads((self.dir / "rig.json").read_text())
        self.name = self.spec.get("name", self.dir.name)
        self.view = self.spec["view"]
        if self.view not in VIEWS:
            raise ValueError(f"view {self.view!r} not in {VIEWS}")
        self.fps = self.spec["fps"]
        self.directions = self.spec.get("directions", [self.spec.get("facing", "east")])
        self._cache = {}

    @property
    def anims(self):
        return list(self.spec["anims"])

    def anim(self, name):
        if name not in self.spec["anims"]:
            raise KeyError(f"{self.name} has no animation {name!r}; it has {self.anims}")
        return self.spec["anims"][name]

    def frames(self, anim, direction=None):
        """The character's frames (h, w, 4) uint8 for one animation and direction (top-down)."""
        a = self.anim(anim)
        d = direction or self.directions[0]
        key = (anim, d)
        if key not in self._cache:
            sheet = a["sheets"][d] if "sheets" in a else a["sheet"]
            w, h = a["frame"]
            self._cache[key] = _cells(self.dir / sheet, w, h, a["frames"])
        return self._cache[key]

    def fps_of(self, anim):
        """The animation's own fps (rig.json anims.<name>.fps), else the rig's."""
        return self.anim(anim).get("fps", self.fps)

    def pivot(self, anim):
        a = self.anim(anim)
        return list(a["pivot"]) if "pivot" in a else measure(self.frames(anim))

    def contact(self, anim):
        return list(self.anim(anim).get("contact", []))

    def swing(self, anim, direction=None):
        """The sword strokes of an animation (for one direction on top-down); [] when rig.json gives none."""
        s = self.anim(anim).get("swing", [])
        if isinstance(s, dict):
            s = s.get(direction or self.directions[0], [])
        return [dict(x) for x in s]

    def root(self, anim, direction=None):
        """[dx, dy] per frame: how far the body has moved from the animation's start; zeros when it stays put."""
        a = self.anim(anim)
        r = a.get("root")
        if isinstance(r, dict):
            r = r.get(direction or self.directions[0])
        return [list(x) for x in r] if r else [[0, 0] for _ in range(a["frames"])]

    def arc(self, anim, direction=None, stroke=0):
        """(a0, a1) in degrees for an effect arc that runs with the blade: a0 the stroke's `from`, a1 = a0 + sweep,
        so a1 - a0 carries the turn (positive cw on screen, y down)."""
        s = self._stroke(anim, direction, stroke)
        return float(s["from"]), float(s["from"] + s["sweep"])

    def check_arc(self, anim, a0, a1, direction=None, stroke=0, tol=60):
        """Problems when an effect arc a0 to a1 (degrees, the sign of a1 - a0 is its turn) leaves the blade's stroke:
        the wrong turn, or an end more than tol degrees from the stroke's from or to. [] when it follows it."""
        s = self._stroke(anim, direction, stroke)
        where = f"{self.name} {anim}{' ' + direction if direction else ''} stroke {stroke}"
        bad = []
        turn = "cw" if a1 > a0 else "ccw"
        if turn != s["turn"]:
            bad.append(f"{where}: arc turns {turn}, the blade turns {s['turn']}")
        for label, got, want in (("start", a0, s["from"]), ("end", a1, s["to"])):
            off = abs((got - want + 180) % 360 - 180)
            if off > tol:
                bad.append(f"{where}: arc {label} {got:.0f} is {off:.0f} deg from the blade's {want}")
        return bad

    def _stroke(self, anim, direction, stroke):
        strokes = self.swing(anim, direction)
        if not strokes:
            raise KeyError(f"{self.name} {anim} has no swing in rig.json")
        return strokes[stroke]

    def frame_at(self, anim, k, direction=None, start=0, hold=True):
        """The character's frame for effect frame k, or None after the animation ends (hold keeps the last)."""
        fr = self.frames(anim, direction)
        i = start + k
        if i < len(fr):
            return fr[max(i, 0)]
        return fr[-1] if hold else None

    def place(self, shape, pivot, anim, k, direction=None, start=0, hold=True, travel=False):
        """The character on an empty canvas of shape (H, W), its pivot on the canvas point pivot; travel=True adds
        the animation's root motion, so pivot is where the move began."""
        H, W = shape
        out = np.zeros((H, W, 4), np.uint8)
        fr = self.frame_at(anim, k, direction, start, hold)
        if fr is None:
            return out
        px, py = self.pivot(anim)
        if travel:
            n = len(self.frames(anim, direction))
            dx, dy = self.root(anim, direction)[min(max(start + k, 0), n - 1)]
            pivot = (pivot[0] + dx, pivot[1] + dy)
        ox, oy = int(round(pivot[0] - px)), int(round(pivot[1] - py))
        h, w = fr.shape[:2]
        y0, y1, x0, x1 = max(oy, 0), min(oy + h, H), max(ox, 0), min(ox + w, W)
        if y0 < y1 and x0 < x1:
            out[y0:y1, x0:x1] = fr[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
        return out

    def meta(self, anim, effect_fps, start=0, layer="front", directions=None, offset=None):
        """meta.beanfx.caster: what the effect rides on. The engine puts the effect pivot on the character's
        pivot, starts it when the character shows frame `start` of `anim`, and draws it in front of (or behind)
        the character. effect_fps must be a whole multiple of the character's fps so the frames stay locked."""
        char_fps = self.fps_of(anim)
        ratio = effect_fps / char_fps
        if abs(ratio - round(ratio)) > 1e-6 or round(ratio) < 1:
            raise ValueError(f"effect fps {effect_fps} is not a whole multiple of {anim}'s {char_fps}")
        if layer not in ("front", "behind"):
            raise ValueError("layer front or behind")
        a = self.anim(anim)
        m = dict(rig=self.name, view=self.view, anim=anim, start=start, char_fps=char_fps,
                 frames_per_char_frame=int(round(ratio)), char_frames=a["frames"], char_frame=list(a["frame"]),
                 char_pivot=self.pivot(anim), contact=self.contact(anim), layer=layer,
                 align="effect pivot on the character's pivot; mirror both together")
        if "ms" in a:  # a game row with uneven frame times: the engine holds effect frames by these, not by fps
            m["char_ms"] = list(a["ms"])
        if "pixel_scale" in self.spec:
            m["pixel_scale"] = self.spec["pixel_scale"]
        if offset:  # the cast lands offset px in front of the character (knobs/placement.md)
            dirs = list(directions or self.directions) if self.view == "top-down" else None
            m["range"] = offset
            m["offset"] = facing.offset(offset, dirs)
            m["align"] = "effect pivot on the character's pivot plus offset[direction]; mirror both together"
        if self.view == "top-down" or len(self.directions) > 1:
            m["directions"] = list(directions or self.directions)
            if "swing" in a:
                m["swing"] = {d: self.swing(anim, d) for d in m["directions"]}
        elif "swing" in a:
            m["swing"] = self.swing(anim)
        if "root" in a:
            m["root"] = ({d: self.root(anim, d) for d in m["directions"]} if "directions" in m
                         else self.root(anim))
            m["anchor"] = "start: the effect stays where the move began; the character travels by root"
        return m


def load(name, root=None):
    """A folder path, else casters/<name>/ in the project, else the casters that ship with the skill (its
    casters/: nghich_tien_kiem, _kiem_topdown, _truong, _truong_topdown)."""
    p = Path(name)
    if (p / "rig.json").exists():
        return Rig(p)
    p = project_root(root) / "casters" / name
    if (p / "rig.json").exists():
        return Rig(p)
    import export
    skill = export.skill_dir(Path(__file__).resolve().parent)
    if skill and (skill / "casters" / name / "rig.json").exists():
        return Rig(skill / "casters" / name)
    raise FileNotFoundError(f"no rig.json for {name} in {p.parent} or the skill's casters/; the owner's character "
                            "sheets go in casters/<name>/")



def over(effect, char):
    """effect (h, w, 4) uint8 in front of the character (both straight alpha)."""
    a = effect[..., 3:4] / 255.0
    b = char[..., 3:4] / 255.0
    alpha = a + b * (1 - a)
    rgb = (effect[..., :3] * a + char[..., :3] * b * (1 - a)) / np.maximum(alpha, 1e-6)
    return np.concatenate([rgb, alpha * 255], -1).round().astype(np.uint8)


if __name__ == "__main__":
    import sys
    r = load(sys.argv[1])
    for an in r.anims:
        for d in (r.directions if r.view == "top-down" or len(r.directions) > 1 else [None]):
            print(an, d or "", "pivot", measure(r.frames(an, d)), "set", r.pivot(an), "contact", r.contact(an),
                  "swing", [(s["turn"], s["from"], s["to"], s["frames"]) for s in r.swing(an, d)])
