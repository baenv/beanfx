//! The export commands: sheet and Aseprite JSON writing, the checks, the act checks, hit-stop, the preview page.
//! Port of kit/export.py; the Python module keeps the authoring helpers and calls these through kit/bridge.py.

mod page;
mod py;

use crate::job::{Answer, Job};
use crate::npy::Array;
use serde_json::{json, Map, Value};
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};

const MAX_EDGE: i64 = 4096; // a texture side most GPUs and WebGL2 phones take
const VRAM_NOTE: f64 = 64e6; // bytes of decoded sheets above which write() notes the texture memory
const BUDGET_MB: i64 = 128; // check() fails past this: one full MAX_EDGE page each for the colour and the light sheet
const TRIM: f64 = 1.0 / 3.0; // check() fails when trimming the lopsided margins would save more than this share
const FILL_MASS: f64 = 0.96; // the share of the colour the framing box holds, 2 % cut from each end
const LIGHT_EDGE: f64 = 0.02; // light below this may reach the cell edge
const POP: f64 = 0.05; // the last frame of a one-shot may keep at most this share of the peak frame's pixels

const POSES: [&str; 8] = ["idle", "guard", "windup", "cast", "channel", "release", "follow", "recover"];
const REACTS: [&str; 5] = ["none", "flinch", "stagger", "knockback", "launch"];

/// Weight classes of a contact: freeze and shake_time in s, shake and push in px, flash in s.
struct Weight {
    name: &'static str,
    freeze: f64,
    shake: i64,
    shake_time: f64,
    push: i64,
    react: &'static str,
    flash: f64,
}

const WEIGHTS: [Weight; 4] = [
    Weight { name: "light", freeze: 0.05, shake: 1, shake_time: 0.07, push: 1, react: "flinch", flash: 0.03 },
    Weight { name: "heavy", freeze: 0.13, shake: 3, shake_time: 0.12, push: 4, react: "knockback", flash: 0.07 },
    Weight { name: "finisher", freeze: 0.25, shake: 6, shake_time: 0.2, push: 10, react: "launch", flash: 0.12 },
    Weight { name: "blast", freeze: 0.08, shake: 5, shake_time: 0.27, push: 8, react: "knockback", flash: 0.1 },
];

pub fn run(cmd: &str, j: &Job) -> Result<Answer, String> {
    match cmd {
        "consts" => Ok(Answer::of(consts())),
        "grid" => {
            let (c, r) = grid(int(j, "n")?, int(j, "w")?, int(j, "h")?, j.arg("columns").and_then(Value::as_i64));
            Ok(Answer::of(json!([c, r])))
        }
        "check_act" => {
            let a = j.arg("act").ok_or("check_act: no act")?;
            let bad = check_act(a, int(j, "frames")?, j.bool("loop"))?;
            Ok(Answer::of(json!(bad)))
        }
        "hitstop" => hitstop(j),
        "framing" => {
            let a = j.array("frames")?;
            let f = Frames::of(&a)?;
            Ok(Answer::of(framing(&f).map(|r| r.json()).unwrap_or(Value::Null)))
        }
        "colours" => {
            let a = j.array("frame")?;
            if !a.is_u8() {
                return Err("colours: frame must be uint8".into());
            }
            let c = *a.shape.last().ok_or("colours: empty shape")?;
            Ok(Answer::of(json!(colours(a.as_u8(), c))))
        }
        "memory_mb" => {
            let light = j.bool("light");
            Ok(Answer::of(json!(memory_mb(int(j, "n")?, int(j, "w")?, int(j, "h")?, light))))
        }
        "check" => check_cmd(j),
        "edges" => edges(j),
        "write" => write(j),
        "page" => page::page(j),
        _ => Err(format!("export: unknown command {cmd:?}")),
    }
}

fn int(j: &Job, k: &str) -> Result<i64, String> {
    j.arg(k).and_then(Value::as_i64).ok_or_else(|| format!("export: missing integer {k}"))
}

fn consts() -> Value {
    let mut w = Map::new();
    for x in &WEIGHTS {
        w.insert(x.name.into(), json!({"freeze": x.freeze, "shake": x.shake, "shake_time": x.shake_time,
                                       "push": x.push, "react": x.react, "flash": x.flash}));
    }
    json!({"WEIGHTS": Value::Object(w), "POSES": POSES, "REACTS": REACTS, "MAX_EDGE": MAX_EDGE, "VRAM_NOTE": VRAM_NOTE,
           "BUDGET_MB": BUDGET_MB, "TRIM": TRIM, "FILL_MASS": FILL_MASS, "LIGHT_EDGE": LIGHT_EDGE, "POP": POP})
}

// ---- frames ----

/// Frames as one block: (rows, n, h, w, c) uint8; a (n, h, w, c) array is one row.
struct Frames<'a> {
    rows: usize,
    n: usize,
    h: usize,
    w: usize,
    c: usize,
    data: &'a [u8],
}

impl<'a> Frames<'a> {
    fn of(a: &'a Array) -> Result<Frames<'a>, String> {
        if !a.is_u8() {
            return Err("frames must be uint8".into());
        }
        let s = &a.shape;
        let (rows, n, h, w, c) = match s.len() {
            4 => (1, s[0], s[1], s[2], s[3]),
            5 => (s[0], s[1], s[2], s[3], s[4]),
            _ => return Err(format!("frames must be (n,h,w,c) or (r,n,h,w,c), got {s:?}")),
        };
        if rows * n == 0 {
            return Err("no frames".into());
        }
        Ok(Frames { rows, n, h, w, c, data: a.as_u8() })
    }

    fn count(&self) -> usize {
        self.rows * self.n
    }

    fn frame(&self, k: usize) -> &'a [u8] {
        let sz = self.h * self.w * self.c;
        &self.data[k * sz..(k + 1) * sz]
    }

    fn alpha(&self, k: usize) -> Vec<bool> {
        self.frame(k).chunks(self.c).map(|p| p[3.min(self.c - 1)] > 0).collect()
    }
}

fn on_edge(y: usize, x: usize, h: usize, w: usize) -> bool {
    y == 0 || x == 0 || y + 1 == h || x + 1 == w
}

struct Framing {
    x0: i64,
    y0: i64,
    x1: i64,
    y1: i64,
    w: i64,
    h: i64,
    cut: [i64; 4],
    trim: f64,
}

impl Framing {
    fn json(&self) -> Value {
        json!({"box": [self.x0, self.y0, self.x1, self.y1], "cell": [self.w, self.h], "cut": self.cut, "trim": self.trim})
    }
}

/// Where the drawing sits in its cell; None when no frame has colour.
fn framing(f: &Frames) -> Option<Framing> {
    let (h, w) = (f.h, f.w);
    let mut occ = vec![0.0f64; h * w];
    for k in 0..f.count() {
        for (p, on) in f.alpha(k).into_iter().enumerate() {
            if on {
                occ[p] += 1.0;
            }
        }
    }
    if occ.iter().all(|&v| v == 0.0) {
        return None;
    }
    let q = (1.0 - FILL_MASS) / 2.0;
    let span = |m: &[f64]| -> (i64, i64) {
        let total: f64 = m.iter().sum();
        let mut run = 0.0;
        let c: Vec<f64> = m.iter().map(|v| { run += v; run / total }).collect();
        (c.partition_point(|&v| v < q) as i64, c.partition_point(|&v| v < 1.0 - q) as i64)
    };
    let cols: Vec<f64> = (0..w).map(|x| (0..h).map(|y| occ[y * w + x]).sum()).collect();
    let rows: Vec<f64> = (0..h).map(|y| occ[y * w..(y + 1) * w].iter().sum()).collect();
    let (x0, x1) = span(&cols);
    let (y0, y1) = span(&rows);
    let (wi, hi) = (w as i64, h as i64);
    let (left, right, top, bottom) = (x0, wi - 1 - x1, y0, hi - 1 - y1);
    let cut = [(left - right).max(0), (top - bottom).max(0), (right - left).max(0), (bottom - top).max(0)];
    let trim = 1.0 - ((wi - cut[0] - cut[2]) * (hi - cut[1] - cut[3])) as f64 / (wi * hi) as f64;
    Some(Framing { x0, y0, x1, y1, w: wi, h: hi, cut, trim })
}

/// Distinct colours in one frame of c channels, fully transparent pixels left out.
fn colours(frame: &[u8], c: usize) -> usize {
    let mut seen = std::collections::HashSet::new();
    for p in frame.chunks(c) {
        if c == 4 && p[3] == 0 {
            continue;
        }
        seen.insert(p);
    }
    seen.len()
}

fn memory_mb(n: i64, w: i64, h: i64, light: bool) -> f64 {
    (n * w * h * 4 * if light { 2 } else { 1 }) as f64 / 1e6
}

// ---- act ----

fn check_act(a: &Value, frames: i64, looped: bool) -> Result<Vec<String>, String> {
    let mut bad = vec![];
    let none = vec![];
    let hits = a.get("hits").and_then(Value::as_array).unwrap_or(&none);
    let keys = a.get("poses").and_then(Value::as_array).unwrap_or(&none);
    let num = |v: Option<&Value>| v.and_then(Value::as_f64);
    let need = |h: &'_ Value, k: &str| -> Result<(), String> { h.get(k).map(|_| ()).ok_or_else(|| format!("KeyError: '{k}'")) };
    let names: Vec<&str> = WEIGHTS.iter().map(|w| w.name).collect();
    for h in hits {
        need(h, "frame")?;
        let fv = num(h.get("frame")).unwrap_or(f64::NAN);
        let fs = py::show(&h["frame"]);
        if !(0.0 <= fv && fv < frames as f64) {
            bad.push(format!("act: hit at frame {fs} is outside the {frames} frames"));
        }
        if num(h.get("freeze")).unwrap_or(0.0) > 0.3 {
            bad.push(format!("act: hit at frame {fs} freezes {} s; past 0.3 s it reads as a stall", py::show(&h["freeze"])));
        }
        let react = h.get("react").cloned().unwrap_or_else(|| json!("none"));
        if !react.as_str().map(|r| REACTS.contains(&r)).unwrap_or(false) {
            bad.push(format!("act: hit at frame {fs} react {} not in {}", py::repr(&react), py::tuple_repr(&REACTS)));
        }
        if let Some(w) = h.get("weight").filter(|w| !w.is_null()) {
            if !w.as_str().map(|s| names.contains(&s)).unwrap_or(false) {
                bad.push(format!("act: hit at frame {fs} weight {} not in {}", py::repr(w), py::tuple_repr(&names)));
            }
        }
        let st = num(h.get("shake_time")).unwrap_or(0.0);
        if !(0.0 <= st && st <= 0.6) {
            bad.push(format!("act: hit at frame {fs} shakes {} s; keep it within 0.6 s", py::show(&h["shake_time"])));
        }
        if num(h.get("flash")).unwrap_or(0.0) > 0.25 {
            bad.push(format!("act: hit at frame {fs} flashes {} s; past 0.25 s it reads as a stun", py::show(&h["flash"])));
        }
    }
    for (i, k) in keys.iter().enumerate() {
        need(k, "pose")?;
        need(k, "t")?;
        if !k["pose"].as_str().map(|p| POSES.contains(&p)).unwrap_or(false) {
            bad.push(format!("act: pose {} at t {} not in {}", py::repr(&k["pose"]), py::show(&k["t"]), py::tuple_repr(&POSES)));
        }
        if i > 0 && num(k.get("t")) < num(keys[i - 1].get("t")) {
            bad.push(format!("act: pose keys out of order at t {}", py::show(&k["t"])));
        }
    }
    if !keys.is_empty() && !hits.is_empty() {
        let t0 = num(hits[0].get("t"));
        let released = keys.iter().any(|k| matches!(k["pose"].as_str(), Some("release") | Some("cast")) && num(k.get("t")) <= t0);
        if !released {
            bad.push("act: no release or cast pose before the first hit".into());
        }
    }
    if looped && !keys.is_empty() && !py::eq(&keys[0]["pose"], &keys[keys.len() - 1]["pose"]) {
        bad.push("act: a loop's poses end on a different pose than they start".into());
    }
    Ok(bad)
}

// ---- hit-stop ----

fn hitstop(j: &Job) -> Result<Answer, String> {
    let a = j.array("frames")?;
    if !a.is_u8() || a.shape.len() != 4 {
        return Err("hitstop: frames must be uint8 (n,h,w,c)".into());
    }
    let (n, h, w, c) = (a.shape[0], a.shape[1], a.shape[2], a.shape[3]);
    let data = a.as_u8();
    let sz = h * w * c;
    let fps = j.f64("fps").ok_or("hitstop: no fps")?;
    let mut by: HashMap<i64, &Value> = HashMap::new();
    for hit in j.arg("hits").and_then(Value::as_array).into_iter().flatten() {
        let f = hit.get("frame").and_then(Value::as_f64).ok_or("KeyError: 'frame'")?;
        by.insert(f as i64, hit);
    }
    // (frames left, total, amp, ux, uy) of the running shake
    let mut shake: Option<(i64, i64, f64, f64, f64)> = None;
    let mut out: Vec<u8> = vec![];
    let mut count = 0usize;
    let shaken = |f: &[u8], out: &mut Vec<u8>, shake: &mut Option<(i64, i64, f64, f64, f64)>| {
        let Some((left, total, amp, ux, uy)) = *shake else {
            out.extend_from_slice(f);
            return;
        };
        let d = amp * left as f64 / total.max(1) as f64;
        let sgn = if left % 2 != 0 { 1.0 } else { -1.0 };
        let dx = (sgn * d * ux).round_ties_even() as i64;
        let dy = (sgn * d * uy).round_ties_even() as i64;
        *shake = if left - 1 <= 0 { None } else { Some((left - 1, total, amp, ux, uy)) };
        if dx == 0 && dy == 0 {
            out.extend_from_slice(f);
            return;
        }
        for y in 0..h {
            let sy = (y as i64 - dy).rem_euclid(h as i64) as usize;
            for x in 0..w {
                let sx = (x as i64 - dx).rem_euclid(w as i64) as usize;
                let at = (sy * w + sx) * c;
                out.extend_from_slice(&f[at..at + c]);
            }
        }
    };
    let get = |h: &Value, k: &str| h.get(k).and_then(Value::as_f64).unwrap_or(0.0);
    for i in 0..n {
        let f = &data[i * sz..(i + 1) * sz];
        if let Some(hit) = by.get(&(i as i64)) {
            let hold = (get(hit, "freeze") * fps).round_ties_even().max(0.0) as i64;
            let amp = get(hit, "shake");
            let ang = get(hit, "dir").to_radians();
            let k = ((get(hit, "shake_time").max(get(hit, "freeze"))) * fps).round_ties_even().max(1.0) as i64;
            shake = if amp != 0.0 { Some((k, k, amp, ang.cos(), ang.sin())) } else { None };
            out.extend_from_slice(f);
            count += 1;
            for _ in 0..hold {
                shaken(f, &mut out, &mut shake);
                count += 1;
            }
            continue;
        }
        shaken(f, &mut out, &mut shake);
        count += 1;
    }
    let mut ans = Answer::of(Value::Null);
    ans.arrays.insert("frames".into(), Array::u8(vec![count, h, w, c], out));
    Ok(ans)
}

// ---- grid, sheets ----

fn grid(n: i64, w: i64, h: i64, columns: Option<i64>) -> (i64, i64) {
    let cols = match columns.filter(|&c| c != 0) {
        Some(c) => c,
        None => (n as f64 * h as f64 / w as f64).sqrt().ceil().max(1.0).min(n as f64) as i64,
    };
    (cols, (n + cols - 1) / cols)
}

/// (frames per page, columns): one page when the near-square grid fits, else pages as full as max_edge takes.
fn page_grid(n: i64, w: i64, h: i64, columns: Option<i64>, max_edge: i64) -> Result<(i64, i64), String> {
    let (cols, rows) = grid(n, w, h, columns);
    if cols * w <= max_edge && rows * h <= max_edge {
        return Ok((n, cols));
    }
    let (cmax, rmax) = (max_edge / w, max_edge / h);
    if cmax < 1 || rmax < 1 {
        return Err(format!("a {w}x{h} cell passes {max_edge} px"));
    }
    Ok((cmax * rmax, cmax))
}

fn row_names(n: usize) -> Vec<String> {
    let v = |a: &[&str]| a.iter().map(|s| s.to_string()).collect();
    match n {
        1 => vec![String::new()],
        8 => v(&["east", "south-east", "south", "south-west", "west", "north-west", "north", "north-east"]),
        4 => v(&["east", "south", "west", "north"]),
        _ => (0..n).map(|k| format!("dir{k}")).collect(),
    }
}

/// The frames of `data` (frame size sz values) as a sheet of cols across, keeping the first `ch` channels.
fn sheet(frames: &[&[u8]], cols: usize, w: usize, h: usize, src_c: usize, ch: usize) -> (usize, usize, Vec<u8>) {
    let rows = (frames.len() + cols - 1) / cols;
    let mut img = vec![0u8; rows * h * cols * w * ch];
    for (i, f) in frames.iter().enumerate() {
        let (x, y) = ((i % cols) * w, (i / cols) * h);
        for yy in 0..h {
            for xx in 0..w {
                let s = (yy * w + xx) * src_c;
                let d = ((y + yy) * cols * w + x + xx) * ch;
                img[d..d + ch].copy_from_slice(&f[s..s + ch]);
            }
        }
    }
    (cols * w, rows * h, img)
}

fn save_png(path: &Path, w: usize, h: usize, rgba: bool, data: &[u8]) -> Result<(), String> {
    let f = fs::File::create(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut enc = png::Encoder::new(std::io::BufWriter::new(f), w as u32, h as u32);
    enc.set_color(if rgba { png::ColorType::Rgba } else { png::ColorType::Rgb });
    enc.set_depth(png::BitDepth::Eight);
    let mut wr = enc.write_header().map_err(|e| e.to_string())?;
    wr.write_image_data(data).map_err(|e| e.to_string())
}

/// The light as u8 frames: u8 stays, floats become clip(0, 1) * 255 rounded half to even.
fn light_u8(a: &Array) -> Vec<u8> {
    if a.is_u8() {
        return a.as_u8().to_vec();
    }
    a.to_f64().iter().map(|&v| (v.clamp(0.0, 1.0) * 255.0).round_ties_even() as u8).collect()
}

/// The act the JSON carries: windup (s before frame 0), hits, poses, target.
fn build_act(hits: Option<&Value>, windup: &Value, poses: Option<&Value>, target: Option<&Value>) -> Result<Value, String> {
    let poses: Vec<Value> = poses.and_then(Value::as_array).cloned().unwrap_or_default();
    let mut wv = windup.clone();
    if let Some(t) = poses.first().and_then(|p| p.get("t")) {
        let tf = t.as_f64().ok_or("act: pose t is not a number")?;
        if tf < 0.0 {
            let neg = if let Some(i) = t.as_i64() { json!(-i) } else { json!(-tf) };
            if -tf > windup.as_f64().unwrap_or(0.0) {
                wv = neg;
            }
        }
    }
    let windup = if wv.is_f64() { json!(py::round_n(wv.as_f64().unwrap(), 4)) } else { wv };
    let mut a = Map::new();
    a.insert("windup".into(), windup);
    a.insert("hits".into(), Value::Array(hits.and_then(Value::as_array).cloned().unwrap_or_default()));
    if !poses.is_empty() {
        a.insert("poses".into(), Value::Array(poses));
    }
    if let Some(t) = target.filter(|t| py::truth(t)) {
        a.insert("target".into(), t.clone());
    }
    Ok(Value::Object(a))
}

fn tag(name: &str, from: i64, to: i64) -> Value {
    json!({"name": name, "from": from, "to": to, "direction": "forward"})
}

fn aseprite(entries: Vec<Value>, tags: Vec<Value>, image: &str, size: Value, bfx: Map<String, Value>) -> Value {
    json!({"frames": entries, "meta": {"app": "beanfx", "version": "1", "image": image, "format": "RGBA8888", "size": size,
                                        "scale": "1", "frameTags": tags, "beanfx": bfx}})
}

fn write(j: &Job) -> Result<Answer, String> {
    let out = PathBuf::from(j.str("out").ok_or("write: no out")?);
    let name = j.str("name").ok_or("write: no name")?.to_string();
    fs::create_dir_all(&out).map_err(|e| format!("{}: {e}", out.display()))?;
    let fa = j.array("frames")?;
    let fr = Frames::of(&fa)?;
    let (n, nrows, h, w) = (fr.n, fr.rows, fr.h, fr.w);
    if fr.c < 4 {
        return Err("write: frames need 4 channels".into());
    }
    let total = fr.count();
    let flat: Vec<&[u8]> = (0..total).map(|k| fr.frame(k)).collect();
    let per_frame = |a: &Array, what: &str, min: usize| -> Result<usize, String> {
        let c = a.len() / (total * h * w).max(1);
        if a.len() != total * h * w * c || c < min {
            return Err(format!("write: {what} must match the frames, with at least {min} channels"));
        }
        Ok(c)
    };
    let light = if j.has("light") { Some(j.array("light")?) } else { None };
    let color = if j.has("color") { Some(j.array("color")?) } else { None };
    let lbytes = light.as_ref().map(light_u8);
    let lc = match &light {
        Some(l) => per_frame(l, "light", 3)?,
        None => 3,
    };
    let lflat: Option<Vec<&[u8]>> = lbytes.as_ref().map(|b| (0..total).map(|k| &b[k * h * w * lc..(k + 1) * h * w * lc]).collect());
    let (cflat, cc): (Option<Vec<&[u8]>>, usize) = match &color {
        Some(c) => {
            if !c.is_u8() {
                return Err("write: color must be uint8".into());
            }
            let cc = per_frame(c, "color", 4)?;
            (Some((0..total).map(|k| &c.as_u8()[k * h * w * cc..(k + 1) * h * w * cc]).collect()), cc)
        }
        None => (None, 4),
    };

    let max_edge = j.arg("max_edge").and_then(Value::as_i64).unwrap_or(MAX_EDGE);
    let vram_note = j.f64("vram_note").unwrap_or(VRAM_NOTE);
    let columns = j.arg("columns").and_then(Value::as_i64);
    let (per, cols) = page_grid(total as i64, w as i64, h as i64, columns, max_edge)?;
    let npages = (total as i64 + per - 1) / per;

    let names = row_names(nrows);
    let fps = j.arg("fps").ok_or("write: no fps")?.clone();
    let ms = (1000.0 / fps.as_f64().ok_or("write: fps is not a number")?).round_ties_even() as i64;
    let states = j.arg("states").and_then(Value::as_object).cloned().unwrap_or_default();
    let mut tags = vec![];
    for r in 0..nrows {
        let base = (r * n) as i64;
        if nrows > 1 {
            tags.push(tag(&names[r], base, base + n as i64 - 1));
        }
        for (s, ab) in &states {
            let (a, b) = (ab.get(0).and_then(Value::as_i64), ab.get(1).and_then(Value::as_i64));
            let (a, b) = a.zip(b).ok_or("write: a state is [from, to] in integers")?;
            let label = if nrows > 1 { format!("{}/{s}", names[r]) } else { s.clone() };
            tags.push(tag(&label, base + a, base + b));
        }
    }
    if tags.is_empty() {
        tags.push(tag(&name, 0, n as i64 - 1));
    }

    let looped = j.bool("loop");
    let hold = j.bool("hold");
    let pivot = j.arg("pivot").and_then(Value::as_array).cloned().ok_or("write: no pivot")?;
    let mut bfx = Map::new();
    bfx.insert("name".into(), json!(name));
    bfx.insert("fps".into(), fps);
    bfx.insert("loop".into(), json!(looped));
    bfx.insert("end".into(), json!(if looped { "loop" } else if hold { "hold" } else { "remove" }));
    bfx.insert("frames".into(), json!(n));
    bfx.insert("rows".into(), json!(nrows));
    bfx.insert("frameSize".into(), json!([w, h]));
    bfx.insert("pivot".into(), Value::Array(pivot));
    bfx.insert("columns".into(), json!(cols));
    if light.is_some() {
        bfx.insert("blend_light".into(), json!("add"));
        bfx.insert("light_gain".into(), json!(1.0));
    }
    if !states.is_empty() {
        let st: Map<String, Value> = states.iter().map(|(k, v)| (k.clone(), v.clone())).collect();
        bfx.insert("states".into(), Value::Object(st));
    }
    let windup = j.args.get("windup").cloned().unwrap_or(json!(0.0));
    let (hits, poses, target) = (j.arg("hits"), j.arg("poses"), j.arg("target"));
    if hits.map(py::truth).unwrap_or(false) || py::truth(&windup) || poses.map(py::truth).unwrap_or(false) || target.map(py::truth).unwrap_or(false) {
        bfx.insert("act".into(), build_act(hits, &windup, poses, target)?);
    }
    let extra = j.arg("extra").and_then(Value::as_object).cloned().unwrap_or_default();
    let mut clash: Vec<&String> = extra.iter().filter(|(k, v)| bfx.get(*k).map(|b| !py::eq(v, b)).unwrap_or(false)).map(|(k, _)| k).collect();
    if !clash.is_empty() {
        clash.sort();
        let list: Vec<String> = clash.iter().map(|k| py::str_repr(k)).collect();
        return Err(format!("extra would overwrite [{}] of meta.beanfx", list.join(", ")));
    }
    for (k, v) in &extra {
        bfx.insert(k.clone(), v.clone());
    }

    let mut entries = vec![];
    let mut pages = vec![];
    let mut js = Value::Null;
    for k in 0..npages {
        let stem = if npages == 1 { name.clone() } else { format!("{name}_p{k}") };
        let (lo, hi) = ((k * per) as usize, total.min(((k + 1) * per) as usize));
        let mut files = Map::new();
        files.insert("image".into(), json!(format!("{stem}.png")));
        let (sw, sh, img) = sheet(&flat[lo..hi], cols as usize, w, h, fr.c, 4);
        save_png(&out.join(format!("{stem}.png")), sw, sh, true, &img)?;
        if let Some(l) = &lflat {
            files.insert("light".into(), json!(format!("{stem}_light.png")));
            let (sw, sh, img) = sheet(&l[lo..hi], cols as usize, w, h, lc, 3);
            save_png(&out.join(format!("{stem}_light.png")), sw, sh, false, &img)?;
        }
        if let Some(c) = &cflat {
            files.insert("color".into(), json!(format!("{stem}_color.png")));
            let (sw, sh, img) = sheet(&c[lo..hi], cols as usize, w, h, cc, 4);
            save_png(&out.join(format!("{stem}_color.png")), sw, sh, true, &img)?;
        }
        let size = json!({"w": cols * w as i64, "h": (((hi - lo) as i64 + cols - 1) / cols) * h as i64});
        let mut local = vec![];
        for i in lo..hi {
            let (r, f) = (i / n, i % n);
            let fname = [name.as_str(), names[r].as_str(), &f.to_string()].iter().filter(|p| !p.is_empty()).cloned().collect::<Vec<_>>().join(" ");
            let j_ = (i - lo) as i64;
            let e = json!({"filename": fname, "frame": {"x": (j_ % cols) * w as i64, "y": (j_ / cols) * h as i64, "w": w, "h": h},
                           "rotated": false, "trimmed": false, "spriteSourceSize": {"x": 0, "y": 0, "w": w, "h": h},
                           "sourceSize": {"w": w, "h": h}, "duration": ms});
            local.push(e.clone());
            if npages > 1 {
                let mut m = e.as_object().unwrap().clone();
                m.insert("page".into(), json!(k));
                entries.push(Value::Object(m));
            } else {
                entries.push(e);
            }
        }
        if npages > 1 {
            let (first, last) = (lo as i64, hi as i64 - 1);
            let ptags: Vec<Value> = tags.iter().filter(|t| t["from"].as_i64().unwrap() <= last && t["to"].as_i64().unwrap() >= first).map(|t| {
                let mut m = t.as_object().unwrap().clone();
                m.insert("from".into(), json!(t["from"].as_i64().unwrap().max(first) - first));
                m.insert("to".into(), json!(t["to"].as_i64().unwrap().min(last) - first));
                Value::Object(m)
            }).collect();
            let mut pb = bfx.clone();
            pb.insert("page".into(), json!(k));
            pb.insert("first".into(), json!(first));
            for (fk, fv) in &files {
                pb.insert(fk.clone(), fv.clone());
            }
            let image = files["image"].as_str().unwrap().to_string();
            let pj = aseprite(local, ptags, &image, size, pb);
            fs::write(out.join(format!("{stem}.json")), py::dumps(&pj, Some(1))).map_err(|e| e.to_string())?;
            let mut pg = files.clone();
            pg.insert("json".into(), json!(format!("{stem}.json")));
            pg.insert("first".into(), json!(first));
            pg.insert("last".into(), json!(last));
            pages.push(Value::Object(pg));
        } else {
            bfx.insert("sheet".into(), files["image"].clone());
            for x in ["light", "color"] {
                if let Some(v) = files.get(x) {
                    bfx.insert(x.into(), v.clone());
                }
            }
            let image = files["image"].as_str().unwrap().to_string();
            js = aseprite(local, tags.clone(), &image, size, bfx.clone());
        }
    }
    if npages > 1 {
        let image = pages[0]["image"].as_str().unwrap().to_string();
        bfx.insert("pages".into(), Value::Array(pages));
        let size = json!({"w": cols * w as i64, "h": ((per + cols - 1) / cols) * h as i64});
        js = aseprite(entries, tags, &image, size, bfx);
    }
    fs::write(out.join(format!("{name}.json")), py::dumps(&js, Some(1))).map_err(|e| e.to_string())?;
    let vram = (total * w * h * 4 * if light.is_some() && color.is_some() { 2 } else { 1 }) as f64;
    let mut ans = Answer::of(js);
    if vram > vram_note {
        ans.print.push(format!("note: {name} needs about {} MB of texture memory decoded (colour and light); porting.md, Budget",
                               py::fmt0(vram / 1e6)));
    }
    Ok(ans)
}

// ---- checks ----

/// Positions of the draft source that match the unseeded-randomness pattern, as 1-based line numbers (UNSEEDED, re.M).
fn unseeded_lines(text: &str) -> Vec<usize> {
    let c: Vec<char> = text.chars().collect();
    let word = |ch: char| ch.is_alphanumeric() || ch == '_';
    let space = |ch: char| ch.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&ch);
    let starts = |at: usize, lit: &str| -> bool { lit.chars().enumerate().all(|(k, l)| c.get(at + k) == Some(&l)) };
    let names = ["rand", "randn", "randint", "random", "uniform", "normal", "choice", "shuffle", "permutation"];
    let mut found = vec![];
    let mut p = 0;
    while p < c.len() {
        let mut end = None;
        if starts(p, "np.random.") {
            let mut e = p + 10;
            while e < c.len() && word(c[e]) {
                e += 1;
            }
            let id: String = c[p + 10..e].iter().collect();
            if names.contains(&id.as_str()) && c.get(e) == Some(&'(') {
                end = Some(e + 1);
            }
        }
        if end.is_none() && starts(p, "default_rng(") {
            let mut e = p + 12;
            while e < c.len() && space(c[e]) {
                e += 1;
            }
            if c.get(e) == Some(&')') {
                end = Some(e + 1);
            }
        }
        if end.is_none() && (p == 0 || c[p - 1] == '\n') {
            let mut e = p;
            while e < c.len() && space(c[e]) {
                e += 1;
            }
            if starts(e, "import random") && !c.get(e + 13).map(|&x| word(x)).unwrap_or(false) {
                end = Some(e + 13);
            } else if starts(e, "from random import") {
                end = Some(e + 18);
            }
        }
        match end {
            Some(e) => {
                found.push(c[..p].iter().filter(|&&x| x == '\n').count() + 1);
                p = e.max(p + 1);
            }
            None => p += 1,
        }
    }
    found
}

fn check_cmd(j: &Job) -> Result<Answer, String> {
    let fa = j.array("frames")?;
    let fr = Frames::of(&fa)?;
    let light = if j.has("light") { Some(j.array("light")?) } else { None };
    let looped = j.bool("loop");
    let hold = j.bool("hold");
    let max_colours = j.arg("max_colours").cloned();
    let trim = match j.args.get("trim") {
        None => Some(TRIM),
        Some(v) => v.as_f64(),
    };
    let max_mb = match j.args.get("max_mb") {
        None => Some(json!(BUDGET_MB)),
        Some(v) if v.is_null() => None,
        Some(v) => Some(v.clone()),
    };
    let mut bad = vec![];
    if let Some(t) = trim {
        if let Some(f) = framing(&fr) {
            if f.trim > t {
                let cuts: Vec<String> = ["left", "top", "right", "bottom"].iter().zip(f.cut).filter(|(_, px)| *px != 0)
                    .map(|(side, px)| format!("{px} px off the {side}")).collect();
                bad.push(format!("framing: {} % of the colour sits in x {}..{}, y {}..{} of the {}x{} cell; cutting {} would save {} % of the sheet with the drawing centred: move the subject or trim the cell (trim=None when the space is wanted)",
                                 py::fmt0(100.0 * FILL_MASS), f.x0, f.x1, f.y0, f.y1, f.w, f.h, cuts.join(" and "), py::fmt0(100.0 * f.trim)));
            }
        }
    }
    let mb = memory_mb(fr.count() as i64, fr.w as i64, fr.h as i64, light.is_some());
    if let Some(m) = &max_mb {
        if mb > m.as_f64().unwrap_or(f64::INFINITY) {
            bad.push(format!("budget: about {} MB of texture memory decoded, over {} MB: fewer frames (a lower fps, a held state as a short loop), a smaller cell, or parts; max_mb=None when the owner accepts the size (porting.md, Budget)",
                             py::fmt0(mb), py::show(m)));
        }
    }
    let (h, w, c) = (fr.h, fr.w, fr.c);
    let lc = match &light {
        Some(l) => {
            let c = l.len() / (fr.count() * h * w).max(1);
            if c == 0 || l.len() != fr.count() * h * w * c {
                return Err("check: light must match the frames".into());
            }
            c
        }
        None => 0,
    };
    let lvals: Option<Vec<f64>> = light.as_ref().map(|l| {
        let raw = l.to_f64();
        if l.is_u8() { raw.into_iter().map(|v| v / 255.0).collect() } else { raw }
    });
    for r in 0..fr.rows {
        let tag = if fr.rows > 1 { format!("row {r} ") } else { String::new() };
        let mut cover = vec![];
        for i in 0..fr.n {
            let k = r * fr.n + i;
            let on = fr.alpha(k);
            let any = on.iter().any(|&b| b);
            if !any {
                bad.push(format!("{tag}frame {i}: empty colour"));
            } else if on.iter().enumerate().any(|(p, &b)| b && on_edge(p / w, p % w, h, w)) {
                bad.push(format!("{tag}frame {i}: colour touches the edge"));
            }
            if let Some(mc) = &max_colours {
                if any {
                    let nc = colours(fr.frame(k), c);
                    if nc as f64 > mc.as_f64().unwrap_or(f64::INFINITY) {
                        bad.push(format!("{tag}frame {i}: {nc} colours, more than {}: cut the light into steps (light.steps) or drop tones", py::show(mc)));
                    }
                }
            }
            if let Some(lv) = &lvals {
                let l = &lv[k * h * w * lc..(k + 1) * h * w * lc];
                let hot = (0..h * w).any(|p| on_edge(p / w, p % w, h, w) && l[p * lc..(p + 1) * lc].iter().cloned().fold(f64::NEG_INFINITY, f64::max) > LIGHT_EDGE);
                if hot {
                    bad.push(format!("{tag}frame {i}: light touches the edge"));
                }
            }
            cover.push(on.iter().filter(|&&b| b).count());
        }
        let peak = *cover.iter().max().unwrap();
        let last = cover[cover.len() - 1];
        if !looped && !hold && cover.len() > 1 && last as f64 > POP * peak as f64 {
            bad.push(format!("{tag}last frame keeps {last} px, {} % of the peak: dissolve to wisps so it does not pop off",
                             py::fmt0(100.0 * last as f64 / peak as f64)));
        }
        if looped && fr.n > 2 {
            let diff = |a: usize, b: usize| -> usize {
                fr.frame(a).chunks(c).zip(fr.frame(b).chunks(c)).filter(|(p, q)| p != q).count()
            };
            let mut step: Vec<usize> = (0..fr.n - 1).map(|i| diff(r * fr.n + i, r * fr.n + i + 1)).collect();
            step.sort();
            let typical = step[(step.len() as f64 * 0.9) as usize];
            let seam = diff(r * fr.n + fr.n - 1, r * fr.n);
            if seam > (2 * typical).max(12) {
                bad.push(format!("{tag}loop seam: {seam} px change from the last frame to the first, a normal step is {typical}"));
            }
        }
    }
    if let Some(src) = j.str("src") {
        let text = fs::read_to_string(src).map_err(|e| format!("{src}: {e}"))?;
        let name = Path::new(src).file_name().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default();
        for line in unseeded_lines(&text) {
            bad.push(format!("{name}:{line}: unseeded randomness; use np.random.default_rng(seed)"));
        }
    }
    Ok(Answer::of(json!(bad)))
}

/// Edge and empty-frame problems of frames the caller rendered with other seeds; labels are [seed, frame] pairs.
fn edges(j: &Job) -> Result<Answer, String> {
    let a = j.array("alpha")?;
    if !a.is_u8() || !(a.shape.len() == 3 || a.shape.len() == 4) {
        return Err("edges: alpha must be uint8 (k,h,w) or (k,h,w,c)".into());
    }
    let (k, h, w) = (a.shape[0], a.shape[1], a.shape[2]);
    let c = if a.shape.len() == 4 { a.shape[3] } else { 1 };
    let at = if c > 3 { 3 } else { c - 1 };
    let labels = j.arg("labels").and_then(Value::as_array).ok_or("edges: no labels")?;
    if labels.len() != k {
        return Err("edges: one label per frame".into());
    }
    let mut bad = vec![];
    for (i, lab) in labels.iter().enumerate() {
        let (sd, f) = (py::show(&lab[0]), py::show(&lab[1]));
        let px = &a.as_u8()[i * h * w * c..(i + 1) * h * w * c];
        let on: Vec<bool> = px.chunks(c).map(|p| p[at] > 0).collect();
        if !on.iter().any(|&b| b) {
            bad.push(format!("seed {sd} frame {f}: empty colour"));
        } else if on.iter().enumerate().any(|(p, &b)| b && on_edge(p / w, p % w, h, w)) {
            bad.push(format!("seed {sd} frame {f}: colour touches the edge"));
        }
    }
    Ok(Answer::of(json!(bad)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn grid_is_near_square() {
        assert_eq!(grid(12, 40, 32, None), (4, 3));
        assert_eq!(grid(1, 8, 8, None), (1, 1));
        assert_eq!(grid(12, 40, 32, Some(5)), (5, 3));
    }

    #[test]
    fn pages_fill_max_edge() {
        assert_eq!(page_grid(12, 40, 32, None, 100).unwrap(), (6, 2));
        assert_eq!(page_grid(12, 40, 32, None, 4096).unwrap(), (12, 4));
        assert!(page_grid(12, 400, 32, None, 100).is_err());
    }

    #[test]
    fn unseeded_matches_the_python_pattern() {
        let t = "import numpy as np\nx = np.random.rand(4)\nimport random\nr = np.random.default_rng(3)\nq = default_rng( )\nz = np.random.rand_x(1)\n";
        assert_eq!(unseeded_lines(t), vec![2, 3, 5]);
        assert_eq!(unseeded_lines("from random import choice\n"), vec![1]);
        assert!(unseeded_lines("import randomly\n").is_empty());
    }

    #[test]
    fn act_checks_read_like_python() {
        let a = json!({"hits": [{"frame": 40, "t": 1.0, "freeze": 0.5, "react": "explode", "shake_time": 0.9, "flash": 0.4, "weight": "huge"}],
                       "poses": [{"t": 0.2, "pose": "windup"}, {"t": 0.1, "pose": "dance"}]});
        let bad = check_act(&a, 12, false).unwrap();
        assert!(bad.contains(&"act: hit at frame 40 is outside the 12 frames".to_string()));
        assert!(bad.contains(&"act: hit at frame 40 freezes 0.5 s; past 0.3 s it reads as a stall".to_string()));
        assert!(bad.iter().any(|b| b.contains("react 'explode' not in ('none', 'flinch'")));
        assert!(bad.contains(&"act: pose 'dance' at t 0.1 not in ('idle', 'guard', 'windup', 'cast', 'channel', 'release', 'follow', 'recover')".to_string()));
        assert!(bad.contains(&"act: pose keys out of order at t 0.1".to_string()));
    }

    #[test]
    fn act_windup_comes_from_the_first_pose() {
        let a = build_act(Some(&json!([])), &json!(0.0), Some(&json!([{"t": -0.3, "pose": "windup"}])), None).unwrap();
        assert_eq!(a["windup"], json!(0.3));
    }
}
