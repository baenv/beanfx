//! numpy-exact helpers: each gives the bits numpy 2.x gives on the same input (same operation order, numpy's
//! pairwise summation, Python's floor rules, half-even rounding). Scalar forms take f64; `_a` forms map an array.
//! Grids come back as (Y, X), the order of `yy, xx = np.mgrid[0:h, 0:w]`.

use crate::rng::madd;
use ndarray::{Array, Array1, Array2, ArrayBase, Axis, Data, Dimension, IxDyn, Zip};

// ---- scalars ------------------------------------------------------------------------------------------------

/// np.round / Python round(): halves go to the even neighbour.
pub fn round(x: f64) -> f64 {
    x.round_ties_even()
}

/// np.round(x, d) for d >= 0: rint(x * 10**d) / 10**d, numpy's own way (not Python's exact-decimal round).
pub fn round_dec(x: f64, d: i32) -> f64 {
    let f = 10f64.powi(d);
    (x * f).round_ties_even() / f
}

/// np.clip(x, lo, hi): max then min; NaN stays NaN.
pub fn clip(x: f64, lo: f64, hi: f64) -> f64 {
    let v = if x < lo { lo } else { x };
    if v > hi { hi } else { v }
}

/// np.hypot (C hypot, no overflow).
pub fn hypot(a: f64, b: f64) -> f64 {
    a.hypot(b)
}

/// numpy's npy_divmod, which Python's float // and % share: (floor quotient, remainder with the divisor's sign).
pub fn divmod(a: f64, b: f64) -> (f64, f64) {
    if b == 0.0 {
        return (a / b, f64::NAN);
    }
    let mut m = a % b;
    let mut div = (a - m) / b;
    if m != 0.0 {
        if (b < 0.0) != (m < 0.0) {
            m += b;
            div -= 1.0;
        }
    } else {
        m = 0f64.copysign(b);
    }
    let fd = if div != 0.0 {
        let mut f = div.floor();
        if div - f > 0.5 {
            f += 1.0;
        }
        f
    } else {
        0f64.copysign(a / b)
    };
    (fd, m)
}

/// a // b for floats (Python and numpy floor division).
pub fn floordiv(a: f64, b: f64) -> f64 {
    divmod(a, b).0
}

/// a % b for floats with Python's sign rule (the result takes b's sign).
pub fn pymod(a: f64, b: f64) -> f64 {
    divmod(a, b).1
}

/// a // b for ints (floor, Python's rule for negatives).
pub fn floordiv_i(a: i64, b: i64) -> i64 {
    let q = a / b;
    if (a % b != 0) && ((a < 0) != (b < 0)) { q - 1 } else { q }
}

/// a % b for ints with Python's sign rule.
pub fn pymod_i(a: i64, b: i64) -> i64 {
    let r = a % b;
    if r != 0 && ((r < 0) != (b < 0)) { r + b } else { r }
}

// ---- ranges and grids ---------------------------------------------------------------------------------------

/// np.linspace(start, stop, num): start + i * step, the last value set to stop.
pub fn linspace(start: f64, stop: f64, num: usize) -> Array1<f64> {
    linspace_ep(start, stop, num, true)
}

/// np.linspace(start, stop, num, endpoint=endpoint).
pub fn linspace_ep(start: f64, stop: f64, num: usize, endpoint: bool) -> Array1<f64> {
    let div = if endpoint { num.saturating_sub(1) } else { num };
    let delta = stop - start;
    let mut y: Array1<f64> = (0..num).map(|i| i as f64).collect();
    if div > 0 {
        let step = delta / div as f64;
        if step == 0.0 {
            y.mapv_inplace(|v| v / div as f64 * delta);
        } else {
            y.mapv_inplace(|v| v * step);
        }
    } else {
        y.mapv_inplace(|v| v * delta);
    }
    y.mapv_inplace(|v| v + start);
    if endpoint && num > 1 {
        y[num - 1] = stop;
    }
    y
}

/// np.arange(start, stop, step) for floats: length ceil((stop - start) / step), values start + i * delta with
/// delta = (start + step) - start, as numpy fills it (one fused multiply-add on arm64).
pub fn arange(start: f64, stop: f64, step: f64) -> Array1<f64> {
    let len = ((stop - start) / step).ceil();
    let n = if len > 0.0 { len as usize } else { 0 };
    let delta = (start + step) - start;
    (0..n).map(|i| if i == 0 { start } else { madd(i as f64, delta, start) }).collect()
}

/// np.arange(start, stop, step) for ints.
pub fn arange_i(start: i64, stop: i64, step: i64) -> Vec<i64> {
    let mut v = vec![];
    let mut x = start;
    while (step > 0 && x < stop) || (step < 0 && x > stop) {
        v.push(x);
        x += step;
    }
    v
}

/// yy, xx = np.mgrid[0:h, 0:w] (as floats).
pub fn mgrid(h: usize, w: usize) -> (Array2<f64>, Array2<f64>) {
    (Array2::from_shape_fn((h, w), |(y, _)| y as f64), Array2::from_shape_fn((h, w), |(_, x)| x as f64))
}

/// np.meshgrid(x, y) in the (Y, X) order of mgrid: both (len y, len x); numpy's own order is X, Y.
pub fn meshgrid(x: &[f64], y: &[f64]) -> (Array2<f64>, Array2<f64>) {
    let (h, w) = (y.len(), x.len());
    (Array2::from_shape_fn((h, w), |(i, _)| y[i]), Array2::from_shape_fn((h, w), |(_, j)| x[j]))
}

/// The shape two shapes broadcast to, numpy's rule (align right, 1 stretches).
pub fn broadcast_shape(a: &[usize], b: &[usize]) -> Result<Vec<usize>, String> {
    let n = a.len().max(b.len());
    let at = |s: &[usize], i: usize| if i + s.len() >= n { s[i + s.len() - n] } else { 1 };
    (0..n)
        .map(|i| match (at(a, i), at(b, i)) {
            (x, y) if x == y => Ok(x),
            (1, y) => Ok(y),
            (x, 1) => Ok(x),
            _ => Err(format!("shapes {a:?} and {b:?} do not broadcast")),
        })
        .collect()
}

// ---- elementwise --------------------------------------------------------------------------------------------

pub fn round_a<S: Data<Elem = f64>, D: Dimension>(a: &ArrayBase<S, D>) -> Array<f64, D> {
    a.mapv(round)
}

pub fn clip_a<S: Data<Elem = f64>, D: Dimension>(a: &ArrayBase<S, D>, lo: f64, hi: f64) -> Array<f64, D> {
    a.mapv(|x| clip(x, lo, hi))
}

pub fn hypot_a<S: Data<Elem = f64>, T: Data<Elem = f64>, D: Dimension>(a: &ArrayBase<S, D>, b: &ArrayBase<T, D>) -> Array<f64, D> {
    Zip::from(a).and(b).map_collect(|&x, &y| x.hypot(y))
}

/// np.where(cond, a, b) for arrays of one shape.
pub fn where_<T: Copy, S: Data<Elem = bool>, A: Data<Elem = T>, B: Data<Elem = T>, D: Dimension>(
    cond: &ArrayBase<S, D>, a: &ArrayBase<A, D>, b: &ArrayBase<B, D>) -> Array<T, D> {
    Zip::from(cond).and(a).and(b).map_collect(|&c, &x, &y| if c { x } else { y })
}

// ---- reductions ---------------------------------------------------------------------------------------------

/// numpy's pairwise summation (blocks of 8 unrolled, split in halves past 128).
fn pairwise(a: &[f64]) -> f64 {
    let n = a.len();
    if n < 8 {
        let mut res = 0.0;
        for &v in a {
            res += v;
        }
        res
    } else if n <= 128 {
        let mut r = [0.0; 8];
        r.copy_from_slice(&a[..8]);
        let mut i = 8;
        while i < n - n % 8 {
            for j in 0..8 {
                r[j] += a[i + j];
            }
            i += 8;
        }
        let mut res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        while i < n {
            res += a[i];
            i += 1;
        }
        res
    } else {
        let mut n2 = n / 2;
        n2 -= n2 % 8;
        pairwise(&a[..n2]) + pairwise(&a[n2..])
    }
}

fn values<S: Data<Elem = f64>, D: Dimension>(a: &ArrayBase<S, D>) -> Vec<f64> {
    a.iter().copied().collect()
}

/// a.sum() over every element (C order), numpy's pairwise sum.
pub fn sum<S: Data<Elem = f64>, D: Dimension>(a: &ArrayBase<S, D>) -> f64 {
    match a.as_slice() {
        Some(s) => 0.0 + pairwise(s),
        None => 0.0 + pairwise(&values(a)),
    }
}

/// a.mean(): sum / n.
pub fn mean<S: Data<Elem = f64>, D: Dimension>(a: &ArrayBase<S, D>) -> f64 {
    sum(a) / a.len() as f64
}

/// a.sum(axis): pairwise along the last axis (contiguous), else added slice by slice in order as numpy does.
pub fn sum_axis<S: Data<Elem = f64>, D>(a: &ArrayBase<S, D>, axis: usize) -> Array<f64, D::Smaller>
where
    D: ndarray::RemoveAxis,
{
    if axis + 1 == a.ndim() {
        a.map_axis(Axis(axis), |lane| 0.0 + pairwise(&lane.to_vec()))
    } else {
        let mut out = a.index_axis(Axis(axis), 0).mapv(|v| 0.0 + v);
        for k in 1..a.len_of(Axis(axis)) {
            out.zip_mut_with(&a.index_axis(Axis(axis), k), |o, &v| *o += v);
        }
        out
    }
}

/// a.mean(axis).
pub fn mean_axis<S: Data<Elem = f64>, D: Dimension + ndarray::RemoveAxis>(a: &ArrayBase<S, D>, axis: usize) -> Array<f64, D::Smaller> {
    let n = a.len_of(Axis(axis)) as f64;
    sum_axis(a, axis).mapv(|v| v / n)
}

/// np.cumsum (sequential, as numpy accumulates).
pub fn cumsum(a: &[f64]) -> Vec<f64> {
    let mut acc = 0.0;
    a.iter()
        .enumerate()
        .map(|(i, &v)| {
            acc = if i == 0 { v } else { acc + v };
            acc
        })
        .collect()
}

fn sorted(a: &[f64]) -> Vec<f64> {
    let mut s = a.to_vec();
    s.sort_by(|x, y| x.total_cmp(y));
    s
}

/// np.median of every value; NaN if any is NaN.
pub fn median(a: &[f64]) -> f64 {
    if a.iter().any(|v| v.is_nan()) || a.is_empty() {
        return f64::NAN;
    }
    let s = sorted(a);
    let n = s.len();
    if n % 2 == 1 { s[n / 2] } else { (s[n / 2 - 1] + s[n / 2]) / 2.0 }
}

/// np.quantile(a, q), the default linear method, with numpy's virtual index and lerp.
pub fn quantile(a: &[f64], q: f64) -> f64 {
    if a.iter().any(|v| v.is_nan()) || a.is_empty() {
        return f64::NAN;
    }
    let s = sorted(a);
    let n = s.len() as f64;
    // numpy's "linear" method: virtual index (n - 1) * q.
    let vi = (n - 1.0) * q;
    let prev = vi.floor();
    let last = n - 1.0;
    let (pi, ni) = (prev.clamp(0.0, last), (prev + 1.0).clamp(0.0, last));
    let g = vi - prev;
    let (lo, hi) = (s[pi as usize], s[ni as usize]);
    let d = hi - lo;
    if vi >= last {
        return s[last as usize];
    }
    if vi < 0.0 {
        return s[0];
    }
    if g >= 0.5 { hi - d * (1.0 - g) } else { lo + d * g }
}

/// np.percentile(a, q): quantile at q / 100.
pub fn percentile(a: &[f64], q: f64) -> f64 {
    quantile(a, q / 100.0)
}

/// np.argmax: the first index of the largest value (the first NaN if any).
pub fn argmax(a: &[f64]) -> usize {
    let mut best = 0;
    for (i, &v) in a.iter().enumerate() {
        if v.is_nan() {
            return i;
        }
        if v > a[best] {
            best = i;
        }
    }
    best
}

/// np.argmin: the first index of the smallest value (the first NaN if any).
pub fn argmin(a: &[f64]) -> usize {
    let mut best = 0;
    for (i, &v) in a.iter().enumerate() {
        if v.is_nan() {
            return i;
        }
        if v < a[best] {
            best = i;
        }
    }
    best
}

/// np.unique: the sorted distinct values.
pub fn unique<T: PartialOrd + Copy>(a: &[T]) -> Vec<T> {
    let mut s = a.to_vec();
    s.sort_by(|x, y| x.partial_cmp(y).unwrap_or(std::cmp::Ordering::Equal));
    s.dedup_by(|x, y| x == y);
    s
}

/// np.nonzero(cond): the indices along each axis of the true cells, C order (for 2-D: ys, xs).
pub fn nonzero<S: Data<Elem = bool>, D: Dimension>(cond: &ArrayBase<S, D>) -> Vec<Vec<usize>> {
    let mut out = vec![vec![]; cond.ndim()];
    for (ix, &c) in cond.view().into_dyn().indexed_iter() {
        if c {
            for (k, v) in ix.slice().iter().enumerate() {
                out[k].push(*v);
            }
        }
    }
    out
}

// ---- lookups ------------------------------------------------------------------------------------------------

/// np.searchsorted(a, v, side): "left" is the first index with a[i] >= v, "right" the first with a[i] > v.
pub fn searchsorted(a: &[f64], v: f64, right: bool) -> usize {
    if right { a.partition_point(|&x| x <= v) } else { a.partition_point(|&x| x < v) }
}

/// np.interp(x, xp, fp) for one x (xp increasing): fp[0] left of xp, fp[-1] right of it.
pub fn interp(x: f64, xp: &[f64], fp: &[f64]) -> f64 {
    let n = xp.len();
    if x.is_nan() {
        return x;
    }
    if x < xp[0] {
        return fp[0];
    }
    if x >= xp[n - 1] {
        return fp[n - 1];
    }
    let j = xp.partition_point(|&p| p <= x) - 1;
    if x == xp[j] {
        return fp[j];
    }
    let slope = (fp[j + 1] - fp[j]) / (xp[j + 1] - xp[j]);
    let mut r = madd(slope, x - xp[j], fp[j]);
    if r.is_nan() {
        r = madd(slope, x - xp[j + 1], fp[j + 1]);
        if r.is_nan() && fp[j] == fp[j + 1] {
            r = fp[j];
        }
    }
    r
}

/// np.interp over an array of x.
pub fn interp_a<S: Data<Elem = f64>, D: Dimension>(x: &ArrayBase<S, D>, xp: &[f64], fp: &[f64]) -> Array<f64, D> {
    x.mapv(|v| interp(v, xp, fp))
}

/// np.digitize(x, bins) (right=False): bins increasing or decreasing.
pub fn digitize(x: f64, bins: &[f64]) -> usize {
    let inc = bins.len() < 2 || bins[0] <= bins[bins.len() - 1];
    if inc {
        searchsorted(bins, x, true)
    } else {
        let rev: Vec<f64> = bins.iter().rev().copied().collect();
        bins.len() - searchsorted(&rev, x, false)
    }
}

// ---- moves --------------------------------------------------------------------------------------------------

/// np.roll(a, shift, axis): cells pushed shift places along axis, wrapping.
pub fn roll<T: Clone, S: Data<Elem = T>, D: Dimension + ndarray::RemoveAxis>(a: &ArrayBase<S, D>, shift: i64, axis: usize) -> Array<T, D> {
    let n = a.len_of(Axis(axis)) as i64;
    let mut out = a.to_owned();
    if n == 0 {
        return out;
    }
    for k in 0..n {
        let src = pymod_i(k - shift, n) as usize;
        out.index_axis_mut(Axis(axis), k as usize).assign(&a.index_axis(Axis(axis), src));
    }
    out
}

/// How `pad` fills: a constant, or the edge value repeated.
#[derive(Clone, Copy, Debug)]
pub enum Pad<T> {
    Constant(T),
    Edge,
}

/// np.pad(a, width, mode): width is (before, after) per axis.
pub fn pad<T: Clone, S: Data<Elem = T>, D: Dimension>(a: &ArrayBase<S, D>, width: &[(usize, usize)], mode: Pad<T>) -> Array<T, D> {
    assert_eq!(width.len(), a.ndim(), "pad: one (before, after) per axis");
    let v = a.view().into_dyn();
    let shape: Vec<usize> = a.shape().iter().zip(width).map(|(s, (b, e))| s + b + e).collect();
    let out = Array::from_shape_fn(IxDyn(&shape), |ix| {
        let mut src = vec![0usize; shape.len()];
        for k in 0..shape.len() {
            let i = ix[k] as i64 - width[k].0 as i64;
            let n = a.shape()[k] as i64;
            if i < 0 || i >= n {
                match &mode {
                    Pad::Constant(c) => return c.clone(),
                    Pad::Edge => src[k] = i.clamp(0, n - 1) as usize,
                }
            } else {
                src[k] = i as usize;
            }
        }
        v[IxDyn(&src)].clone()
    });
    out.into_dimensionality::<D>().unwrap()
}

/// np.gradient(a): one array per axis, central differences inside, one-sided at the ends (unit spacing).
pub fn gradient<S: Data<Elem = f64>, D: Dimension>(a: &ArrayBase<S, D>) -> Vec<Array<f64, D>> {
    (0..a.ndim())
        .map(|ax| {
            let n = a.len_of(Axis(ax));
            let mut g = Array::zeros(a.raw_dim());
            for (mut go, ai) in g.lanes_mut(Axis(ax)).into_iter().zip(a.lanes(Axis(ax))) {
                if n < 2 {
                    continue;
                }
                for i in 1..n - 1 {
                    go[i] = (ai[i + 1] - ai[i - 1]) / 2.0;
                }
                go[0] = (ai[1] - ai[0]) / 1.0;
                go[n - 1] = (ai[n - 1] - ai[n - 2]) / 1.0;
            }
            g
        })
        .collect()
}

#[cfg(test)]
mod tests;

// ---- slice 2b: Python's math.hypot ----------------------------------------------------------------------------

/// Python 3.12 `math.hypot(a, b)`: CPython's own scaled, error-compensated norm, not libm's hypot (the two differ
/// in the last bit for about 15 % of inputs). `np.hypot` stays `hypot`.
pub fn math_hypot(a: f64, b: f64) -> f64 {
    let (a, b) = (a.abs(), b.abs());
    let max = if a >= b { a } else { b };
    if a.is_infinite() || b.is_infinite() {
        return f64::INFINITY;
    }
    if a.is_nan() || b.is_nan() {
        return f64::NAN;
    }
    hyp_norm(&mut [a, b], max)
}

fn frexp_exp(x: f64) -> i32 {
    let bits = x.to_bits();
    let e = ((bits >> 52) & 0x7ff) as i32;
    if e == 0 {
        frexp_exp(x * 18014398509481984.0) - 54
    } else {
        e - 1022
    }
}

fn hyp_norm(vec: &mut [f64; 2], max: f64) -> f64 {
    if max == 0.0 {
        return max;
    }
    let max_e = frexp_exp(max);
    if max_e < -1023 {
        for v in vec.iter_mut() {
            *v /= f64::MIN_POSITIVE;
        }
        return f64::MIN_POSITIVE * hyp_norm(vec, max / f64::MIN_POSITIVE);
    }
    let scale = f64::from_bits(((1023 - max_e) as u64) << 52);
    let (mut csum, mut frac1, mut frac2) = (1.0f64, 0.0f64, 0.0f64);
    let mul = |x: f64, y: f64| {
        let z = x * y;
        (z, x.mul_add(y, -z))
    };
    let fast_sum = |a: f64, b: f64| {
        let x = a + b;
        (x, (a - x) + b)
    };
    for &v in vec.iter() {
        let x = v * scale;
        let pr = mul(x, x);
        let sm = fast_sum(csum, pr.0);
        csum = sm.0;
        frac1 += pr.1;
        frac2 += sm.1;
    }
    let mut h = (csum - 1.0 + (frac1 + frac2)).sqrt();
    let pr = mul(-h, h);
    let sm = fast_sum(csum, pr.0);
    csum = sm.0;
    frac1 += pr.1;
    frac2 += sm.1;
    let x = csum - 1.0 + (frac1 + frac2);
    h += x / (2.0 * h);
    h / scale
}
