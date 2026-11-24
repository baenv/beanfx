//! hp (`beanfx palette`): the host project's palette for the palette knob's recommended option.
//!
//! Before/after: a project with no art gives `source: none` (the knob then falls back to the element's own ramp, as
//! before this feature); a project with art gives ramps in its own colours. The sprites case is also a snapshot
//! (tests/fixtures/snapshots/palette_sprites.json, BEANFX_BLESS=1 rewrites it).

mod common;

use beanfx::hp;
use beanfx::ndarray::Array3;
use beanfx::serde_json::Value;
use std::path::Path;

fn png(path: &Path, w: usize, h: usize, px: impl Fn(usize, usize) -> [u8; 4]) {
    std::fs::create_dir_all(path.parent().unwrap()).unwrap();
    let a = Array3::from_shape_fn((h, w, 4), |(y, x, c)| px(x, y)[c]);
    beanfx::img::write(path, &a.view()).unwrap();
}

const FIRE: [[u8; 4]; 4] = [[0x3a, 0x10, 0x20, 255], [0x8a, 0x2a, 0x18, 255], [0xe0, 0x60, 0x1c, 255], [0xff, 0xc0, 0x40, 255]];
const BLUE: [u8; 4] = [0x20, 0x40, 0xe0, 255];

/// A game folder: a fire sprite on a big dark fill, plus files that must not count.
fn sprites_project(root: &Path) {
    // 16x16: a 4-tone fire in the middle 8x8, the rest a solid background colour
    png(&root.join("assets/sprites/torch.png"), 16, 16, |x, y| {
        if (4..12).contains(&x) && (4..12).contains(&y) { FIRE[(x - 4) / 2] } else { [0x10, 0x10, 0x18, 255] }
    });
    png(&root.join("assets/sprites/coin.png"), 4, 4, |x, _| [[0xff, 0xd8, 0x40, 255], [0xc0, 0x90, 0x20, 255], [0, 0, 0, 0], [0x80, 0x50, 0x10, 255]][x]);
    // the effect work and beanfx outputs: left out
    png(&root.join("drafts/fx/out/fx_1x.png"), 4, 4, |_, _| BLUE);
    png(&root.join("assets/fx_light.png"), 4, 4, |_, _| BLUE);
    png(&root.join(".beanfx/cache.png"), 4, 4, |_, _| BLUE);
    png(&root.join("node_modules/x/icon.png"), 4, 4, |_, _| BLUE);
    // a photo: too many colours to be pixel art
    png(&root.join("assets/photo.png"), 64, 64, |x, y| [(x * 4) as u8, (y * 4) as u8, ((x + y) * 2) as u8, 255]);
}

fn tones(v: &Value, family: &str) -> Vec<String> {
    list(v, family, "tones")
}

fn list(v: &Value, family: &str, key: &str) -> Vec<String> {
    v["ramps"].as_array().unwrap().iter().find(|r| r["family"] == family)
        .map(|r| r[key].as_array().unwrap().iter().map(|t| t.as_str().unwrap().to_string()).collect())
        .unwrap_or_default()
}

#[test]
fn a_project_without_art_recommends_nothing() {
    let d = common::tmpdir("hp_empty");
    std::fs::write(d.join("README.md"), "# a game\n").unwrap();
    let v = hp::scan(&d);
    assert_eq!(v["source"], "none");
    assert_eq!(v["ramps"].as_array().unwrap().len(), 0);
}

#[test]
fn sprites_give_ramps_in_the_games_colours() {
    let d = common::tmpdir("hp_sprites");
    sprites_project(&d);
    let v = hp::scan(&d);
    assert_eq!(v["source"], "sprites");
    assert_eq!(v["locked"], false);
    let files: Vec<&str> = v["files"].as_array().unwrap().iter().map(|f| f.as_str().unwrap()).collect();
    assert_eq!(files, ["assets/sprites/coin.png", "assets/sprites/torch.png"], "only the game's own pixel art");
    assert_eq!(v["skipped"], 1, "the photo");
    let top: Vec<&str> = v["top"].as_array().unwrap().iter().map(|t| t.as_str().unwrap()).collect();
    assert!(!top.contains(&"#101018"), "the torch's background fill is left out: {top:?}");
    assert!(!top.contains(&"#2040e0"), "no colour from drafts, outputs, hidden or dependency folders: {top:?}");
    // the fire's tones sit in the warm families, each ramp dark to bright
    // the fire's whole hue-shifted ramp, purple-red shadow to yellow light, is in one warm family, and the warm
    // ramp takes only the game's warm colours (the fire's and the coin's)
    let warm_all = list(&v, "warm", "colours");
    for c in ["#3a1020", "#8a2a18", "#e0601c", "#ffc040"] {
        assert!(warm_all.contains(&c.to_string()), "{c} among the warm colours: {warm_all:?}");
    }
    let game = ["#3a1020", "#8a2a18", "#e0601c", "#ffc040", "#ffd840", "#c09020", "#805010"];
    let warm = tones(&v, "warm");
    assert!(warm.len() >= 4 && warm.iter().all(|c| game.contains(&c.as_str())), "warm ramp from the game: {warm:?}");
    for r in v["ramps"].as_array().unwrap().iter().flat_map(|r| [(r["family"].clone(), &r["tones"]), (r["family"].clone(), &r["colours"])]) {
        let l: Vec<f64> = r.1.as_array().unwrap().iter().map(|t| {
            let h = u32::from_str_radix(&t.as_str().unwrap()[1..], 16).unwrap();
            0.2126 * (h >> 16) as f64 + 0.7152 * ((h >> 8) & 255) as f64 + 0.0722 * (h & 255) as f64
        }).collect();
        assert!(l.windows(2).all(|w| w[0] <= w[1]), "{} dark to bright: {l:?}", r.0);
    }
    snapshot(&v);
}

/// The sprites case against its blessed JSON: a change to the scan shows up as a diff of the recommendation.
fn snapshot(v: &Value) {
    let p = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/snapshots/palette_sprites.json");
    let got = beanfx::serde_json::to_string_pretty(v).unwrap() + "\n";
    if std::env::var("BEANFX_BLESS").is_ok_and(|b| b == "1") {
        std::fs::write(&p, &got).unwrap();
        return;
    }
    let want = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}; bless with BEANFX_BLESS=1", p.display()));
    assert_eq!(want, got, "palette scan differs from before the change; re-bless only on purpose");
}

#[test]
fn a_palette_file_locks_the_palette_and_wins_over_sprites() {
    let d = common::tmpdir("hp_gpl");
    sprites_project(&d);
    std::fs::create_dir_all(d.join("art")).unwrap();
    std::fs::write(d.join("art/game.gpl"), "GIMP Palette\nName: game\nColumns: 4\n# comment\n 26  28  44\tnight\n 93  39  93 plum\n177  62  83\n239 125  87\n255 205 117\n").unwrap();
    let v = hp::scan(&d);
    assert_eq!(v["source"], "palette_file");
    assert_eq!(v["locked"], true);
    assert_eq!(v["files"], beanfx::serde_json::json!(["art/game.gpl"]), "sprites are not read once a palette file exists");
    assert_eq!(v["colours"], 5);
    let all: Vec<String> = v["ramps"].as_array().unwrap().iter().flat_map(|r| r["tones"].as_array().unwrap().clone())
        .map(|t| t.as_str().unwrap().to_string()).collect();
    assert!(all.iter().all(|c| ["#1a1c2c", "#5d275d", "#b13e53", "#ef7d57", "#ffcd75"].contains(&c.as_str())), "only the file's colours: {all:?}");
}

#[test]
fn reads_jasc_pal_and_hex_lists() {
    let d = common::tmpdir("hp_formats");
    std::fs::write(d.join("a.pal"), "JASC-PAL\n0100\n3\n0 0 0\n255 0 77\n41 173 255\n").unwrap();
    std::fs::write(d.join("b.hex"), "ff004d\n#29adff\nnot a colour\n").unwrap();
    std::fs::write(d.join("c.pal"), "RIFF....").unwrap();
    assert_eq!(hp::read_palette(&d.join("a.pal")).unwrap(), vec![[0, 0, 0], [255, 0, 77], [41, 173, 255]]);
    assert_eq!(hp::read_palette(&d.join("b.hex")).unwrap(), vec![[255, 0, 77], [41, 173, 255]]);
    assert!(hp::read_palette(&d.join("c.pal")).is_none(), "a binary RIFF .pal is not read");
}

/// A minimal Aseprite file: header, one frame with a new palette chunk (one named entry, one transparent).
fn aseprite(entries: &[([u8; 4], Option<&str>)]) -> Vec<u8> {
    let mut chunk = vec![];
    chunk.extend((entries.len() as u32).to_le_bytes());
    chunk.extend(0u32.to_le_bytes());
    chunk.extend((entries.len() as u32 - 1).to_le_bytes());
    chunk.extend([0u8; 8]);
    for (c, name) in entries {
        chunk.extend((name.is_some() as u16).to_le_bytes());
        chunk.extend(c);
        if let Some(n) = name {
            chunk.extend((n.len() as u16).to_le_bytes());
            chunk.extend(n.as_bytes());
        }
    }
    let mut frame = vec![];
    let chunk_size = 6 + chunk.len() as u32;
    frame.extend((16 + chunk_size).to_le_bytes());
    frame.extend(0xF1FAu16.to_le_bytes());
    frame.extend(1u16.to_le_bytes());
    frame.extend(100u16.to_le_bytes());
    frame.extend([0u8; 2]);
    frame.extend(1u32.to_le_bytes());
    frame.extend(chunk_size.to_le_bytes());
    frame.extend(0x2019u16.to_le_bytes());
    frame.extend(chunk);
    let mut head = vec![0u8; 128];
    head[0..4].copy_from_slice(&(128 + frame.len() as u32).to_le_bytes());
    head[4..6].copy_from_slice(&0xA5E0u16.to_le_bytes());
    head[6..8].copy_from_slice(&1u16.to_le_bytes());
    head.extend(frame);
    head
}

#[test]
fn reads_the_palette_of_an_aseprite_file() {
    let d = common::tmpdir("hp_ase");
    let bytes = aseprite(&[([0x3a, 0x10, 0x20, 255], None), ([0xe0, 0x60, 0x1c, 255], Some("ember")),
                           ([0, 0, 0, 0], None), ([0xff, 0xc0, 0x40, 255], None)]);
    std::fs::create_dir_all(d.join("art")).unwrap();
    std::fs::write(d.join("art/hero.aseprite"), &bytes).unwrap();
    assert_eq!(hp::read_aseprite(&d.join("art/hero.aseprite")).unwrap(),
               vec![[0x3a, 0x10, 0x20], [0xe0, 0x60, 0x1c], [0xff, 0xc0, 0x40]], "named entry read, transparent dropped");
    std::fs::write(d.join("art/bad.ase"), b"not aseprite at all, just text that is long enough..................").unwrap();
    assert!(hp::read_aseprite(&d.join("art/bad.ase")).is_none());
    let v = hp::scan(&d);
    assert_eq!(v["source"], "aseprite");
    assert_eq!(v["locked"], false);
    assert_eq!(v["files"], beanfx::serde_json::json!(["art/hero.aseprite"]));
}

#[test]
fn families_name_hues() {
    assert_eq!(hp::family([255, 0, 0]), "warm");
    assert_eq!(hp::family([255, 200, 0]), "warm");
    assert_eq!(hp::family([0x3a, 0x10, 0x20]), "warm", "a fire ramp's purple-red shadow");
    assert_eq!(hp::family([0, 200, 40]), "green");
    assert_eq!(hp::family([0, 0, 255]), "cool");
    assert_eq!(hp::family([160, 0, 255]), "purple");
    assert_eq!(hp::family([128, 128, 128]), "neutral");
    assert_eq!(hp::family([10, 0, 0]), "neutral", "too dark to tell");
}
