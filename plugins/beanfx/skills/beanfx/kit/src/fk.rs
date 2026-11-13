//! fxkit.py: drawing helpers for blows, flames, bolts and smoke. Every helper works on world px grids `x`, `y`
//! (`fl::wgrid`, `Array2<f64>`) and paints shade indices into a shade map `m` (`Array2<i8>`, -1 clear) of the cell.
//! Shades are `i8` values; sequences of them are arrays or slices in the order the Python docstrings give.
//! Seeds are `f64` (Python accepts ints and floats). Keyword arguments are options structs with `Default`.

use std::f64::consts::PI;

use crate::fl;
use crate::np::{self, math_hypot};
use ndarray::{Array2, Zip};

pub const TAU: f64 = std::f64::consts::TAU;
/// The one light, from the top left: (-sqrt(0.5), -sqrt(0.5)).
pub fn light() -> (f64, f64) {
    (-(0.5f64).sqrt(), -(0.5f64).sqrt())
}

type Pt = (f64, f64);
type Grid = Array2<f64>;
type Shade = Array2<i8>;

fn stroke(x: &Grid, y: &Grid, pts: &[Pt], w0: f64, w1: f64) -> (Grid, Grid, Grid) {
    let p: Vec<[f64; 2]> = pts.iter().map(|&(a, b)| [a, b]).collect();
    fl::stroke(x, y, &p, w0, w1)
}

fn outline(m: &Shade, s: i8) -> Shade {
    fl::outline(m, s)
}

/// Paints shade `s` where `f(pixel)` holds (`m[mask] = s`).
fn set(m: &mut Shade, s: i8, f: impl Fn((usize, usize)) -> bool) {
    for (p, v) in m.indexed_iter_mut() {
        if f(p) {
            *v = s;
        }
    }
}

fn pmax(a: f64, b: f64) -> f64 {
    if b > a { b } else { a }
}
fn pmin(a: f64, b: f64) -> f64 {
    if b < a { b } else { a }
}
fn hyp(a: &Grid, b: &Grid) -> Grid {
    np::hypot_a(a, b)
}
fn sub(a: &Grid, c: f64) -> Grid {
    a.mapv(|v| v - c)
}

/// Hash of `i` and `salt` into [0, 1): `fract(sin(i * 12.9898 + salt * 78.233) * 43758.5453)`.
pub fn hsh(i: f64, salt: f64) -> f64 {
    np::pymod((i * 12.9898 + salt * 78.233).sin() * 43758.5453, 1.0)
}

/// u along angle `a`, v across it (left of travel < 0).
pub fn rot(x: &Grid, y: &Grid, a: f64) -> (Grid, Grid) {
    let (c, s) = (a.cos(), a.sin());
    (
        Zip::from(x).and(y).map_collect(|&x, &y| x * c + y * s),
        Zip::from(x).and(y).map_collect(|&x, &y| -x * s + y * c),
    )
}

/// The 4x4 Bayer matrix tiled over the shape of `m`, values (n + 0.5) / 16.
pub fn bayer(m: &Shade) -> Grid {
    bayer_hw(m.nrows(), m.ncols())
}

fn bayer_hw(h: usize, w: usize) -> Grid {
    const B: [[f64; 4]; 4] = [[0.0, 8.0, 2.0, 10.0], [12.0, 4.0, 14.0, 6.0], [3.0, 11.0, 1.0, 9.0], [15.0, 7.0, 13.0, 5.0]];
    Array2::from_shape_fn((h, w), |(j, i)| (B[j % 4][i % 4] + 0.5) / 16.0)
}

/// Ordered-dither dissolve of shade map `m`: 0 keeps all, 1 clears all.
pub fn fade(m: &Shade, amount: f64) -> Shade {
    if amount <= 0.0 {
        return m.clone();
    }
    let b = bayer(m);
    let mut out = m.clone();
    set(&mut out, -1, |p| b[p] < amount);
    out
}

/// Draws `src` over `dst` where `src` is set (>= 0).
pub fn blit(dst: &mut Shade, src: &Shade) {
    Zip::from(dst).and(src).for_each(|d, &s| {
        if s >= 0 {
            *d = s;
        }
    });
}

/// `m` with a 1 px rim of shade `s` round its pixels.
pub fn rim(m: &Shade, s: i8) -> Shade {
    outline(m, s)
}

/// `lumpy` keyword arguments.
#[derive(Clone, Copy)]
pub struct Lumpy {
    pub amp: f64,
    pub seed: f64,
    pub ph: f64,
    pub lobes: i64,
}

impl Default for Lumpy {
    fn default() -> Self {
        Lumpy { amp: 0.16, seed: 0.0, ph: 0.0, lobes: 5 }
    }
}

/// Normalised distance to a lobed round rim (< 1 inside); the lobes turn with `ph`.
pub fn lumpy(x: &Grid, y: &Grid, cx: f64, cy: f64, r: f64, o: Lumpy) -> Grid {
    let (dx, dy) = (sub(x, cx), sub(y, cy));
    let l = o.lobes as f64;
    let l3 = (o.lobes + 3) as f64;
    Zip::from(&dx).and(&dy).map_collect(|&dx, &dy| {
        let a = dy.atan2(dx);
        let k = 1.0 + o.amp * (0.6 * (l * a + o.seed + o.ph).sin() + 0.4 * (l3 * a - 1.7 * o.seed - 1.3 * o.ph).sin());
        np::hypot(dx, dy) / pmax(r * k, 0.01)
    })
}

/// Paints d < 1 into `m` as bands: `shades[i]` where d < `cuts[i]` (cuts rising, the last 1.0), the hottest first.
/// Returns the inside mask (d < 1).
pub fn heat_bands(m: &mut Shade, d: &Grid, shades: &[i8], cuts: &[f64]) -> Array2<bool> {
    let inside = d.mapv(|v| v < 1.0);
    let mut pairs: Vec<(i8, f64)> = shades.iter().copied().zip(cuts.iter().copied()).collect();
    pairs.sort_by(|a, b| (-a.1).partial_cmp(&(-b.1)).unwrap());
    for (s, c) in pairs {
        set(m, s, |p| inside[p] && d[p] < c);
    }
    inside
}

/// The offset of a highlight centre toward the light, `k` of radius `r` (Python default k = 0.35).
pub fn lit_offset(r: f64, k: f64) -> (f64, f64) {
    let l = light();
    (l.0 * r * k, l.1 * r * k)
}

/// `ball` keyword arguments.
#[derive(Clone, Copy, Default)]
pub struct Ball {
    pub amp: f64,
    pub ph: f64,
    pub seed: f64,
}

/// A lit sphere (or lumpy one with `amp`): shades (deep, body, light, core) from the far side to the highlight.
pub fn ball(m: &mut Shade, x: &Grid, y: &Grid, cx: f64, cy: f64, r: f64, shades: &[i8], o: Ball) -> Array2<bool> {
    let (ox, oy) = lit_offset(r, 0.35);
    let d = if o.amp != 0.0 {
        lumpy(x, y, cx, cy, r, Lumpy { amp: o.amp, seed: o.seed, ph: o.ph, lobes: 5 })
    } else {
        hyp(&sub(x, cx), &sub(y, cy)).mapv(|v| v / r)
    };
    let on = d.mapv(|v| v < 1.0);
    let h = hyp(&sub(&sub(x, cx), ox), &sub(&sub(y, cy), oy)).mapv(|v| v / r);
    set(m, shades[0], |p| on[p]);
    set(m, shades[1], |p| on[p] && h[p] < 1.05);
    set(m, shades[2], |p| on[p] && h[p] < 0.62);
    set(m, shades[3], |p| on[p] && h[p] < 0.28);
    on
}

/// `trail_puffs` keyword arguments; `tones` None is [(3, 2), (2, 1), (1, 0), (0, 0)].
#[derive(Clone)]
pub struct TrailPuffs {
    pub n: i64,
    pub gap: f64,
    pub shrink: f64,
    pub tones: Option<Vec<(i8, i8)>>,
    pub wob: f64,
    pub amp: f64,
    pub seed: f64,
}

impl Default for TrailPuffs {
    fn default() -> Self {
        TrailPuffs { n: 4, gap: 1.05, shrink: 0.78, tones: None, wob: 0.6, amp: 0.2, seed: 0.0 }
    }
}

/// Puffs behind a head at `head_u` along u: puff i sits at s = i + phase (phase 0..1 loops seamlessly), r0 * shrink^s
/// across, tones[min(int(s), len - 1)] its (core, rim) shades so it cools, broken into dots as it ages.
pub fn trail_puffs(m: &mut Shade, x: &Grid, y: &Grid, u: &Grid, v: &Grid, head_u: f64, r0: f64, phase: f64, o: TrailPuffs) {
    let _ = (x, y);
    let tones = o.tones.clone().unwrap_or_else(|| vec![(3, 2), (2, 1), (1, 0), (0, 0)]);
    let nf = o.n as f64;
    let bm = bayer(m);
    for i in 0..=o.n {
        let s = i as f64 + phase;
        if s <= 0.15 || s >= nf {
            continue;
        }
        let r = r0 * o.shrink.powf(s);
        let cu = head_u - r0 * o.gap * s - 0.4 * s * s;
        let cv = o.wob * (1.9 * s + o.seed).sin() * pmin(1.0, s);
        let d = lumpy(u, v, cu, cv, r, Lumpy { amp: o.amp, seed: o.seed + i as f64, ph: phase * TAU, lobes: 5 });
        let (core, edge) = tones[(s as usize).min(tones.len() - 1)];
        let on = d.mapv(|q| q < 1.0);
        let mut piece = Shade::from_elem(m.raw_dim(), -1);
        set(&mut piece, edge, |p| on[p]);
        set(&mut piece, core, |p| on[p] && d[p] < 0.6);
        let brk = pmax(0.0, (s - 1.2) / (nf - 1.2));
        set(&mut piece, -1, |p| on[p] && d[p] > 1.0 - 0.7 * brk && bm[p] < 0.5 + 0.5 * brk);
        set(&mut piece, -1, |p| on[p] && bm[p] < 0.55 * brk * brk);
        blit(m, &piece);
    }
}

/// `streaks` keyword arguments.
#[derive(Clone, Copy)]
pub struct Streaks {
    pub seed: f64,
    pub flat: f64,
    pub short: f64,
    pub spin: f64,
    pub hot: f64,
}

impl Default for Streaks {
    fn default() -> Self {
        Streaks { seed: 0.0, flat: 1.0, short: 0.55, spin: 0.0, hot: 0.35 }
    }
}

/// `n` radial tapered streaks from radius `r0` out to `r1` (every other one short of it), `w` wide at the root:
/// shades (outer, mid, hot) along the length, the root hottest. flat < 1 lies them on the ground.
pub fn streaks(m: &mut Shade, x: &Grid, y: &Grid, cx: f64, cy: f64, n: i64, r0: f64, r1: f64, w: f64, shades: &[i8], o: Streaks) -> Array2<bool> {
    let mut best = Grid::from_elem(m.raw_dim(), f64::INFINITY);
    let mut tt = Grid::zeros(m.raw_dim());
    let xs = sub(x, cx);
    let ys = sub(y, cy).mapv(|v| v / pmax(o.flat, 0.05));
    for j in 0..n {
        let a = TAU * j as f64 / n as f64 + o.spin + 0.35 * (hsh(j as f64, o.seed) - 0.5);
        let mut l = if j % 2 == 0 { r1 } else { r0 + (r1 - r0) * o.short };
        l *= 0.88 + 0.24 * hsh(j as f64, o.seed + 3.0);
        let (c, s) = (a.cos(), a.sin());
        let (d, t, _) = stroke(&xs, &ys, &[(r0 * c, r0 * s), (l * c, l * s)], w, 0.0);
        Zip::from(&mut best).and(&mut tt).and(&d).and(&t).for_each(|b, tt, &d, &t| {
            if d < *b {
                *b = d;
                *tt = t;
            }
        });
    }
    let on = best.mapv(|v| v < 0.0);
    set(m, shades[0], |p| on[p]);
    set(m, shades[1], |p| on[p] && tt[p] < 0.7);
    set(m, shades[2], |p| on[p] && tt[p] < o.hot);
    on
}

/// `ring` keyword arguments.
#[derive(Clone, Copy)]
pub struct Ring {
    pub flat: f64,
}

impl Default for Ring {
    fn default() -> Self {
        Ring { flat: 1.0 }
    }
}

/// A ring of radius `r` and width `w` as a mask (q <= r and q > r - w), squashed by `flat` in y.
pub fn ring(x: &Grid, y: &Grid, cx: f64, cy: f64, r: f64, w: f64, o: Ring) -> Array2<bool> {
    let q = hyp(&sub(x, cx), &sub(y, cy).mapv(|v| v / o.flat));
    q.mapv(|q| q <= r && q > r - w)
}

/// `puff` keyword arguments.
#[derive(Clone, Copy, Default)]
pub struct Puff {
    pub brk: f64,
    pub seed: f64,
    pub ph: f64,
}

/// A round puff in 3 tones (shadow, mid, light) lit from the top left, its edge breaking into dots by `brk` (0..1).
pub fn puff(m: &mut Shade, x: &Grid, y: &Grid, cx: f64, cy: f64, r: f64, tones: &[i8], o: Puff) -> Array2<bool> {
    let d = lumpy(x, y, cx, cy, r, Lumpy { amp: 0.14, seed: o.seed, ph: o.ph, lobes: 4 });
    let on = d.mapv(|v| v < 1.0);
    let (ox, oy) = lit_offset(r, 0.38);
    let h = hyp(&sub(&sub(x, cx), ox), &sub(&sub(y, cy), oy)).mapv(|v| v / r);
    let mut piece = Shade::from_elem(m.raw_dim(), -1);
    set(&mut piece, tones[0], |p| on[p]);
    set(&mut piece, tones[1], |p| on[p] && h[p] < 0.95);
    set(&mut piece, tones[2], |p| on[p] && h[p] < 0.5);
    if o.brk > 0.0 {
        let b = bayer(m);
        set(&mut piece, -1, |p| on[p] && d[p] > 1.0 - 0.8 * o.brk && b[p] < 0.45 + 0.55 * o.brk);
        set(&mut piece, -1, |p| on[p] && b[p] < 0.6 * o.brk * o.brk);
    }
    blit(m, &piece);
    on
}

/// `polygon` keyword arguments.
#[derive(Clone, Copy)]
pub struct Polygon {
    pub ph: f64,
    pub jit: f64,
}

impl Default for Polygon {
    fn default() -> Self {
        Polygon { ph: 0.0, jit: 0.22 }
    }
}

/// A jittered `n`-gon of radius `r` round (`cx`, `cy`).
pub fn polygon(cx: f64, cy: f64, r: f64, n: i64, seed: f64, o: Polygon) -> Vec<Pt> {
    (0..n)
        .map(|i| {
            let a = o.ph + TAU * i as f64 / n as f64 + 0.3 * (hsh(i as f64, seed) - 0.5);
            let rr = r * (1.0 - o.jit + 2.0 * o.jit * hsh(i as f64, seed + 5.0));
            (cx + rr * a.cos(), cy + rr * a.sin())
        })
        .collect()
}

/// `facets` keyword arguments.
#[derive(Clone, Copy)]
pub struct Facets {
    pub top: bool,
}

impl Default for Facets {
    fn default() -> Self {
        Facets { top: true }
    }
}

/// A convex faceted solid inside polygon `pts`: each face (centre to edge) shaded by how it faces the light, shades
/// (shadow, mid, lit, highlight); `top` adds a flat lit top face and a hard highlight on the lit rim.
pub fn facets(m: &mut Shade, x: &Grid, y: &Grid, pts: &[Pt], shades: &[i8], o: Facets) -> Array2<bool> {
    let n = pts.len();
    let (mut sx, mut sy) = (0.0, 0.0);
    for p in pts {
        sx += p.0;
        sy += p.1;
    }
    let (cx, cy) = (sx / n as f64, sy / n as f64);
    let cross = |i: usize, x: f64, y: f64| {
        let ((ax, ay), (bx, by)) = (pts[i], pts[(i + 1) % n]);
        (bx - ax) * (y - ay) - (by - ay) * (x - ax)
    };
    let mut inside = Array2::from_shape_fn(m.raw_dim(), |p| (0..n).all(|i| cross(i, x[p], y[p]) >= 0.0));
    if !inside.iter().any(|&b| b) {
        inside = Array2::from_shape_fn(m.raw_dim(), |p| (0..n).all(|i| cross(i, x[p], y[p]) <= 0.0));
    }
    let ang = Zip::from(y).and(x).map_collect(|&y, &x| (y - cy).atan2(x - cx));
    let l = light();
    for i in 0..n {
        let ((ax, ay), (bx, by)) = (pts[i], pts[(i + 1) % n]);
        let (a0, a1) = ((ay - cy).atan2(ax - cx), (by - cy).atan2(bx - cx));
        let span = np::pymod(a1 - a0, TAU);
        let sel = Array2::from_shape_fn(m.raw_dim(), |p| inside[p] && np::pymod(ang[p] - a0, TAU) <= span);
        let mid = a0 + span / 2.0;
        let lit = mid.cos() * l.0 + mid.sin() * l.1;
        let s = if lit > 0.45 { shades[2] } else if lit > -0.35 { shades[1] } else { shades[0] };
        set(m, s, |p| sel[p]);
        if o.top && lit > 0.45 {
            let (ex, ey) = (bx - ax, by - ay);
            let el = pmax(math_hypot(ex, ey), 1e-6);
            set(m, shades[3], |p| sel[p] && (((x[p] - ax) * ey - (y[p] - ay) * ex) / el).abs() < 0.55);
        }
    }
    if o.top {
        let mut r = f64::NEG_INFINITY;
        for p in pts {
            r = pmax(r, math_hypot(p.0 - cx, p.1 - cy));
        }
        let (ox, oy) = lit_offset(r, 0.2);
        set(m, shades[2], |p| inside[p] && np::hypot(x[p] - cx - ox, y[p] - cy - oy) < r * 0.34);
    }
    inside
}

/// A 4-point star at sheet px (`px`, `py`): arms `size` px long, the centre `hot`, the arms `mid`.
pub fn twinkle(m: &mut Shade, px: f64, py: f64, size: i64, hot: i8, mid: i8) {
    let (h, w) = m.dim();
    for k in -size..=size {
        let kf = k as f64;
        for (xx, yy) in [(px + kf, py), (px, py + kf)] {
            let (xi, yi) = (np::round(xx) as i64, np::round(yy) as i64);
            if 0 <= xi && xi < w as i64 && 0 <= yi && yi < h as i64 {
                m[[yi as usize, xi as usize]] = if k.abs() <= np::floordiv_i(size, 2) { hot } else { mid };
            }
        }
    }
}

/// Sheet px (i, j) of world point (`wx`, `wy`) on grids `x`, `y` (the nearest cell centre).
pub fn to_px(m: &Shade, x: &Grid, y: &Grid, wx: f64, wy: f64) -> (usize, usize) {
    let _ = m;
    let first_min = |it: &mut dyn Iterator<Item = f64>| {
        let (mut bi, mut bv) = (0, f64::INFINITY);
        for (i, v) in it.enumerate() {
            if v < bv {
                bi = i;
                bv = v;
            }
        }
        bi
    };
    let j = first_min(&mut y.column(0).iter().map(|v| (v - wy).abs()));
    let i = first_min(&mut x.row(0).iter().map(|v| (v - wx).abs()));
    (i, j)
}

// ----- claws -----

/// `claw_tracks` keyword arguments.
#[derive(Clone, Copy)]
pub struct ClawTracks {
    pub n: i64,
    pub gap: f64,
    pub bow: f64,
    pub tilt: f64,
    pub u0: f64,
    pub sgn: f64,
    pub steps: usize,
    pub spread: f64,
}

impl Default for ClawTracks {
    fn default() -> Self {
        ClawTracks { n: 3, gap: 3.4, bow: 3.0, tilt: 0.3, u0: 0.0, sgn: 1.0, steps: 14, spread: 0.0 }
    }
}

/// `n` parallel claw tracks across the aim as local (u ahead, v right) polylines in world px: each runs from v = -span
/// to +span (sgn -1 mirrors it, the other hand), bowed ahead by bow, slanted by tilt so they read as a slash, spaced
/// gap apart across their normal; spread opens the outer tracks apart toward the far end.
pub fn claw_tracks(span: f64, o: ClawTracks) -> Vec<Vec<Pt>> {
    let base: Vec<Pt> = np::linspace(0.0, 1.0, o.steps)
        .iter()
        .map(|&q| {
            let v = span * (2.0 * q - 1.0);
            (o.u0 + o.bow * (PI * q).sin() + o.tilt * v, v)
        })
        .collect();
    let nb = base.len();
    let half = (o.n - 1) as f64 / 2.0;
    (0..o.n)
        .map(|k| {
            let off = (k as f64 - half) * o.gap;
            base.iter()
                .enumerate()
                .map(|(i, &(u, v))| {
                    let (a, b) = (base[i.saturating_sub(1)], base[(i + 1).min(nb - 1)]);
                    let (du, dv) = (b.0 - a.0, b.1 - a.1);
                    let ln = pmax(math_hypot(du, dv), 1e-6);
                    let (mut nu, mut nv) = (-dv / ln, du / ln);
                    if nu < 0.0 {
                        nu = -nu;
                        nv = -nv;
                    }
                    let q = i as f64 / (nb - 1) as f64;
                    (u + off * nu + (k as f64 - half) * o.spread * q, o.sgn * (v + off * nv))
                })
                .collect()
        })
        .collect()
}

/// Local (u, v) tracks turned to heading `a` (u along it, v to its right) as world (x, y).
pub fn to_world(tracks: &[Vec<Pt>], a: f64) -> Vec<Vec<Pt>> {
    let (c, s) = (a.cos(), a.sin());
    tracks.iter().map(|t| t.iter().map(|&(u, v)| (u * c - v * s, u * s + v * c)).collect()).collect()
}

/// `claw_marks` keyword arguments.
#[derive(Clone, Copy)]
pub struct ClawMarks {
    pub w_claw: f64,
    pub w_scar: f64,
    pub scar_fade: f64,
    pub stagger: f64,
    pub flash: f64,
    pub hot: Option<i8>,
}

impl Default for ClawMarks {
    fn default() -> Self {
        ClawMarks { w_claw: 3.2, w_scar: 2.0, scar_fade: 0.0, stagger: 0.05, flash: 0.0, hot: None }
    }
}

/// Paints one sweep frame of claw tracks (world px polylines) into shade map `m`.
/// head: how far the claws' tips have run (0 at the start of a track, 1 at its end, past 1 they leave it);
/// claw: shades (body, lit, pale, white tip), scar: shades (deep gash, wet lip, specular);
/// the claw is the stretch of `claw_len` behind its tip, the scar the track behind the claw's tail only.
/// flash: radius of a white-hot disc on the middle claw's tip. Returns the middle track's tip point or None.
#[allow(clippy::too_many_arguments)]
pub fn claw_marks(m: &mut Shade, x: &Grid, y: &Grid, tracks: &[Vec<Pt>], head: f64, claw_len: f64, claw: &[i8], scar: &[i8], o: ClawMarks) -> Option<Pt> {
    let n = tracks.len();
    let mut tip_pt = None;
    let bm = bayer(m);
    for (i, pts) in tracks.iter().enumerate() {
        let h = head - o.stagger * (i as f64 - (n as f64 - 1.0) / 2.0).abs();
        let (d, t, sd) = stroke(x, y, pts, 0.0, 0.0);
        let scar_to = pmin(1.0, pmax(0.0, h - claw_len * 0.9));
        if scar_to > 0.02 {
            let wt = t.mapv(|t| o.w_scar * (np::clip(t / pmax(scar_to, 0.05), 0.0, 1.0) * PI).sin().powf(0.7) * pmin(1.0, 0.5 + scar_to));
            let mut on = Array2::from_shape_fn(m.raw_dim(), |p| d[p] < wt[p] / 2.0 && t[p] <= scar_to);
            if o.scar_fade > 0.0 {
                on.zip_mut_with(&bm, |a, &b| *a = *a && b >= o.scar_fade);
            }
            set(m, scar[0], |p| on[p]);
            set(m, scar[1], |p| on[p] && sd[p] < 0.0 && d[p] > wt[p] / 2.0 - 0.75);
            for q in [0.3, 0.62] {
                if q < scar_to {
                    set(m, scar[2], |p| on[p] && (t[p] - q).abs() < 0.035 && sd[p] < 0.0 && d[p] < 0.4);
                }
            }
        }
        let (lo, hi) = (h - claw_len, h);
        if hi > 0.0 && lo < 1.0 {
            let s = t.mapv(|t| (t - lo) / claw_len);
            let prof = s.mapv(|s| if s < 0.8 { 0.3 + 0.7 * (np::clip(s, 0.0, 0.8) / 0.8).powf(0.9) } else { (1.0 - s) / 0.2 });
            let on = Array2::from_shape_fn(m.raw_dim(), |p| {
                d[p] < o.w_claw * np::clip(prof[p], 0.0, 1.0) / 2.0 && s[p] >= 0.0 && s[p] <= 1.0 && t[p] <= 1.0
            });
            set(m, claw[0], |p| on[p]);
            set(m, claw[1], |p| on[p] && sd[p] < 0.0);
            set(m, claw[2], |p| on[p] && d[p] < o.w_claw * prof[p] * 0.18 && s[p] > 0.25);
            set(m, claw[3], |p| on[p] && s[p] > 0.84);
        }
        if i as i64 == (n as i64 - 1) / 2 && hi > 0.0 && lo < 1.0 {
            let k = pmin(1.0, pmax(0.0, hi)) * (pts.len() - 1) as f64;
            let j = k as usize;
            let j2 = (j + 1).min(pts.len() - 1);
            let f = k - j as f64;
            tip_pt = Some((pts[j].0 + (pts[j2].0 - pts[j].0) * f, pts[j].1 + (pts[j2].1 - pts[j].1) * f));
        }
    }
    if let (true, Some(tp), Some(hot)) = (o.flash > 0.0, tip_pt, o.hot) {
        let q = hyp(&sub(x, tp.0), &sub(y, tp.1));
        set(m, hot, |p| q[p] < o.flash);
    }
    tip_pt
}

/// A thick glossy blood drop (shades deep, body, light, specular) with a short streak behind it along `tail` (dx, dy).
pub fn drop(m: &mut Shade, x: &Grid, y: &Grid, cx: f64, cy: f64, r: f64, shades: &[i8], tail: Option<Pt>) {
    if let Some(tail) = tail {
        let (d, _, _) = stroke(&sub(x, cx), &sub(y, cy), &[(0.0, 0.0), tail], r * 1.5, 0.0);
        set(m, shades[0], |p| d[p] < 0.0);
    }
    ball(m, x, y, cx, cy, r, shades, Ball::default());
}

/// `claw_drops` keyword arguments.
#[derive(Clone, Copy)]
pub struct ClawDrops {
    pub r: f64,
    pub n: i64,
    pub fly: f64,
    pub grav: f64,
    pub start: i64,
    pub lim: f64,
}

impl Default for ClawDrops {
    fn default() -> Self {
        ClawDrops { r: 1.1, n: 5, fly: 3.2, grav: 0.8, start: 1, lim: 19.0 }
    }
}

/// Blood drops flung off the far ends of the claw tracks along their last tangent (frame `f` counted from `start`): a
/// thick glossy drop with a dark edge and a short streak behind it while it flies, fewer and lower as it falls.
pub fn claw_drops(m: &mut Shade, x: &Grid, y: &Grid, tracks: &[Vec<Pt>], f: i64, seed: f64, shades: &[i8], o: ClawDrops) {
    if f < o.start {
        return;
    }
    let k = f - o.start;
    for j in 0..o.n {
        let pts = &tracks[(j as usize) % tracks.len()];
        let ((ax, ay), (bx, by)) = (pts[pts.len() - 2], pts[pts.len() - 1]);
        let ln = pmax(math_hypot(bx - ax, by - ay), 1e-6);
        let (dx, dy) = ((bx - ax) / ln, (by - ay) / ln);
        let jf = j as f64;
        let sp = 0.45 * (hsh(jf, seed) - 0.5);
        let (c, s) = (sp.cos(), sp.sin());
        let (ddx, ddy) = (dx * c - dy * s, dx * s + dy * c);
        let dist = o.fly * (0.7 + 0.8 * hsh(jf, seed + 1.0)) * ((k + 1) as f64).powf(0.8);
        let kf = k as f64;
        let (cx, cy) = (bx + ddx * dist, by + ddy * dist + o.grav * kf * kf);
        if (k >= 2 && j % 2 != 0) || cx.abs() > o.lim || cy.abs() > o.lim {
            continue;
        }
        let rr = o.r * (0.85 + 0.35 * hsh(jf, seed + 2.0)) * if k < 3 { 1.0 } else { 0.8 };
        drop(m, x, y, cx, cy, rr, shades, if k < 2 { Some((-ddx * 2.6, -ddy * 2.6)) } else { None });
    }
}

// ----- thematic hits -----

/// What a `Theme` throws as debris (th["kind"]); any other kind in Python draws as `Drop`.
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Kind {
    Drop,
    Shard,
    Chip,
    Ember,
    Spike,
}

/// The `th` dict of `hit_cell`: rim, streak (outer, mid, hot), disc (lit, hot), deb (4 shades, shadow to highlight),
/// drop (4 shades) the drop debris, drops (4 shades) extra flung drops or None, mist (3 tones) or None.
#[derive(Clone, Copy)]
pub struct Theme {
    pub kind: Kind,
    pub rim: i8,
    pub streak: [i8; 3],
    pub disc: [i8; 2],
    pub deb: [i8; 4],
    pub drop: Option<[i8; 4]>,
    pub drops: Option<[i8; 4]>,
    pub mist: Option<[i8; 3]>,
}

/// One cell of a blow's hit on a body (frames 6, the peak at frame 1): a white-hot flash disc with tapered streaks
/// round it, the debris of the theme thrown out and mist puffs that break into dots. `f` is the frame, `big` a heavy
/// hit. Returns the cell.
pub fn hit_cell(x: &Grid, y: &Grid, f: i64, big: bool, th: &Theme, seed: i64) -> Shade {
    let mut m = Shade::from_elem(x.raw_dim(), -1);
    let sd = seed as f64;
    let s = if big { 1.35 } else { 1.0 };
    let turn = 0.4 * hsh(sd, 3.0);
    let p = pmax(0.0, (f as f64 - 0.5) / 4.5);
    let out = 1.0 - (1.0 - p) * (1.0 - p);
    let nbig = |a: i64, b: i64| if big { a } else { b };
    if f == 1 {
        streaks(&mut m, x, y, 0.0, 0.0, nbig(12, 8), 1.5, 12.8 * s, 2.3 * s, &th.streak, Streaks { seed: sd, spin: turn, ..Default::default() });
    } else if f == 2 {
        streaks(&mut m, x, y, 0.0, 0.0, nbig(12, 8), 5.5 * s, 13.4 * s, 1.3 * s, &th.streak, Streaks { seed: sd + 1.0, spin: turn, short: 0.5, ..Default::default() });
    } else if f == 3 {
        let sh = [th.streak[0], th.streak[0], th.streak[1]];
        streaks(&mut m, x, y, 0.0, 0.0, nbig(8, 5), 9.5 * s, 13.0 * s, 0.9, &sh, Streaks { seed: sd + 2.0, spin: turn, short: 0.5, ..Default::default() });
    }
    let r = hyp(x, y);
    let disc = match f {
        0 => 1.6,
        1 => 5.2 * s,
        2 => 3.2 * s,
        _ => 0.0,
    };
    if disc != 0.0 {
        set(&mut m, th.disc[0], |p| r[p] < disc);
        set(&mut m, th.disc[1], |p| r[p] < disc * 0.62);
    }
    let n = nbig(9, 6);
    let fall = {
        let q = pmax(0.0, (f - 2) as f64);
        q * q
    };
    for j in 0..n {
        let jf = j as f64;
        let a = turn + TAU * jf / n as f64 + 0.5 * (hsh(jf, sd) - 0.5);
        let dist = (2.5 + 8.0 * (0.6 + 0.4 * hsh(jf, sd + 4.0))) * s * out;
        let (cx, cy) = (dist * a.cos(), dist * a.sin() + 1.6 * fall * 0.5);
        if f == 0 || (f >= 4 && j % 2 != 0) || (f == 5 && j % 3 != 0) {
            continue;
        }
        let size = (1.2 + 1.3 * hsh(jf, sd + 6.0)) * if big { 1.15 } else { 1.0 } * if f < 4 { 1.0 } else { 0.75 };
        match th.kind {
            Kind::Shard | Kind::Chip if f >= 1 => {
                let pts = polygon(cx, cy, size * 1.5, if th.kind == Kind::Shard { 4 } else { 5 }, sd + jf, Polygon { ph: a, jit: 0.3 });
                facets(&mut m, x, y, &pts, &th.deb, Facets { top: false });
            }
            Kind::Spike => {
                let tip = (cx + a.cos() * size * 2.6, cy + a.sin() * size * 2.6);
                let (d, t, sdv) = stroke(x, y, &[(cx, cy), tip], size * 1.1, 0.0);
                set(&mut m, th.deb[1], |p| d[p] < 0.0);
                set(&mut m, th.deb[2], |p| d[p] < 0.0 && sdv[p] < 0.0);
                set(&mut m, th.deb[3], |p| d[p] < 0.0 && t[p] > 0.7);
            }
            Kind::Ember => {
                ball(&mut m, x, y, cx, cy, size * 0.8, &th.deb, Ball::default());
            }
            _ => {
                let dd = th.drop.unwrap_or(th.deb);
                drop(&mut m, x, y, cx, cy, size * 0.85, &dd, if f < 3 { Some((-a.cos() * 2.4, -a.sin() * 2.4)) } else { None });
            }
        }
    }
    if let (Some(drops), true, true) = (th.drops, th.kind != Kind::Drop, f >= 1) {
        let nn = nbig(5, 3);
        for j in 0..nn {
            let jf = j as f64;
            let a = turn + 0.5 + TAU * (jf + 0.5) / nn as f64 + 0.4 * (hsh(jf, sd + 12.0) - 0.5);
            let dist = (4.0 + 8.0 * hsh(jf, sd + 13.0)) * s * out;
            if f >= 4 && j % 2 != 0 {
                continue;
            }
            drop(&mut m, x, y, dist * a.cos(), dist * a.sin() + 1.4 * fall * 0.5, 1.0 * if big { 1.2 } else { 1.0 }, &drops,
                if f < 3 { Some((-a.cos() * 2.2, -a.sin() * 2.2)) } else { None });
        }
    }
    if let (Some(mist), true) = (th.mist, f >= 2) {
        let k = (f - 1) as f64;
        let nn = nbig(5, 3);
        for j in 0..nn {
            let jf = j as f64;
            let a = turn + 0.7 + TAU * jf / nn as f64 + hsh(jf, sd + 9.0);
            let dd = (2.5 + 2.2 * k) * s * (0.6 + 0.5 * hsh(jf, sd + 10.0));
            puff(&mut m, x, y, dd * a.cos(), dd * a.sin() - 0.6 * k, (2.0 + 0.5 * k) * s * 0.8, &mist,
                Puff { brk: pmin(1.0, (f as f64 - 1.5) / 3.5), seed: jf + sd, ph: 0.3 * f as f64 });
        }
    }
    if f >= 4 {
        m = fade(&m, (f - 3) as f64 * 0.3);
    }
    if f <= 2 { rim(&m, th.rim) } else { m }
}

/// Sheet px (i, j) of the point `du` along and `dv` across heading `a` (world px), for a mote or twinkle on a bolt.
pub fn at(m: &Shade, x: &Grid, y: &Grid, a: f64, du: f64, dv: f64) -> (usize, usize) {
    to_px(m, x, y, du * a.cos() - dv * a.sin(), du * a.sin() + dv * a.cos())
}

/// `kite` keyword arguments.
#[derive(Clone, Copy)]
pub struct Kite {
    pub tail: f64,
}

impl Default for Kite {
    fn default() -> Self {
        Kite { tail: 0.3 }
    }
}

/// A faceted shard (kite) of length `l` and width `w` at (`cx`, `cy`) pointing `ang`: shades (deep, mid, light,
/// highlight), the lit half and a ridge line pale, a hard highlight near the tip.
pub fn kite(m: &mut Shade, x: &Grid, y: &Grid, cx: f64, cy: f64, ang: f64, l: f64, w: f64, shades: &[i8], o: Kite) -> Array2<bool> {
    let (u, v) = rot(&sub(x, cx), &sub(y, cy), ang);
    let tail = o.tail;
    let t = u.mapv(|u| np::clip((u + tail * l) / ((1.0 + tail) * l), 0.0, 1.0));
    let half = t.mapv(|t| w / 2.0 * if t < 0.55 { t / 0.55 } else { (1.0 - t) / 0.45 });
    let on = Array2::from_shape_fn(m.raw_dim(), |p| u[p] > -tail * l && u[p] < l && v[p].abs() <= half[p]);
    set(m, shades[1], |p| on[p]);
    set(m, shades[2], |p| on[p] && v[p] < -0.05 * w);
    set(m, shades[0], |p| on[p] && v[p] > 0.18 * w);
    set(m, shades[3], |p| on[p] && v[p].abs() < 0.09 * w && t[p] > 0.25);
    on
}

/// `hit_burst` keyword arguments.
#[derive(Clone, Copy)]
pub struct HitBurst {
    pub cx: f64,
    pub cy: f64,
    pub r: f64,
    pub flat: f64,
    pub seed: f64,
    pub shards: Option<[i8; 4]>,
    pub rise: f64,
}

impl Default for HitBurst {
    fn default() -> Self {
        HitBurst { cx: 0.0, cy: 0.0, r: 12.0, flat: 1.0, seed: 0.0, shards: None, rise: 1.0 }
    }
}

/// One blow in six frames (frame 1 is the peak, name it impact_peak): 0 a core disc, 1 flash disc with mixed
/// streaks and a ring, 2 a hollow lumpy burst with longer streaks, 3 to 5 three-tone puffs that rise and break up into
/// dots with embers falling out. `tones` (deep, mid, light, hot), `smoke` (shadow, mid, light), `shards` (deep, mid,
/// light, highlight) adds flying kites. flat < 1 squashes the blow onto the ground. Paints into `m` and returns it
/// (with a rim of `rim_s` up to frame 3).
#[allow(clippy::too_many_arguments)]
pub fn hit_burst(m: &mut Shade, x: &Grid, y: &Grid, f: i64, tones: &[i8], smoke: &[i8], rim_s: i8, o: HitBurst) -> Shade {
    let (cx, cy, r, flat, seed) = (o.cx, o.cy, o.r, o.flat, o.seed);
    let yf = y.mapv(|v| cy + (v - cy) / flat);
    let hot = tones[3];
    if f == 0 {
        let q = hyp(&sub(x, cx), &sub(&yf, cy));
        set(m, tones[2], |p| q[p] < 0.22 * r);
        set(m, hot, |p| q[p] < 0.12 * r);
    } else if f == 1 || f == 2 {
        let k = f - 1;
        let kf = k as f64;
        let sh = [tones[1 + k as usize], if 2 + k < 4 { tones[2 + k as usize] } else { hot }, hot];
        streaks(m, x, &yf, cx, cy, 10 + 2 * k, r * (0.34 + 0.22 * kf), r * (0.9 + 0.2 * kf), 2.6 - 0.9 * kf, &sh,
            Streaks { seed: seed + 2.0, spin: 0.2 * kf, ..Default::default() });
        let ring_on = ring(x, &yf, cx, cy, r * (0.72 + 0.14 * kf), 0.8, Ring::default());
        set(m, tones[(2 - k) as usize], |p| ring_on[p]);
        let d = lumpy(x, &yf, cx, cy, r * (0.55 + 0.1 * kf), Lumpy { amp: 0.16, seed, ph: 0.4 + kf, lobes: 6 });
        let on = d.mapv(|v| v < 1.0);
        set(m, tones[1], |p| on[p]);
        set(m, tones[2], |p| on[p] && d[p] < 0.8);
        if k == 0 {
            set(m, hot, |p| on[p] && d[p] < 0.5);
        } else {
            set(m, tones[1], |p| on[p] && d[p] < 0.42);
        }
    } else {
        let k = f - 3;
        let kf = k as f64;
        for j in 0..5i64 {
            let jf = j as f64;
            let aj = TAU * jf / 5.0 - PI / 2.0 + 0.3 + 0.4 * hsh(jf, seed);
            let rr = r * (0.3 + 0.1 * kf);
            let brk = [0.0, 0.45, 0.8][k.min(2) as usize];
            puff(m, x, y, cx + rr * aj.cos(), cy - o.rise * r * (0.12 + 0.2 * kf) + rr * 0.7 * flat * aj.sin(),
                r * (0.24 + 0.04 * kf + 0.03 * (j % 2) as f64), smoke, Puff { brk, seed: jf + seed, ph: f as f64 });
        }
        for j in 0..8i64 {
            let aj = TAU * j as f64 / 8.0 + 0.2;
            let rr = r * (1.05 + 0.1 * kf);
            if np::pymod_i(j + f, 3) != 0 {
                let (i, jj) = to_px(m, x, y, cx + rr * aj.cos(), cy + rr * flat * 0.8 * aj.sin() + 1.5 * kf * kf);
                m[[jj, i]] = [tones[3], tones[2], tones[1]][k.min(2) as usize];
            }
        }
    }
    if let (Some(shards), true) = (o.shards, (1..=4).contains(&f)) {
        for j in 0..6i64 {
            let jf = j as f64;
            let aj = TAU * jf / 6.0 + 0.5 * hsh(jf, seed + 9.0);
            let rr = r * (0.55 + 0.32 * (f - 1) as f64) * (0.8 + 0.4 * hsh(jf, seed + 4.0));
            let f1 = (f - 1) as f64;
            kite(m, x, y, cx + rr * aj.cos(), cy + rr * flat * aj.sin() + 0.6 * (f1 * f1), aj,
                r * 0.26 * (1.0 - 0.12 * f1), r * 0.13, &shards, Kite { tail: 0.35 });
        }
    }
    rim_if(m, rim_s, f <= 3)
}

// ----- ground reaction -----

/// A hit's weight (export.WEIGHTS) and what it throws: `Weight::parse` takes the Python key.
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Weight {
    Light,
    Heavy,
    Finisher,
    Blast,
}

/// One `GROUND` entry: debris chunks, dust puffs, cracks, fly factor.
#[derive(Clone, Copy)]
pub struct Ground {
    pub debris: i64,
    pub dust: i64,
    pub crack: i64,
    pub fly: f64,
}

impl Weight {
    pub fn parse(s: &str) -> Result<Weight, String> {
        match s {
            "light" => Ok(Weight::Light),
            "heavy" => Ok(Weight::Heavy),
            "finisher" => Ok(Weight::Finisher),
            "blast" => Ok(Weight::Blast),
            _ => Err(format!("KeyError: '{s}'")),
        }
    }
    /// The `GROUND[weight]` row.
    pub fn ground(self) -> Ground {
        match self {
            Weight::Light => Ground { debris: 4, dust: 2, crack: 0, fly: 1.0 },
            Weight::Heavy => Ground { debris: 10, dust: 4, crack: 3, fly: 1.4 },
            Weight::Finisher => Ground { debris: 18, dust: 6, crack: 6, fly: 1.9 },
            Weight::Blast => Ground { debris: 16, dust: 6, crack: 5, fly: 1.7 },
        }
    }
}

/// World (x, y) and resting flag of debris chunk `j` at `t` s after contact: an arc up and out under gravity, one
/// bounce at a third of the height, then at rest on its own spot of the ground plane.
#[allow(clippy::too_many_arguments)]
pub fn debris_at(j: i64, t: f64, cx: f64, cy: f64, r: f64, fly: f64, flat: f64, seed: f64) -> (f64, f64, bool) {
    let jf = j as f64;
    let (h0, h1, h2) = (hsh(jf, seed + 11.0), hsh(jf, seed + 12.0), hsh(jf, seed + 13.0));
    let side = if j % 2 != 0 { -1.0 } else { 1.0 };
    let spread = 0.25 + 0.95 * h0;
    let v0 = r * fly * (2.6 + 2.2 * h1);
    let g = r * 18.0 * fly;
    let (vx, vy) = (side * v0 * spread.sin(), v0 * spread.cos());
    let gy = cy + flat * r * 0.5 * (h2 - 0.5);
    let t1 = 2.0 * vy / g;
    if t < t1 {
        return (cx + vx * t, gy - (vy * t - 0.5 * g * t * t), false);
    }
    let (x1, vx2, vy2) = (cx + vx * t1, 0.45 * vx, 0.3 * vy);
    let t2 = 2.0 * vy2 / g;
    let u = t - t1;
    if u < t2 {
        return (x1 + vx2 * u, gy - (vy2 * u - 0.5 * g * u * u), false);
    }
    (x1 + vx2 * t2, gy, true)
}

/// `ground_impact` keyword arguments.
#[derive(Clone, Copy)]
pub struct GroundImpact {
    pub cx: f64,
    pub cy: f64,
    pub r: f64,
    pub weight: Weight,
    pub flat: f64,
    pub life: f64,
    pub seed: f64,
}

impl Default for GroundImpact {
    fn default() -> Self {
        GroundImpact { cx: 0.0, cy: 0.0, r: 12.0, weight: Weight::Heavy, flat: 0.35, life: 1.2, seed: 0.0 }
    }
}

/// The ground's reaction to a blow landing at (cx, cy) on it, frame `f` counted from the contact frame (nothing
/// before it): dust puffs that slide out both ways, rise a little and break into dots; debris chunks (tones deep,
/// mid, light) that arc, bounce once and rest; and for heavy, finisher and blast weights cracks in tones[0] that
/// grow over two frames and stay. What rests on the ground dissolves over the last 40 % of life s, so the one-shot
/// ends empty. flat squashes the ground plane (1 top-down, 0.35 side or 3/4). Paints into `m`.
#[allow(clippy::too_many_arguments)]
pub fn ground_impact(m: &mut Shade, x: &Grid, y: &Grid, f: i64, fps: f64, tones: &[i8], dust: &[i8], o: GroundImpact) {
    if f < 0 {
        return;
    }
    let (cx, cy, r, flat, life, seed) = (o.cx, o.cy, o.r, o.flat, o.life, o.seed);
    let g = o.weight.ground();
    let t = f as f64 / fps;
    let mut piece = Shade::from_elem(m.raw_dim(), -1);
    for j in 0..g.crack {
        let jf = j as f64;
        let a = TAU * (jf + 0.5 * hsh(jf, seed + 21.0)) / g.crack as f64;
        let ln = r * (0.6 + 0.6 * hsh(jf, seed + 22.0)) * pmin(1.0, (f + 1) as f64 / 2.0);
        let mut pts = vec![(cx, cy)];
        let (mut px, mut py) = (cx, cy);
        for k in 0..3 {
            let aj = a + 0.6 * (hsh((j * 3 + k) as f64, seed + 23.0) - 0.5);
            px += ln / 3.0 * aj.cos();
            py += ln / 3.0 * flat * aj.sin();
            pts.push((px, py));
        }
        let (d, _, _) = stroke(x, y, &pts, 1.1, 0.4);
        set(&mut piece, tones[0], |p| d[p] < 0.0);
    }
    for j in 0..g.dust {
        let jf = j as f64;
        let side = if j % 2 != 0 { -1.0 } else { 1.0 };
        let j2 = (j / 2) as f64;
        let out = r * (0.35 + 0.25 * j2) + r * 1.4 * (1.0 - (-t * 6.0).exp()) * (0.7 + 0.5 * hsh(jf, seed + 31.0));
        let rr = r * (0.16 + 0.05 * j2) * (1.0 + 1.2 * (1.0 - (-t * 5.0).exp())) * g.fly.sqrt();
        let brk = pmin(1.0, t / (0.5 * life));
        if brk < 1.0 {
            puff(&mut piece, x, y, cx + side * out, cy - r * 0.15 - r * 0.5 * t - rr * 0.4, rr, dust,
                Puff { brk, seed: jf + seed, ph: f as f64 * 0.3 });
        }
    }
    for j in 0..g.debris {
        let (dx, dy, rest) = debris_at(j, t, cx, cy, r, g.fly, flat, seed);
        let size = if j % 3 != 0 { 0.6 } else { 1.1 };
        let on = Array2::from_shape_fn(m.raw_dim(), |p| (x[p] - dx).abs() < size && (y[p] - dy).abs() < size);
        set(&mut piece, tones[1], |p| on[p]);
        if !rest {
            set(&mut piece, tones[2], |p| on[p] && y[p] < dy);
        }
    }
    if t > 0.6 * life {
        piece = fade(&piece, pmin(1.0, (t - 0.6 * life) / (0.4 * life)));
    }
    blit(m, &piece);
}

/// `outline(m, s)` when `on`, else `m` unchanged.
pub fn rim_if(m: &Shade, s: i8, on: bool) -> Shade {
    if on { outline(m, s) } else { m.clone() }
}

/// `leaf` keyword arguments.
#[derive(Clone, Copy)]
pub struct Leaf {
    pub roll: f64,
    pub bend: f64,
}

impl Default for Leaf {
    fn default() -> Self {
        Leaf { roll: 1.0, bend: 0.0 }
    }
}

/// A lens-shaped leaf or petal from its base at (`cx`, `cy`) along `ang`: shades (deep, mid, light, vein); roll < 1
/// narrows it as it turns edge on, bend curls its tip; the lit half is lighter and a thin midrib runs down it.
pub fn leaf(m: &mut Shade, x: &Grid, y: &Grid, cx: f64, cy: f64, ang: f64, l: f64, w: f64, shades: &[i8], o: Leaf) -> Array2<bool> {
    let (u, v) = rot(&sub(x, cx), &sub(y, cy), ang);
    let t = u.mapv(|u| np::clip(u / l, 0.0, 1.0));
    let vv = Zip::from(&v).and(&t).map_collect(|&v, &t| v - o.bend * l * t * t);
    let half = t.mapv(|t| 0.5 * w * pmax(o.roll, 0.12) * (PI * t).sin().powf(0.75));
    let on = Array2::from_shape_fn(m.raw_dim(), |p| u[p] >= 0.0 && u[p] <= l && vv[p].abs() <= half[p]);
    set(m, shades[1], |p| on[p]);
    set(m, shades[2], |p| on[p] && vv[p] < -0.18 * half[p]);
    set(m, shades[0], |p| on[p] && vv[p] > 0.45 * half[p]);
    set(m, shades[3], |p| on[p] && vv[p].abs() < 0.12 * pmax(half[p], 0.8) && t[p] > 0.1 && t[p] < 0.85);
    on
}
