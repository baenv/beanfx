# beanfx crate API

The kit is a Rust library (`beanfx`, src/lib.rs) plus the `beanfx` binary (src/main.rs: `version`, `gate`). A draft
depends on the crate (`beanfx = { path = "kit" }`) and calls it directly. `cargo test --locked` in this folder runs
the unit and integration tests. Writing a draft: DRAFTS.md.

## Modules

| Module | What it holds |
|---|---|
| `np` | numeric helpers: linspace, arange, mgrid, round half to even, clip, where, median, quantile, interp, roll, pad, gradient, pairwise sum and mean |
| `rng` | the seeded generator (`default_rng(seed)`: uniform, random, integers, choice, normal, beta, shuffle, permutation) |
| `img` | PNG read and write, BOX resize, `zoom(a, k)` (nearest, k times), `tile(cells, cols)` (rows of cells) |
| `color` | hex colours |
| `ex` (+ `ex::page`) | export: write, check, check_seeds, act, hit, pose, framing, grid, hitstop, preview page |
| `fc` | facing: views, heading rows, mirror, the direction fields of the JSON, cast, travel and impact parts |
| `sfx` | sound from the effect's JSON: write, check, volley, layers, render, track, save |
| `pfx` | writers and layers: strip, gif, contact, takes, load, tint, gain, keep, bands, paint, composite |
| `fl` | shade-map helpers: ramp, grids, Pen, stroke, noise, outline, ground ring, impact frames |
| `lt` | additive light: glow, glow_line, glow_ring, steps, bands, Flashes, flash_at, flicker, glow levels |
| `fk` | shapes: lumpy, ball, puffs, streaks, facets, kite, leaf, twinkle, claws, hit_burst, ground_impact |
| `cs` | the mockup caster and avatar |
| `tg` | the preview target dummy |
| `rig` | a game character as the caster (`rig::load(name, None)`) |
| `rf` | an object traced from a reference image (`rf::trace`, `rf::paint`) |
| `dv` | points taken from a finished drawing (outline, simplify, spine, scatter, local, world) |
| `dr` | the draft runner: `Spec`, `Effect`, `Canvas`, `dr::main` (previews, sheet, JSON, page, checks, `look`, `glow`, `bench`) |

A draft on the runner starts with `use beanfx::dr::{self, Canvas, Effect, Layer, Spec};`; the lower modules are for
shapes the canvas does not draw. The crate re-exports `ndarray` and
`serde_json`, so a draft's Cargo.toml needs only `beanfx` (`use beanfx::ndarray::{s, Array2, Array3};`).

## Signatures a draft calls

Read these before opening the kit source. `P = [f64; 2]` world px (y down), `Rgb = [f64; 3]` 0..1.

### dr

- `dr::main(fx: &dyn Effect, env!("CARGO_MANIFEST_DIR")) -> ExitCode`. Args: none (full run), `look [frames]`
  (out/look.png at 3x on dark, look_1x.png), `glow` (out/glow_takes.png at gains 0.6, 1.0, 1.3), `bench <id>`
  (out/bench.png against out/ref from tools/layers.mjs).
- `trait Effect { fn spec(&self) -> Spec; fn draw(&self, cv: &mut Canvas, f: usize, seed: u64, layer: Layer) -> Result<(), String>; }`.
  `draw` is pure in (f, seed, layer); return `Ok(())` untouched for a layer the effect lacks. Pass kit errors on with
  `?` (an `Err` stops the run with exit 2), never `let _ =`, which hides a missing caster.
- `Layer::{Effect, Caster, AuraBack, AuraFront}`. The sheet is `Effect`. Previews stack AuraBack, Caster, AuraFront,
  Effect over the dummy. Aura parts are cut round `caster_foot` with `Canvas::at`, so draw in world px.
- `Spec::new(name, w, h, n, fps)`; fields and defaults: `pivot` [w/2, h/2], `seed` 7, `looped` false, `hold` false,
  `view` "side", `dirs: fc::Meta` (`facing` "east" or "west" for one row), `glow` "medium", `clarity` "clear", `light_ramp: Vec<String>` (dark to white),
  `steps: Option<lt::Steps>` (hard retro light, also caps colours at 48), `edge_fade` 0.0 px, `hits: Vec<Value>`
  (`ex::hit`), `states: Vec<(String, [i64; 2])>`, `poses: Vec<Value>` (`ex::pose`), `windup` 0.0,
  `target: Option<Value>`, `dummy: Option<P>` (preview dummy foot), `caster_foot: Option<P>`,
  `aura: Option<Aura { frames, w, h, pivot }>`, `extra: Map` (more meta.beanfx), `trim: Option<f64>` (`ex::TRIM`;
  None when the cell keeps room on purpose, such as the caster's side of a cast), `pick`, `takes` (frame lists).
- Aura parts and the sheet pass the same checks: every frame needs colour (light alone is an empty frame) and a
  one-shot's last frame keeps at most 5 % of the peak pixels.
- `Canvas` fields `w, h, ox, oy, col: Array3<f64>` (straight RGBA) and `l: Array2<f64>` (summed light). Draw calls
  take world px: `put(x, y, c, a)`, `px(yi, xi, c, a)`, `line(p0, p1, c, a)`, `thick(p0, p1, wd, c, a)`,
  `ellipse(cx, cy, rx, ry, c, a)`, `poly(&[P], c, a)`, `paint(&Array2<i8>, &[Rgb], x0, y0, a)` (a shade map),
  `over_img(&Array3<u8>)` (a `Rig::place` frame), `glow(x, y, r, k)`, `glow_flat(x, y, r, k, flat)`,
  `glow_line(p0, p1, r, k)`, `glow_ring(x, y, big_r, r, k, flat)`, `flash_at(f, f0, x, y, r, k, life)`,
  `caster(foot, sc, pose, f: f64, cs::Draw, charge) -> Result<cs::Figure>` (pass `f as f64`), `win(x0, x1, y0, y1)` (pixel ranges),
  `world(yi, xi) -> P` (pixel centre) for per-pixel fields.
- Helpers: `hex("#rrggbb")`, `ramp(&[..])`, `seg_d(x, y, a, b)`, `hash01(a, b)`, `vnoise(x, y, seed)`,
  `span(f, f0, f1)` (clipped 0..1), `ease_io`, `ease_out`, `ease_in`, `measure(col, l)`,
  `write_part(out, name, &[Cel], ramp, fps, pivot, looped, anchor, more, glow)` for cast, travel or impact sheets.

### cs, tg, rig

- `cs::pose_at(f, front_keys: &[(f64, &str)], back_keys, aim: Option<P>, jab) -> Result<Pose>`; front arm keys `rest`,
  `chest`, `raise`, `pull`, and `point` when aim is set (`cs::aim_from(foot, sc, target)`); back arm keys `rest`,
  `out`, `behind`. Another name is an error.
- `cs::Draw { lift: 0.5, flut: 0.5, hair: "loose", ghost: 0.0, palette: &BODY, trail: None }`. The figure is about
  78 units tall; `sc` 0.44 is 34 px. `cs::Figure { sc, head, neck, hip, feet, finger, hair, .. }` in canvas px.
  `cs::finger_light(&mut cv.l, &g, point, jab)` lights the pointing hand.
- `tg::draw((h, w), (x, y), f, &hits, fps, tg::Draw { facing: -1.0, height })` and `tg::under(effect, dummy)`: the
  runner does both when `dummy` is set.
- `rig::load(name, None)?` then `rig.place((h, w), pivot, anim, k, rig::Place { direction, start, hold, travel })`
  gives an RGBA frame for `cv.over_img`; `rig.meta(anim, fps, Default::default())?` goes in `extra`.

### ex, fc, lt

- `ex::hit(frame: i64, fps, ex::Hit { freeze, shake, push, react, weight, dir, shake_time, flash, .. })`,
  `ex::pose(t, name, how)`.
- `fc::Meta { directions, facing, mirror, target }`: `facing` is "east" or "west" for a one-row sheet.
- `lt::glow_level(name) -> Option<GlowLevel { core, pool_r, pool_k, mean }>`; the runner prints the light mean
  against `mean`. `lt::Steps { levels: 4.0, floor: 0.06, phase: (0, 0) }`; stepped light reads brighter, so
  start the pools at about half the smooth gains.
- Shade-map shapes for `cv.paint`: `fk::lumpy`, `fk::ball`, `fk::puff`, `fk::streaks`, `fk::facets`, `fk::kite`,
  `fk::leaf`, `fk::hit_burst`, `fk::ground_impact` on grids from `fl::grid(w, h, cx, cy)`; `fl::noise`,
  `fl::outline`, `fl::ramp(base)`.

## Conventions

- Errors are `Result<T, String>`. Panics only on a broken invariant.
- Optional arguments are an options struct with `Default`:
  `ex::write(out, name, frames, fps, pivot, looped, ex::Write { light: Some((&flt).into()), hold: true, ..Default::default() })`.
  Options: `ex::Write`, `ex::Check`, `ex::Hit`, `fc::Meta`, `sfx::Write`, `sfx::Volley`, `pfx::Gif`, `pfx::Contact`,
  `pfx::Takes`, `rng::Choice`, and one per shape in `fk`.
- The keyword `loop` is `looped`. `ref` is `r#ref`.
- Free-form JSON (hits, poses, target, extra, the returned sheet JSON) is `serde_json::Value`, keys in insertion order.
  A whole number such as `24` or a whole pivot is written as an int; `windup` and pose `t` stay floats.
- Frames go in as `Stack`: `&Vec<Array3<u8>>` (one row) or `&Vec<Vec<Array3<u8>>>` (one row per heading), via `.into()`.
  Light is `Light`: u8 (0..255) or f64 (0..1) frames. Convert f32 light to f64 first.

## Dtypes and shapes

- Images: `Array3<u8>` indexed `[[y, x, c]]`, shape (h, w, 4) RGBA or (h, w, 3) RGB. Shade maps: `Array2<i8>`
  (palette index, -1 empty) or `Array2<f64>`.
- Floats are `f64`; integers are `i64` (`usize` for counts and indices). Seeds are `u64`.
- `img::read` gives RGBA, `img::read_rgb` RGB, `img::read_raw` the file's own channels.

## Numeric rules

The kit writes its own numbers the way these helpers do, so use them and a draft draws the same frames on every run.

| Need | Rust |
|---|---|
| square | `x * x` (never `powi` or `powf` for a square) |
| square root | `x.sqrt()` |
| round | `np::round(x)` (half to even), `np::round_dec(x, d)` |
| truncate | `x as i64` (toward zero) |
| floor division and modulo | `np::floordiv`, `np::pymod` (floor rules; `_i` forms for ints) |
| clip, hypot | `np::clip`, `np::hypot`; array forms `clip_a`, `hypot_a` |
| sum, mean | `np::sum`, `np::mean` (pairwise); `sum_axis`, `mean_axis` |
| ranges | `np::linspace`, `np::linspace_ep`, `np::arange`, `np::arange_i` |
| pixel grids | `let (ys, xs) = np::mgrid(h, w)`; `np::meshgrid(&x, &y)` (Y first) |
| lookup | `np::interp`, `np::searchsorted(a, v, right)`, `np::digitize` |
| statistics | `np::quantile`, `np::percentile`, `np::median` (linear method) |
| shifts and edges | `np::roll`, `np::pad(a, &[(b, a)], Pad::Edge)`, `np::gradient`, `np::where_` |
| index | `a[[y, x]]` (row first) |
| generator | `let mut rng = default_rng(7);` |
| draws | `rng.random()`, `rng.random_shape((h, w))`, `rng.uniform(a, b)`, `rng.uniform_shape`, `rng.normal_n(m, s, n)` |
| integers | `rng.integers(lo, hi)`, `rng.integers1(hi)` |
| choice | `rng.choice(n, k, Choice { replace: false, ..Default::default() })?` gives indices |
| order | `rng.shuffle(&mut a)`, `rng.permutation(n)` |

On arm64 the helpers fuse `a * b + c` in uniform, normal, arange and interp (`rng::madd`). Hand-written `a * b + c`
may differ in the last bit there; use the helper wherever one exists.

## Binary

- `beanfx version` prints `{"version": "<crate version>", "protocol": 2}`. Protocol 2 means drafts link the library.
- `beanfx gate "<prompt>" [--context "<what the image shows>"]` (`-` as the prompt reads it from stdin) prints the gate JSON (`ask`, `skip`, `source`).
  setup.sh builds it into `<project>/.beanfx/bin/beanfx`.
