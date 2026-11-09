---
name: combo
order: 14
group: extra
stated: Does the request say how the hits of a combo are triggered in the game (one button press per hit, or one press that plays the whole string), or say the effect is a single blow?
applies: Is the effect a combo or string of several blows (a multi-hit sword combo, a flurry, a chain of attacks)?
---
# Combo input

How the player triggers a combo's hits. This picks how the sheet is cut: one clip per hit that the game spawns
on each press, or one continuous sheet that plays the whole string from a single press.

**Fixed when** the prompt says "per press", "each press", "tap to continue", "one button for the whole combo",
"super", "cinematic", "auto combo", or says the effect is a single blow.

**Applies** to an effect of several blows in a row. A single slash, a projectile or an aura leaves it out.

**Ask:** "How does the player trigger the hits?" Options:
- "One press per hit (Recommended)": each hit is its own clip (a state) that starts on its animation's frame 0
  and ends on wisps; repeated strokes share a clip. `meta.beanfx.caster.combo.steps` lists the steps (state,
  animation, the frame the swing ends on). A press while a step plays queues the next one, which cancels the
  recovery once the swing ends; no press by the end of the animation sends the character to idle and the next
  press starts at hit 1. Each hit is its own effect instance, so a combo stopped at any hit still dissolves
  cleanly. The sheet is about 1.5 times one continuous string.
- "One press, whole string": one continuous sheet over a chain of animations (`caster.chain`), tagged per hit;
  the player cannot stop it halfway. For a super or a cinematic finisher.
- "Both": the per-hit clips for play, and the continuous string as a second sheet for a super version.
Follow-ups when "One press per hit" is picked and the prompt leaves them open: whether a press in the recovery
still counts (default yes, until the animation ends) and which hits escalate in weight (default from `timing`:
light, then heavy, then the finisher).

**Examples:**
- One press per hit: Hollow Knight's nail, Dead Cells' sword combos and Hades' attack strings advance one swing
  per press, and a pause resets them to the first swing.
- One press, whole string: a fighting game super or Devil May Cry's Million Stab, where one input plays a fixed
  sequence.

**Default:** one press per hit when the effect rides a game character; the whole string for a cinematic
finisher or a mockup caster.

Each hit's smear follows the blade on the character's own contact frame (the tip measured from the sprite, see
"Follow the sword" in SKILL.md), so the clip lines up however the player times the presses.
