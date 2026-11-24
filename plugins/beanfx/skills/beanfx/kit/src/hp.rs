//! hp: the host project's palette, for the palette knob's recommended option (`beanfx palette [dir]`).
//!
//! An effect that goes into a game should look like the game. This reads the project the skill runs in: a palette
//! file the art uses (GIMP .gpl, JASC .pal, .hex lists) means a locked palette; otherwise the palettes of its
//! Aseprite files and the opaque pixels of its pixel-art PNGs, each file weighing the same (a big sprite sheet does
//! not drown a small one) and a PNG's background fill (one colour over half its pixels) left out. It groups the colours by hue family and gives each family a ramp, dark to bright, in the
//! project's own colours. Folders the effect work writes (drafts, out, .beanfx, target) and the skill's own files
//! are left out, so the effect never recommends its own colours back.

use crate::serde_json::{json, Value};
use std::collections::HashMap;
use std::path::{Path, PathBuf};

/// Folders never read: build output, dependencies, the effect work and other tools' caches.
const SKIP_DIRS: [&str; 14] = ["target", "node_modules", "drafts", "drafts_archive", "out", "pixelfx", "site", "dist",
                               "build", "Library", "Temp", "obj", "bin", "vendor"];
/// At most this many PNGs are read (the first in path order), and one larger than this per side is left out.
pub const MAX_PNGS: usize = 400;
pub const MAX_SIDE: usize = 2048;
/// A PNG with more distinct opaque colours than this is a photo, a render or a gradient, not pixel art.
pub const MAX_COLOURS: usize = 1024;

/// PNG names the beanfx runner writes (light and colour layers, strips, previews): never the game's art.
const OWN_PNG: [&str; 6] = ["_light.png", "_color.png", "_1x.png", "_4x_dark.png", "_4x_mid.png", "contact.png"];


fn hex(c: [u8; 3]) -> String {
    format!("#{:02x}{:02x}{:02x}", c[0], c[1], c[2])
}

/// Relative luminance (Rec. 709 weights on 0..1 values, no gamma: enough to order a ramp).
fn luma(c: [u8; 3]) -> f64 {
    (0.2126 * c[0] as f64 + 0.7152 * c[1] as f64 + 0.0722 * c[2] as f64) / 255.0
}

/// Hue in degrees and HSV saturation.
fn hue_sat(c: [u8; 3]) -> (f64, f64) {
    let [r, g, b] = c.map(|v| v as f64 / 255.0);
    let (mx, mn) = (r.max(g).max(b), r.min(g).min(b));
    let d = mx - mn;
    let s = if mx <= 0.0 { 0.0 } else { d / mx };
    if d <= 1e-9 {
        return (0.0, s);
    }
    let h = if mx == r { 60.0 * (((g - b) / d).rem_euclid(6.0)) } else if mx == g { 60.0 * ((b - r) / d + 2.0) } else { 60.0 * ((r - g) / d + 4.0) };
    (h, s)
}

/// The family of a colour, wide enough to hold a hue-shifted ramp (a fire ramp runs from purple-red shadows to
/// yellow lights): "warm" (hue 330 to 75: reds, oranges, yellows, browns), "green" (75 to 165), "cool" (165 to 270:
/// teal, cyan, blue), "purple" (270 to 330), and "neutral" for greys and colours too dark to tell.
pub fn family(c: [u8; 3]) -> &'static str {
    let (h, s) = hue_sat(c);
    let v = c.iter().copied().max().unwrap_or(0) as f64 / 255.0;
    if s < 0.15 || v < 0.12 {
        return "neutral";
    }
    match h {
        h if h >= 330.0 || h < 75.0 => "warm",
        h if h < 165.0 => "green",
        h if h < 270.0 => "cool",
        _ => "purple",
    }
}

/// Colours of a palette file: GIMP .gpl ("R G B name" lines), JASC .pal ("JASC-PAL" then "R G B" lines), or a
/// .hex list ("rrggbb" per line, with or without "#"). None for a file that is none of them.
pub fn read_palette(path: &Path) -> Option<Vec<[u8; 3]>> {
    let text = std::fs::read_to_string(path).ok()?;
    let ext = path.extension()?.to_str()?.to_ascii_lowercase();
    let rgb_line = |l: &str| {
        let v: Vec<u8> = l.split_whitespace().take(3).filter_map(|t| t.parse().ok()).collect();
        (v.len() == 3).then(|| [v[0], v[1], v[2]])
    };
    let cols: Vec<[u8; 3]> = match ext.as_str() {
        "gpl" if text.starts_with("GIMP Palette") => text.lines().skip(1)
            .filter(|l| !l.starts_with('#') && !l.contains(':')).filter_map(rgb_line).collect(),
        "pal" if text.starts_with("JASC-PAL") => text.lines().skip(3).filter_map(rgb_line).collect(),
        "hex" => text.lines().filter_map(|l| {
            let t = l.trim().trim_start_matches('#');
            (t.len() == 6).then(|| u32::from_str_radix(t, 16).ok()).flatten()
                .map(|v| [(v >> 16) as u8, (v >> 8) as u8, v as u8])
        }).collect(),
        _ => return None,
    };
    (!cols.is_empty()).then_some(cols)
}

/// The first palette of an Aseprite file (.aseprite, .ase): the new palette chunk (0x2019) of the first frame, else
/// the old one (0x0004). None when the file is not Aseprite or has neither.
pub fn read_aseprite(path: &Path) -> Option<Vec<[u8; 3]>> {
    let b = std::fs::read(path).ok()?;
    let u16_ = |i: usize| b.get(i..i + 2).map(|s| u16::from_le_bytes([s[0], s[1]]));
    let u32_ = |i: usize| b.get(i..i + 4).map(|s| u32::from_le_bytes([s[0], s[1], s[2], s[3]]));
    if u16_(4)? != 0xA5E0 || u16_(6)? == 0 {
        return None;
    }
    let f = 128; // the first frame
    if u16_(f + 4)? != 0xF1FA {
        return None;
    }
    let chunks = match u32_(f + 12)? { 0 => u16_(f + 6)? as u32, n => n };
    let (mut at, mut old) = (f + 16, None);
    for _ in 0..chunks {
        let (size, kind) = (u32_(at)? as usize, u16_(at + 4)?);
        let d = at + 6;
        if kind == 0x2019 {
            let (first, last) = (u32_(d + 4)? as usize, u32_(d + 8)? as usize);
            let mut cols = vec![];
            let mut e = d + 20;
            for _ in first..=last.max(first) {
                let flags = u16_(e)?;
                let c = b.get(e + 2..e + 6)?;
                if c[3] > 0 {
                    cols.push([c[0], c[1], c[2]]);
                }
                e += 6;
                if flags & 1 == 1 {
                    e += 2 + u16_(e)? as usize; // the entry's name
                }
            }
            return (!cols.is_empty()).then_some(cols);
        }
        if kind == 0x0004 && old.is_none() {
            let mut cols = vec![];
            let (mut e, mut idx) = (d + 2, 0usize);
            for _ in 0..u16_(d)? {
                let skip = *b.get(e)? as usize;
                let n = match *b.get(e + 1)? as usize { 0 => 256, n => n };
                idx += skip;
                e += 2;
                for _ in 0..n {
                    let c = b.get(e..e + 3)?;
                    cols.push([c[0], c[1], c[2]]);
                    e += 3;
                }
            }
            let _ = idx;
            old = (!cols.is_empty()).then_some(cols);
        }
        at += size.max(6);
    }
    old
}

/// Files under `root` in path order, hidden folders, `SKIP_DIRS` and the beanfx skill's own folder left out.
fn walk(root: &Path) -> Vec<PathBuf> {
    fn go(d: &Path, out: &mut Vec<PathBuf>) {
        let Ok(rd) = std::fs::read_dir(d) else { return };
        let mut es: Vec<PathBuf> = rd.filter_map(|e| e.ok().map(|e| e.path())).collect();
        es.sort();
        for p in es {
            let name = p.file_name().and_then(|n| n.to_str()).unwrap_or("");
            if name.starts_with('.') {
                continue;
            }
            if p.is_dir() {
                let own_skill = p.join("SKILL.md").exists() && p.join("kit").join("API.md").exists();
                if !SKIP_DIRS.contains(&name) && !own_skill {
                    go(&p, out);
                }
            } else {
                out.push(p);
            }
        }
    }
    let mut out = vec![];
    go(root, &mut out);
    out
}

/// Pixel counts of the opaque colours of a PNG; None when it is not pixel art by `MAX_SIDE` and `MAX_COLOURS`.
fn png_counts(path: &Path) -> Option<HashMap<[u8; 3], u64>> {
    let a = crate::img::read(path).ok()?;
    let (h, w, _) = a.dim();
    if h > MAX_SIDE || w > MAX_SIDE {
        return None;
    }
    let mut m: HashMap<[u8; 3], u64> = HashMap::new();
    for y in 0..h {
        for x in 0..w {
            if a[[y, x, 3]] >= 128 {
                *m.entry([a[[y, x, 0]], a[[y, x, 1]], a[[y, x, 2]]]).or_insert(0) += 1;
                if m.len() > MAX_COLOURS {
                    return None;
                }
            }
        }
    }
    let total: u64 = m.values().sum();
    if m.len() >= 4 {
        m.retain(|_, k| *k * 2 < total); // the background fill
    }
    (!m.is_empty()).then_some(m)
}

/// A ramp of at most `n` tones, dark to bright, from colours with counts: the luminance range cut in n bands,
/// the most used colour of each band.
fn ramp(cols: &[([u8; 3], u64)], n: usize) -> Vec<[u8; 3]> {
    let mut v: Vec<([u8; 3], u64)> = cols.to_vec();
    v.sort_by(|a, b| luma(a.0).total_cmp(&luma(b.0)).then(a.0.cmp(&b.0)));
    if v.len() <= n {
        return v.into_iter().map(|c| c.0).collect();
    }
    let (lo, hi) = (luma(v[0].0), luma(v[v.len() - 1].0));
    let mut out = vec![];
    for k in 0..n {
        let (a, b) = (lo + (hi - lo) * k as f64 / n as f64, lo + (hi - lo) * (k + 1) as f64 / n as f64);
        let best = v.iter().filter(|c| { let l = luma(c.0); l >= a && (l < b || k == n - 1) })
            .max_by(|x, y| x.1.cmp(&y.1).then(y.0.cmp(&x.0)));
        if let Some(c) = best {
            out.push(c.0);
        }
    }
    out
}

/// The host palette of the project at `root` as JSON: `source` ("palette_file", "aseprite", "sprites" or "none"), `locked`
/// (a palette file: draw only in its colours), `files` (read, at most 12 listed), `colours` (distinct), `top` (the
/// 24 most used), `ramps` (per family with at least 2 colours, most used first: `family`, `share` of the weight,
/// `tones`: 5 dark to bright, `colours`: its 16 most used, dark to bright, to pick an artist's own ramp from), `skipped` (PNGs left out as not pixel art).
pub fn scan(root: &Path) -> Value {
    let files = walk(root);
    let rel = |p: &Path| p.strip_prefix(root).unwrap_or(p).to_string_lossy().replace('\\', "/");
    let ext = |p: &Path| p.extension().and_then(|e| e.to_str()).map(|e| e.to_ascii_lowercase()).unwrap_or_default();
    // each file adds weight 1 spread over its colours by their share of its pixels (a palette: evenly)
    let mut weight: HashMap<[u8; 3], f64> = HashMap::new();
    let mut add = |m: &HashMap<[u8; 3], u64>| {
        let t: u64 = m.values().sum();
        for (c, k) in m {
            *weight.entry(*c).or_insert(0.0) += *k as f64 / t as f64;
        }
    };
    let even = |cols: Vec<[u8; 3]>| cols.into_iter().fold(HashMap::new(), |mut m, c| { *m.entry(c).or_insert(0u64) += 1; m });
    let mut used: Vec<String> = vec![];
    for p in &files {
        if let Some(cols) = read_palette(p) {
            add(&even(cols));
            used.push(rel(p));
        }
    }
    let locked = !used.is_empty();
    let (mut skipped, mut aseprite) = (0, false);
    if !locked {
        for p in files.iter().filter(|p| matches!(ext(p).as_str(), "aseprite" | "ase")) {
            if let Some(cols) = read_aseprite(p) {
                add(&even(cols));
                used.push(rel(p));
                aseprite = true;
            }
        }
        let pngs = files.iter().filter(|p| ext(p) == "png")
            .filter(|p| !OWN_PNG.iter().any(|o| p.to_string_lossy().ends_with(o)));
        for p in pngs.take(MAX_PNGS) {
            match png_counts(p) {
                Some(m) => {
                    add(&m);
                    used.push(rel(p));
                }
                None => skipped += 1,
            }
        }
    }
    if weight.is_empty() {
        return json!({"source": "none", "locked": false, "files": [], "colours": 0, "top": [], "ramps": [], "skipped": skipped});
    }
    // weights to whole counts for the ramp's "most used" (1e6 per file keeps the order)
    let total: f64 = weight.values().sum();
    let mut all: Vec<([u8; 3], u64)> = weight.into_iter().map(|(c, w)| (c, (w * 1e6).round() as u64)).collect();
    all.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
    let mut fams: HashMap<&str, Vec<([u8; 3], u64)>> = HashMap::new();
    for &(c, k) in &all {
        fams.entry(family(c)).or_default().push((c, k));
    }
    let mut ramps: Vec<(f64, &str, Vec<[u8; 3]>, Vec<[u8; 3]>)> = fams.iter().filter(|(_, v)| v.len() >= 2)
        .map(|(f, v)| {
            let mut by_use = v.clone();
            by_use.truncate(16); // v is most used first
            by_use.sort_by(|a, b| luma(a.0).total_cmp(&luma(b.0)).then(a.0.cmp(&b.0)));
            (v.iter().map(|c| c.1).sum::<u64>() as f64 / (total * 1e6), *f, ramp(v, 5), by_use.into_iter().map(|c| c.0).collect())
        }).collect();
    ramps.sort_by(|a, b| b.0.total_cmp(&a.0).then(a.1.cmp(b.1)));
    json!({
        "source": if locked { "palette_file" } else if aseprite { "aseprite" } else { "sprites" },
        "locked": locked,
        "files": used.iter().take(12).collect::<Vec<_>>(),
        "colours": all.len(),
        "top": all.iter().take(24).map(|c| hex(c.0)).collect::<Vec<_>>(),
        "ramps": ramps.iter().map(|(s, f, t, a)| json!({"family": f, "share": (s * 1000.0).round() / 1000.0,
                                                        "tones": t.iter().map(|c| hex(*c)).collect::<Vec<_>>(),
                                                        "colours": a.iter().map(|c| hex(*c)).collect::<Vec<_>>()})).collect::<Vec<_>>(),
        "skipped": skipped,
    })
}
