#![doc = r#"Fire Attack, the redraw of drafts/hoa_cong: a volley of about 120 fire arrows glints high at the upper left and
rains down on an army camp (tents, a palisade of stakes, a watch tower, banners, crates). Each arrow that sticks
lights a small flame; the burn spreads over cloth and wood, the fires gather into a few big blazes behind the tents
with small licks between them, under one rolling smoke column, then sink to charred frames, glowing stakes and smoke.
No explosion. 240x200, 108 frames at 24 fps, one-shot that holds on the burnt camp, side view, soft style,
glow medium, clarity hazy, no caster.

What changed from hoa_cong (each was a fault in the first draw):
  flames   one flame per 6 px column, all near one height, each with its own dark rim (a row of cones). Now seven
           fire sites sized big, medium or small by what burns there, each a cluster of one main tongue and side
           tongues, summed into one heat field per layer and banded once, so a blaze is one mass with one core.
           The big blazes stand between the palisade and the tents, which read as dark shapes against them.
  smoke    34 puffs each split in three tones along a diagonal and stacked at 34 % alpha, so the seams showed as
           stripes. Now every puff goes into one shade map (kit puffs, lit from the top left, breaking into dots as
           they age) and the map is laid once at one alpha.
  camp     embers and cloth holes picked per pixel from white noise, so the burning camp turned to speckle. Now both
           come from a clumped noise, char keeps three tones, and the burnt frame keeps a warm rim on its lit side.
  framing  the camp sat in the right 60 % of a 320 px cell so the arrows could run in from the left. The arrows now
           fall steeper and the cell is 240 px with the camp near its middle: a quarter less sheet.

States (frames, 24 fps):
  signal    0-11   the first fire arrows come in from afar as glints high at the upper left, the sky glows
  rain      0-58   about 120 fire arrows, each on one path from a far glint into the camp, speeding up
  ignite   20-69   each hit lights a flame; the burn spreads from the hit points, climbing faster than it falls
  blaze    70-91   the big fires roar behind the tents under the smoke column, embers rise
  burndown 92-107  flames sink, charred tent frames and glowing stakes remain under smoke

Run with `cargo run --release -q`.
"#]

use beanfx::ndarray::{s, Array1, Array2, Array3};
use beanfx::serde_json::Value;
use beanfx::{ex, fc, fk, img, lt, np, pfx, rng::default_rng};
use std::cell::RefCell;
use std::collections::HashMap;
use std::f64::consts::PI;
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::rc::Rc;
use std::sync::LazyLock;

const NAME: &str = "hoa_cong_v2";
const W: usize = 240;
const H: usize = 200;
const N: usize = 108;
const FPS: f64 = 24.0;
const SEED: u64 = 7;
const GLOW: &str = "medium";

const SIGNAL0: i64 = 0;
const SIGNAL_N: i64 = 12;
const RAIN0: i64 = SIGNAL0 + SIGNAL_N;
const LAUNCH_LAST: i64 = RAIN0 + 34;
const IGNITE0: i64 = 20;
const BLAZE0: i64 = 70;
const BURN0: i64 = 92;

fn states() -> Vec<(String, [i64; 2])> {
    [("signal", [SIGNAL0, RAIN0 - 1]), ("rain", [SIGNAL0, 58]), ("ignite", [IGNITE0, BLAZE0 - 1]),
     ("blaze", [BLAZE0, BURN0 - 1]), ("burndown", [BURN0, N as i64 - 1])]
        .into_iter().map(|(k, v)| (k.to_string(), v)).collect()
}

const GROUND_Y: f64 = 172.0;
const PIVOT: (f64, f64) = (136.0, 172.0); // the middle of the camp, on the ground
const CAMP: (f64, f64) = (52.0, 216.0);
const APEX_Y: f64 = 16.0;
const SLANT: f64 = 72.0 * (PI / 180.0); // math.radians(72)
const NA: usize = 120;
const ALEN: f64 = 14.0;
const LEAN: f64 = 0.10; // every flame leans this share of its height downwind (to the right)

const FIRE: [&str; 5] = ["#7a1c12", "#c83a1a", "#f07c22", "#ffc852", "#fff3c4"]; // dark flame edge to pale core
const WOOD: [&str; 3] = ["#3a2418", "#7a5030", "#c09058"];
const SMOKE: [&str; 6] = ["#3e3438", "#625656", "#8a7c72", "#5c3226", "#8a4c30", "#b06c3e"]; // 3 tones, then lit
const SMOKE_A: f64 = 0.6; // the one alpha of the whole smoke layer
const CLOTH: [&str; 4] = ["#3a2a1c", "#7a5e3c", "#a8875a", "#d8bb84"];
const TIMBER: [&str; 4] = ["#2a1a10", "#5a3c22", "#8a6438", "#b89060"];
const FLAG: [&str; 4] = ["#4a0c0c", "#8a1a16", "#c83224", "#e86a40"];
const CHAR: [&str; 3] = ["#24140e", "#472818", "#6a3a20"]; // burnt cloth and timber: shadow, body, lit face
const LIGHT_RAMP: [&str; 4] = ["#5a1008", "#e05018", "#ffc060", "#ffffff"];

type Rgb = [f64; 3];

fn hexf(s: &str) -> Rgb {
    let c = |i: usize| i64::from_str_radix(&s[i..i + 2], 16).unwrap() as f64 / 255.0;
    [c(1), c(3), c(5)]
}

fn pal(hexes: &[&str]) -> Vec<Rgb> {
    hexes.iter().map(|c| hexf(c)).collect()
}

static PF: LazyLock<Vec<Rgb>> = LazyLock::new(|| pal(&FIRE));
static PW: LazyLock<Vec<Rgb>> = LazyLock::new(|| pal(&WOOD));
static PC: LazyLock<Vec<Rgb>> = LazyLock::new(|| pal(&CLOTH));
static PT: LazyLock<Vec<Rgb>> = LazyLock::new(|| pal(&TIMBER));
static PG: LazyLock<Vec<Rgb>> = LazyLock::new(|| pal(&FLAG));
static PCH: LazyLock<Vec<Rgb>> = LazyLock::new(|| pal(&CHAR));
static PS: LazyLock<Vec<Rgb>> = LazyLock::new(|| pal(&SMOKE));
const WHITE: Rgb = [1.0; 3];
/// YY, XX = np.mgrid[0:H, 0:W]
static GRID: LazyLock<(Array2<f64>, Array2<f64>)> = LazyLock::new(|| np::mgrid(H, W));
static _GRID: LazyLock<Array2<f64>> = LazyLock::new(|| default_rng(5).random_shape((64, 64)));

fn yy() -> &'static Array2<f64> {
    &GRID.0
}
fn xx() -> &'static Array2<f64> {
    &GRID.1
}

fn ease_io(s: f64) -> f64 {
    let s = np::clip(s, 0.0, 1.0);
    s * s * (3.0 - 2.0 * s)
}

fn eout(s: f64) -> f64 {
    let s = np::clip(s, 0.0, 1.0);
    1.0 - (1.0 - s).powf(3.0) // Python float ** 3 is C pow, so powf, never powi
}

/// The window (ya..yb, xa..xb) of a box, int() truncating toward zero as Python does.
fn _win(x0: f64, x1: f64, y0: f64, y1: f64) -> (usize, usize, usize, usize) {
    let (xa, xb) = ((x0 as i64).max(0), (x1 as i64 + 2).min(W as i64));
    let (ya, yb) = ((y0 as i64).max(0), (y1 as i64 + 2).min(H as i64));
    (ya as usize, yb.max(ya) as usize, xa as usize, xb.max(xa) as usize)
}

fn seg_d(x: f64, y: f64, a: (f64, f64), b: (f64, f64)) -> f64 {
    let (ex_, ey) = (b.0 - a.0, b.1 - a.1);
    let den = ex_ * ex_ + ey * ey;
    let h = np::clip(((x - a.0) * ex_ + (y - a.1) * ey) / if den != 0.0 { den } else { 1e-9 }, 0.0, 1.0);
    np::hypot(x - a.0 - ex_ * h, y - a.1 - ey * h)
}

/// Smooth value noise in 0..1, wrapping every 64 units.
fn vnoise(x: f64, y: f64) -> f64 {
    let (xi, yi) = (x.floor() as i64, y.floor() as i64);
    let (fx, fy) = (x - xi as f64, y - yi as f64);
    let (fx, fy) = (fx * fx * (3.0 - 2.0 * fx), fy * fy * (3.0 - 2.0 * fy));
    let g = &*_GRID;
    let at = |j: i64, i: i64| g[[j.rem_euclid(64) as usize, i.rem_euclid(64) as usize]];
    let (a, b) = (at(yi, xi), at(yi, xi + 1));
    let (c, d) = (at(yi + 1, xi), at(yi + 1, xi + 1));
    (a * (1.0 - fx) + b * fx) * (1.0 - fy) + (c * (1.0 - fx) + d * fx) * fy
}

struct Frame {
    rgb: Array3<f64>,
    a: Array2<f64>,
    l: Array2<f64>,
}

impl Frame {
    fn new() -> Frame {
        Frame { rgb: Array3::zeros((H, W, 3)), a: Array2::zeros((H, W)), l: Array2::zeros((H, W)) }
    }

    /// Lays rgb at alpha a over (ys, xs), one value or one per pixel. All pixels read before any is written,
    /// so a repeated pixel takes its last write, as numpy fancy assignment does.
    fn over(&mut self, ys: &[i64], xs: &[i64], rgb: &[Rgb], a: &[f64]) {
        let mut out = Vec::with_capacity(ys.len());
        for i in 0..ys.len() {
            let (y, x) = (ys[i], xs[i]);
            if !(y >= 0 && y < H as i64 && x >= 0 && x < W as i64) {
                continue;
            }
            let (y, x) = (y as usize, x as usize);
            let (c, a) = (rgb[if rgb.len() == 1 { 0 } else { i }], a[if a.len() == 1 { 0 } else { i }]);
            let a0 = self.a[[y, x]];
            let na = a + a0 * (1.0 - a);
            let k = a0 * (1.0 - a);
            let d = na.max(1e-6);
            let px = [0, 1, 2].map(|j| (c[j] * a + self.rgb[[y, x, j]] * k) / d);
            out.push((y, x, px, na));
        }
        for (y, x, px, na) in out {
            for j in 0..3 {
                self.rgb[[y, x, j]] = px[j];
            }
            self.a[[y, x]] = na;
        }
    }

    fn dot(&mut self, x: f64, y: f64, rgb: Rgb, a: f64) {
        self.over(&[np::round(y) as i64], &[np::round(x) as i64], &[rgb], &[a]);
    }

    fn glow(&mut self, x: f64, y: f64, r: f64, k: f64, flat: f64) {
        if k <= 0.0 || r <= 0.0 {
            return;
        }
        let (ya, yb, xa, xb) = _win(x - r, x + r, y - r * flat, y + r * flat);
        for j in ya..yb {
            for i in xa..xb {
                let d = np::hypot(xx()[[j, i]] - x, (yy()[[j, i]] - y) / flat) / r;
                let q = 1.0 - d.min(1.0);
                self.l[[j, i]] += if d < 1.0 { q * q * k } else { 0.0 };
            }
        }
    }

    fn glow_line(&mut self, p0: (f64, f64), p1: (f64, f64), r: f64, k: f64) {
        if k <= 0.0 {
            return;
        }
        let (ya, yb, xa, xb) = _win(p0.0.min(p1.0) - r, p0.0.max(p1.0) + r, p0.1.min(p1.1) - r, p0.1.max(p1.1) + r);
        for j in ya..yb {
            for i in xa..xb {
                let d = seg_d(xx()[[j, i]], yy()[[j, i]], p0, p1) / r;
                let q = 1.0 - d.min(1.0);
                self.l[[j, i]] += if d < 1.0 { q * q * k } else { 0.0 };
            }
        }
    }

    fn rgba(&self) -> Array3<f64> {
        Array3::from_shape_fn((H, W, 4), |(y, x, c)| if c < 3 { self.rgb[[y, x, c]] } else { self.a[[y, x]] })
    }
}

fn line(fr: &mut Frame, p0: (f64, f64), p1: (f64, f64), c0: Rgb, c1: Rgb, a0: f64, a1: f64) {
    let n = (p1.0 - p0.0).abs().max((p1.1 - p0.1).abs()) as usize + 1;
    let t = np::linspace(0.0, 1.0, n);
    let xs: Vec<i64> = t.iter().map(|&t| np::round(p0.0 + (p1.0 - p0.0) * t) as i64).collect();
    let ys: Vec<i64> = t.iter().map(|&t| np::round(p0.1 + (p1.1 - p0.1) * t) as i64).collect();
    let rgb: Vec<Rgb> = t.iter().map(|&t| [0, 1, 2].map(|j| c0[j] * (1.0 - t) + c1[j] * t)).collect();
    let a: Vec<f64> = t.iter().map(|&t| a0 + (a1 - a0) * t).collect();
    fr.over(&ys, &xs, &rgb, &a);
}

// ---- fire: every tongue adds to one heat field per layer, and the field is banded into tones once ----
fn heat_tones(h: f64) -> usize {
    if h > 0.8 { 4 } else if h > 0.62 { 3 } else if h > 0.44 { 2 } else if h > 0.27 { 1 } else { 0 }
}

/// The keyword arguments of `tongue`.
#[derive(Clone, Copy)]
struct Tongue {
    sway: f64,
    cool: f64,
    fork: f64,
}

impl Default for Tongue {
    fn default() -> Self {
        Tongue { sway: 3.0, cool: 0.0, fork: 0.0 }
    }
}

/// One flame tongue kept where it is hotter than F: hottest low in the middle, its tip leaning downwind, its rim
/// torn by rising noise. fork splits the upper half of a big flame into two tips that trade height.
#[allow(clippy::too_many_arguments)]
fn tongue(big_f: &mut Array2<f64>, cx: f64, by: f64, hgt: f64, hw: f64, f: f64, seed: f64, o: Tongue) {
    if hgt < 1.5 || hw < 0.6 {
        return;
    }
    let Tongue { sway, cool, fork } = o;
    let lean = LEAN * hgt;
    let (ya, yb, xa, xb) = _win(cx - hw * 1.8 - sway, cx + hw * 1.8 + sway + lean, by - hgt * 1.25, by + 1.0);
    let split = 0.18 * (f * 0.3 + seed).sin(); // the gap wanders, so the two tips trade height
    for j in ya..yb {
        for i in xa..xb {
            let (x, y) = (xx()[[j, i]], yy()[[j, i]]);
            let s = (by - y) / hgt;
            let sc = np::clip(s, 0.0, 1.0);
            let axis = cx + sway * (y * 0.09 - f * 0.4 + seed).sin() * sc + lean * sc * sc;
            let w = hw * (1.0 - 0.86 * sc.powf(1.35)) + 0.5;
            let u = (x - axis) / w;
            let n = 0.6 * vnoise(x * 0.09 + seed * 7.0, y * 0.09 + f * 0.6)
                + 0.4 * vnoise(x * 0.23 + seed, y * 0.2 + f * 1.05);
            let mut heat = (1.0 - u.abs()) * (1.1 - 0.62 * sc) + (n - 0.5) * (0.55 + 0.6 * sc)
                - (s - 1.0).max(0.0) * 2.4 - cool;
            heat = heat + 0.08 * np::clip(-u, -1.0, 1.0) * (1.0 - sc); // the pale core sits toward the top left light
            if fork != 0.0 {
                heat = heat - fork * np::clip((sc - 0.45) / 0.4, 0.0, 1.0)
                    * np::clip(1.0 - (u - split).abs() * 3.2, 0.0, 1.0);
            }
            let heat = if y <= by { heat } else { -1.0 };
            let cell = &mut big_f[[j, i]];
            if heat > *cell {
                *cell = heat;
            }
        }
    }
}

/// A fire as one main tongue and its side tongues (dx, height share, width share), each on its own beat.
#[allow(clippy::too_many_arguments)]
fn cluster(big_f: &mut Array2<f64>, cx: f64, by: f64, hgt: f64, hw: f64, f: f64, seed: f64, sides: &[(f64, f64, f64)]) {
    for (k, &(dx, hs, ws)) in sides.iter().enumerate() {
        let beat = 0.82 + 0.18 * (f * 0.55 + seed * 3.1 + k as f64 * 2.3).sin();
        tongue(big_f, cx + dx * hw, by + 1.5, hgt * hs * beat, hw * ws, f, seed + 11.7 * (k + 1) as f64,
               Tongue { sway: 2.0, ..Default::default() });
    }
    tongue(big_f, cx, by, hgt * (0.9 + 0.1 * (f * 0.42 + seed).sin()), hw, f, seed,
           Tongue { sway: 3.0, fork: if hw > 8.0 { 0.9 } else { 0.0 }, ..Default::default() });
}

fn paint_fire(fr: &mut Frame, big_f: &Array2<f64>, a: f64) {
    let (mut ys, mut xs, mut rgb) = (vec![], vec![], vec![]);
    for ((j, i), &v) in big_f.indexed_iter() {
        if v > 0.12 {
            ys.push(j as i64);
            xs.push(i as i64);
            rgb.push(PF[heat_tones(v)]);
        }
    }
    if !ys.is_empty() {
        fr.over(&ys, &xs, &rgb, &[a]);
    }
}

// ---- the camp: material, tone and a clumped noise per pixel (0 none, 1 cloth, 2 timber, 3 crate) ----
const TENTS: [(f64, f64, f64); 4] = [(94.0, 34.0, 30.0), (134.0, 50.0, 44.0), (174.0, 36.0, 32.0), (203.0, 22.0, 22.0)];
const TOWER: (f64, f64) = (62.0, 104.0); // middle x and roof top y of the watch tower
const STAKE_BASE: f64 = 160.0;

struct Camp {
    mat: Array2<i8>,
    tone: Array2<i8>,
    pole: Array2<bool>,
    cn: Array2<f64>, // clumps about 5 px across: holes and embers
    cb: Array2<f64>, // patches about 16 px across: how the blaze fills in
    cy: Vec<usize>,
    cx: Vec<usize>,
    behind: Vec<bool>, // the palisade and the tower stand behind the fires; tents in front
    rim: Array2<bool>,
}

impl Camp {
    /// MAT[m] = mat, TONE[m] = tone, POLE[m] = False over the pixels where tone(X, Y) gives Some.
    fn _paint(&mut self, mat: i8, tone: impl Fn(f64, f64) -> Option<i8>) {
        for ((j, i), m) in self.mat.indexed_iter_mut() {
            if let Some(t) = tone(xx()[[j, i]], yy()[[j, i]]) {
                *m = mat;
                self.tone[[j, i]] = t;
                self.pole[[j, i]] = false;
            }
        }
    }

    fn _build_camp(&mut self) {
        let mut srng = default_rng(3);
        for x0 in np::arange(CAMP.0, CAMP.1 - 2.0, 4.0) {
            // the palisade behind
            let h = 13.0 + srng.uniform(0.0, 5.0);
            let top = STAKE_BASE - h;
            self._paint(2, |x, y| {
                let body = x >= x0 && x < x0 + 3.0 && y >= top && y <= STAKE_BASE;
                let tip = y >= top - 4.0 && y < top && (x - x0 - 1.0).abs() <= (y - top + 4.0) * 0.4;
                (body || tip).then_some(if x == x0 { 3 } else if x == x0 + 2.0 { 1 } else { 2 })
            });
        }
        for ry in [STAKE_BASE - 4.0, STAKE_BASE - 10.0] {
            self._paint(2, |x, y| ((y - ry).abs() < 0.6 && x >= CAMP.0 && x <= CAMP.1 - 2.0).then_some(1));
        }
        let (tx, ty) = TOWER; // the watch tower
        for lx in [tx - 9.0, tx + 8.0] {
            self._paint(2, |x, y| {
                (x >= lx && x < lx + 2.0 && y >= ty + 14.0 && y <= GROUND_Y).then_some(if x == lx { 2 } else { 1 })
            });
        }
        for k in 0..4 {
            // cross braces
            let y0 = ty + 22.0 + (k * 11) as f64;
            self._paint(2, |x, y| {
                let t = np::clip((x - (tx - 9.0)) / 18.0, 0.0, 1.0);
                let yy_ = y0 + if k % 2 != 0 { t * 9.0 } else { (1.0 - t) * 9.0 };
                ((y - yy_).abs() < 0.7 && x >= tx - 9.0 && x <= tx + 9.0).then_some(1)
            });
        }
        self._paint(2, |x, y| {
            (x >= tx - 13.0 && x <= tx + 13.0 && y >= ty + 12.0 && y <= ty + 15.0)
                .then_some(if y == ty + 12.0 { 3 } else { 2 })
        });
        self._paint(2, |x, y| {
            (x >= tx - 12.0 && x <= tx + 12.0 && y >= ty + 7.0 && y < ty + 12.0 && np::pymod((x - tx).abs(), 6.0) < 1.0)
                .then_some(2)
        });
        self._paint(1, |x, y| {
            (y >= ty && y <= ty + 7.0 && (x - tx).abs() <= (y - ty) * 2.0 + 1.0).then_some(if x < tx { 3 } else { 1 })
        });
        for (cx, w, h) in TENTS {
            // tents in front
            self._paint(1, |x, y| {
                let u = (x - cx) / (w / 2.0);
                let roof = GROUND_Y - h * np::clip(1.0 - u.abs(), 0.0, 1.0).powf(1.15);
                if !(u.abs() <= 1.0 && y >= roof && y <= GROUND_Y) {
                    return None;
                }
                let mut tone = if u < 0.0 { 2 } else { 1 };
                if y < roof + 1.2 && u < 0.0 {
                    tone = 3;
                }
                if np::pymod((x - cx).abs(), 7.0) < 1.0 && y > roof + 2.0 {
                    tone = 0;
                }
                if u.abs() < 0.2 && y > GROUND_Y - h * 0.45 && (x - cx).abs() < (y - (GROUND_Y - h * 0.45)) * 0.35 {
                    tone = 0;
                }
                if y > GROUND_Y - 1.5 {
                    tone = 0;
                }
                Some(tone)
            });
            let pm = |x: f64, y: f64| (x - cx).abs() < 0.6 && y >= GROUND_Y - h - 3.0 && y <= GROUND_Y - h + 1.0;
            self._paint(2, |x, y| pm(x, y).then_some(3));
            for ((j, i), p) in self.pole.indexed_iter_mut() {
                if pm(xx()[[j, i]], yy()[[j, i]]) {
                    *p = true;
                }
            }
        }
        for (cx, w, h) in [(112.0, 7.0, 6.0), (154.0, 6.0, 5.0), (186.0, 8.0, 6.0)] {
            // crates
            self._paint(3, |x, y| {
                if !(x >= cx && x < cx + w && y > GROUND_Y - h && y <= GROUND_Y) {
                    return None;
                }
                let mut tone = 2;
                if x == cx || y == GROUND_Y - h + 1.0 {
                    tone = 3;
                }
                if x == cx + w - 1.0 || y == GROUND_Y {
                    tone = 1;
                }
                if ((x - cx) - (y - (GROUND_Y - h)) * w / h).abs() < 0.7 {
                    tone = 0;
                }
                Some(tone)
            });
        }
    }
}

static CAMP_: LazyLock<Camp> = LazyLock::new(|| {
    let noise = |k: f64, ox: f64, oy: f64| Array2::from_shape_fn((H, W), |p| vnoise(xx()[p] * k + ox, yy()[p] * k + oy));
    let mut c = Camp {
        mat: Array2::zeros((H, W)), tone: Array2::zeros((H, W)), pole: Array2::from_elem((H, W), false),
        cn: noise(0.21, 3.0, 9.0), cb: noise(0.06, 17.0, 5.0), cy: vec![], cx: vec![], behind: vec![],
        rim: Array2::from_elem((H, W), false),
    };
    c._build_camp();
    let nz = np::nonzero(&c.mat.mapv(|m| m > 0));
    (c.cy, c.cx) = (nz[0].clone(), nz[1].clone());
    c.behind = c.cy.iter().zip(&c.cx).map(|(&y, &x)| c.mat[[y, x]] == 2 && !c.pole[[y, x]]).collect();
    // the lit rim of the burnt camp: a camp pixel with nothing of the camp up and to its left
    let solid = c.mat.mapv(|m| m > 0);
    let (r1, r2) = (np::roll(&solid, 1, 1), np::roll(&solid, 2, 1));
    let closed = Array2::from_shape_fn((H, W), |p| solid[p] || r1[p] || r2[p]); // the gaps between stakes closed
    let up = np::roll(&closed, 1, 0);
    let up_left = np::roll(&up, 1, 1);
    c.rim = Array2::from_shape_fn((H, W), |p| solid[p] && !up[p] && !up_left[p]);
    c
});

struct Flag {
    pole: (f64, f64),
    top: f64,
    w: f64,
    h: f64,
}

const FLAGS: [Flag; 3] = [
    Flag { pole: (TOWER.0, TOWER.1 + 1.0), top: TOWER.1 - 16.0, w: 11.0, h: 6.0 },
    Flag { pole: (134.0, GROUND_Y - 47.0), top: GROUND_Y - 62.0, w: 11.0, h: 6.0 },
    Flag { pole: (174.0, GROUND_Y - 35.0), top: GROUND_Y - 48.0, w: 9.0, h: 5.0 },
];

/// A fire by what burns there: x and base, the camp span whose burn feeds it, full height and half width, whether
/// it stands behind the tents, and its side tongues (dx in half widths, height share, width share).
struct Site {
    x: f64,
    base: f64,
    span: (usize, usize),
    hgt: f64,
    hw: f64,
    back: bool,
    sides: &'static [(f64, f64, f64)],
}

// three sizes on purpose: two big, three medium, two small
const SITES: [Site; 7] = [
    Site { x: 137.0, base: 162.0, span: (114, 158), hgt: 66.0, hw: 17.0, back: true, // behind the great tent
           sides: &[(-1.1, 0.5, 0.5), (1.05, 0.68, 0.55), (0.3, 0.4, 0.4)] },
    Site { x: 62.0, base: 117.0, span: (50, 76), hgt: 36.0, hw: 7.5, back: false, // the tower cabin: tall and thin
           sides: &[(-1.3, 0.5, 0.6), (1.25, 0.34, 0.55)] },
    Site { x: 92.0, base: 160.0, span: (78, 110), hgt: 38.0, hw: 11.0, back: true, // behind the left tent
           sides: &[(1.1, 0.5, 0.55), (-1.05, 0.36, 0.5)] },
    Site { x: 177.0, base: 160.0, span: (160, 192), hgt: 46.0, hw: 12.0, back: true, // behind the right tent
           sides: &[(-1.1, 0.42, 0.55), (1.05, 0.6, 0.55)] },
    Site { x: 205.0, base: 158.0, span: (194, 214), hgt: 22.0, hw: 6.0, back: true, // the small tent at the end
           sides: &[(-1.1, 0.5, 0.6)] },
    Site { x: 115.0, base: 168.0, span: (108, 122), hgt: 15.0, hw: 4.5, back: false, // the crates in front
           sides: &[(1.3, 0.55, 0.6)] },
    Site { x: 188.0, base: 168.0, span: (182, 196), hgt: 12.0, hw: 4.0, back: false, sides: &[] },
];

struct Arrow {
    t0: f64,
    fly: f64,
    start: (f64, f64),
    end: (f64, f64),
    ang: f64,
    sink: f64,
    ph: f64,
    fh: f64,
    seed: f64,
    onobj: bool,
    burn: f64,
    land: f64,
}

struct Ember {
    t0: f64,
    x: f64,
    y0: f64,
    vy: f64,
    vx: f64,
    ph: f64,
    life: f64,
}

struct Smoke {
    t0: f64,
    x: f64,
    vy: f64,
    vx: f64,
    r0: f64,
    r1: f64,
    wob: f64,
    seed: f64,
}

struct Lick {
    x: f64,
    h: f64,
    hw: f64,
    ph: f64,
    seed: f64,
}

/// The SimpleNamespace that scene() returns.
struct Scene {
    arrows: Vec<Arrow>,
    embers: Vec<Ember>,
    smokes: Vec<Smoke>,
    licks: Vec<Lick>,
    hx: Vec<f64>,
    hy: Vec<f64>,
    hl: Vec<f64>,
}

thread_local! {
    static SCENES: RefCell<HashMap<u64, Rc<Scene>>> = RefCell::new(HashMap::new());
}

/// Everything a seed decides: where and when each arrow lands, the embers, the smoke puffs and the small licks.
fn scene(seed: u64) -> Rc<Scene> {
    if let Some(s) = SCENES.with(|c| c.borrow().get(&seed).cloned()) {
        return s; // @lru_cache
    }
    let s = Rc::new(make_scene(seed));
    SCENES.with(|c| c.borrow_mut().insert(seed, s.clone()));
    s
}

fn make_scene(seed: u64) -> Scene {
    let camp = &*CAMP_;
    let mut rng = default_rng(seed);
    let mut arrows = vec![];
    let mut b = rng.beta_n(1.4, 1.8, NA);
    b.sort_by(|a, b| a.total_cmp(b));
    let launch: Vec<f64> = b.iter().map(|&v| (SIGNAL0 - 1) as f64 + (LAUNCH_LAST - SIGNAL0 + 1) as f64 * v).collect();
    for &t0 in &launch {
        let gx = rng.uniform(CAMP.0 + 2.0, CAMP.1 - 4.0);
        let col: Vec<usize> = (0..H).filter(|&y| camp.mat[[y, gx as usize]] > 0).collect();
        let gy = if !col.is_empty() && rng.random() < 0.75 {
            col[rng.choice(col.len(), 1, Default::default()).unwrap()[0]] as f64 + 0.5
        } else {
            GROUND_Y + rng.uniform(-2.0, 8.0)
        };
        let ang = SLANT + rng.uniform(-0.07, 0.07);
        let mut sy0 = APEX_Y + rng.uniform(-4.0, 8.0);
        let mut dx = (gy - sy0) / ang.tan();
        if gx - dx < 10.0 {
            // enter the cell inside its left margin
            sy0 += (10.0 - (gx - dx)) * ang.tan();
            dx = gx - 10.0;
        }
        let fly = rng.uniform(11.0, 13.0) * (gy - sy0) / (gy - APEX_Y);
        let onobj = !col.is_empty() && gy < GROUND_Y - 0.6;
        let (sink, ph, fh, seed) = (rng.uniform(3.0, 5.0), rng.uniform(0.0, 6.28), rng.uniform(5.0, 8.0), rng.uniform(0.0, 50.0));
        // an arrow in open ground burns out by itself; about one in twelve catches the grass and stays lit
        let burn = if rng.random() < 0.08 { 1e9 } else { rng.uniform(5.0, 12.0) };
        arrows.push(Arrow { t0, fly, start: (gx - dx, sy0), end: (gx, gy), ang, sink, ph, fh, seed, onobj, burn, land: 0.0 });
    }
    for a in &mut arrows {
        a.land = a.t0 + a.fly;
    }
    let big: Vec<&Site> = SITES.iter().filter(|s| s.hgt > 30.0).collect();
    let mut embers = vec![];
    for _ in 0..190 {
        // embers rise off the fires, most off the big ones
        let s = if rng.random() < 0.8 { big[rng.integers1(big.len() as i64) as usize] } else { &SITES[rng.integers1(SITES.len() as i64) as usize] };
        let t0 = rng.uniform(30.0, (N - 8) as f64);
        let x = s.x + rng.normal(0.0, s.hw * 0.9);
        let y0 = s.base - rng.uniform(0.2, 0.9) * s.hgt;
        let (vy, vx, ph, life) = (rng.uniform(0.9, 2.2), rng.uniform(0.0, 1.5), rng.uniform(0.0, 6.28), rng.uniform(10.0, 24.0));
        embers.push(Ember { t0, x, y0, vy, vx, ph, life });
    }
    let smokes = (0..34).map(|k| {
        let t0 = 34.0 + k as f64 * 2.2 + rng.uniform(0.0, 1.5);
        let x = rng.uniform(CAMP.0 + 22.0, CAMP.1 - 26.0);
        let (vy, vx, r0, r1) = (rng.uniform(0.8, 1.2), rng.uniform(0.05, 0.3), rng.uniform(4.0, 6.0), rng.uniform(11.0, 16.0));
        let (wob, seed) = (rng.uniform(0.0, 6.28), rng.uniform(0.0, 40.0));
        Smoke { t0, x, vy, vx, r0, r1, wob, seed }
    }).collect();
    let mut licks = vec![];
    let mut x = CAMP.0 + rng.uniform(5.0, 12.0); // small flames along the palisade, unevenly spaced
    while x < CAMP.1 - 6.0 {
        let (h, hw, ph, seed) = (rng.uniform(5.0, 11.0), rng.uniform(2.0, 3.4), rng.uniform(0.0, 6.28), rng.uniform(0.0, 50.0));
        licks.push(Lick { x, h, hw, ph, seed });
        x += rng.uniform(9.0, 24.0);
    }
    let hx = arrows.iter().map(|a| a.end.0).collect();
    let hy = arrows.iter().map(|a| a.end.1).collect();
    let hl = arrows.iter().map(|a| a.land).collect();
    Scene { arrows, embers, smokes, licks, hx, hy, hl }
}

enum ArrowState {
    Fly((f64, f64), f64),
    Stuck(f64),
}

fn arrow_state(ar: &Arrow, f: f64) -> Option<ArrowState> {
    let t = (f - ar.t0) / ar.fly;
    if t < 0.0 {
        return None;
    }
    if t < 1.0 {
        let u = t * t; // far away it crawls, close up it streaks
        return Some(ArrowState::Fly((ar.start.0 + (ar.end.0 - ar.start.0) * u, ar.start.1 + (ar.end.1 - ar.start.1) * u), u));
    }
    Some(ArrowState::Stuck(f - ar.land))
}

/// Wooden shaft with pale fletching; char darkens the wood toward soot.
fn shaft(fr: &mut Frame, tip: (f64, f64), ang: f64, a: f64, sink: f64, char_: f64) {
    let (ux, uy) = (ang.cos(), ang.sin());
    let tail = (tip.0 - ux * ALEN, tip.1 - uy * ALEN);
    let n = ALEN as usize + 2;
    let t = np::linspace(0.0, 1.0, n);
    let (mut ys, mut xs, mut wood) = (vec![], vec![], vec![]);
    for &t in &t {
        let seg = t * ALEN;
        if seg >= sink {
            let c = if seg < ALEN * 0.5 { PW[2] } else { PW[1] };
            wood.push([0, 1, 2].map(|j| c[j] * (1.0 - char_) + PW[0][j] * char_));
            ys.push(np::round(tip.1 + (tail.1 - tip.1) * t) as i64);
            xs.push(np::round(tip.0 + (tail.0 - tip.0) * t) as i64);
        }
    }
    fr.over(&ys, &xs, &wood, &[a]);
    let (px, py) = (-uy, ux);
    let pale = hexf("#e8dcc0");
    let fl = [0, 1, 2].map(|j| pale[j] * (1.0 - char_) + PW[0][j] * char_);
    for sgn in [-1.0, 1.0] {
        let b0 = (tail.0 + ux * 1.2, tail.1 + uy * 1.2);
        let b1 = (b0.0 - ux * 2.0 + px * sgn, b0.1 - uy * 2.0 + py * sgn);
        line(fr, b0, b1, fl, fl, a * 0.9, a * 0.6);
    }
}

/// A hot head blob, a short flame tongue licking back and up, and three cooling ember dots.
#[allow(clippy::too_many_arguments)]
fn burning_head(fr: &mut Frame, x: f64, y: f64, ux: f64, uy: f64, f: f64, a: f64, seed: f64) {
    let (ya, yb, xa, xb) = _win(x - 3.0, x + 3.0, y - 3.0, y + 3.0);
    let (mut ys, mut xs, mut rgb) = (vec![], vec![], vec![]);
    for j in ya..yb {
        for i in xa..xb {
            let d = np::hypot(xx()[[j, i]] - x, yy()[[j, i]] - y) / 2.4;
            if d <= 1.0 {
                ys.push(j as i64);
                xs.push(i as i64);
                rgb.push(PF[heat_tones(1.05 - 0.8 * d)]);
            }
        }
    }
    fr.over(&ys, &xs, &rgb, &[a]);
    let (bx, by) = (-ux, -uy - 0.55);
    let n = np::math_hypot(bx, by); // math.hypot, not np.hypot
    let (bx, by) = (bx / n, by / n);
    let flick = 1.0 + 0.25 * (f * 1.3 + seed).sin();
    for k in 1..6 {
        let t = k as f64 / 5.0;
        let c = if t < 0.3 { PF[4] } else if t < 0.6 { PF[3] } else { PF[2] };
        fr.dot(x + bx * 6.0 * t * flick + 0.8 * (f * 0.9 + seed + k as f64).sin(), y + by * 6.0 * t * flick, c,
               a * (1.0 - 0.6 * t));
    }
    for k in 1..4 {
        let kf = k as f64;
        fr.dot(x - ux * (7 + 4 * k) as f64 + 0.6 * (seed + kf).sin(), y - uy * (7 + 4 * k) as f64 - 0.5 * kf * kf,
               if k < 3 { PF[2] } else { PF[1] }, a * (0.8 - 0.22 * kf));
    }
    fr.dot(x + ux, y + uy, WHITE, a);
    fr.glow(x, y, 4.0, 0.4 * a, 1.0);
    fr.glow(x, y, 10.0, 0.12 * a, 1.0);
}

/// How hard the camp burns overall: builds with the hits, roars in the blaze, sinks in the burn-down.
fn fire_level(f: f64) -> f64 {
    (0.45 * ease_io((f - IGNITE0 as f64) / 40.0) + 0.55 * ease_io((f - BLAZE0 as f64 + 8.0) / 12.0))
        * (1.0 - 0.7 * ease_io((f - BURN0 as f64) / 14.0))
}

/// Burn per camp pixel: fronts spreading from each landed hit, faster upward, plus the blaze filling in by patch.
fn burn_map(sc: &Scene, f: f64) -> Vec<f64> {
    let c = &*CAMP_;
    let mut b = vec![0.0; c.cy.len()];
    for i in (0..sc.hl.len()).filter(|&i| sc.hl[i] <= f - 1.0) {
        let age = (f - sc.hl[i] - 1.0).min(60.0);
        for p in 0..b.len() {
            let dy = c.cy[p] as f64 - sc.hy[i];
            let dd = np::hypot(c.cx[p] as f64 - sc.hx[i], if dy < 0.0 { dy * 0.55 } else { dy * 1.5 });
            let v = np::clip((age * 0.32 - dd) / 6.0, 0.0, 1.3);
            if v > b[p] {
                b[p] = v;
            }
        }
    }
    let blaze = ease_io((f - BLAZE0 as f64 + 2.0) / 22.0);
    for p in 0..b.len() {
        let v = blaze * (0.55 + 0.9 * c.cb[[c.cy[p], c.cx[p]]]);
        if v > b[p] {
            b[p] = v;
        }
    }
    b
}

/// The camp pixels in sel, charring where the burn reaches: char keeps its faces, cloth opens in clumped holes,
/// a glowing edge runs along the burn front, embers clump on burnt timber, the lit side keeps a warm rim.
fn draw_camp(fr: &mut Frame, f: f64, b: &[f64], sel: impl Fn(usize) -> bool) {
    let c = &*CAMP_;
    let live = (1.0 - ease_io((f - BURN0 as f64 - 4.0) / 12.0)).max(0.0);
    let (mut ys, mut xs, mut rgbs, mut lit) = (vec![], vec![], vec![], vec![]);
    for p in 0..b.len() {
        let (y, x, b) = (c.cy[p], c.cx[p], b[p]);
        let (mat, tone, cn) = (c.mat[[y, x]], c.tone[[y, x]], c.cn[[y, x]]);
        let pal = if mat == 1 { PC[tone as usize] } else { PT[tone as usize] };
        let charred = ease_io((b - 0.45) / 0.5);
        let chc = PCH[(tone as i64 - 1).clamp(0, 2) as usize];
        let mut rgb = [0, 1, 2].map(|j| pal[j] * (1.0 - charred) + chc[j] * charred);
        let front = np::clip(1.0 - (b - 0.22).abs() / 0.2, 0.0, 1.0) * (0.6 + 0.4 * (f * 0.7 + cn * 20.0).sin()) * live;
        let ember = (mat >= 2 && b > 0.7 && cn > 0.8) as i64 as f64 * (0.35 + 0.25 * (f * 0.45 + cn * 30.0).sin()); // dull orange clumps
        let rim = c.rim[[y, x]] && b > 0.6;
        let warm = if rim { 0.75 * (0.35 + 0.65 * live) } else { 0.0 }; // the rim cools to a dull red as the fires sink
        let hot = np::clip(front.max(ember), 0.0, 1.0);
        rgb = [0, 1, 2].map(|j| rgb[j] * (1.0 - warm) + PF[1][j] * warm);
        let (h6, l6) = ((hot > 0.6) as i64 as f64, (hot <= 0.6) as i64 as f64);
        rgb = [0, 1, 2].map(|j| rgb[j] * (1.0 - hot) + (PF[3][j] * h6 + PF[2][j] * l6) * hot);
        let hole = mat == 1 && !c.pole[[y, x]] && b > 0.85 && cn < 0.14 + (b - 0.85).min(0.45) * 0.5;
        if !hole && sel(p) {
            ys.push(y as i64);
            xs.push(x as i64);
            rgbs.push(rgb);
            if hot > 0.2 {
                lit.push((y, x, hot));
            }
        }
    }
    fr.over(&ys, &xs, &rgbs, &[1.0]);
    for (y, x, hot) in lit {
        fr.l[[y, x]] += 0.25 * hot; // np.add.at
    }
}

fn draw_flags(fr: &mut Frame, big_f: &mut Array2<f64>, f: f64, b_at: impl Fn(f64, f64) -> f64) {
    for (j, fl) in FLAGS.iter().enumerate() {
        let jf = j as f64;
        let (px, py) = fl.pole;
        line(fr, (px, py), (px, fl.top), PT[1], PT[2], 1.0, 1.0);
        let burn = b_at(px, py + 2.0) * 1.2;
        let left = fl.w * (1.0 - ease_io((burn - 0.3) / 0.6));
        if left < 1.0 {
            continue;
        }
        let (ya, yb, xa, xb) = _win(px, px + fl.w + 2.0, fl.top - 3.0, fl.top + fl.h + 3.0);
        let (mut ys, mut xs, mut rgb) = (vec![], vec![], vec![]);
        let dim = 1.0 - 0.5 * ease_io((burn - 0.3) / 0.4);
        for y_ in ya..yb {
            for x_ in xa..xb {
                let (x, y) = (xx()[[y_, x_]], yy()[[y_, x_]]);
                let u = (x - px) / fl.w;
                let wave = 1.4 * (u * 5.0 - f * 0.45 + jf).sin() * u;
                let v = y - fl.top - wave;
                if !(x > px && x - px <= left && v >= 0.0 && v <= fl.h * (1.0 - 0.35 * u)) {
                    continue;
                }
                let mut tone = if (u * 5.0 - f * 0.45 + jf + 1.2).sin() > 0.0 { 2 } else { 1 };
                if v < 1.0 {
                    tone = 3;
                }
                let mut c = PG[tone];
                if burn > 0.3 {
                    let edge = (x - px) > left - 2.0;
                    c = if edge { PF[3] } else { c.map(|v| v * dim) };
                }
                ys.push(y_ as i64);
                xs.push(x_ as i64);
                rgb.push(c);
            }
        }
        if burn > 0.3 {
            fr.glow(px + left, fl.top + fl.h * 0.5, 6.0, 0.3, 1.0);
            tongue(big_f, px + left - 1.0, fl.top + fl.h, 6.0 + 3.0 * (f + jf).sin(), 2.2, f, jf * 5.1,
                   Tongue { sway: 1.5, ..Default::default() });
        }
        fr.over(&ys, &xs, &rgb, &[1.0]);
    }
}

/// The smoke column as one shade map at one alpha: kit puffs lit from the top left, the old ones high up drawn first,
/// each breaking into dots as it ages or thins; the puffs just over the fire take the warm tones.
fn draw_smoke(fr: &mut Frame, sc: &Scene, f: f64, lvl: f64) {
    let cx = PIVOT.0;
    let mut m = Array2::<i8>::from_elem((H, W), -1);
    let mut puffs: Vec<[f64; 6]> = vec![];
    for sm in &sc.smokes {
        // gathering toward one column over the great tent
        let t = f - sm.t0;
        if t < 0.0 {
            continue;
        }
        let r = sm.r0 + (sm.r1 - sm.r0) * eout(t / 26.0);
        let x0 = sm.x + (cx - sm.x) * (t / 30.0).min(1.0) * 0.6;
        let y = 134.0 - sm.vy * t;
        let x = x0 + sm.vx * t + 3.0 * (t * 0.15 + sm.wob).sin();
        let k = (t / 4.0).min(1.0) * (1.0 - ease_io((r + 12.0 - y) / 22.0)) * (0.45 + 0.55 * (lvl * 1.6).min(1.0));
        if k > 0.2 {
            puffs.push([y, x, r, k, sm.seed, t]);
        }
    }
    if f >= (BURN0 - 6) as f64 {
        // a late smoke stem off the embers
        for j in 0..10 {
            let t = np::pymod(f - BURN0 as f64 + 6.0 + j as f64 * 3.1, 30.0);
            let (y, r) = (150.0 - t * 1.6, 3.0 + t * 0.32);
            puffs.push([y, cx - 30.0 + ((j * 17) % 70) as f64 + t * 0.2, r, (t / 4.0).min(1.0) * (1.0 - t / 30.0) * 0.9,
                        j as f64 * 1.7, t]);
        }
    }
    puffs.sort_by(|a, b| a.partial_cmp(b).unwrap()); // highest (oldest) first, the young ones over them
    for &[y, x, r, k, seed, t] in &puffs {
        if y - r < 5.0 || x - r < 5.0 || x + r > (W - 6) as f64 {
            continue;
        }
        let brk = 0.6f64.min(((0.75 - k) * 1.1).max((t - 30.0) / 30.0).max(0.0)); // whole while young, dots as it thins
        fk::puff(&mut m, xx(), yy(), x, y, r * (0.6 + 0.4 * (k * 2.0).min(1.0)), &[0, 1, 2],
                 fk::Puff { brk, seed, ph: f * 0.04 });
    }
    let bay = fk::bayer(&m);
    let cut = 126.0 - 14.0 * lvl;
    for (p, v) in m.indexed_iter_mut() {
        if *v >= 0 && yy()[p] > cut - 18.0 * (bay[p] - 0.5) && lvl > 0.2 {
            *v += 3; // lit from below by the fire, with a dithered boundary
        }
    }
    let (mut ys, mut xs, mut rgb) = (vec![], vec![], vec![]);
    for ((j, i), &v) in m.indexed_iter() {
        if v >= 0 {
            ys.push(j as i64);
            xs.push(i as i64);
            rgb.push(PS[v as usize]);
        }
    }
    if !ys.is_empty() {
        fr.over(&ys, &xs, &rgb, &[SMOKE_A]);
    }
}

/// The largest value of BF over a block of rows and columns (ndarray .max()).
fn block_max(bf: &Array2<f64>, rows: std::ops::Range<usize>, cols: std::ops::Range<usize>) -> f64 {
    bf.slice(s![rows, cols]).fold(f64::NEG_INFINITY, |m, &v| if v > m { v } else { m })
}

/// One site's cluster: it grows as the burn reaches its span and roars in the blaze. Returns its height.
fn site_fire(big_f: &mut Array2<f64>, bf: &Array2<f64>, st: &Site, f: f64, k: usize) -> f64 {
    let heat = np::clip(block_max(bf, 0..H, st.span.0..st.span.1), 0.0, 1.0);
    let grow = ease_io((heat - 0.2) / 0.6);
    if grow <= 0.02 {
        return 0.0;
    }
    let roar = ease_io((f - BLAZE0 as f64 + 10.0) / 14.0);
    let sink = 1.0 - 0.85 * ease_io((f - BURN0 as f64) / 13.0);
    let hgt = st.hgt * grow * (0.3 + 0.7 * roar) * sink;
    cluster(big_f, st.x, st.base, hgt, st.hw * (0.7 + 0.3 * roar), f, 3.3 + 7.7 * k as f64, st.sides);
    hgt
}

fn draw(f: usize, seed: u64) -> Frame {
    let sc = scene(seed);
    let camp = &*CAMP_;
    let mut fr = Frame::new();
    let (cx, by) = PIVOT;
    let f = f as f64;
    let lvl = fire_level(f);

    draw_smoke(&mut fr, &sc, f, lvl);

    let b = burn_map(&sc, f);
    let mut bf = Array2::<f64>::zeros((H, W));
    for p in 0..b.len() {
        bf[[camp.cy[p], camp.cx[p]]] = b[p];
    }

    // the fence and tower, then the big fires inside the camp in one heat field, then the tents against them
    draw_camp(&mut fr, f, &b, |p| camp.behind[p]);
    let mut back = Array2::from_elem((H, W), -1.0);
    let mut heights = [0.0; SITES.len()];
    for (k, st) in SITES.iter().enumerate() {
        if st.back {
            heights[k] = site_fire(&mut back, &bf, st, f, k);
        }
    }
    paint_fire(&mut fr, &back, 1.0);
    draw_camp(&mut fr, f, &b, |p| !camp.behind[p]);

    // in front of it: the tower and crate fires, the small licks along the palisade, burning flags and ground fires
    let mut front = Array2::from_elem((H, W), -1.0);
    for (k, st) in SITES.iter().enumerate() {
        if !st.back {
            heights[k] = site_fire(&mut front, &bf, st, f, k);
        }
    }
    draw_flags(&mut fr, &mut front, f, |x, y| {
        block_max(&bf, y as usize..y as usize + 1, (x as i64 - 1).max(0) as usize..x as usize + 3)
    });
    let sink = 1.0 - 0.8 * ease_io((f - BURN0 as f64) / 12.0);
    for lk in &sc.licks {
        let col = bf.slice(s![.., lk.x as usize - 2..lk.x as usize + 3]);
        let rows: Vec<usize> = (0..H).filter(|&r| col.row(r).iter().any(|&v| v > 0.15)).collect();
        if rows.is_empty() {
            continue;
        }
        let heat = np::clip(rows.iter().flat_map(|&r| col.row(r).to_vec()).fold(f64::NEG_INFINITY, f64::max), 0.0, 1.0);
        let beat = 0.5 + 0.5 * (f * 0.33 + lk.ph).sin(); // each lick swells and dies on its own slow beat
        let h = lk.h * heat * (0.35 + 0.65 * beat) * sink;
        let top = rows[0] as f64;
        tongue(&mut front, lk.x, top + 3.0, h, lk.hw, f, lk.seed, Tongue { sway: 1.5, ..Default::default() });
        fr.glow(lk.x, top - h * 0.3, (h * 0.8).max(3.0), 0.1 * heat * sink, 1.0);
    }
    for ar in &sc.arrows {
        let Some(ArrowState::Stuck(age)) = arrow_state(ar, f) else { continue };
        if ar.onobj {
            continue;
        }
        let own = (1.0f64).min((age + 1.0) / 4.0) * (1.0 - ease_io((age - ar.burn) / 8.0)) * sink;
        if own > 0.05 {
            let (x, y) = ar.end;
            tongue(&mut front, x, y + 1.0, ar.fh * own, 2.4, f, ar.seed, Tongue { sway: 1.2, ..Default::default() });
            fr.glow(x, y - 3.0, 6.0, 0.15 * own, 1.0);
        }
    }

    // stuck arrows under the front flames
    for ar in &sc.arrows {
        let Some(ArrowState::Stuck(age)) = arrow_state(ar, f) else { continue };
        let (x, y) = ar.end;
        shaft(&mut fr, (x, y), ar.ang, 1.0, ar.sink, (age / 24.0).min(1.0));
        if age < 3.0 {
            fr.glow(x, y - 2.0, 8.0, 0.35 * (1.0 - age / 3.0), 1.0);
            for jj in 0..3 {
                let a_ = PI + 0.5 + jj as f64 * 0.9 + ar.ph;
                let rr = 2.0 + age * 2.0;
                fr.dot(x + a_.cos() * rr, y - 2.0 + a_.sin() * rr * 0.6, PF[4], 1.0 - age / 3.0);
            }
        }
    }
    paint_fire(&mut fr, &front, 1.0);

    // light on each fire: a tight core low in the flames and a pool round the cluster
    let g = lt::glow_level(GLOW).unwrap();
    for (k, st) in SITES.iter().enumerate() {
        let hgt = heights[k];
        if hgt < 2.0 {
            continue;
        }
        let part = (hgt / st.hgt + 0.25).min(1.0);
        fr.glow(st.x + LEAN * hgt * 0.3, st.base - hgt * 0.3, (hgt * 0.42).max(5.0), 0.42 * part, 1.0);
        fr.glow(st.x + LEAN * hgt * 0.4, st.base - hgt * 0.4, (hgt * 0.42).max(5.0) * g.pool_r,
                0.42 * part * g.pool_k * 0.55, 1.0);
    }

    let sky = ease_io((f + 2.0) / 12.0) * (1.0 - ease_io((f - 40.0) / 20.0));
    fr.glow(64.0, 36.0, 58.0, 0.16 * sky, 0.5);

    for ar in &sc.arrows {
        let Some(ArrowState::Fly(p, u)) = arrow_state(ar, f) else { continue };
        let fade_in = (1.0f64).min((f - ar.t0 + 1.0) / 2.0);
        let (ux, uy) = (ar.ang.cos(), ar.ang.sin());
        if u < 0.2 {
            let tw = 0.5 + 0.5 * (f * 1.3 + ar.ph * 5.0).sin();
            fr.dot(p.0 - ux * 2.0, p.1 - uy * 2.0, PF[2], 0.7 * fade_in);
            fr.dot(p.0, p.1, if tw > 0.5 { PF[4] } else { PF[3] }, fade_in);
            fr.glow(p.0, p.1, 4.0, (0.2 + 0.2 * tw) * fade_in, 1.0);
            continue;
        }
        shaft(&mut fr, (p.0 - ux * 1.5, p.1 - uy * 1.5), ar.ang, fade_in, 0.0, 0.0);
        burning_head(&mut fr, p.0, p.1, ux, uy, f, fade_in, ar.seed);
        let sl_ = (6.0 + 30.0 * u).min((p.1 - 9.0) / uy).min((p.0 - 9.0) / ux).max(4.0);
        fr.glow_line((p.0 - ux * sl_, p.1 - uy * sl_), p, 5.0, 0.1 * fade_in);
    }

    for e in &sc.embers {
        let t = f - e.t0;
        if t < 0.0 || t > e.life || lvl < 0.15 {
            continue;
        }
        let k = (1.0 - t / e.life) * (lvl * 1.5).min(1.0);
        let x = e.x + e.vx * t + 2.5 * (t * 0.35 + e.ph).sin();
        let y = e.y0 - e.vy * t;
        if y < 8.0 || !(8.0 < x && x < (W - 8) as f64) {
            continue;
        }
        let col = if k > 0.7 { PF[4] } else if k > 0.4 { PF[3] } else { PF[2] };
        let vx = e.vx + 0.9 * (t * 0.35 + e.ph).cos();
        line(&mut fr, (x - vx * 1.4, y + e.vy * 1.4), (x, y), PF[2], col, 0.2, (k * 1.8).min(1.0));
        fr.glow(x, y, 3.0, 0.4 * k, 1.0);
        fr.glow(x, y, 7.0, 0.08 * k, 1.0);
    }

    // scene pools (clarity hazy): along the burning camp and a wide warm one above it
    fr.glow_line((CAMP.0 + 12.0, by - 18.0), (CAMP.1 - 14.0, by - 18.0), 30.0, 0.1 * lvl);
    fr.glow(cx - 6.0, by - 52.0, 104.0, 0.04 + 0.1 * lvl, 0.75);
    let rain = ease_io((f - RAIN0 as f64) / 8.0) * (1.0 - ease_io((f - 50.0) / 10.0));
    fr.glow(104.0, 88.0, 96.0, 0.1 * rain, 0.7);
    fr
}

/// Colour (h, w, 4) uint8, light (h, w, 3) float and the summed light L of frame f.
fn render(f: usize, seed: u64) -> (Array3<u8>, Array3<f64>, Array2<f64>) {
    let fr = draw(f, seed);
    let col = fr.rgba().mapv(|v| np::round(np::clip(v, 0.0, 1.0) * 255.0) as u8);
    let l = fr.l.mapv(|v| np::clip(v, 0.0, 1.0));
    let l3 = Array3::from_shape_fn((H, W, 3), |(y, x, _)| l[[y, x]]);
    (col, pfx::tint(&l3, &LIGHT_RAMP).unwrap(), l)
}

fn main() -> ExitCode {
    match run() {
        Ok(code) => ExitCode::from(code),
        Err(e) => {
            eprintln!("{e}");
            ExitCode::from(2)
        }
    }
}

fn run() -> Result<u8, String> {
    let here = Path::new(env!("CARGO_MANIFEST_DIR"));
    let out = here.join("out");
    std::fs::create_dir_all(&out).map_err(|e| e.to_string())?;
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.first().map(String::as_str) == Some("look") {
        // a few frames at 4x on the dark ground, while drawing
        let mut pick: Vec<usize> = args[1..].iter().map(|a| a.parse().unwrap()).collect();
        if pick.is_empty() {
            pick = vec![30, 50, 66, 82, 96, 107];
        }
        let rows = pick.iter().map(|&f| {
            let (c, l, _) = render(f, SEED);
            Ok(img::zoom(&pfx::composite(&c, &l, Some("#101018"))?, 4))
        }).collect::<Result<Vec<_>, String>>()?;
        let n = rows.len();
        img::write(out.join("look.png"), &img::tile(&rows, if n < 4 { n } else { 3 }).view())?;
        println!("look.png {pick:?}");
        return Ok(0);
    }

    let (mut cols, mut lights, mut ls, mut finals) = (vec![], vec![], vec![], vec![]);
    for f in 0..N {
        let (c, l, big_l) = render(f, SEED);
        finals.push(pfx::composite(&c, &l, None)?);
        cols.push(c);
        lights.push(l);
        ls.push(big_l);
    }

    let (mut cov, mut mean) = (vec![], vec![]);
    for (c, l) in cols.iter().zip(&ls) {
        let nz = np::nonzero(&c.slice(s![.., .., 3]).mapv(|a| a > 0));
        let (ys, xs) = (&nz[0], &nz[1]);
        let (y0, y1) = (*ys.iter().min().unwrap(), *ys.iter().max().unwrap());
        let (x0, x1) = (*xs.iter().min().unwrap(), *xs.iter().max().unwrap());
        let bx = l.slice(s![y0..=y1, x0..=x1]);
        let lit: Array1<f64> = bx.iter().copied().filter(|&v| v > 0.03).collect();
        cov.push(lit.len() as f64 / bx.len() as f64);
        mean.push(if lit.is_empty() { 0.0 } else { np::mean(&lit) });
    }
    let g = lt::glow_level(GLOW).unwrap();
    let (lo, hi) = g.mean;
    println!("light: cover {:.0} %, mean {:.3} ({GLOW} mean {lo} to {hi}, hazy cover 40 to 80 %)",
             100.0 * np::median(&cov), np::median(&mean));
    let ncol: Vec<f64> = finals.iter().map(|x| ex::colours(x) as f64).collect();
    println!("colours: median {} a frame (soft style, smooth light)", np::median(&ncol) as i64);
    let fr = ex::framing(&cols)?.ok_or("framing: no colour")?;
    println!("framing: the drawing sits in x {}..{}, y {}..{} of {W}x{H}, {:.0} % to trim; {:.0} MB decoded",
             fr.x0, fr.x1, fr.y0, fr.y1, 100.0 * fr.trim, ex::memory_mb(&cols, true));

    let pick = [6, 18, 26, 34, 44, 54, 62, 70, 80, 90, 100, 107];
    for (bg, tag) in [("#101018", "dark"), ("#5a6070", "mid")] {
        let cells = pick.iter().map(|&i| Ok(img::zoom(&pfx::composite(&cols[i], &lights[i], Some(bg))?, 4)))
            .collect::<Result<Vec<_>, String>>()?;
        img::write(out.join(format!("{NAME}_4x_{tag}.png")), &img::tile(&cells, 3).view())?;
    }
    pfx::strip(&finals, out.join(format!("{NAME}_1x.png")))?;
    pfx::contact(out.join("contact.png"), &finals, FPS, Default::default())?;
    pfx::gif(&finals, out.join(format!("{NAME}.gif")), FPS, pfx::Gif { scale: 3, ..Default::default() })?;

    let mut extra = fc::meta("side", W as f64, H as f64, [PIVOT.0, PIVOT.1], Default::default())?;
    extra.insert("glow".into(), Value::from(GLOW));
    let extra = Value::Object(extra);
    fc::check(&extra)?;
    ex::write(out.join("sheets"), NAME, &finals, FPS, [PIVOT.0, PIVOT.1], false, ex::Write {
        light: Some((&lights).into()), color: Some((&cols).into()), states: states(), hold: true, extra: Some(extra),
        ..Default::default()
    })?;
    ex::page(out.join("sheets").join(format!("{NAME}.json")), Default::default())?;

    let src = PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/src/main.rs"));
    let mut bad = ex::check(&cols, ex::Check { light: Some((&lights).into()), looped: false, src: Some(src), hold: true,
                                                ..Default::default() })?; // the burnt camp stays: end "hold"
    bad.extend(ex::check_seeds(|f, sd| render(f, sd).0, N, &[2, 3, 7], 2)?);
    let (mm, mc) = (np::median(&mean), np::median(&cov));
    if !(lo <= mm && mm <= hi && 0.4 <= mc && mc <= 0.8) {
        bad.push(format!("light outside the {GLOW} and hazy rows"));
    }
    for line_ in &bad {
        println!("{line_}");
    }
    if bad.is_empty() {
        println!("checks: clean");
    } else {
        println!("{} problems", bad.len());
    }
    Ok(if bad.is_empty() { 0 } else { 1 })
}
