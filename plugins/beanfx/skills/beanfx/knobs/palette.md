---
name: palette
order: 8
group: look
stated: Does the request give a palette (hex values, a named palette, the game's palette) or the hue of the effect's light, or show them in a reference image? Colour words that describe the subject (a dark sphere, white sparks, a red dragon, an orange pumpkin) do not count.
---
# Palette and light hue

3 to 5 hue-shifted tones per material (shadows cool, lights warm or white) plus the light hue.

**Fixed when** the prompt names colours, a palette (a hex list, "PICO-8", "the game's palette") or the light hue,
or an image shows them. The subject's own colour ("pumpkin" is orange) is open, and so are colour words that
describe the subject ("a dark sphere collapses to a white point" says what is dark, not the ramp).

**Ask:** "Which colours?" 2 to 4 named ramps with their hex steps from shadow to white core, plus the light hue,
such as "Ember: #3a1020 #8a2a18 #e0601c #ffc040 #fff4d0, light orange (Recommended)" and a cool or off-element
alternative. Say what each does on a dark and a light ground.

**Examples:**
- Warm ramp (fire, explosions, gold): shadows lean red-purple, lights lean yellow-white. Slynyrd's rule: shift the hue
  a little at each step, up to about 20 degrees, or the ramp looks flat.
- Cool ramp (ice, magic, tech): shadows lean violet, lights lean cyan and white.
- High-saturation for threats: Dead Cells makes enemies, projectiles and spells the most saturated and brightest
  things on screen, so the player sees what to dodge. Ambient effects sit lower.
- Small locked palette (8 to 16 colours): instant retro cohesion, like Shovel Knight on the NES palette.
Say what each ramp does on the game's brightest ground (snow, lava, sky): a white flash vanishes on snow.

**Default:** the element's natural ramp, hue-shifted, white only at the hottest core.
