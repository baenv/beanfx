//! One call from the Python kit: a JSON job on stdin, a JSON answer on stdout.
//!
//! Job: {"args": {...}, "arrays": {"name": "/tmp/x/name.npy", ...}, "dir": "/tmp/x"}
//! Answer: {"value": ..., "arrays": {"name": "/tmp/x/out_name.npy"}, "print": ["note ..."]} or {"error": "..."} with exit 1.

use crate::npy::{self, Array};
use serde_json::{Map, Value};
use std::collections::BTreeMap;
use std::path::PathBuf;

pub struct Job {
    pub args: Value,
    pub arrays: BTreeMap<String, PathBuf>,
    pub dir: PathBuf,
}

#[derive(Default)]
pub struct Answer {
    pub value: Value,
    pub arrays: BTreeMap<String, Array>,
    /// Lines the Python side prints (notes such as the texture memory one).
    pub print: Vec<String>,
}

impl Answer {
    pub fn of(value: Value) -> Answer {
        Answer { value, ..Default::default() }
    }
}

impl Job {
    pub fn parse(text: &str) -> Result<Job, String> {
        let v: Value = serde_json::from_str(text).map_err(|e| format!("job: {e}"))?;
        let arrays = v
            .get("arrays")
            .and_then(Value::as_object)
            .map(|m| m.iter().filter_map(|(k, p)| p.as_str().map(|p| (k.clone(), PathBuf::from(p)))).collect())
            .unwrap_or_default();
        if let Some(p) = v.get("protocol").and_then(Value::as_u64) {
            if p != crate::PROTOCOL as u64 {
                return Err(format!(
                    "the kit speaks protocol {p}, this beanfx binary speaks {}: rerun setup.sh, or refresh the \
                     draft's kit (setup.sh --draft <name> --refresh-kit)",
                    crate::PROTOCOL
                ));
            }
        }
        let dir = v.get("dir").and_then(Value::as_str).map(PathBuf::from).unwrap_or_else(std::env::temp_dir);
        Ok(Job { args: v.get("args").cloned().unwrap_or(Value::Object(Map::new())), arrays, dir })
    }

    pub fn has(&self, name: &str) -> bool {
        self.arrays.contains_key(name)
    }

    pub fn array(&self, name: &str) -> Result<Array, String> {
        let p = self.arrays.get(name).ok_or_else(|| format!("job: no array {name}"))?;
        npy::read(p)
    }

    pub fn arg(&self, key: &str) -> Option<&Value> {
        self.args.get(key).filter(|v| !v.is_null())
    }

    pub fn str(&self, key: &str) -> Option<&str> {
        self.arg(key).and_then(Value::as_str)
    }

    pub fn f64(&self, key: &str) -> Option<f64> {
        self.arg(key).and_then(Value::as_f64)
    }

    pub fn bool(&self, key: &str) -> bool {
        match self.arg(key) {
            Some(Value::Bool(b)) => *b,
            Some(Value::Number(n)) => n.as_f64().is_some_and(|x| x != 0.0),
            Some(Value::String(s)) => !s.is_empty(),
            Some(Value::Array(a)) => !a.is_empty(),
            Some(Value::Object(o)) => !o.is_empty(),
            _ => false,
        }
    }

    /// Writes the answer's arrays next to the job's and returns the JSON line to print.
    pub fn finish(&self, a: Answer) -> Result<String, String> {
        let mut paths = Map::new();
        for (k, arr) in &a.arrays {
            let p = self.dir.join(format!("out_{k}.npy"));
            npy::write(&p, arr)?;
            paths.insert(k.clone(), Value::String(p.to_string_lossy().into()));
        }
        let mut out = Map::new();
        out.insert("value".into(), a.value);
        out.insert("arrays".into(), Value::Object(paths));
        if !a.print.is_empty() {
            out.insert("print".into(), a.print.into());
        }
        Ok(Value::Object(out).to_string())
    }
}
