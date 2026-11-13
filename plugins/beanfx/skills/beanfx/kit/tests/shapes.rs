//! Port of tests/test_shapes.py: every painter in fk and fl draws something, draws the same pixels on a second call
//! (no hidden randomness), keeps to the shades it was given, and holds the few rules a drawing leans on (a dissolve
//! only removes, a hit ends empty, a puff breaks up from its edge); the mockup caster in cs draws a figure.

use std::collections::BTreeSet;
use std::f64::consts::PI;

use beanfx::cs;
use beanfx::fk::{self, *};
use beanfx::fl::{self, GroundRing};
use beanfx::ndarray::{Array2, Array3};

type Shade = Array2<i8>;
type Grid = Array2<f64>;

const W: usize = 64;
const H: usize = 48;

fn xy() -> (Grid, Grid) {
    fl::wgrid(W, H, (W / 2) as f64, (H / 2) as f64, 1.0)
}

fn count(m: &Shade) -> usize {
    m.iter().filter(|&&v| v >= 0).count()
}

fn used(m: &Shade) -> BTreeSet<i8> {
    m.iter().cloned().filter(|&v| v >= 0).collect()
}

fn rad(x: &Grid, y: &Grid) -> Grid {
    Array2::from_shape_fn(x.dim(), |p| x[p].hypot(y[p]))
}

fn sel(g: &Grid, m: impl Fn((usize, usize)) -> bool) -> Vec<f64> {
    g.indexed_iter().filter(|(p, _)| m(*p)).map(|(_, &v)| v).collect()
}

fn mean(v: &[f64]) -> f64 {
    v.iter().sum::<f64>() / v.len() as f64
}

fn maxf(v: &[f64]) -> f64 {
    v.iter().cloned().fold(f64::NEG_INFINITY, f64::max)
}

fn minf(v: &[f64]) -> f64 {
    v.iter().cloned().fold(f64::INFINITY, f64::min)
}

/// paint(m) draws into an empty map: something is drawn, a second run draws the same, only `shades` are used.
fn painted(name: &str, paint: impl Fn(&mut Shade), shades: &[i8], low: usize) -> Shade {
    let mut a = fl::empty(W, H);
    let mut b = fl::empty(W, H);
    paint(&mut a);
    paint(&mut b);
    assert!(count(&a) >= low, "{name} draws ({} px)", count(&a));
    assert_eq!(a, b, "{name} draws the same pixels twice");
    let u = used(&a);
    assert!(u.iter().all(|s| shades.contains(s)), "{name} keeps to its shades: {u:?} of {shades:?}");
    a
}

fn lum(hex: &str) -> f64 {
    let c = fl::hexc(hex).unwrap();
    0.299 * c[0] as f64 + 0.587 * c[1] as f64 + 0.114 * c[2] as f64
}

// ---- fl: colour, grids, strokes, noise ----

#[test]
fn fl_colour_and_grids() {
    let r = fl::ramp("#c83a1a").unwrap();
    let l: Vec<f64> = r.iter().map(|c| lum(c)).collect();
    assert!(r.len() == 4 && l.windows(2).all(|w| w[0] <= w[1]), "ramp gives four shades, dark to pale: {r:?}");
    let c = fl::hexc("#12ab9f").unwrap();
    assert_eq!(fl::tohex([c[0] as f64, c[1] as f64, c[2] as f64]), "#12ab9f", "hexc and tohex round trip");
    let (gx, gy) = fl::grid(8, 6, 3.0, 2.0);
    assert!(gx.dim() == (6, 8) && gx[[2, 3]] == 0.5 && gy[[2, 3]] == 0.5, "grid reads pixel centres relative to the pivot");
    let (wx, _) = fl::wgrid(16, 12, 8.0, 6.0, 2.0);
    assert!(((wx[[0, 1]] - wx[[0, 0]]) - 0.5).abs() < 1e-9, "wgrid at density 2 steps half a world px a pixel");
}

#[test]
fn fl_stroke_put_line_outline_stamp() {
    let (x, y) = xy();
    let (d, t, side) = fl::stroke(&x, &y, &[[-20.0, 0.0], [20.0, 0.0]], 6.0, 0.0);
    let on = |p: (usize, usize)| d[p] < 0.0;
    let left = d.indexed_iter().filter(|((_, c), &v)| v < 0.0 && *c < W / 2).count();
    let right = d.indexed_iter().filter(|((_, c), &v)| v < 0.0 && *c >= W / 2).count();
    assert!(d.indexed_iter().any(|(p, _)| on(p)) && left > right, "stroke tapers from its root to its tip");
    let ts = sel(&t, on);
    let sides = sel(&side, on);
    assert!(minf(&ts) >= 0.0 && maxf(&ts) <= 1.0 && sides.iter().any(|&v| v < 0.0) && sides.iter().any(|&v| v > 0.0),
            "stroke returns t along it and a side each way");

    let mut m = fl::empty(W, H);
    fl::put(&mut m, 5.0, 5.0, 2);
    fl::put(&mut m, -3.0, 5.0, 2); // off the map: ignored
    fl::put_max(&mut m, 5.0, 5.0, 1);
    assert!(m[[5, 5]] == 2 && count(&m) == 1, "put clips to the map and put_max keeps the brighter shade");
    fl::line(&mut m, 2.0, 20.0, 30.0, 20.0, 1, false);
    assert!((2..31).all(|c| m[[20, c]] == 1), "line joins its two ends");
    let ring = fl::outline(&m, 0);
    assert!(count(&ring) > count(&m) && m.indexed_iter().all(|(p, &v)| v < 0 || ring[p] == v), "outline adds a rim and leaves the drawing as it was");
    let mut dst = fl::empty(W, H);
    fl::stamp(&mut dst, &m, 4, -3);
    assert!(dst[[2, 9]] == 2 && count(&dst) <= count(&m), "stamp moves a map by its offset, clipped");
}

#[test]
fn fl_noise_checker_ground() {
    let (x, y) = xy();
    let n1 = fl::noise(&x, &y, 8.0, 5, None);
    assert!(minf(&n1.iter().cloned().collect::<Vec<_>>()) >= 0.0 && maxf(&n1.iter().cloned().collect::<Vec<_>>()) <= 1.0, "noise stays in 0..1");
    assert_eq!(n1, fl::noise(&x, &y, 8.0, 5, None), "noise repeats by seed");
    assert_ne!(n1, fl::noise(&x, &y, 8.0, 6, None), "another seed gives another noise");
    let per = fl::noise(&x, &y, 8.0, 5, Some((32.0, 32.0)));
    let (x32, y32) = (x.mapv(|v| v + 32.0), y.mapv(|v| v + 32.0));
    let per2 = fl::noise(&x32, &y32, 8.0, 5, Some((32.0, 32.0)));
    assert!(per.iter().zip(per2.iter()).all(|(a, b)| (a - b).abs() < 1e-8), "periodic noise wraps at its period");
    let ck = fl::checker(&x, &y, 0);
    assert!(ck[[0, 0]] != ck[[0, 1]] && ck[[0, 0]] != ck[[1, 0]], "checker alternates each pixel");
    let g = fl::ground_dist(&Array2::from_elem((1, 1), 10.0), &Array2::from_elem((1, 1), 0.0), 10.0, 4.0);
    assert!((g[[0, 0]] - 1.0).abs() < 1e-9, "ground_dist is 1 on the rim");
    painted("ground_ring", |q| fl::ground_ring(q, (W / 2) as f64, (H / 2) as f64, 20.0, 8.0, GroundRing { width: 3.0, shades: vec![1, 2, 3], ..Default::default() }), &[0, 1, 2, 3], 4);
}

#[test]
fn fl_impact_frames() {
    const PAL: [&str; 4] = ["#3a1408", "#c83a1a", "#f07c22", "#fff3c4"];
    let mut cell = Array3::<u8>::zeros((H, W, 4));
    let c1 = fl::hexc(PAL[1]).unwrap();
    for y in 16..32 {
        for x in 22..42 {
            for k in 0..3 { cell[[y, x, k]] = c1[k]; }
            cell[[y, x, 3]] = 255;
        }
    }
    let mean_rgb = |a: &Array3<u8>, on: &Array3<u8>| {
        let (mut s, mut n) = (0.0, 0.0);
        for y in 0..H { for x in 0..W { if on[[y, x, 3]] > 0 { for k in 0..3 { s += a[[y, x, k]] as f64; n += 1.0; } } } }
        s / n
    };
    let alpha = |a: &Array3<u8>| (0..H).flat_map(|y| (0..W).map(move |x| (y, x))).filter(|&(y, x)| a[[y, x, 3]] > 0).count();
    let hot = fl::heat(&cell, &PAL, 2, 0.0).unwrap();
    assert!(hot.dim() == cell.dim() && mean_rgb(&hot, &cell) > mean_rgb(&cell, &cell), "heat moves a cell toward white");
    let small = fl::contract(&cell, ((W / 2) as f64, (H / 2) as f64), 0.6);
    assert!(alpha(&small) > 0 && alpha(&small) < alpha(&cell), "contract shrinks a cell toward its pivot");
    let order = fl::impact_order(8, 3, 2);
    assert!(order.len() == 8 && *order.iter().max().unwrap() < 8, "impact_order names a source frame per slot: {order:?}");
    let bx = [4usize, 44, 8, 56]; // y0, y1, x0, x1: the bounds the rays may reach
    let rays = fl::flash_rays(&hot, &PAL, 1, bx, 4).unwrap();
    assert!(alpha(&rays) > alpha(&hot), "flash_rays adds streaks round the hot cell");
    assert_eq!(rays, fl::flash_rays(&hot, &PAL, 1, bx, 4).unwrap(), "flash_rays repeats by seed");
    let pts: Vec<(usize, usize)> = (0..H).flat_map(|y| (0..W).map(move |x| (y, x))).filter(|&(y, x)| rays[[y, x, 3]] > 0).collect();
    assert!(pts.iter().all(|&(y, x)| y >= bx[0] && y <= bx[1] && x >= bx[2] && x <= bx[3]), "flash_rays stays inside its box");
}

// ---- fk: dissolve, round shapes, trails ----

#[test]
fn fk_fade_hsh_rot() {
    let full = Shade::from_elem((H, W), 2);
    let left: Vec<usize> = [0.0, 0.25, 0.5, 0.75, 1.0].iter().map(|&a| count(&fk::fade(&full, a))).collect();
    assert!(left[0] == W * H && left[4] == 0 && left.windows(2).all(|w| w[0] >= w[1]), "fade removes more as it rises: {left:?}");
    let half = fk::fade(&full, 0.5);
    for y in 0..4 { for x in 0..4 { assert_eq!(half[[y, x]], half[[y + 4, x + 4]], "fade dissolves by a repeating 4x4 pattern, not by noise"); } }
    let h = fk::hsh(3.0, 1.0);
    assert!(h == fk::hsh(3.0, 1.0) && (0.0..1.0).contains(&h) && h != fk::hsh(4.0, 1.0), "hsh is a fixed value per index");
    let (u, v) = fk::rot(&Array2::from_elem((1, 1), 1.0), &Array2::from_elem((1, 1), 0.0), PI / 2.0);
    assert!(u[[0, 0]].abs() < 1e-9 && (v[[0, 0]] + 1.0).abs() < 1e-9, "rot turns world px into along and across a heading");
}

#[test]
fn fk_round_shapes() {
    let (x, y) = xy();
    let r = rad(&x, &y);
    let d = fk::lumpy(&x, &y, 0.0, 0.0, 10.0, Lumpy { amp: 0.2, seed: 1.0, ..Default::default() });
    let inside = d.iter().filter(|&&v| v < 1.0).count();
    assert!(d[[H / 2, W / 2]] < 0.2 && inside > 200, "lumpy is inside at its centre");
    let a = maxf(&sel(&r, |p| d[p] < 1.0));
    let b = minf(&sel(&r, |p| d[p] >= 1.0));
    assert!(a - b > 1.5, "lumpy has a lobed rim, not a circle: {a} {b}");
    painted("heat_bands", |q| { fk::heat_bands(q, &d, &[3, 2, 1, 0], &[0.3, 0.55, 0.8, 1.0]); }, &[0, 1, 2, 3], 4);
    let bl = painted("ball", |q| { fk::ball(q, &x, &y, 0.0, 0.0, 9.0, &[0, 1, 2, 3], Ball::default()); }, &[0, 1, 2, 3], 4);
    let hi: Vec<(usize, usize)> = bl.indexed_iter().filter(|(_, &v)| v == 3).map(|(p, _)| p).collect();
    let (my, mx) = (mean(&hi.iter().map(|p| p.0 as f64).collect::<Vec<_>>()), mean(&hi.iter().map(|p| p.1 as f64).collect::<Vec<_>>()));
    assert!(!hi.is_empty() && mx < W as f64 / 2.0 && my < H as f64 / 2.0, "ball puts its highlight toward the top left light");

    let whole = painted("puff", |q| { fk::puff(q, &x, &y, 0.0, 0.0, 10.0, &[0, 1, 2], Puff::default()); }, &[0, 1, 2], 4);
    let mut broken = fl::empty(W, H);
    fk::puff(&mut broken, &x, &y, 0.0, 0.0, 10.0, &[0, 1, 2], Puff { brk: 0.7, ..Default::default() });
    let gone = |p: (usize, usize)| whole[p] >= 0 && broken[p] < 0;
    let ngone = whole.indexed_iter().filter(|(p, _)| gone(*p)).count();
    assert!(ngone > 0 && ngone < count(&whole) && !broken.indexed_iter().any(|(p, &v)| v >= 0 && whole[p] < 0), "a breaking puff only loses pixels");
    assert!(mean(&sel(&r, gone)) > mean(&sel(&r, |p| broken[p] >= 0)), "a puff breaks up from its edge inward");

    let (u, v) = fk::rot(&x, &y, 0.0);
    painted("trail_puffs", |q| fk::trail_puffs(q, &x, &y, &u, &v, 20.0, 6.0, 0.4, TrailPuffs::default()), &[0, 1, 2, 3], 4);
    let s8 = painted("streaks", |q| { fk::streaks(q, &x, &y, 0.0, 0.0, 8, 3.0, 18.0, 3.0, &[0, 1, 2], Streaks { seed: 2.0, ..Default::default() }); }, &[0, 1, 2], 4);
    assert!(s8.indexed_iter().all(|(p, &v)| v < 0 || (r[p] >= 1.2 && r[p] <= 22.0)), "streaks run from their inner radius to their outer one");
    let ring = fk::ring(&x, &y, 0.0, 0.0, 12.0, 2.0, Ring::default());
    let rr = sel(&r, |p| ring[p]);
    assert!(ring.iter().any(|&v| v) && !ring[[H / 2, W / 2]] && (mean(&rr) - 11.0).abs() < 0.6, "ring is a band inside its radius");
}

#[test]
fn fk_polygon_facets_twinkle_kite_leaf() {
    let (x, y) = xy();
    let pts = fk::polygon(0.0, 0.0, 12.0, 6, 3.0, Polygon::default());
    assert!(pts.len() == 6 && pts == fk::polygon(0.0, 0.0, 12.0, 6, 3.0, Polygon::default()), "polygon repeats by seed");
    painted("facets", |q| { fk::facets(q, &x, &y, &pts, &[0, 1, 2, 3], Facets::default()); }, &[0, 1, 2, 3], 100);
    let tw = painted("twinkle", |q| fk::twinkle(q, 20.0, 20.0, 3, 3, 2), &[2, 3], 4);
    assert!(tw[[20, 20]] == 3 && tw[[20, 23]] == 2 && tw[[21, 21]] < 0, "twinkle is a four point star, hot at the centre");
    assert_eq!(fk::to_px(&tw, &x, &y, 0.5, 0.5), (W / 2, H / 2), "to_px finds the pixel of a world point");
    assert_eq!(fk::at(&tw, &x, &y, 0.0, 4.5, 0.5), (W / 2 + 4, H / 2), "at finds the pixel of a world point");
    let k = painted("kite", |q| { fk::kite(q, &x, &y, 0.0, 0.0, 0.0, 16.0, 6.0, &[0, 1, 2, 3], Kite::default()); }, &[0, 1, 2, 3], 4);
    let ext = |m: &Shade| {
        let p: Vec<(usize, usize)> = m.indexed_iter().filter(|(_, &v)| v >= 0).map(|(p, _)| p).collect();
        let ys: Vec<usize> = p.iter().map(|q| q.0).collect();
        let xs: Vec<usize> = p.iter().map(|q| q.1).collect();
        (xs.iter().max().unwrap() - xs.iter().min().unwrap(), ys.iter().max().unwrap() - ys.iter().min().unwrap())
    };
    let (ex, ey) = ext(&k);
    assert!(ex > 2 * ey, "kite is long along its heading");
    let lf = painted("leaf", |q| { fk::leaf(q, &x, &y, -10.0, 0.0, 0.0, 20.0, 8.0, &[0, 1, 2, 3], Leaf::default()); }, &[0, 1, 2, 3], 4);
    let mut thin = fl::empty(W, H);
    fk::leaf(&mut thin, &x, &y, -10.0, 0.0, 0.0, 20.0, 8.0, &[0, 1, 2, 3], Leaf { roll: 0.3, ..Default::default() });
    assert!(count(&thin) > 0 && count(&thin) < count(&lf), "a leaf turning edge on narrows");
    assert_eq!(fk::rim_if(&lf, 0, false), lf, "rim_if leaves the drawing as it was when not asked");
    assert!(count(&fk::rim_if(&lf, 0, true)) > count(&lf), "rim_if rims only when asked");
    assert!(count(&fk::rim(&lf, 0)) > count(&lf), "rim adds a 1 px rim");
}

#[test]
fn fk_claws_and_drops() {
    let (x, y) = xy();
    let local = fk::claw_tracks(10.0, ClawTracks { n: 3, ..Default::default() });
    let tracks = fk::to_world(&local, 0.0);
    assert!(tracks.len() == 3 && tracks[0].len() == 14 && tracks[0] != tracks[1], "claw_tracks gives n parallel tracks");
    painted("claw_marks", |q| { fk::claw_marks(q, &x, &y, &tracks, 0.7, 0.4, &[0, 1, 2, 3], &[4, 5, 6], ClawMarks::default()); }, &[0, 1, 2, 3, 4, 5, 6], 4);
    let mut gone_by = fl::empty(W, H);
    let tip = fk::claw_marks(&mut gone_by, &x, &y, &tracks, 2.0, 0.4, &[0, 1, 2, 3], &[4, 5, 6], ClawMarks::default());
    assert!(tip.is_none() && used(&gone_by).iter().all(|s| [4, 5, 6].contains(s)), "once the claws leave, only the scar is left");
    painted("drop", |q| fk::drop(q, &x, &y, 0.0, 0.0, 2.5, &[0, 1, 2, 3], Some((-4.0, 0.0))), &[0, 1, 2, 3], 4);
    painted("claw_drops", |q| fk::claw_drops(q, &x, &y, &tracks, 2, 5.0, &[0, 1, 2, 3], ClawDrops::default()), &[0, 1, 2, 3], 1);
    let mut before = fl::empty(W, H);
    fk::claw_drops(&mut before, &x, &y, &tracks, 0, 5.0, &[0, 1, 2, 3], ClawDrops::default());
    assert_eq!(count(&before), 0, "no drops fly before the claws start");
}

// ---- hits: a blow in six frames, the cell of a themed hit, and the ground's reaction ----

#[test]
fn fk_hits() {
    let (x, y) = xy();
    let tones = [0i8, 1, 2, 3];
    let smoke = [4i8, 5, 6];
    let all: Vec<i8> = (0..8).collect();
    let burst: Vec<Shade> = (0..6).map(|f| {
        painted(&format!("hit_burst frame {f}"),
                |q| { fk::hit_burst(q, &x, &y, f, &tones, &smoke, 7, HitBurst { r: 12.0, seed: 1.0, shards: Some(tones), ..Default::default() }); },
                &all, 3)
    }).collect();
    assert!(count(&burst[1]) > count(&burst[0]), "hit_burst grows from its core to the flash");
    assert!(burst[..2].iter().any(|q| q.iter().any(|&v| v == 3)), "hit_burst is hottest at the start");
    let th = Theme { kind: Kind::Shard, rim: 0, streak: [1, 2, 3], disc: [2, 3], deb: [4, 5, 6, 7], drop: Some([4, 5, 6, 7]), drops: None, mist: Some([8, 9, 10]) };
    let cells: Vec<Shade> = (0..6).map(|f| fk::hit_cell(&x, &y, f, true, &th, 2)).collect();
    assert!(cells[..5].iter().all(|c| count(c) > 0), "hit_cell draws its six frames");
    assert_eq!(cells[1], fk::hit_cell(&x, &y, 1, true, &th, 2), "hit_cell repeats by seed");
    assert!(count(&cells[1]) > count(&fk::hit_cell(&x, &y, 1, false, &th, 2)), "a big hit covers more than a small one");
}

fn ground(x: &Grid, y: &Grid, f: i64, weight: Weight, life: f64) -> Shade {
    let mut m = fl::empty(W, H);
    fk::ground_impact(&mut m, x, y, f, 24.0, &[0, 1, 2], &[3, 4, 5], GroundImpact { cy: 10.0, weight, life, seed: 3.0, ..Default::default() });
    m
}

#[test]
fn fk_ground_impact_and_debris() {
    let (x, y) = xy();
    for w in [Weight::Light, Weight::Heavy, Weight::Finisher, Weight::Blast] {
        assert!(count(&ground(&x, &y, 2, w, 1.2)) > 0, "ground_impact throws dust or debris");
    }
    assert_eq!(count(&ground(&x, &y, -1, Weight::Heavy, 1.2)), 0, "ground_impact draws nothing before the contact frame");
    assert_eq!(count(&ground(&x, &y, (1.2 * 24.0) as i64 + 1, Weight::Heavy, 1.2)), 0, "ground_impact ends empty after its life");
    assert!(count(&ground(&x, &y, 3, Weight::Heavy, 1.2)) > count(&ground(&x, &y, 3, Weight::Light, 1.2)), "a heavy blow marks the ground more than a light one");
    assert!(Weight::parse("feather").is_err() && Weight::parse("heavy").is_ok());
    let (_, y0, rest0) = fk::debris_at(0, 0.02, 0.0, 10.0, 12.0, 1.0, 0.35, 3.0);
    let (_, y1, rest1) = fk::debris_at(0, 5.0, 0.0, 10.0, 12.0, 1.0, 0.35, 3.0);
    assert!(!rest0 && rest1 && y0 < y1 && (y1 - 10.0).abs() <= 0.35 * 12.0 * 0.25 + 1e-9, "debris flies up, then rests on the ground plane");
}

// ---- the mockup caster: a figure with its feet on the ground and light on its body ----

#[test]
fn cs_caster_draws_a_figure() {
    const CW: usize = 96;
    const CH: usize = 128;
    let mut alpha = Array2::<f64>::zeros((CH, CW));
    let mut over = |ys: &[i64], xs: &[i64], _rgb: &Array2<f64>, a: &[f64]| {
        for i in 0..ys.len() {
            let (yy, xx) = (ys[i], xs[i]);
            if yy >= 0 && (yy as usize) < CH && xx >= 0 && (xx as usize) < CW && a[i] > 0.0 {
                alpha[[yy as usize, xx as usize]] = 1.0;
            }
        }
    };
    let pose = cs::pose_at(4.0, &[(0.0, "rest"), (8.0, "raise")], &[(0.0, "rest")], None, 0.0).unwrap();
    let g = cs::draw(&mut over, (CH, CW), [56.0, 118.0], 1.0, pose, 4.0, cs::Draw::default()).unwrap();
    let pts: Vec<(usize, usize)> = alpha.indexed_iter().filter(|(_, &v)| v > 0.0).map(|(p, _)| p).collect();
    let ys: Vec<usize> = pts.iter().map(|p| p.0).collect();
    let xs: Vec<usize> = pts.iter().map(|p| p.1).collect();
    let (py, px) = (ys.iter().max().unwrap() - ys.iter().min().unwrap(), xs.iter().max().unwrap() - xs.iter().min().unwrap());
    assert!(pts.len() > 300 && py > px && *ys.iter().max().unwrap() as f64 >= g.feet[1], "caster draws a standing figure down to its feet");
    assert!(g.head[1] < g.neck[1] && g.neck[1] < g.hip[1] && g.hip[1] < g.feet[1], "caster returns its key points, head above hip above feet");
    let mut l = Array2::<f64>::zeros((CH, CW));
    cs::body_light(&mut l, &g, 1.0);
    let mx = l.iter().cloned().fold(0.0, f64::max);
    assert!(mx > 0.2 && l[[g.hip[1] as usize, g.hip[0] as usize]] > l[[2, 2]], "caster lights its body, not the far corner");
    let aim = cs::aim_from([56.0, 118.0], 1.0, [90.0, 60.0]);
    assert!((aim[0].hypot(aim[1]) - 1.0).abs() < 1e-6 && aim[0] > 0.0, "aim_from points from the shoulder at the target");
    let point = cs::pose_at(8.0, &[(0.0, "rest"), (8.0, "point")], &[(0.0, "rest")], Some(aim), 0.0).unwrap();
    assert_ne!(point, pose, "a pointing pose differs from the raise");
}
