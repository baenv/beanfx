"""Checks kit/sfx.py: seeded bytes, levels, hit timing, weights, loop length and seam, the JSON block and check().

    .venv/bin/python <skill>/tests/test_sfx.py      # exits 0 when every check passes
"""
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kit"))
import checklog  # noqa: E402  (records each check for pytest, see conftest.py)
import export as ex  # noqa: E402
import sfx  # noqa: E402

fails = []


def ok(cond, msg):
    checklog.record(cond, msg)
    if not cond:
        fails.append(msg)


FPS = 24
blank = [np.zeros((8, 8, 4), np.uint8) for _ in range(36)]
for f in blank:
    f[3:5, 3:5] = 255
tmp = Path(tempfile.mkdtemp())

# a one-shot with states and two hits, one with a weight and one without
hits = [ex.hit(10, FPS, weight="light"), ex.hit(24, FPS, freeze=0.25, shake=6)]
js = ex.write(tmp / "a", "fx", blank, FPS, (4, 4), loop=False, hits=hits,
              states={"charge": [0, 9], "slash": [10, 23], "dissolve": [24, 35]}, extra={"glow": "strong"})
ls = sfx.layers(js)
kinds = [L["kind"] for L in ls]
quiet = ex.write(tmp / "q", "qx", blank, FPS, (4, 4), loop=False, states={"hush": [0, 35]})
ok(sfx.layers(quiet) == [], "a hush state stays silent")
ok(kinds.count("hit") == 2 and {"charge", "whoosh", "tail"} <= set(kinds), "layers from hits and state names: %s" % kinds)
ok([L["weight"] for L in ls if L["kind"] == "hit"] == ["light", "finisher"], "a hit with no weight is guessed from freeze and shake")
ok(all(L["t"] == L["frame"] / FPS or abs(L["t"] - L["frame"] / FPS) < 1e-4 for L in ls), "layer t is its frame's time")

snd = sfx.write(tmp / "a", "fx", js, seed=3, voice="retro", element="metal")
disk = json.loads((tmp / "a" / "fx.json").read_text())["meta"]["beanfx"]
ok(disk.get("sound") == snd, "meta.beanfx.sound is written to the JSON")
ok(all(h.get("sound") for h in disk["act"]["hits"]), "every act hit names its cue: %s" % [h.get("sound") for h in disk["act"]["hits"]])
ok(sfx.check(tmp / "a", disk) == [], "check is clean: %s" % sfx.check(tmp / "a", disk))
trk = sfx.load(tmp / "a" / snd["track"])
ok(len(trk) / sfx.RATE >= 36 / FPS, "one-shot track covers the sheet: %.3f s" % (len(trk) / sfx.RATE))
ok(0.5 < np.abs(trk).max() <= 0.95, "track peak in range: %.3f" % np.abs(trk).max())
files = sorted({c["file"] for c in snd["cues"]})
ok(all((tmp / "a" / f).exists() for f in files) and len(files) == len(snd["cues"]), "one file per distinct cue: %s" % files)

# same seed same bytes, another seed differs
b1 = (tmp / "a" / snd["track"]).read_bytes()
sfx.write(tmp / "a", "fx", js, seed=3, voice="retro", element="metal")
ok((tmp / "a" / snd["track"]).read_bytes() == b1, "same seed writes the same bytes")
sfx.write(tmp / "a", "fx", js, seed=4, voice="retro", element="metal")
ok((tmp / "a" / snd["track"]).read_bytes() != b1, "another seed writes another sound")

# hits alone: each hit's onset in the track lands within one frame of its t
only = ex.write(tmp / "b", "hx", blank, FPS, (4, 4), loop=False,
                hits=[ex.hit(6, FPS, weight="heavy"), ex.hit(20, FPS, weight="light")])
sfx.write(tmp / "b", "hx", only, seed=1, voice="soft")
x = sfx.load(tmp / "b" / "hx_sound.wav")
for h in only["meta"]["beanfx"]["act"]["hits"]:
    on = sfx.onset(x, h["t"], FPS, window=0.25)
    ok(abs(on - h["t"]) <= 1 / FPS, "hit at frame %d sounds at %.3f s (t %.3f)" % (h["frame"], on, h["t"]))

# heavier is longer and lower (spectral centroid falls)
def centroid(y):
    s = np.abs(np.fft.rfft(y))
    f = np.fft.rfftfreq(len(y), 1 / sfx.RATE)
    return float((s * f).sum() / s.sum())


cs, ns = [], []
for w in ("light", "heavy", "finisher"):
    y = sfx.render(dict(kind="hit", weight=w), seed=1, voice="soft")
    cs.append(centroid(y))
    ns.append(len(y))
ok(ns[0] < ns[1] < ns[2], "heavier hits last longer: %s" % ns)
ok(cs[0] > cs[1] > cs[2], "heavier hits sound lower: %s" % [round(c) for c in cs])

# every kind, voice and element renders, normalised and not silent
for k in sfx.KINDS:
    for v in sfx.VOICES:
        for e in sfx.ELEMENTS:
            y = sfx.render(dict(kind=k, weight="heavy", dur=0.4), seed=2, voice=v, element=e)
            if not (0.5 < np.abs(y).max() <= sfx.PEAK + 1e-6) or not np.isfinite(y).all():
                ok(False, "%s %s %s level %.3f" % (k, v, e, np.abs(y).max()))
ok(True, "every kind, voice and element renders in level")

# a loop: exactly the sheet's length and no jump at the seam
loopjs = ex.write(tmp / "c", "lp", blank[:24], FPS, (4, 4), loop=True)
ok([L["kind"] for L in sfx.layers(loopjs)] == ["hum"], "a bare loop gets a hum")
sfx.write(tmp / "c", "lp", loopjs, seed=1, element="fire")
y = sfx.load(tmp / "c" / "lp_sound.wav")
ok(len(y) == round(24 / FPS * sfx.RATE), "loop track is exactly frames / fps: %d samples" % len(y))
ok(sfx.check(tmp / "c", loopjs) == [], "loop check clean: %s" % sfx.check(tmp / "c", loopjs))
loop2 = ex.write(tmp / "c", "lq", blank[:24], FPS, (4, 4), loop=True, hits=[ex.hit(20, FPS, weight="heavy")])
sfx.write(tmp / "c", "lq", loop2, seed=1)
y = sfx.load(tmp / "c" / "lq_sound.wav")
ok(len(y) == round(24 / FPS * sfx.RATE) and sfx.check(tmp / "c", loop2) == [],
   "a hit near the end of a loop wraps onto the start: %s" % sfx.check(tmp / "c", loop2))

# real voice: metal stabs and clashes; thunder cracks, then rolls low and long
def peaks(y, k=6):
    s = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    f = np.fft.rfftfreq(len(y), 1 / sfx.RATE)
    out = []
    for i in np.argsort(s)[::-1]:
        if all(abs(f[i] - g) > 40 for g in out):
            out.append(float(f[i]))
        if len(out) == k:
            break
    return out


def t60(y):
    """s from the loudest point until the level falls 40 dB."""
    e = np.convolve(y ** 2, np.ones(441) / 441, "same")
    db = 10 * np.log10(e / e.max() + 1e-12)
    pk_ = int(e.argmax())
    after = np.where(db[pk_:] < -40)[0]
    return (after[0] if len(after) else len(y) - pk_) / sfx.RATE


def tonal(y, k=6):
    """Share of the energy above 500 Hz held in its k strongest tones: near 1 for a bell, low for a clatter."""
    y = sfx.highpass(sfx.highpass(y, 500), 500)
    s = np.abs(np.fft.rfft(y)) ** 2
    f = np.fft.rfftfreq(len(y), 1 / sfx.RATE)
    return float(sum(s[(f > p - 15) & (f < p + 15)].sum() for p in peaks(y, k)) / s.sum())


# a blade that lands (sword rain, a stab) is a short dense chink, never a bell; blade on blade rings at the bar modes
rng = np.random.default_rng(5)
for w, most in (("light", 0.25), ("heavy", 0.35), ("finisher", 0.45)):
    mh = sfx.metal_hit(w, np.random.default_rng(1))
    ok(tonal(mh) < 0.45 and t60(mh) < most, "%s stab is no bell: tonal %.2f, dies in %.2f s (under %.2f)" % (
        w, tonal(mh), t60(mh), most))
ok(len(sfx.metal_hit("light", rng)) < len(sfx.metal_hit("finisher", rng)), "a heavier stab lasts longer")
for w in ("light", "heavy", "finisher"):
    y = sfx.metal_hit(w, np.random.default_rng(1))
    sp = np.abs(np.fft.rfft(y)) ** 2
    fr = np.fft.rfftfreq(len(y), 1 / sfx.RATE)
    lo = sp[fr < 300].sum() / sp.sum()
    ok(lo < 0.1, "%s stab is no drum: %.2f of its energy under 300 Hz" % (w, lo))
mc = sfx.metal_clash("heavy", rng)
pk = sorted(peaks(mc, 4))
f0 = pk[0]
modes = [f0 * r for r in sfx.BAR[:3]]
ok(all(any(abs(p - m) / m < 0.03 for p in pk) for m in modes), "a clash rings at the bar modes: %s vs %s" % (
    [round(p) for p in pk], [round(m) for m in modes]))
ok(tonal(mc) > 0.8 and t60(mc) > 0.5, "a clash rings like steel: tonal %.2f, %.2f s" % (tonal(mc), t60(mc)))
y = sfx.render(dict(kind="hit", weight="heavy", clash=True), seed=1, voice="real", element="metal")
ok(t60(y) > 0.5, "a hit layer with clash=True rings: %.2f s" % t60(y))

def low_share(y):
    s = np.abs(np.fft.rfft(y)) ** 2
    f = np.fft.rfftfreq(len(y), 1 / sfx.RATE)
    return float(s[f < 250].sum() / s.sum())


th = sfx.thunder("finisher", np.random.default_rng(5))
c, tail_ = th[:sfx._n(0.05)], th[sfx._n(0.6):]
ok(len(th) / sfx.RATE > 3.0, "finisher thunder rolls past 3 s: %.2f s" % (len(th) / sfx.RATE))
ok(low_share(tail_) > 2 * low_share(c), "thunder: crack bright, rumble low (%.2f vs %.2f under 250 Hz)" % (
    low_share(c), low_share(tail_)))
ok(np.sqrt((tail_[:sfx._n(1.0)] ** 2).mean()) > 0.05 * np.abs(th).max(), "thunder rumble is heard after the crack")
ok(len(sfx.thunder("light", np.random.default_rng(5))) < len(th), "light thunder is shorter")
y = sfx.render(dict(kind="hit", weight="heavy"), seed=1, voice="real", element="ice")
ok(0.5 < np.abs(y).max() <= sfx.PEAK + 1e-6, "real voice falls back to soft for an element with no model")
jr = ex.write(tmp / "r", "rx", blank, FPS, (4, 4), loop=False, hits=[ex.hit(8, FPS, weight="finisher")],
              states={"swing": [0, 7]})
sr = sfx.write(tmp / "r", "rx", jr, seed=1, voice="real", element="lightning", sounds=None)
ok(sfx.check(tmp / "r", jr) == [] and all(c["source"] == "synth" for c in sr["cues"]), "real voice writes clean: %s" % sfx.check(tmp / "r", jr))
xr = sfx.load(tmp / "r" / "rx_sound.wav")
ok(abs(sfx.onset(xr, 8 / FPS, FPS, 0.2) - 8 / FPS) <= 1 / FPS, "thunder onset on its hit")

# a volley: one fall and one landing per projectile, the fall loudest at its end, gains kept, accents named first
v = sfx.volley([12, 12, 13, 20], FPS, fall_frames=4, weight="light", gain=0.3, jitter=0.02, seed=3)
falls = [L for L in v if L["kind"] == "fall"]
lands = [L for L in v if L["kind"] == "hit"]
ok(len(falls) == 4 and len(lands) == 4, "volley: a fall and a landing per projectile")
ok(all(abs(Fa["t"] + Fa["dur"] - La["t"]) < 1e-3 for Fa, La in zip(falls, lands)), "each fall ends on its landing")
ok(len({L["t"] for L in lands[:2]}) == 2 and all(abs(L["t"] - L["frame"] / FPS) <= 0.02 + 1e-6 for L in lands),
   "blows on one frame are spread apart within the jitter")
for vo, el in (("real", "metal"), ("soft", None), ("retro", "fire")):
    y = sfx.render(dict(kind="fall", dur=0.2, weight="light"), seed=1, voice=vo, element=el)
    q4 = len(y) // 4
    ok(np.abs(y[-q4:]).mean() > 2 * np.abs(y[:q4]).mean(), "%s fall swells toward the landing" % vo)
jv = ex.write(tmp / "v", "vx", blank, FPS, (4, 4), loop=False, hits=[ex.hit(12, FPS, weight="heavy")])
sv = sfx.write(tmp / "v", "vx", jv, seed=1, voice="real", element="metal", sounds=None,
               layers=sfx.volley([12, 12], FPS, gain=0.3) + sfx.layers(jv))
ok(jv["meta"]["beanfx"]["act"]["hits"][0]["sound"] == "hit_heavy", "the act hit keeps its own cue, not a volley's")
ok(sorted({c["gain"] for c in sv["cues"]}) == [0.3, 1.0], "a layer's gain reaches the JSON: %s" % sorted({c["gain"] for c in sv["cues"]}))
ok(sfx.check(tmp / "v", jv) == [], "volley writes clean: %s" % sfx.check(tmp / "v", jv))
for k in ("charge", "tail"):
    y = sfx.render(dict(kind=k, dur=0.6), seed=1, voice="real", element="metal")
    ok(tonal(y) < 0.3, "real metal %s has no bell in it: tonal %.2f" % (k, tonal(y)))

# recordings in a sounds folder: matched by name, onset trimmed, pitched by weight, listed in the JSON
snd_dir = tmp / "sounds"
snd_dir.mkdir()
def put(name, x, ch=1, rate=22050, width=2):
    import wave
    data = np.repeat(x[:, None], ch, 1)
    with wave.open(str(snd_dir / name), "wb") as f:
        f.setnchannels(ch); f.setsampwidth(width); f.setframerate(rate)
        f.writeframes((data * (2 ** (8 * width - 1) - 1)).astype("<i2" if width == 2 else "<i4").tobytes())


tt = np.arange(int(0.4 * 22050)) / 22050
ping = np.concatenate([np.zeros(2205), np.sin(2 * np.pi * 660 * tt) * np.exp(-tt / 0.1)])  # 0.1 s silence first
put("metal_hit_01.wav", ping, ch=2)
put("metal_hit_heavy_01.wav", ping * 0.9, width=4, rate=48000)
p1 = sfx.find_sample(snd_dir, dict(kind="hit", weight="light"), "metal", np.random.default_rng(1))
p2 = sfx.find_sample(snd_dir, dict(kind="hit", weight="heavy"), "metal", np.random.default_rng(1))
ok(p1 and p1.name == "metal_hit_01.wav", "a light hit takes metal_hit_*, not the heavy file: %s" % p1)
ok(p2 and p2.name == "metal_hit_heavy_01.wav", "a heavy hit takes the file named for its weight: %s" % p2)
ok(sfx.find_sample(snd_dir, dict(kind="whoosh", dur=0.3), "metal", np.random.default_rng(1)) is None, "no whoosh file, no sample")
x1 = sfx.from_sample(p1, dict(kind="hit", weight="light"))
ok(np.argmax(np.abs(x1) > 0.05) < sfx._n(0.003), "a sample's leading silence is cut so it lands on t")
x0 = sfx.from_sample(p1, dict(kind="hit", weight="finisher"))
ok(len(x0) > len(x1), "a heavier weight plays the same file slower and lower: %d vs %d" % (len(x0), len(x1)))
js_s = ex.write(tmp / "s", "sx", blank, FPS, (4, 4), loop=False,
                hits=[ex.hit(6, FPS, weight="light"), ex.hit(20, FPS, weight="heavy")])
ss = sfx.write(tmp / "s", "sx", js_s, seed=1, voice="real", element="metal", sounds=snd_dir)
srcs = [c["source"] for c in ss["cues"]]
ok(srcs == ["sample:metal_hit_01.wav", "sample:metal_hit_heavy_01.wav"], "cues use the recordings: %s" % srcs)
ok(ss.get("samples") == ["metal_hit_01.wav", "metal_hit_heavy_01.wav"], "the JSON lists the recordings to credit")
ok(sfx.check(tmp / "s", js_s) == [], "sample cues check clean: %s" % sfx.check(tmp / "s", js_s))
xs = sfx.load(tmp / "s" / "sx_sound.wav")
for h in js_s["meta"]["beanfx"]["act"]["hits"]:
    on = sfx.onset(xs, h["t"], FPS, window=0.25)
    ok(abs(on - h["t"]) <= 1 / FPS, "sample hit at frame %d sounds at %.3f s (t %.3f)" % (h["frame"], on, h["t"]))
ok(sfx.sounds_dir(Path(tempfile.mkdtemp()) / "drafts" / "d" / "out") is None, "no sounds folder in the project, synthesis only")

# check catches a missing file and a bad voice is refused
(tmp / "a" / snd["track"]).unlink()
ok(any("missing" in p for p in sfx.check(tmp / "a", disk)), "check names a missing file")
try:
    sfx.track(js, voice="orchestral")
    ok(False, "unknown voice is refused")
except ValueError:
    ok(True, "unknown voice is refused")
ok(sfx.check(tmp / "a", {"fps": 24, "frames": 1}) == [], "no sound block, no problems")

print("%s sfx checks" % ("ok" if not fails else len(fails)))
for m in fails:
    print("FAIL", m)
sys.exit(1 if fails else 0)
