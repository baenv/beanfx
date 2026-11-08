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
  `knobs/`, `tests/`, `setup.sh`, `tools/layers.mjs` (pixelfx colour and light layers) and the kit source in `kit/`). `.claude/skills/beanfx` is a symlink to its skill
  folder so /beanfx runs here without an install. `setup.sh` builds `.venv/` in the project it runs in
  (git root, else cwd, or `BEANFX_PROJECT`), and `--draft <name>` copies the kit into `drafts/<name>/kit/` once.
- `kit/`: the Python drawing kit as the older drafts import it (`../../kit`), frozen; `setup.sh` no longer writes it.
  The source of truth is the skill's `kit/`, and new drafts carry their own copy in `drafts/<name>/kit/`. Files: `fxkit.py` (shapes: lumpy, puff, streaks, facets, kite, leaf, claws, hits),
  `fxlib.py` (ramps, shade maps, strokes, noise, impact frames), `light.py` (additive glow), `pfx.py` (pixelfx
  layers, tint, composite, strip, gif), `caster.py` (the optional glowing mockup caster and avatar), `target.py` (a
  preview target dummy that reacts to hits), `ref.py` (an object traced from a reference image: derivative
  edges, value levels, skeleton), `facing.py`
  (view, facing, mirror, heading rows and the cast, travel, impact split in the JSON) and `derive.py` (outline,
  inner lines, spine and scatter points taken from the finished peak drawing for build-up and break-down states)
  and `export.py` (the sheet grid with pages, its Aseprite-style JSON with the act, and the checks: edge, empty
  frame, pop off, loop seam, unseeded randomness, other seeds, act).
- `drafts/<name>/`: one draft per effect, `<name>.py` plus `out/`. Only the drafts listed in `.gitignore` are tracked; new ones stay local. `*_v2`, `*_v3` are the redraws to the pixelfx bar.
- `docs/media/`: the README preview gifs.
- `.venv/`: Python with numpy and pillow. `setup.sh` creates it when missing; `--pixelfx` also checks node.
- Local only, gitignored: `site/` (a static gallery of finished sheets), `pixelfx/` (the clone from `setup.sh
  --pixelfx`), and the WIP `kit_char/` and `chars/<name>/` for `/char`, `kit_scene/` and `scenes/<name>/` for `/scene`
  (SDF shapes raymarched in Python, with a Blender route that needs Blender 5.x).

```
cd drafts/<name> && ../../.venv/bin/python <name>.py     # writes out/, exits 1 if a cell touches its edge
```

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
  palette, glow, clarity, density, states, caster). `gate.py` asks Jev (an optional prompt classifier, used only when its client
  is installed) in one call which knobs the prompt leaves open; without it the model decides from the files. Each open knob is one
  AskUserQuestion question, and no draft file is written before the brief is in the reply.
  Tests (`S=plugins/beanfx/skills/beanfx`): `python3 $S/tests/test_gate.py`, `.venv/bin/python $S/tests/test_facing.py`,
  `test_derive.py`, `test_export.py`, `test_ref.py`, `test_light.py`, `test_impact.py` and `test_kit.py`; `node $S/tests/test_runtime.mjs`. Plugin check: `claude plugin validate plugins/beanfx` and `claude plugin validate .`.
- Glow levels are subtle, medium and strong. Clarity is clear (default), balanced or hazy: how far light and
  translucent colour spread.
- All text in this repo is English: docs, skill, comments, printed output and JSON values. Effect ids and file
  names (`van_tien`, `phat_no_hoa_lien`) stay as they are.
