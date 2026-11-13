# Craft: gates, derived states, parts that read, fixes and takes

Read the gates and "Parts that read" before the first drawing. The fixes and takes are for the suggested
upgrades and follow-up requests.

## Craft gates

Draw the first pass with these in mind. A gate the delivered draft misses goes into the suggested upgrades, not
into another round.

- Clean silhouette that reads at 1x; one focal point; a rim or outline where the style uses one.
- Repeated parts (flames along a wall, puffs in a column, shards, arrows) come in three sizes, grouped: a few big,
  some medium, many small, with gaps between the groups. A row of the same shape at one size and one spacing reads
  as wallpaper however good each copy is. Parts of one mass that overlap (the tongues of one fire, the puffs of one
  cloud) are summed into one field or one shade map first and shaded once, so the mass has one core and one
  outline, not a rim round every copy.
- Separate parts that cross (two dragons in a helix, a body over a palm): give each part a depth per pixel, keep
  the nearest, and rim each part where it meets empty space or a part behind it, so the crossing reads at 1x.
- Translucent parts that overlap go into one shade map that is laid once at one alpha. Stacking each copy at its
  own alpha shows every seam as a stripe.
- Texture that marks a surface (holes, embers, cracks, moss) comes from clumped noise a few px across, never from
  one random number per pixel, which reads as static. A structure that burns, freezes or breaks keeps its light
  and dark faces while it changes, so its shape still reads.
- The subject sits near the middle of its cell with like margins on both sides of each axis (`ex::check` flags a
  lopsided cell).
- The focal point is on screen in every phase, the anticipation included: a build-up shows its core from its
  first frame, and no stretch of frames leaves the eye without a point to hold.
- Every main part separates from the ground by value: a part near the ground's value (dark on dark, white on a
  light ground) is a filled volume with a contrasting rim.
- A named object or creature matches its researched part list and proportions (or its traced reference).
- 3 to 5 hue-shifted tones per material; the base reads without the light.
- Anticipation, peak, dissolve. A one-shot dissolves to wisps: no empty frame, and its last frame keeps at most 5 %
  of the peak's pixels, so it neither pops off nor wastes a blank cell. A loop has no seam.
  An effect that ends on a held state (an eye that stays open, a seal that stays) passes `hold: true` to
  `ex::check` and `ex::write`; the JSON's `end: hold` tells the engine to keep the last frame or hand over to a loop.
- Randomness only from a seeded `default_rng(seed)`, so every run draws the same frames.
- Build-up and break-down states land on the peak drawing: their points come from `dv` on the peak's
  maps, and the frame where a build-up hands over to the solid carrier shows no jump.
- Light on every hot part (core, heads, landing flash, sparks, embers), each with a wide soft pool and a tight
  core, smooth or stepped as the style sets (hard retro steps it); white only at the hottest core.
- Nothing cut by the cell edge in any frame or direction; the pivot is the drawing's origin.
- The style picked in the brief holds in every frame (dither or translucency, glow strength).
- Every heading row reads as the same effect: draw the shape in the rotated frame (`fk::rot`, u along travel)
  but keep the shading light fixed in the world (the lighter step stays top-left in every row), and look at the
  sheet with all rows at 4x. A row that looks thinner or stair-stepped (often the diagonals) gets its own pass.
- A mirrored side sheet still reads when flipped: no text or glyph, no part that must stay on one side. When it
  fails, set mirror False and draw the west sheet.

## Peak first, then derive

Draw the carrier whole at its peak pose before any other state and look at it once
(`look <peak>`) before drawing the other frames. Give its draw function a trace mode (a flag, or a second function) that returns the shade map and a part-id
map (skull 0, jaw 1, horn 2, and so on; -1 empty) in the carrier's own frame. Every state that builds up to that
shape or breaks down from it then takes its points from those maps with `dv`, never from hand-placed
points, so a change to the drawing moves every state with it:

| state | from the peak drawing |
|---|---|
| constellation, trace, outline flash, sketch-in | `dv::simplify(&dv::outline(&m)?, n, true)`: n corners round the silhouette, in order |
| inner lines (jaw, eye, horn roots, armour seams) | `dv::part_lines(&parts, min_len)`, each chain through `dv::simplify(&c, n, false)` |
| a body that uncoils or grows along its length | `dv::spine(&m, min_len)`: ordered centre lines |
| gather, assemble, motes landing | `dv::scatter(&m, n, seed)`: even landing spots inside |
| shatter, dissolve, break into motes | `dv::scatter` for the start points, so the pieces leave from what was on screen |

Store the points with `dv::local(&p, anchor, ang, scale)` and place them each frame with `dv::world(..)` at
the carrier's pose for that frame. Learnt on a dragon constellation: the constellation traced from the solid
head lands on it exactly.

## Parts that read (learnt, not copied)

Fire and comets are a lumpy head banded white, yellow, orange, red and a dark
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

## Usual fixes

Mush at 1x, then fewer tones, one focal point, bigger shapes; floaty, then fast in and slow out with
a 1 to 2 frame white-hot peak; stiff, then vary each particle's size, speed and delay and add secondary motion
(sparks, smoke, debris); flat, then a lighter top-left step and a darker bottom-right one; washed out, then less
light and white kept for the hottest core only; glow that floats off the shape, then `pfx::keep` it under a mask of
the base; glow that reads soft or blurry where the owner wants pixel art, then `lt::steps` and tighter pools; stepped glow
that looks outlined or dull, then fewer steps in the halo, a 1 to 2 frame white core and flicker on the sparks;
hazy or muddy where the brief says clear, then remove the scene pool, make the colour solid and light emitters only; thick
saturated strokes, then a 1 px white core with 1 px of tinted edge and let the light carry the brightness;
choppy, then more frames at 24 to 30 fps; dithered smoke or mist, then translucent puffs lit on top (hazy only);
clouds like cotton balls, then one lit deck as in "Parts that read".

## Takes

**Takes only on request.** When the owner did not pick the shape, draw the strongest reading from the research
and name the other readings (a coiled dragon, a dragon in a dive, a dragon head alone) in the suggested upgrades.
When the owner asks for options, draw 2 to 3 genuinely different takes of the peak frame only, put them side by
side at 4x on the dark ground in `out/takes.png`, show it, and ask which one with AskUserQuestion before drawing
any other frame. Write the board with `pfx::takes(out.join("takes.png"), &[(label, vec![peak]), ..], Default::default())?`. Delete the code
of the takes not kept.

**Glow takes only on request** (an upgrade after delivery). `cargo run --release -q -- glow` on the runner
renders the frames round the first hit at three gains (0.6, 1.0, 1.3: subtle, medium, strong) and writes
`out/glow_takes.png` and a gif that plays the three in step. Show both, then ask one AskUserQuestion: "How strong
is the glow?", options "Medium (Recommended)", "Strong", "Subtle", each with its line from `knobs/glow.md` and the
take number it matches; say the light still ships as its own sheet with `light_gain`, so the game can tune it
later. Keep the picked level in `Spec.glow` and rerun.
