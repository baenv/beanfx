//! dr: the draft runner. A draft fills a `Spec`, draws layers on a `Canvas` in `Effect::draw`, and the runner
//! writes previews, sheets, JSON and page and runs the checks (commands: `look [frames]`, `glow`, `bench <id>`).

use crate::serde_json::{json, Map, Value};
use crate::{cs, ex, fc, img, lt, np, pfx, tg};
use ndarray::{s, Array1, Array2, Array3};
use std::ops::Range;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

pub type Rgb = [f64; 3];
pub type P = [f64; 2];

/// "#rrggbb" to 0..1 RGB. Panics on a malformed hex (a typo in a draft constant).
pub fn hex(s: &str) -> Rgb {
    let v = |i: usize| u8::from_str_radix(&s[i..i + 2], 16).expect("hex colour") as f64 / 255.0;
    [v(1), v(3), v(5)]
}

/// A ramp of hexes as RGB.
pub fn ramp(hexes: &[&str]) -> Vec<Rgb> {
    hexes.iter().map(|h| hex(h)).collect()
}

/// Distance from (x, y) to the segment a..b.
pub fn seg_d(x: f64, y: f64, a: P, b: P) -> f64 {
    let (ex, ey) = (b[0] - a[0], b[1] - a[1]);
    let den = (ex * ex + ey * ey).max(1e-9);
    let h = np::clip(((x - a[0]) * ex + (y - a[1]) * ey) / den, 0.0, 1.0);
    np::hypot(x - a[0] - ex * h, y - a[1] - ey * h)
}

/// A stable 0..1 number from two integers (per-particle traits without a generator).
pub fn hash01(a: u64, b: u64) -> f64 {
    let mut h = 0x9E3779B97F4A7C15u64 ^ a.wrapping_mul(0xBF58476D1CE4E5B9);
    h = (h ^ b).wrapping_mul(0x94D049BB133111EB);
    h ^= h >> 31;
    (h & 0xFFFFFF) as f64 / 0xFFFFFF as f64
}

/// Smooth value noise 0..1 on a unit lattice, seeded.
pub fn vnoise(x: f64, y: f64, seed: u64) -> f64 {
    let (xf, yf) = (x.floor(), y.floor());
    let (tx, ty) = (x - xf, y - yf);
    let (sx, sy) = (tx * tx * (3.0 - 2.0 * tx), ty * ty * (3.0 - 2.0 * ty));
    let at = |i: f64, j: f64| hash01(seed, ((i as i64 as u64) << 32) ^ (j as i64 as u64 & 0xFFFF_FFFF));
    let a = at(xf, yf) + (at(xf + 1.0, yf) - at(xf, yf)) * sx;
    let b = at(xf, yf + 1.0) + (at(xf + 1.0, yf + 1.0) - at(xf, yf + 1.0)) * sx;
    a + (b - a) * sy
}

/// 0..1 share of the way from f0 to f1, clipped.
pub fn span(f: f64, f0: f64, f1: f64) -> f64 {
    np::clip((f - f0) / (f1 - f0), 0.0, 1.0)
}

/// Ease in and out (smoothstep of the clipped value).
pub fn ease_io(s: f64) -> f64 {
    cs::ease_io(s)
}

/// Fast start, slow end.
pub fn ease_out(s: f64) -> f64 {
    let s = np::clip(s, 0.0, 1.0);
    1.0 - (1.0 - s) * (1.0 - s) * (1.0 - s)
}

/// Slow start, fast end.
pub fn ease_in(s: f64) -> f64 {
    let s = np::clip(s, 0.0, 1.0);
    s * s * s
}

/// One layer of one frame: straight-alpha RGBA (0..1) and summed light over a window of the world.
/// World px are the joined sheet's px (y down); the window's top left is (ox, oy).
#[derive(Clone, Debug)]
pub struct Canvas {
    pub w: usize,
    pub h: usize,
    pub ox: f64,
    pub oy: f64,
    pub col: Array3<f64>,
    pub l: Array2<f64>,
}

impl Canvas {
    pub fn new(w: usize, h: usize) -> Canvas {
        Canvas::at(w, h, 0.0, 0.0)
    }

    /// A window of w x h px whose top left is world (ox, oy).
    pub fn at(w: usize, h: usize, ox: f64, oy: f64) -> Canvas {
        Canvas { w, h, ox, oy, col: Array3::zeros((h, w, 4)), l: Array2::zeros((h, w)) }
    }

    /// Pixel index ranges (rows, columns) covering world x0..x1, y0..y1.
    pub fn win(&self, x0: f64, x1: f64, y0: f64, y1: f64) -> (Range<usize>, Range<usize>) {
        let c = |v: f64, n: usize| np::clip(v, 0.0, n as f64) as usize;
        (c((y0 - self.oy).floor(), self.h)..c((y1 - self.oy).ceil() + 1.0, self.h),
         c((x0 - self.ox).floor(), self.w)..c((x1 - self.ox).ceil() + 1.0, self.w))
    }

    /// The world centre of pixel (yi, xi).
    pub fn world(&self, yi: usize, xi: usize) -> P {
        [self.ox + xi as f64 + 0.5, self.oy + yi as f64 + 0.5]
    }

    /// Colour c at alpha a over pixel (yi, xi).
    pub fn px(&mut self, yi: usize, xi: usize, c: Rgb, a: f64) {
        let a = np::clip(a, 0.0, 1.0);
        if a <= 0.0 {
            return;
        }
        let da = self.col[[yi, xi, 3]];
        let oa = a + da * (1.0 - a);
        for k in 0..3 {
            self.col[[yi, xi, k]] = (c[k] * a + self.col[[yi, xi, k]] * da * (1.0 - a)) / oa;
        }
        self.col[[yi, xi, 3]] = oa;
    }

    /// Colour at world (x, y), floored to its pixel.
    pub fn put(&mut self, x: f64, y: f64, c: Rgb, a: f64) {
        let (xi, yi) = ((x - self.ox).floor(), (y - self.oy).floor());
        if xi >= 0.0 && yi >= 0.0 && (xi as usize) < self.w && (yi as usize) < self.h {
            self.px(yi as usize, xi as usize, c, a);
        }
    }

    /// A 1 px line, each pixel once.
    pub fn line(&mut self, p0: P, p1: P, c: Rgb, a: f64) {
        let n = ((p1[0] - p0[0]).abs().max((p1[1] - p0[1]).abs()) as i64 + 1).max(1);
        let mut last = (i64::MIN, i64::MIN);
        for k in 0..=n {
            let t = k as f64 / n as f64;
            let (x, y) = (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t);
            let key = (x.floor() as i64, y.floor() as i64);
            if key != last {
                self.put(x, y, c, a);
                last = key;
            }
        }
    }

    /// A line of width wd with round ends.
    pub fn thick(&mut self, p0: P, p1: P, wd: f64, c: Rgb, a: f64) {
        let r = wd / 2.0;
        let (ys, xs) = self.win(p0[0].min(p1[0]) - r, p0[0].max(p1[0]) + r, p0[1].min(p1[1]) - r, p0[1].max(p1[1]) + r);
        for yi in ys {
            for xi in xs.clone() {
                let [x, y] = self.world(yi, xi);
                if seg_d(x, y, p0, p1) <= r {
                    self.px(yi, xi, c, a);
                }
            }
        }
    }

    /// A filled ellipse (rx, ry); a disc when rx == ry.
    pub fn ellipse(&mut self, cx: f64, cy: f64, rx: f64, ry: f64, c: Rgb, a: f64) {
        if rx <= 0.0 || ry <= 0.0 {
            return;
        }
        let (ys, xs) = self.win(cx - rx, cx + rx, cy - ry, cy + ry);
        for yi in ys {
            for xi in xs.clone() {
                let [x, y] = self.world(yi, xi);
                let (dx, dy) = ((x - cx) / rx, (y - cy) / ry);
                if dx * dx + dy * dy <= 1.0 {
                    self.px(yi, xi, c, a);
                }
            }
        }
    }

    /// A filled polygon (even-odd rule).
    pub fn poly(&mut self, pts: &[P], c: Rgb, a: f64) {
        if pts.len() < 3 {
            return;
        }
        let x0 = pts.iter().map(|p| p[0]).fold(f64::INFINITY, f64::min);
        let x1 = pts.iter().map(|p| p[0]).fold(f64::NEG_INFINITY, f64::max);
        let y0 = pts.iter().map(|p| p[1]).fold(f64::INFINITY, f64::min);
        let y1 = pts.iter().map(|p| p[1]).fold(f64::NEG_INFINITY, f64::max);
        let (ys, xs) = self.win(x0, x1, y0, y1);
        for yi in ys {
            for xi in xs.clone() {
                let [x, y] = self.world(yi, xi);
                let mut inside = false;
                let mut j = pts.len() - 1;
                for i in 0..pts.len() {
                    let (a_, b_) = (pts[i], pts[j]);
                    if (a_[1] > y) != (b_[1] > y) && x < (b_[0] - a_[0]) * (y - a_[1]) / (b_[1] - a_[1]) + a_[0] {
                        inside = !inside;
                    }
                    j = i;
                }
                if inside {
                    self.px(yi, xi, c, a);
                }
            }
        }
    }

    /// A shade map (palette indices, -1 empty) laid over the canvas, its top left at world (x0, y0).
    pub fn paint(&mut self, map: &Array2<i8>, pal: &[Rgb], x0: f64, y0: f64, a: f64) {
        let (mh, mw) = map.dim();
        for j in 0..mh {
            for i in 0..mw {
                let v = map[[j, i]];
                if v >= 0 && (v as usize) < pal.len() {
                    self.put(x0 + i as f64, y0 + j as f64, pal[v as usize], a);
                }
            }
        }
    }

    /// An RGBA u8 image the size of the canvas (a rig frame from `Rig::place`) laid over it.
    pub fn over_img(&mut self, im: &Array3<u8>) {
        let (h, w, _) = im.dim();
        for y in 0..h.min(self.h) {
            for x in 0..w.min(self.w) {
                let a = im[[y, x, 3]] as f64 / 255.0;
                if a > 0.0 {
                    let c = [im[[y, x, 0]] as f64 / 255.0, im[[y, x, 1]] as f64 / 255.0, im[[y, x, 2]] as f64 / 255.0];
                    self.px(y, x, c, a);
                }
            }
        }
    }

    /// Round light, (1 - d)^2 * k inside r.
    pub fn glow(&mut self, x: f64, y: f64, r: f64, k: f64) {
        self.glow_flat(x, y, r, k, 1.0);
    }

    /// Round light squashed vertically by flat (a pool on the ground).
    pub fn glow_flat(&mut self, x: f64, y: f64, r: f64, k: f64, flat: f64) {
        if k <= 0.0 || r <= 0.0 || flat <= 0.0 {
            return;
        }
        let (ys, xs) = self.win(x - r, x + r, y - r * flat, y + r * flat);
        for yi in ys {
            for xi in xs.clone() {
                let [px, py] = self.world(yi, xi);
                let d = np::hypot(px - x, (py - y) / flat) / r;
                if d < 1.0 {
                    self.l[[yi, xi]] += (1.0 - d) * (1.0 - d) * k;
                }
            }
        }
    }

    /// Light along a segment.
    pub fn glow_line(&mut self, p0: P, p1: P, r: f64, k: f64) {
        if k <= 0.0 || r <= 0.0 {
            return;
        }
        let (ys, xs) = self.win(p0[0].min(p1[0]) - r, p0[0].max(p1[0]) + r, p0[1].min(p1[1]) - r, p0[1].max(p1[1]) + r);
        for yi in ys {
            for xi in xs.clone() {
                let [x, y] = self.world(yi, xi);
                let d = seg_d(x, y, p0, p1) / r;
                if d < 1.0 {
                    self.l[[yi, xi]] += (1.0 - d) * (1.0 - d) * k;
                }
            }
        }
    }

    /// Light on a ring of radius big_r and width r, squashed by flat.
    pub fn glow_ring(&mut self, x: f64, y: f64, big_r: f64, r: f64, k: f64, flat: f64) {
        if k <= 0.0 || r <= 0.0 || flat <= 0.0 {
            return;
        }
        let e = big_r + r;
        let (ys, xs) = self.win(x - e, x + e, y - e * flat, y + e * flat);
        for yi in ys {
            for xi in xs.clone() {
                let [px, py] = self.world(yi, xi);
                let d = (np::hypot(px - x, (py - y) / flat) - big_r).abs() / r;
                if d < 1.0 {
                    self.l[[yi, xi]] += (1.0 - d) * (1.0 - d) * k;
                }
            }
        }
    }

    /// A flash born at frame f0 that fades over life frames.
    #[allow(clippy::too_many_arguments)]
    pub fn flash_at(&mut self, f: f64, f0: f64, x: f64, y: f64, r: f64, k: f64, life: f64) {
        let age = f - f0;
        if (0.0..life).contains(&age) {
            let u = (life - age) / life;
            self.glow(x, y, r * (0.55 + 0.45 * u), k * u * u);
        }
    }

    /// The mockup caster (`cs::draw`) at world foot with body light charge; the Figure's points are canvas px.
    #[allow(clippy::too_many_arguments)]
    pub fn caster(&mut self, foot: P, sc: f64, pose: cs::Pose, f: f64, o: cs::Draw, charge: f64) -> Result<cs::Figure, String> {
        let (h, w) = (self.h, self.w);
        let local = [foot[0] - self.ox, foot[1] - self.oy];
        let col = &mut self.col;
        let mut over = |ys: &[i64], xs: &[i64], c: &Array2<f64>, a: &[f64]| {
            for i in 0..ys.len() {
                let (y, x) = (ys[i], xs[i]);
                if y < 0 || x < 0 || y >= h as i64 || x >= w as i64 {
                    continue;
                }
                let (y, x) = (y as usize, x as usize);
                let aa = np::clip(a[i], 0.0, 1.0);
                let da = col[[y, x, 3]];
                let oa = aa + da * (1.0 - aa);
                if oa <= 0.0 {
                    continue;
                }
                for k in 0..3 {
                    col[[y, x, k]] = (c[[i, k]] * aa + col[[y, x, k]] * da * (1.0 - aa)) / oa;
                }
                col[[y, x, 3]] = oa;
            }
        };
        let g = cs::draw(&mut over, (h, w), local, sc, pose, f, o)?;
        if charge > 0.0 {
            cs::body_light(&mut self.l, &g, charge);
        }
        Ok(g)
    }

    /// The canvas as a Cel (colour rounded to u8, light as summed).
    pub fn cel(self) -> Cel {
        let col = self.col.mapv(|v| np::round(np::clip(v, 0.0, 1.0) * 255.0) as u8);
        Cel { col, light: self.l }
    }
}

/// A finished layer: colour (h, w, 4) u8 and summed light (h, w), unclipped.
#[derive(Clone, Debug)]
pub struct Cel {
    pub col: Array3<u8>,
    pub light: Array2<f64>,
}

/// The layer `Effect::draw` is asked for. The sheet is `Effect` alone; previews stack AuraBack, Caster,
/// AuraFront and Effect over the target dummy.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Layer {
    Effect,
    Caster,
    AuraBack,
    AuraFront,
}

/// Aura parts: own sheets round the caster's feet, `frames` long, cell w x h with the feet at pivot.
#[derive(Clone, Debug)]
pub struct Aura {
    pub frames: usize,
    pub w: usize,
    pub h: usize,
    pub pivot: P,
}

/// The brief. `Spec::new` fills the defaults; set the rest by field.
#[derive(Clone, Debug)]
pub struct Spec {
    pub name: String,
    pub w: usize,
    pub h: usize,
    pub n: usize,
    pub fps: f64,
    pub pivot: P,
    pub seed: u64,
    pub looped: bool,
    /// One-shot that ends on a held frame (`end: hold`).
    pub hold: bool,
    pub view: String,
    pub dirs: fc::Meta,
    pub glow: String,
    pub clarity: String,
    /// Light colour ramp, dark to white (pfx::tint).
    pub light_ramp: Vec<String>,
    /// Stepped light for hard retro (lt::steps after the measure); also sets the 48-colour check.
    pub steps: Option<lt::Steps>,
    /// Fade the light to 0 over this many px at the cell edge (0 = off).
    pub edge_fade: f64,
    pub hits: Vec<Value>,
    pub states: Vec<(String, [i64; 2])>,
    pub poses: Vec<Value>,
    pub windup: f64,
    /// The act's target: {"x": px from the pivot along the facing, "react": ...}.
    pub target: Option<Value>,
    /// The dummy's foot in world px for the previews (struck from the left).
    pub dummy: Option<P>,
    /// The caster's foot in world px (aura parts are cut round it).
    pub caster_foot: Option<P>,
    pub aura: Option<Aura>,
    /// More meta.beanfx fields (caster binding, range note, sound).
    pub extra: Map<String, Value>,
    /// The framing check's trim limit (`ex::TRIM`); None when the empty space is wanted (caster room in the cell).
    pub trim: Option<f64>,
    /// Frames on the 4x strips; empty picks 12 evenly.
    pub pick: Vec<usize>,
    /// Frames of the glow takes; empty takes every second frame for 12 each side of the first hit.
    pub takes: Vec<usize>,
}

impl Spec {
    pub fn new(name: &str, w: usize, h: usize, n: usize, fps: f64) -> Spec {
        Spec {
            name: name.into(), w, h, n, fps, pivot: [w as f64 / 2.0, h as f64 / 2.0], seed: 7, looped: false, hold: false,
            view: "side".into(), dirs: fc::Meta::default(), glow: "medium".into(), clarity: "clear".into(),
            light_ramp: vec!["#40306a".into(), "#c0a0ff".into(), "#f0e8ff".into(), "#ffffff".into()],
            steps: None, edge_fade: 0.0, hits: vec![], states: vec![], poses: vec![], windup: 0.0, target: None,
            dummy: None, caster_foot: None, aura: None, extra: Map::new(), trim: Some(ex::TRIM), pick: vec![], takes: vec![],
        }
    }
}

/// A draft's effect. `draw` paints one layer of frame f on cv (sized and placed for the sheet or a part) and
/// returns `Ok(())` untouched for a layer the effect lacks; an `Err` stops the run with exit 2.
pub trait Effect {
    fn spec(&self) -> Spec;
    fn draw(&self, cv: &mut Canvas, f: usize, seed: u64, layer: Layer) -> Result<(), String>;
}

/// `fn main() -> ExitCode { dr::main(&Fx, env!("CARGO_MANIFEST_DIR")) }`: exit 0 clean, 1 on a failed check, 2 on
/// an error.
pub fn main(fx: &dyn Effect, draft_dir: &str) -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match run(fx, Path::new(draft_dir), &args) {
        Ok(code) => ExitCode::from(code),
        Err(e) => {
            eprintln!("error: {e}");
            ExitCode::from(2)
        }
    }
}

struct Ctx<'a> {
    fx: &'a dyn Effect,
    sp: Spec,
}

struct Frame {
    fin: Array3<u8>,
    col: Array3<u8>,
    light: Array3<f64>,
    measured: Array2<f64>,
}

impl Ctx<'_> {
    fn layer(&self, mut cv: Canvas, f: usize, seed: u64, layer: Layer) -> Result<Cel, String> {
        self.fx.draw(&mut cv, f, seed, layer).map_err(|e| format!("frame {f} {layer:?}: {e}"))?;
        Ok(cv.cel())
    }

    fn full(&self, f: usize, seed: u64, layer: Layer) -> Result<Cel, String> {
        self.layer(Canvas::new(self.sp.w, self.sp.h), f, seed, layer)
    }

    /// Light after gain and edge fade (the measured light), then stepped and tinted.
    fn finish_light(&self, l: &Array2<f64>, gain: f64) -> Result<(Array2<f64>, Array3<f64>), String> {
        let (h, w) = l.dim();
        let ef = self.sp.edge_fade;
        let measured = Array2::from_shape_fn((h, w), |(y, x)| {
            let mut v = l[[y, x]] * gain;
            if ef > 0.0 {
                let e = (x as f64).min((w - 1 - x) as f64).min(y as f64).min((h - 1 - y) as f64);
                let k = np::clip(e / ef, 0.0, 1.0);
                v *= k * k;
            }
            np::clip(v, 0.0, 1.0)
        });
        let lc = match self.sp.steps {
            Some(st) => lt::steps(&measured, st),
            None => measured.clone(),
        };
        let l3 = Array3::from_shape_fn((h, w, 3), |(y, x, _)| lc[[y, x]]);
        Ok((measured, pfx::tint(&l3, &self.sp.light_ramp)?))
    }

    fn frame(&self, f: usize, seed: u64, gain: f64) -> Result<Frame, String> {
        let c = self.full(f, seed, Layer::Effect)?;
        let (measured, light) = self.finish_light(&c.light, gain)?;
        Ok(Frame { fin: pfx::composite(&c.col, &light, None)?, col: c.col, light, measured })
    }

    fn preview(&self, f: usize, gain: f64, bg: Option<&str>) -> Result<Array3<u8>, String> {
        let sp = &self.sp;
        let mut cv = Canvas::new(sp.w, sp.h);
        for layer in [Layer::AuraBack, Layer::Caster, Layer::AuraFront, Layer::Effect] {
            self.fx.draw(&mut cv, f, sp.seed, layer).map_err(|e| format!("frame {f} {layer:?}: {e}"))?;
        }
        let c = cv.cel();
        let (_, light) = self.finish_light(&c.light, gain)?;
        let mut out = pfx::composite(&c.col, &light, None)?;
        if let Some(d) = sp.dummy {
            let dummy = tg::draw((sp.h, sp.w), (d[0], d[1]), f as f64, &sp.hits, sp.fps, tg::Draw { facing: -1.0, ..Default::default() })?;
            out = tg::under(&out, &dummy);
        }
        match bg {
            None => Ok(out),
            Some(b) => pfx::composite(&out, &Array3::zeros((sp.h, sp.w, 3)), Some(b)),
        }
    }
}

/// Cover and mean of the light inside the colour's box (None for an empty frame); SKILL.md section 3.
pub fn measure(col: &Array3<u8>, l: &Array2<f64>) -> Option<(f64, f64)> {
    let nz = np::nonzero(&col.slice(s![.., .., 3]).mapv(|a| a > 0));
    if nz[0].is_empty() {
        return None;
    }
    let sp = |v: &[usize]| (*v.iter().min().unwrap(), *v.iter().max().unwrap());
    let ((y0, y1), (x0, x1)) = (sp(&nz[0]), sp(&nz[1]));
    let bx = l.slice(s![y0..=y1, x0..=x1]);
    let lit: Array1<f64> = bx.iter().copied().filter(|&v| v > 0.03).collect();
    Some((lit.len() as f64 / bx.len() as f64, if lit.is_empty() { 0.0 } else { np::mean(&lit) }))
}

/// Writes one part sheet (cast, travel, impact, aura) from its cels; returns its meta.beanfx.parts entry and the
/// check lines. Light is clipped and tinted with ramp.
#[allow(clippy::too_many_arguments)]
pub fn write_part(out: &Path, name: &str, cels: &[Cel], ramp: &[String], fps: f64, pivot: P, looped: bool, anchor: &str,
                  more: Value, glow: &str) -> Result<(Value, Vec<String>), String> {
    let (mut cols, mut lights, mut fins) = (vec![], vec![], vec![]);
    for c in cels {
        let (h, w) = c.light.dim();
        let l3 = Array3::from_shape_fn((h, w, 3), |(y, x, _)| np::clip(c.light[[y, x]], 0.0, 1.0));
        let tinted = pfx::tint(&l3, ramp)?;
        fins.push(pfx::composite(&c.col, &tinted, None)?);
        cols.push(c.col.clone());
        lights.push(tinted);
    }
    let (h, w, _) = cols[0].dim();
    let mut extra = fc::meta("side", w as f64, h as f64, pivot, Default::default())?;
    extra.insert("glow".into(), json!(glow));
    let extra = Value::Object(extra);
    fc::check(&extra)?;
    ex::write(out.join("sheets"), name, &fins, fps, pivot, looped, ex::Write {
        light: Some((&lights).into()), color: Some((&cols).into()), extra: Some(extra), ..Default::default()
    })?;
    let bad = ex::check(&cols, ex::Check { light: Some((&lights).into()), looped, trim: None, ..Default::default() })?
        .into_iter().map(|l| format!("{name}: {l}")).collect();
    let mut e = more.as_object().cloned().unwrap_or_default();
    e.insert("json".into(), json!(format!("{name}.json")));
    let entry = fc::part(&format!("{name}.png"), w as i64, h as i64, cels.len() as i64, fps, pivot, looped, anchor, Some(Value::Object(e)));
    Ok((entry, bad))
}

fn evenly(n: usize, k: usize) -> Vec<usize> {
    if n <= k {
        return (0..n).collect();
    }
    (0..k).map(|i| i * (n - 1) / (k - 1)).collect()
}

fn takes_frames(sp: &Spec) -> Vec<usize> {
    if !sp.takes.is_empty() {
        return sp.takes.clone();
    }
    let mid = sp.hits.first().and_then(|h| h["frame"].as_u64()).map(|v| v as usize).unwrap_or(sp.n / 2);
    (mid.saturating_sub(12)..(mid + 12).min(sp.n)).step_by(2).collect()
}

fn command(ctx: &Ctx, out: &Path, args: &[String]) -> Result<u8, String> {
    let sp = &ctx.sp;
    let dark = "#101018";
    match args[0].as_str() {
        "look" => {
            let mut pick: Vec<usize> = args[1..].iter().filter_map(|a| a.parse().ok()).filter(|&f| f < sp.n).collect();
            if pick.is_empty() {
                pick = evenly(sp.n, 6);
            }
            let ones = pick.iter().map(|&f| ctx.preview(f, 1.0, Some(dark))).collect::<Result<Vec<_>, String>>()?;
            let big: Vec<_> = ones.iter().map(|o| img::zoom(o, 3)).collect();
            img::write(out.join("look.png"), &img::tile(&big, big.len().min(3)).view())?;
            img::write(out.join("look_1x.png"), &img::tile(&ones, ones.len()).view())?;
            println!("look.png {pick:?}");
        }
        "glow" => {
            let fr = takes_frames(sp);
            let mut opts = vec![];
            for (lv, k) in [("subtle", 0.6), ("medium", 1.0), ("strong", 1.3)] {
                opts.push((lv, fr.iter().map(|&f| ctx.preview(f, k, None)).collect::<Result<Vec<_>, String>>()?));
            }
            pfx::takes(out.join("glow_takes.png"), &opts, pfx::Takes { fps: Some(sp.fps / 2.0), ..Default::default() })?;
            println!("glow_takes.png (light gain subtle 0.6, medium 1.0, strong 1.3) frames {fr:?}");
        }
        "bench" => {
            let id = args.get(1).ok_or("bench needs a pixelfx id (out/ref from tools/layers.mjs)")?;
            let r = pfx::load(out.join("ref"), id)?;
            let refs = r.color.iter().zip(&r.light).map(|(c, l)| pfx::composite(c, l, None)).collect::<Result<Vec<_>, String>>()?;
            let ref_fps = r.meta["fps"].as_f64().unwrap_or(24.0);
            let mine = (0..sp.n).map(|f| ctx.frame(f, sp.seed, 1.0).map(|x| x.fin)).collect::<Result<Vec<_>, String>>()?;
            pfx::contact(out.join("bench.png"), &mine, sp.fps, pfx::Contact { r#ref: Some((&refs, ref_fps)),
                         names: [sp.name.clone(), id.clone()], ..Default::default() })?;
            println!("bench.png");
        }
        other => return Err(format!("unknown command {other}: look [frames], glow, bench <id>")),
    }
    Ok(0)
}

/// The runner behind `main`, given the draft folder and the command-line arguments.
pub fn run(fx: &dyn Effect, dir: &Path, args: &[String]) -> Result<u8, String> {
    let ctx = Ctx { fx, sp: fx.spec() };
    let sp = &ctx.sp;
    let name = sp.name.as_str();
    let out = dir.join("out");
    std::fs::create_dir_all(&out).map_err(|e| e.to_string())?;
    if !args.is_empty() {
        return command(&ctx, &out, args);
    }

    let (mut fins, mut cols, mut lights, mut covers, mut means) = (vec![], vec![], vec![], vec![], vec![]);
    for f in 0..sp.n {
        let fr = ctx.frame(f, sp.seed, 1.0)?;
        if let Some((cv, mn)) = measure(&fr.col, &fr.measured) {
            covers.push(cv);
            means.push(mn);
        }
        fins.push(fr.fin);
        cols.push(fr.col);
        lights.push(fr.light);
    }
    let g = lt::glow_level(&sp.glow).ok_or(format!("glow {} is not subtle, medium or strong", sp.glow))?;
    let (cover, mean) = if covers.is_empty() { (0.0, 0.0) } else { (np::median(&covers), np::median(&means)) };
    println!("light: cover {:.0} %, mean {:.3} (glow {} mean {} to {}, clarity {})", 100.0 * cover, mean, sp.glow, g.mean.0, g.mean.1, sp.clarity);
    let ncol: Vec<f64> = fins.iter().map(|x| ex::colours(x) as f64).collect();
    println!("colours: median {} a frame", np::median(&ncol) as i64);

    let previews = (0..sp.n).map(|f| ctx.preview(f, 1.0, None)).collect::<Result<Vec<_>, String>>()?;
    let pick = if sp.pick.is_empty() { evenly(sp.n, 12) } else { sp.pick.clone() };
    for (bg, tag) in [("#101018", "dark"), ("#5a6070", "mid")] {
        let cells = pick.iter().filter(|&&i| i < sp.n)
            .map(|&i| Ok(img::zoom(&pfx::composite(&previews[i], &Array3::zeros((sp.h, sp.w, 3)), Some(bg))?, 4)))
            .collect::<Result<Vec<_>, String>>()?;
        img::write(out.join(format!("{name}_4x_{tag}.png")), &img::tile(&cells, cells.len().min(6)).view())?;
    }
    pfx::strip(&fins, out.join(format!("{name}_1x.png")))?;
    pfx::contact(out.join("contact.png"), &previews, sp.fps, Default::default())?;
    let gif_frames = if sp.hits.is_empty() { previews.clone() } else { ex::hitstop(&previews, &sp.hits, sp.fps)? };
    pfx::gif(&gif_frames, out.join(format!("{name}.gif")), sp.fps, pfx::Gif { scale: 3, ..Default::default() })?;

    let mut bad = vec![];
    let mut extra = fc::meta(&sp.view, sp.w as f64, sp.h as f64, sp.pivot, sp.dirs.clone())?;
    extra.insert("glow".into(), json!(sp.glow));
    extra.insert("clarity".into(), json!(sp.clarity));
    if let (Some(a), Some(foot)) = (&sp.aura, sp.caster_foot) {
        let mut parts = Map::new();
        for (layer, key, lay) in [(Layer::AuraBack, "aura_back", "behind"), (Layer::AuraFront, "aura_front", "front")] {
            let cels: Vec<Cel> = (0..a.frames)
                .map(|f| ctx.layer(Canvas::at(a.w, a.h, foot[0] - a.pivot[0], foot[1] - a.pivot[1]), f, sp.seed, layer))
                .collect::<Result<_, String>>()?;
            let (entry, b) = write_part(&out, &format!("{name}_{key}"), &cels, &sp.light_ramp, sp.fps, a.pivot, false,
                                        "caster", json!({"layer": lay}), &sp.glow)?;
            parts.insert(key.into(), entry);
            bad.extend(b);
        }
        extra.insert("parts".into(), Value::Object(parts));
    }
    for (k, v) in &sp.extra {
        extra.insert(k.clone(), v.clone());
    }
    let extra = Value::Object(extra);
    fc::check(&extra)?;
    let meta = ex::write(out.join("sheets"), name, &fins, sp.fps, sp.pivot, sp.looped, ex::Write {
        light: Some((&lights).into()), color: Some((&cols).into()), states: sp.states.clone(), hits: sp.hits.clone(),
        windup: sp.windup, poses: sp.poses.clone(), target: sp.target.clone(), extra: Some(extra), hold: sp.hold,
        ..Default::default()
    })?;
    if let Some(p) = ex::page(out.join("sheets").join(format!("{name}.json")), Default::default())? {
        println!("page: {}", p.display());
    }

    let src: PathBuf = dir.join("src").join("main.rs");
    bad.extend(ex::check(&cols, ex::Check {
        light: Some((&lights).into()), looped: sp.looped, hold: sp.hold, src: Some(src),
        max_colours: sp.steps.map(|_| 48.0), trim: sp.trim, ..Default::default()
    })?);
    let failed = std::cell::RefCell::new(None);
    bad.extend(ex::check_seeds(|f, sd| match ctx.full(f, sd, Layer::Effect) {
        Ok(c) => c.col,
        Err(e) => {
            failed.borrow_mut().get_or_insert(e);
            Array3::zeros((sp.h, sp.w, 4))
        }
    }, sp.n, &[2, 3, 7], 2)?);
    if let Some(e) = failed.into_inner() {
        return Err(e);
    }
    if let Some(act) = meta.pointer("/meta/beanfx/act") {
        bad.extend(ex::check_act(act, sp.n as i64, sp.fps, sp.looped)?);
    }
    if !covers.is_empty() && !(g.mean.0 <= mean && mean <= g.mean.1 + 0.04) {
        println!("note: light mean {mean:.3} outside the {} row; retune the pools", sp.glow);
    }
    for line in &bad {
        println!("{line}");
    }
    println!("{}", if bad.is_empty() { "checks: clean".to_string() } else { format!("{} problems", bad.len()) });
    Ok(u8::from(!bad.is_empty()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn over_and_glow() {
        let mut cv = Canvas::at(8, 8, 10.0, 20.0);
        cv.put(12.0, 21.0, [1.0, 0.0, 0.0], 1.0);
        assert_eq!(cv.col[[1, 2, 3]], 1.0);
        cv.put(12.0, 21.0, [0.0, 0.0, 1.0], 0.5);
        assert!((cv.col[[1, 2, 0]] - 0.5).abs() < 1e-12 && (cv.col[[1, 2, 2]] - 0.5).abs() < 1e-12);
        cv.glow(14.0, 24.0, 3.0, 0.4);
        assert!(cv.l[[3, 3]] > 0.2 && cv.l[[0, 0]] == 0.0);
        cv.put(-5.0, 0.0, [1.0; 3], 1.0);
    }

    #[test]
    fn helpers_are_stable() {
        assert_eq!(hash01(3, 4), hash01(3, 4));
        assert_ne!(hash01(3, 4), hash01(4, 3));
        assert!((0.0..=1.0).contains(&vnoise(2.5, 7.25, 9)));
        assert_eq!(hex("#ff0000"), [1.0, 0.0, 0.0]);
        assert!((seg_d(0.0, 1.0, [-1.0, 0.0], [1.0, 0.0]) - 1.0).abs() < 1e-12);
        assert_eq!(evenly(5, 12), vec![0, 1, 2, 3, 4]);
        assert_eq!(evenly(100, 3), vec![0, 49, 99]);
    }

    #[test]
    fn poly_fills_inside() {
        let mut cv = Canvas::new(10, 10);
        cv.poly(&[[1.0, 1.0], [9.0, 1.0], [9.0, 9.0], [1.0, 9.0]], [1.0; 3], 1.0);
        assert_eq!(cv.col[[5, 5, 3]], 1.0);
        assert_eq!(cv.col[[0, 0, 3]], 0.0);
    }
}
