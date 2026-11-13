# pixelfx: reuse and the benchmark

Read only when the owner asks for reuse or picks the benchmark upgrade. Both need `setup.sh --pixelfx`, which
prints `PIXELFX=<dir>` and `LAYERS=<script>`.

## Reuse (only when the owner asks)

The owner says reuse or pixelfx, names a pixelfx id, or names
an earlier draft. For a named draft, read it and build on it. For pixelfx, find the nearest effect in
`docs/CATALOG.md` of the pixelfx dir (every effect by category), look at it with
`cd $PIXELFX && node tools/render.mjs <id> --gif` (`--opts '{"palette":[...]}'`, `--seed`, `--fps`), then split
it into layers:

```
node $LAYERS <id> --out <draft>/src --pixelfx $PIXELFX [--opts JSON] [--seed N] [--fps N]
```

It writes `<name>_color.png` and `<name>_light.png` (frames left to right) and `<name>.json` (w, h, fps,
frames, loop, pivot). In the draft, `pfx::load(folder, name)` loads them and `pfx` gives `tint` (same glow,
new hue ramp), `gain`, `keep` (light only under a mask, such as your own shape grown by a few px), `bands`
(stepped light on the loaded light; for your own `l` use `lt::steps`), `paint` (shade map to RGBA), `composite`, `strip` and `gif`. Usual use:
keep the light, redraw the colour base yourself on the same frames and pivot, follow pixelfx's motion
(positions, timing) where it is good. Recolour only (`tint` plus `--opts palette`) when the base already reads.

## Benchmark

An upgrade, run when the owner picks it. A quality check only: take nothing from its code, shapes or
motion.

- Find the reference with more than one search: `list.mjs` matches plain substrings, so `implode` misses
  `implosion`. In `$PIXELFX`, run `node tools/list.mjs <w>` for each form of the key words (the stem, `implo`;
  the noun and the verb, implosion and implode; synonyms, collapse and suck), then two or three distinctive words
  from the owner's prompt as it stands, and read the matching category table in `docs/CATALOG.md` (explosions,
  impacts, arcane, and so on). Take the one or two closest; say which and why in the reply.
- Pass 1, the peak: render the reference (`node tools/render.mjs <id> --gif`),
  and put its peak frame and the draft's side by side at the same zoom on the same dark ground. Fix the base,
  size and light of the peak here, while it costs one frame.
- Pass 2, the timeline: load the reference with `node $LAYERS <id> --out
  <draft>/ref --pixelfx $PIXELFX` and `pfx::load`, composite its frames, and write `pfx::contact(out.join("bench.png"), &draft_frames, FPS, pfx::Contact { r#ref: Some((&ref_frames, ref_fps)), .. Default::default() })`: the same moments of both, row over row (`by: "phase"`,
  the default, lines up the same share of each length; `by: "time"` the same seconds). Read it column by column:
  the focal point in every phase, the anticipation, the peak frame count, the dissolve. A peak frame alone hides
  timeline faults, such as a dark centre for 25 frames before the pop.
- Where the reference shows more detail, clearer light or more life at a column, that column is the next upgrade. Note what
  beanfx does better too (a one-shot that ends on a near-empty frame, where pixelfx can waste blank frames).
