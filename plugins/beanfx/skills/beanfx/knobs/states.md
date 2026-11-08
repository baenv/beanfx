---
name: states
order: 12
group: extra
stated: Does the request give the length or the form of each stage of the effect (for example how the swords gather and how they strike)?
applies: Does the effect play in several stages in sequence (charge then release then strike), have more than one carrier, or hand off from one part to another?
---
# Multi-state effects

An effect has several states when the prompt names a sequence ("charge up, the swords fly together, then
strike"), more than one carrier (swords, a caster, a seal), or a hand-off from one part to the next. Ask again
when the owner adds a state or changes how one plays.

1. Split it into states and put a state table in the reply: state, frames, seconds, what moves, which carrier.
2. Ask (in place of the plain timing and shape questions where they overlap): the total length with the seconds
   each state gets; the form of every state with two readings (a gather: spiral, rise, snap; a strike: one
   volley, clusters, a slanted rain, a vertical rain, one big blow); the copy count; the shape the parts hold
   between states (wheel, wedge, cloud, ring). Each option names its per-state split or its look, the recommended
   one first and marked. These may take more than one question each.
3. Recommend from what reads: a state the eye has to follow (spawn, gather, form) gets 1 to 2 s, and each part in
   it moves for at least 1 s; a 0.2 to 0.4 s hold or pull back before the release; the release 1 to 1.5 s with its
   parts staggered; a 1 to 2 frame peak; a 0.5 to 1 s dissolve. A one-shot with 4 or more states runs 4 to 7 s.
4. Put the state table in the script's docstring and keep each state's start and length as named constants, so
   one state can be re-timed alone and the later ones shift with it. Report the table with the frames used.

Learnt on `drafts/van_kiem_quy_tong`: a gather of 0.45 s per sword read as a jump, and "strike" was drawn as four
clusters when the owner meant a rain. Neither state had been asked about.

**Examples** (name one when explaining what a state is):
- Freeze then release: Celeste's dash, 15 frames with 3 frozen at the start.
- Trigger then payload: Noita's double trigger bolt releases its second spell only when it hits something.
- Key states first: block the start, the peak and the end with as few frames as read, then add frames between.
