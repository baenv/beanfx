//! Parity with the legacy Python kit: `.venv/bin/python .parity/rust/gen.py` writes the inputs and the legacy
//! outputs to .parity/rust/cases (or BEANFX_PARITY); this test runs the native API on the same inputs and compares
//! JSON text, wav bytes, PNG pixels and returned values. It skips when the cases are absent. The gifs, contact sheets
//! and takes it writes to pfx/rust are compared after it by .parity/rust/compare_pfx.py (Pillow decodes the gifs, and
//! the label rows, drawn with a different font, are masked).

mod common;

use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

use beanfx::{ex, img, pfx, sfx, Light, Stack};
use common::npy;
use ndarray::Array3;
use serde_json::{json, Value};

enum Frames {
    U8(Vec<Vec<Array3<u8>>>, bool),
    F64(Vec<Vec<Array3<f64>>>, bool),
}

impl Frames {
    fn u8(&self) -> Stack<'_, u8> {
        match self {
            Frames::U8(r, true) => Stack::Rows(r),
            Frames::U8(r, false) => Stack::Flat(&r[0]),
            _ => panic!("not u8"),
        }
    }
    fn flat(&self) -> &[Array3<u8>] {
        match self {
            Frames::U8(r, false) => &r[0],
            _ => panic!("not flat u8"),
        }
    }
    fn light(&self) -> Light<'_> {
        match self {
            Frames::U8(..) => Light::U8(self.u8()),
            Frames::F64(r, true) => Light::F64(Stack::Rows(r)),
            Frames::F64(r, false) => Light::F64(Stack::Flat(&r[0])),
        }
    }
}

fn split<T: Clone>(shape: &[usize], data: &[T]) -> (Vec<Vec<Array3<T>>>, bool) {
    let rows = shape.len() == 5;
    let (r, s) = if rows { (shape[0], &shape[1..]) } else { (1, shape) };
    let (n, h, w, c) = (s[0], s[1], s[2], s[3]);
    let sz = h * w * c;
    let out = (0..r)
        .map(|i| (0..n).map(|k| {
            let o = (i * n + k) * sz;
            Array3::from_shape_vec((h, w, c), data[o..o + sz].to_vec()).unwrap()
        }).collect())
        .collect();
    (out, rows)
}

struct Cases {
    root: PathBuf,
}

impl Cases {
    fn frames(&self, name: &Value) -> Frames {
        let a = npy::read(&self.root.join(name.as_str().unwrap())).unwrap();
        let mut shape = a.shape.clone();
        if shape.len() == 3 {
            shape.push(1);
        }
        match &a.data {
            npy::Data::U8(v) => { let (f, r) = split(&shape, v); Frames::U8(f, r) }
            npy::Data::F64(v) => { let (f, r) = split(&shape, v); Frames::F64(f, r) }
            npy::Data::I64(_) => panic!("int frames"),
        }
    }
}

struct Log {
    count: usize,
    fails: Vec<String>,
}

impl Log {
    fn same<T: PartialEq + std::fmt::Debug>(&mut self, label: &str, a: T, b: T) {
        self.count += 1;
        if a != b {
            let (sa, sb) = (format!("{a:?}"), format!("{b:?}"));
            println!("DIFF {label}\n  legacy: {}\n  rust:   {}", &sa[..sa.len().min(300)], &sb[..sb.len().min(300)]);
            self.fails.push(label.to_string());
        }
    }
}

fn names(d: &Path) -> BTreeSet<String> {
    fs::read_dir(d).map(|r| r.map(|e| e.unwrap().file_name().to_string_lossy().into_owned()).collect()).unwrap_or_default()
}

fn eq_files(log: &mut Log, label: &str, a: &Path, b: &Path) {
    let (fa, fb) = (names(a), names(b));
    log.same(&format!("{label} files"), &fa, &fb);
    for n in fa.intersection(&fb) {
        let (pa, pb) = (a.join(n), b.join(n));
        if n.ends_with(".png") {
            log.same(&format!("{label} {n} pixels"), img::read_raw(&pa).unwrap(), img::read_raw(&pb).unwrap());
        } else if n.ends_with(".json") || n.ends_with(".wav") {
            log.same(&format!("{label} {n} bytes"), fs::read(&pa).unwrap() == fs::read(&pb).unwrap(), true);
        }
    }
}

fn opt_f(v: &Value, k: &str, default: Option<f64>) -> Option<f64> {
    match v.get(k) {
        None => default,
        Some(Value::Null) => None,
        Some(x) => x.as_f64(),
    }
}

#[test]
fn parity_with_legacy_kit() {
    let root = std::env::var("BEANFX_PARITY").map(PathBuf::from)
        .unwrap_or_else(|_| Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../../../.parity/rust/cases"));
    let Ok(text) = fs::read_to_string(root.join("cases.json")) else {
        eprintln!("parity cases absent at {}, skipped (run .parity/rust/gen.py)", root.display());
        return;
    };
    let cases: Value = serde_json::from_str(&text).unwrap();
    let c = Cases { root: root.clone() };
    let mut log = Log { count: 0, fails: vec![] };

    for w in cases["write"].as_array().unwrap() {
        let label = format!("write {}", w["label"].as_str().unwrap());
        let dir = root.join(w["dir"].as_str().unwrap());
        let out = dir.join("rust");
        let _ = fs::remove_dir_all(&out);
        let frames = c.frames(&w["frames"]);
        let light = w.get("light").map(|v| c.frames(v));
        let color = w.get("color").map(|v| c.frames(v));
        let o = ex::Write {
            light: light.as_ref().map(Frames::light),
            color: color.as_ref().map(Frames::u8),
            states: w.get("states").map(|s| s.as_array().unwrap().iter().map(|p| {
                (p[0].as_str().unwrap().to_string(), [p[1][0].as_i64().unwrap(), p[1][1].as_i64().unwrap()])
            }).collect()).unwrap_or_default(),
            hits: w.get("hits").map(|h| h.as_array().unwrap().clone()).unwrap_or_default(),
            windup: w.get("windup").and_then(Value::as_f64).unwrap_or(0.0),
            poses: w.get("poses").map(|h| h.as_array().unwrap().clone()).unwrap_or_default(),
            target: w.get("target").cloned(),
            columns: w.get("columns").and_then(Value::as_i64),
            extra: w.get("extra").cloned(),
            hold: w.get("hold").and_then(Value::as_bool).unwrap_or(false),
            max_edge: w["max_edge"].as_i64(),
            vram_note: None,
        };
        let pivot = [w["pivot"][0].as_f64().unwrap(), w["pivot"][1].as_f64().unwrap()];
        let got = ex::write(&out, "fx", frames.u8(), w["fps"].as_f64().unwrap(), pivot, w["loop"].as_bool().unwrap(), o);
        match (&w["err"], got) {
            (Value::String(e), Err(g)) => log.same(&label, e.as_str(), g.as_str()),
            (Value::Null, Ok(g)) => {
                log.same(&format!("{label} ret"), &w["ret"], &g);
                eq_files(&mut log, &label, &dir.join("legacy"), &out);
            }
            (want, got) => log.same(&label, format!("{want}"), format!("{got:?}")),
        }
    }

    for k in cases["check"].as_array().unwrap() {
        let label = format!("check {}", k["label"].as_str().unwrap());
        let frames = c.frames(&k["frames"]);
        let light = k.get("light").map(|v| c.frames(v));
        let d = ex::Check::default();
        let o = ex::Check {
            light: light.as_ref().map(Frames::light),
            looped: k.get("loop").and_then(Value::as_bool).unwrap_or(false),
            src: k.get("src").map(|s| root.join(s.as_str().unwrap())),
            hold: k.get("hold").and_then(Value::as_bool).unwrap_or(false),
            max_colours: opt_f(k, "max_colours", None),
            trim: opt_f(k, "trim", d.trim),
            max_mb: opt_f(k, "max_mb", d.max_mb),
        };
        let got = ex::check(frames.u8(), o).unwrap();
        log.same(&label, k["want"].clone(), json!(got));
    }

    for m in cases["misc"].as_array().unwrap() {
        let label = format!("{} {}", m["kind"].as_str().unwrap(), m["label"].as_str().unwrap());
        match m["kind"].as_str().unwrap() {
            "framing" => {
                let f = c.frames(&m["frames"]);
                let got = ex::framing(f.u8()).unwrap().map(|g| json!({"box": [g.x0, g.y0, g.x1, g.y1],
                    "cell": [g.w, g.h], "cut": g.cut, "trim": g.trim}));
                log.same(&label, m["want"].clone(), got.unwrap_or(Value::Null));
                log.same(&format!("memory {label}"), m["memory"].as_f64().unwrap(), ex::memory_mb(f.u8(), false));
                log.same(&format!("memory light {label}"), m["memory_light"].as_f64().unwrap(), ex::memory_mb(f.u8(), true));
            }
            "colours" => {
                let f = c.frames(&m["frames"]);
                log.same(&label, m["want"].as_u64().unwrap() as usize, ex::colours(&f.flat()[0]));
            }
            _ => {
                let a: Vec<i64> = m["args"].as_array().unwrap().iter().map(|v| v.as_i64().unwrap()).collect();
                let got = ex::grid(a[0], a[1], a[2], a.get(3).copied());
                log.same(&label, m["want"].clone(), json!([got.0, got.1]));
            }
        }
    }

    for s in cases["sfx"].as_array().unwrap() {
        let label = format!("sfx {}", s["dir"].as_str().unwrap());
        let dir = root.join(s["dir"].as_str().unwrap());
        let out = dir.join("rust");
        let _ = fs::remove_dir_all(&out);
        fs::create_dir_all(&out).unwrap();
        let mut js = s["js"].clone();
        fs::write(out.join("fx.json"), serde_json::to_string_pretty(&js).unwrap()).unwrap();
        let o = sfx::Write {
            seed: s["seed"].as_u64().unwrap(),
            voice: s["voice"].as_str().unwrap().into(),
            element: s["element"].as_str().map(String::from),
            layers: None,
            sounds: None,
        };
        let got = sfx::write(&out, "fx", Some(&mut js), o).unwrap();
        log.same(&format!("{label} sound block"), &s["want"], &got);
        log.same(&format!("{label} js after"), &s["js_after"], &js);
        log.same(&format!("{label} check"), s["check"].clone(), json!(sfx::check(&out, &js).unwrap()));
        let (a, b) = (dir.join("legacy"), out);
        log.same(&format!("{label} files"), names(&a), names(&b));
        for n in names(&a).iter().filter(|n| n.ends_with(".wav")) {
            log.same(&format!("{label} {n} bytes"), fs::read(a.join(n)).unwrap() == fs::read(b.join(n)).unwrap(), true);
        }
        let ja: Value = serde_json::from_slice(&fs::read(a.join("fx.json")).unwrap()).unwrap();
        let jb: Value = serde_json::from_slice(&fs::read(b.join("fx.json")).unwrap()).unwrap();
        log.same(&format!("{label} json on disk"), ja, jb);
    }

    for v in cases["volley"].as_array().unwrap() {
        let lands: Vec<f64> = v["lands"].as_array().unwrap().iter().map(|x| x.as_f64().unwrap()).collect();
        let o = sfx::Volley {
            fall_frames: v["fall_frames"].as_f64().unwrap(),
            weight: v["weight"].as_str().unwrap().into(),
            gain: v["gain"].as_f64().unwrap(),
            jitter: v["jitter"].as_f64().unwrap(),
            seed: v["seed"].as_u64().unwrap(),
            hits: v["hits"].as_bool().unwrap(),
        };
        let got = sfx::volley(&lands, v["fps"].as_f64().unwrap(), o).unwrap();
        log.same(&format!("volley seed {}", v["seed"]), v["want"].clone(), Value::Array(got));
    }

    let pl = root.join("pfx/legacy");
    let pr = root.join("pfx/rust");
    let _ = fs::remove_dir_all(&pr);
    fs::create_dir_all(&pr).unwrap();
    let bg = || "#101018".to_string();
    for p in cases["pfx"].as_array().unwrap() {
        match p["kind"].as_str().unwrap() {
            "strip_gif" => {
                let tag = p["tag"].as_str().unwrap();
                let f = c.frames(&p["frames"]);
                pfx::strip(f.flat(), pr.join(format!("s_{tag}.png"))).unwrap();
                pfx::gif(f.flat(), pr.join(format!("g_{tag}.gif")), 24.0, pfx::Gif { scale: 3, bg: bg() }).unwrap();
                pfx::gif(f.flat(), pr.join(format!("g2_{tag}.gif")), 12.5, pfx::Gif { scale: 4, bg: "#fff".into() }).unwrap();
                let s = format!("s_{tag}.png");
                log.same(&format!("strip {tag}"), img::read_raw(pl.join(&s)).unwrap(), img::read_raw(pr.join(&s)).unwrap());
            }
            "contact" => {
                let i = p["i"].as_u64().unwrap();
                let f = c.frames(&p["frames"]);
                let rf = p["ref"].as_array().map(|r| (c.frames(&r[0]), r[1].as_f64().unwrap()));
                let o = pfx::Contact {
                    n: p["n"].as_u64().unwrap() as usize,
                    scale: p["scale"].as_u64().unwrap() as usize,
                    bg: bg(),
                    r#ref: rf.as_ref().map(|(fr, fps)| (fr.flat(), *fps)),
                    by: p["by"].as_str().unwrap().into(),
                    names: ["draft".into(), "ref".into()],
                };
                let got = pfx::contact(pr.join(format!("c{i}.png")), f.flat(), p["fps"].as_f64().unwrap(), o).unwrap();
                log.same(&format!("contact {i} ret"), p["want"].clone(), json!(got));
            }
            _ => {
                let opts: Vec<(String, Vec<Array3<u8>>)> = p["options"].as_array().unwrap().iter()
                    .map(|o| (o[0].as_str().unwrap().to_string(), c.frames(&o[1]).flat().to_vec())).collect();
                let got = pfx::takes(pr.join("takes.png"), &opts, pfx::Takes { fps: Some(12.0), scale: 4, bg: bg() }).unwrap();
                let got: Vec<String> = got.iter().map(|g| g.file_name().unwrap().to_string_lossy().into_owned()).collect();
                log.same("takes ret", p["want"].clone(), json!(got));
            }
        }
    }

    println!("parity: {} checks, {} failed", log.count, log.fails.len());
    assert!(log.fails.is_empty(), "parity failures: {:?}", log.fails);
}

