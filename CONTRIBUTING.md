# Contributing

Issues and pull requests are welcome. All text in the repo is English; effect ids and file names
(`van_tien`, `phat_no_hoa_lien`) stay as they are.

## Setup

```
git config core.hooksPath .githooks                  # gitleaks on every commit (the repo is public)
bash plugins/beanfx/skills/beanfx/setup.sh           # .venv with numpy and pillow
pip install pytest pytest-cov                        # for the tests
```

## Where to edit

| change | place |
|---|---|
| the drawing kit | `plugins/beanfx/skills/beanfx/kit/` |
| the skill, its knobs, the gate | `plugins/beanfx/skills/beanfx/` (`SKILL.md`, `knobs/`, `gate.py`) |
| the browser runtime | `plugins/beanfx/skills/beanfx/runtime/beanfx.js`, then copy it to `docs/beanfx.js` and run `python3 plugins/beanfx/skills/beanfx/tests/test_preview.py --write` |

Never edit the root `kit/`. It is the frozen kit of the older drafts (`kit/README.md`), and CI fails when a file
there changes.

Each draft made with `setup.sh --draft <name>` keeps its own copy of the kit, so a kit fix does not change a
finished effect. To see which drafts are behind, and to move one to the current kit:

```
bash plugins/beanfx/skills/beanfx/setup.sh --kit-status
bash plugins/beanfx/skills/beanfx/setup.sh --draft <name> --refresh-kit   # then run the draft and compare its output
```

## Tests

```
pytest                                    # every test script, python and node
pytest --cov --cov-report=term-missing    # with coverage of kit/ and gate.py
claude plugin validate plugins/beanfx && claude plugin validate .
```

A test is a script in `plugins/beanfx/skills/beanfx/tests/` named `test_<part>.py` (or `.mjs`) that exits 0 when
clean and prints one `FAIL` line per problem; it also runs alone with python. pytest picks up every such file
through `tests/conftest.py`, and so does CI. A kit change comes with a check in the matching script.

## Media

Images and video are gitignored; only `docs/media/*.gif` and `docs/demo/*.png` are tracked, and every byte
committed there stays in the history. Keep a gif under 5 MB (fewer frames or a smaller scale before more colours),
add one only when a page links it, and remove one that nothing links any more. CI fails when `docs/` passes
16 MB. Other previews belong on the site.

## Releases

1. Move the "Unreleased" notes in `CHANGELOG.md` under a new `## <version>` heading.
2. Set the same version in `plugins/beanfx/.claude-plugin/plugin.json`.
3. Merge to `main`, then `git tag v<version> && git push origin v<version>`. The release workflow checks the tag
   against `plugin.json` and publishes a GitHub release with that section of the changelog.
