---
type: llm
name: one-pass-delivery
weight: 3
---

The reply delivers one finished effect made in one pass. Pass only when all of these hold:

- A brief of about 6 lines (role, view, size and timing, palette, style and glow, shape and beats) appears before the result, and it keeps the values the prompt fixed: 32x32, 10 frames, 20 fps, one-shot, hard retro.
- The reply gives the path of the preview page (an .html file under out/) and of the gif.
- The reply says the checks passed, or names each check that still fails. It never claims success over a failing check.
- The reply ends with a list of 3 to 5 suggested upgrades, each naming a part or knob, a value and a reason, and none of them is already applied.
- The agent did not run a benchmark, shape takes or glow takes, and did not polish in repeated look-and-fix rounds.
