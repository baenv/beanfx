//! Port of tests/test_sfx.py: seeded bytes, levels, hit timing, weights, loop length and seam, the JSON block and
//! check(). Spectra come from a radix-2 FFT padded to a power of two, so frequency bins are finer than numpy's rfft
//! on the exact length; every spectral check keeps the Python thresholds.

mod common;

use beanfx::ex::{self, Hit, Write as ExWrite};
use beanfx::rng::{default_rng, Rng};
use beanfx::serde_json::{json, Value};
use beanfx::sfx::{self, RATE};
use ndarray::Array3;
use std::f64::consts::PI;
use std::fs;
use std::path::Path;

const FPS: f64 = 24.0;

fn blank() -> Vec<Array3<u8>> {
    (0..36).map(|_| {
        let mut f = Array3::<u8>::zeros((8, 8, 4));
        for y in 3..5 {
            for x in 3..5 {
                for c in 0..4 {
                    f[[y, x, c]] = 255;
                }
            }
        }
        f
    }).collect()
}

fn hit(frame: i64, o: Hit) -> Value {
    ex::hit(frame, FPS, o)
}

fn weighted(frame: i64, w: &str) -> Value {
    hit(frame, Hit { weight: Some(w.into()), ..Default::default() })
}

fn write_sheet(dir: &Path, name: &str, frames: &[Array3<u8>], looped: bool, o: ExWrite) -> Value {
    ex::write(dir, name, frames, FPS, [4.0, 4.0], looped, o).unwrap()
}

fn sw(seed: u64, voice: &str, element: Option<&str>) -> sfx::Write {
    sfx::Write { seed, voice: voice.into(), element: element.map(String::from), sounds: None, ..Default::default() }
}

fn render(layer: Value, seed: u64, voice: &str, element: Option<&str>) -> Vec<f64> {
    let mut l = layer;
    sfx::render(&mut l, seed, voice, element, 1.0, 0, None).unwrap()
}

fn absmax(x: &[f64]) -> f64 {
    x.iter().fold(0.0, |m, v| v.abs().max(m))
}

fn n(dur: f64) -> usize {
    sfx::n_of(dur)
}

fn has(p: &[String], s: &str) -> bool {
    p.iter().any(|x| x.contains(s))
}

// ---- spectra -----------------------------------------------------------------------------------------------

fn fft(re: &mut [f64], im: &mut [f64]) {
    let len = re.len();
    let mut j = 0;
    for i in 1..len {
        let mut bit = len >> 1;
        while j & bit != 0 {
            j ^= bit;
            bit >>= 1;
        }
        j ^= bit;
        if i < j {
            re.swap(i, j);
            im.swap(i, j);
        }
    }
    let mut size = 2;
    while size <= len {
        let ang = -2.0 * PI / size as f64;
        for start in (0..len).step_by(size) {
            for k in 0..size / 2 {
                let (wr, wi) = ((ang * k as f64).cos(), (ang * k as f64).sin());
                let (a, b) = (start + k, start + k + size / 2);
                let (tr, ti) = (re[b] * wr - im[b] * wi, re[b] * wi + im[b] * wr);
                re[b] = re[a] - tr;
                im[b] = im[a] - ti;
                re[a] += tr;
                im[a] += ti;
            }
        }
        size <<= 1;
    }
}

/// Magnitudes of the one-sided spectrum and the frequency of each bin.
fn spectrum(y: &[f64]) -> (Vec<f64>, Vec<f64>) {
    let len = y.len().next_power_of_two();
    let mut re = vec![0.0; len];
    re[..y.len()].copy_from_slice(y);
    let mut im = vec![0.0; len];
    fft(&mut re, &mut im);
    let mag: Vec<f64> = (0..=len / 2).map(|i| re[i].hypot(im[i])).collect();
    let fr: Vec<f64> = (0..=len / 2).map(|i| i as f64 * RATE / len as f64).collect();
    (mag, fr)
}

fn centroid(y: &[f64]) -> f64 {
    let (s, f) = spectrum(y);
    s.iter().zip(&f).map(|(a, b)| a * b).sum::<f64>() / s.iter().sum::<f64>()
}

fn peaks(y: &[f64], k: usize) -> Vec<f64> {
    let m = y.len();
    let hann: Vec<f64> = (0..m).map(|i| y[i] * (0.5 - 0.5 * (2.0 * PI * i as f64 / (m - 1) as f64).cos())).collect();
    let (s, f) = spectrum(&hann);
    let mut idx: Vec<usize> = (0..s.len()).collect();
    idx.sort_by(|&a, &b| s[b].partial_cmp(&s[a]).unwrap());
    let mut out: Vec<f64> = vec![];
    for i in idx {
        if out.iter().all(|g| (f[i] - g).abs() > 40.0) {
            out.push(f[i]);
        }
        if out.len() == k {
            break;
        }
    }
    out
}

/// s from the loudest point until the level falls 40 dB.
fn t60(y: &[f64]) -> f64 {
    let len = y.len();
    let mut pre = vec![0.0; len + 1];
    for i in 0..len {
        pre[i + 1] = pre[i] + y[i] * y[i];
    }
    let e: Vec<f64> = (0..len).map(|i| (pre[(i + 221).min(len)] - pre[i.saturating_sub(220)]) / 441.0).collect();
    let (pk, emax) = e.iter().enumerate().fold((0, 0.0), |a, (i, &v)| if v > a.1 { (i, v) } else { a });
    let after = (pk..len).find(|&i| 10.0 * (e[i] / emax + 1e-12).log10() < -40.0);
    after.map(|i| i - pk).unwrap_or(len - pk) as f64 / RATE
}

/// Share of the energy above 500 Hz held in its k strongest tones: near 1 for a bell, low for a clatter.
fn tonal(y: &[f64], k: usize) -> f64 {
    let y = sfx::highpass(&sfx::highpass(y, 500.0), 500.0);
    let (s, f) = spectrum(&y);
    let p2: Vec<f64> = s.iter().map(|v| v * v).collect();
    let tones: f64 = peaks(&y, k).iter().map(|p| p2.iter().zip(&f).filter(|(_, &fr)| fr > p - 15.0 && fr < p + 15.0).map(|(v, _)| v).sum::<f64>()).sum();
    tones / p2.iter().sum::<f64>()
}

fn low_share(y: &[f64]) -> f64 {
    let (s, f) = spectrum(y);
    let p2: Vec<f64> = s.iter().map(|v| v * v).collect();
    p2.iter().zip(&f).filter(|(_, &fr)| fr < 250.0).map(|(v, _)| v).sum::<f64>() / p2.iter().sum::<f64>()
}

fn bfx(js: &Value) -> Value {
    js["meta"]["beanfx"].clone()
}

fn onset_ok(x: &[f64], js: &Value, window: f64) {
    for h in js["meta"]["beanfx"]["act"]["hits"].as_array().unwrap() {
        let t = h["t"].as_f64().unwrap();
        let on = sfx::onset(x, t, FPS, window);
        assert!((on - t).abs() <= 1.0 / FPS, "hit at frame {} sounds at {on:.3} s (t {t:.3})", h["frame"]);
    }
}

// ---- tests -------------------------------------------------------------------------------------------------

#[test]
fn layers_track_and_bytes() {
    let tmp = common::tmpdir("sfx_a");
    let blank = blank();
    let hits = vec![weighted(10, "light"), hit(24, Hit { freeze: Some(0.25), shake: Some(6.0), ..Default::default() })];
    let mut js = write_sheet(&tmp.join("a"), "fx", &blank, false, ExWrite {
        hits,
        states: vec![("charge".into(), [0, 9]), ("slash".into(), [10, 23]), ("dissolve".into(), [24, 35])],
        extra: Some(json!({"glow": "strong"})),
        ..Default::default()
    });
    let ls = sfx::layers(&js).unwrap();
    let kinds: Vec<&str> = ls.iter().map(|l| l["kind"].as_str().unwrap()).collect();
    let quiet = write_sheet(&tmp.join("q"), "qx", &blank, false, ExWrite { states: vec![("hush".into(), [0, 35])], ..Default::default() });
    assert!(sfx::layers(&quiet).unwrap().is_empty(), "a hush state stays silent");
    assert!(kinds.iter().filter(|k| **k == "hit").count() == 2 && ["charge", "whoosh", "tail"].iter().all(|k| kinds.contains(k)), "layers from hits and state names: {kinds:?}");
    let w: Vec<&str> = ls.iter().filter(|l| l["kind"] == "hit").map(|l| l["weight"].as_str().unwrap()).collect();
    assert_eq!(w, ["light", "finisher"], "a hit with no weight is guessed from freeze and shake");
    assert!(ls.iter().all(|l| (l["t"].as_f64().unwrap() - l["frame"].as_f64().unwrap() / FPS).abs() < 1e-4), "layer t is its frame's time");

    let a = tmp.join("a");
    let snd = sfx::write(&a, "fx", Some(&mut js), sw(3, "retro", Some("metal"))).unwrap();
    let disk = bfx(&beanfx::serde_json::from_str::<Value>(&fs::read_to_string(a.join("fx.json")).unwrap()).unwrap());
    assert_eq!(disk["sound"], snd, "meta.beanfx.sound is written to the JSON");
    assert!(disk["act"]["hits"].as_array().unwrap().iter().all(|h| h.get("sound").is_some_and(|s| !s.is_null() && s != "")), "every act hit names its cue");
    let p = sfx::check(&a, &disk).unwrap();
    assert!(p.is_empty(), "check is clean: {p:?}");
    let trk = sfx::load(&a.join(snd["track"].as_str().unwrap())).unwrap();
    assert!(trk.len() as f64 / RATE >= 36.0 / FPS, "one-shot track covers the sheet");
    let pk = absmax(&trk);
    assert!(0.5 < pk && pk <= 0.95, "track peak in range: {pk:.3}");
    let cues = snd["cues"].as_array().unwrap();
    let mut files: Vec<&str> = cues.iter().map(|c| c["file"].as_str().unwrap()).collect();
    files.sort();
    files.dedup();
    assert!(files.iter().all(|f| a.join(f).exists()) && files.len() == cues.len(), "one file per distinct cue: {files:?}");

    // same seed same bytes, another seed differs
    let tpath = a.join(snd["track"].as_str().unwrap());
    let b1 = fs::read(&tpath).unwrap();
    sfx::write(&a, "fx", Some(&mut js), sw(3, "retro", Some("metal"))).unwrap();
    assert_eq!(fs::read(&tpath).unwrap(), b1, "same seed writes the same bytes");
    sfx::write(&a, "fx", Some(&mut js), sw(4, "retro", Some("metal"))).unwrap();
    assert_ne!(fs::read(&tpath).unwrap(), b1, "another seed writes another sound");

    // check catches a missing file and a bad voice is refused
    fs::remove_file(&tpath).unwrap();
    assert!(has(&sfx::check(&a, &disk).unwrap(), "missing"), "check names a missing file");
    assert!(sfx::track(&js, 1, "orchestral", None, None, None).is_err(), "unknown voice is refused");
    assert!(sfx::check(&a, &json!({"fps": 24, "frames": 1})).unwrap().is_empty(), "no sound block, no problems");
}

#[test]
fn hit_onsets_land_on_their_frame() {
    let tmp = common::tmpdir("sfx_b");
    let blank = blank();
    let mut only = write_sheet(&tmp, "hx", &blank, false, ExWrite { hits: vec![weighted(6, "heavy"), weighted(20, "light")], ..Default::default() });
    sfx::write(&tmp, "hx", Some(&mut only), sw(1, "soft", None)).unwrap();
    let x = sfx::load(&tmp.join("hx_sound.wav")).unwrap();
    onset_ok(&x, &only, 0.25);
}

#[test]
fn heavier_is_longer_and_lower() {
    let (mut cs, mut ns) = (vec![], vec![]);
    for w in ["light", "heavy", "finisher"] {
        let y = render(json!({"kind": "hit", "weight": w}), 1, "soft", None);
        cs.push(centroid(&y));
        ns.push(y.len());
    }
    assert!(ns[0] < ns[1] && ns[1] < ns[2], "heavier hits last longer: {ns:?}");
    assert!(cs[0] > cs[1] && cs[1] > cs[2], "heavier hits sound lower: {cs:?}");
}

#[test]
fn every_kind_voice_and_element_renders_in_level() {
    for k in sfx::KINDS {
        for v in sfx::VOICES {
            for e in sfx::ELEMENTS {
                let y = render(json!({"kind": k, "weight": "heavy", "dur": 0.4}), 2, v, Some(e));
                let m = absmax(&y);
                assert!(0.5 < m && m <= sfx::PEAK + 1e-6 && y.iter().all(|v| v.is_finite()), "{k} {v} {e} level {m:.3}");
            }
        }
    }
}

#[test]
fn loops_are_the_sheet_length_and_seamless() {
    let tmp = common::tmpdir("sfx_c");
    let blank = blank();
    let mut lp = write_sheet(&tmp, "lp", &blank[..24], true, ExWrite::default());
    let kinds: Vec<String> = sfx::layers(&lp).unwrap().iter().map(|l| l["kind"].as_str().unwrap().to_string()).collect();
    assert_eq!(kinds, ["hum"], "a bare loop gets a hum");
    sfx::write(&tmp, "lp", Some(&mut lp), sw(1, "retro", Some("fire"))).unwrap();
    let y = sfx::load(&tmp.join("lp_sound.wav")).unwrap();
    assert_eq!(y.len(), (24.0 / FPS * RATE).round() as usize, "loop track is exactly frames / fps");
    let p = sfx::check(&tmp, &lp).unwrap();
    assert!(p.is_empty(), "loop check clean: {p:?}");
    let mut loop2 = write_sheet(&tmp, "lq", &blank[..24], true, ExWrite { hits: vec![weighted(20, "heavy")], ..Default::default() });
    sfx::write(&tmp, "lq", Some(&mut loop2), sw(1, "retro", None)).unwrap();
    let y = sfx::load(&tmp.join("lq_sound.wav")).unwrap();
    let p = sfx::check(&tmp, &loop2).unwrap();
    assert!(y.len() == (24.0 / FPS * RATE).round() as usize && p.is_empty(), "a hit near the end of a loop wraps onto the start: {p:?}");
}

#[test]
fn real_voice_metal_and_thunder() {
    // a blade that lands (sword rain, a stab) is a short dense chink, never a bell; blade on blade rings at the bar modes
    let mut rng: Rng = default_rng(5u64);
    for (w, most) in [("light", 0.25), ("heavy", 0.35), ("finisher", 0.45)] {
        let mh = sfx::metal_hit(w, &mut default_rng(1u64), 1.0).unwrap();
        let (t, d) = (tonal(&mh, 6), t60(&mh));
        assert!(t < 0.45 && d < most, "{w} stab is no bell: tonal {t:.2}, dies in {d:.2} s (under {most:.2})");
    }
    let (a, b) = (sfx::metal_hit("light", &mut rng, 1.0).unwrap(), sfx::metal_hit("finisher", &mut rng, 1.0).unwrap());
    assert!(a.len() < b.len(), "a heavier stab lasts longer");
    for w in ["light", "heavy", "finisher"] {
        let y = sfx::metal_hit(w, &mut default_rng(1u64), 1.0).unwrap();
        let (s, f) = spectrum(&y);
        let p2: Vec<f64> = s.iter().map(|v| v * v).collect();
        let lo = p2.iter().zip(&f).filter(|(_, &fr)| fr < 300.0).map(|(v, _)| v).sum::<f64>() / p2.iter().sum::<f64>();
        assert!(lo < 0.1, "{w} stab is no drum: {lo:.2} of its energy under 300 Hz");
    }
    let mc = sfx::metal_clash("heavy", &mut rng, 1.0).unwrap();
    let mut pk = peaks(&mc, 4);
    pk.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let f0 = pk[0];
    let modes: Vec<f64> = sfx::BAR[..3].iter().map(|r| f0 * r).collect();
    assert!(modes.iter().all(|m| pk.iter().any(|p| (p - m).abs() / m < 0.03)), "a clash rings at the bar modes: {pk:?} vs {modes:?}");
    let (t, d) = (tonal(&mc, 6), t60(&mc));
    assert!(t > 0.8 && d > 0.5, "a clash rings like steel: tonal {t:.2}, {d:.2} s");
    let y = render(json!({"kind": "hit", "weight": "heavy", "clash": true}), 1, "real", Some("metal"));
    assert!(t60(&y) > 0.5, "a hit layer with clash=True rings: {:.2} s", t60(&y));

    let th = sfx::thunder("finisher", &mut default_rng(5u64), 1.0).unwrap();
    let (c, tail) = (&th[..n(0.05)], &th[n(0.6)..]);
    assert!(th.len() as f64 / RATE > 3.0, "finisher thunder rolls past 3 s");
    assert!(low_share(tail) > 2.0 * low_share(c), "thunder: crack bright, rumble low ({:.2} vs {:.2} under 250 Hz)", low_share(c), low_share(tail));
    let rms = (tail[..n(1.0)].iter().map(|v| v * v).sum::<f64>() / n(1.0) as f64).sqrt();
    assert!(rms > 0.05 * absmax(&th), "thunder rumble is heard after the crack");
    assert!(sfx::thunder("light", &mut default_rng(5u64), 1.0).unwrap().len() < th.len(), "light thunder is shorter");
    let y = render(json!({"kind": "hit", "weight": "heavy"}), 1, "real", Some("ice"));
    assert!(0.5 < absmax(&y) && absmax(&y) <= sfx::PEAK + 1e-6, "real voice falls back to soft for an element with no model");

    let tmp = common::tmpdir("sfx_r");
    let mut jr = write_sheet(&tmp, "rx", &blank(), false, ExWrite { hits: vec![weighted(8, "finisher")], states: vec![("swing".into(), [0, 7])], ..Default::default() });
    let sr = sfx::write(&tmp, "rx", Some(&mut jr), sw(1, "real", Some("lightning"))).unwrap();
    let p = sfx::check(&tmp, &jr).unwrap();
    assert!(p.is_empty() && sr["cues"].as_array().unwrap().iter().all(|c| c["source"] == "synth"), "real voice writes clean: {p:?}");
    let xr = sfx::load(&tmp.join("rx_sound.wav")).unwrap();
    assert!((sfx::onset(&xr, 8.0 / FPS, FPS, 0.2) - 8.0 / FPS).abs() <= 1.0 / FPS, "thunder onset on its hit");
}

#[test]
fn volley_falls_and_lands() {
    let v = sfx::volley(&[12.0, 12.0, 13.0, 20.0], FPS, sfx::Volley { fall_frames: 4.0, weight: "light".into(), gain: 0.3, jitter: 0.02, seed: 3, hits: true }).unwrap();
    let falls: Vec<&Value> = v.iter().filter(|l| l["kind"] == "fall").collect();
    let lands: Vec<&Value> = v.iter().filter(|l| l["kind"] == "hit").collect();
    assert!(falls.len() == 4 && lands.len() == 4, "volley: a fall and a landing per projectile");
    let f = |l: &Value, k: &str| l[k].as_f64().unwrap();
    assert!(falls.iter().zip(&lands).all(|(a, b)| (f(a, "t") + f(a, "dur") - f(b, "t")).abs() < 1e-3), "each fall ends on its landing");
    assert!(f(lands[0], "t") != f(lands[1], "t") && lands.iter().all(|l| (f(l, "t") - f(l, "frame") / FPS).abs() <= 0.02 + 1e-6), "blows on one frame are spread apart within the jitter");
    for (vo, el) in [("real", Some("metal")), ("soft", None), ("retro", Some("fire"))] {
        let y = render(json!({"kind": "fall", "dur": 0.2, "weight": "light"}), 1, vo, el);
        let q4 = y.len() / 4;
        let mean = |s: &[f64]| s.iter().map(|v| v.abs()).sum::<f64>() / s.len() as f64;
        assert!(mean(&y[y.len() - q4..]) > 2.0 * mean(&y[..q4]), "{vo} fall swells toward the landing");
    }
    let tmp = common::tmpdir("sfx_v");
    let mut jv = write_sheet(&tmp, "vx", &blank(), false, ExWrite { hits: vec![weighted(12, "heavy")], ..Default::default() });
    let mut layers = sfx::volley(&[12.0, 12.0], FPS, sfx::Volley { gain: 0.3, ..Default::default() }).unwrap();
    layers.extend(sfx::layers(&jv).unwrap());
    let sv = sfx::write(&tmp, "vx", Some(&mut jv), sfx::Write { layers: Some(layers), ..sw(1, "real", Some("metal")) }).unwrap();
    assert_eq!(jv["meta"]["beanfx"]["act"]["hits"][0]["sound"], "hit_heavy", "the act hit keeps its own cue, not a volley's");
    let mut gains: Vec<f64> = sv["cues"].as_array().unwrap().iter().map(|c| c["gain"].as_f64().unwrap()).collect();
    gains.sort_by(|a, b| a.partial_cmp(b).unwrap());
    gains.dedup();
    assert_eq!(gains, [0.3, 1.0], "a layer's gain reaches the JSON");
    let p = sfx::check(&tmp, &jv).unwrap();
    assert!(p.is_empty(), "volley writes clean: {p:?}");
    for k in ["charge", "tail"] {
        let y = render(json!({"kind": k, "dur": 0.6}), 1, "real", Some("metal"));
        assert!(tonal(&y, 6) < 0.3, "real metal {k} has no bell in it: tonal {:.2}", tonal(&y, 6));
    }
}

/// A PCM WAV of x (channels duplicated), 16 or 32 bit.
fn put(dir: &Path, name: &str, x: &[f64], ch: u16, rate: u32, width: u16) {
    let mut data = vec![];
    for v in x {
        for _ in 0..ch {
            let s = v * (2f64.powi(8 * width as i32 - 1) - 1.0);
            if width == 2 {
                data.extend_from_slice(&(s as i16).to_le_bytes());
            } else {
                data.extend_from_slice(&(s as i32).to_le_bytes());
            }
        }
    }
    let mut w = vec![];
    w.extend_from_slice(b"RIFF");
    w.extend_from_slice(&(36 + data.len() as u32).to_le_bytes());
    w.extend_from_slice(b"WAVEfmt ");
    w.extend_from_slice(&16u32.to_le_bytes());
    w.extend_from_slice(&1u16.to_le_bytes());
    w.extend_from_slice(&ch.to_le_bytes());
    w.extend_from_slice(&rate.to_le_bytes());
    w.extend_from_slice(&(rate * ch as u32 * width as u32).to_le_bytes());
    w.extend_from_slice(&(ch * width).to_le_bytes());
    w.extend_from_slice(&(width * 8).to_le_bytes());
    w.extend_from_slice(b"data");
    w.extend_from_slice(&(data.len() as u32).to_le_bytes());
    w.extend_from_slice(&data);
    fs::write(dir.join(name), w).unwrap();
}

#[test]
fn recordings_in_a_sounds_folder() {
    let tmp = common::tmpdir("sfx_s");
    let snd_dir = tmp.join("sounds");
    fs::create_dir_all(&snd_dir).unwrap();
    let tt: Vec<f64> = (0..(0.4 * 22050.0) as usize).map(|i| i as f64 / 22050.0).collect();
    let mut ping = vec![0.0; 2205];
    ping.extend(tt.iter().map(|t| (2.0 * PI * 660.0 * t).sin() * (-t / 0.1).exp())); // 0.1 s silence first
    put(&snd_dir, "metal_hit_01.wav", &ping, 2, 22050, 2);
    let heavy: Vec<f64> = ping.iter().map(|v| v * 0.9).collect();
    put(&snd_dir, "metal_hit_heavy_01.wav", &heavy, 1, 48000, 4);
    let find = |layer: Value| sfx::find_sample(Some(&snd_dir), &layer, Some("metal"), &mut default_rng(1u64)).unwrap();
    let p1 = find(json!({"kind": "hit", "weight": "light"})).unwrap();
    let p2 = find(json!({"kind": "hit", "weight": "heavy"})).unwrap();
    assert_eq!(p1.file_name().unwrap(), "metal_hit_01.wav", "a light hit takes metal_hit_*, not the heavy file");
    assert_eq!(p2.file_name().unwrap(), "metal_hit_heavy_01.wav", "a heavy hit takes the file named for its weight");
    assert!(find(json!({"kind": "whoosh", "dur": 0.3})).is_none(), "no whoosh file, no sample");
    let x1 = sfx::from_sample(&p1, &json!({"kind": "hit", "weight": "light"})).unwrap().unwrap();
    assert!(x1.iter().position(|v| v.abs() > 0.05).unwrap() < n(0.003), "a sample's leading silence is cut so it lands on t");
    let x0 = sfx::from_sample(&p1, &json!({"kind": "hit", "weight": "finisher"})).unwrap().unwrap();
    assert!(x0.len() > x1.len(), "a heavier weight plays the same file slower and lower: {} vs {}", x0.len(), x1.len());
    let mut js_s = write_sheet(&tmp, "sx", &blank(), false, ExWrite { hits: vec![weighted(6, "light"), weighted(20, "heavy")], ..Default::default() });
    let ss = sfx::write(&tmp, "sx", Some(&mut js_s), sfx::Write { sounds: Some(snd_dir.to_str().unwrap().into()), ..sw(1, "real", Some("metal")) }).unwrap();
    let srcs: Vec<&str> = ss["cues"].as_array().unwrap().iter().map(|c| c["source"].as_str().unwrap()).collect();
    assert_eq!(srcs, ["sample:metal_hit_01.wav", "sample:metal_hit_heavy_01.wav"], "cues use the recordings");
    assert_eq!(ss["samples"], json!(["metal_hit_01.wav", "metal_hit_heavy_01.wav"]), "the JSON lists the recordings to credit");
    let p = sfx::check(&tmp, &js_s).unwrap();
    assert!(p.is_empty(), "sample cues check clean: {p:?}");
    let xs = sfx::load(&tmp.join("sx_sound.wav")).unwrap();
    onset_ok(&xs, &js_s, 0.25);
    let other = common::tmpdir("sfx_nosounds").join("drafts/d/out");
    assert!(sfx::sounds_dir(other.to_str()).is_none(), "no sounds folder in the project, synthesis only");
}
