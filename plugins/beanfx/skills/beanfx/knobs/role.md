---
name: role
order: 1
group: fit
stated: Does the request say what kind of effect this is (projectile, hit, explosion, beam, aura, buff, pickup, ambient loop, transition, cast skill) or name a subject that is plainly one of them?
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

**Default:** the plainest reading of the subject.
