---
name: view
order: 2
group: fit
stated: Does the request say the camera view of the game (side view or platformer, top-down, 3/4 or isometric), show it in a reference image, or say how many directions the effect needs?
applies: Does the effect travel, aim, face a way, or go from a caster to a target?
---
# View and directions

The camera of the game the sheet goes into, and how the engine gets every side or heading from the sheet
(section 5, `kit/facing.py`): side view is 1 direction facing east plus mirror; top-down and 3/4 are 8 or 16
heading rows, never rotated at runtime. A caster to target effect also splits into cast, travel and impact parts.

**Fixed when** the prompt names the view or the game genre with a known camera (platformer, fighting game is side;
twin-stick, RPG overworld is top-down or 3/4), states a direction count, or a reference image shows the camera.

**Applies** only when the effect has a heading. A round hit, aura, ring or buff is 1 row in every view: skip it.

**Ask:** "Which view is the game, and how many directions?" Options:
- "Side view, 1 direction plus mirror (Recommended)": smallest sheet, the engine flips it.
- "Top-down or 3/4, 8 directions": one row per heading, 8x the frames.
- "Top-down or 3/4, 16 directions": smooth aim for fast or long travel, 16x the frames.
- "Side view, east and west drawn": for an effect that reads wrong when flipped (text, a one-sided light).
When the effect goes from a caster to a target, say in the question that it ships as cast, travel and impact parts
so the range is free.

**Default:** side, 1 direction, mirror True; 8 rows for a top-down projectile or cone, 16 when it travels fast or far.
