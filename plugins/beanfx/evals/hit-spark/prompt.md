---
runs: 1
max_turns: 80
timeout_seconds: 1500
tags: [draw, fast]
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write, Edit, WebSearch, WebFetch]
---

Use the beanfx skill to make a pixel-art hit spark for a side-view action game: 32x32 px, 10 frames at 20 fps, one-shot, hard retro style, a white and yellow palette with an orange light, medium glow, clear, no caster and no sound.

Work in the current folder (`export BEANFX_PROJECT=$PWD` before `setup.sh`). Do not ask me any question: take the recommended value for every knob I left open and go.
