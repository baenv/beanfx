//! Port of tests/test_rig.py: rig on a synthetic character: frames cut right, the feet measured, the pivot placed,
//! the JSON binding, and the casters that ship with the skill.

mod common;

use std::path::{Path, PathBuf};

use beanfx::img;
use beanfx::ndarray::{concatenate, Array3, Axis};
use beanfx::rig::{self, CheckArc, FrameAt, Meta, Place, Rig};
use serde_json::{json, Value};

const W: usize = 24;
const H: usize = 32;
const N: usize = 3;

/// A 4 px wide body standing on ground at foot_x, with a marker pixel in column k so frames differ.
fn body(k: usize, foot_x: usize, ground: usize) -> Array3<u8> {
    let mut a = Array3::<u8>::zeros((H, W, 4));
    for y in ground - 16..ground {
        for x in foot_x - 2..foot_x + 2 {
            for (c, v) in [200u8, 120, 60, 255].iter().enumerate() {
                a[[y, x, c]] = *v;
            }
        }
    }
    for c in 0..4 {
        a[[2, k, c]] = 255;
    }
    a
}

fn sheet(path: &Path, frames: &[Array3<u8>]) {
    let views: Vec<_> = frames.iter().map(|f| f.view()).collect();
    img::write(path, &concatenate(Axis(1), &views).unwrap().view()).unwrap();
}

fn write_json(path: PathBuf, v: Value) {
    std::fs::write(path, v.to_string()).unwrap();
}

/// Mean alpha column of row y, rounded the way the python check does (int(mean + 0.5)).
fn row_col(f: &Array3<u8>, y: usize) -> i64 {
    let xs: Vec<f64> = (0..W).filter(|&x| f[[y, x, 3]] > 0).map(|x| x as f64).collect();
    (xs.iter().sum::<f64>() / xs.len() as f64 + 0.5) as i64
}

fn first_col(f: &Array3<u8>, y: usize) -> usize {
    (0..W).find(|&x| f[[y, x, 3]] > 0).unwrap()
}

fn alpha_cols(a: &Array3<u8>) -> Vec<usize> {
    let (h, w, _) = a.dim();
    (0..h).flat_map(|y| (0..w).filter(move |&x| a[[y, x, 3]] > 0)).collect::<Vec<_>>()
}

// the fields a bundled caster's animation may carry: the rig contract, nothing from the tool that built it
const SHIP_KEYS: [&str; 11] = ["frame", "frames", "fps", "loop", "sheets", "pivot", "ms", "contact", "swing", "emit", "root"];

struct Fixture {
    root: PathBuf,
}

fn fixture(tag: &str) -> Fixture {
    let root = common::tmpdir(tag);
    let side = root.join("casters/hero");
    std::fs::create_dir_all(&side).unwrap();
    let frames: Vec<_> = (0..N).map(|k| body(k, 10, 28)).collect();
    sheet(&side.join("atk.png"), &frames);
    write_json(side.join("rig.json"), json!({"name": "hero", "view": "side", "facing": "east", "fps": 10,
        "pixel_scale": 1, "anims": {
            "dash": {"frame": [W, H], "frames": N, "sheet": "atk.png", "root": [[0, 0], [5, 0], [12, 0]], "move": "root"},
            "atk": {"frame": [W, H], "frames": N, "sheet": "atk.png", "contact": [1],
                "swing": [{"kind": "slash", "turn": "cw", "from": -60, "to": 150, "sweep": 210, "frames": [1]}]}}}));
    let top = root.join("casters/topper");
    std::fs::create_dir_all(&top).unwrap();
    let mut sheets = serde_json::Map::new();
    let mut swing = serde_json::Map::new();
    for (i, d) in rig::DIRS4.iter().enumerate() {
        let fr: Vec<_> = (0..N).map(|k| body(k, 10 + i, 28)).collect();
        sheet(&top.join(format!("atk_{d}.png")), &fr);
        sheets.insert(d.to_string(), json!(format!("atk_{d}.png")));
        let i = i as i64;
        swing.insert(d.to_string(), json!([{"kind": "slash", "turn": "ccw", "from": i * 90, "to": i * 90 - 180, "sweep": -180, "frames": [1, 2]}]));
    }
    write_json(top.join("rig.json"), json!({"name": "topper", "view": "top-down", "fps": 10, "directions": rig::DIRS4,
        "anims": {"atk": {"frame": [W, H], "frames": N, "sheets": sheets, "swing": swing}}}));
    // a side rig with its own east and west rows and a row at its own fps with uneven ms
    let two = root.join("casters/duo");
    std::fs::create_dir_all(&two).unwrap();
    for (i, d) in ["east", "west"].iter().enumerate() {
        let fr: Vec<_> = (0..N).map(|k| body(k, 10 + i, 28)).collect();
        sheet(&two.join(format!("cast_{d}.png")), &fr);
    }
    write_json(two.join("rig.json"), json!({"name": "duo", "view": "side", "facing": "east", "fps": 7.5,
        "directions": ["east", "west"], "anims": {"cast": {"frame": [W, H], "frames": N, "fps": 20, "ms": [50, 100, 50],
        "sheets": {"east": "cast_east.png", "west": "cast_west.png"}, "contact": [1]}}}));
    Fixture { root }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.root).ok();
    }
}

#[test]
fn side_rig_frames_pivot_and_place() {
    let fx = fixture("rig_side");
    let r = rig::load("hero", Some(&fx.root)).unwrap();
    let fr = r.frames("atk", None).unwrap();
    assert!(fr.len() == N && fr[0].dim() == (H, W, 4), "frames: count and size");
    assert_eq!((0..N).map(|k| first_col(&fr[k], 2)).collect::<Vec<_>>(), (0..N).collect::<Vec<_>>(), "frames: cut at the marker column per frame");
    assert_eq!(r.pivot("atk").unwrap(), [10.0, 28.0], "pivot: measured on the feet");

    let canvas = r.place((60, 70), [40.0, 50.0], "atk", 0, Place::default()).unwrap();
    let (mut ymax, mut feet) = (0, vec![]);
    for y in 0..60 {
        for x in 0..70 {
            if canvas[[y, x, 3]] > 0 {
                if y > ymax { ymax = y; feet.clear(); }
                if y == ymax { feet.push(x); }
            }
        }
    }
    let mid = ((feet.iter().min().unwrap() + feet.iter().max().unwrap() + 1) as f64 / 2.0).round_ties_even() as i64;
    assert!(ymax + 1 == 50 && mid == 40, "place: feet on the given point ({mid}, {})", ymax + 1);
    let late = r.place((60, 70), [40.0, 50.0], "atk", N as i64 + 2, Place { hold: false, ..Default::default() }).unwrap();
    assert!(!late.iter().any(|&v| v > 0), "place: empty after the animation with hold False");
    assert_eq!(r.place((10, 10), [500.0, 500.0], "atk", 0, Place::default()).unwrap().dim(), (10, 10, 4), "place: off-canvas placement clips");
    assert!(r.frame_at("atk", N as i64 + 2, FrameAt { hold: false, ..Default::default() }).unwrap().is_none());
    assert!(r.frame_at("atk", N as i64 + 2, FrameAt::default()).unwrap().is_some());
}

#[test]
fn side_rig_meta_swing_arc_root() {
    let fx = fixture("rig_meta");
    let r = rig::load("hero", Some(&fx.root)).unwrap();
    let m = r.meta("atk", 20.0, Meta { start: 1, ..Default::default() }).unwrap();
    let want = json!({"rig": "hero", "anim": "atk", "start": 1, "char_fps": 10, "frames_per_char_frame": 2,
                      "char_pivot": [10, 28], "contact": [1], "layer": "front", "pixel_scale": 1});
    for (k, v) in want.as_object().unwrap() {
        let got = m.get(k).unwrap_or(&Value::Null);
        let same = got == v || (got.is_number() && v.is_number() && got.as_f64() == v.as_f64())
            || (got.is_array() && v.is_array() && got.to_string().replace(".0", "") == *v.to_string());
        assert!(same, "meta: {k}: got {got}, want {v}");
    }
    let turns: Vec<&Value> = m["swing"].as_array().unwrap().iter().map(|x| &x["turn"]).collect();
    assert!(turns == [&json!("cw")] && r.swing("atk", None).unwrap()[0]["to"].as_f64() == Some(150.0), "side swing: one cw stroke to 150");
    assert_eq!(r.arc("atk", None, 0).unwrap(), (-60.0, 150.0), "arc: follows the stroke");
    assert!(r.check_arc("atk", -60.0, 150.0, CheckArc::default()).unwrap().is_empty(), "arc passes its own check");
    assert_eq!(r.check_arc("atk", 150.0, -60.0, CheckArc::default()).unwrap().len(), 3, "check_arc: a reversed arc fails turn, start and end");
    assert!(r.check_arc("atk", -30.0, 130.0, CheckArc::default()).unwrap().is_empty()
            && !r.check_arc("atk", -60.0, 300.0, CheckArc::default()).unwrap().is_empty(),
            "check_arc: ends within tol pass, an end 150 deg off fails");
    assert_eq!(r.root("atk", None).unwrap(), vec![[0.0, 0.0]; N], "root: zeros");
    assert_eq!(r.root("dash", None).unwrap()[2], [12.0, 0.0], "root: the listed travel");
    let moved = r.place((60, 70), [40.0, 50.0], "dash", 2, Place { travel: true, ..Default::default() }).unwrap();
    let still = r.place((60, 70), [40.0, 50.0], "dash", 2, Place::default()).unwrap();
    let minx = |a: &Array3<u8>| *alpha_cols(a).iter().min().unwrap() as i64;
    assert_eq!(minx(&moved) - minx(&still), 12, "place: travel=True shifts by the root motion");
    let md = r.meta("dash", 10.0, Meta::default()).unwrap();
    assert!(md["root"] == json!([[0, 0], [5, 0], [12, 0]]) && md.contains_key("anchor") && !r.meta("atk", 10.0, Meta::default()).unwrap().contains_key("root"),
            "meta: root and anchor");
}

#[test]
fn side_rig_errors() {
    let fx = fixture("rig_err");
    let r = rig::load("hero", Some(&fx.root)).unwrap();
    let mut no_swing = Rig::new(fx.root.join("casters/hero")).unwrap();
    no_swing.spec["anims"]["atk"].as_object_mut().unwrap().remove("swing");
    assert!(r.meta("atk", 15.0, Meta::default()).is_err(), "error on fps not a multiple");
    assert!(r.meta("atk", 20.0, Meta { layer: "side", ..Default::default() }).is_err(), "error on bad layer");
    assert!(r.frames("walk", None).is_err(), "error on unknown anim");
    assert!(no_swing.arc("atk", None, 0).is_err(), "error on no swing");
    assert!(rig::load("nobody", Some(&fx.root)).is_err(), "error on missing rig");
}

#[test]
fn top_down_rig_reads_each_direction() {
    let fx = fixture("rig_top");
    let t = rig::load(fx.root.join("casters/topper").to_str().unwrap(), None).unwrap();
    let dirs: Vec<&str> = rig::DIRS4.to_vec();
    let keys = |v: &Value| v.as_object().unwrap().keys().cloned().collect::<Vec<_>>();
    assert_eq!(t.meta("atk", 10.0, Meta::default()).unwrap()["directions"], json!(dirs), "top-down meta: directions in order");
    let m = t.meta("atk", 10.0, Meta { offset: Some(50.0), ..Default::default() }).unwrap();
    let to = &m["offset"];
    assert!(keys(to) == dirs && to["south"] == json!([0, 50]) && to["west"] == json!([-50, 0]), "top-down meta: one offset per direction: {to}");
    let m = t.meta("atk", 10.0, Meta::default()).unwrap();
    let sw = &m["swing"];
    assert!(keys(sw) == dirs && sw["west"][0]["from"].as_f64() == Some(180.0)
            && t.swing("atk", Some("north")).unwrap()[0]["frames"] == json!([1, 2]),
            "top-down swing: one list per direction, read per direction");
    let cols: Vec<i64> = dirs.iter().map(|d| row_col(&t.frames("atk", Some(d)).unwrap()[0], H - 5)).collect();
    assert_eq!(cols, [10, 11, 12, 13], "top-down: each direction reads its own sheet");
}

#[test]
fn two_row_side_rig() {
    let fx = fixture("rig_duo");
    let u = rig::load("duo", Some(&fx.root)).unwrap();
    assert_eq!(u.fps_of("cast").unwrap(), 20.0, "fps_of: a row's own fps wins");
    let um = u.meta("cast", 40.0, Meta::default()).unwrap();
    assert!(um["directions"] == json!(["east", "west"]) && um["frames_per_char_frame"].as_f64() == Some(2.0) && um["char_fps"].as_f64() == Some(20.0),
            "two-row side meta: directions, row fps and frame ratio: {um:?}");
    let uo = u.meta("cast", 40.0, Meta { offset: Some(110.0), ..Default::default() }).unwrap();
    assert!(uo["offset"] == json!([110, 0]) && uo["range"].as_f64() == Some(110.0)
            && uo["align"].as_str().unwrap().contains("offset") && !um.contains_key("offset"),
            "side meta: one offset along east and the range: {:?}", uo.get("offset"));
    assert_eq!(um["char_ms"], json!([50, 100, 50]), "two-row side meta: the row's ms pass through as char_ms");
    let cols: Vec<i64> = ["east", "west"].iter().map(|d| row_col(&u.frames("cast", Some(d)).unwrap()[0], H - 5)).collect();
    assert_eq!(cols, [10, 11], "two-row side: west reads its own sheet, not a mirror of east");
    assert!(u.meta("cast", 30.0, Meta::default()).is_err(), "meta: an effect fps that is not a whole multiple of the row's fps is refused");
}

#[test]
fn bundled_casters_load_and_carry_only_the_contract() {
    let fx = fixture("rig_ship");
    let ship = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../casters").canonicalize().unwrap();
    for name in ["nghich_tien_kiem", "nghich_tien_kiem_topdown", "nghich_tien_truong", "nghich_tien_truong_topdown"] {
        let b = rig::load(name, Some(&fx.root)).unwrap_or_else(|e| panic!("bundled {name}: loads from the skill's casters/: {e}"));
        assert_eq!(b.dir.canonicalize().unwrap(), ship.join(name), "bundled {name}: loads from the skill's casters/");
        let spec: Value = serde_json::from_str(&std::fs::read_to_string(ship.join(name).join("rig.json")).unwrap()).unwrap();
        let src = spec["source"].as_str().unwrap_or("");
        let stray = spec["anims"].as_object().unwrap().values().any(|a| a.as_object().unwrap().keys().any(|k| !SHIP_KEYS.contains(&k.as_str())));
        assert!(src.starts_with("beanfx bundled") && !src.contains('/') && !stray, "bundled {name}: rig.json carries only the rig contract");
    }
}
