---
name: size
order: 3
group: fit
stated: Does the request give the size of the effect in pixels, a canvas or frame size, or its size against a character? A bare number that could be the cell or the palette ("256") does not count.
---
# Size

The cell in px and how big the effect draws in it.

**Fixed when** the prompt gives px, a cell, or a size against the body ("twice the character's height"). A bare
number with two readings ("256": the cell or the palette) is open.

**Ask:** "How big is the effect?" 2 to 4 cells from the role's row below, each saying what it does: a smaller cell
reads crisper at 1x and costs less; a bigger one shows more detail and parts. Recommend the middle of the row.

**Examples:** say each cell against the 24x38 body, and give an ASCII `preview` of the cell next to the body
(1 character about 8 px), so an owner who cannot picture "96 px" sees it:

```
64 px hit          128 px aura          256 px ultimate
 +----+             +--------+           +----------------+
 | o  |             |   o    |           |                |
 |/|\ |             |  /|\   |           |       o        |
 +----+             +--------+           |      /|\       |
                                         +----------------+
```

- Small (32 to 64): crisp at 1x, cheap, little room for detail. Dead Cells keeps its pixels low-res on purpose and
  accepts less detail as the price. Pick for busy screens and many copies.
- Medium (64 to 136): room for a core, a rim and sparks. Most skills and hits.
- Large (200 to 320): grand, a few big shapes; 1 px detail disappears unless drawn bigger. Ultimates and bosses.
- Rule of thumb: an effect no taller than the character reads as part of them; twice their height reads as a skill.
Ask the game's screen scale when it is unknown: a 64 px effect shown at 4x has very chunky pixels.

**Default** (canvas only as big as the effect needs around a 24x38 body; detail at 1 px). Every role in
`role.md` has a row; a role added there gets a row here.

| role | cell |
|---|---|
| projectile | 64 to 136 x 40 to 60 |
| hit | 64 to 128 |
| explosion | 128 to 224; 240 to 320 with smoke that rises and drifts |
| beam | 128 to 264 long x 32 to 100 |
| aura | 100 to 140 |
| buff | 64 to 100 |
| pickup | 56 to 112 |
| ambient loop | 64 to 320, the area it fills |
| transition | the screen (320x180 at 1x) |
| cast skill | 120 to 200; 200 to 320 for an ultimate or a boss move |

An effect of many layers (a ring, streaks, grit, a bloom, smoke) needs 128 or more: below that the layers merge
into one blob at 1x. Measured on pixelfx: implosion 208x184, plasma-explosion 224x200, cartoon-pow 184x144,
grenade 300x200, arcane-beam 264x100, gem-spin 64x64, collect-burst 112x108, transitions 320x180.
