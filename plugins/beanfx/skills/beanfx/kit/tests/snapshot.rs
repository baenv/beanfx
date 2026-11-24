//! Before/after tests for the draft runner: every file a run writes, hashed, against the hashes the kit wrote
//! before the change (tests/fixtures/snapshots/<case>.txt).
//!
//! - A change that should not alter output (speed, refactor) must pass unchanged.
//! - A change that alters output on purpose re-blesses: `BEANFX_BLESS=1 cargo test --test snapshot`, and the commit
//!   says which files changed and why.
//! - A new feature adds a case, blessed on the commit that brings it.
//!
//! The `calm` and `busy` cases were blessed on kit 2.2.0, before the parallel runner and the 1x gif indexing, so
//! they prove those two changes left every byte as it was. `variants`, `particles` and `marks` were blessed on 2.3.0.

use beanfx::dr::{self, hash01, hex, Canvas, Effect, Layer, Spec};
use beanfx::ex;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

/// BEANFX_THREADS is process-wide: the runs in this file take turns.
static ENV: Mutex<()> = Mutex::new(());

/// Few colours (the gif's exact palette path), a hit with hit-stop and the preview dummy.
struct Calm;

impl Effect for Calm {
    fn spec(&self) -> Spec {
        let mut sp = Spec::new("calm", 48, 48, 16, 12.0);
        sp.pivot = [24.0, 40.0];
        sp.light_ramp = vec!["#5a2008".into(), "#ff8a30".into(), "#ffe0a0".into(), "#ffffff".into()];
        sp.hits = vec![ex::hit(6, 12.0, ex::Hit { shake: Some(2.0), ..Default::default() })];
        sp.dummy = Some([40.0, 40.0]);
        sp.trim = None;
        sp
    }

    fn draw(&self, cv: &mut Canvas, f: usize, seed: u64, layer: Layer) -> Result<(), String> {
        if layer != Layer::Effect {
            return Ok(());
        }
        let t = f as f64 / 15.0;
        let fade = 1.0 - dr::span(f as f64, 9.0, 15.0);
        let r = (3.0 + 12.0 * dr::ease_out(dr::span(f as f64, 0.0, 6.0))) * fade;
        cv.ellipse(24.0, 26.0, r, r * 0.8, hex("#ff9a30"), 0.9 * fade);
        cv.ellipse(23.0, 25.0, r * 0.5, r * 0.4, hex("#fff4c0"), fade);
        for i in 0..6u64 {
            let a = std::f64::consts::TAU * (i as f64 + hash01(seed, i)) / 6.0;
            let d = 4.0 + 16.0 * t;
            cv.line([24.0, 26.0], [24.0 + d * a.cos(), 26.0 + d * a.sin()], hex("#ffd060"), fade);
        }
        cv.glow(24.0, 26.0, r + 3.0, 0.3 * fade);
        Ok(())
    }
}

/// Many overlapping translucent dots and glows: frames past 256 colours (the gif's median-cut path), edge fade.
struct Busy;

impl Effect for Busy {
    fn spec(&self) -> Spec {
        let mut sp = Spec::new("busy", 64, 64, 20, 24.0);
        sp.light_ramp = vec!["#10204a".into(), "#40a0ff".into(), "#c0f0ff".into(), "#ffffff".into()];
        sp.edge_fade = 6.0;
        sp.glow = "strong".into();
        sp
    }

    fn draw(&self, cv: &mut Canvas, f: usize, seed: u64, layer: Layer) -> Result<(), String> {
        if layer != Layer::Effect {
            return Ok(());
        }
        let t = f as f64 / 19.0;
        let k = 1.0 - t * t;
        for i in 0..160u64 {
            let a = std::f64::consts::TAU * hash01(seed, i) + 2.0 * t;
            let d = 4.0 + 22.0 * hash01(seed, i + 500) * (0.3 + t);
            let (x, y) = (32.0 + d * a.cos(), 32.0 + d * a.sin());
            let c = [0.2 + 0.6 * hash01(seed, i + 900), 0.5 + 0.5 * hash01(seed, i + 1300), 1.0];
            cv.ellipse(x, y, 1.6, 1.6, c, 0.35 + 0.4 * k);
            cv.glow(x, y, 5.0, 0.04 * k);
        }
        Ok(())
    }
}

/// Calm with palette variants: an identity one and a real one.
struct Variants;

impl Effect for Variants {
    fn spec(&self) -> Spec {
        let mut sp = Calm.spec();
        sp.name = "variants".into();
        sp.ramp = vec!["#ff9a30".into(), "#ffd060".into(), "#fff4c0".into()];
        sp.variants = vec![
            dr::Variant::new("same", &["#ff9a30", "#ffd060", "#fff4c0"], &["#5a2008", "#ff8a30", "#ffe0a0", "#ffffff"]),
            dr::Variant::new("frost", &["#2a7ae0", "#80c8ff", "#e0f8ff"], &["#10204a", "#40a0ff", "#c0f0ff", "#ffffff"]),
        ];
        sp
    }

    fn draw(&self, cv: &mut Canvas, f: usize, seed: u64, layer: Layer) -> Result<(), String> {
        Calm.draw(cv, f, seed, layer)
    }
}

/// The mo particles: a burst that cools into smoke and sparks that bounce.
struct Particles;

impl Effect for Particles {
    fn spec(&self) -> Spec {
        let mut sp = Spec::new("particles", 64, 64, 24, 24.0);
        sp.pivot = [32.0, 52.0];
        sp.light_ramp = vec!["#5a2008".into(), "#ff8a30".into(), "#ffe0a0".into(), "#ffffff".into()];
        sp.trim = None;
        sp
    }

    fn draw(&self, cv: &mut Canvas, f: usize, seed: u64, layer: Layer) -> Result<(), String> {
        if layer != Layer::Effect {
            return Ok(());
        }
        use beanfx::mo;
        let t = f as f64 / 24.0;
        let fire = dr::ramp(&["#3a1020", "#8a2a18", "#d0501c", "#f09030", "#ffd060", "#fff4d0"]);
        let smoke = dr::ramp(&["#2a2430", "#4a4250", "#6e6676", "#9a92a0"]);
        mo::burst(cv, seed, [32.0, 40.0], t, &fire, &smoke, &mo::Burst { n: 14, life: (0.5, 0.9), ..Default::default() });
        for i in 0..10u64 {
            let a = -std::f64::consts::PI * (0.2 + 0.6 * hash01(seed + 1, i));
            let s = 40.0 + 40.0 * hash01(seed + 2, i);
            let (p, v, _) = mo::fly_ground([32.0, 40.0], [s * a.cos(), s * a.sin()], 300.0, 2.0, t, mo::Ground { y: 52.0, ..Default::default() });
            let k = 1.0 - (t / 0.9).min(1.0);
            if k > 0.0 {
                mo::spark(cv, p, v, 3.0, 4.0, fire[5], fire[3], k, 0.1 * k);
            }
        }
        Ok(())
    }
}

/// The parts that leave a mark and dress a body: scorch, brands, debris with dust, crystals with a glint, a
/// tilted ring split round a body, frost growing on it.
struct Marks;

impl Effect for Marks {
    fn spec(&self) -> Spec {
        let mut sp = Spec::new("marks", 128, 64, 30, 24.0);
        sp.pivot = [40.0, 52.0];
        sp.light_ramp = vec!["#5a2008".into(), "#ff8a30".into(), "#ffe0a0".into(), "#ffffff".into()];
        sp.hold = true;
        sp.trim = None;
        sp
    }

    fn draw(&self, cv: &mut Canvas, f: usize, seed: u64, layer: Layer) -> Result<(), String> {
        if layer != Layer::Effect {
            return Ok(());
        }
        use beanfx::{mo, pt};
        let t = f as f64 / 24.0;
        let fire = dr::ramp(&["#3a1020", "#8a2a18", "#d0501c", "#f09030", "#ffd060", "#fff4d0"]);
        let smoke = dr::ramp(&["#2a2430", "#4a4250", "#6e6676", "#9a92a0"]);
        let g = mo::Ground { y: 52.0, ..Default::default() };
        mo::scorch(cv, seed, [40.0, 52.5], 14.0, 3.5, t / 1.0, &fire, hex("#1a1418"));
        let rock = [hex("#1a1418"), hex("#4a3a3a"), hex("#7a6458"), hex("#a89080")];
        mo::chunks(cv, seed + 3, [40.0, 50.0], t, rock, &smoke, &mo::Chunks { ground: g, speed: (40.0, 90.0), ..Default::default() });
        mo::brands(cv, seed + 5, [40.0, 46.0], t, &fire, &mo::Brands { ground: mo::Ground { bounce: 0.2, ..g }, speed: (50.0, 80.0), ..Default::default() });
        let ice = [hex("#1a2050"), hex("#3a6ab0"), hex("#8ad0ff"), hex("#ffffff")];
        let gl = (t * 1.5).fract() * 1.4;
        pt::crystal(cv, [70.0, 52.0], 14.0, 6.0, 1.5, ice, (gl <= 1.0).then_some(gl), 1.0);
        pt::ring(cv, [100.0, 50.0], 12.0, 2.0, 0.35, pt::Half::Far, hex("#2a4a90"), hex("#8ad0ff"), 0.9);
        pt::ring_glow(cv, [100.0, 50.0], 12.0, 0.35, 3.0, 0.15, pt::Half::Far);
        let mut b = Canvas::new(128, 64);
        b.ellipse(100.0, 40.0, 5.0, 9.0, hex("#6a5a80"), 1.0);
        b.ellipse(100.0, 28.0, 4.0, 4.0, hex("#8a7aa0"), 1.0);
        let body = b.cel().col;
        cv.over_img(&body);
        pt::frost(cv, seed, &body, t.min(1.0), [hex("#3a6ab0"), hex("#8ad0ff"), hex("#ffffff")], Default::default());
        pt::ring(cv, [100.0, 50.0], 12.0, 2.0, 0.35, pt::Half::Near, hex("#2a4a90"), hex("#8ad0ff"), 0.9);
        pt::ring_glow(cv, [100.0, 50.0], 12.0, 0.35, 3.0, 0.15, pt::Half::Near);
        Ok(())
    }
}

/// FNV-1a 64 of a file's bytes, as hex.
fn hash(path: &Path) -> String {
    let mut h = 0xcbf29ce484222325u64;
    for b in std::fs::read(path).unwrap() {
        h = (h ^ b as u64).wrapping_mul(0x100000001b3);
    }
    format!("{h:016x}")
}

/// Every file under out/ but the preview page (it embeds the skill's preview.html), relative path to hash.
fn hashes(out: &Path) -> BTreeMap<String, String> {
    fn walk(base: &Path, d: &Path, m: &mut BTreeMap<String, String>) {
        for e in std::fs::read_dir(d).unwrap() {
            let p = e.unwrap().path();
            if p.is_dir() {
                walk(base, &p, m);
            } else if p.extension().map_or(true, |x| x != "html") {
                m.insert(p.strip_prefix(base).unwrap().to_string_lossy().replace('\\', "/"), hash(&p));
            }
        }
    }
    let mut m = BTreeMap::new();
    walk(out, out, &mut m);
    m
}

/// Runs the effect in a fresh draft folder at the given thread count; the out/ folder and the exit code.
fn run(fx: &(dyn Effect + Sync), tag: &str, threads: &str) -> (PathBuf, u8) {
    let dir = std::env::temp_dir().join(format!("beanfx_snap_{tag}_{threads}_{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(dir.join("src")).unwrap();
    std::fs::write(dir.join("src").join("main.rs"), "// snapshot case\n").unwrap();
    std::env::set_var("BEANFX_THREADS", threads);
    std::env::set_var("BEANFX_SKILL", dir.join("no_skill")); // no preview page: it is not hashed anyway
    let code = dr::run(fx, &dir, &[]).unwrap();
    std::env::remove_var("BEANFX_THREADS");
    (dir.join("out"), code)
}

fn snapshot_file(case: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/snapshots").join(format!("{case}.txt"))
}

/// The files of `got` against the blessed hashes of `case`; BEANFX_BLESS=1 writes them instead.
fn compare(case: &str, got: &BTreeMap<String, String>) {
    let path = snapshot_file(case);
    let text: String = got.iter().map(|(k, v)| format!("{v} {k}\n")).collect();
    if std::env::var("BEANFX_BLESS").is_ok_and(|v| v == "1") {
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, text).unwrap();
        return;
    }
    let want = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("{}: {e}; bless it with BEANFX_BLESS=1 on the commit that adds the case", path.display()));
    let want: BTreeMap<String, String> =
        want.lines().filter_map(|l| l.split_once(' ')).map(|(h, f)| (f.to_string(), h.to_string())).collect();
    let mut diff = vec![];
    for f in want.keys().chain(got.keys()).collect::<std::collections::BTreeSet<_>>() {
        match (want.get(f), got.get(f)) {
            (Some(a), Some(b)) if a == b => {}
            (Some(_), Some(_)) => diff.push(format!("changed {f}")),
            (Some(_), None) => diff.push(format!("missing {f}")),
            (None, _) => diff.push(format!("new {f}")),
        }
    }
    assert!(diff.is_empty(), "{case}: output differs from before the change:\n  {}\nre-bless with BEANFX_BLESS=1 only when \
        the change is meant to alter output, and say why in the commit", diff.join("\n  "));
}

/// The case at 1 thread (the order the kit drew in before the parallel runner) and at 4 threads: the two runs
/// write the same bytes, and those match the blessed snapshot.
fn case(fx: &(dyn Effect + Sync), name: &str) -> BTreeMap<String, String> {
    let _g = ENV.lock().unwrap_or_else(|e| e.into_inner());
    let (serial, c1) = run(fx, name, "1");
    let (parallel, c4) = run(fx, name, "4");
    let (a, b) = (hashes(&serial), hashes(&parallel));
    assert_eq!(c1, c4, "{name}: exit code at 1 and 4 threads");
    assert!(!a.is_empty(), "{name}: wrote files");
    assert_eq!(a, b, "{name}: 1 thread and 4 threads write the same bytes");
    compare(name, &b);
    b
}

#[test]
fn calm_runner_output_is_unchanged() {
    case(&Calm, "calm");
}

#[test]
fn busy_runner_output_is_unchanged() {
    let got = case(&Busy, "busy");
    assert!(got.contains_key("busy.gif"));
}

#[test]
fn variants_leave_the_sheet_alone_and_an_identity_variant_matches_it() {
    let got = case(&Variants, "variants");
    // before/after: the same effect with no variants (Calm) writes the same sheet images
    let calm = std::fs::read_to_string(snapshot_file("calm")).unwrap();
    let calm: BTreeMap<&str, &str> = calm.lines().filter_map(|l| l.split_once(' ')).map(|(h, f)| (f, h)).collect();
    for (a, b) in [("sheets/calm.png", "sheets/variants.png"), ("sheets/calm_color.png", "sheets/variants_color.png"),
                   ("sheets/calm_light.png", "sheets/variants_light.png"), ("calm_1x.png", "variants_1x.png"),
                   ("calm.gif", "variants.gif")] {
        assert_eq!(calm.get(a).copied(), got.get(b).map(String::as_str), "{b} matches {a} written without variants");
    }
    // an identity variant is the sheet itself
    for (a, b) in [("sheets/variants.png", "sheets/variants_same.png"), ("sheets/variants_color.png", "sheets/variants_same_color.png"),
                   ("sheets/variants_light.png", "sheets/variants_same_light.png"), ("variants_1x.png", "variants_same_1x.png")] {
        assert_eq!(got.get(a), got.get(b), "{b} equals {a}");
    }
    assert_ne!(got.get("sheets/variants.png"), got.get("sheets/variants_frost.png"), "frost recolours");
}

#[test]
fn particles_runner_output_is_unchanged() {
    case(&Particles, "particles");
}

#[test]
fn marks_runner_output_is_unchanged() {
    case(&Marks, "marks");
}

/// Mostly grey smoke with a little of the ramp, and a variant: the smoke keeps its colour on purpose.
struct Smoky;

impl Effect for Smoky {
    fn spec(&self) -> Spec {
        let mut sp = Spec::new("smoky", 32, 32, 8, 12.0);
        sp.looped = true;
        sp.ramp = vec!["#ff9a30".into(), "#fff4c0".into()];
        sp.variants = vec![dr::Variant::new("frost", &["#2a7ae0", "#e0f8ff"], &["#10204a", "#40a0ff", "#c0f0ff", "#ffffff"])];
        sp
    }

    fn draw(&self, cv: &mut Canvas, f: usize, _seed: u64, layer: Layer) -> Result<(), String> {
        if layer == Layer::Effect {
            let r = 8.0 + (f as f64 * 0.785).sin();
            cv.ellipse(16.0, 16.0, r, r, hex("#6e6676"), 1.0);
            cv.ellipse(16.0, 16.0, 2.0, 2.0, hex("#fff4c0"), 1.0);
        }
        Ok(())
    }
}

#[test]
fn a_smoky_variant_is_a_note_not_a_failure() {
    // before the fix the run failed (exit 1) on "most of the colour is off Spec.ramp"; smoke stays grey by design
    let _g = ENV.lock().unwrap_or_else(|e| e.into_inner());
    let (out, code) = run(&Smoky, "smoky", "4");
    assert_eq!(code, 0, "a variant that leaves smoke grey passes");
    assert!(out.join("sheets").join("smoky_frost.png").exists(), "the variant is still written");
}

/// A halo of three dots behind a caster, a dot in front, and two parts: a crop of the sheet (the default
/// `Effect::part`) and a travel loop with its own clock. `split` false draws the halo in `Effect` instead, as a
/// draft did before `Layer::Behind` existed.
struct Halo {
    split: bool,
}

impl Halo {
    fn halo(cv: &mut Canvas, f: usize) {
        for i in 0..3 {
            let a = std::f64::consts::TAU * (i as f64 / 3.0 + f as f64 / 12.0);
            cv.ellipse(16.0 + 7.0 * a.cos(), 12.0 + 7.0 * a.sin(), 2.0, 2.0, hex("#ffc93c"), 1.0);
            cv.glow(16.0 + 7.0 * a.cos(), 12.0 + 7.0 * a.sin(), 3.0, 0.3);
        }
    }
}

impl Effect for Halo {
    fn spec(&self) -> Spec {
        let mut sp = Spec::new("halo", 40, 32, 12, 12.0);
        sp.pivot = [16.0, 28.0];
        sp.caster_foot = Some([16.0, 28.0]);
        sp.trim = None;
        sp.light_ramp = vec!["#5a1a08".into(), "#f07a1e".into(), "#ffd070".into(), "#ffffff".into()];
        let mut travel = dr::Part::new("travel", 4, 12, 8, [0.0, 0.0], [6.0, 4.0], "travel");
        travel.looped = true;
        travel.more = beanfx::serde_json::json!({"speed": 120});
        sp.parts = vec![dr::Part::new("cast", 12, 24, 24, [4.0, 0.0], [12.0, 28.0], "caster"), travel];
        sp
    }

    fn draw(&self, cv: &mut Canvas, f: usize, _seed: u64, layer: Layer) -> Result<(), String> {
        let fade = 1.0 - 0.9 * dr::span(f as f64, 6.0, 11.0);
        match layer {
            Layer::Behind if self.split => Halo::halo(cv, f),
            Layer::Effect => {
                if !self.split {
                    Halo::halo(cv, f);
                }
                cv.ellipse(30.0, 20.0, 2.0 * fade, 2.0 * fade, hex("#fff6d8"), 1.0);
            }
            Layer::Caster => cv.ellipse(16.0, 20.0, 3.0, 8.0, hex("#404050"), 1.0),
            _ => {}
        }
        Ok(())
    }

    fn part(&self, cv: &mut Canvas, key: &str, f: usize, seed: u64) -> Result<(), String> {
        if key != "travel" {
            // the cast part: the default crop of the sheet
            self.draw(cv, f, seed, Layer::Behind)?;
            return self.draw(cv, f, seed, Layer::Effect);
        }
        let r = 2.0 + 0.5 * (std::f64::consts::TAU * f as f64 / 4.0).sin();
        cv.ellipse(6.0, 4.0, r, r, hex("#ffc93c"), 1.0);
        cv.line([0.0, 4.0], [4.0, 4.0], hex("#f07a1e"), 0.8);
        Ok(())
    }
}

#[test]
fn behind_layer_ships_in_the_sheet_and_parts_are_written() {
    let got = case(&Halo { split: true }, "halo");
    for f in ["sheets/halo_cast.png", "sheets/halo_travel.json"] {
        assert!(got.contains_key(f), "missing {f}: {:?}", got.keys().collect::<Vec<_>>());
    }
    // before Layer::Behind the halo was drawn in Effect: the sheet is the same bytes, only the previews change
    let _g = ENV.lock().unwrap_or_else(|e| e.into_inner());
    let (old, _) = run(&Halo { split: false }, "halo_old", "1");
    let before = hashes(&old);
    for f in ["sheets/halo.png", "sheets/halo_color.png", "sheets/halo_light.png", "halo_1x.png", "sheets/halo_cast.png"] {
        assert_eq!(got.get(f), before.get(f), "{f}: Behind + Effect is the sheet the single layer drew");
    }
    assert_ne!(got.get("halo_4x_dark.png"), before.get("halo_4x_dark.png"), "the preview puts the halo behind the caster");
    let js: beanfx::serde_json::Value =
        beanfx::serde_json::from_str(&std::fs::read_to_string(old.join("sheets/halo.json")).unwrap()).unwrap();
    let parts = &js["meta"]["beanfx"]["parts"];
    assert_eq!(parts["cast"]["anchor"], "caster", "{parts}");
    assert_eq!(parts["travel"]["speed"], 120, "{parts}");
    assert_eq!(parts["travel"]["json"], "halo_travel.json", "{parts}");
}
