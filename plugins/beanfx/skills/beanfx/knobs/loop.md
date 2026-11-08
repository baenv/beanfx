---
name: loop
order: 5
group: fit
stated: Is it settled whether the effect loops or plays once, either because the request says so or because the kind of effect has only one reading (an aura, idle or ambient effect always loops; a hit, explosion or impact always plays once)?
---
# Loop or one-shot

**Fixed when** the prompt says loop, looping, idle, ambient, once, one-shot, or "until it ends", or the role has
one reading (an aura loops, a hit plays once; list the implied value under "Suggestions"). Open when the role
leaves both readings (a beam can be a held loop or a one-shot blast).

**Ask:** "Does it loop or play once?" Options "Loop, seamless" and "One-shot: anticipation, peak, dissolve", plus
"Start, loop, end" for a held effect (a beam, a channel), which records its states in the JSON.

**Examples:**
- Loop: runs until the game stops it, first and last frame join with no jump, like a torch or burning wood in
  Noita. Pick for auras, torches, idle effects. Two copies side by side should start on different frames so they do
  not pulse together.
- One-shot: builds, peaks and ends empty, like the Dead Cells grenade blast. Pick for hits and explosions.
- Start, loop, end: a start flare, a middle that repeats while the player holds, a fade, like Dead Cells' ground fire
  that burns for 7 s after the grenade. Pick for beams, channels and ground zones.
A flicker loop shorter than 8 frames looks mechanical; an idle loop needs at least 2 to 4 frames.

**Default:** from the role: aura, ambient and a held beam loop; hit, explosion and a cast play once.
