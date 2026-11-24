//! Standalone CLI subcommands for checking exported sheets and synthesising sound from their JSON.
//!
//!     beanfx check <sheet.json> [--max-colours N] [--max-mb M] [--no-trim] [--json]
//!     beanfx sfx <sheet.json> [--out <dir>] [--voice retro|soft|real] [--element <el>] [--seed N] [--sounds <dir|auto|none>] [--json]
//!
//! Exit codes match the draft runner: 0 clean, 1 a check failed, 2 bad usage or an error.

use beanfx::{ex, img, sfx};
use ndarray::{s, Array3};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};

const CHECK_USAGE: &str = "Run the kit's craft, framing, budget, act and sound checks on an exported sheet JSON.

    beanfx check <sheet.json> [--max-colours N] [--max-mb M] [--no-trim] [--json]

Exit 0 when clean, 1 when a check fails, 2 on bad usage or an error.";

const SFX_USAGE: &str = "Synthesise the WAV track and cue files for an exported sheet JSON and update meta.beanfx.sound.

    beanfx sfx <sheet.json> [--out <dir>] [--voice retro|soft|real] [--element <el>] [--seed N] [--sounds <dir|auto|none>] [--json]

Exit 0 when clean, 1 when a sound check fails, 2 on bad usage or an error.";

struct FrameRect {
    page: usize,
    x: usize,
    y: usize,
    w: usize,
    h: usize,
}

fn read_json(path: &Path) -> Result<Value, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    serde_json::from_str(&text).map_err(|e| format!("{}: {e}", path.display()))
}

fn slice_paged(pages: &[Array3<u8>], rects: &[FrameRect]) -> Result<Vec<Array3<u8>>, String> {
    let mut frames = Vec::with_capacity(rects.len());
    for r in rects {
        let sheet = pages.get(r.page).ok_or_else(|| format!("frame references missing page {}", r.page))?;
        let (sh, sw, _) = sheet.dim();
        if r.x + r.w > sw || r.y + r.h > sh {
            return Err(format!("frame rect ({},{},{},{}) exceeds page {} ({sw}x{sh})", r.x, r.y, r.w, r.h, r.page));
        }
        frames.push(sheet.slice(s![r.y..r.y + r.h, r.x..r.x + r.w, ..]).to_owned());
    }
    Ok(frames)
}

fn load_sheets(dir: &Path, js: &Value, bfx: &Value) -> Result<(Vec<Array3<u8>>, Option<Vec<Array3<u8>>>), String> {
    if let Some(pgs) = bfx.get("pages").and_then(Value::as_array) {
        let mut color_pages = Vec::with_capacity(pgs.len());
        let mut light_pages = Vec::new();
        for p in pgs {
            let cf = p
                .get("color")
                .and_then(Value::as_str)
                .or_else(|| p.get("image").and_then(Value::as_str))
                .ok_or("page entry missing image path")?;
            color_pages.push(img::read(dir.join(cf))?);
            if let Some(lf) = p.get("light").and_then(Value::as_str) {
                let lp = dir.join(lf);
                if lp.is_file() {
                    light_pages.push(img::read_rgb(lp)?);
                }
            }
        }
        let lights = (light_pages.len() == pgs.len() && !light_pages.is_empty()).then_some(light_pages);
        return Ok((color_pages, lights));
    }

    let cf = bfx
        .get("color")
        .and_then(Value::as_str)
        .or_else(|| bfx.get("sheet").and_then(Value::as_str))
        .or_else(|| js.pointer("/meta/image").and_then(Value::as_str))
        .ok_or("cannot find sheet image path in JSON")?;
    let color_pages = vec![img::read(dir.join(cf))?];
    let light_pages = match bfx.get("light").and_then(Value::as_str) {
        Some(lf) if dir.join(lf).is_file() => Some(vec![img::read_rgb(dir.join(lf))?]),
        _ => None,
    };
    Ok((color_pages, light_pages))
}

fn parse_rects(js: &Value) -> Result<Vec<FrameRect>, String> {
    let arr = js.get("frames").and_then(Value::as_array).ok_or("missing frames array in JSON")?;
    if arr.is_empty() {
        return Err("frames array is empty".into());
    }
    let mut rects = Vec::with_capacity(arr.len());
    for entry in arr {
        let r = entry.get("frame").ok_or("frame entry missing rect")?;
        rects.push(FrameRect {
            page: entry.get("page").and_then(Value::as_u64).unwrap_or(0) as usize,
            x: r["x"].as_u64().ok_or("bad frame.x")? as usize,
            y: r["y"].as_u64().ok_or("bad frame.y")? as usize,
            w: r["w"].as_u64().ok_or("bad frame.w")? as usize,
            h: r["h"].as_u64().ok_or("bad frame.h")? as usize,
        });
    }
    Ok(rects)
}

pub fn check(args: &[String]) -> i32 {
    if args.iter().any(|a| a == "-h" || a == "--help") {
        println!("{CHECK_USAGE}");
        return 0;
    }
    match check_inner(args) {
        Ok(code) => code,
        Err(e) => {
            eprintln!("error: {e}");
            2
        }
    }
}

fn check_inner(args: &[String]) -> Result<i32, String> {
    let mut sheet_json: Option<PathBuf> = None;
    let mut max_colours: Option<f64> = None;
    let mut max_mb: Option<f64> = Some(ex::BUDGET_MB);
    let mut trim: Option<f64> = Some(ex::TRIM);
    let mut as_json = false;

    let mut i = 0;
    while i < args.len() {
        let a = args[i].as_str();
        let next = |i: &mut usize, flag: &str| -> Result<String, String> {
            *i += 1;
            args.get(*i).cloned().ok_or_else(|| format!("{flag} needs a value"))
        };
        match a {
            "--max-colours" => max_colours = Some(next(&mut i, a)?.parse().map_err(|_| "bad --max-colours")?),
            "--max-mb" => max_mb = Some(next(&mut i, a)?.parse().map_err(|_| "bad --max-mb")?),
            "--no-trim" => trim = None,
            "--json" => as_json = true,
            s if !s.starts_with('-') && sheet_json.is_none() => sheet_json = Some(PathBuf::from(s)),
            other => return Err(format!("unknown check argument: {other}")),
        }
        i += 1;
    }

    let jp = sheet_json.ok_or("check needs <sheet.json>")?;
    let dir = jp.parent().filter(|p| !p.as_os_str().is_empty()).unwrap_or_else(|| Path::new("."));
    let js = read_json(&jp)?;
    let bfx = js.pointer("/meta/beanfx").ok_or("missing meta.beanfx in JSON")?;
    let rects = parse_rects(&js)?;
    let (color_pages, light_pages) = load_sheets(dir, &js, bfx)?;
    let frames = slice_paged(&color_pages, &rects)?;
    let light_frames = match light_pages {
        Some(lp) => Some(slice_paged(&lp, &rects)?),
        None => None,
    };

    let looped = bfx.get("loop").and_then(Value::as_bool).unwrap_or(false);
    let hold = bfx.get("end").and_then(Value::as_str) == Some("hold");
    let fps = bfx.get("fps").and_then(Value::as_f64).unwrap_or(24.0);

    let mut problems = ex::check(
        &frames,
        ex::Check {
            light: light_frames.as_ref().map(|v| v.into()),
            looped,
            hold,
            src: None,
            max_colours,
            trim,
            max_mb,
        },
    )?;
    if let Some(act) = bfx.get("act") {
        problems.extend(ex::check_act(act, frames.len() as i64, fps, looped)?);
    }
    if bfx.get("sound").is_some() {
        problems.extend(sfx::check(dir, &js)?);
    }

    let mem_mb = ex::memory_mb(&frames, light_frames.is_some());
    let framing = ex::framing(&frames)?;
    let ok = problems.is_empty();
    if as_json {
        let fr_val = framing.map(|f| {
            json!({
                "box": [f.x0, f.y0, f.x1, f.y1],
                "size": [f.w, f.h],
                "cut": f.cut,
                "trim": f.trim,
            })
        });
        println!(
            "{}",
            serde_json::to_string(&json!({
                "ok": ok,
                "json": jp.display().to_string(),
                "frames": frames.len(),
                "memory_mb": mem_mb,
                "framing": fr_val,
                "problems": problems,
            }))
            .map_err(|e| e.to_string())?
        );
    } else {
        println!(
            "check: {} ({} frames, {:.2} MB) — {}",
            jp.display(),
            frames.len(),
            mem_mb,
            if ok { "clean" } else { "problems" }
        );
        for p in &problems {
            println!("{p}");
        }
    }
    Ok(if ok { 0 } else { 1 })
}

pub fn sfx(args: &[String]) -> i32 {
    if args.iter().any(|a| a == "-h" || a == "--help") {
        println!("{SFX_USAGE}");
        return 0;
    }
    match sfx_inner(args) {
        Ok(code) => code,
        Err(e) => {
            eprintln!("error: {e}");
            2
        }
    }
}

fn sfx_inner(args: &[String]) -> Result<i32, String> {
    let mut sheet_json: Option<PathBuf> = None;
    let mut out_dir: Option<PathBuf> = None;
    let mut voice = "retro".to_string();
    let mut element: Option<String> = None;
    let mut seed: u64 = 1;
    let mut sounds: Option<String> = Some("auto".into());
    let mut as_json = false;

    let mut i = 0;
    while i < args.len() {
        let a = args[i].as_str();
        let next = |i: &mut usize, flag: &str| -> Result<String, String> {
            *i += 1;
            args.get(*i).cloned().ok_or_else(|| format!("{flag} needs a value"))
        };
        match a {
            "--out" => out_dir = Some(PathBuf::from(next(&mut i, a)?)),
            "--voice" => voice = next(&mut i, a)?,
            "--element" => element = Some(next(&mut i, a)?),
            "--seed" => seed = next(&mut i, a)?.parse().map_err(|_| "bad --seed")?,
            "--sounds" => {
                let s = next(&mut i, a)?;
                sounds = if s == "none" { None } else { Some(s) };
            }
            "--json" => as_json = true,
            s if !s.starts_with('-') && sheet_json.is_none() => sheet_json = Some(PathBuf::from(s)),
            other => return Err(format!("unknown sfx argument: {other}")),
        }
        i += 1;
    }

    let jp = sheet_json.ok_or("sfx needs <sheet.json>")?;
    let mut js = read_json(&jp)?;
    let name = jp
        .file_stem()
        .and_then(|s| s.to_str())
        .ok_or("sheet.json has no stem")?
        .to_string();
    let json_dir = jp.parent().filter(|p| !p.as_os_str().is_empty()).unwrap_or_else(|| Path::new(".")).to_path_buf();
    let out = out_dir.unwrap_or_else(|| json_dir.clone());
    std::fs::create_dir_all(&out).map_err(|e| e.to_string())?;
    let mut sound_block = sfx::write(
        &out,
        &name,
        Some(&mut js),
        sfx::Write { seed, voice, element, layers: None, sounds },
    )?;
    // sfx::write updates <out>/<name>.json only. When --out is another folder, point the sound paths at it from the
    // sheet's own folder and save the sheet JSON, so `beanfx check <sheet.json>` finds the track and the cues.
    let canon = |p: &Path| std::fs::canonicalize(p).map_err(|e| format!("{}: {e}", p.display()));
    let (out_c, dir_c) = (canon(&out)?, canon(&json_dir)?);
    if out_c != dir_c {
        let prefix = match out_c.strip_prefix(&dir_c) {
            Ok(rel) => rel.components().map(|c| c.as_os_str().to_string_lossy().into_owned()).collect::<Vec<_>>().join("/"),
            Err(_) => out_c.to_string_lossy().replace('\\', "/"),
        };
        let rebase = |v: &mut Value| {
            if let Some(f) = v.as_str() {
                *v = json!(format!("{prefix}/{f}"));
            }
        };
        rebase(&mut sound_block["track"]);
        if let Some(cues) = sound_block.get_mut("cues").and_then(Value::as_array_mut) {
            for c in cues {
                rebase(&mut c["file"]);
            }
        }
        js.pointer_mut("/meta/beanfx").ok_or("missing meta.beanfx in JSON")?["sound"] = sound_block.clone();
        std::fs::write(&jp, beanfx::py::dumps(&js, Some(1))).map_err(|e| format!("{}: {e}", jp.display()))?;
    }
    let problems = sfx::check(&json_dir, &js)?;
    let ok = problems.is_empty();
    if as_json {
        println!(
            "{}",
            serde_json::to_string(&json!({
                "ok": ok,
                "name": name,
                "out_dir": out.display().to_string(),
                "sound": sound_block,
                "problems": problems,
            }))
            .map_err(|e| e.to_string())?
        );
    } else {
        println!(
            "sound: {} ({})",
            out.join(format!("{name}_sound.wav")).display(),
            if ok { "clean" } else { "problems" }
        );
        for p in &problems {
            println!("{p}");
        }
    }
    Ok(if ok { 0 } else { 1 })
}
