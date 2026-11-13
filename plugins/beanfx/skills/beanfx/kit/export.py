"""Export and check a finished effect: a sprite sheet grid with Aseprite-style JSON that engines import, and the
checks that catch what eyes miss.

    import export as ex
    bad = ex.check(frames, lights, loop=False, src=__file__)       # list of problems, empty when clean
                                                                    # (trim=None, max_mb=None switch two of them off)
    bad += ex.check_seeds(lambda f, sd: render(f, sd)[0], N)       # the same with seeds 2, 3 and 7
    bad += ex.check_act(meta["meta"]["beanfx"].get("act", {}), N, FPS)
    gif = ex.hitstop(previews, hits, FPS)                           # previews hold each freeze, for the gif
    meta = ex.write(OUT, NAME, frames, FPS, PIVOT, loop=False,
                    light=lights, color=cols,                       # optional: the additive light, colour only
                    states={"charge": [0, 14], "strike": [15, 36]}, # optional: frame tags
                    hits=[ex.hit(16, FPS, freeze=0.12, shake=3)],   # optional: contact frames for a hit-stop
                    poses=[ex.pose(-0.25, "windup"), ex.pose(0.5, "release", "snap"), ex.pose(1.2, "recover")],
                    target={"x": 60, "react": "knockback"},         # optional: the act around the effect
                    extra=fc.meta("side", W, H, PIVOT))             # direction fields and anything else

frames is a list of (h, w, 4) uint8 frames, or a list of rows (one per heading) of such lists. Frames sit in a
grid, row-major, `columns` across (default: near square); past MAX_EDGE the sheet splits into pages. The JSON is the Aseprite
"array" layout: `frames[i]` has `filename`, `frame` {x, y, w, h}, `duration` in ms, and `meta.frameTags` names
each state (and each heading row). Phaser reads it with `load.aseprite`; other engines slice the grid by
`meta.beanfx.frameSize` and `columns`. Everything beanfx adds lives in `meta.beanfx`.

The work (sheets, JSON, checks, hit-stop, the preview page) runs in the beanfx binary (the skill's rust/, through
bridge.py); this module keeps the authoring helpers and the constants, which come from the binary's table.
"""
import math
from pathlib import Path

import numpy as np

import bridge


def _call(cmd, args=None, arrays=None):
    try:
        return bridge.run("export", cmd, args, arrays)
    except bridge.BeanfxError as e:  # the errors write() and friends raised as ValueError
        pre = f"beanfx export {cmd}: "
        msg = str(e)
        if msg.startswith(pre):
            raise ValueError(msg[len(pre):]) from None
        raise


_C = _call("consts")
MAX_EDGE = _C["MAX_EDGE"]  # a texture side most GPUs and WebGL2 phones take
VRAM_NOTE = _C["VRAM_NOTE"]  # bytes of decoded sheets above which write() prints a texture memory note
BUDGET_MB = _C["BUDGET_MB"]  # check() fails past this: one full MAX_EDGE page each for the colour and the light sheet
TRIM = _C["TRIM"]  # check() fails when cutting the lopsided margins off the cell would save more than this share of it
FILL_MASS = _C["FILL_MASS"]  # the share of the colour (pixels over all frames) the framing box holds, 2 % cut from each end
LIGHT_EDGE = _C["LIGHT_EDGE"]  # light below this may reach the cell edge (a smooth pool fades past it)
POP = _C["POP"]  # the last frame of a one-shot may keep at most this share of the peak frame's pixels
POSES = tuple(_C["POSES"])
REACTS = tuple(_C["REACTS"])

# Weight classes for a contact, after fighting-game and action-game practice (vfx_notes.md, Missing choices 1 to 3):
# a stronger hit freezes longer, shakes harder and longer, pushes further and flashes the target longer.
# freeze and shake_time in s, shake and push in px, flash in s the target shows white.
WEIGHTS = _C["WEIGHTS"]


def _rows(frames):
    return frames if isinstance(frames[0], (list, tuple)) else [frames]


def _flat(frames):
    return [f for r in _rows(frames) for f in r]


def hit(frame, fps, freeze=None, shake=None, push=None, react=None, weight=None, dir=None, shake_time=None,
        flash=None, sound=None):
    """One contact: the sheet frame it lands on, its time in s, and how long the game freezes everything (hit-stop,
    0.06 to 0.2 s), how far it shakes the camera (px), pushes the target (px) and how the target reacts (REACTS).

    weight (WEIGHTS: light, heavy, finisher, blast) fills every field the call leaves out, so one word sets a hit
    that feels as heavy as it looks. dir is the way the blow travels in degrees, y down, 0 along the facing (east):
    the camera shakes along it and the target is pushed along it; a flipped sprite mirrors it to 180 - dir.
    shake_time is how long the shake lasts, flash how long the target shows white, sound the cue name the game maps
    to a sound and plays at t (default hit_<weight>)."""
    w = WEIGHTS[weight] if weight else {}
    pick = lambda v, k, d: v if v is not None else w.get(k, d)  # noqa: E731
    h = dict(frame=frame, t=round(frame / fps, 4), freeze=pick(freeze, "freeze", 0.1), shake=pick(shake, "shake", 0),
             push=pick(push, "push", 0), react=pick(react, "react", "flinch"))
    if weight:
        h["weight"] = weight
    for k, v in (("dir", dir), ("shake_time", pick(shake_time, "shake_time", None)), ("flash", pick(flash, "flash", None)),
                 ("sound", sound or (f"hit_{weight}" if weight else None))):
        if v is not None:
            h[k] = v
    return h


def pose(t, name, how="smooth"):
    """A key for the game's own character: at t s from frame 0 (negative before it) it reaches pose name (POSES);
    how "snap" jumps to it on the key, "smooth" eases from the last key."""
    return dict(t=t, pose=name, how=how)


def act(hits=None, windup=0.0, poses=None, target=None):
    """The body around the effect, as plain data: windup (s the character starts before frame 0; from the first pose
    key when poses start earlier), hits, poses and target {x: px from the pivot along the facing, react}."""
    poses = list(poses or [])
    if poses and poses[0]["t"] < 0:
        windup = max(windup, -poses[0]["t"])
    a = {"windup": round(windup, 4), "hits": list(hits or [])}
    if poses:
        a["poses"] = poses
    if target:
        a["target"] = dict(target)
    return a


def check_act(a, frames, fps, loop=False):
    """The problems of an act: hits outside the sheet or frozen too long, pose keys out of order or unknown,
    a loop whose poses do not close."""
    return _call("check_act", {"act": a, "frames": frames, "fps": fps, "loop": loop})


def hitstop(frames, hits, fps):
    """Preview frames with each hit's freeze held on its contact frame and the camera shake applied along the blow
    (`dir`) for `shake_time` (default: the freeze), so a gif shows the hit-stop and shake the game will add. For
    previews only; the sheet keeps one frame per step."""
    if not hits or not len(frames):
        return list(frames)
    _, arrs = bridge.run("export", "hitstop", {"hits": hits, "fps": fps}, {"frames": bridge.stack(frames)},
                         want_arrays=True)
    return list(arrs["frames"])


def grid(n, w, h, columns=None):
    """Columns and rows of the sheet grid for n frames of w x h: near square unless columns is given."""
    return tuple(_call("grid", {"n": n, "w": w, "h": h, "columns": columns}))


def write(out, name, frames, fps, pivot, loop, light=None, color=None, states=None, hits=None, windup=0.0,
          poses=None, target=None, columns=None, extra=None, hold=False):
    """Writes <name>.png (colour plus light), <name>_light.png and <name>_color.png when given (same grid), and
    <name>.json. Returns the JSON. hold: a one-shot that ends on a held state (an eye that stays open, a seal that
    stays); `end` tells the engine to keep the last frame (or hand over to a loop) instead of removing it.

    A sheet that would pass MAX_EDGE splits into pages <name>_p<k>.png (each with its own Aseprite JSON
    <name>_p<k>.json holding its frames and the tags clipped to it); <name>.json then lists every frame with its
    `page` and the page files in meta.beanfx.pages. Frame filenames are unique across pages."""
    args = dict(out=str(out), name=name, fps=fps, pivot=list(pivot), loop=loop, states=states, hits=hits, windup=windup,
                poses=poses, target=target, columns=columns, extra=extra, hold=hold, max_edge=MAX_EDGE,
                vram_note=VRAM_NOTE)
    arrays = {"frames": bridge.stack(frames)}
    if light is not None:
        arrays["light"] = _light(light)
    if color is not None:
        arrays["color"] = bridge.stack(color)
    return _call("write", args, arrays)


def _light(light):
    """The light frames stacked: all uint8 stay uint8; otherwise every frame as floats 0..1 (uint8 / 255, bool 0 or 1),
    the way the Python kit read each frame."""
    rows = _rows(light)
    if all(np.asarray(f).dtype == np.uint8 for r in rows for f in r):
        return bridge.stack(light)
    f64 = lambda f: np.asarray(f, float) / 255.0 if np.asarray(f).dtype == np.uint8 else np.asarray(f, float)  # noqa: E731
    nested = isinstance(light[0], (list, tuple))
    return bridge.stack([[f64(f) for f in r] for r in rows] if nested else [f64(f) for f in light])


def check_seeds(render, frames, seeds=(2, 3, 7), step=2):
    """Edge and empty-frame problems with other seeds: render(f, seed) returns the colour frame (h, w, 4) of frame f
    drawn with that seed. Particles that a reseed throws further show up here."""
    labels, alpha = [], []
    for sd in seeds:
        for f in range(0, frames, step):
            labels.append([sd, f])
            alpha.append((np.asarray(render(f, sd))[..., 3] > 0).astype(np.uint8))
    if not labels:
        return []
    return _call("edges", {"labels": labels}, {"alpha": np.stack(alpha)})


def colours(frame):
    """The number of distinct colours in one RGBA frame, fully transparent pixels left out: the pixel-art read. Hand
    pixel effects keep to a few dozen; smooth light pushes a frame into the hundreds."""
    return _call("colours", None, {"frame": np.asarray(frame)})


def memory_mb(frames, light=None):
    """Decoded texture memory of the sheets in MB (1e6 bytes): frames x w x h x 4 bytes, twice that when the light
    ships as its own sheet next to the colour."""
    flat = _flat(frames)
    h, w = flat[0].shape[:2]
    return _call("memory_mb", {"n": len(flat), "w": w, "h": h, "light": light is not None})


def framing(frames):
    """Where the drawing sits in its cell. box (x0, y0, x1, y1, inclusive) holds FILL_MASS of the colour, counted
    as pixels over every frame and row with the outer 2 % cut from each end of both axes, so a few arrows or
    sparks that cross the cell do not count as using it. cut is the px that could come off the (left, top, right,
    bottom) to leave the box with the same margin on both sides of each axis, and trim the share of the cell those
    cuts save: near 0 for a centred drawing however small, high when the subject sits in one corner and the rest
    of every frame ships empty. None when no frame has colour."""
    r = _call("framing", None, {"frames": bridge.stack(frames)})
    if r is None:
        return None
    return dict(box=tuple(r["box"]), cell=tuple(r["cell"]), cut=tuple(r["cut"]), trim=r["trim"])


def check(frames, light=None, loop=False, src=None, hold=False, max_colours=None, trim=TRIM, max_mb=BUDGET_MB):
    """The problems of a finished effect, one line each: colour or light on the cell edge, an empty frame, a
    one-shot that pops off (its last frame keeps more than POP of the peak; hold skips it), a loop seam (the last to first step
    changes more than twice a normal step), randomness without a seed in the draft source src, and, when max_colours
    is given, a frame with more distinct colours than that (frames are the composited finals).

    Two more look at the whole sheet. Framing: the drawing sits to one side of its cell, so cutting the lopsided
    margins (`framing`) would save more than trim of the sheet; move the subject or trim the cell (trim=None when
    the space is wanted, such as the run-in of a projectile). Budget: the sheets decode to more than max_mb of
    texture memory (`memory_mb`); cut frames, the cell or split the effect into parts (max_mb=None, or a higher
    number, when the owner accepts the size, such as a full-screen cutscene)."""
    args = dict(loop=loop, hold=hold, max_colours=max_colours, trim=trim, max_mb=max_mb,
                src=str(src) if src is not None else None)
    arrays = {"frames": bridge.stack(frames)}
    if light is not None:
        arrays["light"] = _light(light)
    return _call("check", args, arrays)


def row_names(n):
    if n == 1:
        return [""]
    if n == 8:
        return ["east", "south-east", "south", "south-west", "west", "north-west", "north", "north-east"]
    if n == 4:
        return ["east", "south", "west", "north"]
    return [f"dir{k}" for k in range(n)]


def skill_dir(kit_dir=None):
    """The skill folder: BEANFX_SKILL, else the path setup.sh --draft wrote to kit/skill.txt, else the skill this
    kit sits in (its own kit/). None when none holds tools/preview.html."""
    import os
    kit_dir = Path(kit_dir) if kit_dir else Path(__file__).resolve().parent
    tries = []
    if os.environ.get("BEANFX_SKILL"):
        tries.append(Path(os.environ["BEANFX_SKILL"]))
    note = kit_dir / "skill.txt"
    if note.exists():
        tries.append(Path(note.read_text().strip()))
    tries.append(kit_dir.parent)
    for t in tries:
        if (t / "tools" / "preview.html").exists():
            return t
    return None


def _skill_page(kit_dir):
    """tools/preview.html of the skill (skill_dir)."""
    s = skill_dir(kit_dir)
    return s / "tools" / "preview.html" if s else None


def page(json_path, out=None, template=None, project=None):
    """A preview page for one result: <out>/<name>.html (out defaults to the draft's out/), the skill's
    tools/preview.html with this result's JSON and sheets embedded, and its game character's rig.json and the
    sheets of the animations it rides on when meta.beanfx.caster names one. It opens from disk with no server and
    no folder to pick. The character sprites are the owner's licensed art, so the page stays in out/ (gitignored)
    and is never shipped. Returns the page path, or None (with a note) when the template cannot be found."""
    args = dict(json_path=str(Path(json_path).resolve()), out=str(out) if out else None,
                template=str(template) if template else None, project=str(project) if project else None,
                kit_dir=str(Path(__file__).resolve().parent))
    dst = _call("page", args)
    return Path(dst) if dst else None
