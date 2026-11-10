# Changelog

Versions follow `plugins/beanfx/.claude-plugin/plugin.json`. A release is a tag `v<version>` on `main`; see
`CONTRIBUTING.md`.

## Unreleased

## 0.2.0

Plain questions with pictures (2026-11-10).

- Glow takes: an open glow knob is picked on the drawing. The peak and the frames round it render at subtle,
  medium and strong into `out/glow_takes.png` and `.gif`, then one question asks which. `light.GLOW` holds the
  level table and `pfx.takes` lays out any takes (glow or shape) side by side.
- Every knob file now shows an ASCII preview for its options (view, loop, role, density, placement, clarity, style,
  palette, glow, caster, combo, aura, states, besides size, timing and shape), and an owner new to VFX gets one on
  every question.
- pytest reports each check as its own test (371 of them), not one per script; `tests/checklog.py` records them.
- CI fails when coverage drops under 60% (`fail_under` in `pyproject.toml`; 64% now).
- The published example drafts carry their own kit in `drafts/<name>/kit/` (the same files they were drawn with,
  so their output is byte for byte the same), and the root `kit/` is gone.

## 0.1.0

First public version (2026-11-08 to 2026-11-10).

- `/beanfx` as a standalone Claude Code plugin: an effect drawn in Python from a description or a reference image,
  exported as a sprite sheet with Aseprite-style JSON, strips and gifs.
- The drawing kit (shapes, ramps, additive light, direction fields, derive, export and its checks) and the brief
  knobs with `gate.py`.
- The browser runtime `runtime/beanfx.js`, the preview page and the demo page in `docs/`.
- The kit pinned per draft: `setup.sh --draft <name>` copies it once into `drafts/<name>/kit/`.
- A game character as the caster (`kit/rig.py`), with the placement, aura and combo knobs, and four bundled
  casters: sword and staff, side and top-down.
- gitleaks pre-commit hook and CI scan.
- Tests run under pytest (`pytest --cov` from the repo root); each script still runs alone with python.
- CI runs every test script (`test_rig.py` and `test_preview.py` were missing) and keeps `docs/` under 8 MB.
- `setup.sh --kit-status` lists the drafts whose pinned kit is behind the skill's kit; `setup.sh --draft <name>
  --refresh-kit` copies the current kit into one draft.
- README: demo first, quick start; the layout of the exported JSON in `docs/output-json.md`.
- Removed three preview gifs that no page linked any more (about 8 MB); `docs/` is now 6.5 MB.
- `CONTRIBUTING.md`, this file and a release workflow.
