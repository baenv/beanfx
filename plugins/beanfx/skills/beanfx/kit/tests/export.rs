//! Port of tests/test_export.py: the sheet grid and its Aseprite-style JSON line up, tags and hits hold, and check()
//! catches edge contact, empty frames, a one-shot that pops off, a loop seam, unseeded randomness, a drawing parked in
//! one corner of its cell and sheets over the texture budget.

mod common;

use beanfx::ex::{self, Check, Hit, Write};
use beanfx::serde_json::{json, Value};
use beanfx::{fc, tg};
use ndarray::Array3;
use std::fs;
use std::path::Path;

const W: usize = 40;
const H: usize = 32;
const N: usize = 12;
const FPS: f64 = 24.0;

type Fr = Array3<u8>;

fn disc(r: f64, cx: f64, cy: f64) -> Fr {
    let mut img = Array3::<u8>::zeros((H, W, 4));
    for y in 0..H {
        for x in 0..W {
            let (xs, ys) = (x as f64 + 0.5, y as f64 + 0.5);
            if (xs - cx).powi(2) + (ys - cy).powi(2) < r * r {
                for (c, v) in [250u8, 200, 80, 255].into_iter().enumerate() {
                    img[[y, x, c]] = v;
                }
            }
        }
    }
    img
}

fn d(r: f64) -> Fr {
    disc(r, 20.0, 16.0)
}

fn empty() -> Fr {
    Array3::zeros((H, W, 4))
}

fn shot() -> Vec<Fr> {
    [3.0, 6.0, 9.0, 11.0, 10.0, 8.0, 6.0, 4.0, 3.0, 2.0, 1.2, 0.8].iter().map(|&r| d(r)).collect()
}

fn light() -> Vec<Array3<f64>> {
    (0..N).map(|_| Array3::zeros((H, W, 3))).collect()
}

fn hit(frame: i64, o: Hit) -> Value {
    ex::hit(frame, FPS, o)
}

fn has(p: &[String], s: &str) -> bool {
    p.iter().any(|x| x.contains(s))
}

fn chk(frames: &Vec<Fr>) -> Vec<String> {
    ex::check(frames, Check::default()).unwrap()
}

/// (w, h, channels, bytes) of an 8-bit PNG.
fn read_png(p: &Path) -> (usize, usize, usize, Vec<u8>) {
    let dec = png::Decoder::new(std::io::BufReader::new(fs::File::open(p).unwrap()));
    let mut r = dec.read_info().unwrap();
    let mut buf = vec![0; r.output_buffer_size()];
    let info = r.next_frame(&mut buf).unwrap();
    let ch = info.color_type.samples();
    buf.truncate(info.buffer_size());
    (info.width as usize, info.height as usize, ch, buf)
}

fn cell_of(png: &(usize, usize, usize, Vec<u8>), x: usize, y: usize) -> Fr {
    let (pw, _, ch, buf) = png;
    Array3::from_shape_fn((H, W, 4), |(j, i, c)| buf[((y + j) * pw + x + i) * ch + c])
}

fn read_json(p: &Path) -> Value {
    beanfx::serde_json::from_str(&fs::read_to_string(p).unwrap()).unwrap()
}

fn centre(im: &Fr, axis: usize) -> f64 {
    let (h, w, _) = im.dim();
    let idx: Vec<usize> = if axis == 1 {
        (0..w).filter(|&x| (0..h).any(|y| im[[y, x, 3]] > 0)).collect()
    } else {
        (0..h).filter(|&y| (0..w).any(|x| im[[y, x, 3]] > 0)).collect()
    };
    idx.iter().sum::<usize>() as f64 / idx.len() as f64
}

fn lum(im: &Fr) -> f64 {
    let v: Vec<f64> = im.outer_iter().flat_map(|r| r.outer_iter().filter(|p| p[3] > 0).flat_map(|p| (0..3).map(|c| p[c] as f64).collect::<Vec<_>>()).collect::<Vec<_>>()).collect();
    v.iter().sum::<f64>() / v.len() as f64
}

fn dummy(f: usize, hits: &[Value]) -> Fr {
    tg::draw((64, 64), (32.0, 60.0), f as f64, hits, FPS, tg::Draw::default()).unwrap()
}

fn side_meta() -> Value {
    Value::Object(fc::meta("side", W as f64, H as f64, [20.0, 30.0], fc::Meta::default()).unwrap())
}

#[test]
fn sheet_json_lines_up() {
    let dir = common::tmpdir("ex_sheet");
    let (shot, light) = (shot(), light());
    let js = ex::write(&dir, "blast", &shot, FPS, [20.0, 30.0], false, Write {
        light: Some((&light).into()),
        color: Some((&shot).into()),
        states: vec![("grow".into(), [0, 3]), ("fade".into(), [4, 11])],
        hits: vec![hit(3, Hit { freeze: Some(0.12), shake: Some(2.0), ..Default::default() })],
        windup: 0.25,
        extra: Some(side_meta()),
        ..Default::default()
    }).unwrap();
    let m = &js["meta"];
    let b = &m["beanfx"];
    let img = read_png(&dir.join("blast.png"));
    assert_eq!((img.0 as i64, img.1 as i64), (m["size"]["w"].as_i64().unwrap(), m["size"]["h"].as_i64().unwrap()), "png size vs meta");
    let frames = js["frames"].as_array().unwrap();
    assert_eq!(frames.len(), N, "one entry per frame");
    assert!(frames.iter().all(|f| f["duration"] == json!((1000.0 / FPS).round() as i64)), "duration in ms");
    assert!(frames.iter().all(|f| f["frame"]["x"].as_u64().unwrap() as usize + W <= img.0
        && f["frame"]["y"].as_u64().unwrap() as usize + H <= img.1), "every rect inside the sheet");
    let f5 = &frames[5]["frame"];
    let cell = cell_of(&img, f5["x"].as_u64().unwrap() as usize, f5["y"].as_u64().unwrap() as usize);
    assert_eq!(cell, shot[5], "rect 5 holds frame 5");
    let tags: Vec<&str> = m["frameTags"].as_array().unwrap().iter().map(|t| t["name"].as_str().unwrap()).collect();
    assert_eq!(tags, ["grow", "fade"]);
    assert_eq!(b["act"]["hits"][0], json!({"frame": 3, "t": 0.125, "freeze": 0.12, "shake": 2, "push": 0, "react": "flinch"}), "hit {b:?}");
    assert_eq!(b["end"], "remove");
    assert!(b["act"]["windup"] == 0.25 && b["light"] == "blast_light.png" && b["blend_light"] == "add", "beanfx meta");
    assert!(b["mirror_pivot"] == json!([20, 30]) && b["columns"].as_u64().unwrap() as usize * W == img.0, "direction fields and columns");
    assert_eq!(read_json(&dir.join("blast.json")), js, "json on disk");
    assert_eq!(read_png(&dir.join("blast_light.png")).2, 3, "light sheet RGB for additive blend");
}

#[test]
fn heading_rows_tag_each_row() {
    let dir = common::tmpdir("ex_rows");
    let rows: Vec<Vec<Fr>> = (0..8).map(|k| (0..4).map(|_| disc(4.0, 20.0 + (k % 3) as f64, 16.0)).collect()).collect();
    let js8 = ex::write(&dir, "bolt", &rows, 12.0, [20.0, 16.0], true, Write {
        states: vec![("fly".into(), [0, 3])],
        ..Default::default()
    }).unwrap();
    let tags = js8["meta"]["frameTags"].as_array().unwrap();
    let names: Vec<&str> = tags.iter().map(|t| t["name"].as_str().unwrap()).collect();
    assert!(names[..2] == ["east", "east/fly"] && names.len() == 16, "heading tags {:?}", &names[..4]);
    let t = &tags[2];
    assert_eq!((t["name"].as_str().unwrap(), t["from"].as_i64().unwrap(), t["to"].as_i64().unwrap()), ("south-east", 4, 7));
}

#[test]
fn sheets_split_into_pages() {
    let dir = common::tmpdir("ex_pages");
    let (shot, light) = (shot(), light());
    // a 40 x 32 cell: 2 across, 3 down, 6 frames a page
    let jp = ex::write(&dir, "big", &shot, FPS, [20.0, 30.0], false, Write {
        light: Some((&light).into()),
        states: vec![("grow".into(), [0, 3]), ("fade".into(), [4, 11])],
        max_edge: Some(100),
        ..Default::default()
    }).unwrap();
    let pg = jp["meta"]["beanfx"]["pages"].as_array().unwrap();
    let first: Vec<i64> = pg.iter().map(|p| p["first"].as_i64().unwrap()).collect();
    assert!(pg.len() == 2 && first == [0, 6], "pages {pg:?}");
    let fr = jp["frames"].as_array().unwrap();
    assert!(fr.len() == N && fr[7]["page"] == 1 && fr[7]["frame"]["x"] == 40, "index frames carry their page and local rect");
    let p1 = read_json(&dir.join("big_p1.json"));
    assert!(p1["frames"].as_array().unwrap().len() == 6 && p1["frames"][0]["filename"] == "big 6", "page 1 holds frames 6 to 11");
    let t: Vec<(String, i64, i64)> = p1["meta"]["frameTags"].as_array().unwrap().iter()
        .map(|t| (t["name"].as_str().unwrap().to_string(), t["from"].as_i64().unwrap(), t["to"].as_i64().unwrap())).collect();
    assert_eq!(t, [("fade".to_string(), 0, 5)], "page tags clipped");
    let im1 = read_png(&dir.join("big_p1.png"));
    assert_eq!((im1.1, im1.0), (96, 80));
    assert_eq!(cell_of(&im1, 40, 32), shot[9], "page 1 pixels");
    assert!(dir.join("big_p0_light.png").exists() && !dir.join("big.png").exists(), "page files");
}

#[test]
fn act_with_poses_and_target() {
    let dir = common::tmpdir("ex_act");
    let shot = shot();
    let ja = ex::write(&dir, "slash", &shot, FPS, [20.0, 30.0], false, Write {
        hits: vec![hit(3, Hit { freeze: Some(0.1), shake: Some(2.0), push: Some(4.0), react: Some("knockback".into()), ..Default::default() })],
        poses: vec![ex::pose(-0.3, "windup", "smooth"), ex::pose(0.05, "release", "snap"), ex::pose(0.4, "recover", "smooth")],
        target: Some(json!({"x": 30, "react": "knockback"})),
        ..Default::default()
    }).unwrap();
    let a = &ja["meta"]["beanfx"]["act"];
    assert!(a["windup"] == 0.3 && a["poses"][1] == json!({"t": 0.05, "pose": "release", "how": "snap"}) && a["target"]["x"] == 30, "act {a:?}");
    assert_eq!(ex::check_act(a, N as i64, FPS, false).unwrap(), Vec::<String>::new(), "clean act flagged");
}

#[test]
fn check_finds_edge_empty_pop_and_colours() {
    let (shot, light) = (shot(), light());
    let clean = ex::check(&shot, Check { light: Some((&light).into()), ..Default::default() }).unwrap();
    assert!(clean.is_empty(), "clean one-shot flagged: {clean:?}");

    let mut pop = shot[..N - 1].to_vec();
    pop.push(d(9.0));
    assert!(has(&chk(&pop), "pop off"), "one-shot that pops off");
    assert!(ex::check(&pop, Check { hold: true, ..Default::default() }).unwrap().is_empty(), "a held ending is not a pop");

    let mut noisy = empty();
    for y in 2..H - 2 {
        for x in 2..W - 2 {
            noisy[[y, x, 3]] = 255;
            noisy[[y, x, 0]] = (((y - 2) * (W - 4) + (x - 2)) % 200) as u8;
        }
    }
    assert_eq!(ex::colours(&noisy), 200.min((H - 4) * (W - 4)), "colours counts distinct opaque colours");
    assert_eq!(ex::colours(&empty()), 0, "colours leaves out transparent pixels");
    let nv = vec![noisy];
    assert!(has(&ex::check(&nv, Check { max_colours: Some(32.0), ..Default::default() }).unwrap(), "colours, more than 32"));
    assert!(!has(&ex::check(&nv, Check { max_colours: None, ..Default::default() }).unwrap(), "colours"), "no colour limit, no colour line");

    let mut with_empty = shot[..N - 1].to_vec();
    with_empty.push(empty());
    assert!(has(&chk(&with_empty), "empty colour"), "empty frame");
    let mut edge = vec![disc(3.0, 1.0, 16.0)];
    edge.extend_from_slice(&shot[1..]);
    assert!(has(&chk(&edge), "colour touches the edge"), "colour on the edge");
    let mut hot = light.clone();
    for c in 0..3 {
        hot[2][[0, 10, c]] = 0.5;
    }
    assert!(has(&ex::check(&shot, Check { light: Some((&hot).into()), ..Default::default() }).unwrap(), "light touches the edge"), "light on the edge");
}

#[test]
fn framing_flags_a_drawing_parked_in_a_corner() {
    let shot = shot();
    let fr = ex::framing(&shot).unwrap().unwrap();
    assert!(fr.trim < 0.1 && (fr.w, fr.h) == (W as i64, H as i64), "a centred drawing has nothing to trim: {fr:?}");
    let corner: Vec<Fr> = [2.0, 4.0, 5.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.5, 1.2, 1.0, 0.8].iter().map(|&r| disc(r, 31.0, 24.0)).collect();
    let got: Vec<String> = chk(&corner).into_iter().filter(|p| p.starts_with("framing")).collect();
    assert!(got.len() == 1 && got[0].contains("off the left") && got[0].contains("off the top"), "a drawing in one corner is flagged: {got:?}");
    assert!(!ex::check(&corner, Check { trim: None, ..Default::default() }).unwrap().iter().any(|p| p.starts_with("framing")), "trim=None switches the framing check off");
    let mut stray = corner.clone();
    for (k, f) in stray.iter_mut().take(6).enumerate() {
        for c in 0..4 {
            f[[3 + k, 3 + 2 * k, c]] = 255; // one spark a frame crossing the empty side
        }
    }
    assert!(chk(&stray).iter().any(|p| p.starts_with("framing")), "a few pixels crossing the empty side do not hide it");
    assert!(ex::framing(&vec![empty()]).unwrap().is_none(), "framing of an empty sheet is None");
    let rows8: Vec<Vec<Fr>> = (0..8).map(|k| {
        let a = k as f64 * 0.785;
        vec![disc(4.0, 20.0 + 9.0 * a.cos(), 16.0 + 9.0 * a.sin()); 4]
    }).collect();
    assert!(ex::framing(&rows8).unwrap().unwrap().trim < 0.1, "heading rows are framed together, not one by one");
}

#[test]
fn budget_counts_decoded_texture_memory() {
    let big: Vec<Array3<u8>> = (0..70).map(|_| Array3::zeros((512, 512, 4))).collect();
    let (m1, m2) = (ex::memory_mb(&big, false), ex::memory_mb(&big, true));
    assert!((m1 - 73.4).abs() < 0.1 && (m2 - 146.8).abs() < 0.1, "memory is frames x w x h x 4, twice with light: {m1:.1}, {m2:.1}");
    drop(big);
    let mut a = Array3::<u8>::zeros((512, 512, 4));
    for y in 200..300 {
        for x in 200..300 {
            for c in 0..4 {
                a[[y, x, c]] = 255;
            }
        }
    }
    let over: Vec<Fr> = (0..70).map(|_| a.clone()).collect();
    let lit: Vec<Array3<u8>> = (0..70).map(|_| Array3::zeros((512, 512, 3))).collect();
    let run = |light: bool, max_mb: Option<f64>| {
        let o = Check { hold: true, max_mb, light: light.then(|| (&lit).into()), ..Default::default() };
        ex::check(&over, o).unwrap().iter().any(|p| p.starts_with("budget"))
    };
    assert!(run(true, Some(ex::BUDGET_MB)), "sheets over the budget are flagged");
    assert!(!run(false, Some(ex::BUDGET_MB)), "the same frames without a light sheet fit");
    assert!(!run(true, None), "max_mb=None lifts the budget");
    assert!(!run(true, Some(200.0)), "a higher max_mb lifts it too");
}

#[test]
#[allow(clippy::approx_constant)] // 6.283 as in the Python test
fn loop_seam() {
    let smooth: Vec<Fr> = (0..10).map(|k| {
        let t = k as f64 / 10.0 * 6.283;
        disc(4.0, 20.0 + 6.0 * t.cos(), 16.0 + 6.0 * t.sin())
    }).collect();
    let o = || Check { looped: true, ..Default::default() };
    let p = ex::check(&smooth, o()).unwrap();
    assert!(!has(&p, "seam"), "seamless loop flagged: {p:?}");
    let jump: Vec<Fr> = (0..10).map(|k| disc(4.0, 8.0 + 2.4 * k as f64, 16.0)).collect();
    assert!(has(&ex::check(&jump, o()).unwrap(), "seam"), "loop seam missed");
}

#[test]
fn act_problems_and_seeds() {
    let bad_act = ex::act(
        &[hit(40, Hit { freeze: Some(0.5), react: Some("explode".into()), ..Default::default() })], 0.0,
        &[ex::pose(0.2, "windup", "smooth"), ex::pose(0.1, "dance", "smooth")], None).unwrap();
    let got = ex::check_act(&bad_act, N as i64, FPS, false).unwrap();
    let joined = got.join(" ");
    let n = ["outside", "stall", "react", "'dance'", "out of order", "no release"].iter().filter(|x| joined.contains(**x)).count();
    assert_eq!(n, 6, "act problems {got:?}");

    assert!(ex::check_seeds(|_, _| d(4.0), N, &[2, 3, 7], 2).unwrap().is_empty(), "steady render flagged");
    let got = ex::check_seeds(|_, sd| disc(4.0, if sd == 7 { 1.0 } else { 20.0 }, 16.0), N, &[2, 3, 7], 3).unwrap();
    assert!(got.len() == 4 && got.iter().all(|x| x.starts_with("seed 7")), "seed check {got:?}");
}

#[test]
fn hitstop_holds_and_shakes() {
    let shot = shot();
    let hs = ex::hitstop(&shot, &[hit(3, Hit { freeze: Some(0.125), shake: Some(2.0), ..Default::default() })], FPS).unwrap();
    assert!(hs.len() == N + 3 && hs[3] == shot[3] && hs[4] != shot[3] && hs[7] == shot[4], "hitstop holds and shakes");

    // the preview shake follows the blow: a downward blow shakes rows, not columns, and lasts shake_time
    let down = ex::hitstop(&shot, &[hit(3, Hit { freeze: Some(0.0), shake: Some(2.0), dir: Some(90.0), shake_time: Some(0.125), ..Default::default() })], FPS).unwrap();
    assert_eq!(down.len(), N, "no freeze adds no frames");
    let moved: Vec<usize> = (0..N).filter(|&i| down[i] != shot[i]).collect();
    assert!(!moved.is_empty(), "shake moves frames");
    assert!(moved.iter().all(|&i| centre(&down[i], 1) == centre(&shot[i], 1) && centre(&down[i], 0) != centre(&shot[i], 0)), "a 90 degree blow shakes up and down");
    assert!(moved.len() >= 2, "shake_time carries the shake past the contact frame: {moved:?}");
}

#[test]
fn target_dummy_reacts() {
    let hits = [hit(5, Hit { push: Some(6.0), react: Some("knockback".into()), ..Default::default() })];
    let (d0, d5, d9) = (dummy(0, &hits), dummy(5, &hits), dummy(9, &hits));
    let any_alpha = d0.outer_iter().any(|r| r.outer_iter().any(|p| p[3] > 0));
    assert!(any_alpha && d0 == dummy(4, &hits), "dummy still before the hit");
    assert!(lum(&d5) > lum(&d0) + 30.0, "flash on contact");
    let (x0, x9) = (centre_mean(&d0, 1), centre_mean(&d9, 1));
    assert!(x9 > x0 + 2.0, "knockback pushes right: {x0:.1} to {x9:.1}");
    assert_eq!(tg::under(&d(3.0), &empty()).dim(), (H, W, 4), "under");

    // the dummy flashes for the hit's flash time and a rising blow lifts it
    let fl = [hit(5, Hit { flash: Some(0.125), push: Some(6.0), react: Some("knockback".into()), ..Default::default() })];
    let base = lum(&dummy(0, &fl));
    let lit: Vec<bool> = (5..11).map(|f| lum(&dummy(f, &fl)) > base + 30.0).collect();
    assert_eq!(lit, [true, true, true, true, false, false], "flash lasts 3 frames, then a half frame");
    let up = [hit(5, Hit { push: Some(6.0), react: Some("knockback".into()), dir: Some(-60.0), ..Default::default() })];
    assert!(centre_mean(&dummy(9, &up), 0) < centre_mean(&dummy(0, &up), 0) - 1.0, "a rising blow lifts");
}

/// Mean of the x (axis 1) or y (axis 0) index over every opaque pixel.
fn centre_mean(im: &Fr, axis: usize) -> f64 {
    let mut v = vec![];
    for ((y, x, c), &a) in im.indexed_iter() {
        if c == 3 && a > 0 {
            v.push(if axis == 1 { x } else { y } as f64);
        }
    }
    v.iter().sum::<f64>() / v.len() as f64
}

#[test]
fn weights_fill_the_hit() {
    let hv = hit(6, Hit { weight: Some("heavy".into()), dir: Some(30.0), ..Default::default() });
    let w = ex::weight("heavy").unwrap();
    assert!(hv["freeze"] == w.freeze && hv["react"] == "knockback" && hv["sound"] == "hit_heavy" && hv["dir"] == 30
        && hv["flash"] == w.flash && hv["weight"] == "heavy", "heavy {hv:?}");
    assert_eq!(hit(6, Hit { weight: Some("heavy".into()), push: Some(9.0), sound: Some("clang".into()), ..Default::default() })["push"], 9, "explicit push beats the preset");
    assert_eq!(hit(6, Hit { weight: Some("heavy".into()), sound: Some("clang".into()), ..Default::default() })["sound"], "clang", "explicit sound");
    let old = hit(6, Hit::default());
    let mut keys: Vec<&str> = old.as_object().unwrap().keys().map(String::as_str).collect();
    keys.sort();
    assert!(keys == ["frame", "freeze", "push", "react", "shake", "t"] && old["freeze"] == 0.1, "no weight keeps the old hit {old:?}");
    let order: Vec<_> = ["light", "heavy", "finisher"].iter().map(|k| ex::weight(k).unwrap()).collect();
    for p in order.windows(2) {
        let (a, b) = (p[0], p[1]);
        for (k, x, y) in [("freeze", a.freeze, b.freeze), ("shake", a.shake as f64, b.shake as f64), ("push", a.push as f64, b.push as f64),
                          ("flash", a.flash, b.flash), ("shake_time", a.shake_time, b.shake_time)] {
            assert!(x < y, "{} is not heavier than {}: {k}", b.name, a.name);
        }
    }
    for w in ex::WEIGHTS {
        let a = ex::act(&[hit(3, Hit { weight: Some(w.name.into()), ..Default::default() })], 0.0, &[], None).unwrap();
        assert!(ex::check_act(&a, N as i64, FPS, false).unwrap().is_empty(), "preset {} passes check_act", w.name);
    }
    let mut h = hit(3, Hit::default());
    let o = h.as_object_mut().unwrap();
    o.insert("weight".into(), json!("huge"));
    o.insert("flash".into(), json!(0.4));
    o.insert("shake_time".into(), json!(0.9));
    let a = ex::act(&[h], 0.0, &[], None).unwrap();
    let bad = ex::check_act(&a, N as i64, FPS, false).unwrap();
    assert_eq!(bad.len(), 3, "check_act flags weight, flash and shake time: {bad:?}");
}

#[test]
fn src_scan_flags_unseeded_randomness() {
    let dir = common::tmpdir("ex_src");
    let shot = shot();
    let src = dir.join("draft.py");
    fs::write(&src, "import numpy as np\nrng = np.random.default_rng(3)\nx = rng.random(4)\n").unwrap();
    let run = || ex::check(&shot, Check { src: Some(src.clone()), ..Default::default() }).unwrap();
    assert!(run().is_empty(), "seeded draft flagged");
    fs::write(&src, "import numpy as np\nx = np.random.rand(4)\nimport random\n").unwrap();
    let got: Vec<String> = run().into_iter().filter(|p| p.contains("unseeded")).collect();
    assert!(got.len() == 2 && got[0].contains("draft.py:2"), "unseeded {got:?}");
}

#[test]
fn extra_cannot_change_the_layout() {
    let dir = common::tmpdir("ex_clash");
    let r = ex::write(&dir, "clash", &shot(), FPS, [20.0, 30.0], false, Write { extra: Some(json!({"rows": "text"})), ..Default::default() });
    assert!(r.is_err(), "extra overwriting rows raises");
}

#[test]
fn preview_page_embeds_result_and_caster() {
    let root = common::tmpdir("ex_page");
    let out = root.join("drafts/demo/out");
    let rig = json!({"name": "hero", "view": "top-down", "fps": 10, "directions": ["east"],
        "anims": {"attack1": {"frame": [8, 8], "frames": 1, "sheets": {"east": "a1_east.png"}},
                  "kick": {"frame": [8, 8], "frames": 1, "sheets": {"east": "kick_east.png"}}}});
    let cd = root.join("casters/hero");
    fs::create_dir_all(&cd).unwrap();
    fs::write(cd.join("rig.json"), rig.to_string()).unwrap();
    for n in ["a1_east.png", "kick_east.png"] {
        let f = fs::File::create(cd.join(n)).unwrap();
        let mut e = png::Encoder::new(f, 8, 8);
        e.set_color(png::ColorType::Rgba);
        e.set_depth(png::BitDepth::Eight);
        e.write_header().unwrap().write_image_data(&[0u8; 8 * 8 * 4]).unwrap();
    }
    let (shot, light) = (shot(), light());
    ex::write(out.join("sheets"), "blast", &shot, FPS, [20.0, 30.0], false, Write {
        light: Some((&light).into()),
        color: Some((&shot).into()),
        extra: Some(json!({"caster": {"rig": "hero", "chain": [{"anim": "attack1"}]}})),
        ..Default::default()
    }).unwrap();
    let tpl = root.join("preview.html");
    fs::write(&tpl, r#"<html><body><script type="module">boot()</script></body></html>"#).unwrap();
    let pg = ex::page(out.join("sheets/blast.json"), ex::Page { template: Some(tpl), ..Default::default() }).unwrap().unwrap();
    assert_eq!(fs::canonicalize(&pg).unwrap(), fs::canonicalize(out.join("blast.html")).unwrap(), "page lands in out/: {pg:?}");
    let text = fs::read_to_string(&pg).unwrap();
    assert!(text.find("BEANFX_EMBED").unwrap() < text.find(r#"<script type="module">"#).unwrap(), "page: the embed comes before the app");
    let raw = text.split("window.BEANFX_EMBED = ").nth(1).unwrap().split(";</script>").next().unwrap();
    let emb: Value = beanfx::serde_json::from_str(raw).unwrap();
    let mut files: Vec<&str> = emb["files"].as_object().unwrap().keys().map(String::as_str).collect();
    files.sort();
    let mut want = ["drafts/demo/out/sheets/blast.json", "drafts/demo/out/sheets/blast.png", "drafts/demo/out/sheets/blast_light.png",
        "drafts/demo/out/sheets/blast_color.png", "casters/hero/rig.json", "casters/hero/a1_east.png"];
    want.sort();
    assert_eq!(files, want, "page files");
    assert_eq!(emb["select"], "fx:drafts/demo/out/sheets/blast.json");
}
