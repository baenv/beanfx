# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A sandbox for pixel-art project skills (any style, size and palette, no house rules). The
shipped skill is `/beanfx` effects, packaged as a Claude Code plugin (`plugins/beanfx/skills/beanfx/SKILL.md`;
this repo is its marketplace, `.claude-plugin/marketplace.json`). Work here means running the skill and
judging what it makes, or editing its `SKILL.md` or its kit. The plugin is standalone: it needs only Python
(numpy, pillow), and node with a pixelfx clone for reuse and the benchmark.

Work in progress: `/char` (characters with held weapons and objects) and `/scene` (scenes and backdrops). Their
skills, kits and drafts stay local and are gitignored until they are ready.

## Layout

- `plugins/beanfx/`: the plugin (`.claude-plugin/plugin.json`, `skills/beanfx/` with `SKILL.md`, `gate.py`,
  `knobs/`, `tests/`, `setup.sh`, `tools/layers.mjs` (pixelfx colour and light layers), `tools/preview.html` (browser preview of results and casters; each draft run embeds it with its sheets as `out/<name>.html` via `ex.page`, opened with a double click) and the kit source in `kit/`). `.claude/skills/beanfx` is a symlink to its skill
  folder so /beanfx runs here without an install. `setup.sh` builds `.venv/` in the project it runs in
  (git root, else cwd, or `BEANFX_PROJECT`), and `--draft <name>` copies the kit into `drafts/<name>/kit/` once
  (`--kit-status` lists the drafts whose kit is behind the skill's; `--draft <name> --refresh-kit` recopies one).
- The kit: the source of truth is the skill's `kit/`, and every draft carries its own copy in `drafts/<name>/kit/`
  (the published examples carry the kit they were drawn with, older than the skill's; there is no root `kit/`). Files: `fxkit.py` (shapes: lumpy, puff, streaks, facets, kite, leaf, claws, hits),
  `fxlib.py` (ramps, shade maps, strokes, noise, impact frames), `light.py` (additive glow), `pfx.py` (pixelfx
  layers, tint, composite, strip, gif), `caster.py` (the optional glowing mockup caster and avatar), `target.py` (a
  preview target dummy that reacts to hits), `ref.py` (an object traced from a reference image: derivative
  edges, value levels, skeleton), `facing.py`
  (view, facing, mirror, heading rows and the cast, travel, impact split in the JSON) and `derive.py` (outline,
  inner lines, spine and scatter points taken from the finished peak drawing for build-up and break-down states)
  `sfx.py` (optional sound synthesised from the effect's JSON: hit cues by weight, charge, whoosh, tail, hum; WAV plus `meta.beanfx.sound`)
  and `export.py` (the sheet grid with pages, its Aseprite-style JSON with the act, and the checks: edge, empty
  frame, pop off, loop seam, unseeded randomness, other seeds, act, framing (the drawing parked to one side of its
  cell) and the texture budget).
- `drafts/<name>/`: one draft per effect, `<name>.py`, its `kit/` and `out/`. Only the drafts listed in `.gitignore` are tracked; new ones stay local. `*_v2`, `*_v3` are the redraws to the pixelfx bar.
- `docs/output-json.md`: the fields of the exported JSON, linked from the README.
- `docs/media/`: the README preview gifs (CI budget: `docs/` at most 8 MB, one file at most 5 MB).
- `CONTRIBUTING.md` (where to edit, tests, media, release steps), `CHANGELOG.md`, `pyproject.toml` (pytest and
  coverage settings only).
- `.venv/`: Python with numpy and pillow. `setup.sh` creates it when missing; `--pixelfx` also checks node.
- Bundled casters: the skill's `casters/` ships `nghich_tien_kiem`, `_kiem_topdown`, `_truong` and `_truong_topdown`
  (a sword and a staff caster; side 2 rows, top-down 8), sheets and `rig.json` only. `rig.load(name)` and `ex.page`
  look in the project's `casters/` first, then there, so any project can use them with no setup. Their build script
  stays local (`chars/`, gitignored).
- Local only, gitignored: the project's `casters/<name>/` (bought example packs with a `rig.json`, read by
  `kit/rig.py` as the caster; their licence forbids redistribution, never commit them), `site/` (a static gallery of finished sheets), `drafts_archive/` (drafts that no longer run, kept for reference), `pixelfx/` (the clone from `setup.sh
  --pixelfx`), and the WIP `kit_char/` and `chars/<name>/` for `/char`, `kit_scene/` and `scenes/<name>/` for `/scene`
  (SDF shapes raymarched in Python, with a Blender route that needs Blender 5.x).

```
cd drafts/<name> && ../../.venv/bin/python <name>.py     # writes out/, exits 1 if a cell touches its edge
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

- An effect is code. The base is shade maps of palette indices drawn in Python; the light (glow) is a separate
  additive layer. Default start: research the subject on the web, then draw from scratch. pixelfx effects and
  earlier drafts are reused only when the owner asks (then keep pixelfx's light, redraw its base).
- Size, palette, view and style come from the brief; everything runs in the project.
- Each draft run writes a 1x strip, 4x strips on dark and mid grounds, a 4x gif, and an edge/empty-frame check
  that exits 1 on failure.
- Output is a sprite sheet plus Aseprite-style JSON (frame rects and tags; under `meta.beanfx` frame size, count,
  fps, pivot, loop, glow, hit timing, and the direction fields from
  `kit/facing.py`: view, facing and mirror, or 8 or 16 heading rows; caster to target effects add cast, travel and
  impact parts) and a gif. `porting.md` in the skill covers engine import and porting the draw code. Report in
  English.
- Each brief knob is a file in the skill's `knobs/` (role, view, size, timing, loop, shape, style,
  palette, glow, clarity, density, states, caster, combo, placement, aura, sound). `gate.py` asks Jev (an optional prompt classifier, used only when its client
  is installed) in one call which knobs the prompt leaves open; without it the model decides from the files. Each open knob is one
  AskUserQuestion question, and no draft file is written before the brief is in the reply.
  Tests (`S=plugins/beanfx/skills/beanfx`): `python3 $S/tests/test_gate.py`, `.venv/bin/python $S/tests/test_facing.py`,
  `test_derive.py`, `test_export.py`, `test_rig.py`, `test_ref.py`, `test_light.py`, `test_impact.py`, `test_sfx.py`, `test_kit.py` and `test_shapes.py`; `python3 $S/tests/test_preview.py`; `node $S/tests/test_runtime.mjs`. All of them in one run with coverage: `pytest --cov` from the repo root
  (`tests/conftest.py` runs each script once and reports every check it records through `tests/checklog.py` as its
  own test; CI does the same and fails under the coverage floor in `pyproject.toml`). Plugin check: `claude plugin validate plugins/beanfx` and `claude plugin validate .`.
- Glow levels are subtle, medium and strong. Clarity is clear (default), balanced or hazy: how far light and
  translucent colour spread.
- All text in this repo is English: docs, skill, comments, printed output and JSON values. Effect ids and file
  names (`van_tien`, `phat_no_hoa_lien`) stay as they are.
