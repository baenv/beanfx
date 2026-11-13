//! The synth parts, cue kinds and physical models of kit/sfx.py: the same draws in the same order and the
//! arithmetic in numpy's order (libm sin, exp and pow as numpy calls them; numpy's x**2 is x*x).

use crate::rng::Rng;
use std::f64::consts::PI;
use std::hint::black_box;

pub const RATE: f64 = 44100.0;
pub const PEAK: f64 = 0.8;
const TAU: f64 = 2.0 * PI;

/// One weight's hit: body sweep f0 to f1 (Hz), noise cutoff (Hz), length (s).
pub struct Weight {
    pub name: &'static str,
    pub f0: f64,
    pub f1: f64,
    pub cut: f64,
    pub dur: f64,
}

pub const WEIGHT_SOUND: [Weight; 4] = [
    Weight { name: "light", f0: 440.0, f1: 170.0, cut: 6500.0, dur: 0.2 },
    Weight { name: "heavy", f0: 230.0, f1: 62.0, cut: 3800.0, dur: 0.38 },
    Weight { name: "finisher", f0: 170.0, f1: 40.0, cut: 2800.0, dur: 0.7 },
    Weight { name: "blast", f0: 120.0, f1: 32.0, cut: 2000.0, dur: 0.9 },
];
pub const BAR: [f64; 5] = [1.0, 2.756, 5.404, 8.933, 13.344];
/// Per weight in WEIGHT_SOUND order (light, heavy, finisher, blast).
pub const METAL_F0: [f64; 4] = [1500.0, 820.0, 520.0, 380.0];
pub const METAL_DUR: [f64; 4] = [0.6, 1.0, 1.6, 1.4];
pub const RUMBLE: [f64; 4] = [0.45, 1.4, 3.0, 2.4];
pub const STAB_RING: [f64; 4] = [0.05, 0.08, 0.12, 0.11];
pub const FALL_F0: [f64; 4] = [2200.0, 1300.0, 800.0, 700.0];

pub fn wi(weight: &str) -> Result<usize, String> {
    WEIGHT_SOUND.iter().position(|w| w.name == weight).ok_or_else(|| format!("KeyError: '{weight}'"))
}

/// Python's round() to an int: ties to even.
pub fn pyround(x: f64) -> f64 {
    x.round_ties_even()
}

/// C pow as Python and numpy call it; black_box keeps LLVM from turning pow(x, 0.5) into sqrt.
pub fn pypow(x: f64, e: f64) -> f64 {
    x.powf(black_box(e))
}

pub fn n_of(dur: f64) -> usize {
    let r = pyround(dur * RATE);
    if r < 1.0 { 1 } else { r as usize }
}

fn ramp(n: usize, d: f64) -> Vec<f64> {
    (0..n).map(|i| i as f64 / d).collect()
}

/// np.linspace(a, b, k).
pub fn linspace(a: f64, b: f64, k: usize) -> Vec<f64> {
    if k == 0 {
        return vec![];
    }
    if k == 1 {
        return vec![a];
    }
    let step = (b - a) / (k - 1) as f64;
    let mut y: Vec<f64> = (0..k).map(|i| i as f64 * step + a).collect();
    y[k - 1] = b;
    y
}

fn add_into(x: &mut [f64], y: &[f64]) {
    for (a, b) in x.iter_mut().zip(y) {
        *a += b;
    }
}

fn mul(x: &[f64], y: &[f64]) -> Vec<f64> {
    x.iter().zip(y).map(|(a, b)| a * b).collect()
}

fn scale(k: f64, x: &[f64]) -> Vec<f64> {
    x.iter().map(|v| k * v).collect()
}

pub fn absmax(x: &[f64]) -> f64 {
    x.iter().fold(0.0f64, |m, v| if v.abs() > m { v.abs() } else { m })
}

fn cumsum(x: &[f64]) -> Vec<f64> {
    let mut s = 0.0;
    x.iter()
        .map(|v| {
            s += v;
            s
        })
        .collect()
}

/// A tone sweeping from f0 to f1 Hz (exponential) over dur s; wave sine, square, saw or tri.
pub fn osc(f0: f64, f1: f64, dur: f64, wave: &str) -> Vec<f64> {
    let n = n_of(dur);
    let r = f1 / f0;
    let f: Vec<f64> = ramp(n, n as f64).iter().map(|t| f0 * pypow(r, *t)).collect();
    let ph: Vec<f64> = cumsum(&f).iter().map(|c| c / RATE).collect();
    match wave {
        "square" => ph.iter().map(|p| if p % 1.0 < 0.5 { 1.0 } else { -1.0 }).collect(),
        "saw" => ph.iter().map(|p| 2.0 * (p % 1.0) - 1.0).collect(),
        "tri" => ph.iter().map(|p| 4.0 * ((p % 1.0) - 0.5).abs() - 1.0).collect(),
        _ => ph.iter().map(|p| (TAU * p).sin()).collect(),
    }
}

pub fn noise(dur: f64, rng: &mut Rng) -> Vec<f64> {
    rng.uniform_n(-1.0, 1.0, n_of(dur))
}

/// One-pole low-pass; cut in Hz, one value per sample (a sweep) or one for all.
pub fn lowpass_v(x: &[f64], cut: &[f64]) -> Vec<f64> {
    let mut v = 0.0;
    x.iter()
        .zip(cut.iter().cycle())
        .map(|(s, c)| {
            let a = 1.0 - (-TAU * c.clamp(20.0, RATE / 2.0) / RATE).exp();
            v += a * (s - v);
            v
        })
        .collect()
}

pub fn lowpass(x: &[f64], cut: f64) -> Vec<f64> {
    lowpass_v(x, &[cut])
}

pub fn highpass_v(x: &[f64], cut: &[f64]) -> Vec<f64> {
    let l = lowpass_v(x, cut);
    x.iter().zip(&l).map(|(a, b)| a - b).collect()
}

pub fn highpass(x: &[f64], cut: f64) -> Vec<f64> {
    highpass_v(x, &[cut])
}

/// Linear attack (s), flat hold (s), then exponential decay with time constant decay (s).
pub fn env(n: usize, attack: f64, decay: f64, hold: f64) -> Vec<f64> {
    let am = attack.max(1e-4);
    let dm = decay.max(1e-4);
    (0..n)
        .map(|i| {
            let t = i as f64 / RATE;
            let a = (t / am).clamp(0.0, 1.0);
            let d = (-(t - attack - hold).max(0.0) / dm).exp();
            a * d
        })
        .collect()
}

/// Short ramps at both ends so a cue never starts or stops with a click.
pub fn fade(x: &[f64], ms: f64) -> Vec<f64> {
    let k = (x.len() / 2).min((RATE * ms / 1000.0) as usize);
    let mut x = x.to_vec();
    if k > 0 {
        let r = linspace(0.0, 1.0, k);
        let len = x.len();
        for i in 0..k {
            x[i] *= r[i];
            x[len - k + i] *= r[k - 1 - i];
        }
    }
    x
}

/// Retro: sample-and-hold to RATE / hold and quantise to bits.
pub fn crush(x: &[f64], bits: i32, hold: usize) -> Vec<f64> {
    let q = 2f64.powi(bits - 1);
    (0..x.len()).map(|i| pyround(x[i / hold * hold] * q) / q).collect()
}

/// Sparse random sparks (lightning): short noise bursts at rate per second.
pub fn crackle(dur: f64, rng: &mut Rng, rate: f64) -> Vec<f64> {
    let n = n_of(dur);
    let mut out = vec![0.0; n];
    let count = ((rate * dur) as i64).max(1) as usize;
    for s in rng.integers_n(0, n as i64, count) {
        let s = s as usize;
        let k = rng.integers(40, 400) as usize;
        let kq = k as f64 / 4.0;
        let seg = rng.uniform_n(-1.0, 1.0, k);
        for i in 0..k.min(n - s) {
            out[s + i] += seg[i] * (-(i as f64) / kq).exp();
        }
    }
    out
}

/// Inharmonic partials that ring and decay (metal, ice, arcane).
pub fn ring(freqs: &[f64], dur: f64, decay: f64, rng: &mut Rng) -> Vec<f64> {
    let n = n_of(dur);
    let t = ramp(n, RATE);
    let mut out = vec![0.0; n];
    for (i, f) in freqs.iter().enumerate() {
        let ph = rng.uniform(0.0, TAU);
        let w = TAU * f;
        let dc = decay / (1.0 + 0.4 * i as f64);
        let div = (1 + i) as f64;
        for (o, tt) in out.iter_mut().zip(&t) {
            *o += (w * tt + ph).sin() * (-tt / dc).exp() / div;
        }
    }
    out
}

pub fn norm(x: &[f64], peak: f64) -> Vec<f64> {
    let m = absmax(x);
    if m > 0.0 {
        let k = peak / m;
        x.iter().map(|v| v * k).collect()
    } else {
        x.to_vec()
    }
}

// ---- cue kinds ----------------------------------------------------------------------------------------------

fn waves(voice: &str) -> (&'static str, &'static str) {
    if voice == "retro" { ("square", "tri") } else { ("sine", "sine") }
}

fn add_head(x: Vec<f64>, y: impl Iterator<Item = f64>) -> Vec<f64> {
    let mut x = x;
    for (a, b) in x.iter_mut().zip(y) {
        *a += b;
    }
    x
}

/// Adds the element's colour to a cue of length dur.
pub fn color(x: Vec<f64>, dur: f64, element: Option<&str>, rng: &mut Rng, bright: f64, strength: f64) -> Vec<f64> {
    let n = x.len();
    match element {
        Some("metal") => {
            let r = ring(&[1180.0 * bright, 1870.0, 2650.0, 3420.0], dur, 0.35 * dur + 0.08, rng);
            let k = 0.5 * strength;
            add_head(x, r.into_iter().map(|v| k * v))
        }
        Some("lightning") => {
            let h = highpass(&crackle(dur, rng, 90.0), 900.0);
            let e = env(n, 0.001, dur * 0.5, 0.0);
            let k = 0.7 * strength;
            add_head(x, h.into_iter().zip(e).map(|(a, b)| k * a * b))
        }
        Some("fire") => {
            let l = lowpass(&noise(dur, rng), 900.0 * bright);
            let e = env(n, 0.02, dur * 0.6, 0.0);
            let k = 0.6 * strength;
            add_head(x, l.into_iter().zip(e).map(|(a, b)| k * a * b))
        }
        Some("ice") => {
            let r = ring(&[2400.0 * bright, 3610.0, 5020.0], dur, 0.25 * dur + 0.05, rng);
            let k = 0.4 * strength;
            add_head(x, r.into_iter().map(|v| k * v))
        }
        Some("wind") => {
            let l = lowpass(&highpass(&noise(dur, rng), 500.0), 2600.0 * bright);
            let e = env(n, 0.03, dur * 0.5, 0.0);
            let k = 0.5 * strength;
            add_head(x, l.into_iter().zip(e).map(|(a, b)| k * a * b))
        }
        Some("arcane") => {
            let e = env(n, 0.01, dur * 0.5, 0.0);
            let w = TAU * 880.0 * bright;
            let k = 0.35 * strength;
            add_head(x, (0..n).map(|i| {
                let t = i as f64 / RATE;
                k * (w * t + 3.0 * (TAU * 6.0 * t).sin()).sin() * e[i]
            }))
        }
        _ => x,
    }
}

/// A contact: a falling body tone, a noise crack and the element's colour; heavier is lower and longer.
pub fn hit(weight: &str, rng: &mut Rng, voice: &str, element: Option<&str>, bright: f64) -> Result<Vec<f64>, String> {
    let w = &WEIGHT_SOUND[wi(weight)?];
    let (dur, n) = (w.dur, n_of(w.dur));
    let mut body = mul(&osc(w.f0, w.f1, dur, waves(voice).0), &env(n, 0.002, dur * 0.35, 0.0));
    if voice == "retro" {
        body = lowpass(&body, 2500.0 * bright);
    }
    let crack = mul(&lowpass(&noise(dur, rng), w.cut * bright), &env(n, 0.001, dur * 0.18, 0.0));
    let mut x: Vec<f64> = body.iter().zip(&crack).map(|(b, c)| 0.8 * b + 0.9 * c).collect();
    if weight == "finisher" || weight == "blast" {
        let th = mul(&scale(0.8, &osc(70.0, 30.0, dur, "sine")), &env(n, 0.003, dur * 0.4, 0.0));
        add_into(&mut x, &th);
    }
    Ok(color(x, dur, element, rng, bright, 1.0))
}

/// Air moving: noise whose filter opens and closes over dur, loudest in the middle.
pub fn whoosh(dur: f64, rng: &mut Rng, element: Option<&str>, bright: f64) -> Vec<f64> {
    let n = n_of(dur);
    let shape: Vec<f64> = ramp(n, n as f64).iter().map(|t| (PI * t).sin()).map(|s| s * s).collect();
    let k = 3200.0 * bright;
    let cut: Vec<f64> = shape.iter().map(|s| 300.0 + k * s).collect();
    let x = mul(&lowpass_v(&noise(dur, rng), &cut), &shape);
    color(x, dur, element, rng, bright, 0.5)
}

/// Power gathering: a tone rising and a trembling noise swelling up to the end of dur.
pub fn charge(dur: f64, rng: &mut Rng, voice: &str, element: Option<&str>, bright: f64) -> Vec<f64> {
    let n = n_of(dur);
    let t = ramp(n, n as f64);
    let rise: Vec<f64> = t.iter().map(|v| pypow(*v, 1.5)).collect();
    let c = cumsum(&t.iter().map(|v| 4.0 + 18.0 * v).collect::<Vec<_>>());
    let trem: Vec<f64> = c.iter().map(|v| 0.6 + 0.4 * (TAU * v / RATE).sin()).collect();
    let o = osc(110.0, 520.0 * bright, dur, waves(voice).1);
    let mut x: Vec<f64> = (0..n).map(|i| 0.6 * o[i] * rise[i] * trem[i]).collect();
    let k = 2800.0 * bright;
    let cut: Vec<f64> = rise.iter().map(|r| 400.0 + k * r).collect();
    let l = lowpass_v(&noise(dur, rng), &cut);
    for i in 0..n {
        x[i] += 0.5 * l[i] * rise[i];
    }
    color(x, dur, element, rng, bright, 0.6)
}

/// What is left: a soft shimmer of filtered noise and faint pings that dies over dur.
pub fn tail(dur: f64, rng: &mut Rng, element: Option<&str>, bright: f64) -> Vec<f64> {
    let n = n_of(dur);
    let mut x = mul(&lowpass(&noise(dur, rng), 1800.0 * bright), &env(n, 0.05, dur * 0.4, 0.0));
    let t = ramp(n, RATE);
    for _ in 0..((dur * 6.0) as i64).max(2) {
        let s = rng.uniform(0.0, dur * 0.8);
        let f = rng.uniform(1500.0, 3500.0) * bright;
        let w = TAU * f;
        for i in 0..n {
            let on = if t[i] >= s { 1.0 } else { 0.0 };
            x[i] += 0.25 * (w * t[i]).sin() * (-(t[i] - s).max(0.0) / 0.08).exp() * on;
        }
    }
    color(x, dur, element, rng, bright, 0.4)
}

/// A blow that lands with no act hit: the blast hit stretched or cut to dur.
pub fn boom(dur: f64, rng: &mut Rng, voice: &str, element: Option<&str>, bright: f64) -> Result<Vec<f64>, String> {
    let x = hit("blast", rng, voice, element, bright)?;
    let n = n_of(dur);
    let e = env(n, 0.001, dur * 0.5, 0.0);
    Ok((0..n).map(|i| x.get(i).copied().unwrap_or(0.0) * pypow(e[i], 0.3)).collect())
}

/// A steady loop: two tones with a slow wobble, whole cycles only, so dur joins end to start.
pub fn hum(dur: f64, rng: &mut Rng, element: Option<&str>, bright: f64) -> Result<Vec<f64>, String> {
    let n = n_of(dur);
    let t = ramp(n, RATE);
    let f = pyround(110.0 * dur).max(1.0) / dur;
    let wob = pyround(2.0 * dur).max(1.0) / dur;
    let (w1, w2, w3) = (TAU * f, TAU * 2.0 * f, TAU * wob);
    let mut x: Vec<f64> = t
        .iter()
        .map(|t| (0.5 * (w1 * t).sin() + 0.25 * (w2 * t).sin()) * (0.75 + 0.25 * (w3 * t).sin()))
        .collect();
    if element == Some("lightning") {
        let h = highpass(&crackle(dur, rng, 25.0), 900.0);
        add_into(&mut x, &scale(0.3, &h));
    } else if matches!(element, Some("fire") | Some("wind")) {
        let mut nz = lowpass(&noise(dur + 0.05, rng), 700.0 * bright);
        let k = n_of(0.05);
        if nz.len() < n + k {
            return Err(format!("ValueError: the hum wrap needs {} samples, the noise has {}", n + k, nz.len()));
        }
        let (up, down) = (linspace(0.0, 1.0, k), linspace(1.0, 0.0, k));
        for i in 0..k {
            nz[i] = nz[i] * up[i] + nz[n + i] * down[i];
        }
        for i in 0..n {
            x[i] += 0.5 * nz[i];
        }
    }
    Ok(x)
}

// ---- physical models (voice "real") ------------------------------------------------------------------------

/// A two-pole band-pass resonator at f Hz with quality q (peak gain 1).
pub fn resonate(x: &[f64], f: f64, q: f64) -> Vec<f64> {
    let w = TAU * f.min(RATE * 0.45) / RATE;
    let al = w.sin() / (2.0 * q);
    let a0 = 1.0 + al;
    let (b0, a1, a2) = (al / a0, -2.0 * w.cos() / a0, (1.0 - al) / a0);
    let (mut y1, mut y2, mut x2, mut x1) = (0.0, 0.0, 0.0, 0.0);
    x.iter()
        .map(|&v| {
            let o = b0 * v - b0 * x2 - a1 * y1 - a2 * y2;
            x2 = x1;
            x1 = v;
            y2 = y1;
            y1 = o;
            o
        })
        .collect()
}

/// A blade that lands: a short dense chink of many inharmonic modes over a brief unpitched burst, and grit.
pub fn metal_hit(weight: &str, rng: &mut Rng, bright: f64) -> Result<Vec<f64>, String> {
    let wix = wi(weight)?;
    let dur = WEIGHT_SOUND[wix].dur + 0.1;
    let n = n_of(dur);
    let t = ramp(n, RATE);
    let thud = mul(&highpass(&lowpass(&noise(dur, rng), 1800.0 * bright), 250.0), &env(n, 0.0005, 0.006 + 0.012 * dur, 0.0));
    let f0 = METAL_F0[wix] * rng.uniform(0.9, 1.1);
    let base = STAB_RING[wix];
    let mut chink = vec![0.0; n];
    let top = (9000.0 * bright.min(1.2) / f0).ln();
    for e in rng.uniform_n(0.0, top, 28) {
        let f = f0 * e.exp();
        let ph = rng.uniform(0.0, 6.3);
        let w = TAU * f;
        let dc = base * pypow(f0 / f, 0.6);
        let g = rng.uniform(0.2, 1.0);
        for i in 0..n {
            chink[i] += (w * t[i] + ph).sin() * (-t[i] / dc).exp() * g;
        }
    }
    let cm = absmax(&chink) + 1e-9;
    chink.iter_mut().for_each(|v| *v /= cm);
    let k = n_of(0.012);
    let kq = k as f64 / 4.0;
    let click: Vec<f64> =
        highpass(&rng.uniform_n(-1.0, 1.0, k), 1500.0).iter().enumerate().map(|(i, v)| v * (-(i as f64) / kq).exp()).collect();
    let grit = lowpass(&highpass(&crackle(dur.min(0.08), rng, 220.0), 600.0), 5000.0 * bright);
    let tm = absmax(&thud) + 1e-9;
    let mut x: Vec<f64> = thud.iter().zip(&chink).map(|(a, c)| 0.45 * a / tm + 1.0 * c).collect();
    for i in 0..k {
        x[i] += 0.8 * click[i];
    }
    let gm = absmax(&grit) + 1e-9;
    let ge = env(grit.len(), 0.002, 0.025, 0.0);
    for i in 0..grit.len() {
        x[i] += 0.35 * grit[i] / gm * ge[i];
    }
    Ok(x)
}

/// Blade on blade: the bar modes ring as beating pairs over a sharp strike click, a thump under heavy blows.
pub fn metal_clash(weight: &str, rng: &mut Rng, bright: f64) -> Result<Vec<f64>, String> {
    let wix = wi(weight)?;
    let dur = METAL_DUR[wix];
    let n = n_of(dur);
    let t = ramp(n, RATE);
    let f0 = METAL_F0[wix] * rng.uniform(0.97, 1.03);
    let mut x = vec![0.0; n];
    for (i, ratio) in BAR.iter().enumerate() {
        let f = f0 * ratio;
        if f > 15000.0 * bright.min(1.0) {
            break;
        }
        let dec = dur * 0.4 / (1.0 + 0.8 * i as f64);
        let div = 1.0 + 0.6 * i as f64;
        for det in [1.0, 1.0 + rng.uniform(0.002, 0.006)] {
            let ph = rng.uniform(0.0, TAU);
            let w = TAU * f * det;
            for j in 0..n {
                x[j] += (w * t[j] + ph).sin() * (-t[j] / dec).exp() * 0.5 / div;
            }
        }
    }
    let k = n_of(0.004);
    let click = mul(&highpass(&rng.uniform_n(-1.0, 1.0, k), 2000.0), &linspace(1.0, 0.0, k));
    for i in 0..k {
        x[i] += 1.2 * click[i];
    }
    if weight != "light" {
        let th = mul(&scale(0.5, &osc(110.0, 45.0, dur, "sine")), &env(n, 0.002, 0.08, 0.0));
        add_into(&mut x, &th);
    }
    Ok(x)
}

/// A blade drawn or swept: rough noise driving the bar modes, swelling and fading over dur.
pub fn metal_scrape(dur: f64, rng: &mut Rng, bright: f64) -> Vec<f64> {
    let n = n_of(dur);
    let shape: Vec<f64> = ramp(n, n as f64).iter().map(|t| pypow((PI * t).sin(), 1.5)).collect();
    let a = noise(dur, rng);
    let l = lowpass(&noise(dur, rng), 40.0);
    let grit: Vec<f64> = a.iter().zip(&l).map(|(a, l)| a * (1.0 + 0.8 * l * 8.0)).collect();
    let f0 = rng.uniform(1000.0, 1300.0) * bright;
    let mut x = vec![0.0; n];
    for (i, ratio) in BAR[..4].iter().enumerate() {
        let r = resonate(&grit, f0 * ratio, 45.0 + 10.0 * i as f64);
        let d = 1.0 + 0.5 * i as f64;
        for j in 0..n {
            x[j] += r[j] / d;
        }
    }
    mul(&x, &shape)
}

/// N-waves (a pressure jump falling linearly to its mirror) placed at times (s), lengths (s), amps.
pub fn nwaves(n: usize, times: &[f64], lengths: &[f64], amps: &[f64]) -> Vec<f64> {
    let mut out = vec![0.0; n];
    for ((t0, l), a) in times.iter().zip(lengths).zip(amps) {
        let s = (t0 * RATE) as i64;
        let k = ((l * RATE) as i64).max(2) as usize;
        if s >= n as i64 {
            continue;
        }
        let s = s.max(0) as usize;
        let seg = linspace(1.0, -1.0, k);
        for i in 0..k.min(n - s) {
            out[s + i] += a * seg[i];
        }
    }
    out
}

/// A strike's thunder: crack, rolling rumble, sub-boom and echoes; heavier rolls longer.
pub fn thunder(weight: &str, rng: &mut Rng, bright: f64) -> Result<Vec<f64>, String> {
    let roll = RUMBLE[wi(weight)?];
    let dur = 0.1 + roll * 1.3;
    let n = n_of(dur);
    let k = (12.0 + 25.0 * roll) as usize;
    let times = rng.exponential_n(0.015, k);
    let lens = rng.uniform_n(0.0003, 0.0015, k);
    let amps = rng.uniform_n(0.4, 1.0, k);
    let crack = highpass(&nwaves(n, &times, &lens, &amps), 250.0);
    let m = (350.0 * roll) as usize;
    let at: Vec<f64> = rng.beta_n(1.4, 3.0, m).iter().map(|b| 0.04 + roll * b).collect();
    let far: Vec<f64> = at.iter().map(|a| a / roll).collect();
    let lens: Vec<f64> = rng.uniform_n(0.5, 1.5, m).iter().zip(&far).map(|(u, f)| 0.001 + 0.014 * f * u).collect();
    let amps: Vec<f64> = rng.uniform_n(0.2, 1.0, m).iter().zip(&far).map(|(u, f)| u / (1.0 + 3.0 * f)).collect();
    let rumble = lowpass(&lowpass(&nwaves(n, &at, &lens, &amps), 900.0 * bright), 1400.0);
    let mut brown = cumsum(&noise(dur, rng));
    let lb = lowpass(&brown, 15.0);
    for (b, l) in brown.iter_mut().zip(&lb) {
        *b -= l;
    }
    let sub = lowpass(&lowpass(&brown, 70.0), 90.0);
    let sm = absmax(&sub) + 1e-9;
    let e = env(n, 0.03, roll * 0.45, 0.0);
    let wob = lowpass(&noise(dur, rng), 4.0);
    let sub: Vec<f64> = (0..n).map(|i| sub[i] / sm * e[i] * (1.0 + 0.6 * (wob[i] * 40.0).tanh())).collect();
    let (cm, rm) = (absmax(&crack) + 1e-9, absmax(&rumble) + 1e-9);
    let mut x: Vec<f64> = (0..n).map(|i| 1.0 * crack[i] / cm + 0.9 * rumble[i] / rm + 0.9 * sub[i]).collect();
    for (d, g) in [(0.23, 0.3), (0.51, 0.18), (0.87, 0.1)] {
        let s = n_of(d);
        if s >= n {
            continue;
        }
        let l = lowpass(&x[..n - s], 700.0);
        for i in 0..n - s {
            x[s + i] += g * l[i];
        }
    }
    Ok(x)
}

/// Blades being summoned: an airy swell with tiny steel glints that come faster toward the end. No tone.
pub fn metal_gather(dur: f64, rng: &mut Rng, bright: f64) -> Vec<f64> {
    let n = n_of(dur);
    let tt = ramp(n, n as f64);
    let k = 3500.0 * bright;
    let cut: Vec<f64> = tt.iter().map(|t| 2500.0 + k * t).collect();
    let l = lowpass_v(&highpass(&noise(dur, rng), 800.0), &cut);
    let mut x: Vec<f64> = l.iter().zip(&tt).map(|(l, t)| 0.5 * l * pypow(*t, 1.5)).collect();
    let t = ramp(n, RATE);
    for _ in 0..(10.0 + 30.0 * dur) as i64 {
        let s0 = dur * pypow(rng.uniform(0.0, 1.0), 0.5);
        let k = (s0 * RATE) as i64;
        let m = (n as i64 - k).min(n_of(0.03) as i64);
        if m <= 0 {
            continue;
        }
        let f = rng.uniform(3000.0, 7000.0) * bright;
        let w = TAU * f;
        let g = rng.uniform(0.15, 0.4);
        for i in 0..m as usize {
            x[k as usize + i] += (w * t[i]).sin() * (-t[i] / 0.006).exp() * g;
        }
    }
    x
}

/// After the rain: dust falling back and a few small settling ticks, dying out. No ring.
pub fn metal_settle(dur: f64, rng: &mut Rng, bright: f64) -> Vec<f64> {
    let n = n_of(dur);
    let l = lowpass(&noise(dur, rng), 1200.0 * bright);
    let e = env(n, 0.01, dur * 0.3, 0.0);
    let mut x: Vec<f64> = l.iter().zip(&e).map(|(l, e)| 0.6 * l * e).collect();
    let t = ramp(n, RATE);
    for _ in 0..(3.0 + 6.0 * dur) as i64 {
        let k = (rng.uniform(0.0, 0.6) * n as f64) as usize;
        let m = (n - k).min(n_of(0.02));
        let f = rng.uniform(1500.0, 4000.0) * bright;
        let w = TAU * f;
        let g = rng.uniform(0.1, 0.3);
        let fall = 1.0 - k as f64 / n as f64;
        for i in 0..m {
            x[k + i] += (w * t[i]).sin() * (-t[i] / 0.004).exp() * g * fall;
        }
    }
    x
}

/// A blade dropping point first: a whistle that rises and swells, cut at the landing.
pub fn metal_fall(dur: f64, rng: &mut Rng, bright: f64, weight: &str) -> Result<Vec<f64>, String> {
    let n = n_of(dur);
    let tt = ramp(n, n as f64);
    let f0 = FALL_F0[wi(weight)?] * rng.uniform(0.9, 1.1) * bright;
    let air = noise(dur, rng);
    let a = resonate(&air, f0 * (1.0 + 0.35 * tt[n / 2]), 6.0);
    let b = resonate(&air, f0 * 2.1, 9.0);
    let whistle: Vec<f64> = a.iter().zip(&b).map(|(a, b)| a + 0.6 * b).collect();
    let wm = absmax(&whistle) + 1e-9;
    let mut x: Vec<f64> = whistle.iter().zip(&tt).map(|(w, t)| w / wm * (0.15 + 0.85 * (t * t))).collect();
    if weight != "light" {
        let l = lowpass(&air, 500.0);
        let lm = absmax(&l) + 1e-9;
        for i in 0..n {
            x[i] += 0.7 * l[i] / lm * pypow(tt[i], 1.5);
        }
    }
    let k = n_of(0.004).min(n);
    let r = linspace(1.0, 0.0, k);
    for i in 0..k {
        x[n - k + i] *= r[i];
    }
    Ok(x)
}

/// Something dropping onto its landing: noise whose filter opens as it nears, loudest at the end.
pub fn fall(dur: f64, rng: &mut Rng, element: Option<&str>, bright: f64) -> Vec<f64> {
    let n = n_of(dur);
    let tt = ramp(n, n as f64);
    let k = 4000.0 * bright;
    let cut: Vec<f64> = tt.iter().map(|t| 600.0 + k * t).collect();
    let x: Vec<f64> = lowpass_v(&noise(dur, rng), &cut).iter().zip(&tt).map(|(l, t)| l * (t * t)).collect();
    let el = if matches!(element, Some("metal") | Some("ice") | Some("arcane")) { None } else { element };
    color(x, dur, el, rng, bright, 0.4)
}
