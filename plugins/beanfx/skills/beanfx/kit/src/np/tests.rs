use super::*;
use crate::rng::default_rng;

include!("np_vectors.rs");

/// default_rng(seed).random(n) * 10 - 5, the inputs np_vectors.py used.
fn inp(seed: u64, n: usize) -> Vec<f64> {
    let mut r = default_rng(seed);
    (0..n).map(|_| r.random() * 10.0 - 5.0).collect()
}

fn same(got: &[f64], want: &[u64], what: &str) {
    assert_eq!(got.len(), want.len(), "{what}: length");
    for (i, (g, w)) in got.iter().zip(want).enumerate() {
        assert_eq!(g.to_bits(), *w, "{what} {i}: {g} vs {}", f64::from_bits(*w));
    }
}

#[test]
fn ranges() {
    let mut g = linspace(0.0, 1.0, 7).to_vec();
    g.extend(linspace(-3.3, 2.9, 11));
    g.extend(linspace_ep(0.0, 2.0 * std::f64::consts::PI, 9, false));
    g.extend(linspace(5.0, 5.0, 4));
    g.extend(linspace(1.0, 2.0, 1));
    g.extend(linspace_ep(0.1, 0.7, 6, false));
    same(&g, LINSPACE, "linspace");
    let mut g = arange(0.0, 1.0, 0.1).to_vec();
    g.extend(arange(1.5, -2.0, -0.3));
    g.extend(arange(0.0, 10.0, 0.7));
    g.extend(arange(-1.0, 1.0, 0.25));
    same(&g, ARANGE, "arange");
    assert_eq!(arange_i(5, -3, -3), vec![5, 2, -1]);
    let (yy, xx) = mgrid(2, 3);
    assert_eq!((yy[[1, 0]], xx[[1, 2]]), (1.0, 2.0));
    let (my, mx) = meshgrid(&[1.0, 2.0, 3.0], &[7.0, 8.0]);
    assert_eq!((my.dim(), my[[1, 0]], mx[[0, 2]]), ((2, 3), 8.0, 3.0));
}

#[test]
fn rounding_and_floor_rules() {
    let mut g: Vec<f64> = [0.5, 1.5, 2.5, -0.5, -1.5, 2.4999, 7.5000001].iter().map(|&x| round(x)).collect();
    g.extend([round_dec(2.675, 2), round_dec(-1.005, 2), round_dec(0.125, 2)]);
    same(&g, ROUND, "round");
    let pairs = [(7.5, 2.0), (-7.5, 2.0), (7.5, -2.0), (-7.5, -2.0), (0.3, 0.1), (5.0, 0.3), (-0.0, 3.0), (1e-20, 1.0),
                 (-1e-20, 1.0), (6.0, 3.0), (-6.0, 3.0), (0.7, -0.1)];
    same(&pairs.iter().map(|&(a, b)| floordiv(a, b)).collect::<Vec<_>>(), FLOORDIV, "floordiv");
    same(&pairs.iter().map(|&(a, b)| pymod(a, b)).collect::<Vec<_>>(), PYMOD, "pymod");
    assert_eq!((floordiv_i(-7, 2), pymod_i(-7, 2), floordiv_i(7, -2), pymod_i(7, -2)), (-4, 1, -4, -1));
    assert!(clip(f64::NAN, 0.0, 1.0).is_nan());
    assert_eq!((clip(-2.0, 0.0, 1.0), clip(3.0, 0.0, 1.0)), (0.0, 1.0));
}

#[test]
fn order_statistics() {
    let x = inp(1, 31);
    same(&[median(&x), median(&x[..30]), median(&x[..2]), median(&x[..1])], MEDIAN, "median");
    let qs = [0.0, 0.1, 0.25, 0.5, 0.73, 0.9, 0.999, 1.0];
    let mut g: Vec<f64> = qs.iter().map(|&q| quantile(&x, q)).collect();
    g.extend(qs.iter().map(|&q| quantile(&x[..10], q)));
    g.push(percentile(&x, 99.5));
    same(&g, QUANTILE, "quantile");
    assert_eq!((argmax(&[1.0, 3.0, 3.0, 2.0]), argmin(&[2.0, 1.0, 1.0])), (1, 1));
    assert_eq!(unique(&[3, 1, 3, 2, 1]), vec![1, 2, 3]);
}

#[test]
fn lookups() {
    let mut xp = inp(2, 8);
    xp.sort_by(f64::total_cmp);
    let fp = inp(3, 8);
    let xs: Vec<f64> = inp(4, 40).iter().map(|v| v * 1.2).collect();
    same(&xs.iter().map(|&x| interp(x, &xp, &fp)).collect::<Vec<_>>(), INTERP, "interp");
    same(&xp.iter().map(|&x| interp(x, &xp, &fp)).collect::<Vec<_>>(), INTERP_EDGE, "interp at xp");
    let rev: Vec<f64> = xp.iter().rev().copied().collect();
    let mut d: Vec<i64> = xs.iter().map(|&x| digitize(x, &xp) as i64).collect();
    d.extend(xs.iter().map(|&x| digitize(x, &rev) as i64));
    d.extend(xp.iter().map(|&x| digitize(x, &xp) as i64));
    assert_eq!(d, DIGITIZE);
}

#[test]
fn sums_are_pairwise() {
    let sizes = [1, 5, 7, 8, 13, 127, 128, 129, 136, 1000, 4097, 70001];
    let arrs: Vec<Array1<f64>> = sizes.iter().enumerate().map(|(i, &n)| Array1::from(inp(10 + i as u64, n))).collect();
    same(&arrs.iter().map(sum).collect::<Vec<_>>(), SUMS, "sum");
    same(&arrs.iter().map(mean).collect::<Vec<_>>(), MEANS, "mean");
    let m = Array2::from_shape_vec((37, 300), inp(30, 37 * 300)).unwrap();
    same(&sum_axis(&m, 0).to_vec(), SUM_AX0, "sum axis 0");
    same(&sum_axis(&m, 1).to_vec(), SUM_AX1, "sum axis 1");
    same(&mean_axis(&m, 0).to_vec(), MEAN_AX0, "mean axis 0");
    same(&[sum(&m)], SUM_ALL, "sum 2-d");
    same(&cumsum(&inp(31, 20)), CUMSUM, "cumsum");
}

#[test]
fn shapes_and_moves() {
    let g = Array2::from_shape_vec((5, 7), inp(32, 35)).unwrap();
    let gr = gradient(&g);
    same(&gr[0].iter().copied().collect::<Vec<_>>(), GRAD_Y, "gradient y");
    same(&gr[1].iter().copied().collect::<Vec<_>>(), GRAD_X, "gradient x");
    same(&gradient(&Array1::from(inp(33, 9)))[0].to_vec(), GRAD_1, "gradient 1-d");
    let h = hypot_a(&Array1::from(inp(34, 16)), &Array1::from(inp(35, 16)));
    same(&h.to_vec(), HYPOT, "hypot");
    let a = ndarray::arr2(&[[1, 2, 3], [4, 5, 6]]);
    assert_eq!(roll(&a, 1, 1), ndarray::arr2(&[[3, 1, 2], [6, 4, 5]]));
    assert_eq!(roll(&a, -1, 0), ndarray::arr2(&[[4, 5, 6], [1, 2, 3]]));
    assert_eq!(pad(&a, &[(1, 0), (0, 2)], Pad::Constant(0)), ndarray::arr2(&[[0, 0, 0, 0, 0], [1, 2, 3, 0, 0], [4, 5, 6, 0, 0]]));
    assert_eq!(pad(&a, &[(0, 1), (1, 1)], Pad::Edge), ndarray::arr2(&[[1, 1, 2, 3, 3], [4, 4, 5, 6, 6], [4, 4, 5, 6, 6]]));
    let c = ndarray::arr2(&[[false, true], [true, true]]);
    assert_eq!(nonzero(&c), vec![vec![0, 1, 1], vec![1, 0, 1]]);
    let w = where_(&c, &ndarray::arr2(&[[1, 2], [3, 4]]), &ndarray::arr2(&[[9, 9], [9, 9]]));
    assert_eq!(w, ndarray::arr2(&[[9, 2], [3, 4]]));
    assert_eq!(broadcast_shape(&[3, 1], &[4]).unwrap(), vec![3, 4]);
}
