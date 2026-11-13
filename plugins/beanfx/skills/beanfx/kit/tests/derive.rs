//! Port of tests/test_derive.py: outlines hug the shape and close, simplify hits its count, spines run down the
//! middle, part lines sit where parts meet, scatter stays inside and spreads, local and world round-trip.

use beanfx::dv;
use beanfx::ndarray::{Array2, Axis};

const H: usize = 80;
const W: usize = 120;

fn mask(f: impl Fn(f64, f64) -> bool) -> Array2<bool> {
    Array2::from_shape_fn((H, W), |(y, x)| f(x as f64, y as f64))
}

fn radii(p: &Array2<f64>, cx: f64, cy: f64) -> Vec<f64> {
    p.rows().into_iter().map(|r| (r[0] - cx).hypot(r[1] - cy)).collect()
}

fn min_max(v: &[f64]) -> (f64, f64) {
    (v.iter().cloned().fold(f64::INFINITY, f64::min), v.iter().cloned().fold(f64::NEG_INFINITY, f64::max))
}

fn disc() -> Array2<bool> {
    mask(|x, y| (x - 40.0).hypot(y - 40.0) <= 20.0)
}

fn closed_steps(p: &Array2<f64>) -> Vec<(f64, f64)> {
    let n = p.nrows();
    (0..n).map(|i| {
        let j = (i + 1) % n;
        (p[[j, 0]] - p[[i, 0]], p[[j, 1]] - p[[i, 1]])
    }).collect()
}

#[test]
fn outline_hugs_disc_and_closes() {
    let mut speck = disc();
    speck[[5, 110]] = true;
    let p = dv::outline(&speck).unwrap();
    let (lo, hi) = min_max(&radii(&p, 40.0, 40.0));
    assert!(lo >= 18.5 && hi <= 20.5, "outline on the disc edge: r {lo} to {hi}");
    // the python step check covers the n-1 inner steps plus the closing step
    let step = closed_steps(&p).iter().fold(0.0f64, |m, s| m.max(s.0.abs()).max(s.1.abs()));
    assert!(step <= 1.0, "outline is a closed 8-connected loop: max step {step}");
    let n = p.nrows();
    let area: f64 = 0.5 * (0..n).map(|i| {
        let j = (i + 1) % n;
        p[[i, 0]] * p[[j, 1]] - p[[j, 0]] * p[[i, 1]]
    }).sum::<f64>();
    assert!(area > 0.0, "outline is clockwise on screen: signed area {area}");
    assert!(p.column(0).iter().all(|&x| x < 70.0), "outline skips the speck");
}

#[test]
fn outline_of_empty_mask_is_an_error() {
    assert!(dv::outline(&Array2::from_elem((H, W), false)).is_err());
}

#[test]
fn simplify_keeps_count_edge_order_and_spread() {
    let p = dv::outline(&disc()).unwrap();
    let s = dv::simplify(&p, 24, true);
    assert!((s.nrows() as i64 - 24).abs() <= 2, "simplify near the count: {} points", s.nrows());
    let (lo, hi) = min_max(&radii(&s, 40.0, 40.0));
    assert!(lo >= 18.5 && hi <= 20.5, "simplified points on the edge");
    // unwrapped angle is monotonic
    let mut ang: Vec<f64> = s.rows().into_iter().map(|r| (r[1] - 40.0).atan2(r[0] - 40.0)).collect();
    for i in 1..ang.len() {
        while ang[i] - ang[i - 1] > std::f64::consts::PI { ang[i] -= std::f64::consts::TAU; }
        while ang[i] - ang[i - 1] < -std::f64::consts::PI { ang[i] += std::f64::consts::TAU; }
    }
    let d: Vec<f64> = ang.windows(2).map(|w| w[1] - w[0]).collect();
    assert!(d.iter().all(|&v| v > 0.0) || d.iter().all(|&v| v < 0.0), "simplified points keep their order");
    let gaps: Vec<f64> = closed_steps(&s).iter().map(|v| v.0.hypot(v.1)).collect();
    let mean = gaps.iter().sum::<f64>() / gaps.len() as f64;
    let max = gaps.iter().cloned().fold(0.0, f64::max);
    assert!(max < 3.0 * mean, "simplified points spread round: max gap {max}");
}

#[test]
fn spine_runs_down_the_capsule_axis() {
    let cap = mask(|x, y| (x - x.clamp(30.0, 90.0)).hypot(y - 40.0) <= 8.0);
    let sp = dv::spine(&cap, 3);
    let main = &sp[0];
    let ys = main.column(1);
    let dev = ys.iter().fold(0.0f64, |m, &y| m.max((y - 40.0).abs()));
    assert!(dev <= 1.0, "spine on the capsule axis: deviation {dev}");
    let xs: Vec<f64> = main.column(0).to_vec();
    let (lo, hi) = min_max(&xs);
    assert!(hi - lo >= 0.8 * 60.0, "spine spans the axis: span {}", hi - lo);
    let step = main.axis_iter(Axis(0)).collect::<Vec<_>>().windows(2)
        .fold(0.0f64, |m, w| m.max((w[1][0] - w[0][0]).abs()).max((w[1][1] - w[0][1]).abs()));
    assert!(step <= 1.0, "spine chain is ordered");
}

#[test]
fn part_line_sits_where_parts_meet() {
    let d = disc();
    let parts = Array2::from_shape_fn((H, W), |(y, x)| if d[[y, x]] { if (x as f64) < 40.0 { 0 } else { 1 } } else { -1 });
    let pl = dv::part_lines(&parts, 3);
    assert_eq!(pl.len(), 1, "one part line: {} lines", pl.len());
    let xs = pl[0].column(0);
    assert!(xs.iter().all(|&x| (x - 40.0).abs() <= 1.0), "part line x");
    let (lo, hi) = min_max(&pl[0].column(1).to_vec());
    assert!(hi - lo >= 36.0, "part line spans the meeting edge");
}

#[test]
fn scatter_stays_inside_spreads_and_is_seeded() {
    let d = disc();
    let pts = dv::scatter(&d, 30, 3);
    let inside = pts.rows().into_iter().all(|r| d[[r[1] as usize, r[0] as usize]]);
    assert!(pts.nrows() == 30 && inside, "scatter count and inside");
    let mut min = f64::INFINITY;
    for i in 0..pts.nrows() {
        for j in 0..pts.nrows() {
            if i != j {
                min = min.min((pts[[i, 0]] - pts[[j, 0]]).hypot(pts[[i, 1]] - pts[[j, 1]]));
            }
        }
    }
    let area = d.iter().filter(|&&v| v).count() as f64;
    assert!(min >= 0.5 * (area / 30.0).sqrt(), "scatter spreads evenly: min gap {min}");
    assert_eq!(pts, dv::scatter(&d, 30, 3), "scatter is seeded");
}

#[test]
fn local_world_round_trip_and_carrier() {
    let p = dv::outline(&disc()).unwrap();
    let s = dv::simplify(&p, 24, true);
    let (a, ang, sc) = ([40.0, 40.0], 0.7, 1.6);
    let l = dv::local(&s, a, ang, sc);
    let back = dv::world(&l, a, ang, sc);
    assert!(back.iter().zip(s.iter()).all(|(x, y)| (x - y).abs() < 1e-8), "local then world round-trips");
    let moved = dv::world(&l, [60.0, 30.0], ang + 0.3, sc);
    let r2 = radii(&moved, 60.0, 30.0);
    let rs = radii(&s, 40.0, 40.0);
    assert!(r2.iter().zip(rs.iter()).all(|(a, b)| (a - b).abs() < 1e-8), "points ride the carrier");
}
