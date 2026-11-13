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

`bash <skill>/setup.sh --draft <name>` writes all of it, with a starter `main.rs` (a square that crosses a 24x16 cell
in 8 frames) that already writes the sheet and runs the checks. Run it:

```
cd drafts/<name> && cargo run --release -q     # writes out/, exits 1 when a check fails, 2 on an error
```

The first build of a project takes about a minute; every later draft reuses the shared target folder.

## Shape of main.rs

1. A module doc (`//!` or `#![doc = r#"..."#]`) with the brief: what it shows, size, frames, fps, loop, style, glow,
   clarity, and a state table when there are states.
2. Constants for the brief (`W`, `H`, `N`, `FPS`, `PIVOT`, `SEED`, `GLOW`, state starts) and the palette ramps.
3. `render(f, seed)` draws frame f as a pure function of the frame index and the seed: shade maps (`Array2<i8>`) painted
   with `pfx::paint`, light summed into one `Array2<f64>` with `lt::glow*`, stacked to `Array3` and coloured with `pfx::tint`, both
   composited by `pfx::composite`.
4. `run()` renders every frame, prints the light and colour measures, writes the strips, contact sheet and gif,
   calls `fc::meta` and `fc::check`, then `ex::write`, `ex::page`, `ex::check` and `ex::check_seeds`, prints each
   problem and returns the exit code. `main` maps `Ok(code)` to `ExitCode::from(code)` and an error to 2.

## Rules that keep the output stable

- Draw every random choice from `default_rng(seed + salt)`. `ex::check` scans the source for unseeded randomness:
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
