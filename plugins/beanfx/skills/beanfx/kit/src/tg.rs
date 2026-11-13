//! target.py: a straw training dummy for previews. It stands where a blow lands and reacts to the act's hits, so a
//! strike can be judged with a body taking it. Preview only; the exported sheet stays the effect alone.
//!
//! `tg::draw((H, W), foot, f, &hits, FPS, Draw::default())` gives the dummy alone at frame f; `tg::under(&effect,
//! &img)` puts it behind the effect. foot is the dummy's base in px (x, y). facing -1 means the blow comes from the
//! left and pushes it right. hits are `ex::hit` objects; each reacts by its `react`: flinch (a short tilt),
//! stagger (a wobble that rings down), knockback (a slide back by `push` px with a tilt) or launch (lifted and
//! dropped back). The contact frame flashes it white for the hit's `flash` s (one frame without it), then one
//! frame at half; `dir` turns the knockback.

use crate::color;
use crate::np;
use ndarray::{Array2, Array3, Zip};
use serde_json::Value;

/// shadow, base, lit
pub const POST: [&str; 3] = ["#3a2416", "#6b4428", "#93653c"];
pub const STRAW: [&str; 3] = ["#7a5a24", "#b8913e", "#e3c46a"];
pub const ROPE: &str = "#4a3418";
pub const FLASH: [u8; 3] = [255, 250, 236];
/// px, the stock size beside a 24 px wide body.
pub const HEIGHT: f64 = 38.0;

fn num(v: &Value, key: &str) -> Option<f64> {
    v.get(key).and_then(|x| x.as_f64())
}

/// (dx, dy, tilt radians, flash 0..1) of the dummy at frame f, summed over the hits so far.
pub fn reaction(f: f64, hits: &[Value], fps: f64) -> (f64, f64, f64, f64) {
    let (mut dx, mut dy, mut tilt, mut flash) = (0.0f64, 0.0f64, 0.0f64, 0.0f64);
    for h in hits {
        let frame = num(h, "frame").unwrap_or(0.0);
        let dt = (f - frame) / fps;
        if dt < 0.0 {
            continue;
        }
        let push = match num(h, "push") {
            Some(p) if p != 0.0 => p,
            _ => 3.0,
        };
        let kind = h.get("react").and_then(|v| v.as_str()).unwrap_or("flinch");
        let lit = match num(h, "flash") {
            Some(fl) => np::round(fl * fps).max(1.0),
            None => 1.0,
        }; // frames fully white, then one at half
        let k = f - frame;
        if k <= lit {
            let v = if k < lit { 1.0 } else { 0.5 };
            if v > flash {
                flash = v;
            }
        }
        let a = num(h, "dir").unwrap_or(0.0).to_radians();
        let (ux, uy) = (a.cos().abs(), a.sin()); // away from the blow, and down (+) or up (-) along it
        match kind {
            "flinch" => tilt += 0.18 * (-dt * 10.0).exp(),
            "stagger" => tilt += 0.25 * (-dt * 4.0).exp() * (dt * 22.0).cos(),
            "knockback" => {
                dx += push * ux * (1.0 - (-dt * 12.0).exp());
                let lift = push * uy * (1.0 - (-dt * 12.0).exp()); // a rising blow lifts; the ground stops a falling one
                dy += if lift < 0.0 { lift } else { 0.0 };
                tilt += 0.3 * (-dt * 6.0).exp() * (dt * 14.0).cos();
            }
            "launch" => {
                let up = if dt / 0.35 < 1.0 { dt / 0.35 } else { 1.0 };
                dy -= if dt < 0.35 { push * 2.5 * (std::f64::consts::PI * up).sin() } else { 0.0 };
                tilt += 0.4 * (-dt * 5.0).exp();
            }
            _ => {}
        }
    }
    (dx, dy, tilt, flash)
}

/// Options of `draw`.
#[derive(Clone, Debug)]
pub struct Draw {
    /// -1: the blow comes from the left.
    pub facing: f64,
    /// The dummy's height in px (HEIGHT is the stock size).
    pub height: f64,
}

impl Default for Draw {
    fn default() -> Self {
        Draw { facing: -1.0, height: HEIGHT }
    }
}

/// The dummy alone at frame f as an (h, w, 4) uint8 frame.
pub fn draw(shape: (usize, usize), foot: (f64, f64), f: f64, hits: &[Value], fps: f64, o: Draw) -> Result<Array3<u8>, String> {
    let (hh, ww) = shape;
    let height = o.height;
    let (dx, dy, tilt, flash) = reaction(f, hits, fps);
    let s = -o.facing; // pushed away from the blow
    let (bx, by) = (foot.0 + s * dx, foot.1 + dy);
    let a = -s * tilt; // tilt the top away from the blow
    let (ca, sa) = (a.cos(), a.sin());
    let k = height / HEIGHT;
    let mut img = Array3::<u8>::zeros((hh, ww, 4));
    let hex = |c: &str| color::rgb(c);
    let post_c = [hex(POST[0])?, hex(POST[1])?, hex(POST[2])?];
    let straw_c = [hex(STRAW[0])?, hex(STRAW[1])?, hex(STRAW[2])?];
    let rope_c = hex(ROPE)?;
    let uv = |y: usize, x: usize| {
        let (xs, ys) = (x as f64 + 0.5, y as f64 + 0.5);
        let u = (xs - bx) * ca + (ys - by) * sa; // across
        let v = -(xs - bx) * sa + (ys - by) * ca; // up is negative
        (u, v)
    };
    let set = |img: &mut Array3<u8>, y: usize, x: usize, c: [u8; 3]| {
        img[[y, x, 0]] = c[0];
        img[[y, x, 1]] = c[1];
        img[[y, x, 2]] = c[2];
        img[[y, x, 3]] = 255;
    };
    // paint(post | base | arm, POST), then paint(body | head, STRAW), then the rope
    let mut shapes = Array2::<(bool, bool, bool)>::from_elem((hh, ww), (false, false, false));
    for y in 0..hh {
        for x in 0..ww {
            let (u, v) = uv(y, x);
            let post = (u.abs() < 1.6 * k) && (v < 0.0) && (v > -height);
            let base = (u.abs() < 5.0 * k) && (v < 0.0) && (v > -2.5 * k);
            let arm = ((v + 25.0 * k).abs() < 1.4 * k) && (u.abs() < 10.0 * k);
            let q1 = u / (7.5 * k);
            let q2 = (v + 19.0 * k) / (10.0 * k);
            let body = (q1 * q1 + q2 * q2) < 1.0;
            let r = 4.6 * k;
            let head = (u * u + (v + 33.0 * k) * (v + 33.0 * k)) < r * r;
            let rope = body && (((v + 14.0 * k).abs() < 0.7 * k) || ((v + 24.0 * k).abs() < 0.7 * k));
            shapes[[y, x]] = (post | base | arm, body | head, rope);
        }
    }
    for pass in 0..2 {
        for y in 0..hh {
            for x in 0..ww {
                let sh = shapes[[y, x]];
                if !(if pass == 0 { sh.0 } else { sh.1 }) {
                    continue;
                }
                let (u, v) = uv(y, x);
                let lit = (u < -0.3 * k) && (v < -20.0 * k);
                let tone = if lit { 2 } else if u > 2.0 * k { 0 } else { 1 };
                let c = if pass == 0 { post_c[tone] } else { straw_c[tone] };
                set(&mut img, y, x, c);
            }
        }
    }
    for y in 0..hh {
        for x in 0..ww {
            if shapes[[y, x]].2 {
                set(&mut img, y, x, rope_c);
            }
        }
    }
    if flash != 0.0 {
        for y in 0..hh {
            for x in 0..ww {
                if img[[y, x, 3]] > 0 {
                    for c in 0..3 {
                        let v = img[[y, x, c]] as f64 * (1.0 - 0.7 * flash) + FLASH[c] as f64 * 0.7 * flash;
                        img[[y, x, c]] = v as u8;
                    }
                }
            }
        }
    }
    Ok(img)
}

/// effect (h, w, 4) uint8 over the dummy: the blow reads in front of the body it hits.
pub fn under(effect: &Array3<u8>, dummy: &Array3<u8>) -> Array3<u8> {
    let mut out = Array3::<u8>::zeros(effect.dim());
    Zip::indexed(effect.lanes(ndarray::Axis(2))).for_each(|(y, x), e| {
        let a = e[3] as f64 / 255.0;
        let b = dummy[[y, x, 3]] as f64 / 255.0;
        let alpha = a + b * (1.0 - a);
        let den = if 1e-6 > alpha { 1e-6 } else { alpha };
        for c in 0..3 {
            let rgb = (e[c] as f64 * a + dummy[[y, x, c]] as f64 * b * (1.0 - a)) / den;
            out[[y, x, c]] = np::round(rgb) as u8;
        }
        out[[y, x, 3]] = np::round(alpha * 255.0) as u8;
    });
    out
}
