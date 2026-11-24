//! Integration tests for `beanfx check` and `beanfx sfx` CLI subcommands.

mod common;

use beanfx::ex::{self, Hit, Write as ExWrite};
use beanfx::serde_json::Value;
use ndarray::Array3;
use std::path::Path;
use std::process::{Command, Output};

const BIN: &str = env!("CARGO_BIN_EXE_beanfx");
const FPS: f64 = 24.0;

fn run(args: &[&str]) -> Output {
    Command::new(BIN).args(args).output().expect("spawn beanfx")
}

/// A clean 32x32 one-shot effect: centered disc that swells then fades to a 1px wisp on the last frame.
fn clean_frames(n: usize) -> (Vec<Array3<u8>>, Vec<Array3<f64>>) {
    let (h, w) = (32, 32);
    let mut frames = Vec::with_capacity(n);
    let mut lights = Vec::with_capacity(n);
    for f in 0..n {
        let mut im = Array3::<u8>::zeros((h, w, 4));
        let mut lt = Array3::<f64>::zeros((h, w, 3));
        if f + 1 == n {
            im[[16, 16, 0]] = 255;
            im[[16, 16, 1]] = 180;
            im[[16, 16, 2]] = 80;
            im[[16, 16, 3]] = 255;
        } else {
            let r = 4.0 + 7.0 * ((f as f64) / (n as f64 - 1.0) * std::f64::consts::PI).sin();
            for y in 4..28 {
                for x in 4..28 {
                    let dx = x as f64 - 15.5;
                    let dy = y as f64 - 15.5;
                    if dx * dx + dy * dy <= r * r {
                        im[[y, x, 0]] = 255;
                        im[[y, x, 1]] = 160;
                        im[[y, x, 2]] = 60;
                        im[[y, x, 3]] = 255;
                        lt[[y, x, 0]] = 0.5;
                        lt[[y, x, 1]] = 0.3;
                        lt[[y, x, 2]] = 0.1;
                    }
                }
            }
        }
        frames.push(im);
        lights.push(lt);
    }
    (frames, lights)
}

fn write_clean_sheet(dir: &Path, name: &str, max_edge: Option<i64>) -> String {
    let (frames, lights) = clean_frames(8);
    ex::write(
        dir,
        name,
        &frames,
        FPS,
        [16.0, 16.0],
        false,
        ExWrite {
            color: Some((&frames).into()),
            light: Some((&lights).into()),
            states: vec![("strike".into(), [0, 3]), ("fade".into(), [4, 7])],
            hits: vec![ex::hit(2, FPS, Hit { weight: Some("heavy".into()), ..Default::default() })],
            max_edge,
            ..Default::default()
        },
    )
    .unwrap();
    dir.join(format!("{name}.json")).to_string_lossy().into_owned()
}

#[test]
fn check_passes_clean_single_and_paged_sheets() {
    let dir = common::tmpdir("cli_check_clean");

    // Single sheet (human + --json)
    let single = write_clean_sheet(&dir.join("single"), "spark", None);
    let out = run(&["check", &single]);
    assert_eq!(out.status.code(), Some(0), "human check failed: {}", String::from_utf8_lossy(&out.stderr));
    let txt = String::from_utf8_lossy(&out.stdout);
    assert!(txt.contains("clean"), "expected clean summary, got: {txt}");

    let out = run(&["check", &single, "--json", "--max-colours", "16", "--max-mb", "10", "--no-trim"]);
    assert_eq!(out.status.code(), Some(0));
    let js: Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(js["ok"], true, "json check: {js}");
    assert_eq!(js["frames"], 8);
    assert!(js["framing"]["box"].is_array());

    // Paged sheet (max_edge forces 2 pages of 4 frames each)
    let paged = write_clean_sheet(&dir.join("paged"), "big", Some(64));
    let out = run(&["check", &paged, "--json"]);
    assert_eq!(out.status.code(), Some(0), "paged check failed: {}", String::from_utf8_lossy(&out.stderr));
    let pjs: Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(pjs["ok"], true, "paged json check: {pjs}");
    assert_eq!(pjs["frames"], 8);
}

#[test]
fn check_exits_1_when_sheet_has_craft_problems() {
    let dir = common::tmpdir("cli_check_fail");
    // Frame 0 touches the top-left edge (0, 0) and frame 1 is empty -> both flagged by ex::check
    let mut f0 = Array3::<u8>::zeros((16, 16, 4));
    f0[[0, 0, 0]] = 255;
    f0[[0, 0, 3]] = 255;
    let f1 = Array3::<u8>::zeros((16, 16, 4));
    ex::write(&dir, "bad", &vec![f0, f1], FPS, [8.0, 8.0], false, ExWrite::default()).unwrap();
    let jp = dir.join("bad.json");
    let jp_s = jp.to_string_lossy();

    let out = run(&["check", &jp_s, "--json"]);
    assert_eq!(out.status.code(), Some(1), "expected exit 1 on craft problems");
    let js: Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(js["ok"], false);
    assert!(!js["problems"].as_array().unwrap().is_empty());

    // Human output also exits 1 and prints problems
    let out = run(&["check", &jp_s]);
    assert_eq!(out.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&out.stdout).contains("problems"));
}

#[test]
fn sfx_synthesises_wavs_updates_json_and_passes_check() {
    let dir = common::tmpdir("cli_sfx");
    let jp = write_clean_sheet(&dir, "slash", None);

    // Synthesise with --json into the same folder
    let out = run(&["sfx", &jp, "--voice", "retro", "--element", "metal", "--seed", "5", "--sounds", "none", "--json"]);
    assert_eq!(out.status.code(), Some(0), "sfx failed: {}", String::from_utf8_lossy(&out.stderr));
    let rep: Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(rep["ok"], true, "sfx rep: {rep}");
    assert_eq!(rep["sound"]["track"], "slash_sound.wav");
    assert!(dir.join("slash_sound.wav").is_file());

    // `beanfx check` now also runs `sfx::check` automatically because meta.beanfx.sound is present
    let chk = run(&["check", &jp, "--json"]);
    assert_eq!(chk.status.code(), Some(0), "check with sound failed: {}", String::from_utf8_lossy(&chk.stdout));

    // Human output mode into a separate --out directory
    let out2 = dir.join("alt_audio");
    let res = run(&["sfx", &jp, "--out", out2.to_str().unwrap(), "--voice", "soft", "--element", "ice", "--sounds", "none"]);
    assert_eq!(res.status.code(), Some(0));
    assert!(String::from_utf8_lossy(&res.stdout).contains("clean"));
    assert!(out2.join("slash_sound.wav").is_file());

    // --out elsewhere still updates the sheet's own JSON, with the sound paths pointing into that folder
    let js: Value = serde_json::from_str(&std::fs::read_to_string(&jp).unwrap()).unwrap();
    let snd = &js["meta"]["beanfx"]["sound"];
    assert_eq!(snd["track"], "alt_audio/slash_sound.wav", "sheet json sound: {snd}");
    assert_eq!(snd["voice"], "soft");
    assert!(snd["cues"].as_array().unwrap().iter().all(|c| c["file"].as_str().unwrap().starts_with("alt_audio/")));
    let chk = run(&["check", &jp, "--json"]);
    assert_eq!(chk.status.code(), Some(0), "check after --out failed: {}", String::from_utf8_lossy(&chk.stdout));

    // A folder outside the sheet's folder gets absolute paths
    let far = common::tmpdir("cli_sfx_far");
    let res = run(&["sfx", &jp, "--out", far.to_str().unwrap(), "--sounds", "none"]);
    assert_eq!(res.status.code(), Some(0), "sfx far failed: {}", String::from_utf8_lossy(&res.stdout));
    let js: Value = serde_json::from_str(&std::fs::read_to_string(&jp).unwrap()).unwrap();
    let track = js["meta"]["beanfx"]["sound"]["track"].as_str().unwrap().to_string();
    assert!(Path::new(&track).is_absolute() && Path::new(&track).is_file(), "far track: {track}");
    assert_eq!(run(&["check", &jp]).status.code(), Some(0));
}

#[test]
fn help_and_usage_errors_return_expected_codes() {
    assert_eq!(run(&["--help"]).status.code(), Some(0));
    assert_eq!(run(&["check", "--help"]).status.code(), Some(0));
    assert_eq!(run(&["sfx", "--help"]).status.code(), Some(0));

    assert_eq!(run(&["check"]).status.code(), Some(2));
    assert_eq!(run(&["check", "--bogus"]).status.code(), Some(2));
    assert_eq!(run(&["check", "/nonexistent/sheet.json"]).status.code(), Some(2));
    assert_eq!(run(&["check", "--max-colours", "abc"]).status.code(), Some(2));

    assert_eq!(run(&["sfx"]).status.code(), Some(2));
    assert_eq!(run(&["sfx", "--bogus"]).status.code(), Some(2));
    assert_eq!(run(&["sfx", "/nonexistent/sheet.json"]).status.code(), Some(2));
    assert_eq!(run(&["sfx", "--seed", "abc"]).status.code(), Some(2));
}
