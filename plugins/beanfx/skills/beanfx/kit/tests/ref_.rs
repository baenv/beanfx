//! Port of tests/test_ref.py: rf::trace on a drawn sword: the mask, value levels, derivative edges, skeleton and paint.

mod common;

use beanfx::img;
use beanfx::ndarray::{Array2, Array3};
use beanfx::rf::{self, Paint, Trace};

const H: usize = 60;
const W: usize = 200;
// (y0..y1, x0..x1)
const BLADE: (usize, usize, usize, usize) = (26, 35, 20, 150);
const RIDGE: (usize, usize, usize, usize) = (30, 31, 22, 148);
const GUARD: (usize, usize, usize, usize) = (14, 47, 150, 156);
const GRIP: (usize, usize, usize, usize) = (27, 34, 156, 186);

fn fill(a: &mut Array3<u8>, r: (usize, usize, usize, usize), c: [u8; 4]) {
    for y in r.0..r.1 {
        for x in r.2..r.3 {
            for (k, v) in c.iter().enumerate() {
                a[[y, x, k]] = *v;
            }
        }
    }
}

fn sword(bg: [u8; 4]) -> Array3<u8> {
    let mut a = Array3::from_shape_fn((H, W, 4), |(_, _, c)| bg[c]);
    fill(&mut a, BLADE, [215, 220, 230, 255]);
    fill(&mut a, RIDGE, [90, 95, 110, 255]);
    fill(&mut a, GUARD, [170, 120, 50, 255]);
    fill(&mut a, GRIP, [60, 35, 25, 255]);
    a
}

#[test]
fn trace_a_sword_on_plain_ground_and_on_alpha() {
    let mut shape = Array2::from_elem((H, W), false);
    for r in [BLADE, GUARD, GRIP] {
        for y in r.0..r.1 {
            for x in r.2..r.3 {
                shape[[y, x]] = true;
            }
        }
    }
    let dir = common::tmpdir("ref");
    for (tag, bg) in [("plain ground", [250, 250, 245, 255]), ("alpha", [0, 0, 0, 0])] {
        let p = dir.join(format!("{}.png", tag.replace(' ', "_")));
        img::write(&p, &sword(bg).view()).unwrap();
        let t = rf::trace(&p, Trace { tones: 4, ..Default::default() }).unwrap();
        let (mut inter, mut union) = (0.0, 0.0);
        for (ix, &m) in t.mask.indexed_iter() {
            inter += (m && shape[ix]) as u8 as f64;
            union += (m || shape[ix]) as u8 as f64;
        }
        assert!(inter / union > 0.98, "{tag}: mask iou {}", inter / union);
        assert!(t.shade[[28, 80]] > t.shade[[30, 170]] && t.shade[[28, 80]] == 3, "{tag}: blade lighter than grip {} vs {}", t.shade[[28, 80]], t.shade[[30, 170]]);
        assert!(t.shade[[30, 80]] < t.shade[[28, 80]], "{tag}: ridge darker than the blade");
        let ridge = (40..140).filter(|&x| (29..32).any(|y| t.edges[[y, x]])).count() as f64 / 100.0;
        assert!(ridge > 0.95, "{tag}: the ridge shows in the edges: {ridge}");
        assert!((40..140).all(|x| t.edges[[26, x]]) && !(0..W).any(|x| t.edges[[0, x]]), "{tag}: rim on, background off");
        let sp = t.spine.iter().max_by_key(|s| s.nrows()).unwrap();
        let xs: Vec<f64> = sp.column(0).to_vec();
        let span = xs.iter().cloned().fold(f64::MIN, f64::max) - xs.iter().cloned().fold(f64::MAX, f64::min);
        assert!(span > 120.0, "{tag}: skeleton runs the blade, span {span}");
        assert!(t.outline.nrows() > 50, "{tag}: outline points");
        let m = rf::paint(&t, Paint { ramp_index: Some(vec![1, 2, 3, 4]), edge: Some(0) }).unwrap();
        let mut seen = std::collections::BTreeSet::new();
        for (ix, &v) in m.indexed_iter() {
            if t.mask[ix] {
                seen.insert(v);
            }
        }
        assert!(m[[0, 0]] == -1 && (m[[28, 80]] == 0 || m[[28, 80]] == 4) && seen.iter().all(|v| (0..=4).contains(v)), "{tag}: paint indices {seen:?}");
    }
    // scaling: a half size trace keeps the shape
    let t2 = rf::trace(dir.join("alpha.png"), Trace { height: Some(30), ..Default::default() }).unwrap();
    let share = |m: &Array2<bool>| m.iter().filter(|&&v| v).count() as f64 / m.len() as f64;
    assert_eq!(t2.mask.dim(), (30, 100), "half size mask shape");
    assert!((share(&t2.mask) - share(&shape)).abs() < 0.03, "half size mask share");
    std::fs::remove_dir_all(&dir).ok();
}
