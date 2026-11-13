//! pfx.py: the preview writers strip, gif, contact and takes (the pixelfx layers, tint and composite join later).
//!
//! Frames are RGBA u8 (h, w, 4) as composite gives. Labels use a built-in 5x7 bitmap font, so label pixels differ from
//! PIL's default font; sizes and every pixel outside the label rows match the Python layout.

use crate::stack::{block_u8, Stack};
use ndarray::Array3;
use std::collections::HashMap;
use std::fs::File;
use std::io::BufWriter;
use std::path::{Path, PathBuf};

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
    fn of(f: &[Array3<u8>], what: &str) -> Result<Frames, String> {
        if f.is_empty() {
            return Err(format!("{what}: no frames"));
        }
        let a = block_u8(Stack::Flat(f))?;
        if a.shape[3] != 4 {
            return Err(format!("{what}: need RGBA frames (h, w, 4), got shape {:?}", &a.shape[1..]));
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

/// #rgb, #rgba, #rrggbb or #rrggbbaa as r, g, b, a floats 0..255 (pfx._hexa).
fn hexa(s: &str) -> Result<[f64; 4], String> {
    crate::color::hexa(s).map(|c| c.map(|v| v as f64))
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

fn path_str(p: &Path) -> Result<&str, String> {
    p.to_str().ok_or_else(|| format!("{}: not UTF-8", p.display()))
}

/// Frames side by side, RGBA.
pub fn strip(frames: &[Array3<u8>], path: impl AsRef<Path>) -> Result<(), String> {
    let f = Frames::of(frames, "strip")?;
    let mut data = Vec::with_capacity(f.data.len());
    for y in 0..f.h {
        for i in 0..f.n {
            data.extend_from_slice(&f.frame(i)[y * f.w * 4..(y + 1) * f.w * 4]);
        }
    }
    write_png(path_str(path.as_ref())?, f.n * f.w, f.h, png::ColorType::Rgba, &data)
}

/// Frames stacked as rows, one row per heading, frames left to right (facing.sheet).
pub(crate) fn sheet(rows: &[Vec<Array3<u8>>], path: &Path) -> Result<(), String> {
    let a = block_u8(Stack::Rows(rows))?;
    if a.shape[4] != 4 {
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
    write_png(path_str(path)?, n * w, r * h, png::ColorType::Rgba, &out)
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
    // Pillow merges a frame equal to the one before into it and adds up their durations (in ms, then / 10).
    let ms = round_py(1000.0 / fps);
    let mut runs: Vec<(&Vec<u8>, i64)> = Vec::new();
    for f in frames {
        match runs.last_mut() {
            Some((last, total)) if *last == f => *total += ms,
            _ => runs.push((f, ms)),
        }
    }
    for (f, total) in runs {
        let (pal, idx) = indexed(f);
        let mut fr = gif::Frame::default();
        fr.width = w as u16;
        fr.height = h as u16;
        fr.delay = (total / 10).clamp(0, 65535) as u16;
        if disposal {
            fr.dispose = gif::DisposalMethod::Background;
        }
        fr.palette = Some(pal);
        fr.buffer = std::borrow::Cow::Owned(idx);
        enc.write_frame(&fr).map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// Options of `gif`: scale 4, bg "#101018".
#[derive(Clone, Debug)]
pub struct Gif {
    pub scale: usize,
    pub bg: String,
}

impl Default for Gif {
    fn default() -> Self {
        Gif { scale: 4, bg: "#101018".into() }
    }
}

/// The frames as a looping gif at scale, transparency over bg.
pub fn gif(frames: &[Array3<u8>], path: impl AsRef<Path>, fps: f64, o: Gif) -> Result<(), String> {
    let f = Frames::of(frames, "gif")?;
    let scale = o.scale;
    let bg = hexa(&o.bg)?;
    let frames: Vec<Vec<u8>> =
        (0..f.n).map(|i| scaled(&flat(f.frame(i), f.translucent(i), bg), f.w, f.h, scale)).collect();
    write_gif(path_str(path.as_ref())?, &frames, f.w * scale, f.h * scale, fps, true)
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

/// Python's str() of the fps a caller passes: a whole number reads as an int ("24").
fn num_text(x: f64) -> String {
    crate::py::show(&crate::ex::num(x))
}

struct Run {
    name: String,
    frames: Frames,
    fps: f64,
    fps_text: String,
}

/// Options of `contact`: n 12, scale 3, bg "#101018", no ref, by "phase", names ("draft", "ref").
#[derive(Clone)]
pub struct Contact<'a> {
    pub n: usize,
    pub scale: usize,
    pub bg: String,
    /// A second row (frames, fps) at the same moments, for the benchmark.
    pub r#ref: Option<(&'a [Array3<u8>], f64)>,
    /// "phase" (the same share of each one's length) or "time" (the same seconds).
    pub by: String,
    pub names: [String; 2],
}

impl Default for Contact<'_> {
    fn default() -> Self {
        Contact { n: 12, scale: 3, bg: "#101018".into(), r#ref: None, by: "phase".into(), names: ["draft".into(), "ref".into()] }
    }
}

/// A contact sheet: n moments of the effect in a row, each labelled with its frame and time. Returns the frame
/// indices used per row (None for a cell past the end by "time").
pub fn contact(path: impl AsRef<Path>, frames: &[Array3<u8>], fps: f64, o: Contact) -> Result<Vec<Vec<Option<usize>>>, String> {
    let n = o.n;
    let scale = o.scale;
    let bg = hexa(&o.bg)?;
    let by_time = o.by == "time";
    let names = &o.names;
    let mut runs = vec![Run { name: names[0].clone(), frames: Frames::of(frames, "contact")?, fps, fps_text: num_text(fps) }];
    if let Some((rf, rfps)) = o.r#ref {
        runs.push(Run { name: names[1].clone(), frames: Frames::of(rf, "contact ref")?, fps: rfps, fps_text: num_text(rfps) });
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
    im.save(path_str(path.as_ref())?)?;
    Ok(picks)
}

/// Options of `takes`: no fps (png only), scale 4, bg "#101018".
#[derive(Clone, Debug)]
pub struct Takes {
    pub fps: Option<f64>,
    pub scale: usize,
    pub bg: String,
}

impl Default for Takes {
    fn default() -> Self {
        Takes { fps: None, scale: 4, bg: "#101018".into() }
    }
}

/// Takes to pick from, side by side at scale, each labelled: options is [(label, frames)]. Writes path (png, the first
/// frame of each take) and, with fps and a take of more than one frame, the same name as a gif. Returns the paths.
pub fn takes<S: AsRef<str>>(path: impl AsRef<Path>, options: &[(S, Vec<Array3<u8>>)], o: Takes) -> Result<Vec<PathBuf>, String> {
    let labels: Vec<String> = options.iter().map(|(l, _)| l.as_ref().to_string()).collect();
    let runs: Vec<Frames> = options.iter().map(|(_, f)| Frames::of(f, "takes")).collect::<Result<_, _>>()?;
    if runs.is_empty() {
        return Err("takes: no takes".into());
    }
    let scale = o.scale;
    let bg = hexa(&o.bg)?;
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
    let path = path_str(path.as_ref())?;
    let first = Canvas { w: size.0, h: size.1, px: board(0) };
    first.save(path)?;
    let mut written = vec![path.to_string()];
    let n = runs.iter().map(|r| r.n).max().unwrap();
    let fps = o.fps.unwrap_or(0.0);
    if fps != 0.0 && n > 1 {
        let g = Path::new(path).with_extension("gif").to_string_lossy().to_string();
        let frames: Vec<Vec<u8>> = (0..n).map(board).collect();
        write_gif(&g, &frames, size.0, size.1, fps, false)?;
        written.push(g);
    }
    Ok(written.into_iter().map(PathBuf::from).collect())
}

// ---- pixelfx layers (slice 2a) ------------------------------------------------------------------------------------

use ndarray::Array2;

/// The pixelfx layers of an effect: colour frames (h, w, 4) u8, light frames (h, w, 3) 0..1, and the JSON meta.
/// Light functions take one frame; map them over `light` (`fx.light.iter().map(|f| pfx::tint(f, &ramp))`).
#[derive(Clone, Debug)]
pub struct Layers {
    pub color: Vec<Array3<u8>>,
    pub light: Vec<Array3<f64>>,
    pub meta: serde_json::Value,
}

/// The frames of a sheet strip: n cells of width w.
fn cells<T: Clone>(img: &Array3<T>, n: usize, w: usize) -> Result<Vec<Array3<T>>, String> {
    let (h, sw, c) = img.dim();
    (0..n)
        .map(|i| {
            if (i + 1) * w > sw {
                return Err(format!("sheet is {sw} px wide, frame {i} needs {}", (i + 1) * w));
            }
            Ok(img.slice(ndarray::s![0..h, i * w..(i + 1) * w, 0..c]).to_owned())
        })
        .collect()
}

/// Reads `<folder>/<name>.json`, `<name>_color.png` and `<name>_light.png` (what tools/layers.mjs writes).
pub fn load(folder: impl AsRef<Path>, name: &str) -> Result<Layers, String> {
    let folder = folder.as_ref();
    let jp = folder.join(format!("{name}.json"));
    let text = std::fs::read_to_string(&jp).map_err(|e| format!("{}: {e}", jp.display()))?;
    let meta: serde_json::Value = serde_json::from_str(&text).map_err(|e| format!("{}: {e}", jp.display()))?;
    let n = meta["frames"].as_u64().ok_or("meta has no frames")? as usize;
    let w = meta["w"].as_u64().ok_or("meta has no w")? as usize;
    let color = cells(&crate::img::read(folder.join(format!("{name}_color.png")))?, n, w)?;
    let light = crate::img::read_rgb(folder.join(format!("{name}_light.png")))?.mapv(|v| v as f64 / 255.0);
    Ok(Layers { color, light: cells(&light, n, w)?, meta })
}

/// The strongest channel of each pixel of a light frame.
pub fn luma(light: &Array3<f64>) -> Array2<f64> {
    let (h, w, c) = light.dim();
    Array2::from_shape_fn((h, w), |(y, x)| (1..c).fold(light[[y, x, 0]], |m, k| if light[[y, x, k]] > m { light[[y, x, k]] } else { m }))
}

/// Recolour light by its strength along a hex ramp, weak to strong; the brightness stays the source light's.
pub fn tint<S: AsRef<str>>(light: &Array3<f64>, ramp: &[S]) -> Result<Array3<f64>, String> {
    if ramp.is_empty() {
        return Err("need at least one array to stack".into());
    }
    let tones: Vec<[f64; 3]> = ramp
        .iter()
        .map(|c| hexa(c.as_ref()).map(|v| [v[0] / 255.0, v[1] / 255.0, v[2] / 255.0]))
        .collect::<Result<_, _>>()?;
    let nt = tones.len() as i64;
    let v = luma(light);
    let (h, w) = v.dim();
    let mut out = Array3::zeros((h, w, 3));
    for y in 0..h {
        for x in 0..w {
            let t = v[[y, x]] * (nt - 1) as f64;
            let i = (t as i64).max(0).min(nt - 2);
            let f = t - i as f64;
            let (a, b) = (&tones[i.rem_euclid(nt) as usize], &tones[(i + 1).rem_euclid(nt) as usize]);
            let rgb = [0, 1, 2].map(|k| a[k] * (1.0 - f) + b[k] * f);
            let m = rgb[0].max(rgb[1]).max(rgb[2]);
            let s = v[[y, x]] / if 1e-6 > m { 1e-6 } else { m };
            for k in 0..3 {
                out[[y, x, k]] = rgb[k] * s;
            }
        }
    }
    Ok(out)
}

/// Light scaled by k and clipped to 0..1.
pub fn gain(light: &Array3<f64>, k: f64) -> Array3<f64> {
    light.mapv(|v| crate::np::clip(v * k, 0.0, 1.0))
}

/// Light only where mask is true.
pub fn keep(light: &Array3<f64>, mask: &Array2<bool>) -> Array3<f64> {
    keep_f(light, &mask.mapv(|m| if m { 1.0 } else { 0.0 }))
}

/// Light times a float mask.
pub fn keep_f(light: &Array3<f64>, mask: &Array2<f64>) -> Array3<f64> {
    let mut out = light.clone();
    for ((y, x, _), v) in out.indexed_iter_mut() {
        *v *= mask[[y, x]];
    }
    out
}

/// Options of `bands` (Python defaults: cuts (0.08, 0.2, 0.4), levels (0.3, 0.55, 0.8)).
#[derive(Clone, Debug)]
pub struct Bands {
    pub cuts: Vec<f64>,
    pub levels: Vec<f64>,
}

impl Default for Bands {
    fn default() -> Self {
        Bands { cuts: vec![0.08, 0.2, 0.4], levels: vec![0.3, 0.55, 0.8] }
    }
}

/// Light cut into hard steps; the outer band is checker dithered, as lt::bands does. The top step caps the light.
pub fn bands(light: &Array3<f64>, o: Bands) -> Array3<f64> {
    let v = luma(light);
    let mut out = Array3::zeros(light.dim());
    for ((y, x, k), o_v) in out.indexed_iter_mut() {
        let mut lv = 0.0;
        for (c, l) in o.cuts.iter().zip(&o.levels) {
            if v[[y, x]] >= *c {
                lv = *l;
            }
        }
        if v[[y, x]] >= o.cuts[0] && v[[y, x]] < o.cuts[1] && (x + y) % 2 == 1 {
            lv = 0.0;
        }
        let m = if 1e-6 > v[[y, x]] { 1e-6 } else { v[[y, x]] };
        *o_v = light[[y, x, k]] / m * lv;
    }
    out
}

/// Shade map of palette indices (-1 or out of range for empty) to RGBA; a None palette entry stays empty.
pub fn paint_opt<S: AsRef<str>>(shades: &Array2<i8>, palette: &[Option<S>]) -> Result<Array3<u8>, String> {
    let (h, w) = shades.dim();
    let mut out = Array3::zeros((h, w, 4));
    for (s, c) in palette.iter().enumerate() {
        if let Some(c) = c {
            let col = hexa(c.as_ref())?.map(|v| v as u8);
            for ((y, x), &sh) in shades.indexed_iter() {
                if sh as i64 == s as i64 {
                    for k in 0..4 {
                        out[[y, x, k]] = col[k];
                    }
                }
            }
        }
    }
    Ok(out)
}

/// Shade map (h, w) of palette indices, -1 or out of range for empty, to RGBA.
pub fn paint<S: AsRef<str>>(shades: &Array2<i8>, palette: &[S]) -> Result<Array3<u8>, String> {
    let p: Vec<Option<&str>> = palette.iter().map(|c| Some(c.as_ref())).collect();
    paint_opt(shades, &p)
}

/// One frame: colour (h, w, 4) plus light (h, w, 3) 0..1. bg is a hex for a flat ground, None keeps alpha.
pub fn composite(color: &Array3<u8>, light: &Array3<f64>, bg: Option<&str>) -> Result<Array3<u8>, String> {
    let (h, w, _) = color.dim();
    let bgc = bg.map(hexa).transpose()?;
    let mut out = Array3::zeros((h, w, 4));
    for y in 0..h {
        for x in 0..w {
            let a = color[[y, x, 3]] as f64 / 255.0;
            let lmax = (1..3).fold(light[[y, x, 0]], |m, k| if light[[y, x, k]] > m { light[[y, x, k]] } else { m });
            let mut px = [0.0; 4];
            if let Some(b) = bgc {
                for k in 0..3 {
                    let rgb = color[[y, x, k]] as f64 / 255.0 * a + b[k] / 255.0 * (1.0 - a);
                    px[k] = crate::np::clip(rgb + light[[y, x, k]], 0.0, 1.0);
                }
                px[3] = 1.0;
            } else {
                let alpha = crate::np::clip(if lmax > a { lmax } else { a }, 0.0, 1.0);
                for k in 0..3 {
                    let pre = color[[y, x, k]] as f64 / 255.0 * a + light[[y, x, k]];
                    px[k] = crate::np::clip(pre / if 1e-6 > alpha { 1e-6 } else { alpha }, 0.0, 1.0);
                }
                px[3] = alpha;
            }
            for k in 0..4 {
                out[[y, x, k]] = crate::np::round(px[k] * 255.0) as u8;
            }
        }
    }
    Ok(out)
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
        assert_eq!(num_text(24.0), "24");
        assert_eq!(num_text(12.5), "12.5");
        assert_eq!(secs(25, 24.0), "1.04");
    }
}
