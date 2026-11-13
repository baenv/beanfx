//! Port of tests/test_impact.py (fk::ground_impact): nothing before contact, more of everything as the weight
//! rises, cracks only for heavy blows, debris that flies, lands and rests, an empty cell at the end of life, and the
//! same frames for the same seed.

use beanfx::fk::{ground_impact, GroundImpact, Weight};
use beanfx::fl::wgrid;
use beanfx::ndarray::Array2;

const W: usize = 128;
const H: usize = 80;
const FPS: f64 = 24.0;
const GY: usize = 60;
const TONES: [i8; 3] = [1, 2, 3];
const DUST: [i8; 3] = [4, 5, 6];

fn frame(f: i64, weight: Weight, seed: f64, life: f64) -> Array2<i8> {
    let (x, y) = wgrid(W, H, W as f64 / 2.0, GY as f64, 1.0);
    let mut m = Array2::from_elem((H, W), -1i8);
    ground_impact(&mut m, &x, &y, f, FPS, &TONES, &DUST, GroundImpact { r: 12.0, weight, life, seed, ..Default::default() });
    m
}

fn fr(f: i64, w: Weight) -> Array2<i8> {
    frame(f, w, 3.0, 1.2)
}

fn count(m: &Array2<i8>) -> usize {
    m.iter().filter(|&&v| v >= 0).count()
}

const WEIGHTS: [Weight; 3] = [Weight::Light, Weight::Heavy, Weight::Finisher];

#[test]
fn nothing_before_contact_something_on_it() {
    assert!(fr(-1, Weight::Heavy).iter().all(|&v| v < 0), "nothing before contact");
    assert!(count(&fr(0, Weight::Heavy)) > 0, "something on the contact frame");
}

#[test]
fn more_of_everything_as_weight_rises() {
    let busy = |w: Weight| (0..12).map(|f| count(&fr(f, w))).sum::<usize>();
    let b: Vec<usize> = WEIGHTS.iter().map(|&w| busy(w)).collect();
    assert!(b[0] < b[1] && b[1] < b[2], "light < heavy < finisher: {b:?}");
}

#[test]
fn debris_flies_higher_with_weight() {
    let peak = |w: Weight| {
        let mut top = H;
        for f in 0..12 {
            let m = fr(f, w);
            for (y, row) in m.rows().into_iter().enumerate() {
                if row.iter().any(|&v| v == TONES[1] || v == TONES[2]) {
                    top = top.min(y);
                    break;
                }
            }
        }
        GY as i64 - top as i64
    };
    let p: Vec<i64> = WEIGHTS.iter().map(|&w| peak(w)).collect();
    assert!(p[0] < p[1] && p[1] < p[2], "debris flies higher with weight: {p:?}");
}

#[test]
fn cracks_only_for_heavy_blows_and_stay() {
    let has = |m: &Array2<i8>| m.iter().any(|&v| v == TONES[0]);
    assert!(!has(&fr(4, Weight::Light)), "a light hit leaves no crack");
    assert!(has(&fr(4, Weight::Heavy)) && has(&fr(14, Weight::Heavy)), "a heavy hit cracks and it stays");
}

#[test]
fn debris_rests_and_dust_breaks_up() {
    let late: Vec<Array2<i8>> = [20, 21].iter().map(|&f| frame(f, Weight::Finisher, 3.0, 2.0)).collect();
    let deb: Vec<Array2<bool>> = late.iter().map(|m| m.mapv(|v| TONES[1..].contains(&v))).collect();
    assert!(deb[0].iter().any(|&v| v) && deb[0] == deb[1], "debris lies still once it lands");
    assert!(!fr(15, Weight::Finisher).iter().any(|v| DUST.contains(v)), "dust has broken up by half its life (0.6 s)");
    for d in &deb {
        for ((y, _), &v) in d.indexed_iter() {
            assert!(!v || y >= GY - 4, "resting debris sits on the ground (row {y})");
        }
    }
}

#[test]
fn ends_empty_and_is_seeded() {
    let end = (1.2 * FPS).ceil() as i64;
    assert!(fr(end, Weight::Finisher).iter().all(|&v| v < 0), "empty at the end of life");
    let a = frame(5, Weight::Heavy, 7.0, 1.2);
    assert_eq!(a, frame(5, Weight::Heavy, 7.0, 1.2), "same seed repeats");
    assert_ne!(a, frame(5, Weight::Heavy, 8.0, 1.2), "other seed differs");
}

#[test]
fn stays_inside_the_cell() {
    for f in 0..(1.2 * FPS) as i64 {
        let m = fr(f, Weight::Finisher);
        for ((y, x), &v) in m.indexed_iter() {
            let edge = !(2..H - 2).contains(&y) || !(2..W - 2).contains(&x);
            assert!(!(edge && v >= 0), "frame {f}: pixel on the outer 2 px at ({x},{y})");
        }
    }
}
