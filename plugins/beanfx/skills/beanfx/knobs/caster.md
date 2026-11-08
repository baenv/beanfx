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
"Glowing silhouette" (recommended for a cast skill), "Silhouette with an avatar". If yes and the prompt leaves
them open, the follow-ups: height against the carrier (default shorter than the main carrier, such as about 34 px
beside a 47 px sword, so the effect stays the hero), hair (`loose`, a wild mane; `bun`, pinned with nape locks),
and what it does in each state (charge, rise, point, land).

**Default:** no caster.
