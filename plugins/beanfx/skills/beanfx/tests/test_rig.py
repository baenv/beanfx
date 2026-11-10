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
import checklog  # noqa: E402  (records each check for pytest, see conftest.py)
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

    def ok(cond, name, got=""):
        checklog.record(cond, name)
        if not cond:
            bad.append(name + (f"; got {got}" if got != "" else ""))

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
        ok(len(fr) == N and fr[0].shape == (H, W, 4), "frames: count and size", f"{len(fr)} of {fr[0].shape}")
        ok([int(np.nonzero(f[2, :, 3])[0][0]) for f in fr] == list(range(N)), "frames: cut at the marker column per frame")
        ok(r.pivot("atk") == [10, 28], "pivot: measured on the feet", r.pivot("atk"))

        canvas = r.place((60, 70), (40, 50), "atk", 0)
        ys, xs = np.nonzero(canvas[..., 3] > 0)
        feet = xs[ys == ys.max()]
        ok(ys.max() + 1 == 50 and round((feet.min() + feet.max() + 1) / 2) == 40, "place: feet on the given point",
           ((feet.min() + feet.max() + 1) / 2, ys.max() + 1))
        ok(not r.place((60, 70), (40, 50), "atk", N + 2, hold=False).any(), "place: empty after the animation with hold False")
        ok(r.place((10, 10), (500, 500), "atk", 0).shape == (10, 10, 4), "place: off-canvas placement clips")

        m = r.meta("atk", 20, start=1)
        want = dict(rig="hero", anim="atk", start=1, char_fps=10, frames_per_char_frame=2, char_pivot=[10, 28],
                    contact=[1], layer="front", pixel_scale=1)
        for k, v in want.items():
            ok(m.get(k) == v, f"meta: {k}", m.get(k))
        ok([x["turn"] for x in m.get("swing", [])] == ["cw"] and r.swing("atk")[0]["to"] == 150, "side swing: one cw stroke to 150",
           m.get("swing"))
        ok(r.arc("atk") == (-60.0, 150.0) and not r.check_arc("atk", -60, 150), "arc: follows the stroke and passes its own check",
           r.arc("atk"))
        ok(len(r.check_arc("atk", 150, -60)) == 3, "check_arc: a reversed arc fails turn, start and end", r.check_arc("atk", 150, -60))
        ok(not r.check_arc("atk", -30, 130) and r.check_arc("atk", -60, 300), "check_arc: ends within tol pass, an end 150 deg off fails")
        ok(r.root("atk") == [[0, 0]] * N and r.root("dash")[2] == [12, 0], "root: zeros, and the listed travel",
           (r.root("atk"), r.root("dash")))
        moved = r.place((60, 70), (40, 50), "dash", 2, travel=True)
        still = r.place((60, 70), (40, 50), "dash", 2)
        ok(np.nonzero(moved[..., 3])[1].min() - np.nonzero(still[..., 3])[1].min() == 12, "place: travel=True shifts by the root motion")
        md = r.meta("dash", 10)
        ok(md.get("root") == [[0, 0], [5, 0], [12, 0]] and "anchor" in md and "root" not in r.meta("atk", 10), "meta: root and anchor",
           (md.get("root"), md.get("anchor")))
        for call, why in ((lambda: r.meta("atk", 15), "fps not a multiple"),
                          (lambda: r.meta("atk", 20, layer="side"), "bad layer"),
                          (lambda: r.frames("walk"), "unknown anim"),
                          (lambda: t_no_swing.arc("atk"), "no swing"),
                          (lambda: rig.load("nobody", root), "missing rig")):
            try:
                call()
                ok(False, f"error on {why}")
            except (ValueError, KeyError, FileNotFoundError):
                ok(True, f"error on {why}")

        t = rig.load(str(top))
        ok(t.meta("atk", 10)["directions"] == rig.DIRS4, "top-down meta: directions in order")
        to = t.meta("atk", 10, offset=50)["offset"]
        ok(list(to) == rig.DIRS4 and to["south"] == [0, 50] and to["west"] == [-50, 0], "top-down meta: one offset per direction", to)
        sw = t.meta("atk", 10).get("swing", {})
        ok(list(sw) == rig.DIRS4 and sw["west"][0]["from"] == 180 and t.swing("atk", "north")[0]["frames"] == [1, 2],
           "top-down swing: one list per direction, read per direction", sw)
        ok([int(np.nonzero(t.frames("atk", d)[0][-5, :, 3])[0].mean() + 0.5) for d in rig.DIRS4] == [10, 11, 12, 13],
           "top-down: each direction reads its own sheet")

        # a side rig with its own east and west rows (a game character) and a row at its own fps with uneven ms
        two = root / "casters" / "duo"
        two.mkdir()
        for i, d in enumerate(("east", "west")):
            sheet(two / f"cast_{d}.png", [body(k, foot_x=10 + i) for k in range(N)])
        (two / "rig.json").write_text(json.dumps({"name": "duo", "view": "side", "facing": "east", "fps": 7.5,
            "directions": ["east", "west"], "anims": {"cast": {"frame": [W, H], "frames": N, "fps": 20,
            "ms": [50, 100, 50], "sheets": {"east": "cast_east.png", "west": "cast_west.png"}, "contact": [1]}}}))
        u = rig.load("duo", root)
        ok(u.fps_of("cast") == 20, "fps_of: a row's own fps wins", u.fps_of("cast"))
        um = u.meta("cast", 40)
        ok(um.get("directions") == ["east", "west"] and um["frames_per_char_frame"] == 2 and um["char_fps"] == 20,
           "two-row side meta: directions, row fps and frame ratio", um)
        uo = u.meta("cast", 40, offset=110)
        ok(uo.get("offset") == [110, 0] and uo.get("range") == 110 and "offset" in uo["align"] and "offset" not in um,
           "side meta: one offset along east and the range", uo.get("offset"))
        ok(um.get("char_ms") == [50, 100, 50], "two-row side meta: the row's ms pass through as char_ms")
        ok([int(np.nonzero(u.frames("cast", d)[0][-5, :, 3])[0].mean() + 0.5) for d in ("east", "west")] == [10, 11],
           "two-row side: west reads its own sheet, not a mirror of east")
        try:
            u.meta("cast", 30)
            ok(False, "meta: an effect fps that is not a whole multiple of the row's fps is refused")
        except ValueError:
            ok(True, "meta: an effect fps that is not a whole multiple of the row's fps is refused")

        # the casters that ship with the skill load by name from a project with none of its own, and carry no
        # trace of where they were built
        ship = Path(__file__).resolve().parents[1] / "casters"
        for name in ("nghich_tien_kiem", "nghich_tien_kiem_topdown", "nghich_tien_truong", "nghich_tien_truong_topdown"):
            try:
                b = rig.load(name, root)
                ok(b.dir.resolve() == (ship / name).resolve(), f"bundled {name}: loads from the skill's casters/")
            except FileNotFoundError as e:
                ok(False, f"bundled {name}: loads from the skill's casters/", e)
            spec = json.loads((ship / name / "rig.json").read_text())
            ok(spec.get("source", "").startswith("beanfx bundled") and "/" not in spec["source"] and not any(
                set(a) - SHIP_KEYS for a in spec["anims"].values()),
               f"bundled {name}: rig.json carries only the rig contract")

    for b in bad:
        print(b)
    print(f"test_rig: {len(bad)} problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
