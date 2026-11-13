//! Port of tests/test_light.py: flashes that die, flicker that is seeded and varied, and a clear scene stays mostly dark.

use beanfx::fl::wgrid;
use beanfx::lt::{self, Canvas, Flashes, Flicker, Steps};
use beanfx::ndarray::Array2;

fn canvas() -> Canvas {
    // the python grid is mgrid + 0.5 over 64 x 64
    let (x, y) = wgrid(64, 64, 0.0, 0.0, 1.0);
    Canvas { x, y }
}

fn max(l: &Array2<f64>) -> f64 {
    l.iter().cloned().fold(f64::NEG_INFINITY, f64::max)
}

#[test]
fn grid_is_pixel_centres() {
    let c = canvas();
    assert_eq!((c.x[[0, 0]], c.y[[0, 0]], c.x[[3, 7]], c.y[[3, 7]]), (0.5, 0.5, 7.5, 3.5));
}

#[test]
fn flash_is_born_dims_shrinks_and_dies() {
    let c = canvas();
    let mut fl = Flashes::new();
    fl.add(32.5, 32.5, 10.0, 0.6, 6.0);
    let (mut peaks, mut reach) = (vec![], vec![]);
    for _ in 0..8 {
        let mut l = lt::buffer(&c);
        fl.draw(&mut l, &c);
        peaks.push(max(&l));
        reach.push(l.iter().filter(|&&v| v > 0.01).count());
        fl.step();
    }
    assert!((peaks[0] - 0.6).abs() < 0.05, "a new flash starts at its k: {}", peaks[0]);
    assert!(peaks[..6].windows(2).all(|w| w[0] > w[1]), "a flash dims every frame: {peaks:?}");
    assert!(reach[..6].windows(2).all(|w| w[0] >= w[1]) && reach[5] < reach[0], "a flash shrinks: {reach:?}");
    assert!(peaks[6] == 0.0 && fl.list.is_empty(), "a flash is gone after its life");
}

#[test]
fn flash_at_matches_flashes() {
    let c = canvas();
    let mut fl = Flashes::new();
    for f in 0..10 {
        if f == 2 {
            fl.add(20.5, 30.5, 9.0, 0.5, 5.0);
        }
        let mut a = lt::buffer(&c);
        fl.draw(&mut a, &c);
        fl.step();
        let mut b = lt::buffer(&c);
        lt::flash_at(&mut b, &c, f as f64, 2.0, 20.5, 30.5, 9.0, 0.5, 5.0);
        assert!(a.iter().zip(b.iter()).all(|(p, q)| (p - q).abs() < 1e-8), "flash_at matches Flashes at frame {f}");
    }
    let mut b = lt::buffer(&c);
    lt::flash_at(&mut b, &c, 1.0, 2.0, 20.5, 30.5, 9.0, 0.5, 5.0);
    assert_eq!(max(&b), 0.0, "flash_at is dark before its birth frame");
}

fn flick(seed: i64) -> Vec<f64> {
    (0..40).flat_map(|i| (0..30).map(move |f| lt::flicker(i, f as f64, Flicker { seed, rate: 1.0 }))).collect()
}

#[test]
fn flicker_is_seeded_varied_and_holds_at_rate_zero() {
    let a = flick(3);
    assert!(a.iter().all(|&v| (0.0..=1.0).contains(&v)), "flicker stays in 0..1");
    assert_eq!(a, flick(3), "flicker repeats for a seed");
    assert_ne!(a, flick(4), "another seed flickers differently");
    let rows: Vec<&[f64]> = a.chunks(30).collect();
    let mut s = 0.0;
    let mut n = 0.0;
    for r in &rows {
        for w in r.windows(2) {
            s += (w[1] - w[0]).abs();
            n += 1.0;
        }
    }
    assert!(s / n > 0.15, "flicker changes frame to frame: {}", s / n);
    let col: Vec<f64> = rows.iter().map(|r| r[0]).collect();
    let mean = col.iter().sum::<f64>() / col.len() as f64;
    let std = (col.iter().map(|v| (v - mean) * (v - mean)).sum::<f64>() / col.len() as f64).sqrt();
    assert!(std > 0.15, "sparks flicker out of step: {std}");
    let z = |f: f64| lt::flicker(5, f, Flicker { seed: 3, rate: 0.0 });
    assert_eq!(z(7.0), z(8.0), "rate 0 holds still");
}

#[test]
fn clear_scene_stays_mostly_dark() {
    let c = canvas();
    let mut l = lt::buffer(&c);
    lt::glow(&mut l, &c, 20.0, 20.0, 6.0, 0.6);
    lt::glow_line(&mut l, &c, (40.0, 10.0), (40.0, 50.0), 3.0, 0.4);
    let share = l.iter().filter(|&&v| v > 0.03).count() as f64 / l.len() as f64;
    assert!(share < 0.25, "a clear scene lights under a quarter of its box: {share:.2}");
}

#[test]
fn steps_are_flat_hard_and_dithered_only_outside() {
    let c = canvas();
    let mut l = lt::buffer(&c);
    lt::glow(&mut l, &c, 32.5, 32.5, 24.0, 1.0);
    let s = lt::steps(&l, Steps { levels: 4.0, floor: 0.06, phase: (0, 0) });
    for &v in s.iter() {
        assert!([0.0, 0.25, 0.5, 0.75, 1.0].iter().any(|t| (v - t).abs() < 1e-6), "steps gives only the step values: {v}");
    }
    assert_eq!(max(&s), 1.0, "steps keeps a white-hot core");
    let mut outer_lit = vec![];
    let (mut near, mut far) = ((0.0, 0.0), (0.0, 0.0));
    for ((y, x), &v) in l.indexed_iter() {
        let sv = s[[y, x]];
        if v < 0.06 {
            assert_eq!(sv, 0.0, "steps is dark below the floor");
        }
        if v >= 0.25 {
            assert_eq!(sv, (v * 4.0 + 1e-9).floor() / 4.0, "steps is hard inside the light, no dither");
        }
        if (0.06..0.25).contains(&v) {
            outer_lit.push(sv > 0.0);
            if v > 0.2 { near = (near.0 + sv, near.1 + 1.0); }
            if v < 0.1 { far = (far.0 + sv, far.1 + 1.0); }
        }
    }
    let lit = outer_lit.iter().filter(|&&b| b).count() as f64 / outer_lit.len() as f64;
    assert!(0.1 < lit && lit < 0.9, "the outer step is dithered: {lit:.2} lit");
    assert!(near.0 / near.1 > far.0 / far.1, "the dither thins out as the light fades");
    assert_ne!(lt::steps(&l, Steps { phase: (1, 0), ..Default::default() }), s, "phase moves the dither grid");
}

#[test]
fn glow_levels_grow_from_subtle_to_strong() {
    let lv: Vec<_> = ["subtle", "medium", "strong"].iter().map(|k| lt::glow_level(k).unwrap()).collect();
    assert!(lv.windows(2).all(|w| w[0].pool_k < w[1].pool_k && w[0].mean.1 <= w[1].mean.1));
    assert!(lt::glow_level("blinding").is_none());
}
