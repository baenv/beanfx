---
name: style
order: 7
group: look
stated: Does the request or a reference image say the art style (for example soft and translucent, hard retro pixels with outline and dither, painterly, a named console era)?
---
# Style

**Fixed when** the prompt names a look or an era ("16-bit", "SNES", "HD-2D", "NES"), the technique (outline,
dither, translucent), or an image shows it.

**Ask:** "Which look?" Offer whole looks, never single toggles:
- "Soft (Recommended): 1 px lines, translucent smoke, smooth glow"
- "Hard retro: opaque pixels, dark outline, checker dither, stepped pixel glow"
- "Painterly HD: more tones, no outline, soft volumes"
Ask outline or dither apart only when the owner picked a look and one of them is still open.

The style sets the colour pixels (opaque or translucent, outline, dither, tone count) and the light that goes with
them. Soft and painterly keep smooth light: the bloom at a pop reads as bright, at the cost of hundreds of colours
per frame. Hard retro steps the light (`light.steps`: four flat tones, dither only where it fades out), so the
whole frame keeps to a few dozen colours and reads as pixel art; pixel artists see smooth bloom over crisp
sprites as "not pixel". The owner can swap the light either way in words ("smooth glow", "pixel light",
"stepped light", "no blur").

**Examples:**
- Soft: Dead Cells, saturated pixels with smooth light on top.
- Hard retro: Shovel Knight, which keeps to the NES palette plus four colours. Readable on any ground.
- Painterly HD: Octopath Traveler (HD-2D), pixel sprites with soft high-definition light and depth.
- 1-bit dither (only when the owner hints at it): Return of the Obra Dinn. Dither shimmers when it moves fast, so
  keep it for slow or still effects.
Outline: none for light and gas; a 1 px dark outline for solid objects (a disc, a rock), or when the effect must
read on a busy ground (Dead Cells lets players outline projectiles for that reason).

**Preview:** give each option an ASCII `preview` of one small blob in that look (`#` solid, `%` dither,
`O` dark outline, `.` translucent, `+` smooth glow, `,` stepped glow, dithered):

```
soft             hard retro          painterly HD
  . + .          , , , ,              .:::.
 .+###+.          OOOOO              :=###=:
  . + .          ,O#%#O,              ':::'
                  OOOOO
                 , , , ,
```

**Default:** soft: 1 px lines and rims with white-hot cores, translucent smoke and mist, smooth additive light.
When the prompt asks for a pixel feel in words ("pixel art vibe", "crisp", "no blur", "retro"), recommend hard
retro, or soft with stepped light. Hard retro steps the light; soft and painterly keep it smooth unless the owner
says otherwise.
Pick one look and keep it in every frame.
