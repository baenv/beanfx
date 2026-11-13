//! `beanfx gate` against a fake Jev (a temp python script with the client's API): the ask rule, every fallback to
//! the model, and the knob files. Never calls the real Jev.

use serde_json::Value;
use std::path::{Path, PathBuf};
use std::process::Command;

const BIN: &str = env!("CARGO_BIN_EXE_beanfx");

fn knobs() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../knobs")
}

const WANT: [&str; 17] = [
    "role", "view", "size", "timing", "loop", "shape", "style", "palette", "glow", "clarity", "density", "states",
    "caster", "combo", "placement", "aura", "sound",
];
const APPLIES: [&str; 8] = ["view", "density", "states", "caster", "combo", "placement", "aura", "sound"];

/// The fake client: answers from a table (default 0.0 stated, 1.0 applies), records the request, and trips its
/// breaker after three failures, as jev.py does.
const FAKE_JEV: &str = r#"
import json, os
D = os.environ["FAKE_JEV_DIR"]
ANSWERS = {"stated::size": 0.9, "stated::role": 0.8, "applies::view": 0.2, "stated::glow": 0.5,
           "applies::states": 0.9, "stated::states": 0.1}
def _read(n, d):
    try:
        return int(open(os.path.join(D, n)).read())
    except OSError:
        return d
def breaker_open():
    return _read("fails", 0) >= 3
def breaker_record(error):
    n = 0 if error is None else _read("fails", 0) + 1
    open(os.path.join(D, "fails"), "w").write(str(n))
def api_key():
    return os.environ.get("FAKE_JEV_KEY", "k")
def redact(t):
    return t
def log(record):
    open(os.path.join(D, "log"), "a").write(json.dumps(record) + "\n")
class Client:
    def __init__(self, key):
        pass
    def ask(self, state, questions, timeout=5.0):
        json.dump({"state": state, "questions": questions, "timeout": timeout}, open(os.path.join(D, "seen"), "w"))
        if os.environ.get("FAKE_JEV_FAIL"):
            raise RuntimeError("HTTP 500: boom")
        return {"answers": {k: {"noul": ANSWERS.get(k, 0.0 if k.startswith("stated::") else 1.0)} for k in questions}}
    def close(self):
        pass
"#;

struct Env {
    dir: PathBuf,
}

impl Env {
    fn new(name: &str) -> Env {
        let dir = std::env::temp_dir().join(format!("beanfx-gate-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("jev.py"), FAKE_JEV).unwrap();
        Env { dir }
    }

    fn run(&self, args: &[&str], vars: &[(&str, &str)]) -> (i32, Value) {
        let mut cmd = Command::new(BIN);
        cmd.arg("gate")
            .args(args)
            .env_remove("BEANFX_GATE")
            .env("BEANFX_KNOBS", knobs())
            .env("BEANFX_JEV_PY", self.dir.join("jev.py"))
            .env("FAKE_JEV_DIR", &self.dir);
        for (k, v) in vars {
            cmd.env(k, v);
        }
        let out = cmd.output().unwrap();
        let json = serde_json::from_slice(&out.stdout).unwrap_or(Value::Null);
        (out.status.code().unwrap(), json)
    }

    fn seen(&self) -> Value {
        serde_json::from_str(&std::fs::read_to_string(self.dir.join("seen")).unwrap()).unwrap()
    }
}

fn have_python() -> bool {
    Command::new("python3").arg("--version").output().is_ok()
}

fn frontmatter(text: &str, key: &str) -> Option<String> {
    let mut lines = text.lines();
    lines.next();
    for l in lines {
        if l == "---" {
            break;
        }
        if let Some((k, v)) = l.split_once(':') {
            if k.trim() == key {
                return Some(v.trim().to_string());
            }
        }
    }
    None
}

#[test]
fn knob_files_are_complete() {
    let mut names = vec![];
    let mut files: Vec<_> = std::fs::read_dir(knobs()).unwrap().map(|e| e.unwrap().path()).collect();
    files.sort();
    let mut by = std::collections::HashMap::new();
    for p in files.iter().filter(|p| p.extension().is_some_and(|x| x == "md")) {
        let text = std::fs::read_to_string(p).unwrap();
        let name = frontmatter(&text, "name").unwrap();
        let order: i64 = frontmatter(&text, "order").unwrap().parse().unwrap();
        let stated = frontmatter(&text, "stated").unwrap();
        assert_eq!(p.file_stem().unwrap().to_str().unwrap(), name, "{name}: file name");
        assert!((stated.starts_with("Does") || stated.starts_with("Is")) && stated.contains('?'), "{name}: stated is a question");
        if let Some(a) = frontmatter(&text, "applies") {
            assert!(a.ends_with('?'), "{name}: applies is a question");
        }
        assert!(text.contains("**Fixed when**") || text.contains("1. "), "{name}: body says when it is fixed");
        assert!(text.contains("**Ask") || text.contains("2. Ask"), "{name}: body has the question");
        assert!(text.contains("`preview`") && text.matches("```").count() >= 2, "{name}: body shows an ASCII preview");
        names.push((order, name.clone()));
        by.insert(name, (text, stated));
    }
    names.sort();
    let names: Vec<_> = names.into_iter().map(|(_, n)| n).collect();
    assert_eq!(names, WANT);
    let mut applies: Vec<_> = by.iter().filter(|(_, (t, _))| frontmatter(t, "applies").is_some()).map(|(n, _)| n.as_str()).collect();
    applies.sort();
    let mut want = APPLIES.to_vec();
    want.sort();
    assert_eq!(applies, want, "applies set");

    // Jev reads only the stated line, so an exclusion in a knob's "Fixed when" must be in that line too
    for (n, words) in [("palette", "subject"), ("size", "256"), ("timing", "Fast"), ("glow", "Sparkling"), ("shape", "subject name"),
        ("role", "two readings"), ("sound", "With sound")]
    {
        let stated = &by[n].1;
        assert!(stated.contains(words) && stated.contains("not count"), "{n}: stated carries its exclusion");
    }

    // every role in role.md has a row in the size table
    let role = &by["role"].1;
    let mut roles: Vec<&str> = role.split('(').nth(1).unwrap().split(')').next().unwrap().split(", ").collect();
    let mut rows: Vec<&str> = by["size"].0.lines().filter(|l| l.starts_with("| ") && !l.starts_with("| role")).map(|l| l.split('|').nth(1).unwrap().trim()).collect();
    roles.sort();
    rows.sort();
    assert_eq!(roles, rows, "size rows match the roles");
}

#[test]
fn usage_exits_2() {
    let out = Command::new(BIN).arg("gate").output().unwrap();
    assert_eq!(out.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&out.stdout).contains("beanfx gate"));
}

#[test]
fn model_fallbacks() {
    let e = Env::new("model");
    let (code, out) = e.run(&["x"], &[("BEANFX_GATE", "model")]);
    assert_eq!(code, 0);
    assert_eq!(out["source"], "model");
    assert_eq!(out["knobs"].as_array().unwrap().len(), 17);
    let missing = e.dir.join("nope.py");
    let (code, out) = e.run(&["x"], &[("BEANFX_JEV_PY", missing.to_str().unwrap())]);
    assert_eq!((code, out["reason"].as_str()), (0, Some("no jev.py")));
    assert!(out.get("hint").is_none());
}

#[test]
fn ask_rule_through_fake_jev() {
    if !have_python() {
        return;
    }
    let e = Env::new("ask");
    let (code, out) = e.run(&["a fireball", "--context", "a blue comet sketch"], &[]);
    assert_eq!(code, 0);
    assert_eq!(out["source"], "jev", "{out}");
    let ask: Vec<&str> = out["ask"].as_array().unwrap().iter().map(|v| v.as_str().unwrap()).collect();
    assert!(!ask.contains(&"size") && !ask.contains(&"role"), "stated knobs are skipped");
    assert!(!ask.contains(&"view"), "a knob that does not apply is skipped");
    assert!(!ask.contains(&"glow"), "stated at exactly 0.5 counts as stated");
    assert!(ask.contains(&"states") && ask.contains(&"timing") && ask.contains(&"shape"), "open knobs that apply are asked");
    let order: Vec<&str> = WANT.iter().copied().filter(|n| ask.contains(n)).collect();
    assert_eq!(ask, order, "ask keeps the knob order");
    assert_eq!(out["knobs"]["size"]["stated"], 0.9);
    assert_eq!(out["knobs"]["states"]["ask"], true);
    let seen = e.seen();
    let q = seen["questions"].as_object().unwrap();
    assert!(q.len() == 17 + 8 && q.values().all(|v| v["type"] == "noul"), "one call, 25 nouls");
    assert_eq!(seen["state"]["reference_image"], "a blue comet sketch");
    assert!(seen["state"]["request"].as_str().unwrap().contains("fireball"));
    assert_eq!(seen["timeout"], 8.0);
    assert!(std::fs::read_to_string(e.dir.join("log")).unwrap().contains("beanfx-gate"));
}

#[test]
fn jev_failures_fall_back_and_trip_the_breaker() {
    if !have_python() {
        return;
    }
    let e = Env::new("fail");
    let (code, out) = e.run(&["x"], &[("FAKE_JEV_KEY", "")]);
    assert_eq!((code, out["reason"].as_str()), (0, Some("no jev api key")));
    for _ in 0..3 {
        let (code, out) = e.run(&["x"], &[("FAKE_JEV_FAIL", "1")]);
        assert_eq!(code, 0);
        assert_eq!(out["reason"], "jev failed: HTTP 500", "{out}");
    }
    let (code, out) = e.run(&["x"], &[]);
    assert_eq!((code, out["reason"].as_str()), (0, Some("jev breaker open")));
    let (_, out) = e.run(&["x"], &[("BEANFX_JEV_PY", e.dir.join("broken.py").to_str().unwrap())]);
    assert_eq!(out["source"], "model");
}
