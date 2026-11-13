//! derive.py: points and lines taken from a finished drawing, for the states that build up to it or break down
//! from it. Draw the peak frame first, then take every build-up and break-down state from its masks (outline for
//! stars and threads, spine for a sketch stroke, scatter for motes), never from hand-placed points. Points are
//! (x, y) at pixel centres (column, row), as `Array2<f64>` of shape (n, 2).

use crate::np;
use crate::rng::default_rng;
use ndarray::{s, Array2, ArrayView2};
use std::collections::{BTreeMap, BTreeSet};

const D8: [(i64, i64); 8] = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)];

fn points(v: &[(f64, f64)]) -> Array2<f64> {
    let mut a = Array2::zeros((v.len(), 2));
    for (i, p) in v.iter().enumerate() {
        a[[i, 0]] = p.0;
        a[[i, 1]] = p.1;
    }
    a
}

/// Outer boundary of the largest blob in mask m, clockwise on screen, as (x, y) pixels; holes are ignored.
/// Err when m holds no pixel (Python raises IndexError).
pub fn outline(m: &Array2<bool>) -> Result<Array2<f64>, String> {
    let m = largest(m);
    let (h, w) = m.dim();
    let mut p = Array2::from_elem((h + 2, w + 2), false);
    p.slice_mut(s![1..=h, 1..=w]).assign(&m);
    let first_px = p.indexed_iter().find(|(_, &v)| v).map(|(ix, _)| ix);
    let Some((y0, x0)) = first_px else {
        return Err("outline: the mask is empty".into());
    };
    let (x0, y0) = (x0 as i64, y0 as i64);
    let mut out = vec![(x0, y0)];
    let (mut x, mut y, mut d) = (x0, y0, 0usize);
    let mut first: Option<usize> = None;
    for _ in 0..4 * p.len() {
        let mut found = None;
        for k in 0..8 {
            let nd = (d + 6 + k) % 8;
            let (nx, ny) = (x + D8[nd].0, y + D8[nd].1);
            if p[[ny as usize, nx as usize]] {
                found = Some((nd, nx, ny));
                break;
            }
        }
        let Some((nd, nx, ny)) = found else { break }; // a single pixel
        if (x, y) == (x0, y0) {
            match first {
                None => first = Some(nd),
                Some(f) if f == nd => break,
                _ => {}
            }
        }
        x = nx;
        y = ny;
        d = nd;
        out.push((x, y));
    }
    let keep = if out.len() > 1 { &out[..out.len() - 1] } else { &out[..] };
    let v: Vec<(f64, f64)> = keep.iter().map(|&(x, y)| ((x - 1) as f64, (y - 1) as f64)).collect();
    Ok(points(&v))
}

/// The n most telling corners of polyline P, kept in order: each point is ranked by the error it fixes when
/// Ramer-Douglas-Peucker splits there, and the top n stay. closed: P is a loop, split at the point farthest from
/// P[0] so both halves keep their corners.
pub fn simplify(p: &Array2<f64>, n: usize, closed: bool) -> Array2<f64> {
    if p.nrows() <= n {
        return p.clone();
    }
    let len = p.nrows();
    let rank: Vec<f64> = if closed {
        let dist: Vec<f64> = (0..len).map(|i| np::hypot(p[[i, 0]] - p[[0, 0]], p[[i, 1]] - p[[0, 1]])).collect();
        let far = np::argmax(&dist);
        let mut rank = vec![0.0; len];
        rank[0] = f64::INFINITY;
        rank[far] = f64::INFINITY;
        let head = rank_of(&p.slice(s![..far + 1, ..]));
        for i in 0..=far {
            rank[i] = f64::max(rank[i], head[i]);
        }
        let mut tail_pts = Array2::zeros((len - far + 1, 2));
        tail_pts.slice_mut(s![..len - far, ..]).assign(&p.slice(s![far.., ..]));
        tail_pts.row_mut(len - far).assign(&p.row(0));
        let tail = rank_of(&tail_pts.view());
        for i in far..len {
            rank[i] = f64::max(rank[i], tail[i - far]);
        }
        rank
    } else {
        rank_of(&p.view())
    };
    let mut order: Vec<usize> = (0..len).collect();
    order.sort_by(|&a, &b| (-rank[a]).partial_cmp(&(-rank[b])).unwrap());
    let mut keep: Vec<usize> = order[..n].to_vec();
    keep.sort_unstable();
    let mut out = Array2::zeros((keep.len(), 2));
    for (i, &k) in keep.iter().enumerate() {
        out.row_mut(i).assign(&p.row(k));
    }
    out
}

/// Lines where two labelled parts meet (the jaw against the skull, an eye in the face), as ordered chains. parts:
/// int map, -1 empty. Each boundary pixel is taken on the side of the larger id, so a line is 1 px.
pub fn part_lines(parts: &Array2<i64>, min_len: usize) -> Vec<Array2<f64>> {
    let (h, w) = parts.dim();
    let mut b = Array2::from_elem((h, w), false);
    for (dy, dx) in [(0i64, 1i64), (1, 0), (0, -1), (-1, 0)] {
        for y in 0..h {
            for x in 0..w {
                let (sy, sx) = (y as i64 - dy, x as i64 - dx);
                let q = if sy >= 0 && sx >= 0 && (sy as usize) < h && (sx as usize) < w { parts[[sy as usize, sx as usize]] } else { -1 };
                let v = parts[[y, x]];
                if v >= 0 && q >= 0 && q < v {
                    b[[y, x]] = true;
                }
            }
        }
    }
    chains(&b).into_iter().filter(|c| c.nrows() >= min_len).collect()
}

/// Centre lines of mask m (Zhang-Suen thinning), as ordered chains, longest first.
pub fn spine(m: &Array2<bool>, min_len: usize) -> Vec<Array2<f64>> {
    chains(&thin(m)).into_iter().filter(|c| c.nrows() >= min_len).collect()
}

/// n points spread evenly inside mask m (farthest point sampling from a seeded start), as (x, y) pixels.
pub fn scatter(m: &Array2<bool>, n: usize, seed: u64) -> Array2<f64> {
    let nz = np::nonzero(m);
    let (ys, xs) = (&nz[0], &nz[1]);
    let c: Vec<(f64, f64)> = xs.iter().zip(ys).map(|(&x, &y)| (x as f64, y as f64)).collect();
    if c.len() <= n {
        return points(&c);
    }
    let mut rng = default_rng(seed);
    let dist_to = |q: (f64, f64)| -> Vec<f64> { c.iter().map(|p| np::hypot(p.0 - q.0, p.1 - q.1)).collect() };
    let first = rng.integers1(c.len() as i64) as usize;
    let mut pick = vec![first];
    let mut d = dist_to(c[first]);
    for _ in 1..n {
        let k = np::argmax(&d);
        pick.push(k);
        let dk = dist_to(c[k]);
        for (a, b) in d.iter_mut().zip(dk) {
            *a = if b < *a { b } else { *a };
        }
    }
    let v: Vec<(f64, f64)> = pick.iter().map(|&k| c[k]).collect();
    points(&v)
}

/// 1 px wide pixels of mask b as ordered 8-connected chains, each from an end where it has one, longest first.
pub fn chains(b: &Array2<bool>) -> Vec<Array2<f64>> {
    let mut pts: BTreeSet<(i64, i64)> = BTreeSet::new();
    for ((y, x), &v) in b.indexed_iter() {
        if v {
            pts.insert((y as i64, x as i64));
        }
    }
    let deg: BTreeMap<(i64, i64), usize> = pts
        .iter()
        .map(|&(y, x)| ((y, x), D8.iter().filter(|(dx, dy)| pts.contains(&(y + dy, x + dx))).count()))
        .collect();
    let mut out: Vec<Vec<(f64, f64)>> = vec![];
    while let Some(&first_pt) = pts.iter().next() {
        let start = pts.iter().find(|q| deg[*q] <= 1).copied().unwrap_or(first_pt);
        let mut chain = vec![start];
        let mut cur = start;
        pts.remove(&start);
        loop {
            let (y, x) = cur;
            let mut nb: Vec<(i64, i64)> = D8.iter().map(|(dx, dy)| (y + dy, x + dx)).filter(|q| pts.contains(q)).collect();
            if nb.is_empty() {
                break;
            }
            nb.sort_by_key(|q| ((q.0 - y).abs() + (q.1 - x).abs(), *q)); // side neighbours before corners
            cur = nb[0];
            pts.remove(&cur);
            chain.push(cur);
        }
        out.push(chain.iter().map(|&(y, x)| (x as f64, y as f64)).collect());
    }
    out.sort_by(|a, b| b.len().cmp(&a.len()));
    out.iter().map(|c| points(c)).collect()
}

/// World points to the carrier's frame: about anchor, unrotated by ang, divided by scale.
pub fn local(p: &Array2<f64>, anchor: [f64; 2], ang: f64, scale: f64) -> Array2<f64> {
    let (c, s) = ((-ang).cos(), (-ang).sin());
    let mut out = Array2::zeros(p.dim());
    for i in 0..p.nrows() {
        let (x, y) = (p[[i, 0]] - anchor[0], p[[i, 1]] - anchor[1]);
        out[[i, 0]] = (x * c - y * s) / scale;
        out[[i, 1]] = (x * s + y * c) / scale;
    }
    out
}

/// Points in the carrier's frame back to the world for a frame whose carrier sits at anchor, ang, scale.
pub fn world(l: &Array2<f64>, anchor: [f64; 2], ang: f64, scale: f64) -> Array2<f64> {
    let (c, s) = (ang.cos(), ang.sin());
    let mut out = Array2::zeros(l.dim());
    for i in 0..l.nrows() {
        let (x, y) = (l[[i, 0]] * scale, l[[i, 1]] * scale);
        out[[i, 0]] = (x * c - y * s) + anchor[0];
        out[[i, 1]] = (x * s + y * c) + anchor[1];
    }
    out
}

// ---- internals ----

/// Per point, the deviation at which Ramer-Douglas-Peucker keeps it (inf for the two ends), capped by its parent's
/// so a child never outranks the split that made it.
fn rank_of(p: &ArrayView2<f64>) -> Vec<f64> {
    let n = p.nrows();
    let mut rank = vec![0.0; n];
    rank[0] = f64::INFINITY;
    rank[n - 1] = f64::INFINITY;
    let mut stack = vec![(0usize, n - 1, f64::INFINITY)];
    while let Some((i, j, cap)) = stack.pop() {
        if j <= i + 1 {
            continue;
        }
        let (a, b) = ((p[[i, 0]], p[[i, 1]]), (p[[j, 0]], p[[j, 1]]));
        let ab = (b.0 - a.0, b.1 - a.1);
        let ln = np::hypot(ab.0, ab.1);
        let d: Vec<f64> = (i + 1..j)
            .map(|r| {
                let (sx, sy) = (p[[r, 0]], p[[r, 1]]);
                if ln < 1e-9 {
                    np::hypot(sx - a.0, sy - a.1)
                } else {
                    (ab.0 * (sy - a.1) - ab.1 * (sx - a.0)).abs() / ln
                }
            })
            .collect();
        let k = np::argmax(&d);
        let r = if cap < d[k] { cap } else { d[k] };
        rank[i + 1 + k] = r;
        stack.push((i, i + 1 + k, r));
        stack.push((i + 1 + k, j, r));
    }
    rank
}

/// The largest 8-connected blob of m (flood fill, no scipy); m itself when it holds no pixel.
pub fn largest(m: &Array2<bool>) -> Array2<bool> {
    let (h, w) = m.dim();
    let mut lab = Array2::<i64>::zeros((h, w));
    let (mut best, mut best_n, mut cur) = (0i64, 0usize, 0i64);
    for ((y0, x0), &v) in m.indexed_iter() {
        if !v || lab[[y0, x0]] != 0 {
            continue;
        }
        cur += 1;
        let mut stack = vec![(y0 as i64, x0 as i64)];
        let mut n = 0usize;
        lab[[y0, x0]] = cur;
        while let Some((y, x)) = stack.pop() {
            n += 1;
            for (dx, dy) in D8 {
                let (yy, xx) = (y + dy, x + dx);
                if yy >= 0 && yy < h as i64 && xx >= 0 && xx < w as i64 && m[[yy as usize, xx as usize]] && lab[[yy as usize, xx as usize]] == 0 {
                    lab[[yy as usize, xx as usize]] = cur;
                    stack.push((yy, xx));
                }
            }
        }
        if n > best_n {
            best = cur;
            best_n = n;
        }
    }
    if best != 0 {
        lab.mapv(|l| l == best)
    } else {
        m.clone()
    }
}

/// Zhang-Suen thinning to a 1 px skeleton.
fn thin(m: &Array2<bool>) -> Array2<bool> {
    let (h, w) = m.dim();
    let mut img = Array2::<u8>::zeros((h + 2, w + 2));
    img.slice_mut(s![1..=h, 1..=w]).assign(&m.mapv(|v| v as u8));
    const N: [(i64, i64); 8] = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]; // p2..p9 clockwise
    loop {
        let mut changed = false;
        for step in 0..2 {
            let mut rm = vec![];
            for y in 1..=h {
                for x in 1..=w {
                    if img[[y, x]] != 1 {
                        continue;
                    }
                    let p: Vec<u8> = N.iter().map(|(dx, dy)| img[[(y as i64 + dy) as usize, (x as i64 + dx) as usize]]).collect();
                    let b: u32 = p.iter().map(|&v| v as u32).sum();
                    let a = (0..8).filter(|&k| p[k] == 0 && p[(k + 1) % 8] == 1).count();
                    let c = if step == 0 {
                        (p[0] * p[2] * p[4] == 0) && (p[2] * p[4] * p[6] == 0)
                    } else {
                        (p[0] * p[2] * p[6] == 0) && (p[0] * p[4] * p[6] == 0)
                    };
                    if (2..=6).contains(&b) && a == 1 && c {
                        rm.push((y, x));
                    }
                }
            }
            if !rm.is_empty() {
                for (y, x) in rm {
                    img[[y, x]] = 0;
                }
                changed = true;
            }
        }
        if !changed {
            return img.slice(s![1..=h, 1..=w]).mapv(|v| v == 1);
        }
    }
}
