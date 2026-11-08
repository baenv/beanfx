"""Export and check a finished effect: a sprite sheet grid with Aseprite-style JSON that engines import, and the
checks that catch what eyes miss.

    import export as ex
    bad = ex.check(frames, lights, loop=False, src=__file__)       # list of problems, empty when clean
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
"""
import json
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image

MAX_EDGE = 4096  # a texture side most GPUs and WebGL2 phones take
VRAM_NOTE = 64e6  # bytes of decoded sheets above which write() prints a texture memory note
LIGHT_EDGE = 0.02  # light below this may reach the cell edge (a smooth pool fades past it)
POP = 0.05  # the last frame of a one-shot may keep at most this share of the peak frame's pixels


def _rows(frames):
    return frames if isinstance(frames[0], (list, tuple)) else [frames]


def _flat(frames):
    return [f for r in _rows(frames) for f in r]


POSES = ("idle", "guard", "windup", "cast", "channel", "release", "follow", "recover")
REACTS = ("none", "flinch", "stagger", "knockback", "launch")


# Weight classes for a contact, after fighting-game and action-game practice (vfx_notes.md, Missing choices 1 to 3):
# a stronger hit freezes longer, shakes harder and longer, pushes further and flashes the target longer.
# freeze and shake_time in s, shake and push in px, flash in s the target shows white.
WEIGHTS = {
    "light":    dict(freeze=0.05, shake=1, shake_time=0.07, push=1, react="flinch", flash=0.03),
    "heavy":    dict(freeze=0.13, shake=3, shake_time=0.12, push=4, react="knockback", flash=0.07),
    "finisher": dict(freeze=0.25, shake=6, shake_time=0.2, push=10, react="launch", flash=0.12),
    "blast":    dict(freeze=0.08, shake=5, shake_time=0.27, push=8, react="knockback", flash=0.1),
}


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
    bad = []
    for h in a.get("hits", []):
        if not 0 <= h["frame"] < frames:
            bad.append(f"act: hit at frame {h['frame']} is outside the {frames} frames")
        if h.get("freeze", 0) > 0.3:
            bad.append(f"act: hit at frame {h['frame']} freezes {h['freeze']} s; past 0.3 s it reads as a stall")
        if h.get("react", "none") not in REACTS:
            bad.append(f"act: hit at frame {h['frame']} react {h['react']!r} not in {REACTS}")
        if h.get("weight") is not None and h["weight"] not in WEIGHTS:
            bad.append(f"act: hit at frame {h['frame']} weight {h['weight']!r} not in {tuple(WEIGHTS)}")
        if not 0 <= h.get("shake_time", 0) <= 0.6:
            bad.append(f"act: hit at frame {h['frame']} shakes {h['shake_time']} s; keep it within 0.6 s")
        if h.get("flash", 0) > 0.25:
            bad.append(f"act: hit at frame {h['frame']} flashes {h['flash']} s; past 0.25 s it reads as a stun")
    keys = a.get("poses", [])
    for i, k in enumerate(keys):
        if k["pose"] not in POSES:
            bad.append(f"act: pose {k['pose']!r} at t {k['t']} not in {POSES}")
        if i and k["t"] < keys[i - 1]["t"]:
            bad.append(f"act: pose keys out of order at t {k['t']}")
    if keys and a.get("hits") and not any(k["pose"] in ("release", "cast") and k["t"] <= a["hits"][0]["t"]
                                          for k in keys):
        bad.append("act: no release or cast pose before the first hit")
    if loop and keys and keys[0]["pose"] != keys[-1]["pose"]:
        bad.append("act: a loop's poses end on a different pose than they start")
    return bad


def hitstop(frames, hits, fps):
    """Preview frames with each hit's freeze held on its contact frame and the camera shake applied along the blow
    (`dir`) for `shake_time` (default: the freeze), so a gif shows the hit-stop and shake the game will add. For
    previews only; the sheet keeps one frame per step."""
    by = {h["frame"]: h for h in hits or []}
    out, shake = [], []  # shake: (frames left, total, amp, ux, uy) of the running shake

    def shaken(f):
        if not shake:
            return f
        left, total, amp, ux, uy = shake[0]
        d = amp * left / max(1, total)
        sgn = 1 if left % 2 else -1
        dx, dy = round(sgn * d * ux), round(sgn * d * uy)
        shake[0] = (left - 1, total, amp, ux, uy)
        if left - 1 <= 0:
            shake.clear()
        return np.roll(np.roll(f, dx, axis=1), dy, axis=0) if (dx or dy) else f

    for i, f in enumerate(frames):
        h = by.get(i)
        if h:
            hold = max(0, round(h.get("freeze", 0) * fps))
            amp = h.get("shake", 0)
            a = math.radians(h.get("dir", 0))
            n = max(1, round(max(h.get("shake_time", 0), h.get("freeze", 0)) * fps))
            shake[:] = [(n, n, amp, math.cos(a), math.sin(a))] if amp else []
            out.append(f)
            for _ in range(hold):
                out.append(shaken(f))
            continue
        out.append(shaken(f))
    return out


def grid(n, w, h, columns=None):
    """Columns and rows of the sheet grid for n frames of w x h: near square unless columns is given."""
    cols = columns or min(n, max(1, math.ceil(math.sqrt(n * h / w))))
    return cols, math.ceil(n / cols)


def _page_grid(n, w, h, columns):
    """(frames per page, columns): one page when the near-square grid fits, else pages as full as MAX_EDGE takes."""
    cols, rows = grid(n, w, h, columns)
    if cols * w <= MAX_EDGE and rows * h <= MAX_EDGE:
        return n, cols
    cmax, rmax = MAX_EDGE // w, MAX_EDGE // h
    if cmax < 1 or rmax < 1:
        raise ValueError(f"a {w}x{h} cell passes {MAX_EDGE} px")
    return cmax * rmax, cmax


def _sheet(frames, cols, w, h, channels):
    rows = math.ceil(len(frames) / cols)
    img = np.zeros((rows * h, cols * w, channels), np.uint8)
    for i, f in enumerate(frames):
        x, y = (i % cols) * w, (i // cols) * h
        img[y:y + h, x:x + w] = f[..., :channels]
    return img


def _u8(light):
    return light if light.dtype == np.uint8 else (np.clip(light, 0, 1) * 255).round().astype(np.uint8)


def row_names(n):
    if n == 1:
        return [""]
    if n == 8:
        return ["east", "south-east", "south", "south-west", "west", "north-west", "north", "north-east"]
    if n == 4:
        return ["east", "south", "west", "north"]
    return [f"dir{k}" for k in range(n)]


def _aseprite(entries, tags, image, size, bfx):
    return {"frames": entries, "meta": {"app": "beanfx", "version": "1", "image": image, "format": "RGBA8888",
                                        "size": size, "scale": "1", "frameTags": tags, "beanfx": bfx}}


def write(out, name, frames, fps, pivot, loop, light=None, color=None, states=None, hits=None, windup=0.0,
          poses=None, target=None, columns=None, extra=None, hold=False):
    """Writes <name>.png (colour plus light), <name>_light.png and <name>_color.png when given (same grid), and
    <name>.json. Returns the JSON. hold: a one-shot that ends on a held state (an eye that stays open, a seal that
    stays); `end` tells the engine to keep the last frame (or hand over to a loop) instead of removing it.

    A sheet that would pass MAX_EDGE splits into pages <name>_p<k>.png (each with its own Aseprite JSON
    <name>_p<k>.json holding its frames and the tags clipped to it); <name>.json then lists every frame with its
    `page` and the page files in meta.beanfx.pages. Frame filenames are unique across pages."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows = _rows(frames)
    n, nrows = len(rows[0]), len(rows)
    h, w = rows[0][0].shape[:2]
    flat = _flat(frames)
    lflat = [_u8(f) for f in _flat(light)] if light is not None else None
    cflat = _flat(color) if color is not None else None
    per, cols = _page_grid(len(flat), w, h, columns)
    npages = math.ceil(len(flat) / per)

    names = row_names(nrows)
    ms = round(1000 / fps)
    direction = "forward"
    tags = []
    for r in range(nrows):
        base = r * n
        if nrows > 1:
            tags.append({"name": names[r], "from": base, "to": base + n - 1, "direction": direction})
        for s, (a, b) in (states or {}).items():
            tags.append({"name": f"{names[r]}/{s}" if nrows > 1 else s, "from": base + a, "to": base + b,
                         "direction": direction})
    if not tags:
        tags = [{"name": name, "from": 0, "to": n - 1, "direction": direction}]

    bfx = {"name": name, "fps": fps, "loop": loop, "end": "loop" if loop else "hold" if hold else "remove",
           "frames": n, "rows": nrows, "frameSize": [w, h], "pivot": list(pivot), "columns": cols}
    if light is not None:
        bfx.update(blend_light="add", light_gain=1.0)
    if states:
        bfx["states"] = {k: list(v) for k, v in states.items()}
    if hits or windup or poses or target:
        bfx["act"] = act(hits, windup, poses, target)
    bfx.update(extra or {})

    entries, pages = [], []
    for k in range(npages):
        stem = name if npages == 1 else f"{name}_p{k}"
        part = slice(k * per, min(len(flat), (k + 1) * per))
        idx = range(len(flat))[part]
        files = {"image": f"{stem}.png"}
        Image.fromarray(_sheet(flat[part], cols, w, h, 4), "RGBA").save(out / files["image"])
        if lflat is not None:
            files["light"] = f"{stem}_light.png"
            Image.fromarray(_sheet(lflat[part], cols, w, h, 3), "RGB").save(out / files["light"])
        if cflat is not None:
            files["color"] = f"{stem}_color.png"
            Image.fromarray(_sheet(cflat[part], cols, w, h, 4), "RGBA").save(out / files["color"])
        size = {"w": cols * w, "h": math.ceil(len(idx) / cols) * h}
        local = []
        for j, i in enumerate(idx):
            r, f = divmod(i, n)
            e = {"filename": " ".join(p for p in (name, names[r], str(f)) if p),
                 "frame": {"x": (j % cols) * w, "y": (j // cols) * h, "w": w, "h": h}, "rotated": False,
                 "trimmed": False, "spriteSourceSize": {"x": 0, "y": 0, "w": w, "h": h}, "sourceSize": {"w": w, "h": h},
                 "duration": ms}
            local.append(e)
            entries.append(dict(e, page=k) if npages > 1 else e)
        if npages > 1:
            first, last = idx[0], idx[-1]
            ptags = [dict(t, **{"from": max(t["from"], first) - first, "to": min(t["to"], last) - first})
                     for t in tags if t["from"] <= last and t["to"] >= first]
            pb = dict(bfx, page=k, first=first, **files)
            (out / f"{stem}.json").write_text(json.dumps(_aseprite(local, ptags, files["image"], size, pb), indent=1))
            pages.append(dict(files, json=f"{stem}.json", first=first, last=last))
        else:
            bfx.update({"sheet": files["image"], **{x: files[x] for x in ("light", "color") if x in files}})
            js = _aseprite(local, tags, files["image"], size, bfx)
    if npages > 1:
        bfx["pages"] = pages
        js = _aseprite(entries, tags, pages[0]["image"], {"w": cols * w, "h": math.ceil(per / cols) * h}, bfx)
    (out / f"{name}.json").write_text(json.dumps(js, indent=1))
    vram = len(flat) * w * h * 4 * (2 if lflat is not None and cflat is not None else 1)
    if vram > VRAM_NOTE:
        print("note: %s needs about %d MB of texture memory decoded (colour and light); porting.md, Budget"
              % (name, round(vram / 1e6)))
    return js


def check_seeds(render, frames, seeds=(2, 3, 7), step=2):
    """Edge and empty-frame problems with other seeds: render(f, seed) returns the colour frame (h, w, 4) of frame f
    drawn with that seed. Particles that a reseed throws further show up here."""
    bad = []
    for sd in seeds:
        for f in range(0, frames, step):
            a = render(f, sd)[..., 3] > 0
            if not a.any():
                bad.append(f"seed {sd} frame {f}: empty colour")
            elif a[[0, -1], :].any() or a[:, [0, -1]].any():
                bad.append(f"seed {sd} frame {f}: colour touches the edge")
    return bad


UNSEEDED = re.compile(r"np\.random\.(rand|randn|randint|random|uniform|normal|choice|shuffle|permutation)\("
                      r"|default_rng\(\s*\)|^\s*import random\b|^\s*from random import", re.M)


def check(frames, light=None, loop=False, src=None, hold=False):
    """The problems of a finished effect, one line each: colour or light on the cell edge, an empty frame, a
    one-shot that pops off (its last frame keeps more than POP of the peak; hold skips it), a loop seam (the last to first step
    changes more than twice a normal step), and randomness without a seed in the draft source src."""
    bad = []
    lights = _rows(light) if light is not None else None
    for r, row in enumerate(_rows(frames)):
        tag = f"row {r} " if len(_rows(frames)) > 1 else ""
        on = [f[..., 3] > 0 for f in row]
        h, w = on[0].shape
        edge = np.zeros((h, w), bool)
        edge[[0, -1], :] = True
        edge[:, [0, -1]] = True
        for i, a in enumerate(on):
            if not a.any():
                bad.append(f"{tag}frame {i}: empty colour")
            elif (a & edge).any():
                bad.append(f"{tag}frame {i}: colour touches the edge")
            if lights is not None:
                L = np.asarray(lights[r][i], float)
                L = L / 255.0 if lights[r][i].dtype == np.uint8 else L
                if ((L.max(axis=-1) if L.ndim == 3 else L) > LIGHT_EDGE)[edge].any():
                    bad.append(f"{tag}frame {i}: light touches the edge")
        cover = [int(a.sum()) for a in on]
        if not loop and not hold and len(on) > 1 and cover[-1] > POP * max(cover):
            bad.append(f"{tag}last frame keeps {cover[-1]} px, {100 * cover[-1] / max(cover):.0f} % of the peak: "
                       f"dissolve to wisps so it does not pop off")
        if loop and len(row) > 2:
            step = [int((np.any(row[i] != row[i + 1], axis=-1)).sum()) for i in range(len(row) - 1)]
            typical = sorted(step)[int(len(step) * 0.9)]
            seam = int((np.any(row[-1] != row[0], axis=-1)).sum())
            if seam > max(2 * typical, 12):
                bad.append(f"{tag}loop seam: {seam} px change from the last frame to the first, a normal step is "
                           f"{typical}")
    if src is not None:
        text = Path(src).read_text()
        for m in UNSEEDED.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            bad.append(f"{Path(src).name}:{line}: unseeded randomness; use np.random.default_rng(seed)")
    return bad
