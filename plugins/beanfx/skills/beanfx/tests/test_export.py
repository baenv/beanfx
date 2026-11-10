"""Checks kit/export.py: the sheet grid and its Aseprite-style JSON line up, tags and hits hold, and check() catches
edge contact, empty frames, a one-shot that pops off, a loop seam and unseeded randomness.

    .venv/bin/python <skill>/tests/test_export.py      # exits 0 when every check passes
"""
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kit"))
import checklog  # noqa: E402  (records each check for pytest, see conftest.py)
import export as ex  # noqa: E402
import facing as fc  # noqa: E402
import target as tg  # noqa: E402

W, H, N, FPS = 40, 32, 12, 24
fails = []


def ok(cond, msg):
    checklog.record(cond, msg)
    if not cond:
        fails.append(msg)


def disc(r, cx=20, cy=16, rgb=(250, 200, 80)):
    img = np.zeros((H, W, 4), np.uint8)
    ys, xs = np.mgrid[0:H, 0:W] + 0.5
    img[(xs - cx) ** 2 + (ys - cy) ** 2 < r * r] = (*rgb, 255)
    return img


# a one-shot that grows then dissolves to a speck
shot = [disc(r) for r in (3, 6, 9, 11, 10, 8, 6, 4, 3, 2, 1.2, 0.8)]
light = [np.zeros((H, W, 3)) for _ in shot]

with tempfile.TemporaryDirectory() as d:
    js = ex.write(d, "blast", shot, FPS, (20, 30), False, light=light, color=shot,
                  states={"grow": [0, 3], "fade": [4, 11]}, hits=[ex.hit(3, FPS, freeze=0.12, shake=2)],
                  windup=0.25, extra=fc.meta("side", W, H, (20, 30)))
    m = js["meta"]
    b = m["beanfx"]
    img = Image.open(Path(d) / "blast.png")
    ok(img.size == (m["size"]["w"], m["size"]["h"]), f"png size {img.size} vs meta {m['size']}")
    ok(len(js["frames"]) == N, "one entry per frame")
    ok(all(f["duration"] == round(1000 / FPS) for f in js["frames"]), "duration in ms")
    ok(all(f["frame"]["x"] + W <= img.size[0] and f["frame"]["y"] + H <= img.size[1] for f in js["frames"]),
       "every rect inside the sheet")
    f5 = js["frames"][5]["frame"]
    cell = np.array(img)[f5["y"]:f5["y"] + H, f5["x"]:f5["x"] + W]
    ok((cell == shot[5]).all(), "rect 5 holds frame 5")
    ok([t["name"] for t in m["frameTags"]] == ["grow", "fade"], f"tags {m['frameTags']}")
    ok(b["act"]["hits"][0] == {"frame": 3, "t": 0.125, "freeze": 0.12, "shake": 2, "push": 0, "react": "flinch"},
       f"hit {b['act']}")
    ok(b["end"] == "remove", f"end {b['end']}")
    ok(b["act"]["windup"] == 0.25 and b["light"] == "blast_light.png" and b["blend_light"] == "add", "beanfx meta")
    ok(b["mirror_pivot"] == [20, 30] and b["columns"] * W == img.size[0], "direction fields and columns")
    ok(json.loads((Path(d) / "blast.json").read_text()) == js, "json on disk")
    ok(Image.open(Path(d) / "blast_light.png").mode == "RGB", "light sheet RGB for additive blend")

    # 8 heading rows: tags per row and per row state
    rows = [[disc(4, 20 + k % 3, 16) for _ in range(4)] for k in range(8)]
    js8 = ex.write(d, "bolt", rows, 12, (20, 16), True, states={"fly": [0, 3]})
    names = [t["name"] for t in js8["meta"]["frameTags"]]
    ok(names[:2] == ["east", "east/fly"] and len(names) == 16, f"heading tags {names[:4]}")
    tag = js8["meta"]["frameTags"][2]
    ok((tag["name"], tag["from"], tag["to"]) == ("south-east", 4, 7), f"row 1 tag {tag}")

    # pages: past MAX_EDGE the sheet splits, each page a valid Aseprite pair, the index lists every frame
    keep, ex.MAX_EDGE = ex.MAX_EDGE, 100          # a 40 x 32 cell: 2 across, 3 down, 6 frames a page
    try:
        jp = ex.write(d, "big", shot, FPS, (20, 30), False, light=light, states={"grow": [0, 3], "fade": [4, 11]})
    finally:
        ex.MAX_EDGE = keep
    pg = jp["meta"]["beanfx"]["pages"]
    ok(len(pg) == 2 and [p["first"] for p in pg] == [0, 6], f"pages {pg}")
    ok(len(jp["frames"]) == N and jp["frames"][7]["page"] == 1 and jp["frames"][7]["frame"]["x"] == 40,
       "index frames carry their page and local rect")
    p1 = json.loads((Path(d) / "big_p1.json").read_text())
    ok(len(p1["frames"]) == 6 and p1["frames"][0]["filename"] == "big 6", "page 1 holds frames 6 to 11")
    ok([(t["name"], t["from"], t["to"]) for t in p1["meta"]["frameTags"]] == [("fade", 0, 5)], "page tags clipped")
    im1 = np.array(Image.open(Path(d) / "big_p1.png"))
    ok(im1.shape[:2] == (96, 80) and (im1[32:64, 40:80] == shot[9]).all(), "page 1 pixels")
    ok((Path(d) / "big_p0_light.png").exists() and not (Path(d) / "big.png").exists(), "page files")

    # an act with poses and a target
    ja = ex.write(d, "slash", shot, FPS, (20, 30), False, hits=[ex.hit(3, FPS, 0.1, 2, 4, "knockback")],
                  poses=[ex.pose(-0.3, "windup"), ex.pose(0.05, "release", "snap"), ex.pose(0.4, "recover")],
                  target={"x": 30, "react": "knockback"})
    a = ja["meta"]["beanfx"]["act"]
    ok(a["windup"] == 0.3 and a["poses"][1] == {"t": 0.05, "pose": "release", "how": "snap"} and a["target"]["x"] == 30,
       f"act {a}")
    ok(ex.check_act(a, N, FPS) == [], f"clean act flagged {ex.check_act(a, N, FPS)}")

ok(ex.check(shot, light) == [], f"clean one-shot flagged: {ex.check(shot, light)}")

pop = shot[:-1] + [disc(9)]
ok(any("pop off" in p for p in ex.check(pop)), "one-shot that pops off")
ok(ex.check(pop, hold=True) == [], "a held ending is not a pop")
ok(any("empty colour" in p for p in ex.check(shot[:-1] + [np.zeros((H, W, 4), np.uint8)])), "empty frame")
ok(any("colour touches the edge" in p for p in ex.check([disc(3, 1, 16)] + shot[1:])), "colour on the edge")
hot = [lt.copy() for lt in light]
hot[2][0, 10] = 0.5
ok(any("light touches the edge" in p for p in ex.check(shot, hot)), "light on the edge")

smooth = [disc(4, 20 + 6 * np.cos(k / 10 * 6.283), 16 + 6 * np.sin(k / 10 * 6.283)) for k in range(10)]
ok(not any("seam" in p for p in ex.check(smooth, loop=True)), f"seamless loop flagged: {ex.check(smooth, loop=True)}")
jump = [disc(4, 8 + 2.4 * k, 16) for k in range(10)]
ok(any("seam" in p for p in ex.check(jump, loop=True)), "loop seam missed")

bad_act = ex.act([ex.hit(40, FPS, freeze=0.5, react="explode")],
                 poses=[ex.pose(0.2, "windup"), ex.pose(0.1, "dance")])
got = ex.check_act(bad_act, N, FPS)
ok(sum(x in " ".join(got) for x in ("outside", "stall", "react", "'dance'", "out of order", "no release")) == 6,
   f"act problems {got}")

# other seeds: a seed that throws the disc to the edge is caught
ok(ex.check_seeds(lambda f, sd: disc(4), N) == [], "steady render flagged")
got = ex.check_seeds(lambda f, sd: disc(4, 1 if sd == 7 else 20, 16), N, step=3)
ok(len(got) == 4 and all(x.startswith("seed 7") for x in got), f"seed check {got}")

# hit-stop in previews: the contact frame held for freeze * fps steps, shaken
hs = ex.hitstop(shot, [ex.hit(3, FPS, freeze=0.125, shake=2)], FPS)
ok(len(hs) == N + 3 and (hs[3] == shot[3]).all() and not (hs[4] == shot[3]).all() and (hs[7] == shot[4]).all(),
   "hitstop holds and shakes")

# the target dummy reacts: still before the hit, pale on contact, pushed away from the blow after
hits = [ex.hit(5, FPS, push=6, react="knockback")]
d0, d5, d9 = (tg.draw((64, 64), (32, 60), f, hits, FPS) for f in (0, 5, 9))
xs = lambda im: np.nonzero(im[..., 3])[1].mean()
ok(d0[..., 3].any() and (d0 == tg.draw((64, 64), (32, 60), 4, hits, FPS)).all(), "dummy still before the hit")
ok(d5[..., :3][d5[..., 3] > 0].mean() > d0[..., :3][d0[..., 3] > 0].mean() + 30, "flash on contact")
ok(xs(d9) > xs(d0) + 2, f"knockback pushes right: {xs(d0):.1f} to {xs(d9):.1f}")
ok(tg.under(disc(3), np.zeros((H, W, 4), np.uint8)).shape == (H, W, 4), "under")

# weight presets: one word fills the hit, explicit values win, the cue and the direction ride along
hv = ex.hit(6, FPS, weight="heavy", dir=30)
ok(hv["freeze"] == ex.WEIGHTS["heavy"]["freeze"] and hv["react"] == "knockback" and hv["sound"] == "hit_heavy"
   and hv["dir"] == 30 and hv["flash"] == ex.WEIGHTS["heavy"]["flash"] and hv["weight"] == "heavy", f"heavy {hv}")
ok(ex.hit(6, FPS, weight="heavy", push=9, sound="clang")["push"] == 9, "explicit push beats the preset")
ok(ex.hit(6, FPS, weight="heavy", sound="clang")["sound"] == "clang", "explicit sound")
old = ex.hit(6, FPS)
ok(set(old) == {"frame", "t", "freeze", "shake", "push", "react"} and old["freeze"] == 0.1, f"no weight keeps the old hit {old}")
order = [ex.WEIGHTS[k] for k in ("light", "heavy", "finisher")]
ok(all(a[k] < b[k] for a, b in zip(order, order[1:]) for k in ("freeze", "shake", "push", "flash", "shake_time")),
   "each weight is heavier than the last")
ok(all(ex.check_act(ex.act([ex.hit(3, FPS, weight=k)]), N, FPS) == [] for k in ex.WEIGHTS), "presets pass check_act")
bad = ex.check_act(ex.act([dict(ex.hit(3, FPS), weight="huge", flash=0.4, shake_time=0.9)]), N, FPS)
ok(len(bad) == 3, f"check_act flags weight, flash and shake time: {bad}")

# the preview shake follows the blow: a downward blow shakes rows, not columns, and lasts shake_time
down = ex.hitstop(shot, [ex.hit(3, FPS, freeze=0.0, shake=2, dir=90, shake_time=0.125)], FPS)
ok(len(down) == N, "no freeze adds no frames")
moved = [i for i in range(N) if not (down[i] == shot[i]).all()]
ok(moved and all(not (np.roll(shot[i], 0, axis=1) == down[i]).all() for i in moved), "shake moves frames")
col = lambda im: np.nonzero(im[..., 3].any(0))[0].mean()  # noqa: E731
row = lambda im: np.nonzero(im[..., 3].any(1))[0].mean()  # noqa: E731
ok(all(col(down[i]) == col(shot[i]) and row(down[i]) != row(shot[i]) for i in moved), "a 90 degree blow shakes up and down")
ok(len(moved) >= 2, f"shake_time carries the shake past the contact frame: {moved}")

# the dummy flashes for the hit's flash time and a rising blow lifts it
fl = [ex.hit(5, FPS, flash=0.125, push=6, react="knockback")]
lum = lambda im: im[..., :3][im[..., 3] > 0].mean()  # noqa: E731
base = lum(tg.draw((64, 64), (32, 60), 0, fl, FPS))
lit = [lum(tg.draw((64, 64), (32, 60), f, fl, FPS)) > base + 30 for f in range(5, 11)]
ok(lit == [True, True, True, True, False, False], f"flash lasts 3 frames, then a half frame: {lit}")
up = [ex.hit(5, FPS, push=6, react="knockback", dir=-60)]
ys = lambda im: np.nonzero(im[..., 3])[0].mean()  # noqa: E731
ok(ys(tg.draw((64, 64), (32, 60), 9, up, FPS)) < ys(tg.draw((64, 64), (32, 60), 0, up, FPS)) - 1, "a rising blow lifts")

with tempfile.TemporaryDirectory() as d:
    src = Path(d) / "draft.py"
    src.write_text("import numpy as np\nrng = np.random.default_rng(3)\nx = rng.random(4)\n")
    ok(ex.check(shot, src=src) == [], "seeded draft flagged")
    src.write_text("import numpy as np\nx = np.random.rand(4)\nimport random\n")
    got = [p for p in ex.check(shot, src=src) if "unseeded" in p]
    ok(len(got) == 2 and "draft.py:2" in got[0], f"unseeded {got}")

# extra may add fields but not change the sheet's layout fields
with tempfile.TemporaryDirectory() as d:
    try:
        ex.write(d, "clash", shot, FPS, (20, 30), False, extra={"rows": "text"})
        ok(False, "extra overwriting rows raises")
    except ValueError:
        pass

# the preview page: the result's JSON and sheets and its caster's rig and sheets embedded in out/<name>.html
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    out = root / "drafts" / "demo" / "out"
    rig = {"name": "hero", "view": "top-down", "fps": 10, "directions": ["east"],
           "anims": {"attack1": {"frame": [8, 8], "frames": 1, "sheets": {"east": "a1_east.png"}},
                     "kick": {"frame": [8, 8], "frames": 1, "sheets": {"east": "kick_east.png"}}}}
    (root / "casters" / "hero").mkdir(parents=True)
    (root / "casters" / "hero" / "rig.json").write_text(json.dumps(rig))
    for n in ("a1_east.png", "kick_east.png"):
        Image.new("RGBA", (8, 8)).save(root / "casters" / "hero" / n)
    ex.write(out / "sheets", "blast", shot, FPS, (20, 30), False, light=light, color=shot,
             extra={"caster": {"rig": "hero", "chain": [{"anim": "attack1"}]}})
    tpl = root / "preview.html"
    tpl.write_text('<html><body><script type="module">boot()</script></body></html>')
    pg = ex.page(out / "sheets" / "blast.json", template=tpl)
    ok(pg.resolve() == (out / "blast.html").resolve(), f"page lands in out/: {pg}")
    text = pg.read_text()
    ok(text.index("BEANFX_EMBED") < text.index('<script type="module">'), "page: the embed comes before the app")
    emb = json.loads(text.split("window.BEANFX_EMBED = ", 1)[1].split(";</script>", 1)[0])
    want = {"drafts/demo/out/sheets/blast.json", "drafts/demo/out/sheets/blast.png",
            "drafts/demo/out/sheets/blast_light.png", "drafts/demo/out/sheets/blast_color.png",
            "casters/hero/rig.json", "casters/hero/a1_east.png"}
    ok(set(emb["files"]) == want, f"page files {sorted(emb['files'])}")
    ok(emb["select"] == "fx:drafts/demo/out/sheets/blast.json", f"page select {emb['select']}")

for f in fails:
    print("FAIL", f)
print(f"{'ok' if not fails else len(fails)} export checks")
sys.exit(1 if fails else 0)
