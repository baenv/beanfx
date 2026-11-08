---
name: glow
order: 9
group: look
stated: Does the request say how strong the glow or light of the effect is (subtle, medium, strong, no glow), or show it in a reference image? "Sparkling" or "glowing" alone does not count.
---
# Glow level

subtle, medium or strong: how bright the lit parts are. How far the light spreads is the `clarity` knob. The k
values and the measured mean are in SKILL.md 2a.

**Fixed when** the prompt names the strength ("faint", "blinding", "no glow") or an image shows it. "Sparkling"
implies glints and stronger point light but is open.

**Ask:** "How strong is the glow?" Options "Medium (Recommended): reads on dark and mid grounds", "Strong: bright
cores and many flashes, blows out on a light ground", "Subtle: tight cores for a busy screen". The light ships as its own sheet with
`light_gain`, so the engine can still tune it.

**Examples:**
- Subtle: for a busy screen with many effects. Dead Cells added a switch to turn bright flashes down after players
  complained, which is why beanfx ships the light as its own sheet with `light_gain`.
- Medium: reads on dark and mid grounds; the safe default.
- Strong: for finishers and big magic; Celeste's hair goes white at the fastest moment of the dash. Blows out on a
  light ground.
- No glow: flat pixels, the authentic NES look of Shovel Knight. Offer it only when the owner wants that flat look in words.

**Default:** medium.
