"""Checks kit/rig.py on a synthetic character: frames cut right, the feet measured, the pivot placed, the JSON binding.

    .venv/bin/python <skill>/tests/test_rig.py      # exits 0 when every check passes
"""
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kit"))
import rig  # noqa: E402

W, H, N = 24, 32, 3


def body(k, foot_x=10, ground=28):
    """A 4 px wide body standing on ground at foot_x, with a marker pixel in column k so frames differ."""
    img = np.zeros((H, W, 4), np.uint8)
    img[ground - 16:ground, foot_x - 2:foot_x + 2] = (200, 120, 60, 255)
    img[2, k] = (255, 255, 255, 255)
    return img


def sheet(path, frames):
    Image.fromarray(np.concatenate(frames, 1), "RGBA").save(path)


# the fields a bundled caster's animation may carry: the rig contract, nothing from the tool that built it
SHIP_KEYS = {"frame", "frames", "fps", "loop", "sheets", "pivot", "ms", "contact", "swing", "emit", "root"}


def main():
    bad = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        side = root / "casters" / "hero"
        side.mkdir(parents=True)
        sheet(side / "atk.png", [body(k) for k in range(N)])
        (side / "rig.json").write_text(json.dumps({"name": "hero", "view": "side", "facing": "east", "fps": 10,
            "pixel_scale": 1, "anims": {"dash": {"frame": [W, H], "frames": N, "sheet": "atk.png",
            "root": [[0, 0], [5, 0], [12, 0]], "move": "root"}, "atk": {"frame": [W, H], "frames": N, "sheet": "atk.png", "contact": [1],
            "swing": [{"kind": "slash", "turn": "cw", "from": -60, "to": 150, "sweep": 210, "frames": [1]}]}}}))
        top = root / "casters" / "topper"
        top.mkdir()
        sheets = {}
        for i, d in enumerate(rig.DIRS4):
            sheet(top / f"atk_{d}.png", [body(k, foot_x=10 + i) for k in range(N)])
            sheets[d] = f"atk_{d}.png"
        (top / "rig.json").write_text(json.dumps({"name": "topper", "view": "top-down", "fps": 10,
            "directions": rig.DIRS4, "anims": {"atk": {"frame": [W, H], "frames": N, "sheets": sheets,
            "swing": {d: [{"kind": "slash", "turn": "ccw", "from": i * 90, "to": i * 90 - 180, "sweep": -180,
                           "frames": [1, 2]}] for i, d in enumerate(rig.DIRS4)}}}}))

        r = rig.load("hero", root)
        t_no_swing = rig.Rig(side)
        del t_no_swing.spec["anims"]["atk"]["swing"]
        fr = r.frames("atk")
        if len(fr) != N or fr[0].shape != (H, W, 4):
            bad.append(f"frames: {len(fr)} of {fr[0].shape}, want {N} of {(H, W, 4)}")
        if [int(np.nonzero(f[2, :, 3])[0][0]) for f in fr] != list(range(N)):
            bad.append("frames: cut in the wrong place (marker column per frame)")
        if r.pivot("atk") != [10, 28]:
            bad.append(f"measured pivot {r.pivot('atk')}, want [10, 28]")

        canvas = r.place((60, 70), (40, 50), "atk", 0)
        ys, xs = np.nonzero(canvas[..., 3] > 0)
        feet = xs[ys == ys.max()]
        if ys.max() + 1 != 50 or round((feet.min() + feet.max() + 1) / 2) != 40:
            bad.append(f"place: feet at ({(feet.min() + feet.max() + 1) / 2}, {ys.max() + 1}), want (40, 50)")
        if r.place((60, 70), (40, 50), "atk", N + 2, hold=False).any():
            bad.append("place: frame after the animation with hold False should be empty")
        if not r.place((10, 10), (500, 500), "atk", 0).shape == (10, 10, 4):
            bad.append("place: off-canvas placement should clip, not fail")

        m = r.meta("atk", 20, start=1)
        want = dict(rig="hero", anim="atk", start=1, char_fps=10, frames_per_char_frame=2, char_pivot=[10, 28],
                    contact=[1], layer="front", pixel_scale=1)
        for k, v in want.items():
            if m.get(k) != v:
                bad.append(f"meta {k} = {m.get(k)}, want {v}")
        if [x["turn"] for x in m.get("swing", [])] != ["cw"] or r.swing("atk")[0]["to"] != 150:
            bad.append(f"side swing: meta {m.get('swing')}, want one cw stroke to 150")
        if r.arc("atk") != (-60.0, 150.0) or r.check_arc("atk", -60, 150):
            bad.append(f"arc: {r.arc('atk')} should follow the stroke and pass its own check")
        if len(r.check_arc("atk", 150, -60)) != 3:
            bad.append(f"check_arc: a reversed arc should fail turn, start and end: {r.check_arc('atk', 150, -60)}")
        if r.check_arc("atk", -30, 130) or not r.check_arc("atk", -60, 300):
            bad.append("check_arc: ends within tol pass, an end 150 deg off fails")
        if r.root("atk") != [[0, 0]] * N or r.root("dash")[2] != [12, 0]:
            bad.append(f"root: {r.root('atk')} and {r.root('dash')}, want zeros and the listed travel")
        moved = r.place((60, 70), (40, 50), "dash", 2, travel=True)
        still = r.place((60, 70), (40, 50), "dash", 2)
        if np.nonzero(moved[..., 3])[1].min() - np.nonzero(still[..., 3])[1].min() != 12:
            bad.append("place travel=True should shift the body by its root motion")
        md = r.meta("dash", 10)
        if md.get("root") != [[0, 0], [5, 0], [12, 0]] or "anchor" not in md or "root" in r.meta("atk", 10):
            bad.append(f"meta root: {md.get('root')}, anchor {md.get('anchor')}")
        for call, why in ((lambda: r.meta("atk", 15), "fps not a multiple"),
                          (lambda: r.meta("atk", 20, layer="side"), "bad layer"),
                          (lambda: r.frames("walk"), "unknown anim"),
                          (lambda: t_no_swing.arc("atk"), "no swing"),
                          (lambda: rig.load("nobody", root), "missing rig")):
            try:
                call()
                bad.append(f"no error on {why}")
            except (ValueError, KeyError, FileNotFoundError):
                pass

        t = rig.load(str(top))
        if t.meta("atk", 10)["directions"] != rig.DIRS4:
            bad.append("top-down meta: directions missing or out of order")
        to = t.meta("atk", 10, offset=50)["offset"]
        if list(to) != rig.DIRS4 or to["south"] != [0, 50] or to["west"] != [-50, 0]:
            bad.append(f"top-down meta offset: one pair per direction along its facing; got {to}")
        sw = t.meta("atk", 10).get("swing", {})
        if list(sw) != rig.DIRS4 or sw["west"][0]["from"] != 180 or t.swing("atk", "north")[0]["frames"] != [1, 2]:
            bad.append(f"top-down swing: one list per direction in order, read per direction; got {sw}")
        if [int(np.nonzero(t.frames("atk", d)[0][-5, :, 3])[0].mean() + 0.5) for d in rig.DIRS4] != [10, 11, 12, 13]:
            bad.append("top-down: each direction should read its own sheet")

        # a side rig with its own east and west rows (a game character) and a row at its own fps with uneven ms
        two = root / "casters" / "duo"
        two.mkdir()
        for i, d in enumerate(("east", "west")):
            sheet(two / f"cast_{d}.png", [body(k, foot_x=10 + i) for k in range(N)])
        (two / "rig.json").write_text(json.dumps({"name": "duo", "view": "side", "facing": "east", "fps": 7.5,
            "directions": ["east", "west"], "anims": {"cast": {"frame": [W, H], "frames": N, "fps": 20,
            "ms": [50, 100, 50], "sheets": {"east": "cast_east.png", "west": "cast_west.png"}, "contact": [1]}}}))
        u = rig.load("duo", root)
        if u.fps_of("cast") != 20:
            bad.append(f"fps_of: a row's own fps should win, got {u.fps_of('cast')}")
        um = u.meta("cast", 40)
        if um.get("directions") != ["east", "west"] or um["frames_per_char_frame"] != 2 or um["char_fps"] != 20:
            bad.append(f"two-row side meta: directions, row fps and frame ratio; got {um}")
        uo = u.meta("cast", 40, offset=110)
        if uo.get("offset") != [110, 0] or uo.get("range") != 110 or "offset" not in uo["align"] or "offset" in um:
            bad.append(f"side meta offset: one pair along east and the range; got {uo.get('offset')}")
        if um.get("char_ms") != [50, 100, 50]:
            bad.append("two-row side meta: the row's ms should pass through as char_ms")
        if [int(np.nonzero(u.frames("cast", d)[0][-5, :, 3])[0].mean() + 0.5) for d in ("east", "west")] != [10, 11]:
            bad.append("two-row side: west should read its own sheet, not a mirror of east")
        try:
            u.meta("cast", 30)
            bad.append("meta: an effect fps that is not a whole multiple of the row's fps should be refused")
        except ValueError:
            pass

        # the casters that ship with the skill load by name from a project with none of its own, and carry no
        # trace of where they were built
        ship = Path(__file__).resolve().parents[1] / "casters"
        for name in ("nghich_tien_kiem", "nghich_tien_kiem_topdown", "nghich_tien_truong", "nghich_tien_truong_topdown"):
            try:
                b = rig.load(name, root)
                if b.dir.resolve() != (ship / name).resolve():
                    bad.append(f"bundled {name}: loaded from {b.dir}")
            except FileNotFoundError as e:
                bad.append(f"bundled {name}: {e}")
            spec = json.loads((ship / name / "rig.json").read_text())
            if not spec.get("source", "").startswith("beanfx bundled") or "/" in spec["source"] or any(
                    set(a) - SHIP_KEYS for a in spec["anims"].values()):
                bad.append(f"bundled {name}: rig.json carries build details beyond the rig contract")

    for b in bad:
        print(b)
    print(f"test_rig: {len(bad)} problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
