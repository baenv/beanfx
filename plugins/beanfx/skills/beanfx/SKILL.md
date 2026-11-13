---
name: beanfx
description: Design and draw a pixel-art effect (VFX) from a description or a reference image (/beanfx <description | image>), for any game, engine or video. Asks the open brief knobs, researches the subject, draws it once in Rust on the beanfx kit, then delivers a sprite sheet with JSON, strips, a gif and a preview page, plus suggested upgrades. Use when the owner asks for a new effect, a redraw of one, or a pixelfx effect made better.
argument-hint: <description | image path>
---

# /beanfx: an effect from words or a picture

An effect is code: a small Rust program on the kit crate. The base (shapes, colour) is shade maps of palette
indices; the light (glow) is a separate additive layer. Size, palette, view, density and style come from the
brief; no house style applies unless the owner gives one.

## The run: one pass, then suggest

Every run takes these steps once, in this order:

1. **Setup**: build the binary.
2. **Gate and questions**: ask only the knobs the prompt leaves open (section 1).
3. **Research** the subject on the web (section 2); it also shapes the `shape` question.
4. **Brief** in the reply, 6 lines. Write no draft file before it.
5. **Scaffold the draft** (`setup.sh --draft <name>`), then **draw once** on the runner `dr`: the peak frame first, one look, then the other frames (section 2).
6. **Run and fix only failures**: a check that exits 1, an error that exits 2, a part missing or cut off at 1x
   (section 3).
7. **Deliver** the preview page, the gif and 3 to 5 suggested upgrades (section 4).

Generate what the brief asks for and stop. Never start an upgrade loop on your own: no extra look-and-fix
rounds, benchmark passes, shape takes, glow takes or polish against the craft gates. Each round costs the owner
minutes. What would make the effect better goes into the suggested upgrades, and one is applied only when the
owner picks it (section 5).

## Files in this skill (`${CLAUDE_SKILL_DIR}`)

Read a file when its row applies, not before.

| file | read when |
|---|---|
| `knobs/<knob>.md` | building the question for an open knob |
| `research.md` | researching the subject; tracing an object from a reference image |
| `kit/DRAFTS.md`, `kit/API.md` | before writing `src/main.rs`: the draft shape, every call's signature, what a run writes and checks. Read these two, never the kit source. |
| `craft.md` | before the first drawing (gates, parts that read, states derived from the peak); later for fixes and takes |
| `light.md` | before drawing the light: style, sparkle, the glow and clarity tables, the measure |
| `caster.md` | the brief has a caster (mockup or game character), a combo, a placement or an aura |
| `export.md` | filling hits, poses, target, directions, caster to target parts, or sound |
| `pixelfx.md` | the owner asks for reuse or picks the benchmark |
| `porting.md` | the owner asks how to import the sheet or port the draw code to an engine |
| `vfx_notes.md` | sources and more examples for an owner new to VFX |

## Setup (first, every run)

```
bash ${CLAUDE_SKILL_DIR}/setup.sh                  # builds the beanfx binary (cargo) into .beanfx/bin/beanfx
bash ${CLAUDE_SKILL_DIR}/setup.sh --draft <name>   # after the brief: drafts/<name>/ with its own kit/
bash ${CLAUDE_SKILL_DIR}/setup.sh --pixelfx        # only for reuse or the benchmark: node 18+ and pixelfx
```

Everything lands in the project (its git root, else the current folder; `BEANFX_PROJECT` overrides it). The first
build takes about a minute. On exit 1, report the line it printed and stop; the script never installs cargo
(https://rustup.rs) or node. Each draft carries its own copy of the kit, made once and never overwritten, so a
plugin update leaves a finished draft as it was (`--kit-status` lists drafts behind the skill's kit,
`--draft <name> --refresh-kit` recopies one). A kit fix goes into the skill's `kit/` first, then into the current
draft's `kit/` by hand. Leave other drafts in `drafts/` unread unless the owner names one.

## 1. Brief (write it in the reply, 6 lines)

Each knob is a file in `knobs/`: what it is, when the prompt fixes it, the question with its options, and the
default. In order: `role`, `view` (and directions), `size`, `timing`, `loop`, `shape`, `style`, `palette`, `glow`,
`clarity`, `density`, `states` (multi-state effects), `caster`, `combo` (how a combo's hits are triggered),
`placement` (where a cast lands against the caster), `aura` (what shows round the caster while it casts) and
`sound` (asked only when the request asks for sound).

**Gate: which knobs to ask.** Run it on the owner's prompt, with one line on what a reference image shows when
there is one:

```
<project>/.beanfx/bin/beanfx gate - --context "<what the image shows, or nothing>" <<'PROMPT'
<the owner's prompt, verbatim>
PROMPT
```

- `"source": "jev"`: Jev (an optional prompt classifier, used only when its client is installed) decided. `ask`
  lists the knobs to ask, in order; `skip` the ones the prompt fixes or that do not apply. Follow it. Override
  one only when the owner's words plainly contradict it (the prompt gives "64x48" and `size` is in `ask`), and
  say so in one line.
- `"source": "model"`: the default without Jev (or with `BEANFX_GATE=model`). Read each knob file's "Fixed when"
  and "Applies" and decide yourself. A knob counts as fixed only when the prompt states it or an image shows it;
  the subject's colour or name alone fixes neither palette nor shape.

**Ask, one question per knob.** For each knob in `ask`, read its file and build the question from its "Ask" part:
2 to 4 concrete values, the recommended one first and marked "(Recommended)", each saying what it does to the
result. Send them with AskUserQuestion, at most 4 per call, in the gate's order; a later call waits for the
answers when its options depend on them (a top-down view changes which shapes read). `states` may take more than
one question. `glow` is asked like any other knob, with its ASCII preview; medium when the owner leaves it open.

**Explain for an owner new to VFX.** A thin prompt (a subject only, no words like fps, loop, glow or palette)
means the owner may not know the terms. Then each question gets one plain line saying why it matters, each
option's description gets its "Examples" line from the knob file, and every option carries the ASCII `preview`
its knob file shows, so the owner picks by sight. Use plain words ("how long the hit freezes the screen", not
"hit-stop").

When the owner says "just do it", "go ahead" or answers "Other" with free text, take the recommended values for
the rest and go.

**The brief**, after the answers or when nothing is asked, is 6 lines in the reply: role and where it plays; view
and directions (and the cast, travel and impact split when it goes from a caster to a target); size, frame count,
fps, loop; palette and light hue; style, glow and clarity; shape and beats. Under it, a short "Chosen for you"
list: each knob you set without asking, its value, and one alternative with its effect ("16 fps, 1.4 s; 12 fps
for a heavier, slower feel"). A multi-state effect also gets its state table (`knobs/states.md`).

From an image of an effect take principles only (shape language, beats, colour bands). Never copy a shape, layout
or glyph, and never recreate a specific game's effect. An object's structure (a dragon's anatomy, a sword's
parts) may be traced from a reference (`research.md`); the trace is a base to redraw in the effect's palette and
style, never the final pixels.

## 2. Research, then draw once

**Research first, from scratch by default.** Before the beats and the carrier are fixed, look the subject up on
the open web, following `research.md`. For a named move, spell or creature: its source, how it is described or
drawn, its element, motion and the parts it is known by. For a plain effect (fire, lightning, ice, smoke): how
the real thing moves, breaks up and changes colour. Put 3 to 5 findings with links in the reply and build the
brief from them. pixelfx effects and earlier drafts are reused only when the owner asks (`pixelfx.md`).

**Objects get their true shape.** When the prompt names an object or creature (a dragon, a sword, a lotus),
research its structure per "Objects" in `research.md`: the parts in order, their proportions, how they join, and
the silhouette that makes it read. Write that part list in the reply and draw the peak frame against it. When
the shape is open, draw the strongest reading from the research and name the other readings in the suggested
upgrades.

**Write the draft on the runner.** `drafts/<name>/src/main.rs` holds a `Spec` (the brief as data) and
`Effect::draw` (one frame on a `Canvas`); `dr::main` writes every output and runs every check. Read
`kit/DRAFTS.md` and `kit/API.md` first. Write the file in pieces, never as one large Write: the spec and the
main element, a look, then the other elements with Edit.

```
cd drafts/<name> && cargo run --release -q                 # every output and check; exit 1 a check, 2 an error
cargo run --release -q -- look <frames>                    # just those frames at 3x, in a second
```

**Peak first.** Draw the carrier whole at its peak pose, look at it once (`look <peak>`), then draw the other
frames. States that build up to that shape or break down from it take their points from the peak drawing with
`dv` (table in `craft.md`), never from hand-placed points.

**What makes the first drawing read** (the full gates and the parts that read are in `craft.md`):

- A clean silhouette at 1x and one focal point that is on screen in every phase, the anticipation included.
- 3 to 5 hue-shifted tones per material; the base reads without the light.
- Repeated parts in three sizes, grouped, with gaps. Overlapping parts of one mass are one shade map, shaded once.
- Separate parts that cross (two dragons in a helix, a body over a palm): give each a depth per pixel, keep the
  nearest, and rim each part where it meets empty space or a part behind it.
- Anticipation, peak, dissolve. A one-shot ends on wisps (its last frame keeps at most 5 % of the peak's pixels);
  a loop has no seam.
- Nothing cut by the cell edge; the subject sits near the middle of its cell.
- Every random choice comes from the seed, so each run draws the same frames.

**Light only what emits** (`light.md` has the values): hot cores, eyes, bolt heads, blade edges, the landing
flash, sparks and embers. Each gets a tight core and a pool; dark space between the lit parts is what makes the
light read. Soft and painterly styles keep the light smooth; hard retro steps it (`lt::steps`) and starts at
about half the gains. Sparks and hits are light that lives 3 to 8 frames (`flash_at`). Set `Spec.glow` and the
clarity from the brief.

**Caster and target.** The sheet is the effect alone: the game draws its own character. A mockup caster, a game
character (`rig`) and the target dummy go into the previews only, and the binding goes into the JSON. Read
`caster.md` when the brief has a caster; time blows on the character's contact frames and take slash arcs from
the rig, never from a guess. Hits, poses, the target, directions and caster to target parts are fields of the
`Spec` (`export.md`).

## 3. Run, and fix only what fails

Run the draft. Each run prints its checks and the light measure and exits 1 when a check fails.

- Fix every check line (edge, empty frame, pop-off, loop seam, seed, framing, budget, act) and every error, then
  rerun. `kit/DRAFTS.md` says what each check means.
- Look at the 4x strip and the contact sheet once. Fix a part that is missing, cut off, or unreadable at 1x.
- When the printed mean falls outside the glow row or the cover outside the clarity row (`light.md`), retune the
  pools once; when it still misses, say so in the report and make it a suggested upgrade.

Then stop and deliver. Anything else you notice is a suggested upgrade.

## 4. Deliver

Report in English:

- The absolute path of the preview page `out/<name>.html` (it opens with a double click, no server), the gif,
  and the sheet and JSON paths.
- The brief, and the state table for a multi-state effect.
- **Suggested upgrades**: 3 to 5 concrete changes, most effective first. Each names the part or knob, the value,
  and why. Draw them from a craft gate the draft misses, the usual fixes (`craft.md`), another reading of the
  shape, glow takes (`cargo run --release -q -- glow`), the benchmark against the nearest pixelfx effect
  (`pixelfx.md`), or a knob such as speed, frame count, light hue, density or size. Apply none until the owner
  picks.

With sound in the brief, write one sound (sound takes are an upgrade); the report says the sound is synthesised and lists its files (`export.md`). With no
sound in the brief, write no audio.

## 5. Follow-up requests (after a draft is delivered)

Each later message about the effect (a picked upgrade, a change request, a comment, a complaint, a question)
gets a recommendation, whether or not it asks for one:

1. Name the purpose behind it in one line: what the owner wants the effect to read or feel like ("hits harder",
   "reads at 1x", "matches the caster's colour"). When a vague comment fits two purposes, ask one question first.
2. Do what was asked, one change per pass, and rerun the draft.
3. Then recommend 1 to 3 changes that serve the same purpose, most effective first. Each names the knob or part,
   the value (fps 24 to 30, glow medium to strong, 3 more sparks on frames 4 to 6), and why, drawing on the usual
   fixes in `craft.md`. Apply none of them until the owner picks.
4. When the asked change works against the purpose (more glow to read better, when the draft is already washed
   out), say so with the reason and give the change that would get there; still do what was asked unless the
   owner changes it.

A question or comment with no change in it gets the answer, then the same recommendation list.
