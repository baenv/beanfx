//! Parity of `fk` (the port of kit/fxkit.py) with the Python kit: `.venv/bin/python .parity/rust/gen_fk.py` writes the
//! inputs and Python outputs to .parity/rust/cases_fk (or BEANFX_PARITY_FK); each test runs one function on its cases
//! and compares every output bit for bit. Skips when the cases are absent.

mod common;

use std::fs;
use std::path::{Path, PathBuf};

use beanfx::fk::{self, *};
use beanfx::np;
use common::npy::{self, Array, Data};
use ndarray::Array2;
use serde_json::Value;

type Grid = Array2<f64>;

fn f(v: &Value) -> f64 {
    v.as_f64().unwrap()
}
fn of(a: &Value, k: &str, d: f64) -> f64 {
    a.get(k).map_or(d, f)
}
fn oi(a: &Value, k: &str, d: i64) -> i64 {
    a.get(k).map_or(d, |v| v.as_i64().unwrap())
}
fn sh(v: &Value) -> Vec<i8> {
    v.as_array().unwrap().iter().map(|x| x.as_i64().unwrap() as i8).collect()
}
fn pt(v: &Value) -> (f64, f64) {
    let a = v.as_array().unwrap();
    (f(&a[0]), f(&a[1]))
}
fn pts(v: &Value) -> Vec<(f64, f64)> {
    v.as_array().unwrap().iter().map(pt).collect()
}
fn tracks(v: &Value) -> Vec<Vec<(f64, f64)>> {
    v.as_array().unwrap().iter().map(pts).collect()
}
fn a4(v: &Value) -> [i8; 4] {
    sh(v).try_into().unwrap()
}
fn a3(v: &Value) -> [i8; 3] {
    sh(v).try_into().unwrap()
}
fn opt<T>(v: &Value, k: &str, g: impl Fn(&Value) -> T) -> Option<T> {
    v.get(k).filter(|x| !x.is_null()).map(g)
}

fn grid(g: &Value) -> (Grid, Grid) {
    let g = g.as_array().unwrap();
    let (cw, ch, px, py, dens) = (g[0].as_u64().unwrap() as usize, g[1].as_u64().unwrap() as usize, f(&g[2]), f(&g[3]), f(&g[4]));
    let (ys, xs) = np::mgrid(ch, cw);
    (xs.mapv(|v| (v + 0.5 - px) / dens), ys.mapv(|v| (v + 0.5 - py) / dens))
}

fn read_m(root: &Path, name: &Value) -> Array2<i8> {
    let a = npy::read(&root.join(name.as_str().unwrap())).unwrap();
    let v: Vec<i8> = a.to_f64().iter().map(|&x| x as i8).collect();
    let shape = if a.shape.len() == 2 { (a.shape[0], a.shape[1]) } else { (1, 1) };
    Array2::from_shape_vec(shape, v).unwrap()
}

fn om(m: &Array2<i8>) -> Array {
    Array { shape: vec![m.nrows(), m.ncols()], data: Data::I64(m.iter().map(|&v| v as i64).collect()) }
}
fn ob(m: &Array2<bool>) -> Array {
    Array { shape: vec![m.nrows(), m.ncols()], data: Data::U8(m.iter().map(|&v| v as u8).collect()) }
}
fn og(m: &Grid) -> Array {
    Array::f64(vec![m.nrows(), m.ncols()], m.iter().copied().collect())
}
fn ov(shape: Vec<usize>, v: Vec<f64>) -> Array {
    Array::f64(shape, v)
}
fn oidx(v: Vec<i64>, shape: Vec<usize>) -> Array {
    Array { shape, data: Data::I64(v) }
}
fn flat(p: &[(f64, f64)]) -> Vec<f64> {
    p.iter().flat_map(|&(a, b)| [a, b]).collect()
}

fn same(a: &Array, b: &Array) -> bool {
    a.shape == b.shape
        && match (&a.data, &b.data) {
            (Data::F64(x), Data::F64(y)) => x.iter().zip(y).all(|(p, q)| p.to_bits() == q.to_bits()),
            (Data::I64(x), Data::I64(y)) => x == y,
            (Data::U8(x), Data::U8(y)) => x == y,
            _ => false,
        }
}

fn run(c: &Value, root: &Path) -> Vec<Array> {
    let a = &c["args"];
    let (x, y) = grid(&c["grid"]);
    let mut m = read_m(root, &c["m"]);
    let fname = c["fn"].as_str().unwrap();
    match fname {
        "hsh" => {
            let r: Vec<f64> = a["pairs"].as_array().unwrap().iter().map(|p| fk::hsh(f(&p[0]), f(&p[1]))).collect();
            vec![ov(vec![r.len()], r)]
        }
        "math_hypot" => {
            let r: Vec<f64> = a["pairs"].as_array().unwrap().iter().map(|p| np::math_hypot(f(&p[0]), f(&p[1]))).collect();
            vec![ov(vec![r.len()], r)]
        }
        "lit_offset" => {
            let r: Vec<(f64, f64)> = a["pairs"].as_array().unwrap().iter().map(|p| lit_offset(f(&p[0]), f(&p[1]))).collect();
            vec![ov(vec![r.len(), 2], flat(&r))]
        }
        "bayer" => vec![og(&bayer(&m))],
        "debris_at" => {
            let r: Vec<f64> = a["cs"].as_array().unwrap().iter().flat_map(|c| {
                let (px, py, rest) = debris_at(c["j"].as_i64().unwrap(), f(&c["t"]), f(&c["cx"]), f(&c["cy"]), f(&c["r"]), f(&c["fly"]), f(&c["flat"]), f(&c["seed"]));
                [px, py, rest as u8 as f64]
            }).collect();
            vec![ov(vec![r.len() / 3, 3], r)]
        }
        "fade" => vec![om(&fade(&m, f(&a["amount"])))],
        "blit" => {
            let src = read_m(root, &a["src"]);
            blit(&mut m, &src);
            vec![om(&m)]
        }
        "rim" => vec![om(&rim(&m, a["s"].as_i64().unwrap() as i8))],
        "rim_if" => {
            let s = a["s"].as_i64().unwrap() as i8;
            vec![om(&rim_if(&m, s, true)), om(&rim_if(&m, s, false))]
        }
        "rot" => {
            let (u, v) = rot(&x, &y, f(&a["a"]));
            vec![og(&u), og(&v)]
        }
        "lumpy" => vec![og(&lumpy(&x, &y, f(&a["cx"]), f(&a["cy"]), f(&a["r"]), lumpy_o(a)))],
        "heat_bands" => {
            let d = &a["d"];
            let dd = lumpy(&x, &y, f(&d["cx"]), f(&d["cy"]), f(&d["r"]), lumpy_o(d));
            let cuts: Vec<f64> = a["cuts"].as_array().unwrap().iter().map(f).collect();
            let r = heat_bands(&mut m, &dd, &sh(&a["shades"]), &cuts);
            vec![ob(&r), om(&m)]
        }
        "ball" => {
            let on = ball(&mut m, &x, &y, f(&a["cx"]), f(&a["cy"]), f(&a["r"]), &[1, 2, 3, 4], Ball { amp: of(a, "amp", 0.0), ph: of(a, "ph", 0.0), seed: of(a, "seed", 0.0) });
            vec![om(&m), ob(&on)]
        }
        "puff" => {
            let on = puff(&mut m, &x, &y, f(&a["cx"]), f(&a["cy"]), f(&a["r"]), &[0, 1, 2], Puff { brk: of(a, "brk", 0.0), seed: of(a, "seed", 0.0), ph: of(a, "ph", 0.0) });
            vec![om(&m), ob(&on)]
        }
        "ring" => vec![ob(&ring(&x, &y, f(&a["cx"]), f(&a["cy"]), f(&a["r"]), f(&a["w"]), Ring { flat: f(&a["flat"]) }))],
        "kite" => {
            let on = kite(&mut m, &x, &y, f(&a["cx"]), f(&a["cy"]), f(&a["ang"]), f(&a["L"]), f(&a["w"]), &[0, 1, 2, 3], Kite { tail: of(a, "tail", 0.3) });
            vec![om(&m), ob(&on)]
        }
        "leaf" => {
            let on = leaf(&mut m, &x, &y, f(&a["cx"]), f(&a["cy"]), f(&a["ang"]), f(&a["L"]), f(&a["w"]), &[0, 1, 2, 3], Leaf { roll: of(a, "roll", 1.0), bend: of(a, "bend", 0.0) });
            vec![om(&m), ob(&on)]
        }
        "polygon" => {
            let p = polygon(f(&a["cx"]), f(&a["cy"]), f(&a["r"]), oi(a, "n", 0), f(&a["seed"]), Polygon { ph: of(a, "ph", 0.0), jit: of(a, "jit", 0.22) });
            vec![ov(vec![p.len(), 2], flat(&p))]
        }
        "facets" => {
            let ins = facets(&mut m, &x, &y, &pts(&a["pts"]), &[0, 1, 2, 3], Facets { top: a["top"].as_bool().unwrap() });
            vec![om(&m), ob(&ins)]
        }
        "streaks" => {
            let on = streaks(&mut m, &x, &y, f(&a["cx"]), f(&a["cy"]), oi(a, "n", 0), f(&a["r0"]), f(&a["r1"]), f(&a["w"]), &[1, 2, 3],
                Streaks { seed: of(a, "seed", 0.0), flat: of(a, "flat", 1.0), short: of(a, "short", 0.55), spin: of(a, "spin", 0.0), hot: of(a, "hot", 0.35) });
            vec![om(&m), ob(&on)]
        }
        "trail_puffs" => {
            let (u, v) = rot(&x, &y, f(&a["a"]));
            let d = TrailPuffs::default();
            let o = TrailPuffs {
                n: oi(a, "n", d.n),
                gap: of(a, "gap", d.gap),
                shrink: of(a, "shrink", d.shrink),
                tones: opt(a, "tones", |t| t.as_array().unwrap().iter().map(|p| (p[0].as_i64().unwrap() as i8, p[1].as_i64().unwrap() as i8)).collect()),
                wob: of(a, "wob", d.wob),
                amp: of(a, "amp", d.amp),
                seed: of(a, "seed", d.seed),
            };
            trail_puffs(&mut m, &x, &y, &u, &v, f(&a["head_u"]), f(&a["r0"]), f(&a["phase"]), o);
            vec![om(&m)]
        }
        "twinkle" => {
            twinkle(&mut m, f(&a["px"]), f(&a["py"]), oi(a, "size", 0), oi(a, "hot", 0) as i8, oi(a, "mid", 0) as i8);
            vec![om(&m)]
        }
        "to_px" => {
            let r: Vec<i64> = a["pts"].as_array().unwrap().iter().flat_map(|p| { let (i, j) = to_px(&m, &x, &y, f(&p[0]), f(&p[1])); [i as i64, j as i64] }).collect();
            vec![oidx(r.clone(), vec![r.len() / 2, 2])]
        }
        "at" => {
            let r: Vec<i64> = a["ats"].as_array().unwrap().iter().flat_map(|p| { let (i, j) = at(&m, &x, &y, f(&p[0]), f(&p[1]), f(&p[2])); [i as i64, j as i64] }).collect();
            vec![oidx(r.clone(), vec![r.len() / 2, 2])]
        }
        "claw_tracks" => {
            let d = ClawTracks::default();
            let t = claw_tracks(f(&a["span"]), ClawTracks {
                n: oi(a, "n", d.n), gap: of(a, "gap", d.gap), bow: of(a, "bow", d.bow), tilt: of(a, "tilt", d.tilt), u0: of(a, "u0", d.u0),
                sgn: of(a, "sgn", d.sgn), steps: oi(a, "steps", d.steps as i64) as usize, spread: of(a, "spread", d.spread),
            });
            vec![ov(vec![t.len(), t[0].len(), 2], t.iter().flat_map(|l| flat(l)).collect())]
        }
        "to_world" => {
            let t = to_world(&tracks(&a["tracks"]), f(&a["a"]));
            vec![ov(vec![t.len(), t[0].len(), 2], t.iter().flat_map(|l| flat(l)).collect())]
        }
        "claw_marks" => {
            let d = ClawMarks::default();
            let tip = claw_marks(&mut m, &x, &y, &tracks(&a["tracks"]), f(&a["head"]), f(&a["claw_len"]), &sh(&a["claw"]), &sh(&a["scar"]), ClawMarks {
                w_claw: of(a, "w_claw", d.w_claw), w_scar: of(a, "w_scar", d.w_scar), scar_fade: of(a, "scar_fade", d.scar_fade),
                stagger: of(a, "stagger", d.stagger), flash: of(a, "flash", d.flash), hot: a.get("hot").map(|v| v.as_i64().unwrap() as i8),
            });
            let t = tip.map_or(vec![], |p| vec![p.0, p.1]);
            vec![om(&m), ov(vec![t.len()], t)]
        }
        "drop" => {
            fk::drop(&mut m, &x, &y, f(&a["cx"]), f(&a["cy"]), f(&a["r"]), &[1, 2, 3, 4], opt(a, "tail", pt));
            vec![om(&m)]
        }
        "claw_drops" => {
            let d = ClawDrops::default();
            claw_drops(&mut m, &x, &y, &tracks(&a["tracks"]), oi(a, "f", 0), f(&a["seed"]), &sh(&a["shades"]), ClawDrops {
                r: of(a, "r", d.r), n: oi(a, "n", d.n), fly: of(a, "fly", d.fly), grav: of(a, "grav", d.grav), start: oi(a, "start", d.start), lim: of(a, "lim", d.lim),
            });
            vec![om(&m)]
        }
        "hit_cell" => {
            let t = &a["th"];
            let kind = match t["kind"].as_str().unwrap() {
                "shard" => Kind::Shard,
                "chip" => Kind::Chip,
                "ember" => Kind::Ember,
                "spike" => Kind::Spike,
                _ => Kind::Drop, // "drop" and any unknown kind draw as drops in Python
            };
            let th = Theme {
                kind, rim: t["rim"].as_i64().unwrap() as i8, streak: a3(&t["streak"]), disc: sh(&t["disc"]).try_into().unwrap(), deb: a4(&t["deb"]),
                drop: opt(t, "drop", a4), drops: opt(t, "drops", a4), mist: opt(t, "mist", a3),
            };
            vec![om(&hit_cell(&x, &y, oi(a, "f", 0), a["big"].as_bool().unwrap(), &th, oi(a, "seed", 0)))]
        }
        "hit_burst" => {
            let d = HitBurst::default();
            let out = hit_burst(&mut m, &x, &y, oi(a, "f", 0), &sh(&a["tones"]), &sh(&a["smoke"]), a["rim"].as_i64().unwrap() as i8, HitBurst {
                cx: of(a, "cx", d.cx), cy: of(a, "cy", d.cy), r: of(a, "r", d.r), flat: of(a, "flat", d.flat), seed: of(a, "seed", d.seed),
                shards: opt(a, "shards", a4), rise: of(a, "rise", d.rise),
            });
            vec![om(&m), om(&out)]
        }
        "ground_impact" => {
            let d = GroundImpact::default();
            ground_impact(&mut m, &x, &y, oi(a, "f", 0), f(&a["fps"]), &sh(&a["tones"]), &sh(&a["dust"]), GroundImpact {
                cx: of(a, "cx", d.cx), cy: of(a, "cy", d.cy), r: of(a, "r", d.r), weight: Weight::parse(a["weight"].as_str().unwrap()).unwrap(),
                flat: of(a, "flat", d.flat), life: of(a, "life", d.life), seed: of(a, "seed", d.seed),
            });
            vec![om(&m)]
        }
        other => panic!("no runner for {other}"),
    }
}

fn lumpy_o(a: &Value) -> Lumpy {
    let d = Lumpy::default();
    Lumpy { amp: of(a, "amp", d.amp), seed: of(a, "seed", d.seed), ph: of(a, "ph", d.ph), lobes: oi(a, "lobes", d.lobes) }
}

/// Runs every case of Python function `name`; returns (cases run, failures).
fn check(name: &str) -> (usize, Vec<String>) {
    let root = std::env::var("BEANFX_PARITY_FK").map(PathBuf::from)
        .unwrap_or_else(|_| Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../../../.parity/rust/cases_fk"));
    let Ok(text) = fs::read_to_string(root.join("cases.json")) else {
        eprintln!("kit_fk cases absent at {}, skipped (run .parity/rust/gen_fk.py)", root.display());
        return (0, vec![]);
    };
    let cases: Value = serde_json::from_str(&text).unwrap();
    let (mut n, mut bad) = (0, vec![]);
    for (i, c) in cases.as_array().unwrap().iter().enumerate().filter(|(_, c)| c["fn"] == name) {
        n += 1;
        let got = run(c, &root);
        let want: Vec<Array> = c["outs"].as_array().unwrap().iter().map(|o| npy::read(&root.join(o.as_str().unwrap())).unwrap()).collect();
        let ok = got.len() == want.len() && got.iter().zip(&want).all(|(g, w)| same(g, w));
        if !ok {
            let diff = got.iter().zip(&want).map(|(g, w)| {
                if g.shape != w.shape { return format!("shape {:?} vs {:?}", g.shape, w.shape); }
                let (gf, wf) = (g.to_f64(), w.to_f64());
                format!("{} of {} differ", gf.iter().zip(&wf).filter(|(p, q)| p.to_bits() != q.to_bits()).count(), gf.len())
            }).collect::<Vec<_>>().join("; ");
            bad.push(format!("case {i} {} grid {} args {}: {diff}", name, c["grid"], c["args"]));
        }
    }
    (n, bad)
}

mod cases {
    use super::check;

    macro_rules! parity {
    ($($name:ident),* $(,)?) => {$(
        #[test]
        fn $name() {
            let (n, bad) = check(stringify!($name));
            if n > 0 { eprintln!("{}: {} cases", stringify!($name), n); }
            assert!(bad.is_empty(), "{} of {} cases differ; first: {}", bad.len(), n, bad[0].chars().take(600).collect::<String>());
        }
    )*};
}

    parity!(
    hsh, math_hypot, lit_offset, bayer, debris_at, fade, blit, rim, rim_if, rot, lumpy, heat_bands, ball, puff, ring, kite, leaf,
    polygon, facets, streaks, trail_puffs, twinkle, to_px, at, claw_tracks, to_world, claw_marks, drop, claw_drops, hit_cell,
    hit_burst, ground_impact,
);
}
