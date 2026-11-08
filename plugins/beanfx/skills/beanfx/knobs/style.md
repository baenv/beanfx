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
- "Hard retro: opaque pixels, dark outline, checker dither, smooth glow on top"
- "Painterly HD: more tones, no outline, soft volumes"
Ask outline or dither apart only when the owner picked a look and one of them is still open.

The style sets the colour pixels only (opaque or translucent, outline, dither, tone count). The light stays
smooth in every look: the bloom at a pop or a flash is what makes an effect read as bright, and light cut into
bands loses it. Cut the light into bands (`light.bands`, `pfx.bands`) only when the owner says so in words such
as "NES authentic", "no smooth glow", "stepped light" or "banded glow".

**Examples:**
- Soft: Dead Cells, saturated pixels with smooth light on top.
- Hard retro: Shovel Knight, which keeps to the NES palette plus four colours. Readable on any ground.
- Painterly HD: Octopath Traveler (HD-2D), pixel sprites with soft high-definition light and depth.
- 1-bit dither (only when the owner hints at it): Return of the Obra Dinn. Dither shimmers when it moves fast, so
  keep it for slow or still effects.
Outline: none for light and gas; a 1 px dark outline for solid objects (a disc, a rock), or when the effect must
read on a busy ground (Dead Cells lets players outline projectiles for that reason).

**Default:** soft: 1 px lines and rims with white-hot cores, translucent smoke and mist, smooth additive light.
The light is smooth in every style unless the owner asks for bands.
Pick one look and keep it in every frame.
