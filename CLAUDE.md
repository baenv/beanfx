# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A sandbox for pixel-art project skills (any style, size and palette, no house rules). The
shipped skill is `/beanfx` effects, packaged as a Claude Code plugin (`plugins/beanfx/skills/beanfx/SKILL.md`;
this repo is its marketplace, `.claude-plugin/marketplace.json`). Work here means running the skill and
judging what it makes, or editing its `SKILL.md` or its kit. The plugin is standalone: it needs Rust (cargo builds
the kit and the `beanfx` binary) and, for reuse and the benchmark only, node with a pixelfx clone.

Work in progress: `/char` (characters with held weapons and objects) and `/scene` (scenes and backdrops). Their
skills, kits and drafts stay local and are gitignored until they are ready.

## Layout

S = `plugins/beanfx/skills/beanfx`.

- `plugins/beanfx/`: the plugin (`.claude-plugin/plugin.json`, `skills/beanfx/`). `.claude/skills/beanfx` is a
  symlink to the skill folder so /beanfx runs here without an install.
- `S/SKILL.md`, `S/knobs/` (one file per brief knob), `S/research.md`, `S/vfx_notes.md`, `S/porting.md` (engine import
  and porting the draw code), `S/runtime/beanfx.js` (browser runtime), `S/tools/preview.html` (browser preview;
  each draft run embeds it with its sheets as `out/<name>.html` via `ex::page`, opened with a double click),
  `S/tools/layers.mjs` (pixelfx colour and light layers).
- `S/setup.sh`: builds the `beanfx` binary into `<project>/.beanfx/bin/beanfx` (project = git root, else cwd, or
  `BEANFX_PROJECT`). `--draft <name>` scaffolds `drafts/<name>/` (Cargo.toml, `.cargo/config.toml`, a starter
  `src/main.rs`) and copies the kit into `drafts/<name>/kit/` once. `--kit-status` lists drafts whose kit is behind
  the skill's; `--draft <name> --refresh-kit` recopies one. `--pixelfx` also checks node and clones pixelfx.
- `S/kit/`: the kit, one Rust crate: library `beanfx` plus the `beanfx` binary (`version`, `gate`). `kit/API.md` lists
  the modules and conventions, `kit/DRAFTS.md` is the guide to writing a draft. Modules in `kit/src/`: `fk` (shapes:
  lumpy, puff, streaks, facets, kite, leaf, claws, hits), `fl` (ramps, shade maps, strokes, noise, impact frames),
  `lt` (additive glow), `pfx` (pixelfx layers, tint, composite, strip, gif, contact, takes), `cs` (the optional
  glowing mockup caster and avatar), `tg` (a preview target dummy that reacts to hits), `rig` (a game character as
  the caster), `rf` (an object traced from a reference image), `fc` (view, facing, mirror, heading rows, the cast,
  travel and impact split in the JSON), `dv` (outline, inner lines, spine and scatter points taken from a finished
  drawing), `dr` (the draft runner: a draft fills a `Spec` and draws an `Effect`, `dr::main` writes every output
  and runs the checks), `sfx` (sound synthesised from the effect's JSON), `ex` (the sheet grid with pages, its Aseprite-style
  JSON with the act, the checks, the preview page), and `np`, `rng`, `img` for numbers, the seeded generator and PNG
  files. `gate.rs` is the brief gate. The source of truth for the kit is S/kit; every draft carries its own copy.
- `S/casters/`: bundled casters `nghich_tien_kiem`, `_kiem_topdown`, `_truong` and `_truong_topdown` (a sword and a
  staff caster; side 2 rows, top-down 8), sheets and `rig.json` only. `rig::load(name, None)` and `ex::page` look in
  the project's `casters/` first, then there. Their build script stays local (`chars/`, gitignored).
- `drafts/<name>/`: one Rust crate per effect (`src/main.rs`, its `kit/`, `out/`). Only `drafts/hoa_cong_v2` is
  tracked, as the worked example; new drafts stay local (`git add -f` to publish one). Every draft builds into the
  project's one `.beanfx/target` (gitignored).
- `docs/output-json.md`: the fields of the exported JSON. `docs/media/`: the README preview gifs (CI budget: `docs/`
  at most 8 MB, one file at most 5 MB). `CONTRIBUTING.md`, `CHANGELOG.md`.
- Local only, gitignored: the project's `casters/<name>/` (bought example packs with a `rig.json`, read by `rig` as
  the caster; their licence forbids redistribution, never commit them), `site/` (a static gallery of finished
  sheets), `drafts_archive/`, `pixelfx/` (the clone from `setup.sh --pixelfx`), and the WIP `kit_char/` and
  `chars/<name>/` for `/char`, `kit_scene/` and `scenes/<name>/` for `/scene` (SDF shapes raymarched in Python,
  with a Blender route that needs Blender 5.x).

```
cd drafts/<name> && cargo run --release -q     # writes out/, exits 1 when a check fails
```

## Leak check

The repo is public. `.githooks/pre-commit` runs gitleaks on staged changes (`.gitleaks.toml`: the default rules
plus home paths), then the private terms in `.git/gitleaks-private.toml` (local, never committed). Enable it once
per clone with `git config core.hooksPath .githooks`; `.github/workflows/gitleaks.yml` scans every push.

## pixelfx

`setup.sh --pixelfx` clones https://github.com/patch-gg/pixelfx into `pixelfx/`: the reference effects
(`pixelfx/docs/CATALOG.md`) and Node renderers, used for reuse on request and the benchmark.

```
cd pixelfx && node tools/render.mjs <id> --gif
node plugins/beanfx/skills/beanfx/tools/layers.mjs <id> --out <draft>/src --pixelfx pixelfx   # pixelfx 0.3 dropped its own
```

## How the skill works

- An effect is code. The base is shade maps of palette indices drawn in Rust; the light (glow) is a separate
  additive layer. Default start: research the subject on the web, then draw from scratch. pixelfx effects and
  earlier drafts are reused only when the owner asks (then keep pixelfx's light, redraw its base).
- Size, palette, view and style come from the brief; everything runs in the project.
- Each draft run writes a 1x strip, 4x strips on dark and mid grounds, a 4x gif, and an edge/empty-frame check
  that exits 1 on failure.
- Output is a sprite sheet plus Aseprite-style JSON (frame rects and tags; under `meta.beanfx` frame size, count,
  fps, pivot, loop, glow, hit timing, and the direction fields from `fc`: view, facing and mirror, or 8 or 16
  heading rows; caster to target effects add cast, travel and impact parts) and a gif. `porting.md` in the skill
  covers engine import and porting the draw code. Report in English.
- Each brief knob is a file in the skill's `knobs/` (role, view, size, timing, loop, shape, style, palette, glow,
  clarity, density, states, caster, combo, placement, aura, sound). The gate, `<project>/.beanfx/bin/beanfx gate
  "<prompt>"`, says which knobs the prompt leaves open. It asks Jev (an optional prompt classifier, run through
  `python3` only when its client is installed) in one call; without it the model decides from the files. Each open
  knob is one AskUserQuestion question, and no draft file is written before the brief is in the reply.
- Tests: `cd S/kit && cargo test --locked` (unit and integration tests of the crate, including the gate, the
  export, the facing fields and the preview page check), and `node S/tests/test_runtime.mjs` (the browser
  runtime). Plugin check: `claude plugin validate plugins/beanfx` and `claude plugin validate .`.
- Glow levels are subtle, medium and strong. Clarity is clear (default), balanced or hazy: how far light and
  translucent colour spread.
- All text in this repo is English: docs, skill, comments, printed output and JSON values. Effect ids and file
  names (`van_tien`, `phat_no_hoa_lien`) stay as they are.
