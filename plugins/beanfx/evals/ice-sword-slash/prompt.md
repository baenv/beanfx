---
runs: 1
max_turns: 100
timeout_seconds: 1800
tags: [draw, object]
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write, Edit, WebSearch, WebFetch]
---

Use the beanfx skill to make an ice sword slash: a frost blade sweeps an arc and leaves ice shards. Side view, 64x48 px, about 0.7 s at 20 fps, one-shot, no caster and no sound.

Work in the current folder (`export BEANFX_PROJECT=$PWD` before `setup.sh`). Do not ask me any question: take the recommended value for every knob I left open and go.
