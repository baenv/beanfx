# kit/ (frozen)

Do not edit these files. This is the drawing kit as it was when the older drafts in `drafts/` were drawn; they
import it through `../../kit`, and their output depends on it staying byte for byte the same. It is behind the
current kit on purpose (`export.py`, `facing.py` and `light.py` differ, and there is no `rig.py`).

- The kit to edit is `plugins/beanfx/skills/beanfx/kit/`. That one ships with the plugin and has the tests.
- New drafts never use this folder: `setup.sh --draft <name>` gives each its own copy in `drafts/<name>/kit/`.
- CI checks the files here against `FROZEN.sha256` and fails when one changes.
