//! Port of tests/test_facing.py: heading rows point the right way, mirroring keeps pivots and pixels, the JSON holds.

use beanfx::fc;
use beanfx::img;
use beanfx::ndarray::Array3;
use serde_json::{json, Value};
use std::f64::consts::PI;

const W: usize = 48;
const H: usize = 48;
const PIV: [f64; 2] = [24.0, 24.0];

/// A head 14 px from the pivot along a, with a dim tail behind it.
fn bolt(a: f64, _f: usize) -> Array3<u8> {
    let mut img = Array3::<u8>::zeros((H, W, 4));
    for y in 0..H {
        for x in 0..W {
            let (xs, ys) = (x as f64 + 0.5, y as f64 + 0.5);
            let u = (xs - PIV[0]) * a.cos() + (ys - PIV[1]) * a.sin();
            let v = -(xs - PIV[0]) * a.sin() + (ys - PIV[1]) * a.cos();
            let head = (u - 14.0) * (u - 14.0) + v * v < 9.0;
            let tail = v.abs() < 1.0 && u > -4.0 && u < 12.0;
            if tail {
                for (c, val) in [120u8, 60, 20, 255].iter().enumerate() { img[[y, x, c]] = *val; }
            }
            if head {
                for (c, val) in [255u8, 240, 200, 255].iter().enumerate() { img[[y, x, c]] = *val; }
            }
        }
    }
    img
}

fn heading_of(frame: &Array3<u8>) -> f64 {
    let (mut sx, mut sy, mut n) = (0.0, 0.0, 0.0);
    for y in 0..H {
        for x in 0..W {
            if frame[[y, x, 0]] == 255 {
                sx += x as f64;
                sy += y as f64;
                n += 1.0;
            }
        }
    }
    (sy / n + 0.5 - PIV[1]).atan2(sx / n + 0.5 - PIV[0]).rem_euclid(fc::TAU)
}

fn meta(view: &str, w: f64, h: f64, pivot: [f64; 2], o: fc::Meta) -> Value {
    Value::Object(fc::meta(view, w, h, pivot, o).unwrap())
}

#[test]
fn heading_rows_point_the_right_way() {
    for n in [8usize, 16] {
        let rs = fc::rows(bolt, n, 3);
        assert!(rs.len() == n && rs.iter().all(|r| r.len() == 3), "{n}: rows shape");
        for (k, r) in rs.iter().enumerate() {
            let (got, want) = (heading_of(&r[0]), fc::TAU * k as f64 / n as f64);
            let err = ((got - want + PI).rem_euclid(fc::TAU) - PI).abs();
            assert!(err < 0.05, "{n}: row {k} points at {:.1}, want {:.1}", got.to_degrees(), want.to_degrees());
            let (dx, dy) = (want.cos() * 10.0, want.sin() * 10.0);
            assert_eq!(fc::row_of(dx, dy, n), k, "{n}: row_of for row {k}");
        }
        let dir = std::env::temp_dir().join(format!("beanfx_facing_{}_{n}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let p = dir.join("s.png");
        fc::sheet(&rs, &p).unwrap();
        let a = img::read(&p).unwrap();
        assert_eq!(a.dim(), (n * H, 3 * W, 4), "{n}: sheet size");
        std::fs::remove_dir_all(&dir).ok();
        let m = meta("top-down", W as f64, H as f64, PIV, fc::Meta { directions: n, ..Default::default() });
        fc::check(&m).unwrap();
        assert!(m["directions"] == json!(n) && m.get("row_rule").is_some() && m.get("rows").is_none(), "{n}: meta");
    }
    let m8 = meta("top-down", W as f64, H as f64, PIV, fc::Meta { directions: 8, ..Default::default() });
    assert_eq!(m8["row_names"][2], "south", "row 2 of 8 is south");
    assert!(fc::row_of(0.0, 5.0, 8) == 2 && fc::row_of(-5.0, 0.0, 8) == 4 && fc::row_of(0.0, -5.0, 8) == 6, "row_of compass");
}

#[test]
fn side_view_mirror_keeps_pivot_and_pixels() {
    let east: Vec<Array3<u8>> = (0..3).map(|f| bolt(0.0, f)).collect();
    let west = fc::mirror(&east);
    assert!((heading_of(&west[0]) - PI).abs() < 0.05, "mirror faces west");
    let flipped = Array3::from_shape_fn(east[1].dim(), |(y, x, c)| east[1][[y, W - 1 - x, c]]);
    assert_eq!(west[1], flipped, "mirror is a pixel flip");
    let m = meta("side", 176.0, 192.0, [40.0, 170.0], fc::Meta { target: Some([150.0, 168.0]), ..Default::default() });
    fc::check(&m).unwrap();
    assert!(m["facing"] == "east" && m["mirror"] == true, "side meta facing and mirror");
    assert!(m["mirror_pivot"] == json!([136, 170]) && m["mirror_target"] == json!([26, 168]), "mirror pivot and target are w - x");
    let c = meta("side", 176.0, 192.0, [88.0, 170.0], fc::Meta::default());
    assert_eq!(c["mirror_pivot"], json!([88, 170]), "a centred pivot stays put");
    serde_json::to_string(&m).unwrap();
}

#[test]
fn split_parts_and_bad_metadata() {
    let mut split = meta("side", 320.0, 200.0, [40.0, 172.0], fc::Meta { target: Some([280.0, 172.0]), ..Default::default() });
    let travel_meta = fc::meta("top-down", 48.0, 48.0, [24.0, 24.0], fc::Meta { directions: 16, ..Default::default() }).unwrap();
    let mut extra = serde_json::Map::new();
    extra.insert("speed".into(), json!(320));
    extra.extend(travel_meta);
    split["parts"] = json!({
        "cast": fc::part("x_cast.png", 96, 96, 20, 24.0, [48.0, 88.0], false, "caster", None),
        "travel": fc::part("x_travel.png", 48, 48, 12, 24.0, [24.0, 24.0], true, "travel", Some(Value::Object(extra))),
        "impact": fc::part("x_impact.png", 128, 128, 30, 24.0, [64.0, 110.0], false, "target", None),
    });
    fc::check(&split).unwrap();
    serde_json::to_string(&split).unwrap();

    let with_parts = |parts: Value| { let mut s = split.clone(); s["parts"] = parts; s };
    let bad = [
        json!({"view": "side", "directions": 1, "facing": "east", "mirror": true}),
        json!({"view": "side", "directions": 1, "facing": "east", "mirror": false, "sheets": {}}),
        json!({"view": "top-down", "directions": 6}),
        with_parts(json!({"travel": fc::part("t.png", 8, 8, 4, 24.0, [4.0, 4.0], true, "travel", None)})),
        with_parts(json!({"cast": fc::part("c.png", 8, 8, 4, 24.0, [4.0, 4.0], false, "hand", None)})),
    ];
    for (i, b) in bad.iter().enumerate() {
        assert!(fc::check(b).is_err(), "bad meta {i} passed check");
    }
    assert!(fc::meta("isometric", W as f64, H as f64, PIV, fc::Meta::default()).is_err(), "unknown view passed");
}
