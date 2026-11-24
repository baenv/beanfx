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
| `pfx` | writers and layers: strip, gif, contact, takes, load, tint, recolour, gain, keep, bands, paint, composite |
| `fl` | shade-map helpers: ramp, grids, Pen, stroke, noise, outline, ground ring, impact frames |
| `mo` | motion in closed form (fly with drag, fly_ground, landed_at, cycle) and the particles on it: spark, flame, smoke, burst, chunk(s), dust, brands, scorch |
| `pt` | parts: tilted ring and ring_glow cut into far and near halves, crystal with a glint, edge_depth, frost on a body |
| `lt` | additive light: glow, glow_line, glow_ring, steps, bands, Flashes, flash_at, flicker, glow levels |
| `fk` | shapes: lumpy, ball, puffs, streaks, facets, kite, leaf, twinkle, claws, hit_burst, ground_impact |
| `cs` | the mockup caster and avatar |
| `tg` | the preview target dummy |
| `rig` | a game character as the caster (`rig::load(name, None)`) |
| `rf` | an object traced from a reference image (`rf::trace`, `rf::paint`) |
| `dv` | points taken from a finished drawing (outline, simplify, spine, scatter, local, world) |
| `hp` | the host project's palette (`beanfx palette [dir]`, `hp::scan`): palette files, Aseprite palettes, PNG colours, ramps by family |
| `dr` | the draft runner: `Spec`, `Effect`, `Canvas`, `dr::main` (previews, sheet, JSON, page, checks, `look`, `glow`, `bench`) |

A draft on the runner starts with `use beanfx::dr::{self, Canvas, Effect, Layer, Spec};`; the lower modules are for
shapes the canvas does not draw. The crate re-exports `ndarray` and
`serde_json`, so a draft's Cargo.toml needs only `beanfx` (`use beanfx::ndarray::{s, Array2, Array3};`).

## Signatures a draft calls

Read these before opening the kit source. `P = [f64; 2]` world px (y down), `Rgb = [f64; 3]` 0..1.

### dr

- `dr::main(fx: &(dyn Effect + Sync), env!("CARGO_MANIFEST_DIR")) -> ExitCode`. Args: none (full run), `look [frames]`
  (out/look.png at 3x on dark, look_1x.png), `glow` (out/glow_takes.png at gains 0.6, 1.0, 1.3), `bench <id>`
  (out/bench.png against out/ref from tools/layers.mjs).
- `trait Effect { fn spec(&self) -> Spec; fn draw(&self, cv: &mut Canvas, f: usize, seed: u64, layer: Layer) -> Result<(), String>; }`.
  `draw` is pure in (f, seed, layer); return `Ok(())` untouched for a layer the effect lacks. Pass kit errors on with
  `?` (an `Err` stops the run with exit 2), never `let _ =`, which hides a missing caster.
- The runner draws frames on every core (`dr::par`), so `Fx` must be `Sync`: a plain struct is; keep a cache in a
  `LazyLock` or `thread_local!`, never a `RefCell` field. The output is the same at any thread count;
  `BEANFX_THREADS=1` runs in order on one thread (for a debugger or a print trace).
- `Layer::{Effect, Caster, AuraBack, AuraFront}`. The sheet is `Effect`. Previews stack AuraBack, Caster, AuraFront,
  Effect over the dummy. Aura parts are cut round `caster_foot` with `Canvas::at`, so draw in world px.
- `Spec::new(name, w, h, n, fps)`; fields and defaults: `pivot` [w/2, h/2], `seed` 7, `looped` false, `hold` false,
  `view` "side", `dirs: fc::Meta` (`facing` "east" or "west" for one row), `glow` "medium", `clarity` "clear", `light_ramp: Vec<String>` (dark to white),
  `steps: Option<lt::Steps>` (hard retro light, `Some(lt::Steps::default())`; also caps colours at 48 a frame, so take
  every colour from a ramp tone at a few fixed alphas, never a per-pixel blend), `edge_fade` 0.0 px, `hits: Vec<Value>`
  (`ex::hit`), `states: Vec<(String, [i64; 2])>`, `poses: Vec<Value>` (`ex::pose`), `windup` 0.0,
  `target: Option<Value>`, `dummy: Option<P>` (preview dummy foot), `caster_foot: Option<P>`,
  `aura: Option<dr::Aura { frames, w, h, pivot }>`, `extra: Map` (more meta.beanfx), `trim: Option<f64>` (`ex::TRIM`;
  None when the cell keeps room on purpose, such as the caster's side of a cast), `pick`, `takes` (frame lists).
- Aura parts and the sheet pass the same checks: every frame needs colour (light alone is an empty frame) and a
  one-shot's last frame keeps at most 5 % of the peak pixels. `hold` does not exempt an aura: it starts with colour
  in frame 0 and fades out by its last frame even when the effect ends held.
- A caster with aura parts and a cast that lands `RANGE` px in front (`knobs/placement.md`). Every layer draws in
  the effect's world px; the runner cuts the aura cells round `caster_foot`:

```
// in spec(): size the cell so the caster and the struck spot both fit
sp.pivot = [CASTER[0] + RANGE, GROUND];                                     // the struck spot
sp.caster_foot = Some(CASTER);                                              // the caster's feet, world px
sp.aura = Some(dr::Aura { frames: N, w: 64, h: 80, pivot: [32.0, 70.0] });  // aura cell, the feet at its pivot
sp.trim = None;                                                             // keep the caster's side of the cell
sp.extra.insert("caster".into(), beanfx::serde_json::json!({"offset": {"east": [RANGE, 0]}, "range": RANGE}));
// in draw(): one arm per layer
Layer::Caster => { cv.caster(CASTER, 0.44, pose, ft, cs::Draw::default(), 0.5)?; }
Layer::AuraBack | Layer::AuraFront => {
    let front = layer == Layer::AuraFront;
    let k = (0.25 + 0.75 * span(ft, 0.0, 10.0)) * (1.0 - 0.96 * span(ft, n - 16.0, n - 1.0)); // colour at f 0, gone at the end
    let (bx, by) = (CASTER[0], CASTER[1] - 17.0);                           // the body's middle
    if !front { cv.ellipse(bx, by, 14.0 * k, 22.0 * k, deep, 0.8); cv.glow(bx, by, 26.0, 0.3 * k); }
    // motes round the body: draw mote i in this layer when (angle_i.sin() > 0.0) == front
}
```
- `Canvas` fields `w, h, ox, oy, col: Array3<f64>` (straight RGBA) and `l: Array2<f64>` (summed light). Draw calls
  take world px: `put(x, y, c, a)`, `px(yi, xi, c, a)`, `line(p0, p1, c, a)`, `thick(p0, p1, wd, c, a)`,
  `ellipse(cx, cy, rx, ry, c, a)`, `poly(&[P], c, a)`, `paint(&Array2<i8>, &[Rgb], x0, y0, a)` (a shade map),
  `over_img(&Array3<u8>)` (a `Rig::place` frame), `glow(x, y, r, k)`, `glow_flat(x, y, r, k, flat)`,
  `glow_line(p0, p1, r, k)`, `glow_ring(x, y, big_r, r, k, flat)`, `flash_at(f, f0, x, y, r, k, life)` (all `f64`),
  `caster(foot, sc, pose, f: f64, cs::Draw, charge) -> Result<cs::Figure>` (pass `f as f64`), `win(x0, x1, y0, y1)` (pixel ranges),
  `world(yi, xi) -> P` (pixel centre) for per-pixel fields. `put(x, y, ..)` floors world px to its pixel (no `+ 0.5`).
  JSON in a draft is `beanfx::serde_json::json!`.
- Helpers: `hex("#rrggbb")`, `ramp(&[..])`, `seg_d(x, y, a, b)`, `hash01(a: u64, b: u64)` (0..1), `vnoise(x, y, seed)` (0..1, one cell per unit, so pass `x / 8.0` for
  8 px lumps),
  `span(f, f0, f1)` (clipped 0..1), `ease_io`, `ease_out`, `ease_in`, `measure(col, l)`,
  `write_part(out, name, &[Cel], ramp, fps, pivot, looped, anchor, more, glow)` for cast, travel or impact sheets,
  `par(n, |i| -> Result<T, String>)` (index order, the first error by index) for a draft's own loops.
- Palette variants (`knobs/palette.md`): `sp.ramp` = the tones `draw` paints with, dark to bright, and
  `sp.variants = vec![Variant::new("frost", &[..same count..], &[light ramp])]`. Each writes `sheets/<name>_<variant>`
  (sheet, colour, light, JSON) and `<name>_<variant>_1x.png` by `pfx::recolour` (a gradient map: tones map exactly,
  blends to the same blend, colour over `RECOLOUR_REACH` 40 from the ramp, such as grey smoke, stays); the JSON's
  `variants` lists them. A variant whose ramp misses over half the colour prints a note (fine for a smoky effect).

### mo

Time in seconds (`f as f64 / FPS`), world px, y down, gravity px/s^2 (negative rises). All pure in t.

- `fly(p0, v0, g, drag, t) -> (P, P)` position and velocity with exponential drag (0 = ballistic); speed eases to
  g / drag. `fly_ground(p0, v0, g, drag, t, Ground { y, bounce: 0.45, slide: 0.7, rest: 12.0 }) -> (P, P, landings)`
  bounces on the floor and rests. `cycle(seed, i, t, every, life) -> Option<age 0..1>` for a seamless stream.
- `spark(cv, p, v, stretch, max, hot, tail, a, glow)`: a two-tone streak as long as its speed (`stretch` px per
  100 px/s), a dot when slow. Pair with `fly_ground` for sparks that fall, bounce and stop.
- `flame(cv, x, y, r, age, &fire_ramp, a, glow)`: rim, lit core up-left, tongue; white-hot first, cooling down the
  ramp. `smoke(cv, x, y, r, age, &smoke_ramp, a)`: body, dense low core, lit cap while young; swells and thins.
- `burst(cv, seed, at, t, &fire, &smoke, &Burst { n: 22, speed: (12, 70), g: -40, drag: 4, life: (0.7, 1.4),
  flame_share: 0.45, r: (3.5, 6.5), glow: 0.25 })`: an explosion that cools into smoke, smoke under the flames.
- `chunks(cv, seed, at, t, [rim, dark, mid, lit], &dust_ramp, &Chunks { n: 8, speed: (60, 140), g: 360, drag: 1, r:
  (1.5, 3), spin: 2, ground, dust: 0.5 })`: debris that tumbles, bounces, rests and kicks up `dust` where it lands;
  `chunk(cv, p, r, angle, shades, a)` one of them; `landed_at(p0, v0, g, drag, ground, t_max)` the first landing.
- `brands(cv, seed, at, t, &fire, &Brands { n: 4, .. })`: burning chunks with a flame trail; each lands and burns a
  small fire for `burn` s that dies to embers. `scorch(cv, seed, at, rx, ry, age, &fire, soot)`: the floor under a
  blast, white-hot at age 0, cooling down the ramp to soot that stays from age 1 (a one-shot that leaves a mark,
  `hold: true`). Draw the scorch first, under everything.

### pt

- `ring(cv, c, r, w, flat, Half::{All, Far, Near}, far, near, a)` and `ring_glow(cv, c, r, flat, spread, k, half)`:
  a floor ring at a tilt, depth-shaded; `Far` in `Layer::AuraBack`, `Near` in `Layer::AuraFront`, so the body
  stands inside it (the halves add up to the whole ring, pixel for pixel).
- `crystal(cv, base, h, w, lean, [rim, dark, lit, white], glint: Option<0..1>, a)`: a spike lit on the top-left face,
  a ridge, a white tip; `glint` sweeps a bright band up the lit face (animate it with a phase per crystal).
- `frost(cv, seed, &body_rgba, grow 0..1, [deep, ice, white], Frost { depth: 4, icicles: 0.3, icicle_len: 4 })`:
  frost creeping in from the silhouette (`edge_depth(mask)` gives each pixel's depth) and icicles under its bottom
  edges. `body_rgba` is canvas-sized: a `Rig::place` frame or a body drawn on its own `Canvas` (`cel().col`).
  The same `edge_depth` builds other statuses on the body (burning edges, poison drips).

### cs, tg, rig

- `cs::stepped(f, fps, step_fps)`: the frame floored to a slower beat; pose the limbs on `stepped(f, 24.0, 12.0)` and
  keep the feet and travel on `f`, so arms snap key to key like hand-drawn animation.
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
- `beanfx check <sheet.json> [--max-colours N] [--max-mb M] [--no-trim] [--json]` runs the kit's craft, framing, budget, act and sound checks on an exported sheet (single or paged) and exits 0 when clean, 1 when a check fails, 2 on error.
- `beanfx sfx <sheet.json> [--out <dir>] [--voice retro|soft|real] [--element <el>] [--seed N] [--sounds <dir|auto|none>] [--json]` synthesises the WAV track and cue files for an exported sheet JSON, updates `meta.beanfx.sound`, and runs `sfx::check`.
  setup.sh builds it into `<project>/.beanfx/bin/beanfx`.
