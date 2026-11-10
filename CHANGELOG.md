# Changelog

Versions follow `plugins/beanfx/.claude-plugin/plugin.json`. A release is a tag `v<version>` on `main`; see
`CONTRIBUTING.md`.

## Unreleased

- Tests run under pytest (`pytest --cov` from the repo root); each script still runs alone with python.
- CI runs every test script (`test_rig.py` and `test_preview.py` were missing), checks that the root `kit/` stays
  frozen and keeps `docs/` under a size budget.
- `setup.sh --kit-status` lists the drafts whose pinned kit is behind the skill's kit; `setup.sh --draft <name>
  --refresh-kit` copies the current kit into one draft.
- README: quick start and the layout of the exported JSON.
- `CONTRIBUTING.md`, this file and a release workflow.

## 0.1.0

First public version (2026-11-08 to 2026-11-09).

- `/beanfx` as a standalone Claude Code plugin: an effect drawn in Python from a description or a reference image,
  exported as a sprite sheet with Aseprite-style JSON, strips and gifs.
- The drawing kit (shapes, ramps, additive light, direction fields, derive, export and its checks) and the brief
  knobs with `gate.py`.
- The browser runtime `runtime/beanfx.js`, the preview page and the demo page in `docs/`.
- The kit pinned per draft: `setup.sh --draft <name>` copies it once into `drafts/<name>/kit/`.
- A game character as the caster (`kit/rig.py`), with the placement, aura and combo knobs, and four bundled
  casters: sword and staff, side and top-down.
- gitleaks pre-commit hook and CI scan.
