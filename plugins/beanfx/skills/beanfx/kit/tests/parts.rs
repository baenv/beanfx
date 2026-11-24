//! mo (debris, brands, scorch, dust), pt (tilted ring halves, crystal, frost), cs::stepped and the spill message.
//! Before/after: every new call draws nothing before its start or at zero growth (the frame as it was), the
//! stepped pose at full rate is the old pose, and the edge failure keeps its old wording with the numbers added.

use beanfx::dr::{self, hex, Canvas};
use beanfx::ndarray::{Array2, Array3};
use beanfx::{cs, ex, mo, pt};

const FIRE: [&str; 6] = ["#3a1020", "#8a2a18", "#d0501c", "#f09030", "#ffd060", "#fff4d0"];

fn blank(cel: &dr::Cel) -> bool {
    cel.col.iter().all(|&v| v == 0) && cel.light.iter().all(|&v| v == 0.0)
}

fn rgb_at(cel: &dr::Cel, y: usize, x: usize) -> [u8; 4] {
    [cel.col[[y, x, 0]], cel.col[[y, x, 1]], cel.col[[y, x, 2]], cel.col[[y, x, 3]]]
}

#[test]
fn landed_at_is_where_the_first_landing_happens() {
    let gr = mo::Ground { y: 50.0, ..Default::default() };
    let (p0, v0) = ([0.0, 40.0], [20.0, -50.0]);
    let tl = mo::landed_at(p0, v0, 300.0, 1.0, gr, 3.0).unwrap();
    assert_eq!(mo::fly_ground(p0, v0, 300.0, 1.0, tl - 1e-6, gr).2, 0, "in the air just before");
    assert!(mo::fly_ground(p0, v0, 300.0, 1.0, tl + 1e-6, gr).2 >= 1, "landed just after");
    assert!(mo::landed_at(p0, v0, 300.0, 1.0, gr, 0.05).is_none(), "not yet");
}

#[test]
fn debris_brands_and_scorch_draw_nothing_before_the_blast() {
    let fire = dr::ramp(&FIRE);
    let smoke = dr::ramp(&["#2a2430", "#4a4250", "#6e6676", "#9a92a0"]);
    let rock = [hex("#1a1418"), hex("#4a3a3a"), hex("#7a6458"), hex("#a89080")];
    let draw = |t: f64| {
        let mut cv = Canvas::new(96, 64);
        mo::scorch(&mut cv, 7, [48.0, 52.0], 12.0, 3.0, t / 1.2, &fire, hex("#1a1418"));
        mo::chunks(&mut cv, 7, [48.0, 50.0], t, rock, &smoke, &mo::Chunks { ground: mo::Ground { y: 52.0, ..Default::default() }, ..Default::default() });
        mo::brands(&mut cv, 7, [48.0, 46.0], t, &fire, &mo::Brands { ground: mo::Ground { y: 52.0, bounce: 0.2, ..Default::default() }, ..Default::default() });
        cv.cel()
    };
    assert!(blank(&draw(-0.01)), "before the blast: the frame as it was");
    let mid = draw(0.3);
    assert!(!blank(&mid));
    assert_eq!(mid.col, draw(0.3).col, "pure in time");
}

#[test]
fn a_scorch_cools_to_soot_and_holds() {
    let fire = dr::ramp(&FIRE);
    let at = |age: f64| {
        let mut cv = Canvas::new(48, 16);
        mo::scorch(&mut cv, 3, [24.0, 8.0], 14.0, 4.0, age, &fire, hex("#1a1418"));
        cv.cel()
    };
    let (hot, end, later) = (at(0.0), at(1.0), at(3.0));
    assert_eq!(end.col, later.col, "after it cools the mark holds");
    let centre = rgb_at(&hot, 8, 24);
    assert_eq!(&centre[..3], &[0xff, 0xf4, 0xd0], "white-hot at the blast");
    let c = rgb_at(&end, 8, 24);
    assert!(c[3] > 0 && c[0] < 0x30 && c[1] < 0x30, "soot in the middle at the end: {c:?}");
    let fires: Vec<[u8; 3]> = FIRE.iter().map(|h| { let v = hex(h); v.map(|x| (x * 255.0).round() as u8) }).collect();
    assert!(end.col.outer_iter().flat_map(|r| r.outer_iter().map(|p| [p[0], p[1], p[2], p[3]]).collect::<Vec<_>>())
        .all(|p| p[3] == 0 || !fires.contains(&[p[0], p[1], p[2]])), "no fire colour left once cooled");
}

#[test]
fn a_chunk_is_lit_from_the_top_left() {
    let mut cv = Canvas::new(32, 32);
    let shades = [hex("#101010"), hex("#404040"), hex("#808080"), hex("#e0e0e0")];
    mo::chunk(&mut cv, [16.0, 16.0], 10.0, 0.0, shades, 1.0);
    let c = cv.cel();
    let (lit, dark) = (rgb_at(&c, 13, 13)[0], rgb_at(&c, 19, 19)[0]);
    assert!(lit > dark, "top left {lit} brighter than bottom right {dark}");
    assert_eq!(rgb_at(&c, 16, 7)[0], 0x10, "dark rim at the left corner");
}

#[test]
fn dust_lives_its_age_only() {
    let ramp = dr::ramp(&["#3a3430", "#6a6058", "#9a9088"]);
    for (age, drawn) in [(-0.1, false), (0.0, true), (0.5, true), (1.0, false)] {
        let mut cv = Canvas::new(32, 16);
        mo::dust(&mut cv, 1, [16.0, 14.0], age, 3.0, &ramp);
        assert_eq!(!blank(&cv.cel()), drawn, "age {age}");
    }
}

#[test]
fn ring_halves_add_up_to_the_whole_ring() {
    let draw = |half| {
        let mut cv = Canvas::new(48, 24);
        pt::ring(&mut cv, [24.0, 12.0], 16.0, 2.0, 0.4, half, hex("#204080"), hex("#80c0ff"), 1.0);
        cv.cel().col
    };
    let (all, far, near) = (draw(pt::Half::All), draw(pt::Half::Far), draw(pt::Half::Near));
    for y in 0..24 {
        for x in 0..48 {
            let (a, f, n) = (all[[y, x, 3]] > 0, far[[y, x, 3]] > 0, near[[y, x, 3]] > 0);
            assert_eq!(a, f || n, "({y},{x}) in the ring iff in one half");
            assert!(!(f && n), "({y},{x}) in both halves");
            assert!(!f || (y as f64 + 0.5) < 12.0, "far half above the centre");
        }
    }
    // depth shade: the near edge brighter than the far edge
    let col_at = |y: usize| (0..48).filter(|&x| all[[y, x, 3]] > 0).map(|x| all[[y, x, 2]]).max().unwrap_or(0);
    assert!(col_at(17) > col_at(6), "near {} brighter than far {}", col_at(17), col_at(6));
}

#[test]
fn ring_glow_halves_split_the_light() {
    let light = |half| {
        let mut cv = Canvas::new(48, 24);
        pt::ring_glow(&mut cv, [24.0, 12.0], 14.0, 0.4, 3.0, 0.3, half);
        cv.cel().light
    };
    let (all, far, near) = (light(pt::Half::All), light(pt::Half::Far), light(pt::Half::Near));
    assert!(all.iter().zip(far.iter().zip(near.iter())).all(|(a, (f, n))| (a - (f + n)).abs() < 1e-12));
    assert!(far.iter().any(|&v| v > 0.0) && near.iter().any(|&v| v > 0.0));
}

#[test]
fn a_crystal_has_a_lit_and_a_dark_face_and_a_moving_glint() {
    let shades = [hex("#101830"), hex("#2a4a90"), hex("#8ad0ff"), hex("#ffffff")];
    let draw = |g| {
        let mut cv = Canvas::new(32, 40);
        pt::crystal(&mut cv, [16.0, 36.0], 30.0, 12.0, 0.0, shades, g, 1.0);
        cv.cel()
    };
    let c = draw(None);
    let (left, right) = (rgb_at(&c, 26, 13), rgb_at(&c, 26, 19));
    assert!(left[2] > right[2] && left[0] > right[0], "left face lit {left:?}, right dark {right:?}");
    assert_eq!(rgb_at(&c, 6, 16)[..3], [255, 255, 255], "white tip");
    let (lo, hi) = (draw(Some(0.2)), draw(Some(0.7)));
    assert_ne!(lo.col, hi.col, "the glint moves up");
    assert!(lo.light.iter().any(|&v| v > 0.0), "the glint carries light");
    assert!(c.light.iter().all(|&v| v == 0.0), "no light without a glint");
}

#[test]
fn edge_depth_counts_steps_in_from_the_edge() {
    let m = Array2::from_shape_fn((7, 7), |(y, x)| (1..6).contains(&y) && (1..6).contains(&x));
    let d = pt::edge_depth(&m);
    assert_eq!(d[[0, 0]], 0);
    assert_eq!(d[[1, 1]], 1);
    assert_eq!(d[[1, 3]], 1);
    assert_eq!(d[[2, 2]], 2);
    assert_eq!(d[[3, 3]], 3);
    let full = Array2::from_elem((3, 3), true);
    assert_eq!(pt::edge_depth(&full)[[1, 1]], 2, "the image border counts as outside");
}

#[test]
fn frost_grows_on_the_body_and_icicles_hang_below_it() {
    let (h, w) = (40, 32);
    let body = Array3::from_shape_fn((h, w, 4), |(y, x, c)| {
        let inside = (8..24).contains(&x) && (6..26).contains(&y);
        if !inside { 0 } else if c == 3 { 255 } else { 100 }
    });
    let shades = [hex("#3a6ab0"), hex("#8ad0ff"), hex("#ffffff")];
    let draw = |g| {
        let mut cv = Canvas::new(w, h);
        pt::frost(&mut cv, 5, &body, g, shades, pt::Frost::default());
        cv.cel().col
    };
    assert!(draw(0.0).iter().all(|&v| v == 0), "no growth: the frame as it was");
    let f = draw(1.0);
    let mut below = 0;
    for y in 0..h {
        for x in 0..w {
            if f[[y, x, 3]] == 0 {
                continue;
            }
            let on_body = body[[y, x, 3]] > 0;
            let icicle = !on_body && (8..24).contains(&x) && (26..26 + 5).contains(&y);
            assert!(on_body || icicle, "frost at ({y},{x}) is on the body or an icicle under its bottom edge");
            below += icicle as usize;
        }
    }
    assert!(below > 0, "icicles hang below");
    assert!(f[[16, 16, 3]] == 0, "the middle of the body stays clear at default depth");
    let half = draw(0.5).iter().filter(|&&v| v > 0).count();
    assert!(half < f.iter().filter(|&&v| v > 0).count(), "more frost as it grows");
}

#[test]
fn stepped_limbs_snap_to_the_slower_beat() {
    assert_eq!(cs::stepped(7.0, 24.0, 12.0), 6.0);
    assert_eq!(cs::stepped(6.0, 24.0, 12.0), 6.0);
    assert_eq!(cs::stepped(11.9, 24.0, 8.0), 9.0);
    // before/after: at the sheet's own rate (or 0) the pose is the old pose
    for f in [0.0, 3.5, 7.0, 13.0] {
        assert_eq!(cs::stepped(f, 24.0, 24.0), f);
        assert_eq!(cs::stepped(f, 24.0, 0.0), f);
        let keys = [(0.0, "rest"), (12.0, "raise")];
        assert_eq!(cs::pose_at(cs::stepped(f, 24.0, 24.0), &keys, &[(0.0, "rest")], None, 0.0).unwrap(),
                   cs::pose_at(f, &keys, &[(0.0, "rest")], None, 0.0).unwrap());
    }
}

#[test]
fn an_edge_failure_says_where_and_how_much() {
    let (h, w) = (8, 10);
    let mut fr = Array3::<u8>::zeros((h, w, 4));
    for y in 2..6 {
        for x in 0..4 {
            fr[[y, x, 3]] = 255;
        }
    }
    let msgs = ex::check(&vec![fr.clone(), fr], ex::Check { looped: true, ..Default::default() }).unwrap();
    let m = msgs.iter().find(|m| m.contains("touches the edge")).expect("an edge failure");
    assert!(m.starts_with("frame 0: colour touches the edge ("), "old wording kept: {m}");
    assert!(m.contains("4 px on the left border"), "{m}");
    assert!(m.contains("x 0..3, y 2..5 of 10x8"), "{m}");
    let on: Vec<bool> = (0..h * w).map(|p| p / w == 7 && p % w == 9 || p / w == 0 && p % w == 5).collect();
    assert_eq!(ex::spill(&on, h, w), "2 px on the top and right and bottom border; the drawing fills x 5..9, y 0..7 of 10x8");
}
