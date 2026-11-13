//! fxlib.py: hue-shifted ramps, shade maps, strokes, periodic noise and impact frames.
//! A shade map is an `Array2<i8>` (h, w): -1 clear, 0..n-1 a palette colour. One defaulted argument is a trailing parameter.

use crate::np;
use crate::rng::default_rng;
use ndarray::{Array2, Array3};
use std::f64::consts::{PI, TAU};

/// Shadows lean toward blue.
pub const COOL_HUE: f64 = 230.0;
/// Highlights lean toward yellow.
pub const WARM_HUE: f64 = 55.0;
/// The white-hot flash of an impact peak.
pub const HOT: &str = "#fffaf0";

/// Python's max(a, b): a unless b is greater.
fn pmax(a: f64, b: f64) -> f64 {
    if b > a { b } else { a }
}

/// Python's min(a, b): a unless b is smaller.
fn pmin(a: f64, b: f64) -> f64 {
    if b < a { b } else { a }
}

/// "#rrggbb" to r, g, b (the # optional, extra characters ignored).
pub fn hexc(s: &str) -> Result<[u8; 3], String> {
    let t = s.trim_start_matches('#');
    let mut out = [0u8; 3];
    for (k, o) in out.iter_mut().enumerate() {
        let part = t.get(2 * k..(2 * k + 2).min(t.len())).unwrap_or("");
        *o = u8::from_str_radix(part, 16).map_err(|_| format!("invalid literal for int() with base 16: '{part}'"))?;
    }
    Ok(out)
}

/// r, g, b to "#rrggbb", each rounded half to even.
pub fn tohex(rgb: [f64; 3]) -> String {
    let c = |v: f64| np::round(v) as i64;
    format!("#{:02x}{:02x}{:02x}", c(rgb[0]), c(rgb[1]), c(rgb[2]))
}

/// Hue h (degrees) moved deg degrees along the short way to target.
fn toward(h: f64, target: f64, deg: f64) -> f64 {
    let d = np::pymod(target - h + 540.0, 360.0) - 180.0;
    np::pymod(h + pmin(d.abs(), deg).copysign(d), 360.0)
}

/// colorsys.rgb_to_hsv.
fn rgb_to_hsv(r: f64, g: f64, b: f64) -> (f64, f64, f64) {
    let maxc = pmax(pmax(r, g), b);
    let minc = pmin(pmin(r, g), b);
    let rangec = maxc - minc;
    let v = maxc;
    if minc == maxc {
        return (0.0, 0.0, v);
    }
    let s = rangec / maxc;
    let rc = (maxc - r) / rangec;
    let gc = (maxc - g) / rangec;
    let bc = (maxc - b) / rangec;
    let h = if r == maxc {
        bc - gc
    } else if g == maxc {
        2.0 + rc - bc
    } else {
        4.0 + gc - rc
    };
    (np::pymod(h / 6.0, 1.0), s, v)
}

/// colorsys.hsv_to_rgb.
fn hsv_to_rgb(h: f64, s: f64, v: f64) -> (f64, f64, f64) {
    if s == 0.0 {
        return (v, v, v);
    }
    let i = (h * 6.0) as i64;
    let f = (h * 6.0) - i as f64;
    let p = v * (1.0 - s);
    let q = v * (1.0 - s * f);
    let t = v * (1.0 - s * (1.0 - f));
    match np::pymod_i(i, 6) {
        0 => (v, t, p),
        1 => (q, v, p),
        2 => (p, v, t),
        3 => (p, q, v),
        4 => (t, p, v),
        _ => (v, p, q),
    }
}

fn hsv(rgb: [u8; 3]) -> (f64, f64, f64) {
    rgb_to_hsv(rgb[0] as f64 / 255.0, rgb[1] as f64 / 255.0, rgb[2] as f64 / 255.0)
}

fn rgb_of(h: f64, s: f64, v: f64) -> [f64; 3] {
    let (r, g, b) = hsv_to_rgb(h, pmax(0.0, pmin(1.0, s)), pmax(0.0, pmin(1.0, v)));
    [r * 255.0, g * 255.0, b * 255.0]
}

/// Four hue-shifted shades from one hex colour: shadow 22 degrees cooler, base, light 12 warmer, pale core 20 warmer.
pub fn ramp(base: &str) -> Result<Vec<String>, String> {
    let (h, s, v) = hsv(hexc(base)?);
    let hd = h * 360.0;
    let shadow = rgb_of(toward(hd, COOL_HUE, 22.0) / 360.0, s * 1.15 + 0.1, v * 0.62);
    let base = rgb_of(h, s * 1.05, v);
    let light = rgb_of(toward(hd, WARM_HUE, 12.0) / 360.0, s * 0.62, pmin(1.0, v * 1.12 + 0.06));
    let core = rgb_of(toward(hd, WARM_HUE, 20.0) / 360.0, s * 0.22, 1.0);
    Ok([shadow, base, light, core].into_iter().map(tohex).collect())
}

/// An empty shade map (h, w) filled with -1.
pub fn empty(w: usize, h: usize) -> Array2<i8> {
    Array2::from_elem((h, w), -1)
}

/// Pixel-centre coordinates relative to (cx, cy): arrays x, y of shape (h, w).
pub fn grid(w: usize, h: usize, cx: f64, cy: f64) -> (Array2<f64>, Array2<f64>) {
    let (ys, xs) = np::mgrid(h, w);
    (xs.mapv(|v| v + 0.5 - cx), ys.mapv(|v| v + 0.5 - cy))
}

/// grid over a cell (sheet px, pivot in sheet px) in world px at density sheet px per world px (Python default 1.0).
/// Shapes written in world px draw finer above 1; positions for put and line stay in sheet px.
pub fn wgrid(cw: usize, ch: usize, px: f64, py: f64, density: f64) -> (Array2<f64>, Array2<f64>) {
    let (x, y) = grid(cw, ch, px, py);
    (x.mapv(|v| v / density), y.mapv(|v| v / density))
}

/// put and line in the world px of grid and wgrid (relative to the pivot), so a draft writes every position in one frame.
/// `let pen = Pen::new(px, py, density); pen.put(&mut m, x, y, s); pen.line(&mut m, x0, y0, x1, y1, s, false)`.
#[derive(Clone, Copy, Debug)]
pub struct Pen {
    pub px: f64,
    pub py: f64,
    pub density: f64,
}

impl Pen {
    /// Pen(px, py, density); the Python density default is 1.0.
    pub fn new(px: f64, py: f64, density: f64) -> Pen {
        Pen { px, py, density }
    }

    /// World px to the sheet px that put and line take (the pixel whose centre the grid reads as x, y).
    pub fn sheet(&self, x: f64, y: f64) -> (f64, f64) {
        (x * self.density + self.px - 0.5, y * self.density + self.py - 0.5)
    }

    pub fn put(&self, m: &mut Array2<i8>, x: f64, y: f64, s: i8) {
        let (sx, sy) = self.sheet(x, y);
        put(m, sx, sy, s);
    }

    pub fn put_max(&self, m: &mut Array2<i8>, x: f64, y: f64, s: i8) {
        let (sx, sy) = self.sheet(x, y);
        put_max(m, sx, sy, s);
    }

    /// keep_max defaults to false in Python.
    pub fn line(&self, m: &mut Array2<i8>, x0: f64, y0: f64, x1: f64, y1: f64, s: i8, keep_max: bool) {
        let (ax, ay) = self.sheet(x0, y0);
        let (bx, by) = self.sheet(x1, y1);
        line(m, ax, ay, bx, by, s, keep_max);
    }
}

/// A tapered polyline over float grids x, y: (d, t, side) where d < 0 is inside, t runs 0 to 1 along it, side is the
/// signed offset (left of travel < 0). For claws, crescents, jaws, rays and cracks. w1 defaults to 0.0 in Python.
pub fn stroke(x: &Array2<f64>, y: &Array2<f64>, pts: &[[f64; 2]], w0: f64, w1: f64) -> (Array2<f64>, Array2<f64>, Array2<f64>) {
    let n = pts.len().saturating_sub(1);
    let seg: Vec<[f64; 2]> = (0..n).map(|i| [pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]]).collect();
    let ln: Vec<f64> = seg.iter().map(|s| np::hypot(s[0], s[1])).collect();
    let mut cum = vec![0.0];
    cum.extend(np::cumsum(&ln));
    let tot = pmax(cum[cum.len() - 1], 1e-9);
    let dim = x.dim();
    let mut best = Array2::from_elem(dim, f64::INFINITY);
    let mut tt = Array2::zeros(dim);
    let mut sd = Array2::zeros(dim);
    for i in 0..n {
        let [ax, ay] = pts[i];
        let [dx, dy] = seg[i];
        let li = pmax(ln[i], 1e-9);
        for ((idx, &xv), &yv) in x.indexed_iter().zip(y.iter()) {
            let u = np::clip(((xv - ax) * dx + (yv - ay) * dy) / (li * li), 0.0, 1.0);
            let t = (cum[i] + u * li) / tot;
            let d = np::hypot(xv - ax - u * dx, yv - ay - u * dy) - (w0 + (w1 - w0) * t) / 2.0;
            if d < best[idx] {
                best[idx] = d;
                tt[idx] = t;
                sd[idx] = ((xv - ax) * dy - (yv - ay) * dx) / li;
            }
        }
    }
    (best, tt, sd)
}

/// Draw shade map src over dst at offset (Python defaults 0, 0), clear pixels skipped, clipped.
pub fn stamp(dst: &mut Array2<i8>, src: &Array2<i8>, ox: i64, oy: i64) {
    let (h, w) = dst.dim();
    let (sh, sw) = src.dim();
    for j in 0..sh {
        let y = oy + j as i64;
        if !(0..h as i64).contains(&y) {
            continue;
        }
        for i in 0..sw {
            let x = ox + i as i64;
            if (0..w as i64).contains(&x) && src[[j, i]] >= 0 {
                dst[[y as usize, x as usize]] = src[[j, i]];
            }
        }
    }
}

/// Sets the pixel nearest (x, y) to shade s, off the map ignored.
pub fn put(m: &mut Array2<i8>, x: f64, y: f64, s: i8) {
    let (x, y) = (np::round(x) as i64, np::round(y) as i64);
    if 0 <= y && y < m.nrows() as i64 && 0 <= x && x < m.ncols() as i64 {
        m[[y as usize, x as usize]] = s;
    }
}

/// Like put, but keeps the brighter shade.
pub fn put_max(m: &mut Array2<i8>, x: f64, y: f64, s: i8) {
    let (x, y) = (np::round(x) as i64, np::round(y) as i64);
    if 0 <= y && y < m.nrows() as i64 && 0 <= x && x < m.ncols() as i64 {
        let p = &mut m[[y as usize, x as usize]];
        *p = (*p).max(s);
    }
}

/// A line of shade s from (x0, y0) to (x1, y1); keep_max (Python default false) draws with put_max.
pub fn line(m: &mut Array2<i8>, x0: f64, y0: f64, x1: f64, y1: f64, s: i8, keep_max: bool) {
    let n = pmax((x1 - x0).abs(), (y1 - y0).abs()) as i64 + 1;
    for k in 0..=n {
        let t = k as f64 / n.max(1) as f64;
        let (x, y) = (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t);
        if keep_max {
            put_max(m, x, y, s);
        } else {
            put(m, x, y, s);
        }
    }
}

/// Adds a 1 px shade-s rim (4-neighbour) round the drawn pixels (Python default s = 0).
pub fn outline(m: &Array2<i8>, s: i8) -> Array2<i8> {
    let (h, w) = m.dim();
    let mut out = m.clone();
    for y in 0..h {
        for x in 0..w {
            if m[[y, x]] >= 0 {
                continue;
            }
            let near = |yy: usize, xx: usize| m[[yy, xx]] >= 0;
            let grow = (y > 0 && near(y - 1, x)) || (y + 1 < h && near(y + 1, x)) || (x > 0 && near(y, x - 1)) || (x + 1 < w && near(y, x + 1));
            if grow {
                out[[y, x]] = s;
            }
        }
    }
    out
}

/// The random lattice of noise: (ny, nx) values of default_rng(seed).random((ny, nx)).
pub fn lattice(nx: usize, ny: usize, seed: u64) -> Array2<f64> {
    default_rng(seed).random_shape((ny, nx))
}

/// Smooth value noise in [0, 1] over x, y; cells is the lattice size in px; period (Python default None, 1024 square)
/// makes it tile so loops stay seamless.
pub fn noise(x: &Array2<f64>, y: &Array2<f64>, cells: f64, seed: u64, period: Option<(f64, f64)>) -> Array2<f64> {
    let (px, py) = period.unwrap_or((1024.0, 1024.0));
    let nx = (np::round(px / cells) as i64).max(1);
    let ny = (np::round(py / cells) as i64).max(1);
    let lat = lattice(nx as usize, ny as usize, seed);
    let at = |i: i64, j: i64| lat[[np::pymod_i(j, ny) as usize, np::pymod_i(i, nx) as usize]];
    Array2::from_shape_fn(x.dim(), |idx| {
        let (gx, gy) = (x[idx] / cells, y[idx] / cells);
        let (x0, y0) = (gx.floor() as i64, gy.floor() as i64);
        let (fx, fy) = (gx - x0 as f64, gy - y0 as f64);
        let (fx, fy) = (fx * fx * (3.0 - 2.0 * fx), fy * fy * (3.0 - 2.0 * fy));
        let a = at(x0, y0) * (1.0 - fx) + at(x0 + 1, y0) * fx;
        let b = at(x0, y0 + 1) * (1.0 - fx) + at(x0 + 1, y0 + 1) * fx;
        a * (1.0 - fy) + b * fy
    })
}

/// A checkerboard over x, y (Python default phase 0): true where floor(x) + floor(y) + phase is even.
pub fn checker(x: &Array2<f64>, y: &Array2<f64>, phase: i64) -> Array2<bool> {
    Array2::from_shape_fn(x.dim(), |i| np::pymod_i(x[i].floor() as i64 + y[i].floor() as i64 + phase, 2) == 0)
}

/// Elliptic distance over pixel grids x, y: 1.0 on the rim of (rx, ry), 0 at the centre.
pub fn ground_dist(x: &Array2<f64>, y: &Array2<f64>, rx: f64, ry: f64) -> Array2<f64> {
    let (mx, my) = (pmax(rx, 0.5), pmax(ry, 0.5));
    Array2::from_shape_fn(x.dim(), |i| {
        let (a, b) = (x[i] / mx, y[i] / my);
        (a * a + b * b).sqrt()
    })
}

/// Options of `ground_ring` (Python defaults: width 3, shades (1, 2, 3), dither true, rim 0; rim None skips it).
#[derive(Clone, Debug)]
pub struct GroundRing {
    pub width: f64,
    pub shades: Vec<i8>,
    pub dither: bool,
    pub rim: Option<i8>,
}

impl Default for GroundRing {
    fn default() -> Self {
        GroundRing { width: 3.0, shades: vec![1, 2, 3], dither: true, rim: Some(0) }
    }
}

/// Paints a solid ground ring into m: a band `width` px thick inside the ellipse (rx, ry) about (cx, cy), shaded
/// outer to inner by shades, a dithered inner fade and a shade-rim outline.
pub fn ground_ring(m: &mut Array2<i8>, cx: f64, cy: f64, rx: f64, ry: f64, o: GroundRing) {
    let (h, w) = m.dim();
    let (x, y) = grid(w, h, cx, cy);
    let d = ground_dist(&x, &y, rx, ry);
    let band = pmax(1.0, o.width) / pmax(rx, 1.0);
    let t = d.mapv(|d| (1.0 - d) / band); // 0 on the rim, 1 at the inner edge of the band
    let on = Array2::from_shape_fn((h, w), |i| d[i] <= 1.0 && t[i] <= 1.0);
    let mut out = m.clone();
    let k = o.shades.len() as f64;
    for (i, &sh) in o.shades.iter().enumerate() {
        for idx in ndarray::indices((h, w)) {
            if on[idx] && t[idx] >= i as f64 / k && t[idx] <= (i + 1) as f64 / k {
                out[idx] = sh;
            }
        }
    }
    if o.dither {
        let ck = checker(&x, &y, 0);
        for idx in ndarray::indices((h, w)) {
            if t[idx] > 1.0 && t[idx] <= 1.6 && ck[idx] && out[idx] < 0 {
                out[idx] = o.shades[0];
            }
        }
    }
    if let Some(rim) = o.rim {
        let solid = Array2::from_shape_fn((h, w), |i| if on[i] { out[i] } else { -1 });
        let ol = outline(&solid, rim);
        for idx in ndarray::indices((h, w)) {
            if ol[idx] == rim && !on[idx] && out[idx] < 0 && d[idx] > 1.0 {
                out[idx] = rim;
            }
        }
    }
    *m = out;
}

fn lum(c: &str) -> Result<f64, String> {
    let [r, g, b] = hexc(c)?;
    Ok(0.299 * r as f64 + 0.587 * g as f64 + 0.114 * b as f64)
}

/// Cell (h, w, 4) white-hot: each colour moves toward HOT and snaps to the nearest palette colour; the rim stays.
/// With core > 0 (Python default 0) only about core percent of the shape (its inner pixels) heats up.
pub fn heat<S: AsRef<str>>(cell: &Array3<u8>, palette: &[S], steps: i64, core: f64) -> Result<Array3<u8>, String> {
    let mut pal: Vec<&str> = vec![];
    for c in palette.iter().map(|s| s.as_ref()).chain(std::iter::once(HOT)) {
        if !pal.contains(&c) {
            pal.push(c);
        }
    }
    let rgb: Vec<[f64; 3]> = pal.iter().map(|c| hexc(c).map(|v| v.map(|x| x as f64))).collect::<Result<_, _>>()?;
    let mut rim = pal[0];
    let mut rim_l = lum(rim)?;
    for c in &pal[1..] {
        let l = lum(c)?;
        if l < rim_l {
            rim = c;
            rim_l = l;
        }
    }
    let k = if steps == 1 { 0.5 } else { 0.8 };
    let mut out = cell.clone();
    let (h, w, _) = cell.dim();
    let on = Array2::from_shape_fn((h, w), |(y, x)| cell[[y, x, 3]] > 0);
    let key = Array2::from_shape_fn((h, w), |(y, x)| (cell[[y, x, 0]] as i64) << 16 | (cell[[y, x, 1]] as i64) << 8 | cell[[y, x, 2]] as i64);
    let hot = hexc(HOT)?.map(|x| x as f64);
    let mut inner = on.clone();
    if core != 0.0 {
        // erode a pixel at a time until the core is a share of the shape
        let total = on.iter().filter(|&&v| v).count().max(1) as f64;
        let mut best = Array2::from_elem((h, w), false);
        let mut cur = on.clone();
        for _ in 0..40 {
            let p = np::pad(&cur, &[(1, 1), (1, 1)], np::Pad::Constant(false));
            cur = Array2::from_shape_fn((h, w), |(y, x)| cur[[y, x]] && p[[y, x + 1]] && p[[y + 2, x + 1]] && p[[y + 1, x]] && p[[y + 1, x + 2]]);
            if !cur.iter().any(|&v| v) {
                break;
            }
            best = cur.clone();
            if cur.iter().filter(|&&v| v).count() as f64 <= total * core / 100.0 {
                break;
            }
        }
        inner = best;
    }
    for (ci, c) in pal.iter().enumerate() {
        if *c == rim {
            continue;
        }
        let [r, g, b] = hexc(c)?;
        let want_key = (r as i64) << 16 | (g as i64) << 8 | b as i64;
        let sel: Vec<(usize, usize)> = ndarray::indices((h, w)).into_iter().filter(|&i| inner[i] && key[i] == want_key).collect();
        if sel.is_empty() {
            continue;
        }
        let me = rgb[ci];
        let want = [0, 1, 2].map(|j| me[j] * (1.0 - k) + hot[j] * k);
        let mut pick = 0;
        let mut pick_d = f64::INFINITY;
        for (n, row) in rgb.iter().enumerate() {
            let e = [0, 1, 2].map(|j| (row[j] - want[j]) * (row[j] - want[j]));
            let dist = (e[0] + e[1]) + e[2];
            if dist < pick_d {
                pick = n;
                pick_d = dist;
            }
        }
        for (y, x) in sel {
            for j in 0..3 {
                out[[y, x, j]] = rgb[pick][j] as u8;
            }
        }
    }
    Ok(out)
}

/// Cell shrunk toward pivot by k (nearest): the gathering frame before a blow lands.
pub fn contract(cell: &Array3<u8>, pivot: (f64, f64), k: f64) -> Array3<u8> {
    let (h, w, c) = cell.dim();
    let mut out = Array3::zeros((h, w, c));
    for y in 0..h {
        for x in 0..w {
            let rx = np::round(pivot.0 + (x as f64 + 0.5 - pivot.0) / k - 0.5) as i64;
            let ry = np::round(pivot.1 + (y as f64 + 0.5 - pivot.1) / k - 0.5) as i64;
            // off-cell sources stay clear, never smear the edge
            if rx >= 0 && rx < w as i64 && ry >= 0 && ry < h as i64 {
                for j in 0..c {
                    out[[y, x, j]] = cell[[ry as usize, rx as usize, j]];
                }
            }
        }
    }
    out
}

/// Source frame per slot of an n frame one-shot whose widest frame is peak: slot 0 the anticipation, slots 1..hold the
/// white-hot peak (Python default hold 2), the rest the dissolve eased out.
pub fn impact_order(n: i64, peak: i64, hold: i64) -> Vec<i64> {
    let m = n - 1 - hold;
    let mut src = vec![peak; (1 + hold).max(0) as usize];
    let mut tail: Vec<i64> = (peak + 1..n).collect();
    if tail.is_empty() {
        tail.push(peak);
    }
    let last = tail.len() as i64 - 1;
    for j in 0..m.max(0) {
        let u = j as f64 / (m - 1).max(1) as f64;
        let e = 1.0 - (1.0 - u) * (1.0 - u);
        let at = last.min(np::round(last as f64 * e) as i64);
        src.push(tail[at as usize]);
    }
    src
}

/// Radial tapered streaks round the shape of a white-hot impact cell: step 1 bursts them from the rim, step 2 flies
/// them further out and thinner. Drawn on clear pixels inside box (y0, y1, x0, x1); seed defaults to 0 in Python.
pub fn flash_rays<S: AsRef<str>>(cell: &Array3<u8>, palette: &[S], step: i64, box_: [usize; 4], seed: u64) -> Result<Array3<u8>, String> {
    let (h, w, _) = cell.dim();
    let on = Array2::from_shape_fn((h, w), |(y, x)| cell[[y, x, 3]] > 0);
    let n_on = on.iter().filter(|&&v| v).count();
    if n_on < 6 {
        return Ok(cell.clone());
    }
    let (mut sy, mut sx, mut cnt) = (0i64, 0i64, 0i64);
    let (mut ymin, mut ymax, mut xmin, mut xmax) = (usize::MAX, 0, usize::MAX, 0);
    for ((y, x), &v) in on.indexed_iter() {
        if v {
            sy += y as i64;
            sx += x as i64;
            cnt += 1;
            ymin = ymin.min(y);
            ymax = ymax.max(y);
            xmin = xmin.min(x);
            xmax = xmax.max(x);
        }
    }
    let cy = sy as f64 / cnt as f64 + 0.5;
    let cx = sx as f64 / cnt as f64 + 0.5;
    let flat = if ((ymax - ymin + 1) as f64) < 0.6 * (xmax - xmin + 1) as f64 { 0.5 } else { 1.0 };
    let rr = (n_on as f64 / PI).sqrt();
    let n: usize = if rr < 12.0 { 8 } else { 12 };
    let r0 = rr * if step == 1 { 1.0 } else { 1.35 };
    let span = pmax(3.0, 0.7 * rr);
    let width = pmax(1.2, 0.14 * rr) * if step == 1 { 1.0 } else { 0.7 };
    let hot = hexc(HOT)?;
    let mut best: Option<(&str, f64)> = None;
    for c in palette.iter().map(|s| s.as_ref()).filter(|c| *c != HOT) {
        let l = lum(c)?;
        if best.map_or(true, |(_, bl)| l > bl) {
            best = Some((c, l));
        }
    }
    let light = hexc(best.ok_or("max() arg is an empty sequence")?.0)?;
    let [y0, y1, x0, x1] = box_;
    let mut out = cell.clone();
    let mut rng = default_rng(seed);
    let turn = rng.random() * TAU;
    let polar = Array2::from_shape_fn((h, w), |(y, x)| {
        let dx = x as f64 + 0.5 - cx;
        let dy = (y as f64 + 0.5 - cy) / flat;
        (np::hypot(dx, dy), dy.atan2(dx))
    });
    for j in 0..n {
        let a = turn + TAU * j as f64 / n as f64 + 0.3 * (rng.random() - 0.5);
        let ll = r0 + span * (if j % 2 == 0 { 1.0 } else { 0.55 }) * (0.85 + 0.3 * rng.random());
        for y in 0..h {
            for x in 0..w {
                let (r, th) = polar[[y, x]];
                let da = np::pymod(th - a + PI, TAU) - PI;
                let t = (r - r0) / pmax(ll - r0, 1e-6);
                let ray = t >= 0.0 && t <= 1.0 && (r * da.sin()).abs() <= 0.5 * width * (1.0 - t) + 0.35 && da.abs() < PI / 2.0;
                let inbox = (y0..=y1).contains(&y) && (x0..=x1).contains(&x);
                if ray && !on[[y, x]] && inbox {
                    let c = if t < 0.4 && step == 1 { hot } else { light };
                    for (k, v) in c.iter().enumerate() {
                        out[[y, x, k]] = *v;
                    }
                    out[[y, x, 3]] = 255;
                }
            }
        }
    }
    Ok(out)
}
