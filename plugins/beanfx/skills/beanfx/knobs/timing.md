---
name: timing
order: 4
group: fit
stated: Does the request give the speed of the effect as fps, a frame count, or a length in seconds? "Fast" or "slow" alone does not count.
---
# Timing

fps and frame count, which together give the length.

**Fixed when** the prompt gives fps, frames or seconds. "Fast" or "slow" alone is open.

**Ask:** "How long and how smooth?" Options such as "24 fps, 1.5 s, 36 frames (Recommended)", "30 fps, 2 s, 60
frames: smoother, a bigger sheet", "12 fps, 1 s, 12 frames: choppy retro, a small sheet". Name the frame count and
the sheet cost in each.

**Examples:** give each option an ASCII `preview` of the timeline, one character per frame, so the owner
sees where the time goes (`.` build-up, `#` peak, `-` fade):

```
24 fps, 1 s:   ....##------------------
12 fps, 1 s:   ..#-------
```

- 12 fps: choppy and retro, a small sheet. Store-bought pixel effect packs often run 7 to 18 frames at about 70 ms
  each. Pick for NES and Game Boy looks.
- 24 fps: smooth, the usual choice for hits and explosions.
- 30 fps and up: very smooth for long loops and fast streaks, a big sheet. Celeste's dash lasts 15 game frames, 3 of
  them frozen.
- How time splits in a one-shot: build-up about 15 to 25 percent, the peak 1 to 2 frames, the fade 50 to 65
  percent. The peak frame holds 1.5 to 2.5 times longer than the build-up frames.
- **Impact freeze** (for an effect that hits something; it goes into `act.hits`): the game stops everyone for a
  moment on contact, and a stronger hit stops longer (Sakurai, Smash Bros.). Offer the weights of `ex.WEIGHTS`: "Light: a quick
  tap, the screen barely stops", "Heavy (Recommended for a strike): a clear stop, a short shake, the target slides
  back", "Finisher: a long stop and a hard shake, the target is thrown up", "Blast: a short stop, a long rumble" (for
  an explosion). A combo asks once and escalates light, light, heavy, finisher.
  Say in plain words: "how long the hit freezes the screen". Ask it with timing when the role is a hit, an
  explosion or a strike and the prompt does not say.

**Default:** 24 to 30 fps; one-shot 1 to 3 s with a long decay, loop 2 to 3 s; 12 fps only for a choppy retro look
or a small sheet.
