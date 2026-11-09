---
name: caster
order: 13
group: extra
stated: Does the request say whether to draw a caster figure (a character, silhouette or avatar) with the effect, or say to draw the effect alone?
applies: Is the effect a skill cast by someone (a sword art, a palm strike, a summon), or does the request mention a character, silhouette or avatar?
---
# Mockup caster

Some effects read better with someone casting them. Draw one only when the owner wants it; `kit/caster.py` and
its use are in SKILL.md section 2.

**Fixed when** the prompt says to draw a caster, a silhouette or an avatar, or says effect only.

**Applies** to a cast skill or a prompt that names a caster. A hit, projectile, aura or pickup with no caster named
leaves it out without asking.

**Ask:** "Add a mockup caster?" Options "No, effect only" (recommended for a hit, projectile, aura or pickup),
"Glowing silhouette" (recommended for a cast skill), "Silhouette with an avatar", "Game character" (the owner's
own sprites in `casters/<name>/` or a caster that ships with the skill: `nghich_tien_kiem` (sword) and
`nghich_tien_truong` (staff), each side or `_topdown`; listed by name). If yes and the prompt leaves
them open, the follow-ups: height against the carrier (default shorter than the main carrier, such as about 34 px
beside a 47 px sword, so the effect stays the hero), hair (`loose`, a wild mane; `bun`, pinned with nape locks),
and what it does in each state (charge, rise, point, land).

**Examples:**
- Effect starting from a held object: the flame at the tip of a Noita wand, the sword of light in Hyper Light
  Drifter. Draw the object as the caster when the effect comes out of it.
- A glowing silhouette is a stand-in for scale in the preview only; the sheet ships without it.
- Game character: the effect is drawn on the character's own frames (pivot on its feet, frames locked to one of
  its animations, one row per direction top-down) so the sheet drops into that game as it is. Follow-ups: which
  character, which animation, the character frame the effect starts on (default the first contact frame), and
  front or behind the character. A slash follows the blade's stroke in rig.json `swing` (turn, from, to).
  The example casters are references: a new look or a missing animation means an original character on the same
  rig.json, not a recoloured or edited copy.
  Directions: a side effect on a game character has 2 rows (east and west, each on the character's own row); a
  top-down effect has all 8. A character composed from the owner's own game sheets may be used as it is;
  each comes as `<name>` (side, east and west) and `<name>_topdown` (8 directions).

**Default:** no caster.
