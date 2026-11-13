//! sfx.py: optional sound for an effect. Cues synthesised from the effect's JSON, 16-bit WAVs, meta.beanfx.sound
//! and the sound checks. Samples are mono f64 at RATE in a Vec.

mod synth;

use crate::rng::{madd, Rng};
use serde_json::{json, Map, Value};
use std::path::{Path, PathBuf};
pub use synth::*;

pub const VOICES: [&str; 3] = ["retro", "soft", "real"];
pub const ELEMENTS: [&str; 6] = ["metal", "lightning", "fire", "ice", "wind", "arcane"];
pub const KINDS: [&str; 7] = ["hit", "whoosh", "charge", "tail", "boom", "hum", "fall"];
pub const GLOW_BRIGHT: [(&str, f64); 3] = [("subtle", 0.8), ("medium", 1.0), ("strong", 1.25)];
pub const STATE_KIND: [(&str, &[&str]); 5] = [
    ("charge", &["gather", "summon", "charge", "cast", "chant", "channel", "build", "focus", "windup"]),
    ("whoosh", &["swing", "slash", "travel", "fly", "rain", "dash", "throw", "launch", "rise", "fall"]),
    ("tail", &["dissolve", "fade", "linger", "settle"]),
    ("rest", &["hush", "pause", "still", "breath"]),
    ("boom", &["strike", "impact", "burst", "explode", "land"]),
];
pub const GAIN: [(&str, f64); 7] =
    [("hit", 1.0), ("boom", 0.9), ("charge", 0.45), ("whoosh", 0.4), ("tail", 0.3), ("hum", 0.5), ("fall", 0.5)];
/// Playback rate of a recording by weight: a heavier hit plays lower.
pub const PITCH: [(&str, f64); 4] = [("light", 1.25), ("heavy", 1.0), ("finisher", 0.85), ("blast", 0.75)];
pub const SAMPLE_MAX: f64 = 3.0;
pub const SAMPLE_SYNTH: f64 = 0.2;
/// The hit weights' freeze and shake, the twin of WEIGHTS in export.rs (kit/export.py), for guess_weight.
const WEIGHTS: [(&str, f64, f64); 4] = [("light", 0.05, 1.0), ("heavy", 0.13, 3.0), ("finisher", 0.25, 6.0), ("blast", 0.08, 5.0)];

fn lookup(table: &[(&str, f64)], key: &str) -> Option<f64> {
    table.iter().find(|(k, _)| *k == key).map(|(_, v)| *v)
}

fn gain_of(kind: &str) -> Result<f64, String> {
    lookup(&GAIN, kind).ok_or_else(|| format!("KeyError: '{kind}'"))
}

// ---- Python's numbers and truthiness -----------------------------------------------------------------------

/// Python round(x, nd): the exact decimal value rounded, ties to even.
fn round_to(x: f64, nd: usize) -> f64 {
    format!("{x:.nd$}").parse().unwrap_or(x)
}

/// Python repr of a float: shortest digits, fixed between 1e-4 and 1e16, else d.ddde-XX.
fn py_float(x: f64) -> String {
    if x.is_nan() {
        return "nan".into();
    }
    if x.is_infinite() {
        return if x > 0.0 { "inf".into() } else { "-inf".into() };
    }
    let e = format!("{x:e}");
    let (mant, exp) = e.split_once('e').unwrap();
    let exp: i32 = exp.parse().unwrap();
    let neg = mant.starts_with('-');
    let digits: String = mant.chars().filter(|c| c.is_ascii_digit()).collect();
    let sign = if neg { "-" } else { "" };
    if (-4..16).contains(&exp) {
        let s = if exp >= 0 {
            let p = exp as usize + 1;
            if digits.len() <= p {
                format!("{digits}{}.0", "0".repeat(p - digits.len()))
            } else {
                format!("{}.{}", &digits[..p], &digits[p..])
            }
        } else {
            format!("0.{}{digits}", "0".repeat((-exp - 1) as usize))
        };
        format!("{sign}{s}")
    } else {
        let m = if digits.len() > 1 { format!("{}.{}", &digits[..1], &digits[1..]) } else { digits };
        format!("{sign}{m}e{}{:02}", if exp < 0 { "-" } else { "+" }, exp.abs())
    }
}

/// Python str() of a JSON value, for messages.
fn py_str(v: &Value) -> String {
    match v {
        Value::Null => "None".into(),
        Value::Bool(b) => if *b { "True".into() } else { "False".into() },
        Value::Number(n) if n.is_f64() => py_float(n.as_f64().unwrap()),
        Value::Number(n) => n.to_string(),
        Value::String(s) => s.clone(),
        other => other.to_string(),
    }
}

fn truthy(v: Option<&Value>) -> bool {
    match v {
        None | Some(Value::Null) => false,
        Some(Value::Bool(b)) => *b,
        Some(Value::Number(n)) => n.as_f64() != Some(0.0),
        Some(Value::String(s)) => !s.is_empty(),
        Some(Value::Array(a)) => !a.is_empty(),
        Some(Value::Object(o)) => !o.is_empty(),
    }
}

fn num(v: Option<&Value>, what: &str) -> Result<f64, String> {
    v.and_then(Value::as_f64).ok_or_else(|| format!("KeyError: '{what}'"))
}

fn fnum(x: f64) -> Value {
    json!(x)
}

/// The meta.beanfx block of an ex.write result, or the block itself.
fn bfx(js: &Value) -> &Value {
    js.get("meta").and_then(|m| m.get("beanfx")).unwrap_or(js)
}

fn bfx_mut(js: &mut Value) -> &mut Value {
    if js.get("meta").and_then(|m| m.get("beanfx")).is_some() {
        &mut js["meta"]["beanfx"]
    } else {
        js
    }
}

fn hits_of(b: &Value) -> Vec<Value> {
    b.get("act").and_then(|a| a.get("hits")).and_then(Value::as_array).cloned().unwrap_or_default()
}


// ---- the effect's timeline ----------------------------------------------------------------------------------

/// The weight of a hit that names none, from its freeze and shake (nearest WEIGHTS row).
pub fn guess_weight(h: &Value) -> String {
    if let Some(w) = h.get("weight").and_then(Value::as_str) {
        if wi(w).is_ok() {
            return w.into();
        }
    }
    let fz = h.get("freeze").and_then(Value::as_f64).unwrap_or(0.1);
    let sh = h.get("shake").and_then(Value::as_f64).unwrap_or(0.0);
    let mut best = ("", f64::INFINITY);
    for (k, f, s) in WEIGHTS {
        let d = (f - fz).abs() / 0.2 + (s - sh).abs() / 6.0;
        if d < best.1 {
            best = (k, d);
        }
    }
    best.0.into()
}

pub fn layers(js: &Value) -> Result<Vec<Value>, String> {
    let b = bfx(js);
    let fps = num(b.get("fps"), "fps")?;
    let hits = hits_of(b);
    let mut out = Vec::new();
    for h in &hits {
        let w = guess_weight(h);
        let frame = h.get("frame").cloned().unwrap_or(Value::Null);
        let name = match h.get("sound") {
            s if truthy(s) => s.unwrap().clone(),
            _ => json!(format!("hit_{w}")),
        };
        out.push(json!({"kind": "hit", "t": round_to(num(Some(&frame), "frame")? / fps, 4), "frame": frame,
                        "weight": w, "name": name, "dur": WEIGHT_SOUND[wi(&w)?].dur}));
    }
    if let Some(states) = b.get("states").and_then(Value::as_object) {
        for (s, span) in states {
            let word = s.rsplit('/').next().unwrap_or("").to_lowercase();
            let kind = STATE_KIND.iter().find(|(_, ws)| ws.iter().any(|x| word.contains(x))).map(|(k, _)| *k);
            let kind = match kind {
                None | Some("rest") => continue,
                Some(k) => k,
            };
            let a = num(span.get(0), "state")?;
            let z = num(span.get(1), "state")?;
            if kind == "boom" && hits.iter().any(|h| h.get("frame").and_then(Value::as_f64).is_some_and(|f| a <= f && f <= z)) {
                continue;
            }
            let mut dur = (z + 1.0 - a) / fps;
            if kind == "tail" {
                dur += 0.3;
            }
            if kind == "boom" {
                dur = dur.max(0.6);
            }
            out.push(json!({"kind": kind, "t": round_to(a / fps, 4), "frame": span[0].clone(),
                            "dur": round_to(dur, 4), "name": kind}));
        }
    }
    if out.is_empty() && truthy(b.get("loop")) {
        let n = num(b.get("frames"), "frames")?;
        out.push(json!({"kind": "hum", "t": 0.0, "frame": 0, "dur": round_to(n / fps, 4), "name": "hum"}));
    }
    let key = |l: &Value| (l["t"].as_f64().unwrap_or(0.0), l["kind"].as_str().unwrap_or("").to_string());
    out.sort_by(|a, b| key(a).partial_cmp(&key(b)).unwrap_or(std::cmp::Ordering::Equal));
    Ok(out)
}

/// Options of `volley`: fall_frames 3, weight "light", gain 0.35, jitter 0.008, seed 1, hits true.
#[derive(Clone, Debug)]
pub struct Volley {
    pub fall_frames: f64,
    pub weight: String,
    pub gain: f64,
    pub jitter: f64,
    pub seed: u64,
    pub hits: bool,
}

impl Default for Volley {
    fn default() -> Self {
        Volley { fall_frames: 3.0, weight: "light".into(), gain: 0.35, jitter: 0.008, seed: 1, hits: true }
    }
}

/// Layers for many projectiles that land (a sword rain, an arrow volley, hail): for each landing frame a fall over
/// the fall_frames before it and, with hits, a hit on it, both at gain. jitter (s) spreads blows on one frame apart.
pub fn volley(lands: &[f64], fps: f64, o: Volley) -> Result<Vec<Value>, String> {
    let fall_frames = o.fall_frames;
    let weight = o.weight;
    let gain = json!(o.gain);
    let jitter = o.jitter;
    let mut rng = Rng::new(&[o.seed, 77]);
    let mut out = Vec::new();
    for &fv in lands {
        let dt = rng.uniform(-jitter, jitter);
        let land = (fv / fps + dt).max(0.0);
        let dur = fall_frames / fps;
        let frame = crate::ex::num((fv - fall_frames).max(0.0));
        let d = dur.min(land);
        out.push(json!({"kind": "fall", "t": round_to((land - dur).max(0.0), 4), "frame": frame,
                        "dur": round_to(if d == 0.0 { 1.0 / fps } else { d }, 4), "weight": weight,
                        "name": format!("fall_{weight}"), "gain": gain}));
        if o.hits {
            out.push(json!({"kind": "hit", "t": round_to(land, 4), "frame": fv.trunc() as i64, "weight": weight,
                            "name": format!("volley_{weight}"), "dur": WEIGHT_SOUND[wi(&weight)?].dur, "gain": gain}));
        }
    }
    Ok(out)
}

fn weight_of(layer: &Value) -> Result<String, String> {
    layer.get("weight").and_then(Value::as_str).map(String::from).ok_or_else(|| "KeyError: 'weight'".to_string())
}

fn dur_of(layer: &Value) -> Result<f64, String> {
    num(layer.get("dur"), "dur")
}

/// The physical model for a layer in the real voice, or None when there is none (other elements use soft).
pub fn real(layer: &Value, rng: &mut Rng, element: Option<&str>, bright: f64) -> Result<Option<Vec<f64>>, String> {
    let kind = layer["kind"].as_str().unwrap_or("");
    let lw = || layer.get("weight").and_then(Value::as_str).filter(|s| !s.is_empty()).unwrap_or("light").to_string();
    Ok(match (element, kind) {
        (Some("metal"), "hit") if truthy(layer.get("clash")) => Some(metal_clash(&weight_of(layer)?, rng, bright)?),
        (Some("metal"), "hit") => Some(metal_hit(&weight_of(layer)?, rng, bright)?),
        (Some("metal"), "boom") => Some(metal_hit("blast", rng, bright)?),
        (Some("metal"), "whoosh") => {
            let d = dur_of(layer)?;
            let s = metal_scrape(d, rng, bright);
            let w = whoosh(d, rng, None, bright);
            Some(s.iter().zip(&w).map(|(a, b)| a + 0.5 * b).collect())
        }
        (Some("metal"), "fall") => Some(metal_fall(dur_of(layer)?, rng, bright, &lw())?),
        (Some("metal"), "charge") => Some(metal_gather(dur_of(layer)?, rng, bright)),
        (Some("metal"), "tail") => Some(metal_settle(dur_of(layer)?, rng, bright)),
        (Some("lightning"), "hit") => Some(thunder(&weight_of(layer)?, rng, bright)?),
        (Some("lightning"), "boom") => Some(thunder("blast", rng, bright)?),
        _ => None,
    })
}

/// A layer's synthesised cue in a voice other than real.
fn synth_cue(layer: &Value, rng: &mut Rng, voice: &str, element: Option<&str>, bright: f64) -> Result<Vec<f64>, String> {
    let kind = layer["kind"].as_str().unwrap_or("");
    Ok(match kind {
        "hit" => hit(&weight_of(layer)?, rng, voice, element, bright)?,
        "fall" => fall(dur_of(layer)?, rng, element, bright),
        "whoosh" => whoosh(dur_of(layer)?, rng, element, bright),
        "charge" => charge(dur_of(layer)?, rng, voice, element, bright),
        "tail" => tail(dur_of(layer)?, rng, element, bright),
        "boom" => boom(dur_of(layer)?, rng, voice, element, bright)?,
        "hum" => hum(dur_of(layer)?, rng, element, bright)?,
        _ => return Err(format!("ValueError: {kind:?} is not in KINDS")),
    })
}

/// One layer's samples, normalised; sets layer["source"] to "synth" or "sample:<file>".
pub fn render(layer: &mut Value, seed: u64, voice: &str, element: Option<&str>, bright: f64, index: u64, sounds: Option<&Path>)
    -> Result<Vec<f64>, String> {
    let kind = layer.get("kind").and_then(Value::as_str).unwrap_or("").to_string();
    let ki = KINDS.iter().position(|k| *k == kind).ok_or_else(|| format!("ValueError: '{kind}' is not in tuple"))?;
    let mut rng = Rng::new(&[seed, index, ki as u64]);
    let mut x = if voice == "real" { real(layer, &mut rng, element, bright)? } else { None };
    if x.is_none() {
        let v = if voice == "real" { "soft" } else { voice };
        x = Some(synth_cue(layer, &mut rng, v, element, bright)?);
    }
    let mut x = x.unwrap();
    if voice == "retro" {
        x = crush(&norm(&x, PEAK), 6, 4);
    }
    x = norm(&fade(&x, 4.0), PEAK);
    let obj = layer.as_object_mut().ok_or("layer is not a dict")?;
    obj.insert("source".into(), json!("synth"));
    if let Some(path) = find_sample(sounds, layer, element, &mut rng)? {
        if let Some(smp) = from_sample(&path, layer)? {
            let mut mix = vec![0.0; smp.len().max(x.len())];
            for (m, s) in mix.iter_mut().zip(&smp) {
                *m += s;
            }
            for (m, s) in mix.iter_mut().zip(&x) {
                *m += SAMPLE_SYNTH * s;
            }
            x = norm(&fade(&mix, 4.0), PEAK);
            let name = path.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
            layer["source"] = json!(format!("sample:{name}"));
        }
    }
    Ok(x)
}

fn check_voice(voice: &str, element: Option<&str>) -> Result<(), String> {
    if !VOICES.contains(&voice) {
        return Err(format!("ValueError: voice '{voice}' not in ('retro', 'soft', 'real')"));
    }
    if let Some(e) = element {
        if !ELEMENTS.contains(&e) {
            return Err(format!("ValueError: element '{e}' not in (None, 'metal', 'lightning', 'fire', 'ice', 'wind', 'arcane')"));
        }
    }
    Ok(())
}

/// The whole effect's sound on the sheet's timeline and the rendered cues.
pub fn track(js: &Value, seed: u64, voice: &str, element: Option<&str>, given: Option<Vec<Value>>, sounds: Option<&Path>)
    -> Result<(Vec<f64>, Vec<(Value, Vec<f64>)>), String> {
    check_voice(voice, element)?;
    let b = bfx(js);
    let bright = b.get("glow").and_then(Value::as_str).and_then(|g| lookup(&GLOW_BRIGHT, g)).unwrap_or(1.0);
    let ls = match given {
        Some(l) => l,
        None => layers(js)?,
    };
    let mut cues = Vec::new();
    for (i, mut l) in ls.into_iter().enumerate() {
        let x = render(&mut l, seed, voice, element, bright, i as u64, sounds)?;
        cues.push((l, x));
    }
    let lp = truthy(b.get("loop"));
    let mut length = n_of(num(b.get("frames"), "frames")? / num(b.get("fps"), "fps")?);
    if !lp {
        for (l, x) in &cues {
            length = length.max(n_of(num(l.get("t"), "t")?) + x.len());
        }
    }
    let mut mix = vec![0.0; length];
    for (l, x) in &cues {
        let t = num(l.get("t"), "t")?;
        let s = if t > 0.0 { n_of(t) } else { 0 };
        let kind = l["kind"].as_str().unwrap_or("");
        let g = match l.get("gain") {
            Some(g) => g.as_f64().ok_or("gain must be a number")?,
            None => gain_of(kind)?,
        };
        for (i, v) in x.iter().enumerate() {
            let idx = if lp { (s + i) % length } else { s + i };
            mix[idx] += v * g;
        }
    }
    if absmax(&mix) > 0.0 {
        mix = norm(&mix, PEAK);
    }
    Ok((if lp { mix } else { fade(&mix, 4.0) }, cues))
}

// ---- WAV files ----------------------------------------------------------------------------------------------

/// 16-bit mono WAV at RATE, the header Python's wave module writes.
pub fn save(path: &Path, x: &[f64]) -> Result<(), String> {
    let data: Vec<u8> = x.iter().flat_map(|v| ((v.clamp(-1.0, 1.0) * 32767.0) as i16).to_le_bytes()).collect();
    let mut out = Vec::with_capacity(44 + data.len());
    out.extend_from_slice(b"RIFF");
    out.extend_from_slice(&(36 + data.len() as u32).to_le_bytes());
    out.extend_from_slice(b"WAVEfmt ");
    out.extend_from_slice(&16u32.to_le_bytes());
    out.extend_from_slice(&1u16.to_le_bytes());
    out.extend_from_slice(&1u16.to_le_bytes());
    out.extend_from_slice(&44100u32.to_le_bytes());
    out.extend_from_slice(&88200u32.to_le_bytes());
    out.extend_from_slice(&2u16.to_le_bytes());
    out.extend_from_slice(&16u16.to_le_bytes());
    out.extend_from_slice(b"data");
    out.extend_from_slice(&(data.len() as u32).to_le_bytes());
    out.extend_from_slice(&data);
    std::fs::write(path, out).map_err(|e| format!("{}: {e}", path.display()))
}

/// (channels, sample width in bytes, rate, frame bytes) of a PCM WAV.
fn parse_wav(path: &Path) -> Result<(usize, usize, f64, Vec<u8>), String> {
    let b = std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
    if b.len() < 12 || &b[..4] != b"RIFF" || &b[8..12] != b"WAVE" {
        return Err(format!("{}: file does not start with RIFF id", path.display()));
    }
    let (mut i, mut fmt, mut data) = (12usize, None, None);
    while i + 8 <= b.len() {
        let id = &b[i..i + 4];
        let size = u32::from_le_bytes(b[i + 4..i + 8].try_into().unwrap()) as usize;
        let body = &b[i + 8..(i + 8 + size).min(b.len())];
        if id == b"fmt " && body.len() >= 16 {
            let tag = u16::from_le_bytes([body[0], body[1]]);
            if tag != 1 && tag != 0xFFFE {
                return Err(format!("{}: unknown format: {tag}", path.display()));
            }
            let ch = u16::from_le_bytes([body[2], body[3]]) as usize;
            let rate = u32::from_le_bytes(body[4..8].try_into().unwrap()) as f64;
            let bits = u16::from_le_bytes([body[14], body[15]]) as usize;
            fmt = Some((ch.max(1), bits.div_ceil(8), rate));
        } else if id == b"data" {
            data = Some(body.to_vec());
            break;
        }
        i += 8 + size + (size & 1);
    }
    let (ch, w, rate) = fmt.ok_or_else(|| format!("{}: fmt chunk missing", path.display()))?;
    let mut data = data.ok_or_else(|| format!("{}: data chunk missing", path.display()))?;
    data.truncate(data.len() / (ch * w) * (ch * w));
    Ok((ch, w, rate, data))
}

/// The 16-bit samples of a WAV as floats (kit sfx.load).
pub fn load(path: &Path) -> Result<Vec<f64>, String> {
    let (_, _, _, data) = parse_wav(path)?;
    Ok(data.chunks_exact(2).map(|c| i16::from_le_bytes([c[0], c[1]]) as f64 / 32767.0).collect())
}

/// Any PCM WAV (8, 16, 24 or 32-bit, mono or stereo, any rate) as mono floats at RATE.
pub fn read_wav(path: &Path) -> Result<Vec<f64>, String> {
    let (ch, w, sr, data) = parse_wav(path)?;
    let vals: Vec<f64> = match w {
        1 => data.iter().map(|&v| v as f64 / 128.0 - 1.0).collect(),
        2 => data.chunks_exact(2).map(|c| i16::from_le_bytes([c[0], c[1]]) as f64 / 32768.0).collect(),
        3 => data
            .chunks_exact(3)
            .map(|c| {
                let v = c[0] as i32 | (c[1] as i32) << 8 | (c[2] as i32) << 16;
                (if v >= 1 << 23 { v - (1 << 24) } else { v }) as f64 / (1 << 23) as f64
            })
            .collect(),
        4 => data.chunks_exact(4).map(|c| i32::from_le_bytes([c[0], c[1], c[2], c[3]]) as f64 / 2147483648.0).collect(),
        _ => return Err(format!("{}: unsupported sample width {w}", path.display())),
    };
    let x: Vec<f64> = vals.chunks_exact(ch).map(|f| f.iter().fold(0.0, |s, v| s + v) / ch as f64).collect();
    Ok(resample(&x, sr / RATE))
}

/// x played at rate times its speed (linear interpolation, np.interp): above 1 shorter and higher.
pub fn resample(x: &[f64], rate: f64) -> Vec<f64> {
    if (rate - 1.0).abs() < 1e-9 || x.len() < 2 {
        return x.to_vec();
    }
    let last = (x.len() - 1) as f64;
    let n = (last / rate).ceil().max(0.0) as usize;
    (0..n)
        .map(|i| {
            let p = i as f64 * rate;
            let j = p.floor() as usize;
            if j >= x.len() - 1 {
                x[x.len() - 1]
            } else if j as f64 == p {
                x[j]
            } else {
                madd(x[j + 1] - x[j], p - j as f64, x[j])
            }
        })
        .collect()
}

fn stem(p: &Path) -> String {
    p.file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default()
}

/// The recording for a layer in folder, or None: the most specific name prefix with a match, picked by rng.
pub fn find_sample(folder: Option<&Path>, layer: &Value, element: Option<&str>, rng: &mut Rng) -> Result<Option<PathBuf>, String> {
    let Some(folder) = folder.filter(|f| f.is_dir()) else { return Ok(None) };
    let mut names: Vec<PathBuf> = std::fs::read_dir(folder)
        .map_err(|e| format!("{}: {e}", folder.display()))?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().is_some_and(|x| x == "wav"))
        .collect();
    names.sort();
    let kind = layer["kind"].as_str().unwrap_or("");
    let w = layer.get("weight").and_then(Value::as_str).filter(|s| !s.is_empty());
    let mut keys = Vec::new();
    if let (Some(e), Some(w)) = (element, w) {
        keys.push(format!("{e}_{kind}_{w}"));
    }
    if let Some(e) = element {
        keys.push(format!("{e}_{kind}"));
    }
    if let Some(w) = w {
        keys.push(format!("{kind}_{w}"));
    }
    keys.push(kind.to_string());
    let bare = format!("{}_{kind}", element.unwrap_or("None"));
    for key in keys {
        let mut hit: Vec<&PathBuf> = names.iter().filter(|p| { let s = stem(p); s == key || s.starts_with(&format!("{key}_")) }).collect();
        if key == kind || key == bare {
            hit.retain(|p| {
                let s = stem(p);
                w.is_none() || !PITCH.iter().any(|(x, _)| Some(*x) != w && s.starts_with(&format!("{key}_{x}")))
            });
        }
        if !hit.is_empty() {
            let i = rng.integers(0, hit.len() as i64) as usize;
            return Ok(Some(hit[i].clone()));
        }
    }
    Ok(None)
}

/// A recording made into a cue: leading silence cut so the onset lands on t, pitched by weight, capped.
pub fn from_sample(path: &Path, layer: &Value) -> Result<Option<Vec<f64>>, String> {
    let mut x = read_wav(path)?;
    let m = absmax(&x);
    if m <= 0.0 {
        return Ok(None);
    }
    let start = x.iter().position(|v| v.abs() >= 0.05 * m).unwrap_or(0);
    x = x[start.saturating_sub(n_of(0.001))..].to_vec();
    if let Some(w) = layer.get("weight").and_then(Value::as_str).filter(|s| !s.is_empty()) {
        if !stem(path).contains(&format!("_{w}")) {
            x = resample(&x, lookup(&PITCH, w).ok_or_else(|| format!("KeyError: '{w}'"))?);
        }
    }
    let kind = layer["kind"].as_str().unwrap_or("");
    if ["whoosh", "charge", "tail", "hum"].contains(&kind) && truthy(layer.get("dur")) && x.len() > 1 {
        let r = x.len() as f64 / n_of(dur_of(layer)?) as f64;
        x = resample(&x, r);
    }
    x.truncate(n_of(SAMPLE_MAX));
    Ok(Some(norm(&fade(&x, 8.0), PEAK)))
}

/// Path.resolve() for a path that may not exist: absolute, symlinks of the existing part followed.
fn resolve(p: &Path) -> PathBuf {
    let abs = if p.is_absolute() { p.to_path_buf() } else { std::env::current_dir().unwrap_or_default().join(p) };
    let mut out = PathBuf::new();
    for c in abs.components() {
        match c {
            std::path::Component::ParentDir => {
                out.pop();
            }
            std::path::Component::CurDir => {}
            other => {
                out.push(other);
                if let Ok(r) = std::fs::canonicalize(&out) {
                    out = r;
                }
            }
        }
    }
    out
}

/// BEANFX_SOUNDS, else the project's sounds/ (out is drafts/<name>/out), else None.
pub fn sounds_dir(out: Option<&str>) -> Option<PathBuf> {
    if let Ok(s) = std::env::var("BEANFX_SOUNDS") {
        if !s.is_empty() {
            return Some(PathBuf::from(s));
        }
    }
    let r = resolve(Path::new(out?));
    let d = r.parent()?.parent()?.parent()?.join("sounds");
    d.is_dir().then_some(d)
}

// ---- write and check ----------------------------------------------------------------------------------------

/// Python's json.dumps(v, indent=1): ensure_ascii strings and repr floats.
fn dumps(v: &Value, depth: usize, out: &mut String) {
    let pad = |d: usize| format!("\n{}", " ".repeat(d));
    match v {
        Value::Number(n) if n.is_f64() => out.push_str(&py_float(n.as_f64().unwrap())),
        Value::String(t) => {
            out.push('"');
            for c in t.chars() {
                match c {
                    '"' => out.push_str("\\\""),
                    '\\' => out.push_str("\\\\"),
                    '\n' => out.push_str("\\n"),
                    '\r' => out.push_str("\\r"),
                    '\t' => out.push_str("\\t"),
                    '\u{8}' => out.push_str("\\b"),
                    '\u{c}' => out.push_str("\\f"),
                    c if (c as u32) < 0x20 || (c as u32) > 0x7e => {
                        let mut b = [0u16; 2];
                        for u in c.encode_utf16(&mut b) {
                            out.push_str(&format!("\\u{u:04x}"));
                        }
                    }
                    c => out.push(c),
                }
            }
            out.push('"');
        }
        Value::Array(a) if !a.is_empty() => {
            out.push('[');
            for (i, x) in a.iter().enumerate() {
                out.push_str(if i > 0 { "," } else { "" });
                out.push_str(&pad(depth + 1));
                dumps(x, depth + 1, out);
            }
            out.push_str(&pad(depth));
            out.push(']');
        }
        Value::Object(o) if !o.is_empty() => {
            out.push('{');
            for (i, (k, x)) in o.iter().enumerate() {
                out.push_str(if i > 0 { "," } else { "" });
                out.push_str(&pad(depth + 1));
                dumps(&Value::String(k.clone()), depth + 1, out);
                out.push_str(": ");
                dumps(x, depth + 1, out);
            }
            out.push_str(&pad(depth));
            out.push('}');
        }
        Value::Null => out.push_str("null"),
        other => out.push_str(&other.to_string()),
    }
}

fn write_json(path: &Path, v: &Value) -> Result<(), String> {
    let mut s = String::new();
    dumps(v, 0, &mut s);
    std::fs::write(path, s).map_err(|e| format!("{}: {e}", path.display()))
}

fn read_json(path: &Path) -> Result<Value, String> {
    let t = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    serde_json::from_str(&t).map_err(|e| format!("{}: {e}", path.display()))
}

/// Options of `write` and `track`: seed 1, voice "retro", no element, layers from the JSON, sounds "auto".
#[derive(Clone, Debug)]
pub struct Write {
    pub seed: u64,
    pub voice: String,
    pub element: Option<String>,
    /// Edited layers (from `layers`) in place of the ones the JSON gives.
    pub layers: Option<Vec<Value>>,
    /// A folder of recordings, "auto" (BEANFX_SOUNDS or the project's sounds/) or None (synthesis only).
    pub sounds: Option<String>,
}

impl Default for Write {
    fn default() -> Self {
        Write { seed: 1, voice: "retro".into(), element: None, layers: None, sounds: Some("auto".into()) }
    }
}

/// Writes <name>_sound.wav and one WAV per distinct cue into out, adds meta.beanfx.sound to <name>.json (and to js
/// when given), names the cue on every act hit that had none, and returns the sound block.
pub fn write(out: impl AsRef<Path>, name: &str, js: Option<&mut Value>, o: Write) -> Result<Value, String> {
    let out = out.as_ref();
    check_voice(&o.voice, o.element.as_deref())?;
    let sounds = match o.sounds.as_deref() {
        Some("auto") => sounds_dir(out.to_str()),
        Some(s) => Some(PathBuf::from(s)),
        None => None,
    };
    let jp = out.join(format!("{name}.json"));
    let given_js = js;
    let mut js = match &given_js {
        Some(v) => (**v).clone(),
        None => read_json(&jp)?,
    };
    let seed = json!(o.seed);
    let voice = o.voice;
    let element = o.element;
    let (mix, cues) = track(&js, o.seed, &voice, element.as_deref(), o.layers, sounds.as_deref())?;
    save(&out.join(format!("{name}_sound.wav")), &mix)?;
    let mut files: Vec<((String, String, String), String)> = Vec::new();
    let mut listed = Vec::new();
    for (l, x) in &cues {
        let lname = py_str(l.get("name").ok_or("KeyError: 'name'")?);
        let dur = round_to(dur_of(l)?, 3);
        let source = l["source"].as_str().unwrap_or("").to_string();
        let key = (lname.clone(), dur.to_bits().to_string(), source.clone());
        let file = match files.iter().find(|(k, _)| *k == key) {
            Some((_, f)) => f.clone(),
            None => {
                let st = if files.iter().any(|(k, _)| k.0 == lname) { format!("{lname}_{}", files.len()) } else { lname.clone() };
                let f = format!("{name}_{st}.wav");
                save(&out.join(&f), x)?;
                files.push((key, f.clone()));
                f
            }
        };
        let kind = l["kind"].as_str().unwrap_or("");
        let mut c = Map::new();
        c.insert("name".into(), l["name"].clone());
        c.insert("kind".into(), json!(kind));
        c.insert("t".into(), l["t"].clone());
        c.insert("frame".into(), l.get("frame").cloned().ok_or("KeyError: 'frame'")?);
        c.insert("file".into(), json!(file));
        c.insert("length".into(), fnum(round_to(x.len() as f64 / RATE, 4)));
        c.insert("gain".into(), l.get("gain").cloned().unwrap_or_else(|| fnum(gain_of(kind).unwrap_or(1.0))));
        c.insert("source".into(), json!(source));
        if truthy(l.get("weight")) {
            c.insert("weight".into(), l["weight"].clone());
        }
        listed.push(Value::Object(c));
    }
    let b = bfx_mut(&mut js);
    if let Some(hs) = b.get_mut("act").and_then(|a| a.get_mut("hits")).and_then(Value::as_array_mut) {
        for h in hs.iter_mut() {
            if truthy(h.get("sound")) {
                continue;
            }
            let f = h.get("frame").and_then(Value::as_f64);
            let on: Vec<&Value> = listed.iter().filter(|c| c["kind"] == "hit" && c["frame"].as_f64() == f && f.is_some()).collect();
            let first = on.first().ok_or("IndexError: list index out of range")?;
            let pick = on.iter().find(|c| !c["name"].as_str().unwrap_or("").starts_with("volley_")).unwrap_or(first);
            h["sound"] = pick["name"].clone();
        }
    }
    let mut snd = Map::new();
    snd.insert("track".into(), json!(format!("{name}_sound.wav")));
    snd.insert("loop".into(), json!(truthy(b.get("loop"))));
    snd.insert("length".into(), fnum(round_to(mix.len() as f64 / RATE, 4)));
    snd.insert("rate".into(), json!(44100));
    snd.insert("seed".into(), seed);
    snd.insert("voice".into(), json!(voice));
    snd.insert("element".into(), json!(element));
    let mut used: Vec<String> =
        listed.iter().filter_map(|c| c["source"].as_str().and_then(|s| s.strip_prefix("sample:")).map(String::from)).collect();
    snd.insert("cues".into(), Value::Array(listed));
    used.sort();
    used.dedup();
    if !used.is_empty() {
        snd.insert("samples".into(), json!(used));
    }
    let snd = Value::Object(snd);
    let act = b.get("act").cloned();
    if jp.exists() {
        let mut disk = read_json(&jp)?;
        let ob = bfx_mut(&mut disk);
        ob["sound"] = snd.clone();
        if let Some(a) = &act {
            ob["act"] = a.clone();
        }
        write_json(&jp, &disk)?;
    }
    if let Some(g) = given_js {
        let gb = bfx_mut(g);
        let new_hits = act.as_ref().and_then(|a| a.get("hits")).and_then(Value::as_array).cloned().unwrap_or_default();
        if let Some(hs) = gb.get_mut("act").and_then(|a| a.get_mut("hits")).and_then(Value::as_array_mut) {
            for (h, h2) in hs.iter_mut().zip(&new_hits) {
                if !truthy(h.get("sound")) {
                    h["sound"] = h2["sound"].clone();
                }
            }
        }
        gb["sound"] = snd.clone();
    }
    Ok(snd)
}

/// np.percentile(x, q), the linear method.
fn percentile(x: &[f64], q: f64) -> f64 {
    let mut s = x.to_vec();
    s.sort_by(|a, b| a.total_cmp(b));
    let n = s.len();
    let vi = (n as f64 - 1.0) * (q / 100.0);
    let lo = vi.floor().clamp(0.0, n as f64 - 1.0);
    let hi = (lo + 1.0).min(n as f64 - 1.0);
    let g = vi - lo;
    let (a, b) = (s[lo as usize], s[hi as usize]);
    let d = b - a;
    if g >= 0.5 { b - d * (1.0 - g) } else { a + d * g }
}

/// The problems of an effect's sound: missing files, a silent or clipping file, a track shorter than the sheet (or,
/// for a loop, not exactly its length or with a jump at the seam), and hit cues off their hit by a frame.
pub fn check(out: impl AsRef<Path>, js: &Value) -> Result<Vec<String>, String> {
    let out = out.as_ref();
    let b = bfx(js);
    let Some(snd) = b.get("sound").filter(|s| truthy(Some(s))) else { return Ok(vec![]) };
    let mut bad = Vec::new();
    let fps = num(b.get("fps"), "fps")?;
    let sheet = num(b.get("frames"), "frames")? / fps;
    let cues = snd["cues"].as_array().cloned().unwrap_or_default();
    let trk = py_str(&snd["track"]);
    let mut files: Vec<String> = cues.iter().map(|c| py_str(&c["file"])).collect();
    files.sort();
    files.dedup();
    let mut data = std::collections::HashMap::new();
    for p in std::iter::once(trk.clone()).chain(files) {
        if !out.join(&p).exists() {
            bad.push(format!("sound: {p} is missing"));
            continue;
        }
        let x = load(&out.join(&p))?;
        let pk = absmax(&x);
        if pk < 0.05 {
            bad.push(format!("sound: {p} is silent (peak {pk:.3})"));
        }
        if pk > 0.95 {
            bad.push(format!("sound: {p} clips (peak {pk:.3})"));
        }
        data.insert(p, x);
    }
    if let Some(x) = data.get(&trk) {
        let l = x.len() as f64 / RATE;
        if truthy(snd.get("loop")) {
            if (l - sheet).abs() > 1.0 / RATE * 2.0 {
                bad.push(format!("sound: loop track is {l:.4} s, the sheet loops every {sheet:.4} s"));
            }
            let d: Vec<f64> = x.windows(2).map(|w| (w[1] - w[0]).abs()).collect();
            let step = percentile(&d, 99.5);
            let jump = (x[x.len() - 1] - x[0]).abs();
            if jump > (4.0 * step).max(0.02) {
                bad.push(format!("sound: loop track jumps {jump:.3} at the seam (99.5 % step {step:.3})"));
            }
        } else if l + 1e-6 < sheet {
            bad.push(format!("sound: track is {l:.3} s, shorter than the sheet's {sheet:.3} s"));
        }
    }
    for h in hits_of(b) {
        let f = h.get("frame").and_then(Value::as_f64);
        let c: Vec<&Value> = cues.iter().filter(|c| c["kind"] == "hit" && f.is_some() && c["frame"].as_f64() == f).collect();
        let fr = py_str(h.get("frame").unwrap_or(&Value::Null));
        match c.first() {
            None => bad.push(format!("sound: no cue on the hit at frame {fr}")),
            Some(c0) => {
                if (num(c0.get("t"), "t")? - f.unwrap_or(0.0) / fps).abs() > 1.0 / fps {
                    bad.push(format!("sound: cue {} at {} s is off the hit at frame {fr}", py_str(&c0["name"]), py_str(&c0["t"])));
                }
            }
        }
    }
    Ok(bad)
}

/// The time (s) the sound first rises past half its peak within window s from t - one frame.
pub fn onset(x: &[f64], t: f64, fps: f64, window: f64) -> f64 {
    let a = if t > 1.0 / fps { n_of(t - 1.0 / fps) } else { 0 };
    let a = a.min(x.len());
    let seg: Vec<f64> = x[a..(a + n_of(window)).min(x.len())].iter().map(|v| v.abs()).collect();
    let k = n_of(0.003);
    let (nn, kk) = (seg.len(), k);
    let len = nn.max(kk);
    let off = (nn.min(kk) as i64 - 1) / 2;
    let w = 1.0 / k as f64;
    let sm: Vec<f64> = (0..len as i64)
        .map(|i| {
            let m = i + off;
            let lo = (m - kk as i64 + 1).max(0);
            let hi = m.min(nn as i64 - 1);
            (lo..=hi).fold(0.0, |s, j| s + seg[j as usize] * w)
        })
        .collect();
    let top = sm.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let i = sm.iter().position(|v| *v >= 0.5 * top).unwrap_or(0);
    (a + i) as f64 / RATE
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn python_float_repr() {
        assert_eq!(py_float(0.4167), "0.4167");
        assert_eq!(py_float(2.0), "2.0");
        assert_eq!(py_float(0.0), "0.0");
        assert_eq!(py_float(1e-5), "1e-05");
        assert_eq!(py_float(0.0001), "0.0001");
        assert_eq!(py_float(1.5e16), "1.5e+16");
        assert_eq!(py_float(-12.25), "-12.25");
        assert_eq!(round_to(0.41666666, 4), 0.4167);
        assert_eq!(round_to(10.0 / 24.0, 4), 0.4167);
    }

    #[test]
    fn n_rounds_like_python() {
        // test_sfx.py checked sfx._n: at least one sample, half to even
        assert_eq!(n_of(0.0), 1);
        assert_eq!(n_of(1.0), 44100);
        assert_eq!(n_of(0.5 / RATE), 1);
        assert_eq!(n_of(2.5 / RATE), 2);
    }

    #[test]
    fn metal_hit_is_a_short_chink() {
        // a stab dies fast and a heavier one lasts longer; a clash rings longer than a stab
        let light = metal_hit("light", &mut Rng::new(&[1]), 1.0).unwrap();
        let fin = metal_hit("finisher", &mut Rng::new(&[1]), 1.0).unwrap();
        assert!(light.len() < fin.len());
        let clash = metal_clash("heavy", &mut Rng::new(&[1]), 1.0).unwrap();
        assert!(clash.len() > light.len());
    }

    #[test]
    fn thunder_rolls_longer_when_heavier() {
        let th = thunder("finisher", &mut Rng::new(&[5]), 1.0).unwrap();
        assert!(th.len() as f64 / RATE > 3.0);
        assert!(thunder("light", &mut Rng::new(&[5]), 1.0).unwrap().len() < th.len());
    }

    #[test]
    fn highpass_removes_dc() {
        let x = vec![1.0; 4000];
        assert!(highpass(&x, 500.0)[3999].abs() < 1e-9);
    }
}
