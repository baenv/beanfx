# Casters: the mockup caster and a game character

Read only when the brief has a caster (`knobs/caster.md`). Signatures are in `kit/API.md`. On the runner, set
`Spec.caster_foot` (size the cell so the caster and the foe both fit) and draw the caster in `Layer::Caster` with `cv.caster(..)`; the raw `cs` calls below are what it
runs, and a draft writes them only in its own `run()`.

**Mockup caster** (only when the brief says yes): `cs` (`kit/src/cs.rs`) draws a golden robed silhouette with no face,
glowing at max, plus an optional avatar. The style: 5 gold tones (`cs::BODY`) shaded by neighbour (a step up
where the top-left is empty, a step down at the bottom-right), wide sleeves and three robe flaps that trail back,
hair and flaps that lift with `lift` and flap with `flut`, and a two-finger sword sign whose tip glows. Use:

```
use beanfx::cs;
let pose = cs::pose_at(f, &[(0.0, "chest"), (28.0, "raise"), (98.0, "pull"), (103.0, "point")],
                       &[(0.0, "rest"), (28.0, "out"), (103.0, "behind")], Some(cs::aim_from(foot, sc, target)), jab)?;
let g = cs::draw(&mut over, (H, W), foot, sc, pose, f, cs::Draw { lift, flut, hair: "loose", ..Default::default() })?;
// over(ys, xs, rgb, a) is a closure that lays the caster's pixels on the frame
cs::body_light(&mut l, &g, charge); cs::finger_light(&mut l, &g, point, jab);
let gg = cs::draw(&mut over, (H, W), [foot[0] - 4.0, foot[1] - 6.0], sc * 1.27, pose, f * 0.7,
                  cs::Draw { lift: lift * 0.6, flut: flut * 0.7, ghost: k, ..Default::default() })?;  // avatar, drawn first (behind)
cs::ghost_light(&mut over, &mut l, &gg, k, f, point)?;
```

**Game character caster** (the brief picks "Game character"): `rig` (`kit/src/rig.rs`) reads the owner's sprite sheets from
`casters/<name>/rig.json` in the project (frame size, fps, pivot at the feet, animations with frame counts and
contact frames, and per direction the sheet of each row). Four casters ship with the skill in its own
`casters/` and load by name with no setup when the project has none of that name: `nghich_tien_kiem` and
`nghich_tien_truong` (a robed cultivator with a straight sword or a staff, side, east and west) and their
`_topdown` versions (8 directions), each with idle, run, cast, attack1 to 3, hurt and dead. A project's own sprites
in `casters/` are the owner's licensed art: they stay local (gitignored) and never go into the plugin or the sheet.
Draw the effect in the character's frame space, so it drops into that game as it is:

```
use beanfx::rig;
let r = rig::load("knight_side", None)?;           // casters/knight_side/rig.json
const PIVOT: [f64; 2] = [56.0, 84.0];              // the character's feet on the effect canvas
let k = (FPS / r.fps_of(anim)?) as i64;            // effect frames per character frame (a row may set its own fps)
// character time of effect frame f is START + f / k; r.contact(anim)? lists the hits
let ch = r.place((H, W), PIVOT, anim, f as i64 / k, rig::Place { direction: Some(dir), start: START, ..Default::default() })?;  // preview only
let prev = pfx::composite(&rig::over(&color, &ch), &light, None)?;
let (a0, a1) = r.arc(anim, Some(dir), 0)?;         // the slash runs with the blade
problems.extend(r.check_arc(anim, a0, a1, rig::CheckArc { direction: Some(dir), ..Default::default() })?);
let caster = r.meta(anim, FPS, rig::Meta { start: START, ..Default::default() })?;   // into ex::Write's extra
```

- The effect fps is a whole multiple of the animation's fps (`r.fps_of(anim)`); `r.meta` refuses any other. A row
  with uneven frame times (rig.json `ms`, from a game) goes into the JSON as `char_ms`, and the engine holds the
  effect frames by those times.
- Directions of a game caster: a side (horizontal) effect uses 2 rows, east and west, each drawn on the
  character's own row of that name (`fc::rows(draw, 2, n)`, `fc::meta("side", .., fc::Meta { directions: 2, .. })`), since the
  character holds its weapon in one hand and west is not a mirror. A top-down effect uses all 8 rows
  (`fc::rows(draw, 8, n)`, order `fc::NAMES8`). A rig with one side row (`facing` only) keeps the mirrored
  single row.
- Time the blows on the character's contact frames, not on a guess. Character sheets come without baked smears
  (white arcs in the attack frames), so the effect's slash is the only one; strip them from a bought pack first
  and keep the original in `casters/<name>/orig/`.
- A combo on a game character follows the `combo` knob. One press per hit: draw one clip per stroke and weight,
  each from its animation's frame 0 to wisps, write `caster.combo.steps` (state, anim, char_from, char_to the
  frame the swing ends on, contact, weight) and `caster.chain` (each clip on its animation, for the viewer), and
  preview the whole string with every press on time by laying the clips on the timeline.
- Follow the sword. rig.json `swing` gives each stroke's turn (cw or ccw on screen), `from` and `to` angles
  (0 east, 90 south, y down) and frames. Take a slash arc from `let (a0, a1) = r.arc(anim, direction, stroke)?` (a1 - a0
  carries the turn), never from a guess, and add `r.check_arc(anim, a0, a1, rig::CheckArc { direction, stroke, .. })` to the draft's
  problems so a wrong turn or an end over 60 deg off exits 1. Time the arc's head on the stroke's frames.
  `r.meta` carries `swing` and `pixel_scale` into the JSON. `swing` fixes the turn and the ends, not where the
  blade is on the contact frame: put the smear's head on the blade tip measured from that frame of the sprite (the
  weapon's own colour, the pixel farthest from the hand; write a small `measure_blade` helper in the draft) and the hit spark
  on rig.json `emit` (the weapon tip). A smear placed by eye or toward the target runs ahead of or behind the
  blade. A stroke near 180 deg (an overhead chop) swings in the upright plane of the heading: squash it across by
  |cos heading|, and facing away, end it at the ground in front.
  Top-down, the way round comes from the camera: when the blade jumps from `from` to `to` in one character frame
  the sprite cannot show which way it went, and rig.json's turn is only the shorter screen path. A cut sweeps the
  side the character faces, so draw the way round that passes the heading (the other way when the rig's way runs
  behind the body, as on a character facing the camera), and check that the blade's tip on the contact frame
  lies on the drawn arc in place of `r.check_arc`. Record the drawn way in `caster.swing_drawn`.
- A cast that lands away from the body (a summon, a strike from the sky, a ground blast) follows the `placement`
  knob: the sheet's pivot is the struck spot and `r.meta(anim, fps, rig::Meta { start, offset: Some(range), .. })` writes
  `caster.offset` (per direction the `[dx, dy]` from the character's pivot to the effect's pivot) and `range`.
  Never leave such a cast on the character's own pivot: the engine then plays it on the caster's feet. Learnt on
  a heavenly-tribulation strike, whose first cut struck under the caster in the game.
- The caster shows the power it calls, per the `aura` knob: `aura_back` and `aura_front` parts in
  `meta.beanfx.parts` (anchor caster, layer behind and front), each its own sheet from `ex.write` on the effect's
  frames and palette, its JSON named in the part's `json`. A part that follows the hand or weapon (rig.json
  `emit`) takes one row per caster direction.
- Moving animations (a dash): frames stay in place and rig.json `root` gives the body's travel per frame
  (`r.root(anim, direction)`). The effect stays where the move began: size the canvas for the whole travel, preview
  with `r.place(.., rig::Place { travel: true, .. })`, and put trails and afterimages at earlier `root` points; `r.meta` carries `root`.
- The example casters (`knight_side`, `adventurer_topdown`) are references to learn from: proportions, cell size,
  pivot, frame counts, fps, contact frames, swing and root motion. A caster that needs a new look or a missing
  animation is an original character built to the same rig.json contract (the `/char` route), never a recolour,
  edit or composite of the example sheets; the local `chars/` build script only cleans the references.
- A caster composed from the owner's game sheets builds each row the way the game draws it, never from the baked
  layers alone. Take the game's own row for the weapon (a staff runs on the staff's own run row, not the generic
  run). On rows where the game draws the weapon in the fist (its swing sprite on a per-frame hand track), draw it
  there on every frame: turned to the track's angle, foreshortened by its length, and split in front of or behind
  the body as the game splits it. Check every moving row at 4x, and fail the build when a held weapon leaves the
  fist: a weapon that holds still while the body bobs is a baked pose for another grip, and the hand slides off it.
  Learnt on `nghich_tien_truong`, whose staff floated beside the hand in the run.
- Top-down: draw rows with `fc::rows(draw, r.directions.len(), n)`; their order is the rig's directions.
- A held weapon can dip below the feet, so check each animation's pivot with `r.place` over a ground line before
  drawing; rig.json pivots override the measured ones (`r.pivot(anim)` is the rig.json one, `rig::measure(&frames)` the measured one).
- Review in the browser: every draft run writes its own page, `out/<name>.html` (`ex::page`), that
  opens straight from disk. `<skill>/tools/preview.html` is the template and also opens from disk
  on its own (pick the project folder) to browse every result. The page shows directions, actions (states, tags,
  caster animations), frame stepping, speed, light layer, pivot, cell box, swing arc and root motion; Control mode
  drives the caster with WASD, J and K attack, L dash, and fires the effect. An effect on a chain of animations
  (a combo: `meta.beanfx.caster.chain`, each `{anim, char_from, char_to, effect_from, effect_to}`) shows the
  character of each segment, and J plays the whole chain; animations with rig.json `ms` play by those times. A
  segment may add `walk` (`[[x0, y0], [x1, y1]]` px, eased over the segment) to move the body, and `portal`
  (`{in, out}` px from the pivot along the facing) to cut the body at `in` and show it past `out`, for a step
  through a rift. A part with an `offset` is already in the joined sheet, so the page does not draw it on the body. It
  carries `runtime/beanfx.js` inline: after a runtime change paste it into `tools/preview.html` between its RUNTIME START and RUNTIME END markers with `export ` removed; `cargo test` in `kit/` checks that the copy matches.
- A slash drawn by eye, before rig.json `swing` existed, ran against the blade and `check_arc` failed it; take arcs from `r.arc`.

Draw the avatar before everything else and the caster after the swords behind it. Move the caster with a
`foot_at(f)` path (rise, hover with a 2 px bob, land) and feed `lift` and `flut` from its speed. What made it
read, learnt on a sword-rain effect with a caster:
- Keep it shorter than the main carrier; at 104 px and a 270 px avatar the caster took over the effect.
- Keep the core light on a small body low (`body_light` is tuned for 34 px); the pools from the scene, the
  avatar and the hip stack on it, and at core k 0.3 the figure burnt to a white blob.
- Keep every lock, flap and finger at least 1 px (`mw = 0.6 / sc`), or they vanish at small sizes.
- Light the avatar from inside its mask, with a bright rim, a faint fill and a halo; a translucent fill alone
  read as a grey copy.
- Hair grows from the scalp and nape and falls before it streams back; locks drawn from the bun fanned out like a
  broom.
