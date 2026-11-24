//! mo (closed-form motion), dr::par and pfx::recolour.

use beanfx::dr::{self, Canvas};
use beanfx::mo::{self, Ground};
use ndarray::Array3;

#[test]
fn fly_matches_small_steps() {
    // closed form against 1/10000 s Euler steps of dv = (g - k v) dt
    let (p0, v0, g, k, t) = ([3.0, 5.0], [80.0, -120.0], 300.0, 2.5, 0.8);
    let (mut p, mut v) = (p0, v0);
    let dt = 1e-4;
    for _ in 0..(t / dt) as usize {
        v = [v[0] - k * v[0] * dt, v[1] + (g - k * v[1]) * dt];
        p = [p[0] + v[0] * dt, p[1] + v[1] * dt];
    }
    let (q, w) = mo::fly(p0, v0, g, k, t);
    for i in 0..2 {
        assert!((q[i] - p[i]).abs() < 0.05, "pos {i}: {} vs {}", q[i], p[i]);
        assert!((w[i] - v[i]).abs() < 0.1, "vel {i}: {} vs {}", w[i], v[i]);
    }
    // no drag is plain ballistic; t <= 0 is the start
    assert_eq!(mo::fly([0.0, 0.0], [10.0, 0.0], 20.0, 0.0, 2.0).0, [20.0, 40.0]);
    assert_eq!(mo::fly(p0, v0, g, k, -1.0), (p0, v0));
}

#[test]
fn fly_ground_bounces_then_rests() {
    let gr = Ground { y: 50.0, ..Default::default() };
    let (p, _, hits) = mo::fly_ground([0.0, 40.0], [30.0, -60.0], 400.0, 1.0, 0.1, gr);
    assert!(p[1] < 50.0 && hits == 0, "still in the air: {p:?}");
    let (p, v, hits) = mo::fly_ground([0.0, 40.0], [30.0, -60.0], 400.0, 1.0, 5.0, gr);
    assert!(hits >= 1 && p[1] == 50.0 && v == [0.0, 0.0], "rests on the floor: {p:?} {v:?} {hits}");
    for i in 0..60 {
        let (p, _, _) = mo::fly_ground([0.0, 40.0], [30.0, -60.0], 400.0, 1.0, i as f64 / 24.0, gr);
        assert!(p[1] <= 50.0 + 1e-9, "never under the floor at frame {i}: {p:?}");
    }
}

#[test]
fn cycle_ages_in_range() {
    let mut alive = 0;
    for i in 0..20 {
        if let Some(a) = mo::cycle(7, i, 1.0, 0.1, 0.5) {
            assert!((0.0..1.0).contains(&a));
            alive += 1;
        }
    }
    assert!((3..=7).contains(&alive), "about life / every alive: {alive}");
}

#[test]
fn burst_draws_and_is_pure() {
    let fire = dr::ramp(&["#3a1020", "#8a2a18", "#d0501c", "#f09030", "#ffd060", "#fff4d0"]);
    let smoke = dr::ramp(&["#2a2430", "#4a4250", "#6e6676", "#9a92a0"]);
    let draw = |t: f64| {
        let mut cv = Canvas::new(64, 64);
        mo::burst(&mut cv, 7, [32.0, 40.0], t, &fire, &smoke, &Default::default());
        cv.cel()
    };
    let (a, b) = (draw(0.3), draw(0.3));
    assert_eq!(a.col, b.col);
    assert!(a.col.iter().any(|&v| v > 0), "draws colour");
    assert!(a.light.iter().any(|&v| v > 0.0), "flames carry light");
    assert!(draw(-0.1).col.iter().all(|&v| v == 0), "nothing before the burst");
}

#[test]
fn par_keeps_order_and_first_error() {
    let got = dr::par(200, |i| Ok(i * i)).unwrap();
    assert_eq!(got, (0..200).map(|i| i * i).collect::<Vec<_>>());
    let e = dr::par(50, |i| if i == 7 || i == 30 { Err(format!("bad {i}")) } else { Ok(i) }).unwrap_err();
    assert_eq!(e, "bad 7");
    assert!(dr::par(0, |i| Ok(i)).unwrap().is_empty());
}

#[test]
fn recolour_maps_tones_blends_and_keeps_the_rest() {
    let mut f = Array3::<u8>::zeros((1, 5, 4));
    let px = [[255, 0, 0, 255], [0, 0, 255, 255], [128, 0, 128, 200], [0, 255, 0, 255], [9, 9, 9, 0]];
    for (x, p) in px.iter().enumerate() {
        for k in 0..4 {
            f[[0, x, k]] = p[k];
        }
    }
    let (g, kept) = beanfx::pfx::recolour(&f, &["#ff0000", "#0000ff"], &["#000000", "#ffffff"]).unwrap();
    let at = |x: usize| [g[[0, x, 0]], g[[0, x, 1]], g[[0, x, 2]], g[[0, x, 3]]];
    assert_eq!(at(0), [0, 0, 0, 255], "first tone");
    assert_eq!(at(1), [255, 255, 255, 255], "last tone");
    assert_eq!(at(2), [128, 128, 128, 200], "the blend half way, alpha kept");
    assert_eq!(at(3), [0, 255, 0, 255], "off the ramp: kept");
    assert_eq!(at(4), [9, 9, 9, 0], "transparent untouched");
    assert_eq!(kept, 1);
    assert!(beanfx::pfx::recolour(&f, &["#ff0000"], &["#000000"]).is_err());
}
