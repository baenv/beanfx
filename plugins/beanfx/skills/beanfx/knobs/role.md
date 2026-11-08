---
name: role
order: 1
group: fit
stated: Does the request say what kind of effect this is (projectile, hit, explosion, beam, aura, buff, pickup, ambient loop, transition, cast skill) or name a subject that is plainly one of them? A subject with two readings ("bolt": lightning or a crossbow bolt) does not count.
---
# Role

What the effect is and where it plays: projectile, hit, explosion, beam, aura, buff, pickup, ambient loop,
transition, cast skill; the engine if known. The role picks the size, timing and directions defaults in the other
knobs.

**Fixed when** the prompt names the role or a subject that is plainly one ("fireball" is a projectile, "shield
bubble" a buff). A subject with two readings ("bolt", lightning or a crossbow bolt; "slash", an arc or a straight
cut) is open.

**Ask:** "What is this effect in the game?" Options from the subject's readings, such as "Projectile that flies to
a target (Recommended)", "Hit that plays where something lands", "Aura that loops on a character", each saying
what it changes (directions, loop, size).

**Examples** (for an owner new to VFX; put the matching one in each option's description; sources in `vfx_notes.md`):
- Projectile: a thing that flies and lands, like the Dead Cells fire grenade (lobbed in an arc, bursts on contact,
  leaves fire). Pick when the eye should follow it to the target.
- Hit: a short spark where a blow lands, like a fighting-game hit spark with its freeze. Pick for melee contact and
  bullet impacts.
- Explosion: the biggest, brightest one-shot, like the Dead Cells powerful grenade. Pick for area damage and kills;
  it hides the enemy, so not for small contacts.
- Aura or buff: loops on a body and must leave the face and weapon readable, like Celeste's hair changing colour
  when a dash is spent. Pick for a lasting status.
- Ring that clears an area: shows its radius and keeps the middle open, like the Enter the Gungeon Blank.
Ask one plain line when it is open: what the player does while it plays. A player who is locked in place takes 1 to
2 s; a running player needs it under 0.5 s.

**Default:** the plainest reading of the subject.
