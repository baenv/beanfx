# Export: the sheet, the JSON, the act, directions and sound

`dr::main` writes the sheet and JSON from `Spec`; read this to fill the hits, poses, target, directions, parts
and sound, or when a draft writes its own `run()`. `docs/output-json.md` in the repo lists every JSON field.

On the runner these are fields of `Spec` (hits, poses, target, states, extra; `kit/API.md`), and `dr::main` makes
the calls below. A draft calls them itself only when it writes its own `run()` (heading rows, a custom sheet):

```
let mut extra = fc::meta("side", W as f64, H as f64, PIVOT, Default::default())?;
extra.insert("glow".into(), "medium".into());
let meta = ex::write(out, NAME, &finals, FPS, PIVOT, LOOP, ex::Write {
    light: Some((&lights).into()), color: Some((&cols).into()), states: states(), hold: false,
    hits: vec![ex::hit(PEAK, FPS, ex::Hit { weight: Some("heavy".into()), dir: Some(0.0), ..Default::default() })],
    poses: vec![ex::pose(-0.3, "windup", ""), ex::pose(0.0, "release", "snap"), ex::pose(0.6, "recover", "")],
    target: Some(json!({"x": 72, "react": "knockback"})), extra: Some(Value::Object(extra)),
    ..Default::default()
})?;
```

- `<name>.png` is colour plus light (`pfx::composite` over transparency), frames in a near-square grid, row-major.
  A sheet that would pass 4096 px a side splits into pages `<name>_p<k>.png`, each with its own Aseprite JSON
  `<name>_p<k>.json` (its frames and the tags clipped to it); `<name>.json` then lists every frame with its `page`
  and the page files in `meta.beanfx.pages`. Frame names stay unique across pages (`<name> 37`).
  `<name>_light.png` (RGB, add it in the engine) and `<name>_color.png` sit on the same grid, so the engine can
  dim or drop the glow; the light sheet holds the light as drawn (smooth, or stepped for hard retro).
- `<name>.json` is the Aseprite "array" layout: `frames[i]` with `filename`, `frame` {x, y, w, h} and `duration`
  in ms, `meta.frameTags` one tag per state (and per heading row, `east`, `east/strike`), and everything beanfx
  adds under `meta.beanfx`: fps, loop, frames, rows, frameSize, pivot, columns, the files, `blend_light`,
  `light_gain` (1.0; the engine multiplies the light sheet by it to tune the glow at runtime), `states`, `glow`
  and the direction fields. Phaser loads it with `load.aseprite`; `porting.md` in this skill's folder has the
  import for each engine, and `runtime/beanfx.js` plays it in a browser game with no engine.
- **The act** for a blow, a strike, a cast or an impact: plain data in `meta.beanfx.act` that the game's own
  character and target follow.
  - `hits`: one `ex::hit(frame, fps, ex::Hit { weight, dir, .. })` per contact. **Weight sells the hit**: pick it from
    `ex::WEIGHTS` (light, heavy, finisher, blast) to match how hard the blow looks, and it sets the freeze (hit-stop,
    past 0.3 s it reads as a stall), the shake and how long it lasts, the push, the react (none, flinch, stagger,
    knockback, launch), how long the target flashes white and the sound cue `hit_<weight>`; any field given
    explicitly wins. `dir` is the way the blow travels (degrees, y down, 0 along the facing): the shake and the push
    follow it, so a downward smash shakes up and down and a rising uppercut lifts. A combo escalates: light, light,
    heavy, finisher.
  - `poses`: keys `ex::pose(t, name, how)` from `ex::POSES` (idle, guard, windup, cast, channel, release, follow,
    recover), t in s from frame 0, negative before it; "snap" jumps on the key. The game maps each name to its own
    animation. A wind-up the opposite way to the blow, the release on the contact frame or just before, a recovery.
  - `windup`: the seconds the character starts before frame 0; taken from the first pose key when that is earlier.
  - `target`: {x: px from the pivot along the facing, react}.
  The game starts the character `windup` s early, plays the poses, and at each hit freezes everything for
  `freeze` s, shakes along `dir` for `shake_time`, flashes the target for `flash` s, pushes, plays the react and
  the `sound` cue on the contact frame (sound, freeze, flash and shake within one frame of each other).
- **The ground answers a blow that lands on it.** `fk::ground_impact(&mut m, &x, &y, f - contact, FPS, &tones, &dust,
  fk::GroundImpact { cx, cy, r, weight, .. })` adds dust kicked out along the ground, debris that arcs, bounces once and rests where it lands, and
  cracks for heavy, finisher and blast weights; use the same weight as the hit. Put it under the blow for a ground
  strike, a slam, a landing or an explosion; leave it out for a hit in the air or on a body.
- **The sheet is the effect alone.** The game draws its own character, so the mockup caster and the target dummy
  go into the previews only (the 4x strips and the gif), and so does a game character (`rig`); its JSON
  binding goes in `meta.beanfx.caster`. `render(f, seed, caster)` draws with or without the
  caster; export and check the frames without it. For a hit, put `tg` (`kit/src/tg.rs`) under the preview at the
  target's foot (`tg::under(&frame, &tg::draw((H, W), (foot[0], foot[1]), f, &hits, FPS, tg::Draw { facing: -1.0, .. Default::default() })?)`), so the gif shows the body
  taking the blow.

**Directions in the JSON (every sheet).** The engine plays the effect from any side, so the JSON says how. Build
the fields with `fc` (`kit/src/fc.rs`) and pass the whole meta through `fc::check` before writing:

- `fc::meta(view, w, h, pivot, fc::Meta { directions, facing, mirror, target })` writes `view`, `directions` and, for one
  direction, `facing` (east by default), `mirror`, `mirror_pivot` and `mirror_target` (x becomes w - x). With
  `mirror` False, draw the west sheet (`fc::mirror(&frames)` as the start, then fix what reads wrong) and list it
  as `sheets.west`.
- With 8 or 16 directions, draw each heading with `fc::rows(draw, n, frames)` (draw(a, f), a the heading) and
  pass the rows to `ex::write`, which lays heading k after heading k - 1 and tags each: row k faces `tau * k / n`, y down (0 east, n/4 south); the JSON tells the engine
  `row = round(atan2(dy, dx) / tau * n) mod n`.
- **Caster to target** (a projectile that lands, a beam, a strike on a foe): the distance between them changes in
  play, so never only bake it into one sheet. Export three parts in `parts`, each from `fc::part(sheet, w, h, frames, fps, pivot, looped, anchor, extra)`: `cast`
  (anchor caster, one-shot, the charge and release), `travel` (anchor travel, a loop the engine moves at `speed`
  px/s from the caster to the target, with its own direction rows for top-down or `facing` for side) and
  `impact` (anchor target, one-shot, the hit and dissolve). Keep the joined preview sheet and gif too, for review. When the owner wants one fixed-range sheet, record `target` and its mirror and say the range is
  fixed in the report.

**Sound (only when the brief asks for it; `knobs/sound.md`).** After `ex::write`, `sfx::write(out, NAME, Some(&mut meta),
sfx::Write { seed: 1, voice: "retro".into(), element, .. Default::default() })` (`kit/src/sfx.rs`) synthesises the sound from the effect's own data and adds
`meta.beanfx.sound`: a hit cue per act hit by its weight, a charge, whoosh, tail or boom per state by its name, a
hum for a bare loop. Look at `sfx::layers(&meta)?` first and fix a state the names map wrong (pass the edited list as
`layers: Some(..)`). Pick the element from the subject (a sword is metal). voice "real" models metal (a blade that lands: thud,
short chink, grit; a hit layer with `clash` set for blade on blade rings at the bar modes) and thunder (N-wave
crack and rumble); recordings in the project's `sounds/` replace a cue whose name they match.
Many things that land (a sword rain, an arrow volley, hail) are many sounds: add `sfx::volley(&landing_frames, FPS,
sfx::Volley { fall_frames, weight, gain, .. Default::default() })?` from the draft's own plan, a fall that whistles down and a quiet landing
per projectile, and drop the broad state whoosh; one sound per wave reads as a few blows, not a rain. The first pass writes one sound, the recommended voice. Sound is
judged by ear, so sound takes are the first suggested upgrade: when the owner picks it, write two or three into `out/sound_takes/`
(`sfx::save(path, &sfx::track(&meta, seed, voice, element, layers, sounds)?.0)`, each a different balance or voice, the one
delivered among them) and ask which with one AskUserQuestion, naming each file. Before handing
them over, rule out the two known misses: a bell (most of the energy above 500 Hz in a few long tones) and a drum
(a pitched low thud, most of the energy under 300 Hz). After a second miss, offer CC0 recordings in `sounds/`. Add `sfx::check(out, &meta)` to the checks; the
preview page plays the track with the effect, and the report says the sound is synthesised and lists its files.
With no sound in the brief, write no audio.

For a game that cannot load a sheet as it is, or needs the effect to follow a moving target or recolour per
instance at runtime, `porting.md` also covers porting the draw code to the engine's own language.
