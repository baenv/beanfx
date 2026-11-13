//! Parity of fl, lt and the pfx layers with the Python kit: cases from .parity/rust/gen_fl_lt_pfx.py (or BEANFX_PARITY_FLP).
//! Arrays must be equal, floats bit for bit. Skips when the cases folder is absent.

mod common;

use std::path::{Path, PathBuf};

use beanfx::{fl, lt, pfx};
use common::npy;
use ndarray::{Array2, Array3};
use serde_json::{json, Value};

enum Out {
    F(Vec<usize>, Vec<f64>),
    U(Vec<usize>, Vec<u8>),
    I(Vec<usize>, Vec<i64>),
    J(Value),
}

fn f2(a: &Array2<f64>) -> Out {
    Out::F(a.shape().to_vec(), a.iter().copied().collect())
}
fn f3(a: &Array3<f64>) -> Out {
    Out::F(a.shape().to_vec(), a.iter().copied().collect())
}
fn b2(a: &Array2<bool>) -> Out {
    Out::U(a.shape().to_vec(), a.iter().map(|&v| v as u8).collect())
}
fn i2(a: &Array2<i8>) -> Out {
    Out::I(a.shape().to_vec(), a.iter().map(|&v| v as i64).collect())
}
fn u3(a: &Array3<u8>) -> Out {
    Out::U(a.shape().to_vec(), a.iter().copied().collect())
}
fn stack_u(v: &[Array3<u8>]) -> Out {
    let s = v[0].shape();
    Out::U(vec![v.len(), s[0], s[1], s[2]], v.iter().flat_map(|a| a.iter().copied()).collect())
}
fn stack_f(v: &[Array3<f64>]) -> Out {
    let s = v[0].shape();
    Out::F(vec![v.len(), s[0], s[1], s[2]], v.iter().flat_map(|a| a.iter().copied()).collect())
}

struct Ctx {
    root: PathBuf,
}

impl Ctx {
    fn npy(&self, v: &Value) -> npy::Array {
        npy::read(&self.root.join(v["npy"].as_str().unwrap())).unwrap()
    }
    fn a2(&self, v: &Value) -> Array2<f64> {
        let a = self.npy(v);
        Array2::from_shape_vec((a.shape[0], a.shape[1]), a.to_f64()).unwrap()
    }
    fn a3(&self, v: &Value) -> Array3<f64> {
        let a = self.npy(v);
        Array3::from_shape_vec((a.shape[0], a.shape[1], a.shape[2]), a.to_f64()).unwrap()
    }
    fn i2(&self, v: &Value) -> Array2<i8> {
        self.a2(v).mapv(|x| x as i8)
    }
    fn b2(&self, v: &Value) -> Array2<bool> {
        self.a2(v).mapv(|x| x != 0.0)
    }
    fn u3(&self, v: &Value) -> Array3<u8> {
        let a = self.npy(v);
        Array3::from_shape_vec((a.shape[0], a.shape[1], a.shape[2]), a.as_u8().to_vec()).unwrap()
    }
}

fn f(v: &Value) -> f64 {
    v.as_f64().unwrap()
}
fn u(v: &Value) -> usize {
    v.as_u64().unwrap() as usize
}
fn i(v: &Value) -> i64 {
    v.as_i64().unwrap()
}
fn strs(v: &Value) -> Vec<String> {
    v.as_array().unwrap().iter().map(|s| s.as_str().unwrap().to_string()).collect()
}
fn floats(v: &Value) -> Vec<f64> {
    v.as_array().unwrap().iter().map(f).collect()
}
fn pair(v: &Value) -> (f64, f64) {
    (f(&v[0]), f(&v[1]))
}

fn canvas(a: &Value) -> lt::Canvas {
    let (x, y) = fl::wgrid(u(&a["w"]), u(&a["h"]), f(&a["px"]), f(&a["py"]), f(&a["d"]));
    lt::Canvas { x, y }
}

fn run(c: &Ctx, name: &str, a: &Value) -> Vec<Out> {
    match name {
        "hexc" => vec![Out::J(json!(fl::hexc(a["s"].as_str().unwrap()).unwrap()))],
        "ramp" => vec![Out::J(json!(fl::ramp(a["base"].as_str().unwrap()).unwrap()))],
        "tohex" => {
            let v = floats(&a["rgb"]);
            vec![Out::J(json!(fl::tohex([v[0], v[1], v[2]])))]
        }
        "empty" => vec![i2(&fl::empty(u(&a["w"]), u(&a["h"])))],
        "grid" => {
            let (x, y) = fl::grid(u(&a["w"]), u(&a["h"]), f(&a["cx"]), f(&a["cy"]));
            vec![f2(&x), f2(&y)]
        }
        "wgrid" => {
            let (x, y) = fl::wgrid(u(&a["w"]), u(&a["h"]), f(&a["px"]), f(&a["py"]), f(&a["d"]));
            vec![f2(&x), f2(&y)]
        }
        "pen" => {
            let pen = fl::Pen::new(f(&a["px"]), f(&a["py"]), f(&a["d"]));
            let mut m = fl::empty(u(&a["w"]), u(&a["h"]));
            for op in a["ops"].as_array().unwrap() {
                let (x, y) = (f(&op[1]), f(&op[2]));
                match op[0].as_str().unwrap() {
                    "put" => pen.put(&mut m, x, y, i(&op[3]) as i8),
                    "put_max" => pen.put_max(&mut m, x, y, i(&op[3]) as i8),
                    _ => pen.line(&mut m, x, y, f(&op[3]), f(&op[4]), i(&op[5]) as i8, op[6].as_bool().unwrap()),
                }
            }
            let (sx, sy) = pen.sheet(1.25, -2.5);
            vec![i2(&m), Out::J(json!([sx, sy]))]
        }
        "stroke" => {
            let pts: Vec<[f64; 2]> = a["pts"].as_array().unwrap().iter().map(|p| [f(&p[0]), f(&p[1])]).collect();
            let (d, t, s) = fl::stroke(&c.a2(&a["x"]), &c.a2(&a["y"]), &pts, f(&a["w0"]), f(&a["w1"]));
            vec![f2(&d), f2(&t), f2(&s)]
        }
        "stamp" => {
            let mut d = c.i2(&a["dst"]);
            fl::stamp(&mut d, &c.i2(&a["src"]), i(&a["ox"]), i(&a["oy"]));
            vec![i2(&d)]
        }
        "put" => {
            let (mut p, mut q) = (c.i2(&a["m"]), c.i2(&a["m"]));
            for pt in a["pts"].as_array().unwrap() {
                fl::put(&mut p, f(&pt[0]), f(&pt[1]), i(&pt[2]) as i8);
                fl::put_max(&mut q, f(&pt[0]), f(&pt[1]), i(&pt[2]) as i8);
            }
            vec![i2(&p), i2(&q)]
        }
        "line" => {
            let (mut p, mut q) = (c.i2(&a["m"]), c.i2(&a["m"]));
            let v = floats(&a["p"]);
            fl::line(&mut p, v[0], v[1], v[2], v[3], i(&a["s"]) as i8, false);
            fl::line(&mut q, v[0], v[1], v[2], v[3], i(&a["s"]) as i8, true);
            vec![i2(&p), i2(&q)]
        }
        "outline" => {
            let m = c.i2(&a["m"]);
            vec![i2(&fl::outline(&m, 0)), i2(&fl::outline(&m, 2))]
        }
        "lattice" => vec![f2(&fl::lattice(u(&a["nx"]), u(&a["ny"]), u(&a["seed"]) as u64))],
        "noise" => {
            let period = if a["period"].is_null() { None } else { Some(pair(&a["period"])) };
            vec![f2(&fl::noise(&c.a2(&a["x"]), &c.a2(&a["y"]), f(&a["cells"]), u(&a["seed"]) as u64, period))]
        }
        "checker" => vec![b2(&fl::checker(&c.a2(&a["x"]), &c.a2(&a["y"]), i(&a["phase"])))],
        "ground_dist" => vec![f2(&fl::ground_dist(&c.a2(&a["x"]), &c.a2(&a["y"]), f(&a["rx"]), f(&a["ry"])))],
        "ground_ring" => {
            let mut o = fl::GroundRing::default();
            let kw = &a["kw"];
            if let Some(v) = kw.get("width") {
                o.width = f(v);
            }
            if let Some(v) = kw.get("shades") {
                o.shades = v.as_array().unwrap().iter().map(|s| i(s) as i8).collect();
            }
            if let Some(v) = kw.get("dither") {
                o.dither = v.as_bool().unwrap();
            }
            if let Some(v) = kw.get("rim") {
                o.rim = if v.is_null() { None } else { Some(i(v) as i8) };
            }
            let mut m = c.i2(&a["m"]);
            fl::ground_ring(&mut m, f(&a["cx"]), f(&a["cy"]), f(&a["rx"]), f(&a["ry"]), o);
            vec![i2(&m)]
        }
        "heat" => vec![u3(&fl::heat(&c.u3(&a["cell"]), &strs(&a["pal"]), i(&a["steps"]), f(&a["core"])).unwrap())],
        "contract" => vec![u3(&fl::contract(&c.u3(&a["cell"]), pair(&a["pivot"]), f(&a["k"])))],
        "impact_order" => vec![Out::J(json!(fl::impact_order(i(&a["n"]), i(&a["peak"]), i(&a["hold"]))))],
        "flash_rays" => {
            let b: Vec<usize> = a["box"].as_array().unwrap().iter().map(u).collect();
            vec![u3(&fl::flash_rays(&c.u3(&a["cell"]), &strs(&a["pal"]), i(&a["step"]), [b[0], b[1], b[2], b[3]], u(&a["seed"]) as u64).unwrap())]
        }
        "buffer" => vec![f2(&lt::buffer(&canvas(a)))],
        "glow" => {
            let cv = canvas(a);
            let mut l = lt::buffer(&cv);
            lt::glow(&mut l, &cv, f(&a["x"]), f(&a["y"]), f(&a["r"]), f(&a["k"]));
            let mut l2 = Array2::from_elem(cv.x.dim(), 0.1);
            lt::glow(&mut l2, &cv, f(&a["x"]), f(&a["y"]), f(&a["r"]), 0.4);
            vec![f2(&l), f2(&l2)]
        }
        "glow_line" => {
            let cv = canvas(a);
            let mut l = lt::buffer(&cv);
            lt::glow_line(&mut l, &cv, pair(&a["p0"]), pair(&a["p1"]), f(&a["r"]), f(&a["k"]));
            let mut l2 = lt::buffer(&cv);
            lt::glow_line(&mut l2, &cv, pair(&a["p0"]), pair(&a["p1"]), f(&a["r"]), 0.4);
            vec![f2(&l), f2(&l2)]
        }
        "glow_ring" => {
            let cv = canvas(a);
            let mut l = lt::buffer(&cv);
            lt::glow_ring(&mut l, &cv, f(&a["x"]), f(&a["y"]), f(&a["R"]), f(&a["r"]), f(&a["k"]), f(&a["flat"]));
            let mut l2 = lt::buffer(&cv);
            lt::glow_ring(&mut l2, &cv, f(&a["x"]), f(&a["y"]), f(&a["R"]), f(&a["r"]), 0.4, 1.0);
            vec![f2(&l), f2(&l2)]
        }
        "bayer4" => vec![f2(&lt::bayer4())],
        "consts" => {
            let g: Vec<Value> = ["subtle", "medium", "strong"]
                .iter()
                .map(|n| {
                    let l = lt::glow_level(n).unwrap();
                    json!([n, l.core.0, l.core.1, l.pool_r, l.pool_k, l.mean.0, l.mean.1])
                })
                .collect();
            vec![Out::F(vec![3], lt::LEVELS.to_vec()), Out::F(vec![3], lt::CUTS.to_vec()), Out::J(json!(g))]
        }
        "steps" => {
            let mut o = lt::Steps::default();
            if let Some(v) = a["kw"].get("levels") {
                o.levels = f(v);
            }
            if let Some(v) = a["kw"].get("floor") {
                o.floor = f(v);
            }
            if let Some(v) = a["kw"].get("phase") {
                o.phase = (i(&v[0]), i(&v[1]));
            }
            vec![f2(&lt::steps(&c.a2(&a["L"]), o))]
        }
        "lt_bands" => vec![i2(&lt::bands(&c.a2(&a["L"]), i(&a["phase"])))],
        "lt_palette" => vec![Out::J(json!(lt::palette(a["hue"].as_str().unwrap()).unwrap()))],
        "flashes" => {
            let cv = canvas(a);
            let mut fs = lt::Flashes::new();
            let mut draws = vec![];
            for op in a["script"].as_array().unwrap() {
                match op[0].as_str().unwrap() {
                    "add" => fs.add(f(&op[1]), f(&op[2]), f(&op[3]), f(&op[4]), f(&op[5])),
                    "draw" => {
                        let mut l = lt::buffer(&cv);
                        fs.draw(&mut l, &cv);
                        draws.push(l);
                    }
                    _ => fs.step(),
                }
            }
            let (h, w) = draws[0].dim();
            let flat: Vec<f64> = draws.iter().flat_map(|d| d.iter().copied()).collect();
            let list: Vec<f64> = fs.list.iter().flatten().copied().collect();
            let ls = if list.is_empty() { vec![0] } else { vec![fs.list.len(), 6] };
            vec![Out::F(vec![draws.len(), h, w], flat), Out::F(ls, list)]
        }
        "flash_at" => {
            let cv = canvas(a);
            let mut flat = vec![];
            for fr in 0..12 {
                let mut l = lt::buffer(&cv);
                lt::flash_at(&mut l, &cv, fr as f64, f(&a["f0"]), 1.5, -2.0, 7.0, 0.6, f(&a["life"]));
                flat.extend(l.iter().copied());
            }
            let (h, w) = cv.x.dim();
            vec![Out::F(vec![12, h, w], flat)]
        }
        "flicker" => {
            let o = lt::Flicker { seed: i(&a["seed"]), rate: f(&a["rate"]) };
            let flat: Vec<f64> = (0..8).flat_map(|n| (0..30).map(move |fr| lt::flicker(n, fr as f64, o))).collect();
            vec![Out::F(vec![8, 30], flat)]
        }
        "luma" => vec![f2(&pfx::luma(&c.a3(&a["L"])))],
        "tint" => vec![f3(&pfx::tint(&c.a3(&a["L"]), &strs(&a["ramp"])).unwrap())],
        "gain" => vec![f3(&pfx::gain(&c.a3(&a["L"]), f(&a["k"])))],
        "keep" => vec![f3(&pfx::keep(&c.a3(&a["L"]), &c.b2(&a["mask"])))],
        "keep_f" => vec![f3(&pfx::keep_f(&c.a3(&a["L"]), &c.a2(&a["mask"])))],
        "pfx_bands" => {
            let mut o = pfx::Bands::default();
            if let Some(v) = a["kw"].get("cuts") {
                o.cuts = floats(v);
            }
            if let Some(v) = a["kw"].get("levels") {
                o.levels = floats(v);
            }
            vec![f3(&pfx::bands(&c.a3(&a["L"]), o))]
        }
        "paint" => {
            let pal: Vec<Option<String>> = a["pal"].as_array().unwrap().iter().map(|s| s.as_str().map(String::from)).collect();
            vec![u3(&pfx::paint_opt(&c.i2(&a["shades"]), &pal).unwrap())]
        }
        "composite" => vec![u3(&pfx::composite(&c.u3(&a["color"]), &c.a3(&a["L"]), a["bg"].as_str()).unwrap())],
        "load" => {
            let fx = pfx::load(c.root.join(a["dir"].as_str().unwrap()), "fx").unwrap();
            vec![stack_u(&fx.color), stack_f(&fx.light), Out::J(fx.meta)]
        }
        other => panic!("unknown case fn {other}"),
    }
}

fn diff(c: &Ctx, got: &Out, want: &Value) -> Option<String> {
    if let Some(j) = want.get("json") {
        return match got {
            Out::J(g) if g == j => None,
            Out::J(g) => Some(format!("json got {g} want {j}")),
            _ => Some("expected json".into()),
        };
    }
    let w = c.npy(want);
    match (got, &w.data) {
        (Out::F(s, g), npy::Data::F64(v)) => {
            if *s != w.shape && !(g.is_empty() && v.is_empty()) {
                return Some(format!("shape got {s:?} want {:?}", w.shape));
            }
            g.iter().zip(v).position(|(a, b)| a.to_bits() != b.to_bits()).map(|k| format!("float at {k}: rust {:e} python {:e}", g[k], v[k]))
        }
        (Out::U(s, g), npy::Data::U8(v)) => (*s != w.shape || g != v).then(|| format!("u8 differs, shape {s:?} want {:?}", w.shape)),
        (Out::I(s, g), npy::Data::I64(v)) => (*s != w.shape || g != v).then(|| format!("int differs, shape {s:?} want {:?}", w.shape)),
        _ => Some("dtype mismatch".into()),
    }
}

fn replay(fns: &[&str]) {
    let root = std::env::var("BEANFX_PARITY_FLP").map(PathBuf::from)
        .unwrap_or_else(|_| Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../../../.parity/rust/cases_fl_lt_pfx"));
    let Ok(text) = std::fs::read_to_string(root.join("cases.json")) else {
        eprintln!("cases absent at {}, skipped (run .parity/rust/gen_fl_lt_pfx.py)", root.display());
        return;
    };
    let cases: Vec<Value> = serde_json::from_str(&text).unwrap();
    let c = Ctx { root };
    let (mut n, mut fails) = (0, vec![]);
    for case in cases.iter().filter(|k| fns.contains(&k["fn"].as_str().unwrap())) {
        let got = run(&c, case["fn"].as_str().unwrap(), &case["a"]);
        let outs = case["out"].as_array().unwrap();
        assert_eq!(got.len(), outs.len(), "{} {}: output count", case["fn"], case["label"]);
        for (g, w) in got.iter().zip(outs) {
            n += 1;
            if let Some(d) = diff(&c, g, w) {
                fails.push(format!("{} [{}]: {d}", case["fn"], case["label"]));
            }
        }
    }
    println!("{n} checks over {fns:?}");
    assert!(n > 0, "no cases for {fns:?}");
    assert!(fails.is_empty(), "{} of {n} differ:\n{}", fails.len(), fails.iter().take(25).cloned().collect::<Vec<_>>().join("\n"));
}

#[test]
fn fl_colours_and_grids() {
    replay(&["hexc", "ramp", "tohex", "empty", "grid", "wgrid", "pen"]);
}

#[test]
fn fl_drawing() {
    replay(&["stroke", "stamp", "put", "line", "outline", "ground_ring"]);
}

#[test]
fn fl_noise_and_distance() {
    replay(&["lattice", "noise", "checker", "ground_dist"]);
}

#[test]
fn fl_impact() {
    replay(&["heat", "contract", "impact_order", "flash_rays"]);
}

#[test]
fn lt_light() {
    replay(&["buffer", "glow", "glow_line", "glow_ring", "bayer4", "consts", "steps", "lt_bands", "lt_palette", "flashes", "flash_at", "flicker"]);
}

#[test]
fn pfx_layers() {
    replay(&["luma", "tint", "gain", "keep", "keep_f", "pfx_bands", "paint", "composite", "load"]);
}
