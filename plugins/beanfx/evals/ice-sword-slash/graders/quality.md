---
type: llm
name: one-pass-delivery
weight: 3
---

The reply delivers one finished effect made in one pass, with the knobs the prompt left open chosen by the agent. Pass only when all of these hold:

- The reply shows research (findings with links) and a part list for the sword or blade (its parts and proportions).
- A brief of about 6 lines appears before the result, keeps 64x48, 20 fps, side view and one-shot, and is followed by a short list of the knobs the agent chose with one alternative each (style, palette, glow or clarity).
- The reply gives the path of the preview page (an .html file under out/) and of the gif.
- The reply says the checks passed, or names each check that still fails.
- The reply ends with a list of 3 to 5 suggested upgrades, each naming a part or knob, a value and a reason, and none of them is already applied.
- The agent did not run a benchmark, shape takes or glow takes, and did not polish in repeated look-and-fix rounds.
