"""Optional sound for an effect: cues synthesised from the effect's own JSON (hits, weights, states, loop, glow),
written as 16-bit mono WAV and listed in meta.beanfx.sound. Off unless the brief asks for sound.

    import sfx
    meta = ex.write(OUT, NAME, frames, FPS, ...)                     # the sheet and its JSON first
    snd = sfx.write(OUT, NAME, meta, seed=1, voice="retro", element="metal")
    bad += sfx.check(OUT, meta)                                      # files, length, level, timing, loop seam

The synthesis, the WAV files and the checks run in the beanfx binary (rust/src/sfx.rs); this module keeps the
Python names and hands numpy arrays back. What it writes: <name>_sound.wav (the whole effect on the sheet's
timeline, frame 0 at 0 s) and one file per cue (<name>_hit_heavy.wav, <name>_charge.wav, ...), each named in
meta.beanfx.sound.cues with the t and frame it fires on. A game plays the track at frame 0, or fires the cues
itself (the hits' `sound` names match). The track runs on sheet time: the game's hit-stop freezes the picture, not
the sound, so a cue fired at its hit keeps in step.

Where the layers come from (`layers(js)`, edit the list and pass it as layers= to change them):
- each act hit: a hit cue by its weight (light, heavy, finisher, blast; guessed from freeze and shake when absent);
- each state by its name: gather, summon, charge, cast, chant, channel, build, focus, windup give a charge rising to
  the state's end; swing, slash, travel, fly, rain, dash, throw, launch, rise, fall give a whoosh over it; dissolve,
  fade, linger, settle give a tail; hush, pause, still, breath stay silent (the held breath before a blow); strike, impact, burst, explode, land give a boom when no hit lands there;
- a loop effect with no other layer: a hum the length of the loop.
voice "retro" (square and triangle waves, crushed to 6 bits at 11 kHz, the 8 and 16-bit console sound) or "soft"
(sine and filtered noise) or "real" (physical models: modal synthesis for metal, N-wave thunder for lightning;
other elements fall back to soft). element colours every cue: metal rings, lightning crackles, fire roars, ice chimes, wind
hisses, arcane shimmers, None stays neutral. The glow level brightens the filter (subtle darker, strong brighter).
All randomness comes from seed, so the same call writes the same bytes.

Recordings: when the project has sounds/ (or BEANFX_SOUNDS points to a folder) with files named
<element>_<kind>[_<weight>]*.wav (metal_hit_heavy_01.wav, lightning_hit.wav, metal_whoosh.wav) or <kind>*.wav, a
cue that finds one uses it, picked by seed, onset on the cue's t, pitched by weight, with a little synthesis under
it. Each cue records its source ("synth" or "sample:<file>") and sound.samples lists the files to credit.
"""
from pathlib import Path

import numpy as np

import bridge


def _run(cmd, args=None, arrays=None):
    return bridge.run("sfx", cmd, args, arrays=arrays, want_arrays=True)


_C = _run("consts")[0]
RATE = _C["RATE"]
PEAK = _C["PEAK"]
VOICES = tuple(_C["VOICES"])
ELEMENTS = tuple(_C["ELEMENTS"])
KINDS = tuple(_C["KINDS"])
WEIGHT_SOUND = _C["WEIGHT_SOUND"]
GLOW_BRIGHT = _C["GLOW_BRIGHT"]
STATE_KIND = {k: tuple(v) for k, v in _C["STATE_KIND"].items()}
GAIN = _C["GAIN"]
BAR = tuple(_C["BAR"])
METAL_F0 = _C["METAL_F0"]
METAL_DUR = _C["METAL_DUR"]
RUMBLE = _C["RUMBLE"]
STAB_RING = _C["STAB_RING"]
PITCH = _C["PITCH"]
SAMPLE_MAX = _C["SAMPLE_MAX"]
SAMPLE_SYNTH = _C["SAMPLE_SYNTH"]


def _check_voice(voice, element):
    if voice not in VOICES:
        raise ValueError(f"voice {voice!r} not in {VOICES}")
    if element not in ELEMENTS:
        raise ValueError(f"element {element!r} not in {ELEMENTS}")


# ---- internals: one binary call each, a numpy Generator's PCG64 state goes over and comes back ---------------

def _state_out(rng):
    s = rng.bit_generator.state
    return dict(state=str(s["state"]["state"]), inc=str(s["state"]["inc"]), has_uint32=int(s["has_uint32"]),
                uinteger=int(s["uinteger"]))


def _state_in(rng, v):
    rng.bit_generator.state = dict(bit_generator="PCG64", state=dict(state=int(v["state"]), inc=int(v["inc"])),
                                   has_uint32=v["has_uint32"], uinteger=v["uinteger"])


def _call(fn, rng=None, arrays=None, **args):
    args["fn"] = fn
    if rng is not None:
        args["rng"] = _state_out(rng)
    value, arrs = _run("call", args, {k: np.asarray(a, float) for k, a in (arrays or {}).items()})
    if rng is not None and value.get("rng"):
        _state_in(rng, value["rng"])
    return value, arrs.get("x")


def _x(fn, rng=None, arrays=None, **args):
    return _call(fn, rng, arrays, **args)[1]


def _split(**vals):
    """Array-like values go over as arrays, the rest as JSON args."""
    arrays = {k: v for k, v in vals.items() if np.ndim(v) > 0}
    return arrays, {k: v for k, v in vals.items() if k not in arrays}


def _n(dur):
    return max(1, int(round(dur * RATE)))


def osc(f0, f1, dur, wave="sine"):
    return _x("osc", f0=f0, f1=f1, dur=dur, wave=wave)


def noise(dur, rng):
    return _x("noise", rng, dur=dur)


def lowpass(x, cut):
    arrays, args = _split(x=x, cut=cut)
    return _x("lowpass", arrays=arrays, **args)


def highpass(x, cut):
    arrays, args = _split(x=x, cut=cut)
    return _x("highpass", arrays=arrays, **args)


def env(n, attack=0.004, decay=0.2, hold=0.0):
    return _x("env", n=n, attack=attack, decay=decay, hold=hold)


def fade(x, ms=4):
    return _x("fade", arrays=dict(x=x), ms=ms)


def crush(x, bits=6, hold=4):
    return _x("crush", arrays=dict(x=x), bits=bits, hold=hold)


def crackle(dur, rng, rate=60):
    return _x("crackle", rng, dur=dur, rate=rate)


def ring(freqs, dur, decay, rng):
    return _x("ring", rng, arrays=dict(freqs=freqs), dur=dur, decay=decay)


def _norm(x, peak=PEAK):
    return _x("_norm", arrays=dict(x=x), peak=peak)


def _wave(voice):
    return ("square", "tri") if voice == "retro" else ("sine", "sine")


def _color(x, dur, element, rng, bright, strength=1.0):
    return _x("_color", rng, arrays=dict(x=x), dur=dur, element=element, bright=bright, strength=strength)


def hit(weight, rng, voice="retro", element=None, bright=1.0):
    return _x("hit", rng, weight=weight, voice=voice, element=element, bright=bright)


def whoosh(dur, rng, voice="retro", element=None, bright=1.0):
    return _x("whoosh", rng, dur=dur, voice=voice, element=element, bright=bright)


def charge(dur, rng, voice="retro", element=None, bright=1.0):
    return _x("charge", rng, dur=dur, voice=voice, element=element, bright=bright)


def tail(dur, rng, voice="retro", element=None, bright=1.0):
    return _x("tail", rng, dur=dur, voice=voice, element=element, bright=bright)


def boom(dur, rng, voice="retro", element=None, bright=1.0):
    return _x("boom", rng, dur=dur, voice=voice, element=element, bright=bright)


def hum(dur, rng, voice="retro", element=None, bright=1.0):
    return _x("hum", rng, dur=dur, voice=voice, element=element, bright=bright)


def resonate(x, f, q):
    return _x("resonate", arrays=dict(x=x), f=f, q=q)


def metal_hit(weight, rng, bright=1.0):
    return _x("metal_hit", rng, weight=weight, bright=bright)


def metal_clash(weight, rng, bright=1.0):
    return _x("metal_clash", rng, weight=weight, bright=bright)


def metal_scrape(dur, rng, bright=1.0):
    return _x("metal_scrape", rng, dur=dur, bright=bright)


def _nwaves(n, times, lengths, amps):
    return _x("_nwaves", arrays=dict(times=times, lengths=lengths, amps=amps), n=n)


def thunder(weight, rng, bright=1.0):
    return _x("thunder", rng, weight=weight, bright=bright)


def metal_gather(dur, rng, bright=1.0):
    return _x("metal_gather", rng, dur=dur, bright=bright)


def metal_settle(dur, rng, bright=1.0):
    return _x("metal_settle", rng, dur=dur, bright=bright)


def metal_fall(dur, rng, bright=1.0, weight="light"):
    return _x("metal_fall", rng, dur=dur, bright=bright, weight=weight)


def fall(dur, rng, voice="retro", element=None, bright=1.0, weight="light"):
    return _x("fall", rng, dur=dur, voice=voice, element=element, bright=bright)


def real(layer, rng, element, bright):
    """The physical model for a layer in the real voice, or None when there is none (other elements use soft)."""
    value, x = _call("real", rng, layer=layer, element=element, bright=bright)
    return None if value["none"] else x


SYNTH = {"hit": None, "whoosh": whoosh, "charge": charge, "tail": tail, "boom": boom, "hum": hum, "fall": fall}


def volley(lands, fps, fall_frames=3, weight="light", gain=0.35, jitter=0.008, seed=1, hits=True):
    """Layers for many projectiles that land (a sword rain, an arrow volley, hail): for each landing frame a fall
    over the fall_frames before it and, with hits, a hit on it, both at gain (many quiet ones read as a rain).
    jitter (s) spreads blows on one frame apart, seeded, so a wave is a clatter and not one blow."""
    return _run("volley", dict(lands=list(lands), fps=fps, fall_frames=fall_frames, weight=weight, gain=gain,
                               jitter=jitter, seed=seed, hits=hits))[0]


# ---- recorded samples (optional) ----------------------------------------------------------------------------

def read_wav(path):
    """Any PCM WAV (8, 16, 24 or 32-bit, mono or stereo, any rate) as mono floats at RATE."""
    return _x("read_wav", path=str(path))


def resample(x, rate):
    """x played at rate times its speed (linear interpolation): above 1 shorter and higher."""
    if abs(rate - 1) < 1e-9 or len(x) < 2:
        return x
    return _x("resample", arrays=dict(x=x), rate=rate)


def find_sample(folder, layer, element, rng):
    """The recording for a layer in folder, or None: the most specific name prefix with a match, picked by rng."""
    args = dict(fn="find_sample", folder=str(folder) if folder else None, layer=layer, element=element,
                rng=_state_out(rng))
    value = _run("call", args)[0]
    _state_in(rng, value["rng"])
    return Path(value["path"]) if value["path"] else None


def from_sample(path, layer):
    """A recording made into a cue: leading silence cut so the onset lands on t, pitched by weight, capped."""
    value, x = _call("from_sample", path=str(path), layer=layer)
    return None if value["none"] else x


def sounds_dir(out=None):
    """BEANFX_SOUNDS, else the project's sounds/ (out is drafts/<name>/out), else None."""
    p = _run("sounds_dir", dict(out=None if out is None else str(out)))[0]
    return Path(p) if p else None


# ---- the effect's timeline ----------------------------------------------------------------------------------

def guess_weight(h):
    """The weight of a hit that names none, from its freeze and shake (nearest WEIGHTS row)."""
    return _run("guess_weight", dict(h=h))[0]


def _bfx(js):
    return js["meta"]["beanfx"] if "meta" in js else js


def layers(js):
    """The sound layers of an effect from its JSON (an ex.write result): one dict per layer with kind, t (s from
    frame 0), dur (s), frame, and weight for hits. Edit and pass back as layers= to write() or track()."""
    return _run("layers", dict(js=js))[0]


def _sounds(sounds):
    return None if not sounds else str(sounds)


def render(layer, seed=1, voice="retro", element=None, bright=1.0, index=0, sounds=None):
    """One layer's samples, normalised; the rng comes from seed and the layer's place so it is stable. With a
    sounds folder holding a matching recording, the cue is that recording (see find_sample); layer["source"] is set
    to "synth" or "sample:<file>"."""
    value, arrs = _run("render", dict(layer=layer, seed=seed, voice=voice, element=element, bright=bright,
                                      index=index, sounds=_sounds(sounds)))
    layer["source"] = value["source"]
    return arrs["x"]


def track(js, seed=1, voice="retro", element=None, layers_=None, sounds=None):
    """The whole effect's sound on the sheet's timeline and the rendered cues: (samples, [(layer, samples)]).
    A loop wraps what runs past the end onto the start, so the track is exactly frames / fps long and joins."""
    _check_voice(voice, element)
    value, arrs = _run("track", dict(js=js, seed=seed, voice=voice, element=element, layers=layers_,
                                     sounds=_sounds(sounds)))
    return arrs["mix"], [(L, arrs[f"cue{i}"]) for i, L in enumerate(value)]


def save(path, x):
    """16-bit mono WAV at RATE."""
    _run("save", dict(path=str(path)), dict(x=np.asarray(x, float)))


def load(path):
    return _x("load", path=str(path))


def write(out, name, js=None, seed=1, voice="retro", element=None, layers=None, sounds="auto"):
    """Writes <name>_sound.wav and one WAV per distinct cue into out, adds meta.beanfx.sound to <name>.json (and to
    js when given), names the cue on every act hit that had none, and returns the sound block. sounds: a folder of
    recordings, "auto" (BEANFX_SOUNDS or the project's sounds/) or None (synthesis only)."""
    _check_voice(voice, element)
    if sounds is not None and sounds != "auto":
        sounds = str(sounds)
    value = _run("write", dict(out=str(out), name=name, js=js, seed=seed, voice=voice, element=element,
                               layers=layers, sounds=sounds))[0]
    snd = value["sound"]
    if js is not None:
        b = _bfx(js)
        for h, h2 in zip(b.get("act", {}).get("hits", []), (value["act"] or {}).get("hits", [])):
            if not h.get("sound"):
                h["sound"] = h2["sound"]
        b["sound"] = snd
    return snd


def check(out, js):
    """The problems of an effect's sound: missing files, a silent or clipping file, a track shorter than the sheet
    (or, for a loop, not exactly its length or with a jump at the seam), and hit cues off their hit by a frame."""
    return _run("check", dict(out=str(out), js=js))[0]


def onset(x, t, fps, window=0.5):
    """The time (s) the sound first rises past half its peak within window s from t - one frame; for checks."""
    return _run("onset", dict(t=t, fps=fps, window=window), dict(x=np.asarray(x, float)))[0]
