//! ref.py: reverse a detailed reference image into maps to draw from: the object's mask, its edges from the
//! image's derivative, its value levels (how light each part is), and its skeleton. Trace the reference, then
//! paint the maps in the effect's own palette and style (`paint`), and feed `outline` and `spine` to `dv`.
//!
//! `let t = rf::trace("refs/dragon.png", rf::Trace { height: Some(96), ..Default::default() })?;`

use crate::dv;
use crate::img;
use crate::np;
use ndarray::{s, Array2, Array3, ArrayView3};
use std::path::Path;

/// The Sobel kernel, rows top to bottom.
pub const SOBEL: [[f64; 3]; 3] = [[-1.0, 0.0, 1.0], [-2.0, 0.0, 2.0], [-1.0, 0.0, 1.0]];

fn sobel_t() -> [[f64; 3]; 3] {
    let mut t = [[0.0; 3]; 3];
    for j in 0..3 {
        for i in 0..3 {
            t[j][i] = SOBEL[i][j];
        }
    }
    t
}

/// RGBA float 0..1 of the image at path, scaled (box filter, so detail averages) to height or width px.
pub fn load(path: impl AsRef<Path>, height: Option<usize>, width: Option<usize>) -> Result<Array3<f64>, String> {
    let mut im = img::read(path)?;
    let (ih, iw, _) = im.dim();
    let want = |v: Option<usize>| v.filter(|&x| x != 0);
    let (height, width) = (want(height), want(width));
    if height.is_some() || width.is_some() {
        let w = match width {
            Some(w) => w,
            None => np::round(iw as f64 * height.unwrap() as f64 / ih as f64) as usize,
        };
        let h = match height {
            Some(h) => h,
            None => np::round(ih as f64 * width.unwrap() as f64 / iw as f64) as usize,
        };
        im = img::resize_box(&im.view(), w.max(1), h.max(1));
    }
    Ok(im.mapv(|v| v as f64 / 255.0))
}

/// Luminance of an RGB(A) float image: 0.299 r + 0.587 g + 0.114 b.
pub fn luminance(rgb: &ArrayView3<f64>) -> Array2<f64> {
    let (h, w, _) = rgb.dim();
    Array2::from_shape_fn((h, w), |(y, x)| rgb[[y, x, 0]] * 0.299 + rgb[[y, x, 1]] * 0.587 + rgb[[y, x, 2]] * 0.114)
}

/// 3 x 3 correlation of a with k over an edge-padded copy (terms added in k's row-major order from 0).
fn conv3(a: &Array2<f64>, k: &[[f64; 3]; 3]) -> Array2<f64> {
    let p = np::pad(a, &[(1, 1), (1, 1)], np::Pad::Edge);
    let (h, w) = a.dim();
    Array2::from_shape_fn((h, w), |(y, x)| {
        let mut acc = 0.0;
        for j in 0..3 {
            for i in 0..3 {
                acc += k[j][i] * p[[y + j, x + i]];
            }
        }
        acc
    })
}

/// (magnitude, angle) of the luminance derivative, Sobel 3 x 3.
pub fn gradient(lum: &Array2<f64>) -> (Array2<f64>, Array2<f64>) {
    let gx = conv3(lum, &SOBEL);
    let gy = conv3(lum, &sobel_t());
    let mag = np::hypot_a(&gx, &gy);
    let mut ang = Array2::zeros(gx.dim());
    ndarray::Zip::from(&mut ang).and(&gx).and(&gy).for_each(|o, &x, &y| *o = y.atan2(x));
    (mag, ang)
}

/// The object: the alpha when the image has one, else the pixels whose colour differs from the median border
/// colour by more than tol; the largest blob only.
pub fn mask_of(img: &Array3<f64>, tol: f64) -> Array2<bool> {
    let (h, w, _) = img.dim();
    let amin = img.slice(s![.., .., 3]).iter().cloned().fold(f64::INFINITY, |a, b| if b < a { b } else { a });
    let m = if amin < 0.99 {
        img.slice(s![.., .., 3]).mapv(|a| a > 0.5)
    } else {
        let mut border: Vec<[f64; 3]> = vec![];
        let px = |y: usize, x: usize| [img[[y, x, 0]], img[[y, x, 1]], img[[y, x, 2]]];
        border.extend((0..w).map(|x| px(0, x)));
        border.extend((0..w).map(|x| px(h - 1, x)));
        border.extend((0..h).map(|y| px(y, 0)));
        border.extend((0..h).map(|y| px(y, w - 1)));
        let bg: Vec<f64> = (0..3).map(|c| np::median(&border.iter().map(|p| p[c]).collect::<Vec<_>>())).collect();
        Array2::from_shape_fn((h, w), |(y, x)| {
            let mut mx = f64::NEG_INFINITY;
            for c in 0..3 {
                let d = (img[[y, x, c]] - bg[c]).abs();
                if d > mx {
                    mx = d;
                }
            }
            mx > tol
        })
    };
    dv::largest(&m)
}

/// Value levels inside mask m: tones bands split at luminance quantiles, 0 darkest; -1 outside.
pub fn levels(lum: &Array2<f64>, m: &Array2<bool>, tones: usize) -> Array2<i8> {
    let mut out = Array2::from_elem(lum.dim(), -1i8);
    if !m.iter().any(|&v| v) {
        return out;
    }
    let vals: Vec<f64> = lum.iter().zip(m.iter()).filter(|(_, &k)| k).map(|(&v, _)| v).collect();
    let qs = np::linspace(0.0, 1.0, tones + 1);
    let cuts: Vec<f64> = qs.iter().skip(1).take(tones.saturating_sub(1)).map(|&q| np::quantile(&vals, q)).collect();
    ndarray::Zip::from(&mut out).and(lum).and(m).for_each(|o, &v, &k| {
        if k {
            *o = np::searchsorted(&cuts, v, true) as i8;
        }
    });
    out
}

/// The silhouette's rim plus the strongest share of the gradient inside it (the inner lines a pixel artist would
/// ink: jaw, scale rows, the blade's ridge).
pub fn edge_map(grad: &Array2<f64>, m: &Array2<bool>, share: f64) -> Array2<bool> {
    let (h, w) = m.dim();
    let on = np::pad(m, &[(1, 1), (1, 1)], np::Pad::Constant(false));
    let rim = Array2::from_shape_fn((h, w), |(y, x)| {
        m[[y, x]] && !(on[[y, x + 1]] && on[[y + 2, x + 1]] && on[[y + 1, x]] && on[[y + 1, x + 2]])
    });
    let inner_zone = Array2::from_shape_fn((h, w), |(y, x)| m[[y, x]] && !rim[[y, x]]);
    let g: Vec<f64> = grad.iter().zip(inner_zone.iter()).filter(|(_, &k)| k).map(|(&v, _)| v).collect();
    let mut out = rim;
    if !g.is_empty() {
        let q = np::quantile(&g, 1.0 - share);
        for ((y, x), o) in out.indexed_iter_mut() {
            if inner_zone[[y, x]] && grad[[y, x]] >= q {
                *o = true;
            }
        }
    }
    out
}

/// Options of `trace`; the defaults are the Python keyword defaults.
#[derive(Clone, Debug)]
pub struct Trace {
    pub height: Option<usize>,
    pub width: Option<usize>,
    pub tones: usize,
    pub share: f64,
    pub tol: f64,
}

impl Default for Trace {
    fn default() -> Self {
        Trace { height: None, width: None, tones: 4, share: 0.12, tol: 0.12 }
    }
}

/// Every map of one traced reference (the SimpleNamespace `trace` returns).
#[derive(Clone, Debug)]
pub struct Traced {
    /// RGBA float 0..1, (h, w, 4).
    pub img: Array3<f64>,
    /// The object.
    pub mask: Array2<bool>,
    /// Luminance 0..1.
    pub lum: Array2<f64>,
    /// Gradient magnitude (Sobel): where value changes fast.
    pub grad: Array2<f64>,
    /// Gradient angle.
    pub angle: Array2<f64>,
    /// The outline plus inner lines where the gradient is strongest.
    pub edges: Array2<bool>,
    /// Value level 0 (darkest) .. tones - 1 (lightest), -1 outside.
    pub shade: Array2<i8>,
    /// (x, y) points round the silhouette, clockwise (dv::outline).
    pub outline: Array2<f64>,
    /// Centre-line chains, longest first (dv::spine): the skeleton.
    pub spine: Vec<Array2<f64>>,
}

/// Every map of the reference at path, at the target size.
pub fn trace(path: impl AsRef<Path>, o: Trace) -> Result<Traced, String> {
    let img = load(path, o.height, o.width)?;
    let lum = luminance(&img.slice(s![.., .., ..3]));
    let m = mask_of(&img, o.tol);
    let (grad, ang) = gradient(&lum);
    let edges = edge_map(&grad, &m, o.share);
    let shade = levels(&lum, &m, o.tones);
    let outline = dv::outline(&m)?;
    let spine = dv::spine(&m, 3);
    Ok(Traced { img, mask: m, lum, grad, angle: ang, edges, shade, outline, spine })
}

/// Options of `paint`.
#[derive(Clone, Debug)]
pub struct Paint {
    /// Level k becomes ramp_index[k]; None is k itself.
    pub ramp_index: Option<Vec<i64>>,
    /// The index the edges take; None leaves them to the levels.
    pub edge: Option<i8>,
}

impl Default for Paint {
    fn default() -> Self {
        Paint { ramp_index: None, edge: Some(0) }
    }
}

/// A shade map from the traced levels: level k becomes ramp_index[k] (default k), and the edges become index edge
/// (None leaves them to the levels). Draw it with pfx.paint(m, palette).
pub fn paint(t: &Traced, o: Paint) -> Result<Array2<i8>, String> {
    let tones = t.shade.iter().cloned().max().unwrap_or(-1) as i64 + 1;
    let idx: Vec<i8> = match &o.ramp_index {
        Some(r) => r.iter().map(|&v| v as i8).collect(),
        None => (0..tones).map(|v| v as i8).collect(),
    };
    if idx.is_empty() {
        return Err("paint: no levels to index".into());
    }
    let last = idx.len() as i64 - 1;
    let mut m = t.shade.mapv(|v| if v >= 0 { idx[(v as i64).clamp(0, last) as usize] } else { -1 });
    if let Some(e) = o.edge {
        for ((y, x), v) in m.indexed_iter_mut() {
            if t.edges[[y, x]] {
                *v = e;
            }
        }
    }
    Ok(m)
}
