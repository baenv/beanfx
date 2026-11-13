//! The preview page: the skill's tools/preview.html with one result's JSON and sheets embedded as data URLs.

use super::py;
use crate::job::{Answer, Job};
use serde_json::{Map, Value};
use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

/// The skill folder: BEANFX_SKILL, else the path in kit/skill.txt, else the folder above the kit; None when none holds
/// tools/preview.html.
pub fn skill_dir(kit_dir: &Path) -> Option<PathBuf> {
    let mut tries = vec![];
    if let Ok(e) = std::env::var("BEANFX_SKILL") {
        if !e.is_empty() {
            tries.push(PathBuf::from(e));
        }
    }
    if let Ok(t) = fs::read_to_string(kit_dir.join("skill.txt")) {
        tries.push(PathBuf::from(t.trim()));
    }
    if let Some(p) = kit_dir.parent() {
        tries.push(p.to_path_buf());
    }
    tries.into_iter().find(|t| t.join("tools").join("preview.html").exists())
}

fn base64(b: &[u8]) -> String {
    const T: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut o = String::with_capacity(b.len() / 3 * 4 + 4);
    for c in b.chunks(3) {
        let n = (c[0] as u32) << 16 | (*c.get(1).unwrap_or(&0) as u32) << 8 | *c.get(2).unwrap_or(&0) as u32;
        o.push(T[(n >> 18) as usize & 63] as char);
        o.push(T[(n >> 12) as usize & 63] as char);
        o.push(if c.len() > 1 { T[(n >> 6) as usize & 63] as char } else { '=' });
        o.push(if c.len() > 2 { T[n as usize & 63] as char } else { '=' });
    }
    o
}

fn read_json(p: &Path) -> Result<Value, String> {
    let t = fs::read_to_string(p).map_err(|e| format!("{}: {e}", p.display()))?;
    serde_json::from_str(&t).map_err(|e| format!("{}: {e}", p.display()))
}

/// Files keyed by path, in insertion order.
#[derive(Default)]
struct Files(Vec<(PathBuf, String)>);

impl Files {
    fn set(&mut self, k: PathBuf, v: String) {
        match self.0.iter_mut().find(|(p, _)| *p == k) {
            Some(e) => e.1 = v,
            None => self.0.push((k, v)),
        }
    }
}

fn text<'a>(v: &'a Value, k: &str) -> Option<&'a str> {
    v.get(k).and_then(Value::as_str).filter(|s| !s.is_empty())
}

pub fn page(j: &Job) -> Result<Answer, String> {
    let kit_dir = PathBuf::from(j.str("kit_dir").ok_or("page: no kit_dir")?);
    let json_path = fs::canonicalize(j.str("json_path").ok_or("page: no json_path")?).map_err(|e| e.to_string())?;
    let mut print = vec![];
    let template = match j.str("template") {
        Some(t) => Some(PathBuf::from(t)),
        None => skill_dir(&kit_dir).map(|s| s.join("tools").join("preview.html")),
    };
    let template = match template.filter(|t| t.exists()) {
        Some(t) => t,
        None => {
            print.push("note: no tools/preview.html found for the preview page; set BEANFX_SKILL or rerun setup.sh --draft".to_string());
            return Ok(Answer { value: Value::Null, print, ..Default::default() });
        }
    };
    let parts: Vec<_> = json_path.components().collect();
    let i = parts.iter().rposition(|c| c.as_os_str() == "out").ok_or_else(|| format!("{} is not under a draft's out/", json_path.display()))?;
    let draft_dir: PathBuf = parts[..i].iter().collect();
    let drafts = draft_dir.parent().ok_or("page: draft folder has no parent")?.to_path_buf();
    let project = match j.str("project") {
        Some(p) => PathBuf::from(p),
        None => drafts.parent().map(Path::to_path_buf).unwrap_or_default(),
    };
    let vpath = |p: &Path| -> Result<String, String> {
        let r = fs::canonicalize(p).map_err(|e| format!("{}: {e}", p.display()))?;
        let rel = r.strip_prefix(&drafts).map_err(|_| format!("'{}' is not in the subpath of '{}'", r.display(), drafts.display()))?;
        let parts: Vec<String> = rel.components().map(|c| c.as_os_str().to_string_lossy().into_owned()).collect();
        Ok(format!("drafts/{}", parts.join("/")))
    };

    let js = read_json(&json_path)?;
    let bfx = js.pointer("/meta/beanfx").ok_or("page: no meta.beanfx")?;
    let mut files = Files::default();
    let dir_of = |p: &Path| p.parent().map(Path::to_path_buf).unwrap_or_default();

    let sheet_files = |files: &mut Files, jp: &Path, b: &Value, image: &str| -> Result<(), String> {
        files.set(jp.to_path_buf(), vpath(jp)?);
        let listed: Vec<Value> = match b.get("pages").and_then(Value::as_array).filter(|a| !a.is_empty()) {
            Some(a) => a.clone(),
            None => {
                let mut m = Map::new();
                m.insert("image".into(), Value::String(text(b, "sheet").unwrap_or(image).to_string()));
                for k in ["color", "light"] {
                    m.insert(k.into(), b.get(k).cloned().unwrap_or(Value::Null));
                }
                vec![Value::Object(m)]
            }
        };
        for pg in &listed {
            for k in ["image", "color", "light", "json"] {
                if let Some(f) = text(pg, k) {
                    let p = dir_of(jp).join(f);
                    if p.exists() {
                        files.set(p.clone(), vpath(&p)?);
                    }
                }
            }
        }
        Ok(())
    };
    sheet_files(&mut files, &json_path, bfx, js.pointer("/meta/image").and_then(Value::as_str).unwrap_or(""))?;

    let sound = bfx.get("sound").cloned().unwrap_or(Value::Null);
    let mut snd: Vec<String> = vec![];
    if let Some(t) = text(&sound, "track") {
        snd.push(t.to_string());
    }
    for c in sound.get("cues").and_then(Value::as_array).into_iter().flatten() {
        if let Some(f) = text(c, "file") {
            snd.push(f.to_string());
        }
    }
    let mut seen = BTreeSet::new();
    for f in snd {
        let p = dir_of(&json_path).join(&f);
        if seen.insert(f) && p.exists() {
            files.set(p.clone(), vpath(&p)?);
        }
    }
    for part in bfx.get("parts").and_then(Value::as_object).into_iter().flat_map(|m| m.values()) {
        if let Some(pj) = text(part, "json") {
            let jp = dir_of(&json_path).join(pj);
            if jp.exists() {
                let pjs = read_json(&jp)?;
                let b = pjs.pointer("/meta/beanfx").ok_or("page: part has no meta.beanfx")?;
                sheet_files(&mut files, &jp, b, pjs.pointer("/meta/image").and_then(Value::as_str).unwrap_or(""))?;
            }
        }
    }
    let caster = bfx.get("caster").cloned().unwrap_or(Value::Null);
    if let Some(rig) = text(&caster, "rig") {
        let mut rdir = project.join("casters").join(rig);
        let bundled = skill_dir(&kit_dir);
        if !rdir.join("rig.json").exists() {
            if let Some(b) = &bundled {
                rdir = b.join("casters").join(rig);
            }
        }
        if rdir.join("rig.json").exists() {
            let spec = read_json(&rdir.join("rig.json"))?;
            let mut used: Vec<String> = vec![];
            for s in caster.get("chain").and_then(Value::as_array).into_iter().flatten() {
                if let Some(a) = s.get("anim").and_then(Value::as_str) {
                    used.push(a.to_string());
                }
            }
            if let Some(a) = text(&caster, "anim") {
                used.push(a.to_string());
            }
            let anims = spec.get("anims").and_then(Value::as_object);
            for a in ["idle", "run"] {
                if anims.map(|m| m.contains_key(a)).unwrap_or(false) {
                    used.push(a.to_string());
                }
            }
            files.set(rdir.join("rig.json"), format!("casters/{rig}/rig.json"));
            let mut seen = BTreeSet::new();
            for an in used {
                if !seen.insert(an.clone()) {
                    continue;
                }
                let a = anims.ok_or("KeyError: 'anims'")?.get(&an).cloned().unwrap_or(Value::Object(Map::new()));
                let mut sheets: Vec<String> = a.get("sheets").and_then(Value::as_object).into_iter().flat_map(|m| m.values())
                    .filter_map(|v| v.as_str().map(String::from)).collect();
                if let Some(s) = text(&a, "sheet") {
                    sheets.push(s.to_string());
                }
                for sheet in sheets {
                    if rdir.join(&sheet).exists() {
                        files.set(rdir.join(&sheet), format!("casters/{rig}/{sheet}"));
                    }
                }
            }
        } else {
            print.push(format!("note: casters/{rig}/rig.json not found; the preview page shows the effect alone"));
        }
    }

    let url = |p: &Path| -> Result<String, String> {
        let kind = match p.extension().and_then(|e| e.to_str()) {
            Some("json") => "application/json",
            Some("wav") => "audio/wav",
            _ => "image/png",
        };
        let b = fs::read(p).map_err(|e| format!("{}: {e}", p.display()))?;
        Ok(format!("data:{kind};base64,{}", base64(&b)))
    };
    let mut embedded = Map::new();
    for (k, v) in &files.0 {
        embedded.insert(v.clone(), Value::String(url(k)?));
    }
    let stem = json_path.file_stem().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default();
    let draft_name = draft_dir.file_name().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default();
    let mut embed = Map::new();
    embed.insert("label".into(), Value::String(format!("{draft_name}/{stem}")));
    embed.insert("select".into(), Value::String(format!("fx:{}", vpath(&json_path)?)));
    embed.insert("files".into(), Value::Object(embedded));
    let tag = format!("<script>window.BEANFX_EMBED = {};</script>\n", py::dumps(&Value::Object(embed), None));
    let html = fs::read_to_string(&template).map_err(|e| format!("{}: {e}", template.display()))?;
    let at = html.find("<script type=\"module\">").ok_or("substring not found")?;
    let out = j.str("out").map(PathBuf::from).unwrap_or_else(|| draft_dir.join("out"));
    fs::create_dir_all(&out).map_err(|e| e.to_string())?;
    let dst = out.join(format!("{stem}.html"));
    fs::write(&dst, format!("{}{}{}", &html[..at], tag, &html[at..])).map_err(|e| e.to_string())?;
    Ok(Answer { value: Value::String(dst.to_string_lossy().into_owned()), print, ..Default::default() })
}

#[cfg(test)]
mod tests {
    #[test]
    fn base64_pads_like_the_standard() {
        assert_eq!(super::base64(b""), "");
        assert_eq!(super::base64(b"f"), "Zg==");
        assert_eq!(super::base64(b"fo"), "Zm8=");
        assert_eq!(super::base64(b"foo"), "Zm9v");
        assert_eq!(super::base64(b"foobar"), "Zm9vYmFy");
    }
}
