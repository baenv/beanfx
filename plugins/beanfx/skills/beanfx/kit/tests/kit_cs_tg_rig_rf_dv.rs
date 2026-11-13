//! Parity of the Rust cs, tg, rig, rf and dv modules with the Python kit: `.venv/bin/python
//! .parity/rust/gen_cs_tg_rig_rf_dv.py` writes inputs and the Python results to
//! .parity/rust/cases_cs_tg_rig_rf_dv (or BEANFX_PARITY_KIT); this test replays them and compares arrays bit for
//! bit. It skips when the cases are absent.

mod common;

use std::path::{Path, PathBuf};

use beanfx::{cs, dv, np, rf, rig, tg};
use common::npy;
use ndarray::{Array2, Array3};
use serde_json::Value;

struct Log {
    count: usize,
    fails: Vec<String>,
}

impl Log {
    fn ok<T: PartialEq + std::fmt::Debug>(&mut self, label: &str, want: T, got: T) {
        self.count += 1;
        if want != got {
            let (a, b) = (format!("{want:?}"), format!("{got:?}"));
            println!("DIFF {label}\n  python: {}\n  rust:   {}", &a[..a.len().min(300)], &b[..b.len().min(300)]);
            self.fails.push(label.to_string());
        }
    }
}

struct C {
    root: PathBuf,
}

fn bits(v: impl IntoIterator<Item = f64>) -> Vec<u64> {
    v.into_iter().map(|x| x.to_bits()).collect()
}

fn fa(v: &Value) -> f64 {
    v.as_f64().unwrap_or_else(|| panic!("not a number: {v}"))
}

fn fv(v: &Value) -> Vec<f64> {
    v.as_array().unwrap().iter().map(fa).collect()
}

fn p2(v: &Value) -> [f64; 2] {
    [fa(&v[0]), fa(&v[1])]
}

fn arm(v: &Value) -> cs::Arm {
    (p2(&v[0]), p2(&v[1]))
}

fn pose(v: &Value) -> cs::Pose {
    (arm(&v[0]), arm(&v[1]))
}

fn s(v: &Value) -> &str {
    v.as_str().unwrap()
}

impl C {
    fn raw(&self, v: &Value) -> npy::Array {
        npy::read(&self.root.join(s(v))).unwrap()
    }
    fn f2(&self, v: &Value) -> Array2<f64> {
        let a = self.raw(v);
        Array2::from_shape_vec((a.shape[0], a.shape[1]), a.to_f64()).unwrap()
    }
    fn b2(&self, v: &Value) -> Array2<bool> {
        let a = self.raw(v);
        Array2::from_shape_vec((a.shape[0], a.shape[1]), a.to_f64().iter().map(|&x| x != 0.0).collect()).unwrap()
    }
    fn i2(&self, v: &Value) -> Array2<i64> {
        let a = self.raw(v);
        Array2::from_shape_vec((a.shape[0], a.shape[1]), a.to_f64().iter().map(|&x| x as i64).collect()).unwrap()
    }
    fn i8_2(&self, v: &Value) -> Array2<i8> {
        self.i2(v).mapv(|x| x as i8)
    }
    fn u3(&self, v: &Value) -> Array3<u8> {
        let a = self.raw(v);
        Array3::from_shape_vec((a.shape[0], a.shape[1], a.shape[2]), a.as_u8().to_vec()).unwrap()
    }
    fn f3(&self, v: &Value) -> Array3<f64> {
        let a = self.raw(v);
        Array3::from_shape_vec((a.shape[0], a.shape[1], a.shape[2]), a.to_f64()).unwrap()
    }
    fn vec_f(&self, v: &Value) -> Vec<f64> {
        self.raw(v).to_f64()
    }
    fn chains(&self, v: &Value) -> Vec<Array2<f64>> {
        v.as_array().unwrap().iter().map(|n| self.f2(n)).collect()
    }
}

fn same_f2(log: &mut Log, label: &str, want: &Array2<f64>, got: &Array2<f64>) {
    log.ok(&format!("{label} shape"), want.dim(), got.dim());
    log.ok(label, bits(want.iter().cloned()), bits(got.iter().cloned()));
}

fn same_chains(log: &mut Log, label: &str, want: &[Array2<f64>], got: &[Array2<f64>]) {
    log.ok(&format!("{label} count"), want.len(), got.len());
    for (i, (w, g)) in want.iter().zip(got).enumerate() {
        same_f2(log, &format!("{label}[{i}]"), w, g);
    }
}

#[derive(Default)]
struct Rec {
    lens: Vec<usize>,
    ys: Vec<i64>,
    xs: Vec<i64>,
    rgb: Vec<f64>,
    a: Vec<f64>,
}

fn rec_over(r: &mut Rec) -> impl FnMut(&[i64], &[i64], &Array2<f64>, &[f64]) + '_ {
    move |ys, xs, rgb, a| {
        r.lens.push(ys.len());
        r.ys.extend_from_slice(ys);
        r.xs.extend_from_slice(xs);
        r.rgb.extend(rgb.iter().cloned());
        r.a.extend_from_slice(a);
    }
}

fn same_rec(log: &mut Log, c: &C, label: &str, want: &Value, got: &Rec) {
    let lens: Vec<usize> = want["lens"].as_array().unwrap().iter().map(|v| v.as_u64().unwrap() as usize).collect();
    log.ok(&format!("{label} over lens"), lens, got.lens.clone());
    log.ok(&format!("{label} over ys"), c.raw(&want["ys"]).to_f64().iter().map(|&x| x as i64).collect::<Vec<_>>(), got.ys.clone());
    log.ok(&format!("{label} over xs"), c.raw(&want["xs"]).to_f64().iter().map(|&x| x as i64).collect::<Vec<_>>(), got.xs.clone());
    log.ok(&format!("{label} over rgb"), bits(c.vec_f(&want["rgb"])), bits(got.rgb.iter().cloned()));
    log.ok(&format!("{label} over a"), bits(c.vec_f(&want["a"])), bits(got.a.iter().cloned()));
}

fn pts(v: &Value) -> Vec<[f64; 2]> {
    v.as_array().unwrap().iter().map(p2).collect()
}

fn same_pts(log: &mut Log, label: &str, want: &[[f64; 2]], got: &[[f64; 2]]) {
    log.ok(label, bits(want.iter().flatten().cloned()), bits(got.iter().flatten().cloned()));
}

#[test]
fn parity_cs_tg_rig_rf_dv() {
    let root = std::env::var("BEANFX_PARITY_KIT").map(PathBuf::from)
        .unwrap_or_else(|_| Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../../../.parity/rust/cases_cs_tg_rig_rf_dv"));
    let Ok(text) = std::fs::read_to_string(root.join("cases.json")) else {
        eprintln!("cases absent at {}, skipped (run .parity/rust/gen_cs_tg_rig_rf_dv.py)", root.display());
        return;
    };
    let cases: Vec<Value> = serde_json::from_str(&text).unwrap();
    let c = C { root: root.clone() };
    let mut log = Log { count: 0, fails: vec![] };

    for (ci, cs_) in cases.iter().enumerate() {
        let fname = s(&cs_["fn"]);
        let label = format!("{fname}#{ci}");
        match fname {
            "outline" => {
                let m = c.b2(&cs_["mask"]);
                same_f2(&mut log, &label, &c.f2(&cs_["out"]), &dv::outline(&m).unwrap());
            }
            "spine" => {
                let m = c.b2(&cs_["mask"]);
                let ml = cs_["min_len"].as_u64().unwrap() as usize;
                same_chains(&mut log, &label, &c.chains(&cs_["out"]), &dv::spine(&m, ml));
            }
            "largest" => {
                let m = c.b2(&cs_["mask"]);
                log.ok(&label, c.b2(&cs_["out"]), dv::largest(&m));
            }
            "scatter" => {
                let m = c.b2(&cs_["mask"]);
                let (n, seed) = (cs_["n"].as_u64().unwrap() as usize, cs_["seed"].as_u64().unwrap());
                same_f2(&mut log, &label, &c.f2(&cs_["out"]), &dv::scatter(&m, n, seed));
            }
            "chains" => {
                let m = c.b2(&cs_["mask"]);
                same_chains(&mut log, &label, &c.chains(&cs_["out"]), &dv::chains(&m));
            }
            "simplify" => {
                let p = c.f2(&cs_["pts"]);
                let (n, closed) = (cs_["n"].as_u64().unwrap() as usize, cs_["closed"].as_bool().unwrap());
                same_f2(&mut log, &label, &c.f2(&cs_["out"]), &dv::simplify(&p, n, closed));
            }
            "part_lines" => {
                let p = c.i2(&cs_["parts"]);
                let ml = cs_["min_len"].as_u64().unwrap() as usize;
                same_chains(&mut log, &label, &c.chains(&cs_["out"]), &dv::part_lines(&p, ml));
            }
            "local" | "world" => {
                let p = c.f2(&cs_["pts"]);
                let (an, ang, sc) = (p2(&cs_["anchor"]), fa(&cs_["ang"]), fa(&cs_["scale"]));
                let got = if fname == "local" { dv::local(&p, an, ang, sc) } else { dv::world(&p, an, ang, sc) };
                same_f2(&mut log, &label, &c.f2(&cs_["out"]), &got);
            }
            "load" => {
                let kw = &cs_["kw"];
                let o = |k: &str| kw.get(k).map(|v| v.as_u64().unwrap() as usize);
                let got = rf::load(root.join(s(&cs_["png"])), o("height"), o("width")).unwrap();
                let want = c.f3(&cs_["out"]);
                log.ok(&format!("{label} shape"), want.dim(), got.dim());
                log.ok(&label, bits(want.iter().cloned()), bits(got.iter().cloned()));
            }
            "trace" => {
                let kw = &cs_["kw"];
                let mut o = rf::Trace::default();
                if let Some(v) = kw.get("height") { o.height = Some(v.as_u64().unwrap() as usize); }
                if let Some(v) = kw.get("width") { o.width = Some(v.as_u64().unwrap() as usize); }
                if let Some(v) = kw.get("tones") { o.tones = v.as_u64().unwrap() as usize; }
                if let Some(v) = kw.get("share") { o.share = fa(v); }
                if let Some(v) = kw.get("tol") { o.tol = fa(v); }
                let t = rf::trace(root.join(s(&cs_["png"])), o).unwrap();
                let want = c.f3(&cs_["img"]);
                log.ok(&format!("{label} img"), bits(want.iter().cloned()), bits(t.img.iter().cloned()));
                log.ok(&format!("{label} mask"), c.b2(&cs_["mask"]), t.mask.clone());
                same_f2(&mut log, &format!("{label} lum"), &c.f2(&cs_["lum"]), &t.lum);
                same_f2(&mut log, &format!("{label} grad"), &c.f2(&cs_["grad"]), &t.grad);
                same_f2(&mut log, &format!("{label} angle"), &c.f2(&cs_["angle"]), &t.angle);
                log.ok(&format!("{label} edges"), c.b2(&cs_["edges"]), t.edges.clone());
                log.ok(&format!("{label} shade"), c.i8_2(&cs_["shade"]), t.shade.clone());
                same_f2(&mut log, &format!("{label} outline"), &c.f2(&cs_["outline"]), &t.outline);
                same_chains(&mut log, &format!("{label} spine"), &c.chains(&cs_["spine"]), &t.spine);
                log.ok(&format!("{label} paint"), c.i8_2(&cs_["paint"]), rf::paint(&t, rf::Paint::default()).unwrap());
                let tones = t.shade.iter().cloned().max().unwrap() as usize + 1;
                let ri: Vec<i64> = [3, 5, 7, 9, 11][..tones.min(5)].to_vec();
                log.ok(&format!("{label} paint2"), c.i8_2(&cs_["paint2"]), rf::paint(&t, rf::Paint { ramp_index: Some(ri), edge: None }).unwrap());
                log.ok(&format!("{label} paint3"), c.i8_2(&cs_["paint3"]),
                       rf::paint(&t, rf::Paint { ramp_index: Some(vec![1, 2]), edge: Some(6) }).unwrap());
            }
            "reaction" => {
                let hits = cs_["hits"].as_array().unwrap();
                let fps = fa(&cs_["fps"]);
                for (f, want) in cs_["frames"].as_array().unwrap().iter().zip(cs_["out"].as_array().unwrap()) {
                    let (a, b, cc, d) = tg::reaction(fa(f), hits, fps);
                    log.ok(&format!("{label} f={f}"), bits(fv(want)), bits([a, b, cc, d]));
                }
            }
            "tg_draw" => {
                let hits = cs_["hits"].as_array().unwrap();
                for (i, d) in cs_["cases"].as_array().unwrap().iter().enumerate() {
                    let mut o = tg::Draw::default();
                    if let Some(v) = d["kw"].get("facing") { o.facing = fa(v); }
                    if let Some(v) = d["kw"].get("height") { o.height = fa(v); }
                    let got = tg::draw((70, 60), (30.0, 62.0), fa(&d["f"]), hits, fa(&cs_["fps"]), o).unwrap();
                    log.ok(&format!("{label}[{i}] f={} kw={}", d["f"], d["kw"]), c.u3(&d["out"]), got);
                }
            }
            "under" | "over" => {
                let (e, d) = (c.u3(&cs_["effect"]), c.u3(&cs_["dummy"]));
                let got = if fname == "under" { tg::under(&e, &d) } else { rig::over(&e, &d) };
                log.ok(&label, c.u3(&cs_["out"]), got);
            }
            "rig" => rig_case(&mut log, &c, cs_),
            "rig_missing" => {
                let got = rig::load("no_such_rig_xyz", Some(Path::new(s(&cs_["root"])))).err().unwrap();
                log.ok(&label, s(&cs_["msg"]).to_string(), got);
            }
            "project_root" => {
                let got = rig::project_root(Some(Path::new(s(&cs_["start"]))));
                log.ok(&label, s(&cs_["out"]).to_string(), got.display().to_string());
            }
            "pose_at" => {
                for (i, p) in cs_["cases"].as_array().unwrap().iter().enumerate() {
                    let keys = |v: &Value| -> Vec<(f64, String)> {
                        v.as_array().unwrap().iter().map(|k| (fa(&k[0]), s(&k[1]).to_string())).collect()
                    };
                    let (fk, bk) = (keys(&p["keys"]), keys(&p["bk"]));
                    let fk: Vec<(f64, &str)> = fk.iter().map(|(a, b)| (*a, b.as_str())).collect();
                    let bk: Vec<(f64, &str)> = bk.iter().map(|(a, b)| (*a, b.as_str())).collect();
                    let aim = if p["aim"].is_null() { None } else { Some(p2(&p["aim"])) };
                    let got = cs::pose_at(fa(&p["f"]), &fk, &bk, aim, fa(&p["jab"])).unwrap();
                    let w = pose(&p["out"]);
                    let fl = |q: cs::Pose| bits([q.0 .0[0], q.0 .0[1], q.0 .1[0], q.0 .1[1], q.1 .0[0], q.1 .0[1], q.1 .1[0], q.1 .1[1]]);
                    log.ok(&format!("{label}[{i}]"), fl(w), fl(got));
                }
            }
            "aim_from" => {
                for (i, p) in cs_["cases"].as_array().unwrap().iter().enumerate() {
                    let got = cs::aim_from(p2(&p["foot"]), fa(&p["sc"]), p2(&p["target"]));
                    log.ok(&format!("{label}[{i}]"), bits(fv(&p["out"])), bits(got));
                }
            }
            "bez" => {
                for (i, p) in cs_["cases"].as_array().unwrap().iter().enumerate() {
                    let got = cs::bez(p2(&p["p0"]), p2(&p["c"]), p2(&p["p1"]), p["n"].as_u64().unwrap() as usize);
                    same_pts(&mut log, &format!("{label}[{i}]"), &pts(&p["out"]), &got);
                }
            }
            "shade" => {
                let m = c.b2(&cs_["mask"]);
                for p in cs_["cases"].as_array().unwrap() {
                    log.ok(&format!("{label} base {}", p["base"]), c.i2(&p["out"]), cs::shade(&m, p["base"].as_i64().unwrap()));
                }
            }
            "geom" => {
                let (w, h) = (30usize, 24usize);
                let x = Array2::from_shape_fn((h, w), |(_, i)| i as f64);
                let y = Array2::from_shape_fn((h, w), |(j, _)| j as f64);
                let poly = pts(&cs_["poly"]);
                log.ok(&format!("{label} poly_in"), c.b2(&cs_["poly_in"]), cs::poly_in(&x.view(), &y.view(), &poly));
                let (a, b, cc) = (p2(&cs_["a"]), p2(&cs_["b"]), p2(&cs_["c"]));
                log.ok(&format!("{label} tri"), c.b2(&cs_["tri"]), cs::tri(&x.view(), &y.view(), a, b, cc));
                same_f2(&mut log, &format!("{label} seg_d"), &c.f2(&cs_["seg"]), &cs::seg_d(&x.view(), &y.view(), a, b));
                same_f2(&mut log, &format!("{label} seg_d0"), &c.f2(&cs_["seg0"]), &cs::seg_d(&x.view(), &y.view(), [7.0, 7.0], [7.0, 7.0]));
            }
            "strand" => {
                let (lx, ly) = (c.f2(&cs_["lx"]), c.f2(&cs_["ly"]));
                for (i, p) in cs_["cases"].as_array().unwrap().iter().enumerate() {
                    let mut o = cs::Strand::default();
                    if let Some(v) = p["kw"].get("n") { o.n = v.as_u64().unwrap() as usize; }
                    if let Some(v) = p["kw"].get("mw") { o.mw = fa(v); }
                    let wave = |k: usize| 0.3 * (k as f64).sin();
                    let (m, got) = cs::strand(&lx.view(), &ly.view(), [-3.0, -2.0], 1.2, 2.5, 6.0, 1.4, 0.3, &wave, o);
                    log.ok(&format!("{label}[{i}] mask"), c.b2(&p["mask"]), m);
                    same_pts(&mut log, &format!("{label}[{i}] pts"), &pts(&p["pts"]), &got);
                }
            }
            "glows" => {
                for (i, p) in cs_["cases"].as_array().unwrap().iter().enumerate() {
                    let mut l = Array2::<f64>::zeros((70, 80));
                    let a = p["args"].as_array().unwrap();
                    match s(&p["f"]) {
                        "glow" => cs::glow(&mut l, fa(&a[0]), fa(&a[1]), fa(&a[2]), fa(&a[3]), fa(&a[4])),
                        "glow_line" => cs::glow_line(&mut l, p2(&a[0]), p2(&a[1]), fa(&a[2]), fa(&a[3])),
                        _ => cs::glow_ring(&mut l, fa(&a[0]), fa(&a[1]), fa(&a[2]), fa(&a[3]), fa(&a[4]), fa(&a[5])),
                    }
                    same_f2(&mut log, &format!("{label}[{i}] {}", p["f"]), &c.f2(&p["out"]), &l);
                }
            }
            "ellipse_line" => {
                for (i, p) in cs_["cases"].as_array().unwrap().iter().enumerate() {
                    let mut r = Rec::default();
                    {
                        let mut over = rec_over(&mut r);
                        let mut o = cs::Ellipse::default();
                        if let Some(v) = p["kw"].get("phase") { o.phase = fa(v); }
                        if let Some(v) = p["kw"].get("dash") { o.dash = Some(fa(v)); }
                        if p.get("small").is_some() {
                            cs::ellipse_line(&mut over, 3.0, 3.0, 0.4, 0.4, "#112233", 1.0, o).unwrap();
                        } else {
                            cs::ellipse_line(&mut over, 30.4, 20.6, 12.2, 9.1, "#fff4c8", 0.5, o).unwrap();
                        }
                    }
                    same_rec(&mut log, &c, &format!("{label}[{i}]"), &p["rec"], &r);
                }
            }
            "cs_draw" => draw_cases(&mut log, &c, cs_, &label),
            other => panic!("unknown case {other}"),
        }
    }
    println!("{} checks, {} differences", log.count, log.fails.len());
    assert!(log.fails.is_empty(), "differences: {:?}", log.fails);
}

fn draw_cases(log: &mut Log, c: &C, cs_: &Value, label: &str) {
    let sh = cs_["shape"].as_array().unwrap();
    let shape = (sh[0].as_u64().unwrap() as usize, sh[1].as_u64().unwrap() as usize);
    for (i, d) in cs_["cases"].as_array().unwrap().iter().enumerate() {
        let lb = format!("{label}[{i}]");
        let pal: Option<Vec<String>> = d["pal"].as_array().map(|a| a.iter().map(|v| s(v).to_string()).collect());
        let pal_refs: Option<Vec<&str>> = pal.as_ref().map(|p| p.iter().map(|x| x.as_str()).collect());
        let mut o = cs::Draw {
            lift: fa(&d["lift"]),
            flut: fa(&d["flut"]),
            hair: s(&d["hair"]),
            ghost: fa(&d["ghost"]),
            trail: if d["trail"].is_null() { None } else { Some(pose(&d["trail"])) },
            ..Default::default()
        };
        if let Some(p) = &pal_refs {
            o.palette = p;
        }
        let (foot, sc, f) = (p2(&d["foot"]), fa(&d["sc"]), fa(&d["f"]));
        let ps = pose(&d["pose"]);
        let mut r = Rec::default();
        let g = {
            let mut over = rec_over(&mut r);
            cs::draw(&mut over, shape, foot, sc, ps, f, o).unwrap()
        };
        same_rec(log, c, &format!("{lb} draw"), &d["rec"], &r);
        let w = &d["g"];
        log.ok(&format!("{lb} sc"), fa(&w["sc"]).to_bits(), g.sc.to_bits());
        for (k, got) in [("head", g.head), ("neck", g.neck), ("hip", g.hip), ("feet", g.feet), ("finger", g.finger)] {
            same_pts(log, &format!("{lb} {k}"), &[p2(&w[k])], &[got]);
        }
        let hair: Vec<Vec<[f64; 2]>> = w["hair"].as_array().unwrap().iter().map(pts).collect();
        log.ok(&format!("{lb} hair"), hair.iter().map(|h| bits(h.iter().flatten().cloned())).collect::<Vec<_>>(),
               g.hair.iter().map(|h| bits(h.iter().flatten().cloned())).collect::<Vec<_>>());
        match (&d["mask"], &g.mask) {
            (Value::Null, None) => log.ok(&format!("{lb} mask"), true, true),
            (m, Some(gm)) => {
                let r2 = |v: &Value| (v[0].as_u64().unwrap() as usize, v[1].as_u64().unwrap() as usize);
                log.ok(&format!("{lb} mask sy"), r2(&m["sy"]), (gm.sy.start, gm.sy.end));
                log.ok(&format!("{lb} mask sx"), r2(&m["sx"]), (gm.sx.start, gm.sx.end));
                same_f2(log, &format!("{lb} mask inner"), &c.f2(&m["inner"]), &gm.inner);
            }
            _ => log.ok(&format!("{lb} mask presence"), true, false),
        }
        let mut l = Array2::<f64>::zeros(shape);
        cs::body_light(&mut l, &g, 0.7);
        cs::finger_light(&mut l, &g, 0.8, 0.5);
        same_f2(log, &format!("{lb} light"), &c.f2(&d["light"]), &l);
        if fa(&d["ghost"]) > 0.0 {
            let mut r2 = Rec::default();
            let mut l2 = Array2::<f64>::zeros(shape);
            {
                let mut over = rec_over(&mut r2);
                cs::ghost_light(&mut over, &mut l2, &g, fa(&d["ghost"]), f, 0.6).unwrap();
            }
            same_rec(log, c, &format!("{lb} ghost_light"), &d["ghost_rec"], &r2);
            same_f2(log, &format!("{lb} ghost L"), &c.f2(&d["ghost_light"]), &l2);
        }
    }
}

fn rig_case(log: &mut Log, c: &C, cs_: &Value) {
    for rc in cs_["rigs"].as_array().unwrap() {
        let name = s(&rc["name"]);
        let r = rig::load(name, None).unwrap();
        let lb = format!("rig {name}");
        log.ok(&format!("{lb} view"), s(&rc["view"]).to_string(), r.view.clone());
        log.ok(&format!("{lb} anims"), rc["anims"].as_array().unwrap().iter().map(|v| s(v).to_string()).collect::<Vec<_>>(), r.anims());
        log.ok(&format!("{lb} keyerr"), s(&rc["keyerr"]).to_string(), r.anim("nope").err().unwrap());
        for e in rc["list"].as_array().unwrap() {
            let an = s(&e["anim"]);
            let dir = e["dir"].as_str();
            let lb = format!("{lb} {an} {dir:?}");
            let fr = r.frames(an, dir).unwrap();
            log.ok(&format!("{lb} n"), e["n"].as_u64().unwrap() as usize, fr.len());
            log.ok(&format!("{lb} frames0"), c.u3(&e["frames0"]), fr[0].clone());
            let stack = c.raw(&e["framesN"]);
            let want: Vec<u8> = stack.as_u8().to_vec();
            let got: Vec<u8> = fr.iter().flat_map(|f| f.iter().cloned()).collect();
            log.ok(&format!("{lb} frames"), want, got);
            let m = rig::measure(&fr).unwrap();
            log.ok(&format!("{lb} measure"), vec![fa(&e["measure"][0]), fa(&e["measure"][1])], vec![m[0] as f64, m[1] as f64]);
            log.ok(&format!("{lb} pivot"), bits(fv(&e["pivot"])), bits(r.pivot(an).unwrap()));
            log.ok(&format!("{lb} contact"), e["contact"].to_string(), Value::Array(r.contact(an).unwrap()).to_string());
            log.ok(&format!("{lb} swing"), e["swing"].to_string(), Value::Array(r.swing(an, dir).unwrap()).to_string());
            let root: Vec<f64> = e["root"].as_array().unwrap().iter().flat_map(fv).collect();
            log.ok(&format!("{lb} root"), bits(root), bits(r.root(an, dir).unwrap().iter().flatten().cloned()));
            log.ok(&format!("{lb} fps"), fa(&e["fps"]).to_bits(), r.fps_of(an).unwrap().to_bits());
            if let Some(arc) = e.get("arc") {
                let (a0, a1) = r.arc(an, dir, 0).unwrap();
                log.ok(&format!("{lb} arc"), bits(fv(arc)), bits([a0, a1]));
                let sets = [(a0, a1, 60.0), (a1, a0, 60.0), (a0 + 100.0, a1 - 100.0, 60.0), (a0 + 10.0, a1 + 20.0, 5.0)];
                for (k, (x, y, t)) in sets.into_iter().enumerate() {
                    let got = r.check_arc(an, x, y, rig::CheckArc { direction: dir, stroke: 0, tol: t }).unwrap();
                    log.ok(&format!("{lb} check{k}"), e["check"][k].to_string(), serde_json::json!(got).to_string());
                }
            }
            for (k, p) in e["place"].as_array().unwrap().iter().enumerate() {
                let kw = &p["kw"];
                let o = rig::Place {
                    direction: dir,
                    start: kw.get("start").map(|v| v.as_i64().unwrap()).unwrap_or(0),
                    hold: kw.get("hold").map(|v| v.as_bool().unwrap()).unwrap_or(true),
                    travel: kw.get("travel").map(|v| v.as_bool().unwrap()).unwrap_or(false),
                };
                let got = r.place((90, 110), [40.5, 70.2], an, p["k"].as_i64().unwrap(), o).unwrap();
                log.ok(&format!("{lb} place{k}"), c.u3(&p["out"]), got);
            }
            let fa_ = r.frame_at(an, 99, rig::FrameAt { direction: dir, start: 0, hold: false }).unwrap();
            log.ok(&format!("{lb} frame_at none"), e["frame_at_none"].as_bool().unwrap(), fa_.is_none());
            for (k, m) in e["meta"].as_array().unwrap().iter().enumerate() {
                let kw = &m["kw"];
                let o = rig::Meta {
                    start: kw.get("start").map(|v| v.as_i64().unwrap()).unwrap_or(0),
                    layer: kw.get("layer").map(s).unwrap_or("front"),
                    directions: kw.get("directions").map(|v| v.as_array().unwrap().iter().map(|x| s(x).to_string()).collect()),
                    offset: kw.get("offset").map(fa),
                };
                let got = r.meta(an, fa(&m["efps"]), o);
                match (m.get("err"), got) {
                    (Some(err), Err(g)) => log.ok(&format!("{lb} meta{k} err"), s(err).to_string(), g),
                    (None, Ok(g)) => log.ok(&format!("{lb} meta{k}"), m["out"].to_string(), Value::Object(g).to_string()),
                    (w, g) => log.ok(&format!("{lb} meta{k} kind"), format!("{w:?}"), format!("{g:?}")),
                }
            }
        }
    }
    let _ = np::round(0.0);
}
