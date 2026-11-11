"""Optional sound for an effect: cues synthesised in numpy from the effect's own JSON (hits, weights, states, loop,
glow), written as 16-bit mono WAV and listed in meta.beanfx.sound. Off unless the brief asks for sound.

    import sfx
    meta = ex.write(OUT, NAME, frames, FPS, ...)                     # the sheet and its JSON first
    snd = sfx.write(OUT, NAME, meta, seed=1, voice="retro", element="metal")
    bad += sfx.check(OUT, meta)                                      # files, length, level, timing, loop seam

What it writes: <name>_sound.wav (the whole effect on the sheet's timeline, frame 0 at 0 s) and one file per cue
(<name>_hit_heavy.wav, <name>_charge.wav, ...), each named in meta.beanfx.sound.cues with the t and frame it
fires on. A game plays the track at frame 0, or fires the cues itself (the hits' `sound` names match). The track
runs on sheet time: the game's hit-stop freezes the picture, not the sound, so a cue fired at its hit keeps in step.

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
import json
import wave
from pathlib import Path

import numpy as np

RATE = 44100
PEAK = 0.8  # each file is normalised to this peak (about -2 dBFS), so nothing clips
VOICES = ("retro", "soft", "real")
ELEMENTS = (None, "metal", "lightning", "fire", "ice", "wind", "arcane")
KINDS = ("hit", "whoosh", "charge", "tail", "boom", "hum", "fall")
WEIGHT_SOUND = {  # body pitch sweep (Hz), noise cutoff (Hz), length (s): a heavier hit is lower and longer
    "light":    dict(f0=440, f1=170, cut=6500, dur=0.2),
    "heavy":    dict(f0=230, f1=62, cut=3800, dur=0.38),
    "finisher": dict(f0=170, f1=40, cut=2800, dur=0.7),
    "blast":    dict(f0=120, f1=32, cut=2000, dur=0.9),
}
GLOW_BRIGHT = {"subtle": 0.8, "medium": 1.0, "strong": 1.25}
STATE_KIND = {
    "charge": ("gather", "summon", "charge", "cast", "chant", "channel", "build", "focus", "windup"),
    "whoosh": ("swing", "slash", "travel", "fly", "rain", "dash", "throw", "launch", "rise", "fall"),
    "tail": ("dissolve", "fade", "linger", "settle"),
    "rest": ("hush", "pause", "still", "breath"),  # held silence before a blow: no layer
    "boom": ("strike", "impact", "burst", "explode", "land"),
}
GAIN = {"hit": 1.0, "boom": 0.9, "charge": 0.45, "whoosh": 0.4, "tail": 0.3, "hum": 0.5, "fall": 0.5}


# ---- synth parts --------------------------------------------------------------------------------------------

def _n(dur):
    return max(1, int(round(dur * RATE)))


def osc(f0, f1, dur, wave="sine"):
    """A tone sweeping from f0 to f1 Hz (exponential) over dur s; wave sine, square, saw or tri."""
    n = _n(dur)
    t = np.arange(n) / n
    f = f0 * (f1 / f0) ** t
    ph = np.cumsum(f) / RATE
    if wave == "square":
        return np.where((ph % 1) < 0.5, 1.0, -1.0)
    if wave == "saw":
        return 2 * (ph % 1) - 1
    if wave == "tri":
        return 4 * np.abs((ph % 1) - 0.5) - 1
    return np.sin(2 * np.pi * ph)


def noise(dur, rng):
    return rng.uniform(-1, 1, _n(dur))


def lowpass(x, cut):
    """One-pole low-pass; cut in Hz, a number or one value per sample (a sweep)."""
    cut = np.broadcast_to(np.asarray(cut, float), x.shape)
    a = (1 - np.exp(-2 * np.pi * np.clip(cut, 20, RATE / 2) / RATE)).tolist()
    y, v = [0.0] * len(x), 0.0
    for i, s in enumerate(x.tolist()):
        v += a[i] * (s - v)
        y[i] = v
    return np.array(y)


def highpass(x, cut):
    return x - lowpass(x, cut)


def env(n, attack=0.004, decay=0.2, hold=0.0):
    """Linear attack (s), flat hold (s), then exponential decay with time constant decay (s)."""
    t = np.arange(n) / RATE
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    d = np.exp(-np.clip(t - attack - hold, 0, None) / max(decay, 1e-4))
    return a * d


def fade(x, ms=4):
    """Short ramps at both ends so a cue never starts or stops with a click."""
    k = min(len(x) // 2, int(RATE * ms / 1000))
    if k:
        r = np.linspace(0, 1, k)
        x = x.copy()
        x[:k] *= r
        x[-k:] *= r[::-1]
    return x


def crush(x, bits=6, hold=4):
    """Retro: sample-and-hold to RATE / hold and quantise to bits."""
    y = np.repeat(x[::hold], hold)[:len(x)]
    q = 2 ** (bits - 1)
    return np.round(y * q) / q


def crackle(dur, rng, rate=60):
    """Sparse random sparks (lightning): short noise bursts at rate per second."""
    n = _n(dur)
    out = np.zeros(n)
    for s in rng.integers(0, n, max(1, int(rate * dur))):
        k = int(rng.integers(40, 400))
        seg = rng.uniform(-1, 1, k) * np.exp(-np.arange(k) / (k / 4))
        out[s:s + k] += seg[:n - s]
    return out


def ring(freqs, dur, decay, rng):
    """Inharmonic partials that ring and decay (metal, ice, arcane)."""
    n = _n(dur)
    t = np.arange(n) / RATE
    out = np.zeros(n)
    for i, f in enumerate(freqs):
        ph = rng.uniform(0, 2 * np.pi)
        out += np.sin(2 * np.pi * f * t + ph) * np.exp(-t / (decay / (1 + 0.4 * i))) / (1 + i)
    return out


def _norm(x, peak=PEAK):
    m = np.abs(x).max()
    return x * (peak / m) if m > 0 else x


# ---- cue kinds ----------------------------------------------------------------------------------------------

def _wave(voice):
    return ("square", "tri") if voice == "retro" else ("sine", "sine")


def _color(x, dur, element, rng, bright, strength=1.0):
    """Adds the element's colour to a cue of length dur."""
    n = len(x)
    if element == "metal":
        x = x + 0.5 * strength * ring([1180 * bright, 1870, 2650, 3420], dur, 0.35 * dur + 0.08, rng)[:n]
    elif element == "lightning":
        x = x + 0.7 * strength * highpass(crackle(dur, rng, 90), 900)[:n] * env(n, 0.001, dur * 0.5)
    elif element == "fire":
        x = x + 0.6 * strength * lowpass(noise(dur, rng), 900 * bright)[:n] * env(n, 0.02, dur * 0.6)
    elif element == "ice":
        x = x + 0.4 * strength * ring([2400 * bright, 3610, 5020], dur, 0.25 * dur + 0.05, rng)[:n]
    elif element == "wind":
        x = x + 0.5 * strength * lowpass(highpass(noise(dur, rng), 500), 2600 * bright)[:n] * env(n, 0.03, dur * 0.5)
    elif element == "arcane":
        t = np.arange(n) / RATE
        x = x + 0.35 * strength * np.sin(2 * np.pi * 880 * bright * t + 3 * np.sin(2 * np.pi * 6 * t)) * env(n, 0.01, dur * 0.5)
    return x


def hit(weight, rng, voice="retro", element=None, bright=1.0):
    """A contact: a falling body tone, a noise crack and the element's colour; heavier is lower and longer."""
    w = WEIGHT_SOUND[weight]
    dur, n = w["dur"], _n(w["dur"])
    body_wave, _ = _wave(voice)
    body = osc(w["f0"], w["f1"], dur, body_wave) * env(n, 0.002, dur * 0.35)
    if voice == "retro":
        body = lowpass(body, 2500 * bright)
    crack = lowpass(noise(dur, rng), w["cut"] * bright) * env(n, 0.001, dur * 0.18)
    x = 0.8 * body + 0.9 * crack
    if weight in ("finisher", "blast"):  # a low thump under the big ones
        x += 0.8 * osc(70, 30, dur, "sine") * env(n, 0.003, dur * 0.4)
    return _color(x, dur, element, rng, bright)


def whoosh(dur, rng, voice="retro", element=None, bright=1.0):
    """Air moving: noise whose filter opens and closes over dur, loudest in the middle."""
    n = _n(dur)
    t = np.arange(n) / n
    shape = np.sin(np.pi * t) ** 2
    x = lowpass(noise(dur, rng), 300 + 3200 * bright * shape) * shape
    return _color(x, dur, element, rng, bright, 0.5)


def charge(dur, rng, voice="retro", element=None, bright=1.0):
    """Power gathering: a tone rising and a trembling noise swelling up to the end of dur."""
    n = _n(dur)
    t = np.arange(n) / n
    _, tone_wave = _wave(voice)
    rise = t ** 1.5
    trem = 0.6 + 0.4 * np.sin(2 * np.pi * np.cumsum(4 + 18 * t) / RATE)
    x = 0.6 * osc(110, 520 * bright, dur, tone_wave) * rise * trem
    x += 0.5 * lowpass(noise(dur, rng), 400 + 2800 * bright * rise) * rise
    return _color(x, dur, element, rng, bright, 0.6)


def tail(dur, rng, voice="retro", element=None, bright=1.0):
    """What is left: a soft shimmer of filtered noise and faint pings that dies over dur."""
    n = _n(dur)
    x = lowpass(noise(dur, rng), 1800 * bright) * env(n, 0.05, dur * 0.4)
    t = np.arange(n) / RATE
    for _ in range(max(2, int(dur * 6))):
        s, f = rng.uniform(0, dur * 0.8), rng.uniform(1500, 3500) * bright
        x += 0.25 * np.sin(2 * np.pi * f * t) * np.exp(-np.clip(t - s, 0, None) / 0.08) * (t >= s)
    return _color(x, dur, element, rng, bright, 0.4)


def boom(dur, rng, voice="retro", element=None, bright=1.0):
    """A blow that lands with no act hit: the blast hit stretched or cut to dur."""
    x = hit("blast", rng, voice, element, bright)
    n = _n(dur)
    return np.pad(x, (0, max(0, n - len(x))))[:n] * env(n, 0.001, dur * 0.5, hold=0.0) ** 0.3


def hum(dur, rng, voice="retro", element=None, bright=1.0):
    """A steady loop: two tones with a slow wobble, whole cycles only, so dur joins end to start."""
    n = _n(dur)
    t = np.arange(n) / RATE
    f = max(1, round(110 * dur)) / dur  # whole cycles over the loop
    wob = max(1, round(2 * dur)) / dur
    _, tone_wave = _wave(voice)
    x = 0.5 * np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t)
    x *= 0.75 + 0.25 * np.sin(2 * np.pi * wob * t)
    if element == "lightning":
        x += 0.3 * highpass(crackle(dur, rng, 25), 900)
    elif element in ("fire", "wind"):
        nz = lowpass(noise(dur + 0.05, rng), 700 * bright)
        k = _n(0.05)
        nz[:k] = nz[:k] * np.linspace(0, 1, k) + nz[n:n + k] * np.linspace(1, 0, k)  # cross-fade the wrap
        x += 0.5 * nz[:n]
    return x


# ---- physical models (voice "real") ------------------------------------------------------------------------
# Metal: a blade that lands is a thud, a short dense chink and grit (metal_hit); blade on blade (clash=True) is
# modal synthesis. A struck bar rings at the free-free modes of an Euler-Bernoulli beam; each mode is a
# damped sine, higher modes die faster, and each comes as a slightly detuned pair so the blade beats as it rings.
# Thunder: after Farnell (Designing Sound, Thunder) and Fineberg, Walters and Reiss (AES 2022): a crack of N-waves
# from the near channel, a rumble of N-waves arriving from ever further segments (lower, wider, weaker), a sub-boom
# of brown noise, and ground echoes.
BAR = (1.0, 2.756, 5.404, 8.933, 13.344)
METAL_F0 = {"light": 1500, "heavy": 820, "finisher": 520, "blast": 380}  # a small blade rings higher
METAL_DUR = {"light": 0.6, "heavy": 1.0, "finisher": 1.6, "blast": 1.4}
RUMBLE = {"light": 0.45, "heavy": 1.4, "finisher": 3.0, "blast": 2.4}    # s of rolling after the crack


def resonate(x, f, q):
    """A two-pole band-pass resonator at f Hz with quality q (peak gain 1)."""
    w = 2 * np.pi * min(f, RATE * 0.45) / RATE
    al = np.sin(w) / (2 * q)
    a0 = 1 + al
    b0, a1, a2 = al / a0, -2 * np.cos(w) / a0, (1 - al) / a0
    y, y1, y2, x2, x1 = [0.0] * len(x), 0.0, 0.0, 0.0, 0.0
    for i, v in enumerate(x.tolist()):
        o = b0 * v - b0 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, v, y1, o
        y[i] = o
    return np.array(y)


STAB_RING = {"light": 0.05, "heavy": 0.08, "finisher": 0.12, "blast": 0.11}  # s the steel's chink lasts


def metal_hit(weight, rng, bright=1.0):
    """A blade that lands (in the ground, a body, armour): a short dense chink of many inharmonic modes that die
    within a tenth of a second over a brief unpitched burst, and grit kicked up. Not a bell (no mode rings on its
    own) and not a drum (no pitched low body)."""
    w = WEIGHT_SOUND[weight]
    dur = w["dur"] + 0.1
    n = _n(dur)
    t = np.arange(n) / RATE
    # the blade going in: a short unpitched burst (no swept sine, which is how a kick drum is made)
    thud = highpass(lowpass(noise(dur, rng), 1800 * bright), 250) * env(n, 0.0005, 0.006 + 0.012 * dur)
    f0 = METAL_F0[weight] * rng.uniform(0.9, 1.1)
    base = STAB_RING[weight]
    chink = np.zeros(n)
    for f in f0 * np.exp(rng.uniform(0, np.log(9000 * min(bright, 1.2) / f0), 28)):
        chink += np.sin(2 * np.pi * f * t + rng.uniform(0, 6.3)) * np.exp(-t / (base * (f0 / f) ** 0.6)) * rng.uniform(0.2, 1)
    chink /= np.abs(chink).max() + 1e-9
    k = _n(0.012)
    click = highpass(rng.uniform(-1, 1, k), 1500) * np.exp(-np.arange(k) / (k / 4))
    grit = lowpass(highpass(crackle(min(dur, 0.08), rng, 220), 600), 5000 * bright)
    x = 0.45 * thud / (np.abs(thud).max() + 1e-9) + 1.0 * chink
    x[:k] += 0.8 * click
    x[:len(grit)] += 0.35 * grit / (np.abs(grit).max() + 1e-9) * env(len(grit), 0.002, 0.025)
    return x


def metal_clash(weight, rng, bright=1.0):
    """Blade on blade: the bar modes ring as beating pairs over a sharp strike click, a thump under heavy blows.
    A layer with clash=True uses it (a parry, a sword lock); it rings like struck steel, near a bell."""
    dur = METAL_DUR[weight]
    n = _n(dur)
    t = np.arange(n) / RATE
    f0 = METAL_F0[weight] * rng.uniform(0.97, 1.03)
    x = np.zeros(n)
    for i, ratio in enumerate(BAR):
        f = f0 * ratio
        if f > 15000 * min(bright, 1.0):
            break
        dec = dur * 0.4 / (1 + 0.8 * i)
        for det in (1.0, 1.0 + rng.uniform(0.002, 0.006)):
            x += np.sin(2 * np.pi * f * det * t + rng.uniform(0, 2 * np.pi)) * np.exp(-t / dec) * 0.5 / (1 + 0.6 * i)
    k = _n(0.004)
    click = highpass(rng.uniform(-1, 1, k), 2000) * np.linspace(1, 0, k)
    x[:k] += 1.2 * click
    if weight in ("heavy", "finisher", "blast"):
        x += 0.5 * osc(110, 45, dur, "sine") * env(n, 0.002, 0.08)
    return x


def metal_scrape(dur, rng, bright=1.0):
    """A blade drawn or swept: rough noise driving the bar modes, swelling and fading over dur."""
    n = _n(dur)
    tt = np.arange(n) / n
    shape = np.sin(np.pi * tt) ** 1.5
    grit = noise(dur, rng) * (1 + 0.8 * lowpass(noise(dur, rng), 40) * 8)
    f0 = rng.uniform(1000, 1300) * bright
    x = sum(resonate(grit, f0 * ratio, 45 + 10 * i) / (1 + 0.5 * i) for i, ratio in enumerate(BAR[:4]))
    return x * shape


def _nwaves(n, times, lengths, amps):
    """N-waves (a pressure jump falling linearly to its mirror) placed at times (s), lengths (s), amps."""
    out = np.zeros(n)
    for t0, L, a in zip(times, lengths, amps):
        s, k = int(t0 * RATE), max(2, int(L * RATE))
        if s >= n:
            continue
        seg = a * np.linspace(1, -1, k)[:n - s]
        out[s:s + len(seg)] += seg
    return out


def thunder(weight, rng, bright=1.0):
    """A strike's thunder: crack, rolling rumble, sub-boom and echoes; heavier rolls longer."""
    roll = RUMBLE[weight]
    dur = 0.1 + roll * 1.3
    n = _n(dur)
    k = int(12 + 25 * roll)                       # the near channel: a cluster of sharp N-waves
    crack = _nwaves(n, rng.exponential(0.015, k), rng.uniform(0.0003, 0.0015, k), rng.uniform(0.4, 1.0, k))
    crack = highpass(crack, 250)
    m = int(350 * roll)                           # far segments arrive later, smeared and weaker
    at = 0.04 + roll * rng.beta(1.4, 3.0, m)
    far = at / roll
    rumble = _nwaves(n, at, 0.001 + 0.014 * far * rng.uniform(0.5, 1.5, m), rng.uniform(0.2, 1, m) / (1 + 3 * far))
    rumble = lowpass(lowpass(rumble, 900 * bright), 1400)
    brown = np.cumsum(noise(dur, rng))
    brown -= lowpass(brown, 15)                   # keep it from drifting off
    sub = lowpass(lowpass(brown, 70), 90)
    sub = sub / (np.abs(sub).max() + 1e-9) * env(n, 0.03, roll * 0.45) * (1 + 0.6 * np.tanh(lowpass(noise(dur, rng), 4) * 40))
    x = 1.0 * crack / (np.abs(crack).max() + 1e-9) + 0.9 * rumble / (np.abs(rumble).max() + 1e-9) + 0.9 * sub
    for d, g in ((0.23, 0.3), (0.51, 0.18), (0.87, 0.1)):   # ground and hill echoes, duller each time
        s = _n(d)
        x[s:] += g * lowpass(x[:-s], 700)
    return x


def metal_gather(dur, rng, bright=1.0):
    """Blades being summoned: an airy swell with tiny steel glints that come faster toward the end. No tone."""
    n = _n(dur)
    tt = np.arange(n) / n
    x = 0.5 * lowpass(highpass(noise(dur, rng), 800), 2500 + 3500 * bright * tt) * tt ** 1.5
    t = np.arange(n) / RATE
    for _ in range(int(10 + 30 * dur)):
        s0 = dur * rng.uniform(0, 1) ** 0.5                # denser near the end
        k = int(s0 * RATE)
        m = min(n - k, _n(0.03))
        if m <= 0:
            continue
        f = rng.uniform(3000, 7000) * bright
        tick = np.sin(2 * np.pi * f * t[:m]) * np.exp(-t[:m] / 0.006) * rng.uniform(0.15, 0.4)
        x[k:k + m] += tick
    return x


def metal_settle(dur, rng, bright=1.0):
    """After the rain: dust falling back and a few small settling ticks, dying out. No ring."""
    n = _n(dur)
    x = 0.6 * lowpass(noise(dur, rng), 1200 * bright) * env(n, 0.01, dur * 0.3)
    t = np.arange(n) / RATE
    for _ in range(int(3 + 6 * dur)):
        k = int(rng.uniform(0, 0.6) * n)
        m = min(n - k, _n(0.02))
        f = rng.uniform(1500, 4000) * bright
        x[k:k + m] += np.sin(2 * np.pi * f * t[:m]) * np.exp(-t[:m] / 0.004) * rng.uniform(0.1, 0.3) * (1 - k / n)
    return x


def metal_fall(dur, rng, bright=1.0, weight="light"):
    """A blade dropping point first: air torn over the edge, a whistle that rises and swells, cut at the landing.
    A heavier blade whistles lower with a body of wind under it."""
    n = _n(dur)
    tt = np.arange(n) / n
    f0 = {"light": 2200, "heavy": 1300, "finisher": 800, "blast": 700}[weight] * rng.uniform(0.9, 1.1) * bright
    air = noise(dur, rng)
    whistle = resonate(air, f0 * (1 + 0.35 * tt[n // 2]), 6) + 0.6 * resonate(air, f0 * 2.1, 9)
    x = whistle / (np.abs(whistle).max() + 1e-9) * (0.15 + 0.85 * tt ** 2)
    if weight != "light":
        x += 0.7 * lowpass(air, 500) / (np.abs(lowpass(air, 500)).max() + 1e-9) * tt ** 1.5
    k = _n(0.004)
    x[-k:] *= np.linspace(1, 0, k)                         # the hit takes over on the landing
    return x


def fall(dur, rng, voice="retro", element=None, bright=1.0, weight="light"):
    """Something dropping onto its landing: noise whose filter opens as it nears, loudest at the end."""
    n = _n(dur)
    tt = np.arange(n) / n
    x = lowpass(noise(dur, rng), 600 + 4000 * bright * tt) * tt ** 2
    return _color(x, dur, element if element not in ("metal", "ice", "arcane") else None, rng, bright, 0.4)


def volley(lands, fps, fall_frames=3, weight="light", gain=0.35, jitter=0.008, seed=1, hits=True):
    """Layers for many projectiles that land (a sword rain, an arrow volley, hail): for each landing frame a fall
    over the fall_frames before it and, with hits, a hit on it, both at gain (many quiet ones read as a rain).
    jitter (s) spreads blows on one frame apart, seeded, so a wave is a clatter and not one blow."""
    rng = np.random.default_rng([seed, 77])
    out = []
    for f in lands:
        dt = float(rng.uniform(-jitter, jitter))
        land = max(0.0, f / fps + dt)
        dur = fall_frames / fps
        out.append(dict(kind="fall", t=round(max(0.0, land - dur), 4), frame=max(0, f - fall_frames),
                        dur=round(min(dur, land) or 1 / fps, 4), weight=weight, name=f"fall_{weight}", gain=gain))
        if hits:
            out.append(dict(kind="hit", t=round(land, 4), frame=int(f), weight=weight, name=f"volley_{weight}",
                            dur=WEIGHT_SOUND[weight]["dur"], gain=gain))
    return out


def real(layer, rng, element, bright):
    """The physical model for a layer in the real voice, or None when there is none (other elements use soft)."""
    kind = layer["kind"]
    if element == "metal":
        if kind == "hit":
            return (metal_clash if layer.get("clash") else metal_hit)(layer["weight"], rng, bright)
        if kind == "boom":
            return metal_hit("blast", rng, bright)
        if kind == "whoosh":
            return metal_scrape(layer["dur"], rng, bright) + 0.5 * whoosh(layer["dur"], rng, "soft", None, bright)
        if kind == "fall":
            return metal_fall(layer["dur"], rng, bright, layer.get("weight") or "light")
        if kind == "charge":
            return metal_gather(layer["dur"], rng, bright)
        if kind == "tail":
            return metal_settle(layer["dur"], rng, bright)
    if element == "lightning":
        if kind == "hit":
            return thunder(layer["weight"], rng, bright)
        if kind == "boom":
            return thunder("blast", rng, bright)
    return None


# ---- recorded samples (optional) ----------------------------------------------------------------------------
# A project may hold recordings in sounds/ (or BEANFX_SOUNDS): <element>_<kind>[_<weight>]*.wav, such as
# metal_hit_heavy_01.wav, lightning_hit_02.wav, metal_whoosh.wav, or <kind>[_<weight>]*.wav for any element. A
# cue that finds one uses it (picked by seed, onset trimmed to the cue's t, pitched by weight) with a little of
# its synthesised self under it. Use only recordings you may ship (CC0 or your own); the JSON lists the files.
PITCH = {"light": 1.25, "heavy": 1.0, "finisher": 0.85, "blast": 0.75}  # playback rate: a heavier hit plays lower
SAMPLE_MAX = 3.0
SAMPLE_SYNTH = 0.2  # share of the synthesised cue under a sample


def read_wav(path):
    """Any PCM WAV (8, 16, 24 or 32-bit, mono or stereo, any rate) as mono floats at RATE."""
    with wave.open(str(path), "rb") as f:
        ch, w, sr, raw = f.getnchannels(), f.getsampwidth(), f.getframerate(), f.readframes(f.getnframes())
    if w == 1:
        x = np.frombuffer(raw, np.uint8).astype(float) / 128 - 1
    elif w == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = np.where(v >= 1 << 23, v - (1 << 24), v).astype(float) / (1 << 23)
    else:
        x = np.frombuffer(raw, "<i2" if w == 2 else "<i4").astype(float) / (2 ** (8 * w - 1))
    x = x.reshape(-1, ch).mean(axis=1)
    return resample(x, sr / RATE)


def resample(x, rate):
    """x played at rate times its speed (linear interpolation): above 1 shorter and higher."""
    if abs(rate - 1) < 1e-9 or len(x) < 2:
        return x
    pos = np.arange(0, len(x) - 1, rate)
    return np.interp(pos, np.arange(len(x)), x)


def find_sample(folder, layer, element, rng):
    """The recording for a layer in folder, or None: the most specific name prefix with a match, picked by rng."""
    if not folder or not Path(folder).is_dir():
        return None
    names = sorted(p for p in Path(folder).glob("*.wav"))
    kind, w = layer["kind"], layer.get("weight")
    keys = ([f"{element}_{kind}_{w}"] if element and w else []) + ([f"{element}_{kind}"] if element else []) + \
        ([f"{kind}_{w}"] if w else []) + [kind]
    for key in keys:
        hit_ = [p for p in names if p.stem == key or p.stem.startswith(key + "_")]
        if key == kind or key == f"{element}_{kind}":   # a bare kind prefix must not swallow a weighted file
            hit_ = [p for p in hit_ if not w or not any(p.stem.startswith(f"{key}_{x}") for x in PITCH if x != w)]
        if hit_:
            return hit_[int(rng.integers(len(hit_)))]
    return None


def from_sample(path, layer):
    """A recording made into a cue: leading silence cut so the onset lands on t, pitched by weight, capped."""
    x = read_wav(path)
    m = np.abs(x).max()
    if m <= 0:
        return None
    start = int(np.argmax(np.abs(x) >= 0.05 * m))
    x = x[max(0, start - _n(0.001)):]
    w = layer.get("weight")
    if w and f"_{w}" not in Path(path).stem:
        x = resample(x, PITCH[w])   # a file named for its weight plays as it is
    if layer["kind"] in ("whoosh", "charge", "tail", "hum") and layer.get("dur"):
        x = resample(x, len(x) / _n(layer["dur"])) if len(x) > 1 else x   # fit the state's span
    return _norm(fade(x[:_n(SAMPLE_MAX)], 8))


def sounds_dir(out=None):
    """BEANFX_SOUNDS, else the project's sounds/ (out is drafts/<name>/out), else None."""
    import os
    if os.environ.get("BEANFX_SOUNDS"):
        return Path(os.environ["BEANFX_SOUNDS"])
    if out is not None:
        d = Path(out).resolve().parent.parent.parent / "sounds"
        return d if d.is_dir() else None
    return None


SYNTH = {"hit": None, "whoosh": whoosh, "charge": charge, "tail": tail, "boom": boom, "hum": hum, "fall": fall}


# ---- the effect's timeline ----------------------------------------------------------------------------------

def guess_weight(h):
    """The weight of a hit that names none, from its freeze and shake (nearest WEIGHTS row)."""
    if h.get("weight") in WEIGHT_SOUND:
        return h["weight"]
    import export as ex
    fz, sh = h.get("freeze", 0.1), h.get("shake", 0)
    return min(ex.WEIGHTS, key=lambda k: abs(ex.WEIGHTS[k]["freeze"] - fz) / 0.2 + abs(ex.WEIGHTS[k]["shake"] - sh) / 6)


def _bfx(js):
    return js["meta"]["beanfx"] if "meta" in js else js


def layers(js):
    """The sound layers of an effect from its JSON (an ex.write result): one dict per layer with kind, t (s from
    frame 0), dur (s), frame, and weight for hits. Edit and pass back as layers= to write() or track()."""
    b = _bfx(js)
    fps, n = b["fps"], b["frames"]
    hits = b.get("act", {}).get("hits", [])
    out = []
    for h in hits:
        w = guess_weight(h)
        out.append(dict(kind="hit", t=round(h["frame"] / fps, 4), frame=h["frame"], weight=w,
                        name=h.get("sound") or f"hit_{w}", dur=WEIGHT_SOUND[w]["dur"]))
    for s, (a, z) in (b.get("states") or {}).items():
        word = s.split("/")[-1].lower()
        kind = next((k for k, words in STATE_KIND.items() if any(x in word for x in words)), None)
        if kind in (None, "rest"):
            continue
        if kind == "boom" and any(a <= h["frame"] <= z for h in hits):
            continue  # the hit already sounds there
        dur = (z + 1 - a) / fps
        if kind == "tail":
            dur += 0.3  # let it ring out past the last frame
        if kind == "boom":
            dur = max(dur, 0.6)
        out.append(dict(kind=kind, t=round(a / fps, 4), frame=a, dur=round(dur, 4), name=kind))
    if not out and b.get("loop"):
        out.append(dict(kind="hum", t=0.0, frame=0, dur=round(n / fps, 4), name="hum"))
    return sorted(out, key=lambda L: (L["t"], L["kind"]))


def render(layer, seed=1, voice="retro", element=None, bright=1.0, index=0, sounds=None):
    """One layer's samples, normalised; the rng comes from seed and the layer's place so it is stable. With a
    sounds folder holding a matching recording, the cue is that recording (see find_sample); layer["source"] is set
    to "synth" or "sample:<file>"."""
    rng = np.random.default_rng([seed, index, KINDS.index(layer["kind"])])
    x = real(layer, rng, element, bright) if voice == "real" else None
    if x is None:
        v = "soft" if voice == "real" else voice
        if layer["kind"] == "hit":
            x = hit(layer["weight"], rng, v, element, bright)
        elif layer["kind"] == "fall":
            x = fall(layer["dur"], rng, v, element, bright, layer.get("weight") or "light")
        else:
            x = SYNTH[layer["kind"]](layer["dur"], rng, v, element, bright)
    if voice == "retro":
        x = crush(_norm(x))
    x = _norm(fade(x))
    layer["source"] = "synth"
    path = find_sample(sounds, layer, element, rng)
    smp = from_sample(path, layer) if path else None
    if smp is not None:
        mix = np.zeros(max(len(smp), len(x)))
        mix[:len(smp)] += smp
        mix[:len(x)] += SAMPLE_SYNTH * x
        x = _norm(fade(mix))
        layer["source"] = "sample:" + path.name
    return x


def track(js, seed=1, voice="retro", element=None, layers_=None, sounds=None):
    """The whole effect's sound on the sheet's timeline and the rendered cues: (samples, [(layer, samples)]).
    A loop wraps what runs past the end onto the start, so the track is exactly frames / fps long and joins."""
    if voice not in VOICES:
        raise ValueError(f"voice {voice!r} not in {VOICES}")
    if element not in ELEMENTS:
        raise ValueError(f"element {element!r} not in {ELEMENTS}")
    b = _bfx(js)
    bright = GLOW_BRIGHT.get(b.get("glow"), 1.0)
    ls = layers(js) if layers_ is None else layers_
    ls = [dict(L) for L in ls]
    cues = [(L, render(L, seed, voice, element, bright, i, sounds)) for i, L in enumerate(ls)]
    loop = bool(b.get("loop"))
    length = _n(b["frames"] / b["fps"])
    if not loop:
        length = max([length] + [_n(L["t"]) + len(x) for L, x in cues])
    mix = np.zeros(length)
    for L, x in cues:
        s = _n(L["t"]) if L["t"] > 0 else 0
        x = x * L.get("gain", GAIN[L["kind"]])
        if loop:
            idx = (s + np.arange(len(x))) % length
            np.add.at(mix, idx, x)
        else:
            mix[s:s + len(x)] += x
    mix = _norm(mix) if np.abs(mix).max() > 0 else mix
    return (mix if loop else fade(mix)), cues


def save(path, x):
    """16-bit mono WAV at RATE."""
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def load(path):
    with wave.open(str(path), "rb") as f:
        return np.frombuffer(f.readframes(f.getnframes()), "<i2").astype(float) / 32767


def write(out, name, js=None, seed=1, voice="retro", element=None, layers=None, sounds="auto"):
    """Writes <name>_sound.wav and one WAV per distinct cue into out, adds meta.beanfx.sound to <name>.json (and to
    js when given), names the cue on every act hit that had none, and returns the sound block. sounds: a folder of
    recordings, "auto" (BEANFX_SOUNDS or the project's sounds/) or None (synthesis only)."""
    out = Path(out)
    if sounds == "auto":
        sounds = sounds_dir(out)
    jp = out / f"{name}.json"
    if js is None:
        js = json.loads(jp.read_text())
    b = _bfx(js)
    mix, cues = track(js, seed, voice, element, layers, sounds)
    save(out / f"{name}_sound.wav", mix)
    files, listed = {}, []
    for L, x in cues:
        key = (L["name"], round(L["dur"], 3), L["source"])
        if key not in files:
            stem = L["name"] if L["name"] not in {k[0] for k in files} else f"{L['name']}_{len(files)}"
            files[key] = f"{name}_{stem}.wav"
            save(out / files[key], x)
        c = dict(name=L["name"], kind=L["kind"], t=L["t"], frame=L["frame"], file=files[key],
                 length=round(len(x) / RATE, 4), gain=L.get("gain", GAIN[L["kind"]]), source=L["source"])
        if L.get("weight"):
            c["weight"] = L["weight"]
        listed.append(c)
    for h in b.get("act", {}).get("hits", []):
        if not h.get("sound"):
            on = [c for c in listed if c["kind"] == "hit" and c["frame"] == h["frame"]]
            h["sound"] = next((c["name"] for c in on if not c["name"].startswith("volley_")), on[0]["name"])
    snd = dict(track=f"{name}_sound.wav", loop=bool(b.get("loop")), length=round(len(mix) / RATE, 4), rate=RATE,
               seed=seed, voice=voice, element=element, cues=listed)
    used = sorted({c["source"][7:] for c in listed if c["source"].startswith("sample:")})
    if used:
        snd["samples"] = used   # recordings from the sounds folder; credit them as their licence asks
    b["sound"] = snd
    if jp.exists():
        on_disk = json.loads(jp.read_text())
        ob = _bfx(on_disk)
        ob["sound"] = snd
        if "act" in b:
            ob["act"] = b["act"]
        jp.write_text(json.dumps(on_disk, indent=1))
    return snd


def check(out, js):
    """The problems of an effect's sound: missing files, a silent or clipping file, a track shorter than the sheet
    (or, for a loop, not exactly its length or with a jump at the seam), and hit cues off their hit by a frame."""
    out, b = Path(out), _bfx(js)
    snd = b.get("sound")
    if not snd:
        return []
    bad = []
    fps, sheet = b["fps"], b["frames"] / b["fps"]
    paths = [snd["track"]] + sorted({c["file"] for c in snd["cues"]})
    data = {}
    for p in paths:
        if not (out / p).exists():
            bad.append(f"sound: {p} is missing")
            continue
        x = data[p] = load(out / p)
        pk = np.abs(x).max()
        if pk < 0.05:
            bad.append(f"sound: {p} is silent (peak {pk:.3f})")
        if pk > 0.95:
            bad.append(f"sound: {p} clips (peak {pk:.3f})")
    x = data.get(snd["track"])
    if x is not None:
        L = len(x) / RATE
        if snd["loop"]:
            if abs(L - sheet) > 1 / RATE * 2:
                bad.append(f"sound: loop track is {L:.4f} s, the sheet loops every {sheet:.4f} s")
            step = np.percentile(np.abs(np.diff(x)), 99.5)
            if abs(x[-1] - x[0]) > max(4 * step, 0.02):
                bad.append(f"sound: loop track jumps {abs(x[-1] - x[0]):.3f} at the seam (99.5 % step {step:.3f})")
        elif L + 1e-6 < sheet:
            bad.append(f"sound: track is {L:.3f} s, shorter than the sheet's {sheet:.3f} s")
    for h in b.get("act", {}).get("hits", []):
        c = [c for c in snd["cues"] if c["kind"] == "hit" and c["frame"] == h["frame"]]
        if not c:
            bad.append(f"sound: no cue on the hit at frame {h['frame']}")
        elif abs(c[0]["t"] - h["frame"] / fps) > 1 / fps:
            bad.append(f"sound: cue {c[0]['name']} at {c[0]['t']} s is off the hit at frame {h['frame']}")
    return bad


def onset(x, t, fps, window=0.5):
    """The time (s) the sound first rises past half its peak within window s from t - one frame; for checks."""
    a = max(0, _n(t - 1 / fps)) if t > 1 / fps else 0
    seg = np.abs(x[a:a + _n(window)])
    k = _n(0.003)
    sm = np.convolve(seg, np.ones(k) / k, "same")
    i = int(np.argmax(sm >= 0.5 * sm.max()))
    return (a + i) / RATE
