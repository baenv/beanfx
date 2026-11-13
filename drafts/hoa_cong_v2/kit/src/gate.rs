//! The /beanfx brief gate: which knobs to ask the owner about before drawing.
//!
//! Each knob is a file in knobs/ whose frontmatter holds two yes or no questions for Jev, an optional prompt
//! classifier client (~/.claude/hooks/jev.py, or BEANFX_JEV_PY): `stated` (true when the request already fixes the
//! knob) and, for some knobs, `applies` (true when the knob matters for this effect). One Jev call answers all of
//! them; a knob is asked when it applies and is not stated. Jev is Python, so the binary runs it with `python3`
//! through a short embedded script; without it the source is "model" and the model reads the knob files.

use serde_json::{json, Map, Value};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::time::Duration;

const ASK_BELOW: f64 = 0.5;
const APPLIES_AT: f64 = 0.5;
const BUDGET_S: f64 = 8.0;
const PROCESS_S: u64 = 15;

const USAGE: &str = "The /beanfx brief gate: which knobs to ask the owner about before drawing.

    beanfx gate \"<the owner's prompt>\" [--context \"<what a reference image shows>\"]
    beanfx gate - < prompt.txt

Prints one JSON object and exits 0. Source \"jev\": `ask` (knob names in order) and `skip`. Source \"model\": Jev is
not available (no jev.py, no key, breaker open, an error); the model reads each knob file's \"Fixed when\" and
decides. BEANFX_GATE=model turns Jev off. BEANFX_KNOBS names the knobs folder. Exit 2 only on bad usage.";

/// Runs inside python3: asks Jev and prints one JSON line, {"fallback": reason} or {"answers", "ms"}.
const JEV_SCRIPT: &str = r#"
import json, os, sys, time
from pathlib import Path
job = json.load(sys.stdin)
def out(o):
    print(json.dumps(o))
    sys.exit(0)
path = Path(os.environ.get("BEANFX_JEV_PY", "~/.claude/hooks/jev.py")).expanduser()
try:
    sys.path.insert(0, str(path.parent))
    sys.dont_write_bytecode = True
    import jev
except Exception as e:
    out({"fallback": "jev.py does not import: %s" % type(e).__name__})
if jev.breaker_open():
    out({"fallback": "jev breaker open"})
key = jev.api_key()
if not key:
    out({"fallback": "no jev api key"})
prompt, context = job["prompt"], job["context"]
state = {"request": jev.redact(prompt)[:6000], "task": "The request asks for a pixel-art game effect (a sprite sheet)."}
if context:
    state["reference_image"] = jev.redact(context)[:1000]
client, t0 = jev.Client(key), time.monotonic()
record = {"ts": int(time.time()), "hook": "beanfx-gate", "prompt": jev.redact(prompt)[:120]}
try:
    res = client.ask(state, job["questions"], timeout=job["budget"])
    answers = {k: float(v["noul"]) for k, v in res["answers"].items()}
    ask = []
    for k in job["knobs"]:
        st = answers["stated::" + k["name"]]
        ap = answers["applies::" + k["name"]] if k["applies"] else 1.0
        if ap >= job["applies_at"] and st < job["ask_below"]:
            ask.append(k["name"])
except Exception as e:
    record["error"] = str(e)[:200] or type(e).__name__
    jev.breaker_record(record["error"])
    jev.log(record)
    out({"fallback": "jev failed: %s" % record["error"].split(":", 1)[0]})
finally:
    client.close()
jev.breaker_record(None)
record["ms"] = int((time.monotonic() - t0) * 1000)
record["ask"] = ask
jev.log(record)
out({"answers": answers, "ms": record["ms"]})
"#;

struct Knob {
    name: String,
    order: i64,
    stated: String,
    applies: Option<String>,
    file: String,
}

/// Each knob file's one-line frontmatter fields, sorted by order.
fn load_knobs(folder: &Path) -> Vec<Knob> {
    let mut paths: Vec<PathBuf> = match std::fs::read_dir(folder) {
        Ok(rd) => rd.filter_map(|e| e.ok()).map(|e| e.path()).filter(|p| p.extension().is_some_and(|x| x == "md")).collect(),
        Err(_) => return vec![],
    };
    paths.sort();
    let mut knobs = vec![];
    for path in paths {
        let Ok(text) = std::fs::read_to_string(&path) else { continue };
        let mut lines = text.split('\n');
        if lines.next().map(str::trim) != Some("---") {
            continue;
        }
        let mut meta = Map::new();
        for line in lines {
            if line.trim() == "---" {
                break;
            }
            if let Some((k, v)) = line.split_once(':') {
                meta.insert(k.trim().to_string(), Value::String(v.trim().to_string()));
            }
        }
        let get = |k: &str| meta.get(k).and_then(Value::as_str).filter(|s| !s.is_empty()).map(String::from);
        let (Some(name), Some(stated)) = (get("name"), get("stated")) else { continue };
        let file = std::fs::canonicalize(&path).unwrap_or(path.clone());
        knobs.push(Knob {
            name,
            order: get("order").and_then(|o| o.parse().ok()).unwrap_or(99),
            stated,
            applies: get("applies"),
            file: file.to_string_lossy().into_owned(),
        });
    }
    knobs.sort_by_key(|k| k.order);
    knobs
}

/// The knobs folder: BEANFX_KNOBS, else `skill.txt` beside the installed binary (setup.sh writes the skill's path
/// to <project>/.beanfx/skill.txt), else the folder next to the kit this binary was built from.
fn knobs_dir() -> PathBuf {
    if let Some(d) = std::env::var_os("BEANFX_KNOBS") {
        return PathBuf::from(d);
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(stamp) = exe.parent().and_then(Path::parent).map(|p| p.join("skill.txt")) {
            if let Ok(s) = std::fs::read_to_string(stamp) {
                let d = Path::new(s.trim()).join("knobs");
                if d.is_dir() {
                    return d;
                }
            }
        }
    }
    Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join("knobs")
}

/// Python's `json.dumps(v, indent=1)`: serde's pretty output with one space per level.
fn dumps(v: &Value) -> String {
    let pretty = serde_json::to_string_pretty(v).expect("json");
    pretty
        .lines()
        .map(|l| {
            let n = l.len() - l.trim_start_matches(' ').len();
            format!("{}{}", " ".repeat(n / 2), &l[n..])
        })
        .collect::<Vec<_>>()
        .join("\n")
}

fn fallback(knobs: &[Knob], reason: &str) -> i32 {
    let files: Vec<&str> = knobs.iter().map(|k| k.file.as_str()).collect();
    let out = json!({"source": "model", "reason": reason, "knobs": files,
        "note": "Read each knob file's 'Fixed when' and decide which to ask."});
    println!("{}", dumps(&out));
    0
}

fn round3(x: f64) -> f64 {
    (x * 1000.0).round() / 1000.0
}

/// Runs the embedded script; Ok(answers, ms) or Err(fallback reason).
fn ask_jev(jev: &Path, knobs: &[Knob], prompt: &str, context: &str) -> Result<(Map<String, Value>, u64), String> {
    let mut questions = Map::new();
    for k in knobs {
        questions.insert(format!("stated::{}", k.name), json!({"type": "noul", "instructions": k.stated}));
        if let Some(a) = &k.applies {
            questions.insert(format!("applies::{}", k.name), json!({"type": "noul", "instructions": a}));
        }
    }
    let list: Vec<Value> = knobs.iter().map(|k| json!({"name": k.name, "applies": k.applies.is_some()})).collect();
    let job = json!({"prompt": prompt, "context": context, "questions": questions, "knobs": list,
        "budget": BUDGET_S, "ask_below": ASK_BELOW, "applies_at": APPLIES_AT});
    let mut child = Command::new("python3")
        .arg("-c")
        .arg(JEV_SCRIPT)
        // `python3 -c` puts the working folder first on sys.path; run in jev.py's folder so a json.py or time.py in
        // the project cannot shadow the standard library
        .current_dir(jev.parent().unwrap_or(Path::new("/")))
        .env("BEANFX_JEV_PY", jev)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| "python3 not found".to_string())?;
    let mut stdin = child.stdin.take().expect("stdin");
    let mut stdout = child.stdout.take().expect("stdout");
    let body = job.to_string();
    std::thread::spawn(move || {
        let _ = stdin.write_all(body.as_bytes());
    });
    let (tx, rx) = mpsc::channel();
    std::thread::spawn(move || {
        let mut s = String::new();
        let _ = stdout.read_to_string(&mut s);
        let _ = tx.send(s);
    });
    let Ok(text) = rx.recv_timeout(Duration::from_secs(PROCESS_S)) else {
        let _ = child.kill();
        return Err("jev failed: timeout".into());
    };
    let _ = child.wait();
    let v: Value = serde_json::from_str(text.lines().last().unwrap_or("")).map_err(|_| "jev failed: bad output".to_string())?;
    if let Some(r) = v.get("fallback").and_then(Value::as_str) {
        return Err(r.to_string());
    }
    match (v.get("answers").and_then(Value::as_object), v.get("ms").and_then(Value::as_u64)) {
        (Some(a), Some(ms)) => Ok((a.clone(), ms)),
        _ => Err("jev failed: bad output".into()),
    }
}

/// `beanfx gate`: returns the exit code.
pub fn run(args: &[String]) -> i32 {
    let mut args: Vec<String> = args.to_vec();
    let mut context = String::new();
    if let Some(i) = args.iter().position(|a| a == "--context") {
        context = args.get(i + 1).cloned().unwrap_or_default();
        args.drain(i..(i + 2).min(args.len()));
    }
    if args.is_empty() {
        println!("{USAGE}");
        return 2;
    }
    let prompt = if args[0] == "-" {
        let mut s = String::new();
        let _ = std::io::stdin().read_to_string(&mut s);
        s
    } else {
        args.join(" ")
    };
    let knobs = load_knobs(&knobs_dir());
    if knobs.is_empty() {
        println!("{}", json!({"source": "model", "reason": "no knob files"}));
        return 0;
    }
    if std::env::var("BEANFX_GATE").as_deref() == Ok("model") {
        return fallback(&knobs, "BEANFX_GATE=model");
    }
    let jev = std::env::var("BEANFX_JEV_PY").unwrap_or_else(|_| "~/.claude/hooks/jev.py".into());
    let jev = match jev.strip_prefix("~/") {
        Some(rest) => PathBuf::from(std::env::var_os("HOME").unwrap_or_default()).join(rest),
        None => PathBuf::from(jev),
    };
    if !jev.is_file() {
        return fallback(&knobs, "no jev.py");
    }
    let (answers, ms) = match ask_jev(&jev, &knobs, &prompt, &context) {
        Ok(r) => r,
        Err(reason) => return fallback(&knobs, &reason),
    };
    let num = |k: &str| answers.get(k).and_then(Value::as_f64);
    let mut result = Map::new();
    let (mut ask, mut skip) = (vec![], vec![]);
    for k in &knobs {
        let Some(stated) = num(&format!("stated::{}", k.name)) else { return fallback(&knobs, "jev failed: KeyError") };
        let applies = match &k.applies {
            Some(_) => match num(&format!("applies::{}", k.name)) {
                Some(a) => a,
                None => return fallback(&knobs, "jev failed: KeyError"),
            },
            None => 1.0,
        };
        let asked = applies >= APPLIES_AT && stated < ASK_BELOW;
        (if asked { &mut ask } else { &mut skip }).push(k.name.clone());
        result.insert(k.name.clone(), json!({"stated": round3(stated), "applies": round3(applies), "ask": asked, "file": k.file}));
    }
    println!("{}", dumps(&json!({"source": "jev", "ms": ms, "ask": ask, "skip": skip, "knobs": result})));
    0
}
