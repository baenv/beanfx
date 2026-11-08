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
- "Hard retro: opaque pixels, dark outline, checker dither, light in bands"
- "Painterly HD: more tones, no outline, soft volumes"
Ask outline or dither apart only when the owner picked a look and one of them is still open.

**Default:** soft: 1 px lines and rims with white-hot cores, translucent smoke and mist, smooth additive light.
Pick one look and keep it in every frame.
