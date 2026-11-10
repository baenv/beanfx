---
name: beanfx
description: Design and draw a pixel-art effect from a description or a reference image (/beanfx <description | image>), for any game, engine or video. Researches the subject on the open web, then draws the base in Python (fxlib and fxkit shapes, own palette and size); only when the owner asks for reuse does it start from a pixelfx effect or an earlier draft, keeping its light (the glow) while redrawing or recolouring its base. Previews as strips and gifs, and exports a sprite sheet with JSON. Use when the owner asks for a new effect, a redraw of one, or a pixelfx effect made better.
argument-hint: <description | image path>
---

# /beanfx: an effect from words or a picture

Effects are code. The base (shapes, colour) is drawn in Python as shade maps of palette indices; the light (glow)
is a separate additive layer. The default start is research on the subject, then a base and light drawn from
scratch. pixelfx and earlier drafts in `drafts/<name>/` are reused only when the owner asks; then
take pixelfx's light (it reads well) and redraw its base (often weak: blobs, flat fills, smooth teardrops).

Paths: the skill is self-contained in the project you run in (its git root, else the current folder). This
skill's folder is `${CLAUDE_SKILL_DIR}` and holds `setup.sh`, `gate.py`, `knobs/`, `research.md`, `vfx_notes.md`, `porting.md`, `runtime/beanfx.js`, `tools/layers.mjs` and the source of the drawing
kit. `setup.sh --draft <name>` copies the kit into the draft's own `drafts/<name>/kit/` (`fxkit.py`, `fxlib.py`, `light.py`, `pfx.py`, `caster.py`
the mockup caster, `target.py` the preview target dummy, `ref.py` an object traced from a reference image, `facing.py` the direction fields for the JSON, `derive.py` points taken from a finished
drawing, `rig.py` the owner's game character as the caster, `export.py` the sheet, its Aseprite-style JSON and the checks). Each `--draft` run also writes `kit/skill.txt`, the skill path `ex.page` takes the preview template from, so pages always use the current `tools/preview.html`. The copy is made once and never overwritten, so a plugin update leaves each existing draft on the kit
it was drawn with. A kit fix goes into the skill copy first, then into the current draft's `kit/` by hand; other
drafts get it only when the owner names them (`setup.sh --kit-status` lists the drafts whose kit is behind; `setup.sh --draft <name> --refresh-kit` copies the current kit into a named one, then run that draft and compare). Drafts are `drafts/<name>/` in the project, Python is
`.venv/bin/python` there. Older drafts without their own `kit/` import the project's root `kit/`; leave it as it is.

## Setup (first, every run)

```
bash ${CLAUDE_SKILL_DIR}/setup.sh             # .venv with numpy and pillow, checks the kit imports
bash ${CLAUDE_SKILL_DIR}/setup.sh --draft <name>   # once the draft is named, before its first file: drafts/<name>/kit/
bash ${CLAUDE_SKILL_DIR}/setup.sh --pixelfx   # reuse (2b) and the benchmark: also node 18+ and pixelfx
```

It checks each tool and installs only what is missing, in the project: the venv (uv, else `python3 -m venv`),
with `--draft <name>` the draft's `kit/` copied from this skill's `kit/` (only when that folder is missing), and pixelfx, a clone of
`https://github.com/patch-gg/pixelfx` into the project's `pixelfx/`. With `--pixelfx` it checks each use apart:
the benchmark needs `render.mjs` and `list.mjs` and prints `PIXELFX=<dir>` (run them from that dir); reuse needs
this skill's `tools/layers.mjs`, which runs on pixelfx's `tools/lib/fxlib.mjs`, and prints `LAYERS=<script>`.
`BEANFX_PROJECT` overrides the project folder. On exit 1, report the line it printed and stop; node itself is
never installed by the script.

An effect is for any game, engine or video. Size, palette, view, density, alpha and style come from the brief;
no house style applies unless the owner gives one.

## 1. Brief (write it in the reply, 6 lines)

Each knob lives in its own file in `knobs/` (this skill's folder): what it is, when the prompt fixes it, the
question to ask with its options, and the default. In order: `role`, `view` (and directions), `size`, `timing`,
`loop`, `shape`, `style`, `palette`, `glow`, `clarity`, `density`, `states` (multi-state effects), `caster` (mockup caster), `combo` (how a combo's hits are triggered), `placement` (where a cast lands
against the caster), `aura` (what shows round the caster while it casts).

**Gate: which knobs to ask.** Run it on the owner's prompt, with one line on what a reference image shows when
there is one:

```
python3 ${CLAUDE_SKILL_DIR}/gate.py - --context "<what the image shows, or nothing>" <<'PROMPT'
<the owner's prompt, verbatim>
PROMPT
```

- `"source": "jev"`: Jev (an optional prompt classifier, used only when its client is installed) decided. `ask` lists the knobs to ask, in order; `skip` the ones the prompt
  fixes or that do not apply to this effect. Follow it. Override one only when the owner's words plainly
  contradict it (the prompt gives "64x48" and `size` is in `ask`), and say so in one line.
- `"source": "model"`: the default when Jev is not installed or turned off (`BEANFX_GATE=model`). Read each knob file's "Fixed when" and "Applies" and decide
  yourself; a knob counts as fixed only when the prompt states it or an image shows it, and the subject's colour
  or name alone fixes neither palette nor shape.

**Ask, one question per knob.** For each knob in `ask`, read its file and build its question from the "Ask" part:
2 to 4 concrete values, the recommended one first and marked "(Recommended)", each saying what it does to the
result. Send them with AskUserQuestion, at most 4 per call, in the gate's order; the next call goes after the
answers when its options depend on them (a top-down view changes which shapes read). `states` may take more
than one question.

**Explain for an owner new to VFX.** A thin prompt (a subject only, no words like fps, loop, glow or palette)
means the owner may not know the terms. Then each question gets one plain line saying why it matters, each
option's description gets its "Examples" line from the knob file (what it looks like in a known game and when to
pick it), and size, timing and shape options carry an ASCII `preview`. Use plain words in the text the owner reads
("how long the hit freezes the screen", not "hit-stop"). `vfx_notes.md` holds the sources and more examples.

Research the subject (section 2a) before the `shape` question, so its options come from how
the subject is known. When the owner says "just do it", "go ahead" or answers "Other" with free text, take the
recommended values for the rest and go.

**The brief**, after the answers or when nothing is asked: write it in the reply as 6 lines (role and where it
plays; view and directions, and the cast, travel and impact split when it goes from a caster to a target; size,
frame count, fps, loop; palette and light hue; style, glow and clarity; shape and beats). Under it a short "Suggestions"
list: each knob you chose without asking, the value, and one alternative with its effect, such as "16 fps, 1.4 s;
12 fps for a heavier, slower feel". A multi-state effect also gets its state table (`knobs/states.md`).

Order, every run: gate, questions, brief with "Suggestions" in the reply, and only then draw. Write no draft file
before the brief is in the reply. Web research may run before the questions when it shapes their options.

From an image of an effect take principles (shape language, beats, colour bands) only. Never copy a shape,
layout or glyph, and never recreate a specific game's effect. An object's structure (a dragon's anatomy, a
sword's parts) may be traced from a reference (section 2a); the trace is a base to redraw in the effect's
palette and style, never the final pixels.

## 2. Base

Research and draw from scratch by default. Reuse only on request.

a. **Research, then from scratch (default).** Before the brief's beats and carrier are fixed, look the subject up
   on the open web, following `research.md` in this skill's folder. For a named move, spell or creature
   (Eighteen Dragon-Subduing Palms, a sword art): its source, how it is described or drawn, element, motion and the
   parts it is known by. For a plain effect (fire, lightning, ice, smoke): how the real thing moves, breaks up and
   changes colour. Put 3 to 5 findings with links in the reply and build the brief from them.

   **Find the reference in the same pass** (when `setup.sh --pixelfx` is set up), per "Benchmark" in section 3:
   the pixelfx effect nearest the prompt. When the prompt matches one closely (its words or its description in
   `docs/CATALOG.md`), say so in the reply before the questions: "This reads like pixelfx `<id>`; I will
   benchmark against it." Its size and length are data for the size and timing options, never a shape to copy.

   **Objects get their true shape.** When the prompt names an object or creature (a dragon, a sword, a phoenix,
   a lotus, a tiger), research its structure before drawing, per "Objects" in `research.md`: the parts in order,
   their proportions, how they join, and the silhouette that makes it read. Write that part list with
   proportions in the reply and draw the peak frame against it; a dragon with the wrong head, horns or claws, or a
   sword with a wrong guard or blade, is not done however good its light.

   **Skeleton from a reference image** (when the owner asks for the skeleton, the true structure, or gives a
   detailed image of the object): reverse the image with `kit/ref.py` instead of drawing the structure by eye.
   `t = ref.trace(path, height=<the object's size in the cell>, tones=<the style's tones>)` takes the derivative
   of the image (Sobel gradient) for the outline and the inner lines (`t.edges`), the value levels for how light
   each part is (`t.shade`, 0 darkest), and the skeleton (`t.spine`, centre lines). Then fill by it: `ref.paint(t,
   ramp_index, edge)` maps the levels onto the effect's own ramp and inks the edges, the light goes on top, and
   `t.outline` and `t.spine` feed `kit/derive.py` for the build-up and break-down states. Use a reference the
   owner gave, a photo of the real thing, an anatomy or reference sheet, or public-domain art, and put its link
   in the reply. Clean the traced map by hand where the trace is noisy at the target size (stray pixels, broken
   lines), keeping its proportions.

   Then shapes come from
   `kit/fxkit.py` (`lumpy`, `ball`, `trail_puffs`, `streaks`, `puff`, `facets`, `kite`, `leaf`, `drop`,
   `twinkle`, `hit_burst`, `claw_tracks`) and `kit/fxlib.py` (`stroke`, `outline`, `checker`,
   `ground_ring`, `ramp`, `wgrid`, `noise`, and `Pen(px, py, density)`, whose `put` and `line` take the same
   world px as `grid` and `wgrid`, so no draft converts to sheet px by hand); light from `kit/light.py` (`glow`, `glow_line`, `glow_ring`,
   falloff `(1 - d)^2 * k`); output with `kit/pfx.py` (`paint`, `composite`, `strip`, `gif`, `contact`). A draft puts its own
   `kit/` on `sys.path` (`sys.path.insert(0, str(HERE / "kit"))`). These are generic; use your own palette and size. Leave other drafts in `drafts/` unread.

   **Light stays smooth in every style.** Sum the glows into one float map `L`, then colour it with
   `pfx.tint(np.repeat(np.clip(L, 0, 1)[..., None], 3, -1), [deep, hue, pale, "#ffffff"])` and pass that to
   `pfx.composite` as is. The style knob sets the colour pixels (outline, dither, opaque); it never sets the
   light. `light.bands`, `light.palette` and hand-made step cuts are only for an owner who asks for stepped light
   in words ("NES authentic", "no smooth glow"): cut into 3 steps the glow turns into a flat outlined halo, and
   the bloom at a pop or a flash, the part that makes the moment read as bright, is lost. Light only what
   emits: hot cores, eyes, bolt heads, blade edges, the landing flash, sparks and embers. Stack two lights on
   each of those, the way pixelfx does: a tight core (r 4 to 15) and a pool along it. Dark space between the
   lit parts is what makes the light read; a glow over the whole cell reads as haze.

   **Sparkle is light that lives a few frames.** Give every spark, glint, sword entry and hit a `light.Flashes`
   light that starts at its k and dies in 3 to 8 frames (`light.flash_at(L, c, f, f0, x, y, r, k, life)` draws it
   from the frame alone, so `render(f, seed)` stays per frame for `check_seeds`; `Flashes` keeps state between
   frames and suits only a loop that draws frames in order), and multiply the k of lasting glints by
   `light.flicker(i, f, seed)` so they blink out of step. Draw the glint itself as opaque pixels (`fxkit.twinkle`,
   a white heart). A big move wants dozens of these at its peak; pixelfx myriad-swords carries 400 to 800 bright
   points a frame and its light changes about three times as much between frames as a draft lit by still pools.

   **Glow level** (a brief knob: subtle, medium, strong; medium when open) sets how bright the lit parts are:

   | level | core k | pool along a part | mean |
   |---|---|---|---|
   | subtle | 0.25 to 0.5 | r 2x, k 0.2 x core | 0.04 to 0.07 |
   | medium | 0.3 to 0.7 | r 2.5x, k 0.4 x core | 0.06 to 0.10 |
   | strong | 0.3 to 0.7 | r 3x, k 0.45 x core | 0.08 to 0.14 |

   **Clarity** (a brief knob: clear, balanced, hazy; clear when open) sets where light and colour may spread:

   | clarity | scene pool k (peak) | colour alpha | cover |
   |---|---|---|---|
   | clear | none | solid: alpha 1 except smoke, mist and fades | 5 to 20 % |
   | balanced | 0.05 (0.2), r 1.5x the focal part | mist at 0.3 to 0.7 | 20 to 40 % |
   | hazy | 0.12 (0.4), r 50 to 70 | translucent volumes | 40 to 80 % |

   When the effect is itself the light source (a torch, a portal, an orb, an aura round a body), its cover runs
   60 to 100 % at any clarity; then judge clarity by the dark ground round it and by solid colour pixels.

   Cover is the share of the drawing's box (the colour alpha's bounding box, per frame, median over frames) with
   light above 0.03; mean is the median light of those pixels. Measured on pixelfx: myriad-swords 15 % at 0.09,
   lightning-call 6 % at 0.06, meteor-call 8 % at 0.07, hit-spark 5 % at 0.06; torch 97 % at 0.19 and portal
   100 % at 0.12 are light sources. `van_kiem_quy_tong_v4`, lit by the old single table, read hazy at 70 % and 0.13.
   Strength above medium goes into the pools round emitters, never the core or the pool along a stroke: past about
   0.45 x core along a 1 px line the light sums to white and buries the line (tested on `drafts/aura_thunder_v3`).

b. **Reuse (only when the owner asks):** the owner says reuse or pixelfx, names a pixelfx id, or names
   an earlier draft. For a named draft, read it and build on it. For pixelfx, find the nearest effect in
   `docs/CATALOG.md` of the pixelfx dir (every effect by category), look at it with
   `cd $PIXELFX && node tools/render.mjs <id> --gif` (`--opts '{"palette":[...]}'`, `--seed`, `--fps`), then split
   it into layers:

   ```
   node $LAYERS <id> --out <draft>/src --pixelfx $PIXELFX [--opts JSON] [--seed N] [--fps N]
   ```

   It writes `<name>_color.png` and `<name>_light.png` (frames left to right) and `<name>.json` (w, h, fps,
   frames, loop, pivot). In the draft, `kit/pfx.py` loads them (`pfx.load`) and gives `tint` (same glow,
   new hue ramp), `gain`, `keep` (light only under a mask, such as your own shape grown by a few px), `bands`
   (stepped light, only when the owner asks for it), `paint` (shade map to RGBA), `composite`, `strip` and `gif`. Usual use:
   keep the light, redraw the colour base yourself on the same frames and pivot, follow pixelfx's motion
   (positions, timing) where it is good. Recolour only (`tint` plus `--opts palette`) when the base already reads.

Drafts live in `drafts/<name>/` of the project (`<name>.py`, output in `out/`, run with
`cd drafts/<name> && ../../.venv/bin/python <name>.py`). Overlapping parts (two dragons in a helix, a body over a palm): give each part a depth per pixel, keep the
nearest, and rim each part where it meets empty space or a part behind it, so the crossing reads at 1x.

**Peak first, then derive.** Draw the carrier whole at its peak pose before any other state, and judge that frame
at 1x and 4x until it reads, then run benchmark pass 1 (section 3) on it before drawing any other frame. Give its draw function a `trace=True` mode that returns the shade map and a part-id
map (skull 0, jaw 1, horn 2, and so on; -1 empty) in the carrier's own frame. Every state that builds up to that
shape or breaks down from it then takes its points from those maps with `kit/derive.py`, never from hand-placed
points, so a change to the drawing moves every state with it:

| state | from the peak drawing |
|---|---|
| constellation, trace, outline flash, sketch-in | `simplify(outline(m), n)`: n corners round the silhouette, in order |
| inner lines (jaw, eye, horn roots, armour seams) | `part_lines(parts)`, each chain through `simplify(c, n, closed=False)` |
| a body that uncoils or grows along its length | `spine(m)`: ordered centre lines |
| gather, assemble, motes landing | `scatter(m, n)`: even landing spots inside |
| shatter, dissolve, break into motes | `scatter(m, n)` for the start points, so the pieces leave from what was on screen |

Store the points with `derive.local(P, anchor, ang, scale)` and place them each frame with `derive.world(...)` at
the carrier's pose for that frame. Learnt on `drafts/tinh_long_chuong`: the constellation traced from the solid
head lands on it exactly.

**Takes when the direction is open.** When the owner did not pick the shape (it went to its default after "just
do it", or the owner asks for options), draw 2 to 3 genuinely different takes of the peak frame only, each from a
different reading in the research (a coiled dragon, a dragon in a dive, a dragon head alone). Put them side by
side at 4x on the dark ground in `out/takes.png`, show it, and ask which one with AskUserQuestion before drawing
any other frame. Delete the code of the takes not kept.

**Mockup caster** (only when the brief says yes): `kit/caster.py` draws a golden robed silhouette with no face,
glowing at max, plus an optional avatar. The style: 5 gold tones (`cs.BODY`) shaded by neighbour (a step up
where the top-left is empty, a step down at the bottom-right), wide sleeves and three robe flaps that trail back,
hair and flaps that lift with `lift` and flap with `flut`, and a two-finger sword sign whose tip glows. Use:

```
import caster as cs
pose = cs.pose_at(f, [(0, "chest"), (28, "raise"), (98, "pull"), (103, "point")],
                  [(0, "rest"), (28, "out"), (103, "behind")], cs.aim_from(foot, sc, target), jab)
g = cs.draw(fr.over, (H, W), foot, sc, pose, f, lift, flut, hair="loose")   # over(ys, xs, rgb, a)
cs.body_light(L, g, charge); cs.finger_light(L, g, point, jab)
gg = cs.draw(fr.over, (H, W), (foot[0] - 4, foot[1] - 6), sc * 1.27, pose, f * 0.7, lift * 0.6, flut * 0.7,
             ghost=k)                                                     # avatar, drawn first (behind)
cs.ghost_light(fr.over, L, gg, k, f, point)
```

**Game character caster** (the brief picks "Game character"): `kit/rig.py` reads the owner's sprite sheets from
`casters/<name>/rig.json` in the project (frame size, fps, pivot at the feet, animations with frame counts and
contact frames, and per direction the sheet of each row). Four casters ship with the skill in its own
`casters/` and load by name with no setup when the project has none of that name: `nghich_tien_kiem` and
`nghich_tien_truong` (a robed cultivator with a straight sword or a staff, side, east and west) and their
`_topdown` versions (8 directions), each with idle, run, cast, attack1 to 3, hurt and dead. A project's own sprites
in `casters/` are the owner's licensed art: they stay local (gitignored) and never go into the plugin or the sheet.
Draw the effect in the character's frame space, so it drops into that game as it is:

```
import rig
r = rig.load("knight_side")                       # casters/knight_side/rig.json
PIVOT = (56, 84)                                  # the character's feet on the effect canvas
K = FPS // r.fps_of(anim)                         # effect frames per character frame (a row may set its own fps)
t = START + f / K                                 # character time of effect frame f; r.contact(anim) for the hits
char = r.place((H, W), PIVOT, anim, f // K, direction, start=START)   # preview only
prev = pfx.composite(rig.over(color, char), light)
a0, a1 = r.arc(anim, direction, 0)                # the slash runs with the blade
problems += r.check_arc(anim, a0, a1, direction, 0)
meta["caster"] = r.meta(anim, FPS, start=START)  # into ex.write(extra=...)
```

- The effect fps is a whole multiple of the animation's fps (`r.fps_of(anim)`); `r.meta` refuses any other. A row
  with uneven frame times (rig.json `ms`, from a game) goes into the JSON as `char_ms`, and the engine holds the
  effect frames by those times.
- Directions of a game caster: a side (horizontal) effect uses 2 rows, east and west, each drawn on the
  character's own row of that name (`fc.rows(draw, 2, n)`, `fc.meta("side", ..., directions=2)`), since the
  character holds its weapon in one hand and west is not a mirror. A top-down effect uses all 8 rows
  (`fc.rows(draw, 8, n)`, order `facing.NAMES8`). A rig with one side row (`facing` only) keeps the mirrored
  single row.
- Time the blows on the character's contact frames, not on a guess. Character sheets come without baked smears
  (white arcs in the attack frames), so the effect's slash is the only one; strip them from a bought pack first
  and keep the original in `casters/<name>/orig/`.
- A combo on a game character follows the `combo` knob. One press per hit: draw one clip per stroke and weight,
  each from its animation's frame 0 to wisps, write `caster.combo.steps` (state, anim, char_from, char_to the
  frame the swing ends on, contact, weight) and `caster.chain` (each clip on its animation, for the viewer), and
  preview the whole string with every press on time by laying the clips on the timeline. `drafts/thap_tram` is
  the reference.
- Follow the sword. rig.json `swing` gives each stroke's turn (cw or ccw on screen), `from` and `to` angles
  (0 east, 90 south, y down) and frames. Take a slash arc from `a0, a1 = r.arc(anim, direction, stroke)` (a1 - a0
  carries the turn), never from a guess, and add `r.check_arc(anim, a0, a1, direction, stroke)` to the draft's
  problems so a wrong turn or an end over 60 deg off exits 1. Time the arc's head on the stroke's frames.
  `r.meta` carries `swing` and `pixel_scale` into the JSON. `swing` fixes the turn and the ends, not where the
  blade is on the contact frame: put the smear's head on the blade tip measured from that frame of the sprite (the
  weapon's own colour, the pixel farthest from the hand; `measure_blade` in `drafts/thap_tram`) and the hit spark
  on rig.json `emit` (the weapon tip). A smear placed by eye or toward the target runs ahead of or behind the
  blade. A stroke near 180 deg (an overhead chop) swings in the upright plane of the heading: squash it across by
  |cos heading|, and facing away, end it at the ground in front (`plane` in the same draft).
  Top-down, the way round comes from the camera: when the blade jumps from `from` to `to` in one character frame
  the sprite cannot show which way it went, and rig.json's turn is only the shorter screen path. A cut sweeps the
  side the character faces, so draw the way round that passes the heading (the other way when the rig's way runs
  behind the body, as on a character facing the camera), and check that the blade's tip on the contact frame
  lies on the drawn arc in place of `r.check_arc`. Record the drawn way in `caster.swing_drawn`.
- A cast that lands away from the body (a summon, a strike from the sky, a ground blast) follows the `placement`
  knob: the sheet's pivot is the struck spot and `r.meta(anim, fps, start, offset=range)` writes
  `caster.offset` (per direction the `[dx, dy]` from the character's pivot to the effect's pivot) and `range`.
  Never leave such a cast on the character's own pivot: the engine then plays it on the caster's feet. Learnt on
  `drafts/thien_kiep`, whose first cut struck under the caster in the game.
- The caster shows the power it calls, per the `aura` knob: `aura_back` and `aura_front` parts in
  `meta.beanfx.parts` (anchor caster, layer behind and front), each its own sheet from `ex.write` on the effect's
  frames and palette, its JSON named in the part's `json`. A part that follows the hand or weapon (rig.json
  `emit`) takes one row per caster direction. `drafts/thien_kiep` is the reference.
- Moving animations (a dash): frames stay in place and rig.json `root` gives the body's travel per frame
  (`r.root(anim, direction)`). The effect stays where the move began: size the canvas for the whole travel, preview
  with `r.place(..., travel=True)`, and put trails and afterimages at earlier `root` points; `r.meta` carries `root`.
- The example casters (`knight_side`, `adventurer_topdown`) are references to learn from: proportions, cell size,
  pivot, frame counts, fps, contact frames, swing and root motion. A caster that needs a new look or a missing
  animation is an original character built to the same rig.json contract (the `/char` route), never a recolour,
  edit or composite of the example sheets; `casters/build.py` only cleans the local references.
- A caster composed from the owner's game sheets builds each row the way the game draws it, never from the baked
  layers alone. Take the game's own row for the weapon (a staff runs on the staff's own run row, not the generic
  run). On rows where the game draws the weapon in the fist (its swing sprite on a per-frame hand track), draw it
  there on every frame: turned to the track's angle, foreshortened by its length, and split in front of or behind
  the body as the game splits it. Check every moving row at 4x, and fail the build when a held weapon leaves the
  fist: a weapon that holds still while the body bobs is a baked pose for another grip, and the hand slides off it.
  Learnt on `nghich_tien_truong`, whose staff floated beside the hand in the run.
- Top-down: draw rows with `fc.rows(draw, len(r.directions), n)`; their order is the rig's directions.
- A held weapon can dip below the feet, so check each animation's pivot with `r.place` over a ground line before
  drawing; rig.json pivots override the measured ones (`python kit/rig.py <name>` prints both).
- Review in the browser: every draft run writes its own page, `out/<name>.html` (`ex.page`, section 3), that
  opens straight from disk. `<skill>/tools/preview.html` is the template and also opens from disk
  on its own (pick the project folder) to browse every result. The page shows directions, actions (states, tags,
  caster animations), frame stepping, speed, light layer, pivot, cell box, swing arc and root motion; Control mode
  drives the caster with WASD, J and K attack, L dash, and fires the effect. An effect on a chain of animations
  (a combo: `meta.beanfx.caster.chain`, each `{anim, char_from, char_to, effect_from, effect_to}`) shows the
  character of each segment, and J plays the whole chain; animations with rig.json `ms` play by those times. It
  carries `runtime/beanfx.js` inline: after a runtime change run `python3 <skill>/tests/test_preview.py --write`.
- `drafts/rig_slash` is the reference: a side slash on `knight_side` attack1 and a top-down slash in 4 directions
  on `adventurer_topdown` attack1, for the frame space, pivot and timing. Its arcs predate `swing` and run against
  the blade (`check_arc` fails both knight strokes), so take arcs from `r.arc`, not from it.

Draw the avatar before everything else and the caster after the swords behind it. Move the caster with a
`foot_at(f)` path (rise, hover with a 2 px bob, land) and feed `lift` and `flut` from its speed. What made it
read, learnt on `drafts/van_kiem_quy_tong_v2` and `v3` (v3 is the reference draft):
- Keep it shorter than the main carrier; at 104 px and a 270 px avatar the caster took over the effect.
- Keep the core light on a small body low (`body_light` is tuned for 34 px); the pools from the scene, the
  avatar and the hip stack on it, and at core k 0.3 the figure burnt to a white blob.
- Keep every lock, flap and finger at least 1 px (`mw = 0.6 / sc`), or they vanish at small sizes.
- Light the avatar from inside its mask, with a bright rim, a faint fill and a halo; a translucent fill alone
  read as a grey copy.
- Hair grows from the scalp and nape and falls before it streams back; locks drawn from the bun fanned out like a
  broom.

## 3. Draft loop

The draft script writes, each run: the sheet and JSON (section 5), a 4x strip on a dark and on a mid ground, a
4x gif at its fps (`pfx.gif`, through `ex.hitstop` when there are hits) and `out/contact.png`
(`pfx.contact(path, frames, fps)`: 12 moments labelled with frame and time, so timing reads without the gif),
a preview page per sheet, `ex.page(<out>/sheets/<name>.json)`: `out/<name>.html`, the skill's `tools/preview.html`
with the sheets, the JSON and the caster's rig and sheets embedded, so it opens with no folder to pick (it embeds
the owner's caster sprites, so it stays in the gitignored `out/` and is never shipped), and runs the checks on the effect
frames, printing every line and exiting 1 when there is one:

- `ex.check(frames, lights, loop, src=__file__, hold=HOLD)`: colour on the cell edge, light above 0.02 on the edge
  (smooth light spreads wide, so the pool radius leaves a margin to the cell), an empty frame, a one-shot that pops
  off, a loop seam, randomness without a seed.
- `ex.check_seeds(lambda f, sd: render(f, seed=sd)[0], N)`: the edge and empty checks again with seeds 2, 3 and 7,
  every second frame. So `render` takes a `seed` (default `SEED`) and draws every random choice from
  `np.random.default_rng(seed + salt)`; particles a reseed throws further show up here.
- `ex.check_act(act, N, FPS, loop)` when the JSON has an act (below).
 Judge at 1x for read, 4x for detail, the gif for timing.
Change one thing per pass; crop one frame to 5x when the grid hides a problem. Go round at least three times
(look, fix the worst thing, run again) before calling a draft done; a showpiece takes more.

The script also prints the light measure for the glow level and clarity (smooth light only), from each frame's colour `col`
and summed light `L`:

```
ys, xs = np.nonzero(col[..., 3]); box = np.clip(L[ys.min():ys.max() + 1, xs.min():xs.max() + 1], 0, 1)
cover = (box > 0.03).mean(); mean = box[box > 0.03].mean()     # median of each over frames, printed
```

When mean falls outside the glow row or cover outside the clarity row, retune the pools. These numbers are a
floor: a draft inside both rows can still lose by eye (void_pop had cover 19 % and mean 0.118 and lost to pixelfx
implosion). The draft is done when it passes the benchmark below, and every other number in this skill (the
5 % last frame, the edge margin) works the same way.

**Benchmark** (when `setup.sh --pixelfx` is set up). A quality check only: take nothing from its code, shapes or
motion.

- Find the reference with more than one search: `list.mjs` matches plain substrings, so `implode` misses
  `implosion`. In `$PIXELFX`, run `node tools/list.mjs <w>` for each form of the key words (the stem, `implo`;
  the noun and the verb, implosion and implode; synonyms, collapse and suck), then two or three distinctive words
  from the owner's prompt as it stands, and read the matching category table in `docs/CATALOG.md` (explosions,
  impacts, arcane, and so on). Take the one or two closest; say which and why in the reply.
- Pass 1, the peak, before any other frame is drawn: render the reference (`node tools/render.mjs <id> --gif`),
  and put its peak frame and the draft's side by side at the same zoom on the same dark ground. Fix the base,
  size and light of the peak here, while it costs one frame.
- Pass 2, the timeline, before calling the draft done: load the reference with `node $LAYERS <id> --out
  <draft>/ref --pixelfx $PIXELFX` and `pfx.load`, composite its frames, and write `pfx.contact(out /
  "bench.png", draft_frames, FPS, ref=(ref_frames, ref_fps))`: the same moments of both, row over row (`by="phase"`,
  the default, lines up the same share of each length; `by="time"` the same seconds). Read it column by column:
  the focal point in every phase, the anticipation, the peak frame count, the dissolve. A peak frame alone hides
  timeline faults, such as a dark centre for 25 frames before the pop.
- If the reference shows more detail, clearer light or more life at any column, the draft is not done. Note what
  beanfx does better too (a one-shot that ends on a near-empty frame, where pixelfx can waste blank frames).

Usual fixes: mush at 1x, then fewer tones, one focal point, bigger shapes; floaty, then fast in and slow out with
a 1 to 2 frame white-hot peak; stiff, then vary each particle's size, speed and delay and add secondary motion
(sparks, smoke, debris); flat, then a lighter top-left step and a darker bottom-right one; washed out, then less
light and white kept for the hottest core only; glow that floats off the shape, then `pfx.keep` it under a mask of
the base; glow that looks stepped, outlined or dull, then drop the bands and add flashes and flicker on the sparks;
hazy or muddy where the brief says clear, then remove the scene pool, make the colour solid and light emitters only; thick
saturated strokes, then a 1 px white core with 1 px of tinted edge and let the light carry the brightness;
choppy, then more frames at 24 to 30 fps; dithered smoke or mist, then translucent puffs lit on top (hazy only);
clouds like cotton balls, then one lit deck as below.

Parts that read (learnt, not copied): fire and comets are a lumpy head banded white, yellow, orange, red and a dark
edge with broken trailing puffs that shrink and cool; a blow is a flash disc, tapered streaks of mixed length and a
brief ring; an explosion contracts, flashes a core, throws shards or embers, then leaves 3-tone smoke that breaks
up; a cloud deck or smoke mass is one continuous field: noise along its flow (a vortex winds tighter
near the eye), lit from the source inside or behind it (brightest at the inner rim, darker outward, the belly darker
than the top), 5 to 7 hard tone steps, solid pixels, a 1 px pale rim where it meets the light;
a bolt has a bright tip and a ribbon trail with sparkles; rock and ice are faceted with a hard highlight;
lightning is jagged with a white core, short branches and a spark star where it lands; a fire body is shaded by
heat (palest at the core toward the top left, dark flame tone at a ragged edge, no near-black outline);
an implosion, a charge or anything that builds up shows its hot core from frame 0, small and dim, and brightens it
as the inflow pours in, so the eye has a point to hold through the whole anticipation and not only at the peak;
a dark mass on a dark ground (a void sphere, a black hole, a shadow orb) is a filled volume darker than the
ground with a hot rim, and the other parts (streaks, a core, sparks) sit inside or across it: a ring of outline
over an empty middle does not read as a sphere. The same holds for any part close to the ground's value (a white
flash over snow): fill it, rim it in a contrasting tone, and judge it on the ground the game uses.

A loop that flies (a dragon, a serpent) follows a helix or wave that stands still on the ground: phase
`s * tau / lam + tau * f / frames`, the head on the same curve, and the node moves at lam / frames * fps per
second. Judge it in a travel gif; in place it reads as a pole that spins.

## 4. Craft gates

- Clean silhouette that reads at 1x; one focal point; a rim or outline where the style uses one.
- The focal point is on screen in every phase, the anticipation included: a build-up shows its core from its
  first frame, and no stretch of frames leaves the eye without a point to hold.
- Every main part separates from the ground by value: a part near the ground's value (dark on dark, white on a
  light ground) is a filled volume with a contrasting rim.
- A named object or creature matches its researched part list and proportions (or its traced reference).
- 3 to 5 hue-shifted tones per material; the base reads without the light.
- Anticipation, peak, dissolve. A one-shot dissolves to wisps: no empty frame, and its last frame keeps at most 5 %
  of the peak's pixels, so it neither pops off nor wastes a blank cell. A loop has no seam.
  An effect that ends on a held state (an eye that stays open, a seal that stays) passes `hold=True` to
  `ex.check` and `ex.write`; the JSON's `end: hold` tells the engine to keep the last frame or hand over to a loop.
- Randomness only from a seeded `np.random.default_rng(seed)`, so every run draws the same frames.
- Build-up and break-down states land on the peak drawing: their points come from `kit/derive.py` on the peak's
  maps, and the frame where a build-up hands over to the solid carrier shows no jump.
- Light on every hot part (core, heads, landing flash, sparks, embers), each with a wide soft pool and a tight
  core, smooth in every style unless the owner asked for stepped light; white only at the hottest core.
- Benchmark pass 2 (section 3) shows no column where the reference reads better.
- Nothing cut by the cell edge in any frame or direction; the pivot is the drawing's origin.
- The style picked in the brief holds in every frame (dither or translucency, glow strength).
- Every heading row reads as the same effect: draw the shape in the rotated frame (`fxkit.rot`, u along travel)
  but keep the shading light fixed in the world (the lighter step stays top-left in every row), and look at the
  sheet with all rows at 4x. A row that looks thinner or stair-stepped (often the diagonals) gets its own pass.
- A mirrored side sheet still reads when flipped: no text or glyph, no part that must stay on one side. When it
  fails, set mirror False and draw the west sheet.

**Hand over the page, every run.** Give the owner the absolute path of `out/<name>.html` next to the gif; it
opens with a double click (file://), no server and no folder to pick.

## 5. Export

Write the sheets with `kit/export.py` (`import export as ex`):

```
meta = ex.write(OUT, NAME, finals, FPS, PIVOT, LOOP, light=lights, color=cols, states=STATES,
                hits=[ex.hit(PEAK, FPS, weight="heavy", dir=0)],
                poses=[ex.pose(-0.3, "windup"), ex.pose(0.0, "release", "snap"), ex.pose(0.6, "recover")],
                target={"x": 72, "react": "knockback"}, hold=False,
                extra=dict(fc.meta("side", W, H, PIVOT), glow="medium"))
```

- `<name>.png` is colour plus light (`pfx.composite` over transparency), frames in a near-square grid, row-major.
  A sheet that would pass 4096 px a side splits into pages `<name>_p<k>.png`, each with its own Aseprite JSON
  `<name>_p<k>.json` (its frames and the tags clipped to it); `<name>.json` then lists every frame with its `page`
  and the page files in `meta.beanfx.pages`. Frame names stay unique across pages (`<name> 37`).
  `<name>_light.png` (RGB, add it in the engine) and `<name>_color.png` sit on the same grid, so the engine can
  dim or drop the glow; the light sheet keeps the smooth light.
- `<name>.json` is the Aseprite "array" layout: `frames[i]` with `filename`, `frame` {x, y, w, h} and `duration`
  in ms, `meta.frameTags` one tag per state (and per heading row, `east`, `east/strike`), and everything beanfx
  adds under `meta.beanfx`: fps, loop, frames, rows, frameSize, pivot, columns, the files, `blend_light`,
  `light_gain` (1.0; the engine multiplies the light sheet by it to tune the glow at runtime), `states`, `glow`
  and the direction fields. Phaser loads it with `load.aseprite`; `porting.md` in this skill's folder has the
  import for each engine, and `runtime/beanfx.js` plays it in a browser game with no engine.
- **The act** for a blow, a strike, a cast or an impact: plain data in `meta.beanfx.act` that the game's own
  character and target follow.
  - `hits`: one `ex.hit(frame, fps, weight=..., dir=...)` per contact. **Weight sells the hit**: pick it from
    `ex.WEIGHTS` (light, heavy, finisher, blast) to match how hard the blow looks, and it sets the freeze (hit-stop,
    past 0.3 s it reads as a stall), the shake and how long it lasts, the push, the react (none, flinch, stagger,
    knockback, launch), how long the target flashes white and the sound cue `hit_<weight>`; any field given
    explicitly wins. `dir` is the way the blow travels (degrees, y down, 0 along the facing): the shake and the push
    follow it, so a downward smash shakes up and down and a rising uppercut lifts. A combo escalates: light, light,
    heavy, finisher.
  - `poses`: keys `ex.pose(t, name, how)` from `ex.POSES` (idle, guard, windup, cast, channel, release, follow,
    recover), t in s from frame 0, negative before it; "snap" jumps on the key. The game maps each name to its own
    animation. A wind-up the opposite way to the blow, the release on the contact frame or just before, a recovery.
  - `windup`: the seconds the character starts before frame 0; taken from the first pose key when that is earlier.
  - `target`: {x: px from the pivot along the facing, react}.
  The game starts the character `windup` s early, plays the poses, and at each hit freezes everything for
  `freeze` s, shakes along `dir` for `shake_time`, flashes the target for `flash` s, pushes, plays the react and
  the `sound` cue on the contact frame (sound, freeze, flash and shake within one frame of each other).
- **The ground answers a blow that lands on it.** `fk.ground_impact(m, X, Y, f - contact, FPS, tones, dust, cx, cy,
  r, weight)` adds dust kicked out along the ground, debris that arcs, bounces once and rests where it lands, and
  cracks for heavy, finisher and blast weights; use the same weight as the hit. Put it under the blow for a ground
  strike, a slam, a landing or an explosion; leave it out for a hit in the air or on a body.
- **The sheet is the effect alone.** The game draws its own character, so the mockup caster and the target dummy
  go into the previews only (the 4x strips and the gif), and so does a game character (`kit/rig.py`); its JSON
  binding goes in `meta.beanfx.caster`. `render(f, seed, caster)` draws with or without the
  caster; export and check the frames without it. For a hit, put `kit/target.py` under the preview at the
  target's foot (`tg.under(frame, tg.draw((H, W), foot, f, hits, FPS, facing=-1))`), so the gif shows the body
  taking the blow.

**Directions in the JSON (every sheet).** The engine plays the effect from any side, so the JSON says how. Build
the fields with `kit/facing.py` (`import facing as fc`) and pass the whole meta through `fc.check` before writing:

- `fc.meta(view, w, h, pivot, directions, facing, mirror, target)` writes `view`, `directions` and, for one
  direction, `facing` (east by default), `mirror`, `mirror_pivot` and `mirror_target` (x becomes w - x). With
  `mirror` False, draw the west sheet (`fc.mirror(frames)` as the start, then fix what reads wrong) and list it
  as `sheets.west`.
- With 8 or 16 directions, draw each heading with `fc.rows(draw, n, frames)` (draw(a, f), a the heading) and
  pass the rows to `ex.write`, which lays heading k after heading k - 1 and tags each: row k faces `tau * k / n`, y down (0 east, n/4 south); the JSON tells the engine
  `row = round(atan2(dy, dx) / tau * n) mod n`.
- **Caster to target** (a projectile that lands, a beam, a strike on a foe): the distance between them changes in
  play, so never only bake it into one sheet. Export three parts in `parts`, each from `fc.part`: `cast`
  (anchor caster, one-shot, the charge and release), `travel` (anchor travel, a loop the engine moves at `speed`
  px/s from the caster to the target, with its own direction rows for top-down or `facing` for side) and
  `impact` (anchor target, one-shot, the hit and dissolve). Keep the joined preview sheet and gif too, for review. When the owner wants one fixed-range sheet, record `target` and its mirror and say the range is
  fixed in the report.

For a game that cannot load a sheet as it is, or needs the effect to follow a moving target or recolour per
instance at runtime, `porting.md` also covers porting the draw code to the engine's own language.

Report in English with the path of the preview page `out/<name>.html` and the other paths, the brief, the state table for a multi-state effect, the "Suggestions" list
(knobs the owner can turn next: speed or the length of one state, frame count, glow, light hue, density, size)
and what is left.

## 6. Follow-up requests (after a draft is delivered)

Each later message about the effect (a change request, a comment, a complaint, a question) gets a recommendation,
whether or not it asks for one:

1. Name the purpose behind it in one line: what the owner wants the effect to read or feel like ("hits harder",
   "reads at 1x", "matches the caster's colour"). When a vague comment fits two purposes, ask one question first.
2. Do what was asked, one change per pass as in the draft loop, and rerun the draft.
3. Then recommend 1 to 3 changes that serve the same purpose, most effective first. Each names the knob or part,
   the value (fps 24 to 30, glow medium to strong, 3 more sparks on frames 4 to 6), and why it serves the purpose,
   drawing on the usual fixes in section 3. Apply none of them until the owner picks.
4. When the asked change works against the purpose (more glow to read better, when the draft is already washed
   out), say so with the reason and give the change that would get there; still do what was asked unless the owner
   changes it.

A question or comment with no change in it gets the answer, then the same recommendation list.
