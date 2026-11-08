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

**Default:** from the role: aura, ambient and a held beam loop; hit, explosion and a cast play once.
