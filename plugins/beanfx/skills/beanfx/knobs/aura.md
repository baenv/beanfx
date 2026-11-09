---
name: aura
order: 16
group: extra
stated: Does the request say whether the caster shows an aura or glow round the body while casting, and what it looks like, or say the effect has no caster?
applies: Is the effect cast by someone (a spell, a summon, a channelled or charged skill), so the caster could show power gathering round the body?
---
# Cast aura

The caster shows the power they call: a matching glow round the body while the effect plays, so the eye links the
two even when the effect lands far away. It is a separate part that rides on the caster, never baked into the
effect's sheet (the distance between them changes per direction and per target).

**Fixed when** the prompt describes the aura ("lightning crawls over him", "a sigil under her feet") or says none.

**Applies** to any effect with a caster. A hit, pickup or ambient effect with no caster skips it.

**Ask:** "What shows round the caster while casting?" Options, in the effect's palette and light hue:
- "Body aura (Recommended)": a glyph ring under the feet, small arcs or flames of the element round the body, motes
  rising, a flash at the weapon or hand on the release; grows with the effect, flares on its peak, then dies.
- "Ground ring only": a lit ring or sigil under the feet; nothing on the body, so the sprite stays clear.
- "Body outline only": light hugging the silhouette; needs the character's own frames, so it fits a game character.
- "None".
Follow-ups when open: when it starts (the release frame by default) and how long it lasts after the peak.

**Examples:**
- Body aura: fighting-game supers often flash and wrap the fighter in the move's colour on the startup, so the
  player reads who is casting before the blow lands.
- Ground ring: top-down RPG casters stand on a spell circle while they channel.

**How it ships:** two parts in `meta.beanfx.parts`, both `anchor: caster` on the character's pivot, locked to the
effect's frames: `aura_back` (`layer: behind`: the ring's far half, motes behind the body, the glow) and
`aura_front` (`layer: front`: the ring's near half, arcs over the body, the flash at the hand). Each is its own
sheet and JSON (`json` in the part), drawn with `ex.write`; a part that follows the hand or weapon (the emit point
in rig.json) has one row per caster direction. Preview it with the caster; it is checked like any sheet.

**Default:** body aura for a cast skill with a caster; none otherwise.
