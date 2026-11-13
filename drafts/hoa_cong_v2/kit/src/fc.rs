//! facing.py: directions for a general-mode sheet, what a game needs to play one effect from any side or heading.
//!
//! Side view, 1 direction: drawn facing east; the engine flips it for west and uses mirror_pivot and mirror_target
//! (x becomes w - x). Top-down or 3/4, n rows: row k faces tau * k / n radians, y down: 0 east, n/4 south, n/2
//! west, 3n/4 north. A caster to target effect is exported as parts (cast, travel, impact): `part` builds each
//! entry, `check` validates. Points and numbers go into the JSON as ints when whole, as the Python ints did.

use crate::ex::num;
use ndarray::{s, Array3};
use serde_json::{json, Map, Value};
use std::f64::consts::TAU as TAU_;
use std::path::Path;

pub const TAU: f64 = TAU_;
pub const VIEWS: [&str; 3] = ["side", "top-down", "3/4"];
pub const NAMES8: [&str; 8] = ["east", "south-east", "south", "south-west", "west", "north-west", "north", "north-east"];

/// The angle of each row, radians, y down: row 0 east, n/4 south.
pub fn headings(n: usize) -> Vec<f64> {
    (0..n).map(|k| TAU * k as f64 / n as f64).collect()
}

/// The row an engine plays for a move of (dx, dy), y down.
pub fn row_of(dx: f64, dy: f64, n: usize) -> usize {
    let r = (dy.atan2(dx) / TAU * n as f64).round_ties_even() as i64;
    crate::np::pymod_i(r, n as i64) as usize
}

/// rows[k][f] = draw(a, f) for each heading a; draw returns an (h, w, 4) u8 frame.
pub fn rows(mut draw: impl FnMut(f64, usize) -> Array3<u8>, n: usize, frames: usize) -> Vec<Vec<Array3<u8>>> {
    headings(n).into_iter().map(|a| (0..frames).map(|f| draw(a, f)).collect()).collect()
}

/// One row per heading, frames left to right, as a PNG.
pub fn sheet(rows: &[Vec<Array3<u8>>], path: impl AsRef<Path>) -> Result<(), String> {
    crate::pfx::sheet(rows, path.as_ref())
}

/// The frames flipped left to right (the west-facing copy of an east-facing side sheet).
pub fn mirror(frames: &[Array3<u8>]) -> Vec<Array3<u8>> {
    frames.iter().map(|f| f.slice(s![.., ..;-1, ..]).to_owned()).collect()
}

/// A point in the flipped sheet: x becomes w - x (pixel edges, so a centred pivot stays put).
pub fn flip(p: [f64; 2], w: f64) -> [f64; 2] {
    [w - p[0], p[1]]
}

fn point(p: [f64; 2]) -> Value {
    json!([num(p[0]), num(p[1])])
}

/// Options of `meta`: directions 1, facing "east", mirror true, no target.
#[derive(Clone, Debug)]
pub struct Meta {
    pub directions: usize,
    pub facing: String,
    pub mirror: bool,
    pub target: Option<[f64; 2]>,
}

impl Default for Meta {
    fn default() -> Self {
        Meta { directions: 1, facing: "east".into(), mirror: true, target: None }
    }
}

/// The direction fields of the sheet's JSON (merge them into ex::Write's extra).
pub fn meta(view: &str, w: f64, _h: f64, pivot: [f64; 2], o: Meta) -> Result<Map<String, Value>, String> {
    if !VIEWS.contains(&view) {
        return Err(format!("view '{view}' not in ('side', 'top-down', '3/4')"));
    }
    let mut m = Map::new();
    m.insert("view".into(), json!(view));
    m.insert("directions".into(), json!(o.directions));
    if o.directions == 1 {
        m.insert("facing".into(), json!(o.facing));
        m.insert("mirror".into(), json!(o.mirror));
        if o.mirror {
            m.insert("mirror_pivot".into(), point(flip(pivot, w)));
            if let Some(t) = o.target {
                m.insert("mirror_target".into(), point(flip(t, w)));
            }
        }
    } else {
        m.insert("row_rule".into(), json!("row k faces tau * k / n, y down: 0 east, n/4 south, n/2 west, 3n/4 north"));
        m.insert("row_of".into(), json!("round(atan2(dy, dx) / tau * n) mod n"));
        if o.directions == 8 {
            m.insert("row_names".into(), json!(NAMES8));
        }
    }
    Ok(m)
}

fn at(rng: f64, name: &str) -> [i64; 2] {
    let k = NAMES8.iter().position(|n| *n == name).expect("offset: a direction from NAMES8");
    let a = TAU * k as f64 / 8.0;
    [(rng * a.cos()).round_ties_even() as i64, (rng * a.sin()).round_ties_even() as i64]
}

/// Where a side-view cast lands: [dx, dy] from the caster's pivot to the effect's pivot, rng px facing east.
pub fn offset(rng: f64) -> [i64; 2] {
    at(rng, "east")
}

/// offset with directions: one [dx, dy] per name from NAMES8, in the order given.
pub fn offset_dirs(rng: f64, directions: &[&str]) -> Vec<(String, [i64; 2])> {
    directions.iter().map(|d| (d.to_string(), at(rng, d))).collect()
}

/// One part of a split effect. anchor: caster, target or travel; a travel part also gives speed (px/s) in extra
/// (a JSON object whose fields follow the fixed ones).
#[allow(clippy::too_many_arguments)]
pub fn part(sheet_file: &str, w: i64, h: i64, frames: i64, fps: f64, pivot: [f64; 2], looped: bool, anchor: &str,
            extra: Option<Value>) -> Value {
    let mut m = Map::new();
    m.insert("sheet".into(), json!(sheet_file));
    m.insert("w".into(), json!(w));
    m.insert("h".into(), json!(h));
    m.insert("frames".into(), json!(frames));
    m.insert("fps".into(), num(fps));
    m.insert("pivot".into(), point(pivot));
    m.insert("loop".into(), json!(looped));
    m.insert("anchor".into(), json!(anchor));
    if let Some(Value::Object(e)) = extra {
        m.extend(e);
    }
    Value::Object(m)
}

/// An error when the direction fields do not hold together (facing.check's ValueError messages).
pub fn check(m: &Value) -> Result<(), String> {
    for k in ["view", "directions"] {
        if m.get(k).is_none() {
            return Err(format!("missing {k}"));
        }
    }
    let truth = |v: Option<&Value>| v.map(crate::py::truth).unwrap_or(false);
    let d = m["directions"].as_f64();
    if d == Some(1.0) {
        let f = m.get("facing").and_then(Value::as_str);
        if f != Some("east") && f != Some("west") {
            return Err("a 1-direction sheet needs facing east or west".into());
        }
        if truth(m.get("mirror")) && m.get("mirror_pivot").is_none() {
            return Err("mirror True needs mirror_pivot".into());
        }
        if !truth(m.get("mirror")) && m.get("sheets").and_then(|s| s.get("west")).is_none() {
            return Err("mirror False needs a west sheet in sheets".into());
        }
    } else if !matches!(d, Some(x) if x == 4.0 || x == 8.0 || x == 16.0) {
        return Err("directions is 1, 4, 8 or 16".into());
    }
    if let Some(Value::Object(parts)) = m.get("parts") {
        for (name, p) in parts {
            let a = p.get("anchor").and_then(Value::as_str);
            if !matches!(a, Some("caster" | "target" | "travel")) {
                return Err(format!("part {name}: anchor caster, target or travel"));
            }
            if a == Some("travel") && !truth(p.get("speed")) {
                return Err(format!("part {name}: a travel part needs speed px/s"));
            }
            if p.get("view").is_some() {
                check(p)?;
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rows_and_headings() {
        assert_eq!(row_of(1.0, 0.0, 8), 0);
        assert_eq!(row_of(0.0, 1.0, 8), 2);
        assert_eq!(row_of(-1.0, 0.0, 8), 4);
        assert_eq!(row_of(0.0, -1.0, 8), 6);
        assert_eq!(row_of(1.0, -0.01, 16), 0);
        assert_eq!(headings(4)[1], TAU / 4.0);
        let r = rows(|a, f| Array3::from_elem((2, 3, 4), (a * 10.0) as u8 + f as u8), 4, 2);
        assert_eq!((r.len(), r[0].len(), r[1][1][[0, 0, 0]]), (4, 2, 16));
    }

    #[test]
    fn meta_matches_python() {
        let m = meta("side", 64.0, 48.0, [20.0, 40.0], Meta { target: Some([50.0, 30.0]), ..Default::default() }).unwrap();
        assert_eq!(Value::Object(m.clone()).to_string(),
                   r#"{"view":"side","directions":1,"facing":"east","mirror":true,"mirror_pivot":[44,40],"mirror_target":[14,30]}"#);
        assert!(check(&Value::Object(m)).is_ok());
        let m = meta("top-down", 64.0, 64.0, [32.0, 32.0], Meta { directions: 8, ..Default::default() }).unwrap();
        assert_eq!(m["row_names"][2], "south");
        assert!(meta("iso", 1.0, 1.0, [0.0, 0.0], Meta::default()).is_err());
        assert_eq!(check(&json!({"view": "side", "directions": 1, "facing": "east", "mirror": false})).unwrap_err(),
                   "mirror False needs a west sheet in sheets");
        assert_eq!(check(&json!({"view": "side", "directions": 3})).unwrap_err(), "directions is 1, 4, 8 or 16");
        let bad = json!({"view": "side", "directions": 8, "parts": {"fly": {"anchor": "travel"}}});
        assert_eq!(check(&bad).unwrap_err(), "part fly: a travel part needs speed px/s");
    }

    #[test]
    fn offsets_parts_and_mirror() {
        assert_eq!(offset(10.0), [10, 0]);
        assert_eq!(offset_dirs(10.0, &["south-east", "north"]), vec![("south-east".into(), [7, 7]), ("north".into(), [0, -10])]);
        let p = part("fly.png", 32, 16, 6, 24.0, [16.0, 8.0], true, "travel", Some(json!({"speed": 180})));
        assert_eq!(p.to_string(),
                   r#"{"sheet":"fly.png","w":32,"h":16,"frames":6,"fps":24,"pivot":[16,8],"loop":true,"anchor":"travel","speed":180}"#);
        let f = Array3::from_shape_fn((1, 3, 4), |(_, x, _)| x as u8);
        assert_eq!(mirror(&[f])[0][[0, 0, 0]], 2);
        assert_eq!(flip([20.0, 5.0], 64.0), [44.0, 5.0]);
    }
}
