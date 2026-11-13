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

`use beanfx::{np, rng::default_rng, ex, fc, sfx, pfx};` brings in the usual set. The crate re-exports `ndarray` and
`serde_json`, so a draft's Cargo.toml needs only `beanfx` (`use beanfx::ndarray::{s, Array2, Array3};`).

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
