//! pt: parts drawn on the canvas that need more than one call: a tilted floor ring cut into its far and near
//! halves (behind and in front of a body), a crystal spike with a sweeping glint, and frost that grows on a
//! body's silhouette (from the edge inward, with icicles under its bottom edges).

use crate::dr::{hash01, Canvas, Rgb, P};
use ndarray::{Array2, Array3};
use std::collections::VecDeque;

/// Which half of a tilted ring to draw: the far half (above the centre on screen, drawn behind a body), the near
/// half (below it, drawn in front), or both.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Half {
    All,
    Far,
    Near,
}

impl Half {
    fn keeps(self, dy: f64) -> bool {
        match self {
            Half::All => true,
            Half::Far => dy < 0.0,
            Half::Near => dy >= 0.0,
        }
    }
}

/// A ring on the floor seen at a tilt: radius `r`, `w` px thick, squashed by `flat` (0.3 to 0.5 for a floor),
/// shaded by depth from `far` (the back edge) to `near` (the front edge). Draw `Half::Far` in the layer behind
/// the body and `Half::Near` in the layer in front (AuraBack and AuraFront), so the body stands inside the ring.
pub fn ring(cv: &mut Canvas, c: P, r: f64, w: f64, flat: f64, half: Half, far: Rgb, near: Rgb, a: f64) {
    if r <= 0.0 || w <= 0.0 || flat <= 0.0 {
        return;
    }
    let (ys, xs) = (0..cv.h, 0..cv.w);
    for yi in ys {
        for xi in xs.clone() {
            let [x, y] = cv.world(yi, xi);
            let (dx, dy) = (x - c[0], y - c[1]);
            let q = (dx * dx + (dy / flat) * (dy / flat)).sqrt();
            if q <= r && q > r - w && half.keeps(dy) {
                let t = (dy / (r * flat) * 0.5 + 0.5).clamp(0.0, 1.0);
                let col = [0, 1, 2].map(|k| far[k] + (near[k] - far[k]) * t);
                cv.px(yi, xi, col, a);
            }
        }
    }
}

/// Light along the same tilted ring and half: k at the ring's middle line, falling off over `spread` px.
pub fn ring_glow(cv: &mut Canvas, c: P, r: f64, flat: f64, spread: f64, k: f64, half: Half) {
    if r <= 0.0 || flat <= 0.0 || spread <= 0.0 || k <= 0.0 {
        return;
    }
    for yi in 0..cv.h {
        for xi in 0..cv.w {
            let [x, y] = cv.world(yi, xi);
            let (dx, dy) = (x - c[0], y - c[1]);
            if !half.keeps(dy) {
                continue;
            }
            let q = (dx * dx + (dy / flat) * (dy / flat)).sqrt();
            let d = (q - r).abs() / spread;
            if d < 1.0 {
                cv.l[[yi, xi]] += (1.0 - d) * (1.0 - d) * k;
            }
        }
    }
}

/// A crystal spike standing on `base` (world px), `h` tall and `w` wide at the foot, its tip leaning `lean` px
/// sideways. The face toward the top-left light is lit, the other dark, a lit ridge between them, a dark rim and a
/// white tip. `glint` (0..1, None for none) is a bright band sweeping up the lit face, bottom to tip, with a
/// small light. `shades` = (rim, dark face, lit face, white).
pub fn crystal(cv: &mut Canvas, base: P, h: f64, w: f64, lean: f64, shades: [Rgb; 4], glint: Option<f64>, a: f64) {
    if h <= 0.0 || w <= 0.0 {
        return;
    }
    let tip = [base[0] + lean, base[1] - h];
    let (bl, br) = ([base[0] - w * 0.5, base[1]], [base[0] + w * 0.5, base[1]]);
    let mid = [base[0] + w * 0.08, base[1] + 0.5]; // the ridge's foot, just right of centre
    cv.poly(&[bl, tip, br], shades[0], a);
    let (ibl, ibr) = ([bl[0] + w * 0.12, bl[1] - 0.6], [br[0] - w * 0.12, br[1] - 0.6]); // inside the rim
    let itip = [tip[0] + (base[0] - tip[0]) * 0.06, tip[1] + 1.2];
    cv.poly(&[ibl, itip, mid], shades[2], a);
    cv.poly(&[mid, itip, ibr], shades[1], a);
    cv.line(mid, itip, shades[2], a);
    cv.put(tip[0], tip[1] + 0.5, shades[3], a);
    if let Some(g) = glint {
        if (0.0..=1.0).contains(&g) {
            // a short band across the lit face at height g, between its left edge and the ridge
            let at = |p0: P, p1: P| [p0[0] + (p1[0] - p0[0]) * g, p0[1] + (p1[1] - p0[1]) * g];
            let (l, r) = (at(ibl, itip), at(mid, itip));
            cv.line(l, r, shades[3], a);
            cv.glow((l[0] + r[0]) * 0.5, (l[1] + r[1]) * 0.5, 3.0, 0.15 * (1.0 - g * 0.5));
        }
    }
}

/// How deep each pixel of `mask` sits inside it: 1 on the silhouette's edge (a 4-neighbour is outside or off the
/// image), 2 one step in, and so on; 0 outside.
pub fn edge_depth(mask: &Array2<bool>) -> Array2<i32> {
    let (h, w) = mask.dim();
    let mut d = Array2::<i32>::zeros((h, w));
    let mut q = VecDeque::new();
    for y in 0..h {
        for x in 0..w {
            if !mask[[y, x]] {
                continue;
            }
            let out = |yy: isize, xx: isize| yy < 0 || xx < 0 || yy >= h as isize || xx >= w as isize || !mask[[yy as usize, xx as usize]];
            let (yi, xi) = (y as isize, x as isize);
            if out(yi - 1, xi) || out(yi + 1, xi) || out(yi, xi - 1) || out(yi, xi + 1) {
                d[[y, x]] = 1;
                q.push_back((y, x));
            }
        }
    }
    while let Some((y, x)) = q.pop_front() {
        let next = d[[y, x]] + 1;
        for (dy, dx) in [(-1isize, 0isize), (1, 0), (0, -1), (0, 1)] {
            let (yy, xx) = (y as isize + dy, x as isize + dx);
            if yy >= 0 && xx >= 0 && (yy as usize) < h && (xx as usize) < w {
                let (yy, xx) = (yy as usize, xx as usize);
                if mask[[yy, xx]] && d[[yy, xx]] == 0 {
                    d[[yy, xx]] = next;
                    q.push_back((yy, xx));
                }
            }
        }
    }
    d
}

/// `frost` options: how many px deep the frost grows at `grow` 1, the share of bottom-edge pixels that hang an
/// icicle, and its longest length in px.
#[derive(Clone, Copy, Debug)]
pub struct Frost {
    pub depth: f64,
    pub icicles: f64,
    pub icicle_len: f64,
}

impl Default for Frost {
    fn default() -> Self {
        Frost { depth: 4.0, icicles: 0.3, icicle_len: 4.0 }
    }
}

/// Frost on a body: `body` is a canvas-sized RGBA image of it (a `Rig::place` frame, or the caster drawn alone),
/// `grow` 0..1 how far it has spread. Frost creeps in from the silhouette's edge as ferns (solid on the edge,
/// broken further in), whitest on the edge; icicles hang under bottom edges that have clear space below. Draw it
/// right after the body, in the same layer. `shades` = (deep ice, ice, white).
pub fn frost(cv: &mut Canvas, seed: u64, body: &Array3<u8>, grow: f64, shades: [Rgb; 3], o: Frost) {
    if grow <= 0.0 {
        return;
    }
    let (h, w, _) = body.dim();
    let (h, w) = (h.min(cv.h), w.min(cv.w));
    let mask = Array2::from_shape_fn((h, w), |(y, x)| body[[y, x, 3]] >= 128);
    let depth = edge_depth(&mask);
    let reach = grow.min(1.0) * o.depth;
    for y in 0..h {
        for x in 0..w {
            let d = depth[[y, x]];
            if d == 0 || d as f64 > reach.ceil() {
                continue;
            }
            let id = (y * w + x) as u64;
            // a fern: keep a pixel when its seeded value beats the depth, so the frost thins toward the inside
            let keep = d == 1 && hash01(seed, id) < 0.85 * grow.min(1.0) + 0.15 || hash01(seed, id) < 0.7 - 0.18 * d as f64;
            if keep && (d as f64) <= reach + 0.5 {
                let c = match d { 1 => shades[2], 2 => shades[1], _ => shades[0] };
                cv.px(y, x, c, 0.9);
            }
        }
    }
    // icicles under bottom edges with room below
    let len = (o.icicle_len * grow.min(1.0)).round() as usize;
    if len == 0 {
        return;
    }
    for y in 0..h.saturating_sub(1) {
        for x in 0..w {
            if !mask[[y, x]] || mask[[y + 1, x]] {
                continue;
            }
            let id = (y * w + x) as u64 + 1_000_003;
            if hash01(seed, id) >= o.icicles {
                continue;
            }
            let n = ((len as f64) * (0.4 + 0.6 * hash01(seed, id + 1))).round().max(1.0) as usize;
            let room = (1..=n).take_while(|k| y + k < h && !mask[[y + k, x]]).count();
            for k in 1..=room {
                let c = if k == room { shades[2] } else { shades[1] };
                cv.px(y + k, x, c, 0.95);
            }
        }
    }
}
