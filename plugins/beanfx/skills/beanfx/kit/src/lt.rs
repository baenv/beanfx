//! light.py: the additive glow pass of an effect, drawn on its own sheet `<name>_light`.
//! Light is an `Array2<f64>` buffer over a `Canvas`; one defaulted argument is a trailing parameter, several make a struct.

use crate::fl::checker;
use crate::np;
use ndarray::Array2;
use std::f64::consts::TAU;

/// Outer, middle and inner band of the hard steps.
pub const LEVELS: [f64; 3] = [0.3, 0.55, 0.8];
/// Summed light where the outer, middle and inner band begin.
pub const CUTS: [f64; 3] = [0.08, 0.2, 0.4];

/// A canvas with world px grids x, y (the `c` of the Python calls, from `fl::wgrid`).
#[derive(Clone, Debug)]
pub struct Canvas {
    pub x: Array2<f64>,
    pub y: Array2<f64>,
}

/// A glow level: core k, pool radius and k as factors of the core, target mean of lit pixels.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct GlowLevel {
    pub core: (f64, f64),
    pub pool_r: f64,
    pub pool_k: f64,
    pub mean: (f64, f64),
}

/// GLOW["subtle" | "medium" | "strong"].
pub fn glow_level(name: &str) -> Option<GlowLevel> {
    match name {
        "subtle" => Some(GlowLevel { core: (0.25, 0.5), pool_r: 2.0, pool_k: 0.2, mean: (0.04, 0.07) }),
        "medium" => Some(GlowLevel { core: (0.3, 0.7), pool_r: 2.5, pool_k: 0.4, mean: (0.06, 0.10) }),
        "strong" => Some(GlowLevel { core: (0.3, 0.7), pool_r: 3.0, pool_k: 0.45, mean: (0.08, 0.14) }),
        _ => None,
    }
}

/// An empty light buffer shaped like the canvas.
pub fn buffer(c: &Canvas) -> Array2<f64> {
    Array2::zeros(c.x.dim())
}

fn fall(d: f64, k: f64) -> f64 {
    if d < 1.0 {
        let m = 1.0 - d.min(1.0);
        m * m * k
    } else {
        0.0
    }
}

/// A round light, k at the centre (Python default k = 0.4).
pub fn glow(l: &mut Array2<f64>, c: &Canvas, x: f64, y: f64, r: f64, k: f64) {
    for (idx, v) in l.indexed_iter_mut() {
        *v += fall(np::hypot(c.x[idx] - x, c.y[idx] - y) / r, k);
    }
}

/// Light round a segment: beams, bolts, trails (Python default k = 0.4).
pub fn glow_line(l: &mut Array2<f64>, c: &Canvas, p0: (f64, f64), p1: (f64, f64), r: f64, k: f64) {
    let ((ax, ay), (bx, by)) = (p0, p1);
    let (ex, ey) = (bx - ax, by - ay);
    let den = if ex * ex + ey * ey != 0.0 { ex * ex + ey * ey } else { 1e-9 };
    for (idx, v) in l.indexed_iter_mut() {
        let (cx, cy) = (c.x[idx], c.y[idx]);
        let h = np::clip(((cx - ax) * ex + (cy - ay) * ey) / den, 0.0, 1.0);
        *v += fall(np::hypot(cx - ax - ex * h, cy - ay - ey * h) / r, k);
    }
}

/// Light hugging a ring of radius big_r: shock waves, ground seals (Python defaults k = 0.4, flat = 1.0).
pub fn glow_ring(l: &mut Array2<f64>, c: &Canvas, x: f64, y: f64, big_r: f64, r: f64, k: f64, flat: f64) {
    for (idx, v) in l.indexed_iter_mut() {
        *v += fall((np::hypot(c.x[idx] - x, (c.y[idx] - y) / flat) - big_r).abs() / r, k);
    }
}

/// BAYER4 as numpy builds it: the 4x4 ordered-dither matrix over 16.
pub fn bayer4() -> Array2<f64> {
    const M: [[i64; 4]; 4] = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]];
    Array2::from_shape_fn((4, 4), |(y, x)| M[y][x] as f64 / 16.0)
}

/// Options of `steps` (Python defaults: levels 4, floor 0.06, phase (0, 0)).
#[derive(Clone, Copy, Debug)]
pub struct Steps {
    pub levels: f64,
    pub floor: f64,
    pub phase: (i64, i64),
}

impl Default for Steps {
    fn default() -> Self {
        Steps { levels: 4.0, floor: 0.06, phase: (0, 0) }
    }
}

/// The light cut into `levels` flat steps of 1/levels, the pixel-art light; the outer step fades out by a 4x4 ordered
/// dither, below `floor` it is 0. phase shifts the dither grid (x, y).
pub fn steps(l: &Array2<f64>, o: Steps) -> Array2<f64> {
    let t4 = bayer4();
    let step = 1.0 / o.levels;
    Array2::from_shape_fn(l.dim(), |(y, x)| {
        let v = np::clip(l[[y, x]], 0.0, 1.0);
        let t = t4[[np::pymod_i(y as i64 + o.phase.1, 4) as usize, np::pymod_i(x as i64 + o.phase.0, 4) as usize]];
        let mut out = (v * o.levels + 1e-9).floor() * step;
        let outer = v >= o.floor && v < step;
        let fade = (v - o.floor) / (step - o.floor).max(1e-6);
        if outer && fade > t {
            out = step;
        }
        if v < o.floor { 0.0 } else { out }
    })
}

/// The summed light as a shade map in three hard bands; the outer band is a checker (phase default 0).
pub fn bands(l: &Array2<f64>, phase: i64) -> Array2<i8> {
    let (h, w) = l.dim();
    let (ys, xs) = np::mgrid(h, w);
    let ck = checker(&xs, &ys, phase);
    Array2::from_shape_fn((h, w), |i| {
        let mut m = -1;
        if l[i] >= CUTS[0] && ck[i] {
            m = 0;
        }
        if l[i] >= CUTS[1] {
            m = 1;
        }
        if l[i] >= CUTS[2] {
            m = 2;
        }
        m
    })
}

/// The light sheet's three colours: hue scaled by each band level (added, so darker means fainter).
pub fn palette(hue: &str) -> Result<Vec<String>, String> {
    let ch = |i: usize| {
        let part = hue.get(i..i + 2).unwrap_or("");
        u8::from_str_radix(part, 16).map(|v| v as f64).map_err(|_| format!("invalid literal for int() with base 16: '{part}'"))
    };
    let (r, g, b) = (ch(1)?, ch(3)?, ch(5)?);
    Ok(LEVELS.iter().map(|&v| format!("#{:02x}{:02x}{:02x}", np::round(r * v) as i64, np::round(g * v) as i64, np::round(b * v) as i64)).collect())
}

/// Lights that flare and die: each starts at k and radius r, dims as (life left / life) squared, shrinks to 0.55 r.
#[derive(Clone, Debug, Default)]
pub struct Flashes {
    /// Each light as x, y, r, k, frames left, life.
    pub list: Vec<[f64; 6]>,
}

impl Flashes {
    pub fn new() -> Flashes {
        Flashes::default()
    }

    /// Adds a light living `life` frames (Python default 6).
    pub fn add(&mut self, x: f64, y: f64, r: f64, k: f64, life: f64) {
        self.list.push([x, y, r, k, life, life]);
    }

    pub fn draw(&self, l: &mut Array2<f64>, c: &Canvas) {
        for &[x, y, r, k, left, life] in &self.list {
            flash(l, c, x, y, r, k, left / life);
        }
    }

    pub fn step(&mut self) {
        for f in &mut self.list {
            f[4] -= 1.0;
        }
        self.list.retain(|f| f[4] > 0.0);
    }
}

fn flash(l: &mut Array2<f64>, c: &Canvas, x: f64, y: f64, r: f64, k: f64, u: f64) {
    glow(l, c, x, y, r * (0.55 + 0.45 * u), k * u * u);
}

/// A Flashes light born at frame f0, drawn at frame f with no state (life defaults to 6).
pub fn flash_at(l: &mut Array2<f64>, c: &Canvas, f: f64, f0: f64, x: f64, y: f64, r: f64, k: f64, life: f64) {
    let age = f - f0;
    if 0.0 <= age && age < life {
        flash(l, c, x, y, r, k, (life - age) / life);
    }
}

fn hash01(n: &[i64]) -> f64 {
    let mut h: u64 = 0x9E3779B97F4A7C15;
    for &v in n {
        h = (h ^ (v as u64 & 0xFFFFFFFF)).wrapping_mul(0xBF58476D1CE4E5B9);
        h ^= h >> 31;
    }
    (h & 0xFFFFFF) as f64 / 0xFFFFFF as f64
}

/// Options of `flicker` (Python defaults: seed 0, rate 1.0).
#[derive(Clone, Copy, Debug)]
pub struct Flicker {
    pub seed: i64,
    pub rate: f64,
}

impl Default for Flicker {
    fn default() -> Self {
        Flicker { seed: 0, rate: 1.0 }
    }
}

/// Twinkle 0..1 for spark i at frame f: a fast wave with its own phase and speed plus a seeded jitter. rate 0 holds still.
pub fn flicker(i: i64, f: f64, o: Flicker) -> f64 {
    let ph = TAU * hash01(&[o.seed, i, 1]);
    let sp = 1.2 + 1.8 * hash01(&[o.seed, i, 2]);
    let v = 0.5 + 0.5 * (ph + f * sp * o.rate).sin();
    let jitter = 0.4 * o.rate * hash01(&[o.seed, i, f as i64, 3]);
    (v * (1.0 - 0.4 * o.rate) + jitter).max(0.0).min(1.0)
}
