# VFX craft notes behind the knob examples

Purpose: give each knob option a plain effect, a verified game example and a fit rule, for owners who know
nothing about VFX. Research date 2026-11-08.

Evidence tags used below:
- [V] a page I fetched states the fact (URL in Sources, group letter in brackets).
- [S] the fact came from a search-result summary of a page I could not open in full, or from a single low-quality
  blog. Use it as a default number, not as a quote.
- [C] craft consensus (twelve principles of animation, common pixel-art practice). No single source checked.

Limits of the examples: most game wikis state mechanics (what the effect does, how long it lasts), not what it looks
like. Where a source gives only the mechanic, the example says so. No example below is a guess, but a few are
weaker than the brief asked for; section "Not verified" lists what I dropped.

---

## 1. role

What it decides: size, directions, loop, timing defaults. The owner needs to hear "where does this play and what
does the player do while it plays".

- Projectile that flies to a target. Effect: needs a heading, a travel loop and an impact part. Example: Dead Cells
  Fire Grenade, lobbed in an arc, explodes on contact with an enemy or flat surface, leaves fire on the ground for
  7 seconds [V, A]. Fits: any shot the player can follow with the eye. Not for: something that appears on the
  target with no travel.
- Hit that plays where something lands. Effect: round, one row, very short, no direction. Example: fighting-game
  hit spark plus freeze; Sakurai describes the freeze that "emphasizes the power of impact" [V, B]. Fits: melee
  contact, bullet impact. Not for: effects that need to cross the screen.
- Explosion. Effect: biggest silhouette, one-shot, strongest flash. Example: Dead Cells Powerful Grenade, "a large
  explosion" of 200 damage in a large area; the Bigger Explosion affix makes it 200 percent larger [V, A]. Fits:
  area damage, kills, breakables. Not for: small contacts (it hides the enemy).
- Aura or buff on a character. Effect: loops, sits on the body, must not cover the face or weapon. Example: Celeste
  hair as dash indicator: red or pink with dashes left, white while dashing, cyan with none [V, C]. A state shown
  on the body itself reads faster than a separate icon. Fits: long-lived status. Not for: one-time events.
- Pickup or reward. Effect: draws the eye, short sparkle, ends with a settle frame. Example: Vampire Survivors
  chest opening, drawn after slot-machine graphics [V, E]. Fits: loot and level-up moments where the player should
  stop and look.
- Counter-hit "clear the screen" ring. Example: Enter the Gungeon Blank, erases all enemy bullets in the room,
  radius 7 tiles on the wiki [V, F]. Fits: panic buttons. The source gives rules, not the look.

Missing in the knob file: "what is the player doing while it plays" (running, standing, locked). A locked player
tolerates 1 to 2 s; a running player needs under 0.5 s [C].

## 2. view

- Side view, 1 direction plus mirror. Effect: smallest sheet, flips at runtime. Example: Katana Zero, described as a
  side-scrolling hack-and-slash [V, G]. Fits: platformers, fighters. Not for: lit-from-one-side glow (the light
  flips with the sprite) or text.
- Top-down or 3/4, 8 directions. Effect: 8 rows, the hit lands at the right angle. Example: Celeste's dash goes in
  any of eight directions [V, C], the same 8-heading set a top-down shot uses. Fits: twin-stick, short travel.
- Top-down or 3/4, 16 directions. Effect: smooth aim, big sheet. Example: Enter the Gungeon is a top-down bullet
  hell [V, F], where long free-aim shots show an 8-row step. Fits: fast or long travel. Not for: short shots, the
  jump between 8 rows is invisible at under 30 px.
- Side view, east and west drawn. Fits: effects with a fixed light or text. [C]
- Round effects (ring, burst, aura) need 1 row in every view. Example: Blank above.

Missing: which side the shadow falls on in top-down (ground contact), and whether the effect must draw behind and in
front of the character in two layers (a ring or a swirl wraps the body) [C].

## 3. size

- Small cell (about 32 to 64 px). Effect: crisp at 1x, cheap, few details. Example: Dead Cells renders low-res
  without anti-aliasing and admits "the disappointing level of details" is the trade-off [V, H]. A 2 px wide colour
  trail still works at 32 px and below [S, I]. Fits: busy screens, many on screen.
- Medium cell (about 64 to 136 px). Effect: room for a core, rim and sparks. Fits: most skills and hits.
- Large cell (about 200 to 320 px). Effect: grand, a few big shapes; the 1 px detail vanishes unless drawn bigger.
  Fits: ultimates, bosses. Example: Dead Cells Bigger Explosion affix doubles area size [V, A], so a normal and a
  large explosion are two sizes of one design.
- Size against the body: effect no taller than the character reads as part of them; 2x reads as a skill. [C]

Missing: the game's render scale. An effect drawn at 64 px that the game shows at 4x has chunky pixels; state the
screen size (Dead Cells and the 320 by 180 guidance in [S, I]).

## 4. timing

Craft anchors (animation principle: timing is the number of frames per action, light things move faster [V, J]):

- 12 fps, about 8 to 12 frames. Effect: choppy, retro, small sheet. Example: itch effect packs run 7 to 18 frames at
  about 70 ms per frame [S, K]. Fits: NES and Game Boy looks.
- 24 fps, 1 to 1.5 s. Effect: smooth, standard hit and explosion. Fits: most.
- 30 to 60 fps. Effect: very smooth, best for long loops and fast streaks; big sheet. Example: Celeste's dash is
  15 game frames including 3 freeze frames [V, C]; the game steps in game frames, not art frames.
- Variable hold (not an fps choice): hold the impact frame 1.5 to 2.5x longer than setup frames. One guide gives
  80 to 100 ms for setup and 150 to 200 ms on impact [S, I]. Fits: one-shots with a hit.

Timing split for a one-shot [C unless noted]: anticipation about 15 to 25 percent, peak 1 to 2 frames, dissipation
50 to 65 percent. Fast attack total: 3 to 6 frames split into wind-up, strike, recovery, 1 to 2 frames each [S, I].
Slow-in and slow-out: more frames near the start and the end of a move, fewer in the middle [V, J].

## 5. loop

- Loop, seamless. Effect: runs forever; first and last frame must match. Example: Noita burning wood makes smoke
  continuously [V, L]; a fire that never stops is an ambient loop. Fits: auras, torches, idle. Not for: a hit.
- One-shot: anticipation, peak, dissolve. Effect: ends empty. Example: Dead Cells Fire Grenade explosion, one blast,
  then the fire on the floor [V, A]. Fits: hits, explosions.
- Start, loop, end. Effect: three tags; the loop part repeats while the player holds. Example: Dead Cells ground
  fire lasts 7 s [V, A], a held state with a start flare and a fade. Fits: beams, channels, ground zones.
- Loop with a decay timer. Example as above; the engine ends the loop, the art needs a short end part. [C]

Missing: loop length (2 to 4 frames is the floor for an idle [S, I]; flicker loops that are shorter than 8 frames
look mechanical [C]), and an off-beat loop so two copies do not pulse together (offset the start frame).

## 6. shape

- Round burst. Effect: fastest read, hides what is behind it. Example: Dead Cells Powerful Grenade blast [V, A].
- Ring or shockwave. Effect: shows radius, leaves the middle open so the player is visible. Example: Blank, clear
  radius of 7 tiles [V, F]. Fits: area rules the player must see.
- Streak or trail. Effect: speed and direction; a smear frame is the pixel-art version. Example: Celeste's dash
  trail of shadows and white contrail [S, M]; mechanic and hair colour verified [V, C]. Fits: dashes, slashes.
- Teardrop or comet. Effect: shows travel direction by its tail. Example: Noita Spark Bolt, a fast projectile with
  a slight arc, "sparkling" [V, N]. Fits: shots.
- Disc or solid chunk. Effect: reads as an object, not a gas. Example: Noita Giga Disc and Omega Disc, larger discs
  that dig through terrain [V, L]. Fits: effects with a physical hit.

Missing: silhouette first. A shape that reads when filled with one flat colour will read at 1x. Draw the effect as
one-colour silhouette frames and check them before shading [C]. Dead Cells makes threats the brightest and most
saturated element for the same reason [V, O].

## 7. style

- Soft (1 px lines, translucent smoke, smooth glow). Fits: modern indie. Example: Dead Cells, saturated, "dynamic
  particles, normal maps and 3D lighting" over pixels [V, O].
- Hard retro (opaque pixels, dark outline, dither). Effect: strict, readable on any ground, needs a locked palette.
  Example: Shovel Knight limits itself to the NES palette and four extra colours [V, P]. Fits: 8-bit and 16-bit
  looks.
- 1-bit or two-tone dither. Effect: texture from pixel patterns, no glow. Example: Return of the Obra Dinn,
  "monochromatic dithering style" [V, Q]. Dither shimmer at motion can cause motion sickness; the dev added a
  motion-blur equivalent [V, Q]. Fits: stylised, still scenes.
- Painterly HD (HD-2D). Effect: sprite plus post effects. Example: Octopath Traveler combines SNES-style sprites with
  "high-definition effects" [V, R]. Fits: bloom and depth blur add.

Pixel-art definition notes [V, S]: dithering uses "noise or a repeating pattern such as a checkerboard"; sub-pixelling
changes pixel colours "to create an illusion of movement"; a low colour count is a common trait (8 or 16 colours
argued by some as a defining feature). Outline is not covered by that page; see "Missing choices".

## 8. palette

- Warm hue-shifted ramp (fire). Effect: shadows go red-purple, lights go yellow-white. Craft rule: positive hue shift
  per step "usually results in more natural colors, warming as they become brighter"; Slynyrd uses 20 degrees per
  swatch at most, 9 swatches per ramp [V, T]. Fits: fire, explosion, gold light.
- Cool ramp (ice, magic, tech). Shadows go violet, lights go cyan to white. Fits: frost, shields.
- Small shared palette (8 to 16). Effect: instant cohesion, hard retro. Example: Shovel Knight NES palette [V, P].
  Slynyrd advice: build a large palette, pull small ones per job; you "don't have to make such a large palette" [V, T].
- High-saturation threats. Effect: effects pop against dull backgrounds. Example: Dead Cells gives enemies,
  projectiles and spells the highest saturation, contrast and brightness; biome palettes come from a gradient map
  [V, O]. Fits: anything the player must dodge. Not for: ambience, which should sit lower.
- Colour count rule for an effect: 3 to 5 tones per material; two tones plus a highlight is often enough for smears
  [S, I].

Missing: "will it read against the game's biggest bright background" (snow, lava). White flashes vanish on snow; pick
a tint that survives the brightest biome [S, I]. Contrast too low and "pixels begin to blend together" [V, U].

## 9. glow

- Subtle (tight cores, busy screen). Fits: many effects on screen. Example: Dead Cells ships a toggle to turn off
  "bright flashes... (explosions, wounds, etc.)" and a limiter for particles, so the glow can be tuned [V, V].
- Medium (reads on dark and mid grounds). Fits: default.
- Strong (bright cores, many flashes). Effect: spectacle, blows out on light grounds. Example: Celeste's hair goes
  white during a dash, the brightest state at the fastest moment [V, C]. Fits: finishers, magic.
- No glow. Effect: flat opaque pixels. Example: Shovel Knight's NES limits [V, P]. Fits: authentic retro.

Missing: accessibility. Dead Cells added a flash toggle and shake toggle in its 2.9 accessibility update after
player complaints [V, V]; Katana Zero's flashing and VHS look drew headache remarks in reviews [V, G]. Ship the light
as a separate layer (already `light_gain`) and tell owners this is why.

## 10. clarity

- Clear. Solid pixels on dark. Fits: fast play. Example: Dead Cells collisions must contrast strongly with the
  background, and effects get the highest brightness and contrast [V, O].
- Balanced. Light mist round the peak. Fits: magic, heat.
- Hazy. Wide translucent volumes. Effect: soft and dreamy, muddy at 1x. Example: Dead Cells uses "air-density
  particles and foreground clouds" for depth [V, O]. Fits: fog, dreams, set dressing. Not for: threats.
- Background control. Dead Cells has a background filter option that changes colour, saturation and opacity so
  foreground objects stand out, and colour outlines for projectiles [V, V]. Lesson: a hazy effect on a busy ground
  needs a separate dark pad or outline pass in the engine.

## 11. density

- Few (1 to 3 parts). Effect: cleanest read at 1x. Example: Enter the Gungeon is a bullet hell where the
  player must tell bullets apart [V, F]; keep each part few and distinct. Fits: heroic single moves.
- Medium (4 to 10). Effect: reads as a group; good for a volley.
- Many (hundreds). Effect: grand, noise past what the cell holds. Example: Vampire Survivors, "continuous waves" of
  enemies [V, E]; Dead Cells includes a particle-limit setting (10 percent steps) so players can thin out dense scenes
  [V, V]. Fits: swarms. Not for: small cells.
- Debris rule: 3 to 8 debris pixels for a light hit, a big burst only for kills or breakables; cut melee particles in
  half when projectiles are also on screen [S, I].

## 12. states

- Single state. Fits: simple hits.
- Windup then release (2 states). Example: Cave Story weapons gain levels from collected crystals and lose them on
  damage [V, W]; the power state changes the effect look. Fits: tiered attacks.
- Trigger then payload (hand-off). Example: Noita Double Trigger bolt releases its second spell only when it hits
  something [V, N]. Fits: two-stage effects.
- Slow-motion window. Example: Katana Zero Chronos slows time and the music slows with it [V, G]. Lesson: a state
  change should change more than the picture.
- Freeze-and-release. Example: Celeste's dash, 15 frames including 3 freeze frames [V, C]. Fits: dashes, big hits.

Timing rule from practice: key poses first and the right timing "with the least amount of frames possible", then add
in-betweens [V, X]. State tables in the docstring match this (set key states, then add frames).

## 13. caster

- No caster, effect only. Fits: hits, pickups. 
- Glowing silhouette. Effect: placeholder body so the owner sees the effect in scale. Example: Celeste's hair
  colour carries state with no body detail [V, C]. Fits: cast skills.
- Silhouette with avatar. Fits: marketing previews only.
- Item-as-caster. Example: Noita wand "making the end of your wand flame" [V, L]; Hyper Light Drifter's sword is made
  of shifting light and the gun recharges when the sword hits [V, Y]. Fits: effects that start from a held thing.

---

## Missing choices (not in the knob files)

Ask or default each one; ordered by how often it breaks a first draft.

1. Hit-stop pairing. When an effect lands, the game freezes briefly. Sakurai: both parties freeze for the same
   length; stronger attacks freeze longer [V, B]. Numbers: light hits 2 to 4 frames, heavy 6 to 10, supers 12 to 18
   at 60 fps [S, I]. Vlambeer's talk lists a "sleep" on hit among about 30 small tweaks; one reproduction uses
   `sleep(20)` per enemy death [V, Z]. Deliver the freeze timing in the JSON hit field.
2. Screen shake pairing. Vlambeer: shake against the firing direction; camera kick; bigger bullets; muzzle flash;
   bodies and shells stay on screen (permanence) [V, Z, AA]. Melee shake 4 to 8 frames, explosion 10 to 16 frames,
   reduce horizontal first if testers feel dizzy [S, I]. Ship an off switch (Dead Cells did) [V, V].
3. Flash frame. Frame 1 of a hit is a 1 to 2 frame white or high-contrast flash, then back to colour [S, I]. Long
   flashes read as stun.
4. Anticipation, impact, dissipation. Anticipation prepares the viewer [V, J]. Rule of thumb: windup 15 to 25
   percent, peak 1 to 2 frames, dissipation the rest [C].
5. Smear frames. One smear frame on the weapon arc or limb; a second only for charged attacks [S, I]. Defined as
   "a single frame... exaggeration or distortion of an object" [V, AB]. In pixel art use a 2 px trail.
6. Outline vs none. Outlined effects survive busy grounds; unoutlined effects look cleaner. Dead Cells lets
   players add coloured outlines to projectiles and active skills [V, V]. Default: no outline for light, 1 px dark
   outline only for solid objects like discs [C].
7. Dither vs flat. Dither adds texture in retro looks but shimmers in motion (Obra Dinn needed extra processing)
   [V, Q]. Default flat for fast effects.
8. Hue shift in ramps. 20 degrees per step at most [V, T]. Skipping it makes "straight ramps" that "lack interest"
   [V, T].
9. Colour count. 3 to 5 tones per material; too-similar tones merge at 1x [V, U]. Check at 1x.
10. Sub-pixel animation. Changing pixel colours to suggest motion smaller than one pixel [V, S]. Use it for slow
    drifts (embers, mist) not for hits.
11. Readability on busy backgrounds. Brightest and most saturated element is the threat [V, O]; test on the brightest
    biome [S, I]; test at 2x enemy count [S, I].
12. Sound sync. Contact, freeze, flash peak and sound transient within one frame of each other [S, I].
13. Ground contact layers. Effects that wrap a body draw back and front layers [C].
14. Game frames vs art frames. Sample hit-stop in game frames so timing survives an animation swap [S, I].
15. Twelve principles used for effects: anticipation (windup), timing (frames per action), slow in and out, staging
    (clear read), exaggeration, follow-through (embers keep moving after the peak) [V, J].

## Not verified (dropped)

- Hyper Light Drifter dash look. Sources give a vibrant palette and a light sword; none describes the dash effect.
- Dead Cells hit-stop of 0.05 s and 24 to 30 frame attacks: claimed by a low-quality blog only.
- Dead Cells and fighting-game feedback references: one secondary report, not a primary source.
- Super Metroid charge beam, Spelunky bomb, Enter the Gungeon Blank visual ring: wiki pages returned errors or gave
  rules only.
- Capcom Street Fighter 6 hit stop of 8 frames: seen in a search summary; the page returned 503 on fetch.
- Celeste dash trail "shadows and a blazing white contrail": a video-essay transcript quoted in search results,
  not opened.
- Saint11 (Pedro Medeiros) tutorials: his site and Patreon content did not load; only the Lospec index of titles
  (fire, light magic, explosion) was read.
- AdamCYounis, MortMort, realtimevfx: only titles and listing pages reached, no body text usable.
- GDC Dead Cells and Celeste art talks: no transcripts found; only the Game Anim listing of the Celeste talk.

---

## Sources

A. Dead Cells wiki: https://deadcells.wiki.gg/wiki/Fire_Grenade and https://deadcells.wiki.gg/wiki/Powerful_Grenade
B. Sakurai hitstop column: https://sourcegaming.info/2015/11/11/thoughts-on-hitstop-sakurais-famitsu-column-vol-490-1/
C. Celeste dash page: https://celeste.ink/wiki/Dash ; Wikipedia: https://en.wikipedia.org/wiki/Celeste_(video_game)
E. Vampire Survivors: https://en.wikipedia.org/wiki/Vampire_Survivors
F. Enter the Gungeon: https://enterthegungeon.wiki.gg/wiki/Blank and https://en.wikipedia.org/wiki/Enter_the_Gungeon
G. Katana Zero: https://en.wikipedia.org/wiki/Katana_Zero
H. Dead Cells 3D pipeline: https://www.gamedeveloper.com/production/art-design-deep-dive-using-a-3d-pipeline-for-2d-animation-in-i-dead-cells-i-
I. Sprite AI animation guide (attack timing, 2 px trail): https://www.sprite-ai.art/guides/how-to-animate-pixel-art
   Pixel Art Combat FX guide (hitstop, smear, flash, shake numbers, low reliability):
   https://gamineai.com/blog/pixel-art-combat-fx-hitstop-smear-frames-impact-timing-2026
J. Twelve principles: https://en.wikipedia.org/wiki/Twelve_basic_principles_of_animation
K. Effect pack frame counts and rates: https://pimen.itch.io/explosion-effect
L. Noita: https://en.wikipedia.org/wiki/Noita_(video_game)
M. Celeste dash trail, video-essay transcript: found via search, not opened (see Not verified).
N. Noita Spark Bolt: https://noita.wiki.gg/wiki/Spark_Bolt
O. Dead Cells colour and contrast: https://gamedeveloper.com/production/art-design-deep-dive-giving-back-colors-to-cryptic-worlds-in-i-dead-cells-i-
P. Shovel Knight: https://en.wikipedia.org/wiki/Shovel_Knight
Q. Return of the Obra Dinn: https://en.wikipedia.org/wiki/Return_of_the_Obra_Dinn
R. Octopath Traveler: https://en.wikipedia.org/wiki/Octopath_Traveler
S. Pixel art (dithering, sub-pixelling, colour count): https://en.wikipedia.org/wiki/Pixel_art
T. Slynyrd Pixelblog 1: https://www.slynyrd.com/blog/2018/1/10/pixelblog-1-color-palettes
U. Derek Yu pixel art tutorial: https://derekyu.com/makegames/pixelart2.html
V. Dead Cells accessibility: https://deadcells.wiki.gg/wiki/Assist_Mode_and_Accessibility
W. Cave Story: https://en.wikipedia.org/wiki/Cave_Story
X. Dead Cells key frames then interpolation: same page as H.
Y. Hyper Light Drifter: https://en.wikipedia.org/wiki/Hyper_Light_Drifter
Z. Vlambeer "The art of screenshake" (talk): https://www.youtube.com/watch?v=AJdEqssNZ-U ; technique list with timestamps:
   https://theengineeringofconsciousexperience.com/jan-willem-nijman-vlambeer-the-art-of-screenshake/ ;
   outline: https://crypticcreation.wordpress.com/2017/03/10/the-art-of-screenshake/
AA. Vlambeer advice article (shake opposite to gunfire): https://gamedeveloper.com/design/vlambeer-co-founder-shares-advice-on-building-better-action-games
AB. Smear frames definition: https://blog.cg-wire.com/smear-frames/
Index of Pedro Medeiros pixel tutorials on Lospec (titles only): https://lospec.com/pixel-art-tutorials/tags/fire
