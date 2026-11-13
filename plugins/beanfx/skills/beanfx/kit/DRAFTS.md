# Writing a draft in Rust

A draft is one effect as a small Rust program on the kit crate. `drafts/hoa_cong_v2` is the worked example (a
volley of fire arrows on a camp, 108 frames). API.md lists the kit calls.

## Layout

```
drafts/<name>/Cargo.toml          package <name>, beanfx = { path = "kit" }
drafts/<name>/.cargo/config.toml  [build] target-dir = "../../.beanfx/target"   (one shared build per project, gitignored)
drafts/<name>/kit/                the pinned copy of the kit crate (setup.sh --draft <name> makes it once)
drafts/<name>/src/main.rs         the effect; Cargo.lock is tracked, out/ and the target dir are not
```

`bash <skill>/setup.sh --draft <name>` writes all of it, with a starter `main.rs` on the runner (a spark that swells and
fades in a 32x32 cell over 10 frames) that already writes the sheet and runs the checks. Run it:

```
cd drafts/<name> && cargo run --release -q     # writes out/, exits 1 when a check fails, 2 on an error
cargo run --release -q -- look 20 30 44         # just those frames, 3x, in a second
cargo run --release -q -- glow                  # the three glow takes round the first hit
```

The first build of a project takes about a minute; every later draft reuses the shared target folder.

## Shape of main.rs

A draft holds only the effect: the brief and the drawing. `dr` (API.md) writes previews, strips, gif, sheet, JSON,
parts and page and runs every check, so a new draft is about 150 to 350 lines.

1. A two-line module doc with the brief (what it shows, size, frames, fps, loop, style, glow, clarity); states go in
   `Spec.states`, so the table lives in code.
2. Palette constants (hex) and timing constants (frame of each beat).
3. `impl Effect for Fx`: `spec()` fills `Spec` (size, fps, pivot, light ramp, hits, poses, target, dummy,
   caster foot, aura, extra); `draw(cv, f, seed, layer)` paints one layer with the canvas calls and `cv.glow*`.
   Split `draw` into one function per element (core, rocks, ring, sparks) when it passes about 60 lines.
4. `fn main() -> ExitCode { dr::main(&Fx, env!("CARGO_MANIFEST_DIR")) }`.

Write main.rs in pieces: the spec and one element first, run `look`, then add elements with Edit. A shape the
canvas does not draw comes from `fk` as a shade map and goes in with `cv.paint`. A draft that needs a step the
runner does not take (heading rows, a custom sheet) writes its own `run()` on `ex`, `fc` and `pfx` as before; the
worked example `drafts/hoa_cong_v2` predates the runner and shows that route.

## Rules that keep the output stable

- Draw every random choice from `default_rng(seed + salt)` or `dr::hash01(seed, i)`. `ex::check` scans the source for unseeded randomness:
  pass `src: Some(concat!(env!("CARGO_MANIFEST_DIR"), "/src/main.rs").into())`.
- The draw order of random calls is part of the output. Keep it fixed once the effect looks right.
- Use `np::round` (half to even), `np::pymod` and `np::floordiv` for rounding and modulo, `x * x` for a square, and
  `x as i64` for a truncating cast. A window bound that truncates toward zero and then clamps keeps negative edges.
- Write float expressions in one fixed order; `a * (1.0 - t) + b * t` and `a + (b - a) * t` differ in the last bit.
- Write outputs under `env!("CARGO_MANIFEST_DIR")/out`, so `cargo run` from any folder lands in the draft.
- Where a window of a map takes a maximum (`F[y][x] = max(F[y][x], heat)`), loop over the window and compare per pixel.
- Keep several writes to one pixel in order: the last write wins.

## Idioms

| Need | Rust |
|---|---|
| shared pixel grids | `static X: LazyLock<..>` filled from `np::mgrid(H, W)` (gives ys, xs) |
| a scene built once per seed | `thread_local!` holding a `HashMap<u64, Rc<Scene>>`, filled on first use |
| records | plain structs, one field per key |
| non-zero pixels | `np::nonzero(&mask)` (row-major) |
| stacking cells | `Array3::from_shape_fn`, `img::tile(cells, cols)` |
| a 4x preview | `img::zoom(&a, 4)`, `img::write(path, &a.view())` |
| JSON | `serde_json::json!` or a `Map`; key order is insertion order |
| sorting rows of floats | `[f64; n]` rows and `sort_by(partial_cmp)` |

## Pinned kit

The copy in `drafts/<name>/kit/` stays as it was when the draft was made, so a plugin update never changes a
finished effect. `setup.sh --kit-status` lists drafts whose kit is behind; `setup.sh --draft <name> --refresh-kit`
copies the current kit over one named draft (then run it and compare the frames). A draft that needs the old
behaviour after a refresh copies it into its own `main.rs` with a comment.

## Gifs

A gif frame with more than 256 colours is quantised, so a soft-light effect shows small colour shifts in the gif only. The sheet PNGs are exact.

## What a run writes and checks

The runner makes every call in this section; a draft on `dr` writes none of them. They are named so a check line
can be traced, and for a draft with its own `run()`.

`dr::main` writes, each run: the sheet and JSON (`export.md` in the skill folder), a 4x strip on a dark and on a mid ground, a
4x gif at its fps (`pfx::gif`, through `ex::hitstop` when there are hits) and `out/contact.png`
(`pfx::contact(path, &frames, fps, Default::default())`: 12 moments labelled with frame and time, so timing reads without the gif),
a preview page per sheet, `ex::page(out.join("sheets").join("<name>.json"), Default::default())`: `out/<name>.html`, the skill's `tools/preview.html`
with the sheets, the JSON and the caster's rig and sheets embedded, so it opens with no folder to pick (it embeds
the owner's caster sprites, so it stays in the gitignored `out/` and is never shipped), and runs the checks on the effect
frames, printing every line and exiting 1 when there is one:

- `ex::check(&frames, ex::Check { light, looped, src, hold, .. })` (`src` is the draft's `src/main.rs`): colour on the cell edge, light above 0.02 on the edge
  (smooth light spreads wide, so the pool radius leaves a margin to the cell), an empty frame, a one-shot that pops
  off, a loop seam, randomness without a seed. With stepped light also pass `max_colours: Some(48.0)`: a frame over it
  has smooth light or stray tones left in. Every draft prints the median colours per frame (`ex::colours(&last)`)
  whatever the style, so the owner sees how pixel the effect reads. The same call looks at the whole sheet twice
  more. Framing: when the drawing sits to one side of its cell (`ex::framing(frames)`: the box holding 96 % of the
  colour over all frames, and what cutting the lopsided margins would save), a `framing:` line says how many px
  to cut from which side; move the subject or trim the cell, and pass `trim: None` only when the empty side is
  wanted. Budget: sheets that decode to more than 128 MB of texture memory (`ex::memory_mb`) give a `budget:`
  line; cut frames (a lower fps, a held state as a short loop), the cell, or split the effect into parts, and pass
  `max_mb: None` only after the owner accepts the size (a full-screen cutscene).
- `ex::check_seeds(|f, sd| render(f, sd).0, N, &[2, 3, 7], 2)`: the edge and empty checks again with seeds 2, 3 and 7,
  every second frame. So `render` takes a `seed` (default `SEED`) and draws every random choice from
  `default_rng(seed + salt)`; particles a reseed throws further show up here.
- `ex::check_act(&act, N, FPS, looped)?` when the JSON has an act (`export.md`).

Judge at 1x for read, 4x for detail, the gif for timing.
