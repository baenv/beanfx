//! The draft runner end to end: a small burst through `dr::run`, its commands and its errors.

mod common;

use beanfx::dr::{self, Aura, Canvas, Effect, Layer, Spec};
use beanfx::ex::{self, Hit};
use beanfx::lt;
use beanfx::serde_json::Value;
use std::path::Path;

const FPS: f64 = 24.0;

/// A disc that swells and fades on a 32x32 cell, with glow, a hit and, when `aura` is set, aura parts.
struct Burst {
    aura: bool,
    steps: bool,
    fail_at: Option<usize>,
}

impl Effect for Burst {
    fn spec(&self) -> Spec {
        let mut sp = Spec::new("burst", 32, 32, 10, FPS);
        sp.hits = vec![ex::hit(3, FPS, Hit { weight: Some("medium".into()), ..Default::default() })];
        sp.states = vec![("burst".into(), [0, 5]), ("fade".into(), [6, 9])];
        sp.dummy = Some([26.0, 30.0]);
        sp.edge_fade = 2.0;
        sp.trim = None;
        if self.steps {
            sp.steps = Some(lt::Steps::default());
        }
        let note = beanfx::fc::part("x.png", 8, 8, 2, FPS, [4.0, 4.0], false, "target", None);
        sp.extra.insert("parts".into(), beanfx::serde_json::json!({"note_part": note}));
        if self.aura {
            sp.caster_foot = Some([16.0, 28.0]);
            sp.aura = Some(Aura { frames: 4, w: 16, h: 12, pivot: [8.0, 10.0] });
        }
        sp
    }

    fn draw(&self, cv: &mut Canvas, f: usize, _seed: u64, layer: Layer) -> Result<(), String> {
        if self.fail_at == Some(f) {
            return Err("boom".into());
        }
        let t = f as f64 / 9.0;
        match layer {
            Layer::Effect => {
                let r = if f == 9 { 0.6 } else { 2.0 + 7.0 * (t * std::f64::consts::PI).sin() };
                cv.ellipse(16.0, 16.0, r, r * 0.8, dr::hex("#ffb060"), 1.0);
                cv.line([16.0 - r, 16.0], [16.0 + r, 16.0], dr::hex("#fff0d0"), 1.0);
                if f < 9 {
                    cv.glow(16.0, 16.0, r + 2.0, 0.5 * (1.0 - t));
                }
            }
            Layer::Caster => cv.ellipse(16.0, 26.0, 2.0, 2.0, dr::hex("#404050"), 1.0),
            Layer::AuraBack | Layer::AuraFront => {
                let dy = if layer == Layer::AuraBack { 0.0 } else { 1.0 };
                cv.ellipse(16.0, 26.0 + dy, 4.0, 1.5, dr::hex("#80c0ff"), 0.8);
                cv.glow(16.0, 26.0, 3.0, 0.3);
            }
            Layer::Behind => {}
        }
        Ok(())
    }
}

fn draft(tag: &str) -> std::path::PathBuf {
    let dir = common::tmpdir(tag);
    std::fs::create_dir_all(dir.join("src")).unwrap();
    std::fs::write(dir.join("src/main.rs"), "// a test draft\n").unwrap();
    dir
}

fn args(a: &[&str]) -> Vec<String> {
    a.iter().map(|s| s.to_string()).collect()
}

fn read(p: &Path) -> Value {
    beanfx::serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap()
}

#[test]
fn run_writes_every_output_and_the_parts() {
    let dir = draft("runner_full");
    let code = dr::run(&Burst { aura: true, steps: false, fail_at: None }, &dir, &[]).unwrap();
    assert!(code <= 1, "exit {code}");
    let out = dir.join("out");
    for f in ["burst_1x.png", "burst_4x_dark.png", "burst_4x_mid.png", "burst.gif", "contact.png",
              "sheets/burst.png", "sheets/burst.json", "sheets/burst_aura_back.json", "sheets/burst_aura_front.json"] {
        assert!(out.join(f).is_file(), "missing {f}");
    }
    let js = read(&out.join("sheets/burst.json"));
    let bfx = &js["meta"]["beanfx"];
    assert_eq!(bfx["frames"], 10);
    assert_eq!(bfx["glow"], "medium");
    assert_eq!(bfx["parts"]["aura_back"]["layer"], "behind");
    assert_eq!(bfx["parts"]["aura_front"]["layer"], "front");
    assert_eq!(bfx["parts"]["note_part"]["anchor"], "target", "parts in Spec.extra join the aura parts: {}", bfx["parts"]);
    assert!(bfx["act"]["hits"].as_array().is_some_and(|h| h.len() == 1));
}

#[test]
fn run_with_stepped_light_and_the_commands() {
    let dir = draft("runner_cmds");
    let fx = Burst { aura: false, steps: true, fail_at: None };
    assert!(dr::run(&fx, &dir, &[]).unwrap() <= 1);
    let out = dir.join("out");

    assert!(dr::run(&fx, &dir, &args(&["quick"])).unwrap() <= 1);
    assert_eq!(dr::run(&fx, &dir, &args(&["look"])).unwrap(), 0);
    assert!(out.join("look.png").is_file() && out.join("look_1x.png").is_file());
    assert_eq!(dr::run(&fx, &dir, &args(&["look", "1", "4", "99"])).unwrap(), 0);
    assert_eq!(dr::run(&fx, &dir, &args(&["glow"])).unwrap(), 0);
    assert!(out.join("glow_takes.png").is_file());

    assert!(dr::run(&fx, &dir, &args(&["bench"])).unwrap_err().contains("pixelfx id"));
    assert!(dr::run(&fx, &dir, &args(&["nope"])).unwrap_err().contains("unknown command nope"));

    // quick flags what the full run flags on the sheet: a disc cut by the cell edge exits 1
    struct Cut;
    impl Effect for Cut {
        fn spec(&self) -> Spec {
            Spec::new("cut", 16, 16, 4, FPS)
        }
        fn draw(&self, cv: &mut Canvas, _f: usize, _seed: u64, layer: Layer) -> Result<(), String> {
            if layer == Layer::Effect {
                cv.ellipse(1.0, 8.0, 4.0, 4.0, [1.0; 3], 1.0);
            }
            Ok(())
        }
    }
    let quick = dr::run(&Cut, &dir, &args(&["quick"])).unwrap();
    let full = dr::run(&Cut, &dir, &[]).unwrap();
    assert_eq!((quick, full), (1, 1), "quick and the full run both fail an edge cut");
}

#[test]
fn run_reports_draw_errors_and_a_bad_glow() {
    let dir = draft("runner_err");
    let e = dr::run(&Burst { aura: false, steps: false, fail_at: Some(2) }, &dir, &[]).unwrap_err();
    assert!(e.contains("frame 2") && e.contains("boom"), "{e}");

    struct BadGlow;
    impl Effect for BadGlow {
        fn spec(&self) -> Spec {
            let mut sp = Spec::new("bad", 16, 16, 4, FPS);
            sp.glow = "blinding".into();
            sp
        }
        fn draw(&self, cv: &mut Canvas, _f: usize, _seed: u64, _layer: Layer) -> Result<(), String> {
            cv.put(8.0, 8.0, [1.0; 3], 1.0);
            Ok(())
        }
    }
    let e = dr::run(&BadGlow, &dir, &[]).unwrap_err();
    assert!(e.contains("blinding"), "{e}");
}

#[test]
fn measure_and_part_sheets() {
    use beanfx::ndarray::{Array2, Array3};
    let mut col = Array3::<u8>::zeros((8, 8, 4));
    assert!(dr::measure(&col, &Array2::zeros((8, 8))).is_none());
    col[[2, 2, 3]] = 255;
    col[[5, 5, 3]] = 255;
    let mut l = Array2::<f64>::zeros((8, 8));
    l[[3, 3]] = 0.5;
    let (cover, mean) = dr::measure(&col, &l).unwrap();
    assert!((cover - 1.0 / 16.0).abs() < 1e-12 && (mean - 0.5).abs() < 1e-12);

    let dir = common::tmpdir("runner_part");
    let mut cv = Canvas::new(12, 12);
    cv.ellipse(6.0, 6.0, 3.0, 3.0, dr::hex("#ff8040"), 1.0);
    cv.glow(6.0, 6.0, 4.0, 0.4);
    let cels = vec![cv.cel(); 3];
    let ramp: Vec<String> = ["#402010", "#ffa040", "#ffffff"].iter().map(|s| s.to_string()).collect();
    let (entry, bad) = dr::write_part(&dir, "spark_impact", &cels, &ramp, FPS, [6.0, 6.0], true, "target",
                                      beanfx::serde_json::json!({"note": "x"}), "subtle").unwrap();
    assert!(dir.join("sheets/spark_impact.json").is_file());
    assert_eq!(entry["json"], "spark_impact.json");
    assert_eq!(entry["note"], "x");
    assert!(bad.iter().all(|b| b.starts_with("spark_impact: ")), "{bad:?}");
}

#[test]
fn easing_and_span_helpers() {
    assert_eq!(dr::span(5.0, 0.0, 10.0), 0.5);
    assert_eq!(dr::span(-1.0, 0.0, 10.0), 0.0);
    for e in [dr::ease_io, dr::ease_out, dr::ease_in] {
        assert!(e(0.0).abs() < 1e-9 && (e(1.0) - 1.0).abs() < 1e-9);
    }
    assert_eq!(dr::ramp(&["#000000", "#ffffff"]).len(), 2);
}
