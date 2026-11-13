//! The preview writers of pfx.py and facing.sheet: strip, gif, contact, takes, sheet.
//!
//! Frames arrive as (n, h, w, 4) u8 arrays. Labels use a built-in 5x7 bitmap font, so label pixels differ from
//! PIL's default font; sizes and every pixel outside the label rows match the Python layout.

use crate::job::{Answer, Job};
use crate::npy::Array;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::fs::File;
use std::io::BufWriter;
use std::path::Path;

pub fn run(cmd: &str, j: &Job) -> Result<Answer, String> {
    match cmd {
        "strip" => strip(j),
        "gif" => gif_cmd(j),
        "contact" => contact(j),
        "takes" => takes(j),
        "sheet" => sheet(j),
        _ => Err(format!("preview: unknown command {cmd:?}")),
    }
}

/// Python's round(): halves go to the even neighbour.
fn round_py(x: f64) -> i64 {
    x.round_ties_even() as i64
}

/// An RGBA frame stack: n frames of h x w x 4 bytes.
struct Frames {
    n: usize,
    h: usize,
    w: usize,
    data: Vec<u8>,
}

impl Frames {
    fn of(a: &Array, what: &str) -> Result<Frames, String> {
        if !a.is_u8() || a.shape.len() != 4 || a.shape[3] != 4 {
            return Err(format!("{what}: need a u8 array (n, h, w, 4), got shape {:?}", a.shape));
        }
        if a.shape[0] == 0 {
            return Err(format!("{what}: no frames"));
        }
        Ok(Frames { n: a.shape[0], h: a.shape[1], w: a.shape[2], data: a.as_u8().to_vec() })
    }
    fn frame(&self, i: usize) -> &[u8] {
        let s = self.h * self.w * 4;
        &self.data[i * s..(i + 1) * s]
    }
    fn translucent(&self, i: usize) -> bool {
        self.frame(i).chunks(4).any(|p| p[3] < 255)
    }
}

fn load(j: &Job, name: &str) -> Result<Frames, String> {
    Frames::of(&j.array(name)?, name)
}

/// #rgb, #rgba, #rrggbb or #rrggbbaa as r, g, b, a floats 0..255 (pfx._hexa).
fn hexa(s: &str) -> Result<[f64; 4], String> {
    let mut s: String = s.trim_start_matches('#').to_string();
    if s.len() == 3 || s.len() == 4 {
        s = s.chars().flat_map(|c| [c, c]).collect();
    }
    if s.len() != 6 && s.len() != 8 {
        return Err(format!("bad hex colour #{s}"));
    }
    let mut out = [0.0, 0.0, 0.0, 255.0];
    for k in 0..s.len() / 2 {
        out[k] = u8::from_str_radix(&s[2 * k..2 * k + 2], 16).map_err(|_| format!("bad hex colour #{s}"))? as f64;
    }
    Ok(out)
}

/// The RGB bytes of a frame, transparency composited over bg (pfx._flat, composite with no light).
fn flat(f: &[u8], translucent: bool, bg: [f64; 4]) -> Vec<u8> {
    let mut out = Vec::with_capacity(f.len() / 4 * 3);
    for p in f.chunks(4) {
        if translucent {
            let a = p[3] as f64 / 255.0;
            for c in 0..3 {
                let v = p[c] as f64 / 255.0 * a + bg[c] / 255.0 * (1.0 - a);
                out.push(round_py(v.clamp(0.0, 1.0) * 255.0) as u8);
            }
        } else {
            out.extend_from_slice(&p[..3]);
        }
    }
    out
}

fn scaled(rgb: &[u8], w: usize, h: usize, k: usize) -> Vec<u8> {
    let mut out = Vec::with_capacity(w * h * k * k * 3);
    for y in 0..h {
        let mut row = Vec::with_capacity(w * k * 3);
        for x in 0..w {
            for _ in 0..k {
                row.extend_from_slice(&rgb[(y * w + x) * 3..(y * w + x) * 3 + 3]);
            }
        }
        for _ in 0..k {
            out.extend_from_slice(&row);
        }
    }
    out
}

fn mkdirs(path: &str) -> Result<(), String> {
    match Path::new(path).parent() {
        Some(p) if !p.as_os_str().is_empty() => std::fs::create_dir_all(p).map_err(|e| format!("{}: {e}", p.display())),
        _ => Ok(()),
    }
}

fn write_png(path: &str, w: usize, h: usize, color: png::ColorType, data: &[u8]) -> Result<(), String> {
    mkdirs(path)?;
    let file = File::create(path).map_err(|e| format!("{path}: {e}"))?;
    let mut enc = png::Encoder::new(BufWriter::new(file), w as u32, h as u32);
    enc.set_color(color);
    enc.set_depth(png::BitDepth::Eight);
    let mut wr = enc.write_header().map_err(|e| e.to_string())?;
    wr.write_image_data(data).map_err(|e| e.to_string())
}

fn path_arg(j: &Job) -> Result<&str, String> {
    j.str("path").ok_or_else(|| "preview: no path".to_string())
}

/// Frames side by side, RGBA.
fn strip(j: &Job) -> Result<Answer, String> {
    let f = load(j, "frames")?;
    let mut data = Vec::with_capacity(f.data.len());
    for y in 0..f.h {
        for i in 0..f.n {
            data.extend_from_slice(&f.frame(i)[y * f.w * 4..(y + 1) * f.w * 4]);
        }
    }
    write_png(path_arg(j)?, f.n * f.w, f.h, png::ColorType::Rgba, &data)?;
    Ok(Answer::of(Value::Null))
}

/// Frames stacked as rows (r, n, h, w, 4), one row per heading, frames left to right.
fn sheet(j: &Job) -> Result<Answer, String> {
    let a = j.array("rows")?;
    if !a.is_u8() || a.shape.len() != 5 || a.shape[4] != 4 {
        return Err(format!("sheet: need a u8 array (rows, n, h, w, 4), got shape {:?}", a.shape));
    }
    let (r, n, h, w) = (a.shape[0], a.shape[1], a.shape[2], a.shape[3]);
    let d = a.as_u8();
    let mut out = Vec::with_capacity(d.len());
    for ri in 0..r {
        for y in 0..h {
            for i in 0..n {
                let at = (((ri * n + i) * h + y) * w) * 4;
                out.extend_from_slice(&d[at..at + w * 4]);
            }
        }
    }
    write_png(path_arg(j)?, n * w, r * h, png::ColorType::Rgba, &out)?;
    Ok(Answer::of(Value::Null))
}

// ---- gif ----

/// Median cut of colours with counts down to at most 256 tones.
fn median_cut(counts: &HashMap<[u8; 3], u32>) -> Vec<[u8; 3]> {
    let mut all: Vec<([u8; 3], u32)> = counts.iter().map(|(c, n)| (*c, *n)).collect();
    all.sort();
    let mut boxes: Vec<Vec<([u8; 3], u32)>> = vec![all];
    while boxes.len() < 256 {
        let (bi, ch) = {
            let mut best = (0, 0, 0u32);
            for (i, b) in boxes.iter().enumerate() {
                if b.len() < 2 {
                    continue;
                }
                for c in 0..3 {
                    let lo = b.iter().map(|p| p.0[c]).min().unwrap() as u32;
                    let hi = b.iter().map(|p| p.0[c]).max().unwrap() as u32;
                    if hi - lo >= best.2 && hi > lo {
                        best = (i, c, hi - lo);
                    }
                }
            }
            if best.2 == 0 {
                break;
            }
            (best.0, best.1)
        };
        let mut b = boxes.swap_remove(bi);
        b.sort_by_key(|p| p.0[ch]);
        let total: u64 = b.iter().map(|p| p.1 as u64).sum();
        let (mut acc, mut cut) = (0u64, 1);
        for (k, p) in b.iter().enumerate() {
            acc += p.1 as u64;
            if acc * 2 >= total {
                cut = (k + 1).clamp(1, b.len() - 1);
                break;
            }
        }
        let hi = b.split_off(cut);
        boxes.push(b);
        boxes.push(hi);
    }
    boxes
        .iter()
        .map(|b| {
            let t: u64 = b.iter().map(|p| p.1 as u64).sum();
            let mut c = [0u8; 3];
            for k in 0..3 {
                let s: u64 = b.iter().map(|p| p.0[k] as u64 * p.1 as u64).sum();
                c[k] = ((s + t / 2) / t) as u8;
            }
            c
        })
        .collect()
}

/// A frame as a palette and indices: its exact colours when it has at most 256, else a median cut.
fn indexed(rgb: &[u8]) -> (Vec<u8>, Vec<u8>) {
    let mut counts: HashMap<[u8; 3], u32> = HashMap::new();
    let mut order: Vec<[u8; 3]> = Vec::new();
    for p in rgb.chunks(3) {
        let c = [p[0], p[1], p[2]];
        let e = counts.entry(c).or_insert_with(|| {
            order.push(c);
            0
        });
        *e += 1;
    }
    let pal: Vec<[u8; 3]> = if order.len() <= 256 { order } else { median_cut(&counts) };
    let mut at: HashMap<[u8; 3], u8> = HashMap::new();
    let mut idx = Vec::with_capacity(rgb.len() / 3);
    for p in rgb.chunks(3) {
        let c = [p[0], p[1], p[2]];
        let i = *at.entry(c).or_insert_with(|| {
            let mut best = (0usize, i64::MAX);
            for (k, q) in pal.iter().enumerate() {
                let d: i64 = (0..3).map(|m| (c[m] as i64 - q[m] as i64).pow(2)).sum();
                if d < best.1 {
                    best = (k, d);
                }
            }
            best.0 as u8
        });
        idx.push(i);
    }
    (pal.iter().flatten().copied().collect(), idx)
}

/// Writes RGB frames (all w x h) as a looping gif; each frame carries its own palette.
fn write_gif(path: &str, frames: &[Vec<u8>], w: usize, h: usize, fps: f64, disposal: bool) -> Result<(), String> {
    mkdirs(path)?;
    let file = File::create(path).map_err(|e| format!("{path}: {e}"))?;
    let mut enc = gif::Encoder::new(BufWriter::new(file), w as u16, h as u16, &[]).map_err(|e| e.to_string())?;
    enc.set_repeat(gif::Repeat::Infinite).map_err(|e| e.to_string())?;
    let delay = (round_py(1000.0 / fps) / 10).clamp(0, 65535) as u16;
    for f in frames {
        let (pal, idx) = indexed(f);
        let mut fr = gif::Frame::default();
        fr.width = w as u16;
        fr.height = h as u16;
        fr.delay = delay;
        if disposal {
            fr.dispose = gif::DisposalMethod::Background;
        }
        fr.palette = Some(pal);
        fr.buffer = std::borrow::Cow::Owned(idx);
        enc.write_frame(&fr).map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn gif_cmd(j: &Job) -> Result<Answer, String> {
    let f = load(j, "frames")?;
    let fps = j.f64("fps").ok_or("gif: no fps")?;
    let scale = j.f64("scale").unwrap_or(4.0) as usize;
    let bg = hexa(j.str("bg").unwrap_or("#101018"))?;
    let frames: Vec<Vec<u8>> =
        (0..f.n).map(|i| scaled(&flat(f.frame(i), f.translucent(i), bg), f.w, f.h, scale)).collect();
    write_gif(path_arg(j)?, &frames, f.w * scale, f.h * scale, fps, true)?;
    Ok(Answer::of(Value::Null))
}

// ---- labels ----

/// The classic 5x7 font, ASCII 0x20..0x7e: five columns per glyph, bit 0 the top row.
#[rustfmt::skip]
const FONT: [[u8; 5]; 95] = [
    [0x00,0x00,0x00,0x00,0x00],[0x00,0x00,0x5F,0x00,0x00],[0x00,0x07,0x00,0x07,0x00],[0x14,0x7F,0x14,0x7F,0x14],
    [0x24,0x2A,0x7F,0x2A,0x12],[0x23,0x13,0x08,0x64,0x62],[0x36,0x49,0x56,0x20,0x50],[0x00,0x05,0x03,0x00,0x00],
    [0x00,0x1C,0x22,0x41,0x00],[0x00,0x41,0x22,0x1C,0x00],[0x14,0x08,0x3E,0x08,0x14],[0x08,0x08,0x3E,0x08,0x08],
    [0x00,0x50,0x30,0x00,0x00],[0x08,0x08,0x08,0x08,0x08],[0x00,0x60,0x60,0x00,0x00],[0x20,0x10,0x08,0x04,0x02],
    [0x3E,0x51,0x49,0x45,0x3E],[0x00,0x42,0x7F,0x40,0x00],[0x42,0x61,0x51,0x49,0x46],[0x21,0x41,0x45,0x4B,0x31],
    [0x18,0x14,0x12,0x7F,0x10],[0x27,0x45,0x45,0x45,0x39],[0x3C,0x4A,0x49,0x49,0x30],[0x01,0x71,0x09,0x05,0x03],
    [0x36,0x49,0x49,0x49,0x36],[0x06,0x49,0x49,0x29,0x1E],[0x00,0x36,0x36,0x00,0x00],[0x00,0x56,0x36,0x00,0x00],
    [0x08,0x14,0x22,0x41,0x00],[0x14,0x14,0x14,0x14,0x14],[0x00,0x41,0x22,0x14,0x08],[0x02,0x01,0x51,0x09,0x06],
    [0x32,0x49,0x79,0x41,0x3E],[0x7E,0x11,0x11,0x11,0x7E],[0x7F,0x49,0x49,0x49,0x36],[0x3E,0x41,0x41,0x41,0x22],
    [0x7F,0x41,0x41,0x22,0x1C],[0x7F,0x49,0x49,0x49,0x41],[0x7F,0x09,0x09,0x09,0x01],[0x3E,0x41,0x49,0x49,0x7A],
    [0x7F,0x08,0x08,0x08,0x7F],[0x00,0x41,0x7F,0x41,0x00],[0x20,0x40,0x41,0x3F,0x01],[0x7F,0x08,0x14,0x22,0x41],
    [0x7F,0x40,0x40,0x40,0x40],[0x7F,0x02,0x0C,0x02,0x7F],[0x7F,0x04,0x08,0x10,0x7F],[0x3E,0x41,0x41,0x41,0x3E],
    [0x7F,0x09,0x09,0x09,0x06],[0x3E,0x41,0x51,0x21,0x5E],[0x7F,0x09,0x19,0x29,0x46],[0x46,0x49,0x49,0x49,0x31],
    [0x01,0x01,0x7F,0x01,0x01],[0x3F,0x40,0x40,0x40,0x3F],[0x1F,0x20,0x40,0x20,0x1F],[0x3F,0x40,0x38,0x40,0x3F],
    [0x63,0x14,0x08,0x14,0x63],[0x07,0x08,0x70,0x08,0x07],[0x61,0x51,0x49,0x45,0x43],[0x00,0x7F,0x41,0x41,0x00],
    [0x02,0x04,0x08,0x10,0x20],[0x00,0x41,0x41,0x7F,0x00],[0x04,0x02,0x01,0x02,0x04],[0x40,0x40,0x40,0x40,0x40],
    [0x00,0x01,0x02,0x04,0x00],[0x20,0x54,0x54,0x54,0x78],[0x7F,0x48,0x44,0x44,0x38],[0x38,0x44,0x44,0x44,0x20],
    [0x38,0x44,0x44,0x48,0x7F],[0x38,0x54,0x54,0x54,0x18],[0x08,0x7E,0x09,0x01,0x02],[0x0C,0x52,0x52,0x52,0x3E],
    [0x7F,0x08,0x04,0x04,0x78],[0x00,0x44,0x7D,0x40,0x00],[0x20,0x40,0x44,0x3D,0x00],[0x7F,0x10,0x28,0x44,0x00],
    [0x00,0x41,0x7F,0x40,0x00],[0x7C,0x04,0x18,0x04,0x78],[0x7C,0x08,0x04,0x04,0x78],[0x38,0x44,0x44,0x44,0x38],
    [0x7C,0x14,0x14,0x14,0x08],[0x08,0x14,0x14,0x18,0x7C],[0x7C,0x08,0x04,0x04,0x08],[0x48,0x54,0x54,0x54,0x20],
    [0x04,0x3F,0x44,0x40,0x20],[0x3C,0x40,0x40,0x20,0x7C],[0x1C,0x20,0x40,0x20,0x1C],[0x3C,0x40,0x30,0x40,0x3C],
    [0x44,0x28,0x10,0x28,0x44],[0x0C,0x50,0x50,0x50,0x3C],[0x44,0x64,0x54,0x4C,0x44],[0x00,0x08,0x36,0x41,0x00],
    [0x00,0x00,0x7F,0x00,0x00],[0x00,0x41,0x36,0x08,0x00],[0x10,0x08,0x08,0x10,0x08],
];

/// An RGB canvas.
struct Canvas {
    w: usize,
    h: usize,
    px: Vec<u8>,
}

impl Canvas {
    fn new(w: usize, h: usize, bg: [f64; 4]) -> Canvas {
        let c = [bg[0] as u8, bg[1] as u8, bg[2] as u8];
        Canvas { w, h, px: c.iter().copied().cycle().take(w * h * 3).collect() }
    }

    /// Draws text with its top-left at (x, y); glyphs are 5x7 with a 1 px gap, clipped to the canvas.
    fn text(&mut self, x: usize, y: usize, s: &str, rgb: [u8; 3]) {
        let mut cx = x;
        for ch in s.chars() {
            let g = if (' '..='~').contains(&ch) { FONT[ch as usize - 32] } else { FONT['?' as usize - 32] };
            for (col, bits) in g.iter().enumerate() {
                for row in 0..7 {
                    let (px, py) = (cx + col, y + row);
                    if bits >> row & 1 == 1 && px < self.w && py < self.h {
                        self.px[(py * self.w + px) * 3..(py * self.w + px) * 3 + 3].copy_from_slice(&rgb);
                    }
                }
            }
            cx += 6;
        }
    }

    /// Pastes an RGB cell scaled by k with its top-left at (x, y).
    fn paste(&mut self, rgb: &[u8], w: usize, h: usize, k: usize, x: usize, y: usize) {
        let cell = scaled(rgb, w, h, k);
        let cw = w * k;
        for row in 0..h * k {
            if y + row >= self.h {
                break;
            }
            let n = cw.min(self.w.saturating_sub(x));
            let at = ((y + row) * self.w + x) * 3;
            self.px[at..at + n * 3].copy_from_slice(&cell[row * cw * 3..(row * cw + n) * 3]);
        }
    }

    fn save(&self, path: &str) -> Result<(), String> {
        write_png(path, self.w, self.h, png::ColorType::Rgb, &self.px)
    }
}

/// Python's "%.2f" of a ratio.
fn secs(n: usize, fps: f64) -> String {
    format!("{:.2}", n as f64 / fps)
}

/// Python's str() of a number the caller passed: 24 stays "24", 24.0 stays "24.0".
fn num_text(v: &Value) -> String {
    match v {
        Value::Number(n) if n.is_f64() => format!("{:?}", n.as_f64().unwrap()),
        Value::Number(n) => n.to_string(),
        _ => String::new(),
    }
}

struct Run {
    name: String,
    frames: Frames,
    fps: f64,
    fps_text: String,
}

fn contact(j: &Job) -> Result<Answer, String> {
    let fps_v = j.arg("fps").ok_or("contact: no fps")?;
    let n = j.f64("n").unwrap_or(12.0) as usize;
    let scale = j.f64("scale").unwrap_or(3.0) as usize;
    let bg = hexa(j.str("bg").unwrap_or("#101018"))?;
    let by_time = j.str("by") == Some("time");
    let names: Vec<String> = j
        .arg("names")
        .and_then(Value::as_array)
        .map(|a| a.iter().map(|v| v.as_str().unwrap_or("").to_string()).collect())
        .unwrap_or_else(|| vec!["draft".into(), "ref".into()]);
    let mut runs = vec![Run {
        name: names[0].clone(),
        frames: load(j, "frames")?,
        fps: fps_v.as_f64().ok_or("contact: bad fps")?,
        fps_text: num_text(fps_v),
    }];
    if j.has("ref") {
        let rf = j.arg("ref_fps").ok_or("contact: no ref_fps")?;
        runs.push(Run {
            name: names.get(1).cloned().unwrap_or_default(),
            frames: load(j, "ref")?,
            fps: rf.as_f64().ok_or("contact: bad ref_fps")?,
            fps_text: num_text(rf),
        });
    }
    let span = runs.iter().map(|r| (r.frames.n as f64 - 1.0) / r.fps).fold(f64::MIN, f64::max);
    let denom = (n as f64 - 1.0).max(1.0);
    let picks: Vec<Vec<Option<usize>>> = runs
        .iter()
        .map(|r| {
            (0..n)
                .map(|k| {
                    if by_time {
                        let i = round_py(k as f64 / denom * span * r.fps);
                        (i < r.frames.n as i64).then_some(i as usize)
                    } else {
                        Some(round_py(k as f64 / denom * (r.frames.n as f64 - 1.0)) as usize)
                    }
                })
                .collect()
        })
        .collect();
    let ch = runs.iter().map(|r| r.frames.h).max().unwrap() * scale;
    let cw = runs.iter().map(|r| r.frames.w).max().unwrap() * scale;
    let (lab, gap, head) = (12, 4, 14);
    let mut im = Canvas::new(n * (cw + gap) + gap, runs.len() * (ch + lab + head + gap) + gap, bg);
    for (r, (run, idx)) in runs.iter().zip(&picks).enumerate() {
        let y0 = gap + r * (ch + lab + head + gap);
        let f = &run.frames;
        let head_text = format!("{}: {} frames, {} fps, {} s", run.name, f.n, run.fps_text, secs(f.n, run.fps));
        im.text(gap, y0 + 3, &head_text, [220, 220, 230]);
        for (k, pick) in idx.iter().enumerate() {
            let Some(i) = *pick else { continue };
            let a = flat(f.frame(i), f.translucent(i), bg);
            let x = gap + k * (cw + gap);
            let (w, h) = (f.w * scale, f.h * scale);
            im.paste(&a, f.w, f.h, scale, x + (cw - w) / 2, y0 + head + (ch - h) / 2);
            im.text(x, y0 + head + ch + 2, &format!("f{} {}s", i, secs(i, run.fps)), [170, 170, 185]);
        }
    }
    im.save(path_arg(j)?)?;
    let value: Vec<Value> = picks.iter().map(|r| json!(r)).collect();
    Ok(Answer::of(Value::Array(value)))
}

fn takes(j: &Job) -> Result<Answer, String> {
    let labels: Vec<String> = j
        .arg("labels")
        .and_then(Value::as_array)
        .ok_or("takes: no labels")?
        .iter()
        .map(|v| v.as_str().unwrap_or("").to_string())
        .collect();
    let runs: Vec<Frames> = (0..labels.len()).map(|i| load(j, &format!("take{i}"))).collect::<Result<_, _>>()?;
    if runs.is_empty() {
        return Err("takes: no takes".into());
    }
    let scale = j.f64("scale").unwrap_or(4.0) as usize;
    let bg = hexa(j.str("bg").unwrap_or("#101018"))?;
    let ch = runs.iter().map(|r| r.h).max().unwrap() * scale;
    let cw = runs.iter().map(|r| r.w).max().unwrap() * scale;
    let (gap, head) = (8, 16);
    let size = (runs.len() * (cw + gap) + gap, ch + head + 2 * gap);
    let board = |k: usize| -> Vec<u8> {
        let mut im = Canvas::new(size.0, size.1, bg);
        for (n, (lab, fr)) in labels.iter().zip(&runs).enumerate() {
            let i = k.min(fr.n - 1);
            let a = flat(fr.frame(i), fr.translucent(i), bg);
            let x = gap + n * (cw + gap);
            im.text(x, gap + 2, &format!("{}. {}", n + 1, lab), [220, 220, 230]);
            let (w, h) = (fr.w * scale, fr.h * scale);
            im.paste(&a, fr.w, fr.h, scale, x + (cw - w) / 2, gap + head + (ch - h) / 2);
        }
        im.px
    };
    let path = path_arg(j)?;
    let first = Canvas { w: size.0, h: size.1, px: board(0) };
    first.save(path)?;
    let mut written = vec![path.to_string()];
    let n = runs.iter().map(|r| r.n).max().unwrap();
    let fps = j.f64("fps").unwrap_or(0.0);
    if fps != 0.0 && n > 1 {
        let g = Path::new(path).with_extension("gif").to_string_lossy().to_string();
        let frames: Vec<Vec<u8>> = (0..n).map(board).collect();
        write_gif(&g, &frames, size.0, size.1, fps, false)?;
        written.push(g);
    }
    Ok(Answer::of(json!(written)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_half_even() {
        assert_eq!(round_py(2.5), 2);
        assert_eq!(round_py(3.5), 4);
        assert_eq!(round_py(41.666), 42);
    }

    #[test]
    fn exact_palette_under_256() {
        let rgb: Vec<u8> = (0..300u32).flat_map(|i| [(i % 200) as u8, 5, 9]).collect();
        let (pal, idx) = indexed(&rgb);
        assert_eq!(pal.len(), 200 * 3);
        for (p, i) in rgb.chunks(3).zip(&idx) {
            assert_eq!(&pal[*i as usize * 3..*i as usize * 3 + 3], p);
        }
    }

    #[test]
    fn median_cut_over_256() {
        let rgb: Vec<u8> = (0..1000u32).flat_map(|i| [(i % 250) as u8, (i / 4) as u8, 7]).collect();
        let (pal, idx) = indexed(&rgb);
        assert!(pal.len() <= 256 * 3 && idx.len() == 1000);
    }

    #[test]
    fn translucent_goes_over_bg() {
        let bg = hexa("#101018").unwrap();
        assert_eq!(flat(&[0, 0, 0, 0], true, bg), vec![16, 16, 24]);
    }

    #[test]
    fn python_number_text() {
        assert_eq!(num_text(&json!(24)), "24");
        assert_eq!(num_text(&json!(24.0)), "24.0");
        assert_eq!(secs(25, 24.0), "1.04");
    }
}
