---
name: placement
order: 15
group: extra
stated: Does the request say where the effect lands relative to the caster (on the caster, a fixed distance in front, or at a target the game picks), or say there is no caster?
applies: Is the effect cast by someone onto a spot or a foe (a summon, a strike from the sky, a ground blast, a spell that lands away from the body)?
---
# Placement

Where the effect's pivot sits relative to the caster's feet. A strike called down from the sky, a summon or a ground
blast lands in front of the caster, not under them; drawn at the caster's own pivot, the engine plays it on their
feet and the caster stands inside their own blast.

**Fixed when** the prompt gives a distance or a spot ("110 px ahead", "on the enemy", "at the cursor", "round
himself"), or says it plays on the caster (an aura, a buff, a self-centred nova).

**Applies** to a cast effect that lands away from the body. A hit, aura, buff or projectile (its travel part carries
it) skips it.

**Ask:** "Where does it land?" Options:
- "Fixed distance in front (Recommended)": `range` px along the facing, sized so the caster stands outside the
  struck area (range at least the area's half width plus about 40 px). Name the px.
- "Closer, at the edge": the area's near edge touches the caster; reads as calling it right before them.
- "At a target the game picks": `anchor: target`; the JSON keeps the default range for when there is no target.
- "On the caster": offset 0, for a nova or an aura.

**Examples:**
- Fixed range: a ground-target spell at a set distance, the way many top-down action RPG mages throw a fixed-range
  blast in front.
- Game target: a lock-on or cursor spell, such as a meteor dropped on the clicked spot.

**How it ships:** the sheet's pivot stays the struck spot. `r.meta(anim, fps, start, offset=range)` (or
`fc.offset(range, directions)` for the mockup caster) writes `meta.beanfx.caster.offset`: per direction the
`[dx, dy]` from the character's pivot to the effect's pivot (screen px, y down; a side view gives one pair that
flips with the mirror), and `range`. The engine adds it at spawn and leaves the effect there while the caster moves.

**Default:** fixed range in front for a cast that lands away; 0 (on the caster) for everything else.
