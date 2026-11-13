# Contributing

Issues and pull requests are welcome. All text in the repo is English; effect ids and file names
(`van_tien`, `phat_no_hoa_lien`) stay as they are.

## Setup

```
git config core.hooksPath .githooks                  # gitleaks on every commit (the repo is public)
bash plugins/beanfx/skills/beanfx/setup.sh           # builds the beanfx binary into .beanfx/bin (needs cargo)
```

## Where to edit

| change | place |
|---|---|
| the drawing kit, export and checks, sound, preview page, gate | `plugins/beanfx/skills/beanfx/kit/src/` (one Rust crate; `kit/API.md` lists the modules) |
| the skill and its knobs | `plugins/beanfx/skills/beanfx/` (`SKILL.md`, `knobs/`) |
| the browser runtime | `plugins/beanfx/skills/beanfx/runtime/beanfx.js`, then copy it to `docs/beanfx.js` and paste it into `tools/preview.html` between the RUNTIME START and RUNTIME END markers (`export ` removed); `cargo test` in `kit/` checks the copy |

Each draft keeps its own copy of the kit, so a kit fix does not change a
finished effect. To see which drafts are behind, and to move one to the current kit:

```
bash plugins/beanfx/skills/beanfx/setup.sh --kit-status
bash plugins/beanfx/skills/beanfx/setup.sh --draft <name> --refresh-kit   # then run the draft and compare its output
```

## Tests

```
(cd plugins/beanfx/skills/beanfx/kit && cargo test --locked)   # the crate's unit and integration tests
node plugins/beanfx/skills/beanfx/tests/test_runtime.mjs       # the browser runtime
claude plugin validate plugins/beanfx && claude plugin validate .
```

A kit change comes with a test in the matching module or in `kit/tests/`. Give each test a name that says what
should hold, and put values in the failure message. CI runs the same tests under `cargo llvm-cov` and fails below
85 percent line coverage (`.github/workflows/tests.yml`).

## Media

Images and video are gitignored; only `docs/media/*.gif` and `docs/demo/*.png` are tracked, and every byte
committed there stays in the history. Keep a gif under 5 MB (fewer frames or a smaller scale before more colours),
add one only when a page links it, and remove one that nothing links any more. CI fails when `docs/` passes
8 MB. Other previews belong on the site.

## Releases

1. Move the "Unreleased" notes in `CHANGELOG.md` under a new `## <version>` heading.
2. Set the same version in `plugins/beanfx/.claude-plugin/plugin.json`.
3. Merge to `main`, then `git tag v<version> && git push origin v<version>`. The release workflow checks the tag
   against `plugin.json` and publishes a GitHub release with that section of the changelog.
