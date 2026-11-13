//! caster.py: the mockup caster for /beanfx (optional, asked in the brief): a glowing robed silhouette that
//! performs the effect, with an optional avatar (a translucent copy behind it with a halo). No face; it shows
//! scale and the casting beats.
//!
//! ```ignore
//! let pose = cs::pose_at(f, &[(0.0, "chest"), (20.0, "raise"), (40.0, "point")], &[(0.0, "rest"), (40.0, "behind")], Some(aim), 0.0)?;
//! let g = cs::draw(&mut over, (h, w), foot, sc, pose, f, cs::Draw { hair: "loose", ..Default::default() })?;
//! cs::body_light(&mut light, &g, charge);
//! cs::finger_light(&mut light, &g, point, jab);
//! ```
//!
//! `over` is `&mut dyn FnMut(ys, xs, rgb, a)` and composites one colour per point: ys and xs are the points'
//! rows and columns (they may fall outside the canvas), `rgb` is (n, 3) floats 0..1 and `a` has n alphas. Where
//! Python passes one colour or one alpha for every point, it arrives here already repeated to n.
//!
//! Local units: feet at (0, 0), y down, the figure faces +x and is about 78 units tall; sc maps units to px (0.44
//! is 34 px). lift (0..1) raises hair and flaps into the wind, flut (0..1) is how hard cloth and hair flap. Learnt
//! on drafts/van_kiem_quy_tong_v2 and v3: keep the body core light low on a small figure (it burns white under
//! the pools), keep every strand at least 1 px wide (mw), and light the avatar from inside its mask with a bright
//! rim so it reads as luminous rather than a grey copy.
//!
//! Single trailing keyword arguments (`flat`, `charge`, `jab`, `point`) are plain parameters; the others are
//! option structs (`Draw`, `Strand`, `Ellipse`).

use crate::color;
use crate::np;
use ndarray::{Array2, ArrayView2, Zip};
use std::f64::consts::PI;
use std::ops::Range;

/// Golden figure, dark to hot.
pub const BODY: [&str; 5] = ["#4a2208", "#9a5a10", "#d89a28", "#f6d266", "#fff4c8"];

/// A point (x, y).
pub type P = [f64; 2];
/// One arm: (elbow, hand) in local units.
pub type Arm = (P, P);
/// (front arm, back arm).
pub type Pose = (Arm, Arm);
/// over(ys, xs, rgb, a): see the module doc.
pub type Over<'a> = dyn FnMut(&[i64], &[i64], &Array2<f64>, &[f64]) + 'a;

pub const SHOULDER: P = [5.0, -56.0];

const FRONT: [(&str, Arm); 4] = [
    ("rest", ([7.0, -47.0], [8.0, -38.0])),
    ("chest", ([9.0, -48.0], [6.0, -60.0])),
    ("raise_", ([9.0, -66.0], [12.0, -78.0])),
    ("pull", ([2.0, -50.0], [7.0, -61.0])),
];
const BACK: [(&str, Arm); 3] = [
    ("rest", ([-6.0, -47.0], [-7.0, -38.0])),
    ("out", ([-9.0, -50.0], [-14.0, -44.0])),
    ("behind", ([-8.0, -48.0], [-3.0, -43.0])),
];

fn hexf(s: &str) -> Result<[f64; 3], String> {
    let c = color::rgb(s)?;
    Ok([c[0] as f64 / 255.0, c[1] as f64 / 255.0, c[2] as f64 / 255.0])
}

/// Python's max(a, b): a unless b is larger.
fn pmax(a: f64, b: f64) -> f64 {
    if b > a {
        b
    } else {
        a
    }
}

/// The window (rows, columns) of a (H, W) canvas that a shape spanning x0..x1, y0..y1 can touch.
fn win(shape: (usize, usize), x0: f64, x1: f64, y0: f64, y1: f64) -> (Range<usize>, Range<usize>) {
    let (h, w) = (shape.0 as i64, shape.1 as i64);
    let xa = (x0 as i64).max(0);
    let xb = ((x1 as i64) + 2).min(w);
    let ya = (y0 as i64).max(0);
    let yb = ((y1 as i64) + 2).min(h);
    let (xa, xb) = (xa.min(w), xb.max(xa).min(w));
    let (ya, yb) = (ya.min(h), yb.max(ya).min(h));
    (ya as usize..yb as usize, xa as usize..xb as usize)
}

/// np.clip(s, 0, 1) then s * s * (3 - 2 s): a smooth step.
pub fn ease_io(s: f64) -> f64 {
    let s = np::clip(s, 0.0, 1.0);
    s * s * (3.0 - 2.0 * s)
}

/// (a + (b - a) t) for both coordinates.
pub fn lerp(a: P, b: P, t: f64) -> P {
    [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
}

fn seg_d1(x: f64, y: f64, a: P, b: P) -> f64 {
    let (ex, ey) = (b[0] - a[0], b[1] - a[1]);
    let den = ex * ex + ey * ey;
    let den = if den == 0.0 { 1e-9 } else { den };
    let h = np::clip(((x - a[0]) * ex + (y - a[1]) * ey) / den, 0.0, 1.0);
    np::hypot(x - a[0] - ex * h, y - a[1] - ey * h)
}

/// Distance from every (X, Y) to the segment a to b.
pub fn seg_d(x: &ArrayView2<f64>, y: &ArrayView2<f64>, a: P, b: P) -> Array2<f64> {
    let mut out = Array2::zeros(x.dim());
    Zip::from(&mut out).and(x).and(y).for_each(|o, &xv, &yv| *o = seg_d1(xv, yv, a, b));
    out
}

// ---- light, same falloff as lt, windowed ----

fn splat(l: &mut Array2<f64>, sy: Range<usize>, sx: Range<usize>, k: f64, dist: impl Fn(f64, f64) -> f64) {
    for y in sy {
        for x in sx.clone() {
            let d = dist(x as f64, y as f64);
            let t = if d < 1.0 {
                let m = 1.0 - d;
                m * m * k
            } else {
                0.0
            };
            l[[y, x]] += t;
        }
    }
}

/// A round pool of light at (x, y), radius r, strength k; flat squashes it vertically (1 is round).
pub fn glow(l: &mut Array2<f64>, x: f64, y: f64, r: f64, k: f64, flat: f64) {
    let (sy, sx) = win(l.dim(), x - r, x + r, y - r * flat, y + r * flat);
    splat(l, sy, sx, k, |px, py| np::hypot(px - x, (py - y) / flat) / r);
}

/// A pool of light along the segment p0 to p1.
pub fn glow_line(l: &mut Array2<f64>, p0: P, p1: P, r: f64, k: f64) {
    let (sy, sx) = win(
        l.dim(),
        p0[0].min(p1[0]) - r,
        p0[0].max(p1[0]) + r,
        p0[1].min(p1[1]) - r,
        p0[1].max(p1[1]) + r,
    );
    splat(l, sy, sx, k, |px, py| seg_d1(px, py, p0, p1) / r);
}

/// A ring of light, radius big_r, thickness r.
pub fn glow_ring(l: &mut Array2<f64>, x: f64, y: f64, big_r: f64, r: f64, k: f64, flat: f64) {
    let (sy, sx) = win(l.dim(), x - big_r - r, x + big_r + r, y - (big_r + r) * flat, y + (big_r + r) * flat);
    splat(l, sy, sx, k, |px, py| (np::hypot(px - x, (py - y) / flat) - big_r).abs() / r);
}

// ---- shapes ----

/// Tone map for one part: base, a step up where the top-left neighbour is empty, a step down bottom-right.
pub fn shade(m: &Array2<bool>, base: i64) -> Array2<i64> {
    let (h, w) = m.dim();
    let at = |y: i64, x: i64| y >= 0 && x >= 0 && (y as usize) < h && (x as usize) < w && m[[y as usize, x as usize]];
    let mut t = Array2::from_elem((h, w), base);
    for y in 0..h {
        for x in 0..w {
            let (yi, xi) = (y as i64, x as i64);
            let ul = at(yi - 1, xi - 1);
            let dr = at(yi + 1, xi + 1);
            let v = m[[y, x]];
            if v && !ul {
                t[[y, x]] = (base + 1).min(4);
            }
            if v && !dr && ul {
                t[[y, x]] = (base - 1).max(0);
            }
        }
    }
    t
}

/// Points of a quadratic Bezier from p0 to p1 bowed toward c.
pub fn bez(p0: P, c: P, p1: P, n: usize) -> Vec<P> {
    np::linspace(0.0, 1.0, n)
        .iter()
        .map(|&t| {
            let u = 1.0 - t;
            [
                u * u * p0[0] + 2.0 * u * t * c[0] + t * t * p1[0],
                u * u * p0[1] + 2.0 * u * t * c[1] + t * t * p1[1],
            ]
        })
        .collect()
}

/// Pixels inside the closed polygon pts (even-odd), for soft cloth outlines built from curves.
pub fn poly_in(x: &ArrayView2<f64>, y: &ArrayView2<f64>, pts: &[P]) -> Array2<bool> {
    let mut inside = Array2::from_elem(x.dim(), false);
    for i in 0..pts.len() {
        let (a, b) = (pts[i], pts[(i + 1) % pts.len()]);
        let d = if b[1] - a[1] == 0.0 { 1e-9 } else { b[1] - a[1] };
        Zip::from(&mut inside).and(x).and(y).for_each(|o, &xv, &yv| {
            let cross = (a[1] > yv) != (b[1] > yv);
            let xi = (b[0] - a[0]) * (yv - a[1]) / d + a[0];
            *o ^= cross && (xv < xi);
        });
    }
    inside
}

/// Pixels inside the triangle a, b, c.
pub fn tri(x: &ArrayView2<f64>, y: &ArrayView2<f64>, a: P, b: P, c: P) -> Array2<bool> {
    let side = |p: P, q: P, xv: f64, yv: f64| (xv - q[0]) * (p[1] - q[1]) - (p[0] - q[0]) * (yv - q[1]);
    let mut out = Array2::from_elem(x.dim(), false);
    Zip::from(&mut out).and(x).and(y).for_each(|o, &xv, &yv| {
        let (d1, d2, d3) = (side(a, b, xv, yv), side(b, c, xv, yv), side(c, a, xv, yv));
        *o = !(((d1 < 0.0) || (d2 < 0.0) || (d3 < 0.0)) && ((d1 > 0.0) || (d2 > 0.0) || (d3 > 0.0)));
    });
    out
}

/// Options of `strand`.
#[derive(Clone, Debug)]
pub struct Strand {
    /// Capsules in the chain.
    pub n: usize,
    /// Thinnest width.
    pub mw: f64,
}

impl Default for Strand {
    fn default() -> Self {
        Strand { n: 12, mw: 0.0 }
    }
}

/// A hair lock, ribbon or cloth flap: a chain of capsules from s0, its angle turning from a0 to a1, waving.
/// Returns the mask and the chain's points.
#[allow(clippy::too_many_arguments)]
pub fn strand(lx: &ArrayView2<f64>, ly: &ArrayView2<f64>, s0: P, a0: f64, a1: f64, length: f64, w0: f64, w1: f64,
              wave: &dyn Fn(usize) -> f64, o: Strand) -> (Array2<bool>, Vec<P>) {
    let mut m = Array2::from_elem(lx.dim(), false);
    let mut pts = vec![s0];
    let (mut x, mut y) = (s0[0], s0[1]);
    let n = o.n;
    for k in 0..n {
        let t = k as f64 / (n as f64 - 1.0);
        let a = a0 + (a1 - a0) * t + wave(k) * t;
        let (nx, ny) = (x + a.cos() * length / n as f64, y + a.sin() * length / n as f64);
        let r = pmax(w0 + (w1 - w0) * t, o.mw);
        let d = seg_d(lx, ly, [x, y], [nx, ny]);
        Zip::from(&mut m).and(&d).for_each(|mv, &dv| *mv |= dv <= r);
        x = nx;
        y = ny;
        pts.push([x, y]);
    }
    (m, pts)
}

fn named(poses: &[(&str, Arm)], name: &str) -> Result<Arm, String> {
    poses.iter().find(|(n, _)| *n == name).map(|(_, a)| *a).ok_or_else(|| format!("'{name}'"))
}

/// Front and back arm (elbow, hand) in local units from (frame, pose name) keys, eased between keys. Front poses:
/// rest, chest (two-finger sign), raise (to the sky), pull, point (along unit vector aim, the hand pushed out by
/// jab). Back poses: rest, out (balance while flying), behind (hand at the small of the back).
pub fn pose_at(f: f64, front_keys: &[(f64, &str)], back_keys: &[(f64, &str)], aim: Option<P>, jab: f64) -> Result<Pose, String> {
    let mut front: Vec<(&str, Arm)> = FRONT.to_vec();
    if let Some(d) = aim {
        let sh = SHOULDER;
        front.push((
            "point",
            (
                [sh[0] + d[0] * 11.5, sh[1] + d[1] * 11.5],
                [sh[0] + d[0] * (23.5 + jab), sh[1] + d[1] * (23.5 + jab)],
            ),
        ));
    }
    let at = |keys: &[(f64, &str)], poses: &[(&str, Arm)]| -> Result<Arm, String> {
        let keys: Vec<(f64, &str)> = keys.iter().map(|&(k, p)| (k, if p == "raise" { "raise_" } else { p })).collect();
        let first = keys.first().ok_or("list index out of range")?;
        if f <= first.0 {
            return named(poses, first.1);
        }
        for w in keys.windows(2) {
            let ((f0, a), (f1, b)) = (w[0], w[1]);
            if f0 <= f && f <= f1 {
                let t = ease_io((f - f0) / pmax(f1 - f0, 1e-6));
                let (pa, pb) = (named(poses, a)?, named(poses, b)?);
                return Ok((lerp(pa.0, pb.0, t), lerp(pa.1, pb.1, t)));
            }
        }
        named(poses, keys[keys.len() - 1].1)
    };
    Ok((at(front_keys, &front)?, at(back_keys, &BACK)?))
}

/// Unit vector from the caster's front shoulder to a world point, for pose_at(aim).
pub fn aim_from(foot: P, sc: f64, target: P) -> P {
    let d = [target[0] - (foot[0] + SHOULDER[0] * sc), target[1] - (foot[1] + SHOULDER[1] * sc)];
    let n = np::math_hypot(d[0], d[1]);
    let n = if n == 0.0 { 1.0 } else { n };
    [d[0] / n, d[1] / n]
}

/// What `draw` hands back: where the avatar's inner mask sits, and world key points.
#[derive(Clone, Debug)]
pub struct Mask {
    pub sy: Range<usize>,
    pub sx: Range<usize>,
    /// The fade inside the figure, over the window.
    pub inner: Array2<f64>,
}

/// World key points of a drawn figure (head, neck, hip, feet, finger, hair polylines) and, for a ghost, its inner
/// mask.
#[derive(Clone, Debug)]
pub struct Figure {
    pub mask: Option<Mask>,
    pub sc: f64,
    pub head: P,
    pub neck: P,
    pub hip: P,
    pub feet: P,
    pub finger: P,
    pub hair: Vec<Vec<P>>,
}

/// Options of `draw`.
#[derive(Clone, Debug)]
pub struct Draw<'a> {
    pub lift: f64,
    pub flut: f64,
    /// "loose" (a wild mane past the waist, two locks over the face) or "bun" (pinned bun, four nape locks).
    pub hair: &'a str,
    /// More than 0 draws the translucent avatar: faint fill, bright rim, fading out below the waist.
    pub ghost: f64,
    pub palette: &'a [&'a str],
    /// The pose a few frames earlier (pose_at(f - 4, ...)); the sleeve hems follow it, so cloth lags the arm.
    pub trail: Option<Pose>,
}

impl Default for Draw<'_> {
    fn default() -> Self {
        Draw { lift: 0.5, flut: 0.5, hair: "loose", ghost: 0.0, palette: &BODY, trail: None }
    }
}

struct Canvas {
    lx: Array2<f64>,
    ly: Array2<f64>,
    tone: Array2<i64>,
    union_: Array2<bool>,
    folds: Array2<bool>,
    mw: f64,
    f: f64,
    flut: f64,
    lift: f64,
}

impl Canvas {
    fn sd(&self, a: P, b: P) -> Array2<f64> {
        seg_d(&self.lx.view(), &self.ly.view(), a, b)
    }

    fn put(&mut self, m: &Array2<bool>, base: i64) {
        if m.iter().any(|&v| v) {
            let t = shade(m, base);
            Zip::from(&mut self.tone).and(&t).and(m).for_each(|o, &tv, &mv| {
                if mv {
                    *o = tv;
                }
            });
            Zip::from(&mut self.union_).and(m).for_each(|u, &mv| {
                if mv {
                    *u = true;
                }
            });
        }
    }

    fn set_tone(&mut self, m: &Array2<bool>, v: i64) {
        Zip::from(&mut self.tone).and(m).for_each(|o, &mv| {
            if mv {
                *o = v;
            }
        });
    }

    /// Thin arm with a wide sleeve: one piece of cloth from the shoulder along the arm to the wrist, its opening
    /// falling from the wrist in a curve and trailing back, its hem sagging in a curve back to the armpit, so the
    /// sleeve hangs from the arm with no gap and no straight edge.
    fn arm(&mut self, sh: P, e: P, h: P, base: i64, te: P, th: P) {
        let mw = self.mw;
        let (flut, lift, f) = (self.flut, self.lift, self.f);
        let a1 = self.sd(sh, e);
        let a2 = self.sd(e, h);
        let thin = Array2::from_shape_fn(a1.dim(), |ix| (a1[ix] <= pmax(1.9, mw)) | (a2[ix] <= pmax(1.5, mw)));
        self.put(&thin, base);
        let b = lerp(e, h, 0.85);
        let wv = (f * 0.7 + sh[0]).sin() * flut;
        let tb = lerp(te, th, 0.85); // the hem hangs where the arm was a moment ago
        let mid = lerp(te, th, 0.5);
        let tail = [mid[0] - 9.0 - 10.0 * flut, pmax(mid[1], tb[1]) + 13.0 - 6.0 * lift + 3.0 * wv];
        let pit = [sh[0] - 1.5, sh[1] + 7.0]; // where the hem rejoins the body
        let drop = [b[0] - 1.0 + 2.0 * wv, pmax(b[1], tail[1]) + 2.0]; // the opening falls from the wrist first
        let sag = [(tail[0] + pit[0]) / 2.0 + 2.0, pmax(tail[1], pit[1]) + 4.0 + 2.0 * wv];
        let mut outline = vec![sh, e, b];
        outline.extend(bez(b, drop, tail, 10).into_iter().skip(1));
        let back = bez(tail, sag, pit, 10);
        outline.extend(back[1..back.len() - 1].iter().cloned());
        let cloth = poly_in(&self.lx.view(), &self.ly.view(), &outline);
        let sb = self.sd(sh, b);
        let both = Array2::from_shape_fn(cloth.dim(), |ix| cloth[ix] | (sb[ix] <= 2.6));
        self.put(&both, base - 1);
        // a fold from the elbow down into the hanging cloth, bowed with the sag
        let fold_pts = bez(
            lerp(e, b, 0.35),
            [(e[0] + tail[0]) / 2.0 - 1.0, (e[1] + tail[1]) / 2.0 + 3.0],
            lerp(tail, pit, 0.25),
            8,
        );
        let mut fd = Array2::from_elem(self.lx.dim(), f64::INFINITY);
        for w in fold_pts.windows(2) {
            let d = self.sd(w[0], w[1]);
            Zip::from(&mut fd).and(&d).for_each(|o, &dv| *o = if dv < *o { dv } else { *o });
        }
        let lim = pmax(0.45, mw * 0.5);
        let fm = Array2::from_shape_fn(cloth.dim(), |ix| cloth[ix] & (fd[ix] <= lim));
        self.set_tone(&fm, (base - 2).max(0));
        Zip::from(&mut self.folds).and(&fm).for_each(|o, &mv| {
            if mv {
                *o = true;
            }
        });
    }
}

/// Draw the figure with its feet at `foot`, scale sc, through over(ys, xs, rgb, a). Returns world key points
/// (head, neck, hip, feet, finger, hair polylines) and, for a ghost, its inner mask.
pub fn draw(over: &mut Over, shape: (usize, usize), foot: P, sc: f64, pose: Pose, f: f64, o: Draw) -> Result<Figure, String> {
    let rgbs: Vec<[f64; 3]> = o.palette.iter().map(|c| hexf(c)).collect::<Result<_, _>>()?;
    let (lift, flut, ghost) = (o.lift, o.flut, o.ghost);
    let (fx, fy) = (foot[0], foot[1]);
    let (sy, sx) = win(shape, fx - 110.0 * sc, fx + 50.0 * sc, fy - 120.0 * sc, fy + 10.0 * sc);
    let mw = 0.6 / sc; // thinnest part stays about one pixel
    let dim = (sy.len(), sx.len());
    let lx = Array2::from_shape_fn(dim, |(_, i)| ((sx.start + i) as f64 - fx) / sc);
    let ly = Array2::from_shape_fn(dim, |(j, _)| ((sy.start + j) as f64 - fy) / sc);
    let mut c = Canvas {
        tone: Array2::from_elem(dim, -1),
        union_: Array2::from_elem(dim, false),
        folds: Array2::from_elem(dim, false), // inner cloth lines: a darker tone, a faint line on a ghost
        lx,
        ly,
        mw,
        f,
        flut,
        lift,
    };
    let strand_of = |c: &Canvas, s0: P, a0: f64, a1: f64, len: f64, w0: f64, w1: f64, wave: &dyn Fn(usize) -> f64, n: usize| {
        strand(&c.lx.view(), &c.ly.view(), s0, a0, a1, len, w0, w1, wave, Strand { n, mw })
    };
    let mut hair_pts: Vec<Vec<P>> = vec![];
    if o.hair == "loose" {
        // a wild loose mane from crown to nape, past the waist, streaming back and up in the qi wind
        for j in 0..7i64 {
            let jf = j as f64;
            let a0 = (84.0 + jf * 5.0).to_radians();
            let a1 = a0 + (55.0 + jf * 9.0).to_radians() * (0.35 + lift);
            let wave = move |k: usize| {
                let kf = k as f64;
                flut * (0.4 * (kf * 0.55 - f * 0.5 + jf * 1.7).sin() + 0.15 * (kf * 1.7 - f * 0.9 + jf).sin())
            };
            let (m, pts) = strand_of(&c, [-1.5 - jf * 0.6, -76.0 + jf * 1.6], a0, a1,
                                     50.0 + ((j * 37) % 23) as f64 + 10.0 * lift, 3.2, 0.5, &wave, 12);
            c.put(&m, if j % 2 != 0 { 1 } else { 2 });
            hair_pts.push(pts);
        }
    } else {
        // four locks from the nape that fall down the back, then curl back as the wind lifts them
        for j in 0..4i64 {
            let jf = j as f64;
            let a0 = (92.0 + jf * 7.0).to_radians();
            let a1 = a0 + (40.0 + jf * 12.0).to_radians() * (0.4 + lift);
            let wave = move |k: usize| 0.35 * flut * (k as f64 * 0.6 - f * 0.45 + jf * 1.3).sin();
            let (m, pts) = strand_of(&c, [-3.6 - jf * 0.4, -70.0 + jf * 1.3], a0, a1,
                                     30.0 + jf * 5.0 + 6.0 * lift, 2.4, 0.6, &wave, 12);
            c.put(&m, if j % 2 != 0 { 1 } else { 2 });
            hair_pts.push(pts);
        }
    }
    // wide robe flaps from the hips and the hem, flapping behind
    for (j, (sx0, sy0, ln, w0)) in [(-5.0, -38.0, 30.0, 5.0), (-7.0, -22.0, 40.0, 6.0), (-9.0, -6.0, 34.0, 6.0)].into_iter().enumerate() {
        let jf = j as f64;
        let a0 = (150.0 - jf * 8.0).to_radians();
        let a1 = a0 + (25.0 + 15.0 * jf).to_radians() * (0.3 + lift);
        let wave = move |k: usize| 0.7 * flut * (k as f64 * 0.8 - f * 0.6 + jf * 2.1).sin();
        let (m, _) = strand_of(&c, [sx0, sy0], a0, a1, ln * (0.8 + 0.4 * flut), w0, 1.2, &wave, 12);
        c.put(&m, if j != 1 { 2 } else { 3 });
    }

    let ((fe, fh), (be, bh)) = pose;
    let ((tfe, tfh), (tbe, tbh)) = o.trail.unwrap_or(pose);

    c.arm([-4.0, -55.0], be, bh, 2, tbe, tbh);

    // robe: rows from sloped shoulders to a fluttering hem that trails back when flying
    let s = Array2::from_shape_fn(dim, |ix| np::clip((c.ly[ix] + 60.0) / 60.0, 0.0, 1.0));
    let hw = np::interp_a(&s, &[0.0, 0.05, 0.14, 0.36, 1.0], &[3.5, 7.5, 8.5, 6.5, 16.0 + 5.0 * flut]);
    let robe = Array2::from_shape_fn(dim, |ix| {
        let (lxv, lyv, sv) = (c.lx[ix], c.ly[ix], s[ix]);
        let cx = -(flut * 12.0 + lift * 4.0) * (sv * sv) + 1.2 * (f * 0.5 + sv * 4.0).sin() * sv * flut * 2.0;
        let hem = 2.4 * (lxv * 0.5 + f * 0.8).sin() * flut;
        (lyv >= -60.0) && (lyv <= hem) && ((lxv - cx).abs() <= hw[ix])
    });
    let neck = Array2::from_shape_fn(dim, |ix| c.sd([0.8, -64.0], [0.5, -58.0])[ix] <= 2.2);
    c.put(&neck, 3); // neck
    c.put(&robe, 2);
    let sash = Array2::from_shape_fn(dim, |ix| robe[ix] && c.ly[ix] >= -41.0 && c.ly[ix] <= -39.0);
    c.set_tone(&sash, 1); // sash
    let lap = c.sd([-2.0, -58.0], [3.5, -43.0]);
    let lapel = Array2::from_shape_fn(dim, |ix| robe[ix] && lap[ix] <= 0.5);
    c.set_tone(&lapel, 3); // lapel
    let head = Array2::from_shape_fn(dim, |ix| np::hypot((c.lx[ix] - 1.5) / 5.4, (c.ly[ix] + 69.0) / 6.6) <= 1.0);
    c.put(&head, 2);
    let face = Array2::from_shape_fn(dim, |ix| head[ix] && c.lx[ix] > 2.5 && c.ly[ix] > -68.0);
    c.set_tone(&face, 3);
    if o.hair == "loose" {
        for j in 0..2i64 {
            // two locks over the face
            let jf = j as f64;
            let wave = move |k: usize| 0.3 * flut * (k as f64 - f * 0.6 + jf).sin();
            let (m, _) = strand_of(&c, [2.5 + jf * 2.2, -75.0], (96.0 - jf * 10.0).to_radians(),
                                   (100.0 + 30.0 * lift).to_radians(), 14.0 + 4.0 * jf, 1.4, 0.4, &wave, 6);
            c.put(&m, 2);
        }
    } else {
        let bun = Array2::from_shape_fn(dim, |ix| np::hypot(c.lx[ix] + 1.5, c.ly[ix] + 76.5) <= 3.2);
        c.put(&bun, 2); // bun
    }
    // front arm, wide sleeve, two-finger sword sign
    c.arm([5.0, -55.0], fe, fh, 3, tfe, tfh);
    let hand = Array2::from_shape_fn(dim, |ix| np::hypot(c.lx[ix] - fh[0], c.ly[ix] - fh[1]) <= 1.7);
    c.put(&hand, 3);
    let dl = np::math_hypot(fh[0] - fe[0], fh[1] - fe[1]);
    let dl = if dl == 0.0 { 1.0 } else { dl };
    let tipl = [fh[0] + (fh[0] - fe[0]) / dl * 4.0, fh[1] + (fh[1] - fe[1]) / dl * 4.0];
    let fd = c.sd(fh, tipl);
    let lim = pmax(0.8, mw * 0.8);
    let finger = Array2::from_shape_fn(dim, |ix| fd[ix] <= lim);
    c.set_tone(&finger, 4);
    Zip::from(&mut c.union_).and(&finger).for_each(|u, &v| *u |= v);
    if o.hair == "bun" {
        let pd = c.sd([-7.5, -78.5], [6.0, -75.2]);
        let pin = Array2::from_shape_fn(dim, |ix| pd[ix] <= pmax(0.6, mw)); // hairpin through the bun
        c.set_tone(&pin, 4);
        Zip::from(&mut c.union_).and(&pin).for_each(|u, &v| *u |= v);
    }

    let (h, w) = dim;
    let mut pix: Vec<(usize, usize)> = vec![];
    for y in 0..h {
        for x in 0..w {
            if c.union_[[y, x]] && c.tone[[y, x]] >= 0 {
                pix.push((y, x));
            }
        }
    }
    let ys: Vec<i64> = pix.iter().map(|&(y, _)| (y + sy.start) as i64).collect();
    let xs: Vec<i64> = pix.iter().map(|&(_, x)| (x + sx.start) as i64).collect();
    let mut mask = None;
    if ghost > 0.0 {
        let un = &c.union_;
        let mut er = un.clone();
        for y in 1..h.saturating_sub(1) {
            for x in 1..w.saturating_sub(1) {
                er[[y, x]] = un[[y, x]] && un[[y - 1, x]] && un[[y + 1, x]] && un[[y, x - 1]] && un[[y, x + 1]];
            }
        }
        let mut rgb = Array2::zeros((pix.len(), 3));
        let mut al = Vec::with_capacity(pix.len());
        let mut inner = Array2::zeros(dim);
        for (n, &(y, x)) in pix.iter().enumerate() {
            let rim = un[[y, x]] && !er[[y, x]];
            let fade = ease_io((-c.ly[[y, x]] - 12.0) / 26.0);
            let fold = c.folds[[y, x]] && !rim;
            let wgt = if rim { 0.75 } else if fold { 0.4 } else { 0.14 };
            al.push(wgt * fade * ghost);
            let t = c.tone[[y, x]];
            let ci = if rim { 4 } else if fold { 3 } else { (t + 1).min(4) } as usize;
            for k in 0..3 {
                rgb[[n, k]] = rgbs[ci][k];
            }
            inner[[y, x]] = fade;
        }
        over(&ys, &xs, &rgb, &al);
        mask = Some(Mask { sy: sy.clone(), sx: sx.clone(), inner });
    } else {
        let mut rgb = Array2::zeros((pix.len(), 3));
        for (n, &(y, x)) in pix.iter().enumerate() {
            let t = c.tone[[y, x]] as usize;
            for k in 0..3 {
                rgb[[n, k]] = rgbs[t][k];
            }
        }
        over(&ys, &xs, &rgb, &vec![1.0; pix.len()]);
    }

    let wd = |p: P| [fx + p[0] * sc, fy + p[1] * sc];
    Ok(Figure {
        mask,
        sc,
        head: wd([1.5, -69.0]),
        neck: wd([0.5, -60.0]),
        hip: wd([0.0, -40.0]),
        feet: wd([0.0, -4.0]),
        finger: wd(tipl),
        hair: hair_pts.iter().map(|pts| pts.iter().step_by(4).map(|&p| wd(p)).collect()).collect(),
    })
}

// ---- light, tuned at sc 0.44 (34 px) for glow max; radii follow the figure's size ----

/// Core and pool along the body, the head, every hair lock, and a wide pool round the hip.
pub fn body_light(l: &mut Array2<f64>, g: &Figure, charge: f64) {
    let u = g.sc / 0.44;
    glow_line(l, g.feet, g.head, 8.0 * u, 0.12);
    glow_line(l, g.feet, g.head, 26.0 * u, 0.08);
    glow(l, g.head[0], g.head[1], 6.0 * u, 0.12, 1.0);
    for pts in &g.hair {
        for w in pts.windows(2) {
            glow_line(l, w[0], w[1], 4.0 * u, 0.08);
        }
    }
    glow(l, g.hip[0], g.hip[1], 100.0 * u, 0.12 * (0.4 + 0.6 * charge), 0.85);
}

/// The sword-sign fingertip: a tight hot core and a pool, both pulsing with jab while it points.
pub fn finger_light(l: &mut Array2<f64>, g: &Figure, point: f64, jab: f64) {
    let u = g.sc / 0.44;
    glow(l, g.finger[0], g.finger[1], 7.0 * u, (0.4 + 0.3 * jab) * point, 1.0);
    glow(l, g.finger[0], g.finger[1], 20.0 * u, (0.15 + 0.15 * jab) * point, 1.0);
}

/// Options of `ellipse_line`.
#[derive(Clone, Debug, Default)]
pub struct Ellipse {
    pub phase: f64,
    /// Some(n): a dashed line, n dashes' worth of turn; None: solid.
    pub dash: Option<f64>,
}

/// An ellipse outline of single pixels in colour col (hex), alpha a, through over.
#[allow(clippy::too_many_arguments)]
pub fn ellipse_line(over: &mut Over, cx: f64, cy: f64, rx: f64, ry: f64, col: &str, a: f64, o: Ellipse) -> Result<(), String> {
    let rgb = hexf(col)?;
    let n = (((2.0 * PI * pmax(rx, 1.0) * 1.6) as i64).max(12)) as usize;
    let mut th: Vec<f64> = np::linspace_ep(0.0, 2.0 * PI, n, false).to_vec();
    if let Some(d) = o.dash.filter(|&d| d != 0.0) {
        th.retain(|&t| (t * d + o.phase).sin() > -0.2);
    }
    let mut pts: Vec<(i64, i64)> = th
        .iter()
        .map(|&t| (np::round(cy + ry * t.sin()) as i64, np::round(cx + rx * t.cos()) as i64))
        .collect();
    pts.sort_unstable();
    pts.dedup();
    let ys: Vec<i64> = pts.iter().map(|p| p.0).collect();
    let xs: Vec<i64> = pts.iter().map(|p| p.1).collect();
    let mut cols = Array2::zeros((pts.len(), 3));
    for i in 0..pts.len() {
        for k in 0..3 {
            cols[[i, k]] = rgb[k];
        }
    }
    over(&ys, &xs, &cols, &vec![a; pts.len()]);
    Ok(())
}

/// The avatar: light inside its mask, a halo ring behind the head, a faint pool and spine, the finger.
pub fn ghost_light(over: &mut Over, l: &mut Array2<f64>, g: &Figure, ghost: f64, f: f64, point: f64) -> Result<(), String> {
    let u = g.sc / 0.56;
    let m = g.mask.as_ref().ok_or("ghost_light: the figure has no mask (draw it with ghost > 0)")?;
    for (j, y) in m.sy.clone().enumerate() {
        for (i, x) in m.sx.clone().enumerate() {
            l[[y, x]] += m.inner[[j, i]] * 0.1 * ghost;
        }
    }
    let (hx, hy) = (g.head[0] - 2.0 * u, g.head[1] - 1.0 * u);
    let r = (12.0 + (f * 0.2).sin()) * u;
    ellipse_line(over, hx, hy, r, r, BODY[4], 0.5 * ghost, Ellipse::default())?;
    glow_ring(l, hx, hy, r, 4.0 * u, 0.3 * ghost, 1.0);
    glow(l, hx, hy, 50.0 * u, 0.07 * ghost, 1.0);
    glow_line(l, g.hip, g.head, 30.0 * u, 0.04 * ghost);
    glow(l, g.finger[0], g.finger[1], 12.0 * u, 0.25 * ghost * point, 1.0);
    Ok(())
}
