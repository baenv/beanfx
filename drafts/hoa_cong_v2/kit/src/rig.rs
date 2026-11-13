//! rig.py: a game character as the caster, the owner's own sprite sheets read through a rig.json.
//!
//! The effect is drawn in the character's frame space: the effect's pivot is the character's pivot (the feet), its
//! frame k plays with the character's frame `start + k` at the character's fps, and a top-down effect has one row
//! per direction of the character. The sheet stays the effect alone; the character goes into the previews only,
//! and the JSON tells the engine which animation and frame the effect rides on (meta.beanfx.caster).
//!
//! The sprites are the owner's licensed art and stay local: `casters/<name>/` in the project (gitignored), never
//! in the plugin. A later character that keeps the same rig.json works with every effect drawn on the first one.
//!
//! casters/<name>/rig.json:
//! `{"name": "knight_side", "view": "side", "facing": "east", "fps": 10, "anims": {"attack1": {"frame": [96, 80],
//! "frames": 8, "sheet": "attack01.png", "pivot": [50, 64], "contact": [1, 5]}}}`.
//! Top-down: `"view": "top-down", "directions": ["east", "south", "west", "north"]` (or the 8 of fc::NAMES8), and
//! each animation gives `"sheets": {"east": "attack1_right.png", ...}` in place of `"sheet"`. A side view with its
//! own west row (an asymmetric character): `"view": "side", "directions": ["east", "west"]` and `"sheets"` by
//! direction; the engine then picks the row and never mirrors. Each animation may carry its own `"fps"`.
//! Optional: `"pixel_scale"`, `"height"`, and per animation `"swing"` (the sword strokes as [{"kind": "slash",
//! "turn": "cw" | "ccw", "from": deg, "to": deg, "sweep": deg, "frames": [...]}] in screen degrees, 0 east, 90
//! south, y down; on top-down a dict of those lists by direction), `"root"` (with `"move": "root"`: the body's
//! travel per frame as [dx, dy] px from where the animation starts, a dict by direction on top-down), `"thrust"`,
//! `"emit"` and `"hit"` (read by the engine and the effect author, passed through untouched). A missing pivot is
//! measured from the sheet (`measure`).
//!
//! Where the skill folder is found: `load` falls back to the skill's `casters/` through `ex::skill_dir`, which
//! tries the env var BEANFX_SKILL, then the path in `<kit>/skill.txt`, then the folder above the kit, where the
//! kit folder is this crate's folder (CARGO_MANIFEST_DIR at build time). In a draft the pinned kit copy is the
//! crate, so setup.sh's skill.txt or BEANFX_SKILL points back to the skill.

use crate::{ex, fc, img, np};
use ndarray::{s, Array3};
use serde_json::{json, Map, Value};
use std::cell::RefCell;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::rc::Rc;

pub const VIEWS: [&str; 2] = ["side", "top-down"];
/// export.row_names(4) and facing rows, in order.
pub const DIRS4: [&str; 4] = ["east", "south", "west", "north"];

/// BEANFX_PROJECT, else the nearest folder up from start (cwd) holding casters/, else the git root.
pub fn project_root(start: Option<&Path>) -> PathBuf {
    if let Ok(e) = std::env::var("BEANFX_PROJECT") {
        if !e.is_empty() {
            return PathBuf::from(e);
        }
    }
    let raw = match start {
        Some(p) => p.to_path_buf(),
        None => std::env::current_dir().unwrap_or_default(),
    };
    let p = std::fs::canonicalize(&raw).unwrap_or(raw);
    let mut d = Some(p.as_path());
    while let Some(dir) = d {
        if dir.join("casters").is_dir() || dir.join(".git").exists() {
            return dir.to_path_buf();
        }
        d = dir.parent();
    }
    p
}

/// The first n frames of w x h cut from the sheet at path, left to right.
fn cells(path: &Path, w: usize, h: usize, n: usize) -> Result<Vec<Array3<u8>>, String> {
    let im = img::read(path)?;
    let (ih, iw, _) = im.dim();
    if ih < h || iw < w * n {
        let name = path.file_name().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default();
        return Err(format!("{name}: {iw}x{ih} holds fewer than {n} frames of {w}x{h}"));
    }
    Ok((0..n).map(|k| im.slice(s![..h, k * w..(k + 1) * w, ..]).to_owned()).collect())
}

/// The feet on frame 0 (the neutral pose; later frames carry smears and lunges): y the row under its lowest pixel
/// (pixel edges, so the sprite stands on y), x the mean of the opaque pixels in the legs (its lowest quarter),
/// which stays on the body in a stride where the feet spread.
pub fn measure(frames: &[Array3<u8>]) -> Result<[i64; 2], String> {
    let f = frames.first().ok_or("measure: no frames")?;
    let (h, w, _) = f.dim();
    let on = |y: usize, x: usize| f[[y, x, 3]] > 0;
    let rows: Vec<usize> = (0..h).filter(|&y| (0..w).any(|x| on(y, x))).collect();
    let (top, low) = match (rows.first(), rows.last()) {
        (Some(&t), Some(&l)) => (t, l),
        _ => return Err("zero-size array to reduction operation minimum which has no identity".into()),
    };
    let leg = np::floordiv_i((low - top) as i64, 4).max(1) as usize;
    let start = low + 1 - leg;
    let xs: Vec<f64> = (start..=low).flat_map(|y| (0..w).map(move |x| (y, x))).filter(|&(y, x)| on(y, x)).map(|(_, x)| x as f64).collect();
    if xs.is_empty() {
        return Err("measure: no opaque pixel in the legs".into());
    }
    Ok([np::round(np::mean(&ndarray::Array1::from(xs)) + 0.5) as i64, low as i64 + 1])
}

fn repr_list(v: &[String]) -> String {
    format!("[{}]", v.iter().map(|s| format!("'{s}'")).collect::<Vec<_>>().join(", "))
}

/// A whole f64 as an int Value, else a float (how Python writes the number it was given).
fn num(x: f64) -> Value {
    if x.fract() == 0.0 && x.abs() < 1e15 {
        json!(x as i64)
    } else {
        json!(x)
    }
}

fn show(x: f64) -> String {
    if x.fract() == 0.0 && x.abs() < 1e15 { format!("{}", x as i64) } else { format!("{x}") }
}

fn fnum(v: &Value, what: &str) -> Result<f64, String> {
    v.as_f64().ok_or_else(|| format!("{what}: not a number"))
}

/// A rig.json and the sprite sheets beside it.
pub struct Rig {
    pub dir: PathBuf,
    pub spec: Value,
    pub name: String,
    pub view: String,
    pub fps: f64,
    pub directions: Vec<String>,
    cache: RefCell<HashMap<(String, String), Rc<Vec<Array3<u8>>>>>,
}

/// Options of `frame_at`.
#[derive(Clone, Debug)]
pub struct FrameAt<'a> {
    pub direction: Option<&'a str>,
    pub start: i64,
    /// Keep the last frame after the animation ends.
    pub hold: bool,
}

impl Default for FrameAt<'_> {
    fn default() -> Self {
        FrameAt { direction: None, start: 0, hold: true }
    }
}

/// Options of `place`.
#[derive(Clone, Debug)]
pub struct Place<'a> {
    pub direction: Option<&'a str>,
    pub start: i64,
    pub hold: bool,
    /// Add the animation's root motion, so pivot is where the move began.
    pub travel: bool,
}

impl Default for Place<'_> {
    fn default() -> Self {
        Place { direction: None, start: 0, hold: true, travel: false }
    }
}

/// Options of `check_arc`.
#[derive(Clone, Debug)]
pub struct CheckArc<'a> {
    pub direction: Option<&'a str>,
    pub stroke: usize,
    /// Degrees an arc end may sit from the stroke's.
    pub tol: f64,
}

impl Default for CheckArc<'_> {
    fn default() -> Self {
        CheckArc { direction: None, stroke: 0, tol: 60.0 }
    }
}

/// Options of `meta`.
#[derive(Clone, Debug)]
pub struct Meta<'a> {
    pub start: i64,
    /// "front" or "behind".
    pub layer: &'a str,
    pub directions: Option<Vec<String>>,
    /// The cast lands offset px in front of the character (knobs/placement.md); None or 0 for none.
    pub offset: Option<f64>,
}

impl Default for Meta<'_> {
    fn default() -> Self {
        Meta { start: 0, layer: "front", directions: None, offset: None }
    }
}

fn dir_or<'a>(rig: &'a Rig, direction: Option<&'a str>) -> &'a str {
    direction.filter(|d| !d.is_empty()).unwrap_or(&rig.directions[0])
}

impl Rig {
    /// Reads folder/rig.json.
    pub fn new(folder: impl AsRef<Path>) -> Result<Rig, String> {
        let dir = folder.as_ref().to_path_buf();
        let file = dir.join("rig.json");
        let text = std::fs::read_to_string(&file).map_err(|e| format!("{}: {e}", file.display()))?;
        let spec: Value = serde_json::from_str(&text).map_err(|e| format!("{}: {e}", file.display()))?;
        let dname = dir.file_name().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default();
        let name = spec.get("name").and_then(|v| v.as_str()).map(String::from).unwrap_or(dname);
        let view = spec.get("view").and_then(|v| v.as_str()).ok_or("rig.json: no view")?.to_string();
        if !VIEWS.contains(&view.as_str()) {
            return Err(format!("view '{view}' not in ('side', 'top-down')"));
        }
        let fps = fnum(spec.get("fps").ok_or("rig.json: no fps")?, "fps")?;
        let directions: Vec<String> = match spec.get("directions").and_then(|v| v.as_array()) {
            Some(a) => a.iter().filter_map(|v| v.as_str().map(String::from)).collect(),
            None => vec![spec.get("facing").and_then(|v| v.as_str()).unwrap_or("east").to_string()],
        };
        if !spec.get("anims").map(|a| a.is_object()).unwrap_or(false) {
            return Err("rig.json: no anims".into());
        }
        Ok(Rig { dir, spec, name, view, fps, directions, cache: RefCell::new(HashMap::new()) })
    }

    /// The animation names, in rig.json order.
    pub fn anims(&self) -> Vec<String> {
        self.spec["anims"].as_object().map(|m| m.keys().cloned().collect()).unwrap_or_default()
    }

    /// One animation's rig.json object.
    pub fn anim(&self, name: &str) -> Result<&Value, String> {
        self.spec["anims"].get(name).ok_or_else(|| format!("{} has no animation '{}'; it has {}", self.name, name, repr_list(&self.anims())))
    }

    /// The character's frames (h, w, 4) uint8 for one animation and direction (top-down).
    pub fn frames(&self, anim: &str, direction: Option<&str>) -> Result<Rc<Vec<Array3<u8>>>, String> {
        let a = self.anim(anim)?;
        let d = dir_or(self, direction).to_string();
        let key = (anim.to_string(), d.clone());
        if let Some(f) = self.cache.borrow().get(&key) {
            return Ok(f.clone());
        }
        let sheet = if a.get("sheets").is_some() {
            a["sheets"].get(&d).and_then(|v| v.as_str()).ok_or_else(|| format!("'{d}'"))?
        } else {
            a.get("sheet").and_then(|v| v.as_str()).ok_or("'sheet'")?
        };
        let w = a["frame"][0].as_u64().ok_or("'frame'")? as usize;
        let h = a["frame"][1].as_u64().ok_or("'frame'")? as usize;
        let n = a["frames"].as_u64().ok_or("'frames'")? as usize;
        let f = Rc::new(cells(&self.dir.join(sheet), w, h, n)?);
        self.cache.borrow_mut().insert(key, f.clone());
        Ok(f)
    }

    /// The animation's own fps (rig.json anims.<name>.fps), else the rig's.
    pub fn fps_of(&self, anim: &str) -> Result<f64, String> {
        let a = self.anim(anim)?;
        match a.get("fps") {
            Some(v) => fnum(v, "fps"),
            None => Ok(self.fps),
        }
    }

    fn fps_value(&self, anim: &str) -> Result<Value, String> {
        let a = self.anim(anim)?;
        Ok(a.get("fps").cloned().unwrap_or_else(|| self.spec["fps"].clone()))
    }

    /// The pivot as rig.json writes it (ints stay ints), else measured from the sheet.
    fn pivot_value(&self, anim: &str) -> Result<Vec<Value>, String> {
        let a = self.anim(anim)?;
        match a.get("pivot").and_then(|v| v.as_array()) {
            Some(p) => Ok(p.clone()),
            None => Ok(measure(&self.frames(anim, None)?)?.iter().map(|&v| json!(v)).collect()),
        }
    }

    /// The animation's pivot [x, y]: from rig.json, else measured from the sheet.
    pub fn pivot(&self, anim: &str) -> Result<[f64; 2], String> {
        let p = self.pivot_value(anim)?;
        Ok([fnum(&p[0], "pivot")?, fnum(&p[1], "pivot")?])
    }

    /// The contact frames of an animation, as rig.json writes them; empty when it gives none.
    pub fn contact(&self, anim: &str) -> Result<Vec<Value>, String> {
        Ok(self.anim(anim)?.get("contact").and_then(|v| v.as_array()).cloned().unwrap_or_default())
    }

    /// The sword strokes of an animation (for one direction on top-down); empty when rig.json gives none.
    pub fn swing(&self, anim: &str, direction: Option<&str>) -> Result<Vec<Value>, String> {
        let a = self.anim(anim)?;
        let s = match a.get("swing") {
            Some(Value::Object(m)) => m.get(dir_or(self, direction)).and_then(|v| v.as_array()).cloned().unwrap_or_default(),
            Some(Value::Array(v)) => v.clone(),
            _ => vec![],
        };
        Ok(s)
    }

    fn root_value(&self, anim: &str, direction: Option<&str>) -> Result<Vec<Value>, String> {
        let a = self.anim(anim)?;
        let r = match a.get("root") {
            Some(Value::Object(m)) => m.get(dir_or(self, direction)).cloned(),
            other => other.cloned(),
        };
        match r {
            Some(Value::Array(v)) if !v.is_empty() => Ok(v),
            _ => {
                let n = a["frames"].as_u64().ok_or("'frames'")? as usize;
                Ok((0..n).map(|_| json!([0, 0])).collect())
            }
        }
    }

    /// [dx, dy] per frame: how far the body has moved from the animation's start; zeros when it stays put.
    pub fn root(&self, anim: &str, direction: Option<&str>) -> Result<Vec<[f64; 2]>, String> {
        self.root_value(anim, direction)?
            .iter()
            .map(|p| Ok([fnum(&p[0], "root")?, fnum(&p[1], "root")?]))
            .collect()
    }

    /// (a0, a1) in degrees for an effect arc that runs with the blade: a0 the stroke's `from`, a1 = a0 + sweep, so
    /// a1 - a0 carries the turn (positive cw on screen, y down).
    pub fn arc(&self, anim: &str, direction: Option<&str>, stroke: usize) -> Result<(f64, f64), String> {
        let s = self.stroke(anim, direction, stroke)?;
        let from = fnum(&s["from"], "from")?;
        Ok((from, from + fnum(&s["sweep"], "sweep")?))
    }

    /// Problems when an effect arc a0 to a1 (degrees, the sign of a1 - a0 is its turn) leaves the blade's stroke:
    /// the wrong turn, or an end more than tol degrees from the stroke's from or to. Empty when it follows it.
    pub fn check_arc(&self, anim: &str, a0: f64, a1: f64, o: CheckArc) -> Result<Vec<String>, String> {
        let s = self.stroke(anim, o.direction, o.stroke)?;
        let dir = match o.direction.filter(|d| !d.is_empty()) {
            Some(d) => format!(" {d}"),
            None => String::new(),
        };
        let where_ = format!("{} {anim}{dir} stroke {}", self.name, o.stroke);
        let mut bad = vec![];
        let turn = if a1 > a0 { "cw" } else { "ccw" };
        let want_turn = s["turn"].as_str().unwrap_or("");
        if turn != want_turn {
            bad.push(format!("{where_}: arc turns {turn}, the blade turns {want_turn}"));
        }
        for (label, got, key) in [("start", a0, "from"), ("end", a1, "to")] {
            let want = fnum(&s[key], key)?;
            let off = np::pymod(got - want + 180.0, 360.0) - 180.0;
            let off = off.abs();
            if off > o.tol {
                bad.push(format!("{where_}: arc {label} {got:.0} is {off:.0} deg from the blade's {}", s[key]));
            }
        }
        Ok(bad)
    }

    fn stroke(&self, anim: &str, direction: Option<&str>, stroke: usize) -> Result<Value, String> {
        let strokes = self.swing(anim, direction)?;
        if strokes.is_empty() {
            return Err(format!("{} {anim} has no swing in rig.json", self.name));
        }
        strokes.get(stroke).cloned().ok_or_else(|| "list index out of range".to_string())
    }

    /// The character's frame for effect frame k, or None after the animation ends (hold keeps the last).
    pub fn frame_at(&self, anim: &str, k: i64, o: FrameAt) -> Result<Option<Array3<u8>>, String> {
        let fr = self.frames(anim, o.direction)?;
        let i = o.start + k;
        if i < fr.len() as i64 {
            return Ok(Some(fr[i.max(0) as usize].clone()));
        }
        Ok(if o.hold { fr.last().cloned() } else { None })
    }

    /// The character on an empty canvas of shape (H, W), its pivot on the canvas point pivot; travel adds the
    /// animation's root motion, so pivot is where the move began.
    pub fn place(&self, shape: (usize, usize), pivot: [f64; 2], anim: &str, k: i64, o: Place) -> Result<Array3<u8>, String> {
        let (hh, ww) = (shape.0 as i64, shape.1 as i64);
        let mut out = Array3::<u8>::zeros((shape.0, shape.1, 4));
        let fa = FrameAt { direction: o.direction, start: o.start, hold: o.hold };
        let Some(fr) = self.frame_at(anim, k, fa)? else {
            return Ok(out);
        };
        let [px, py] = self.pivot(anim)?;
        let mut pivot = pivot;
        if o.travel {
            let n = self.frames(anim, o.direction)?.len() as i64;
            let root = self.root(anim, o.direction)?;
            let [dx, dy] = root[(o.start + k).max(0).min(n - 1) as usize];
            pivot = [pivot[0] + dx, pivot[1] + dy];
        }
        let (ox, oy) = (np::round(pivot[0] - px) as i64, np::round(pivot[1] - py) as i64);
        let (h, w) = (fr.dim().0 as i64, fr.dim().1 as i64);
        let (y0, y1, x0, x1) = (oy.max(0), (oy + h).min(hh), ox.max(0), (ox + w).min(ww));
        if y0 < y1 && x0 < x1 {
            out.slice_mut(s![y0 as usize..y1 as usize, x0 as usize..x1 as usize, ..])
                .assign(&fr.slice(s![(y0 - oy) as usize..(y1 - oy) as usize, (x0 - ox) as usize..(x1 - ox) as usize, ..]));
        }
        Ok(out)
    }

    /// meta.beanfx.caster: what the effect rides on. The engine puts the effect pivot on the character's pivot,
    /// starts it when the character shows frame `start` of `anim`, and draws it in front of (or behind) the
    /// character. effect_fps must be a whole multiple of the character's fps so the frames stay locked.
    pub fn meta(&self, anim: &str, effect_fps: f64, o: Meta) -> Result<Map<String, Value>, String> {
        let char_fps = self.fps_of(anim)?;
        let ratio = effect_fps / char_fps;
        if (ratio - np::round(ratio)).abs() > 1e-6 || np::round(ratio) < 1.0 {
            return Err(format!("effect fps {} is not a whole multiple of {anim}'s {}", show(effect_fps), self.fps_value(anim)?));
        }
        if o.layer != "front" && o.layer != "behind" {
            return Err("layer front or behind".into());
        }
        let a = self.anim(anim)?;
        let mut m = Map::new();
        m.insert("rig".into(), json!(self.name));
        m.insert("view".into(), json!(self.view));
        m.insert("anim".into(), json!(anim));
        m.insert("start".into(), json!(o.start));
        m.insert("char_fps".into(), self.fps_value(anim)?);
        m.insert("frames_per_char_frame".into(), json!(np::round(ratio) as i64));
        m.insert("char_frames".into(), a["frames"].clone());
        m.insert("char_frame".into(), a["frame"].clone());
        m.insert("char_pivot".into(), Value::Array(self.pivot_value(anim)?));
        m.insert("contact".into(), Value::Array(self.contact(anim)?));
        m.insert("layer".into(), json!(o.layer));
        m.insert("align".into(), json!("effect pivot on the character's pivot; mirror both together"));
        if let Some(ms) = a.get("ms") {
            // a game row with uneven frame times: the engine holds effect frames by these, not by fps
            m.insert("char_ms".into(), ms.clone());
        }
        if let Some(ps) = self.spec.get("pixel_scale") {
            m.insert("pixel_scale".into(), ps.clone());
        }
        let chosen: Vec<String> = match &o.directions {
            Some(d) if !d.is_empty() => d.clone(),
            _ => self.directions.clone(),
        };
        if let Some(off) = o.offset.filter(|&v| v != 0.0) {
            // the cast lands offset px in front of the character
            m.insert("range".into(), num(off));
            if self.view == "top-down" {
                let mut om = Map::new();
                for d in &chosen {
                    if !fc::NAMES8.contains(&d.as_str()) {
                        return Err(format!("'{d}' is not in list"));
                    }
                }
                let names: Vec<&str> = chosen.iter().map(|s| s.as_str()).collect();
                for (d, v) in fc::offset_dirs(off, &names) {
                    om.insert(d, json!(v));
                }
                m.insert("offset".into(), Value::Object(om));
            } else {
                m.insert("offset".into(), json!(fc::offset(off)));
            }
            m.insert("align".into(), json!("effect pivot on the character's pivot plus offset[direction]; mirror both together"));
        }
        let by_dir = self.view == "top-down" || self.directions.len() > 1;
        if by_dir {
            m.insert("directions".into(), json!(chosen));
            if a.get("swing").is_some() {
                let mut sm = Map::new();
                for d in &chosen {
                    sm.insert(d.clone(), Value::Array(self.swing(anim, Some(d))?));
                }
                m.insert("swing".into(), Value::Object(sm));
            }
        } else if a.get("swing").is_some() {
            m.insert("swing".into(), Value::Array(self.swing(anim, None)?));
        }
        if a.get("root").is_some() {
            if by_dir {
                let mut rm = Map::new();
                for d in &chosen {
                    rm.insert(d.clone(), Value::Array(self.root_value(anim, Some(d))?));
                }
                m.insert("root".into(), Value::Object(rm));
            } else {
                m.insert("root".into(), Value::Array(self.root_value(anim, None)?));
            }
            m.insert("anchor".into(), json!("start: the effect stays where the move began; the character travels by root"));
        }
        Ok(m)
    }
}

/// A folder path, else casters/<name>/ in the project (root, else see project_root), else the casters that ship
/// with the skill (its casters/: nghich_tien_kiem, _kiem_topdown, _truong, _truong_topdown).
pub fn load(name: &str, root: Option<&Path>) -> Result<Rig, String> {
    let p = Path::new(name);
    if p.join("rig.json").exists() {
        return Rig::new(p);
    }
    let p = project_root(root).join("casters").join(name);
    if p.join("rig.json").exists() {
        return Rig::new(p);
    }
    let kit = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    if let Some(skill) = ex::skill_dir(&kit) {
        if skill.join("casters").join(name).join("rig.json").exists() {
            return Rig::new(skill.join("casters").join(name));
        }
    }
    Err(format!(
        "no rig.json for {name} in {} or the skill's casters/; the owner's character sheets go in casters/<name>/",
        p.parent().map(|d| d.display().to_string()).unwrap_or_default()
    ))
}

/// effect (h, w, 4) uint8 in front of the character (both straight alpha).
pub fn over(effect: &Array3<u8>, char: &Array3<u8>) -> Array3<u8> {
    crate::tg::under(effect, char)
}
