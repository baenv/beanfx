---
name: sound
order: 17
group: extra
stated: Does the request say what the effect should sound like (retro chiptune or soft, metal, fire, lightning and so on) or say it needs no sound? "With sound" alone does not count.
applies: Does the request ask for sound, audio, SFX or a sound effect for the effect?
---
# Sound

An optional sound that sits on the effect's own timing: a hit cue on every act hit (its weight sets how heavy it
sounds), a charge over a gather or cast state, a whoosh over a swing or travel state, a tail over a dissolve, a hum
for a loop. Synthesised in Rust by `kit/src/sfx.rs`, seeded, written as WAV next to the sheet and listed in
`meta.beanfx.sound`. The sheet and JSON stay the main output; sound never changes the drawing.

**Fixed when** the prompt describes the sound ("8-bit clang", "soft magical chime", "crackling thunder") or says
none. "With sound" alone is open: ask the voice and the element.

**Applies** only when the request asks for sound. Otherwise skip it and write no audio.

**Ask:** "What should it sound like?" Options:
- "Retro (Recommended)": square and triangle waves crushed to 6 bits, the 8 and 16-bit console sound that suits
  pixel art.
- "Real": physical models, a blade that lands as a thud and a short chink (blade on blade rings), and thunder
  that cracks then rolls; other elements
  sound soft. Recordings in the project's `sounds/` take over when their names match (below).
- "Soft": sine tones and filtered noise, smoother and quieter in a mix.
- "No sound".
Follow-up when open: the element (metal, lightning, fire, ice, wind, arcane, or neutral), offered from the subject:
a sword is metal, a thunder strike is lightning.

**Examples:**
- Retro: Shovel Knight and Celeste lean on chip-style hits that cut through music.
- Real: a sword clash or a thunder strike that should sound like the thing, as in most modern action games.
- Soft: cosy and ambient games keep magic quiet so it sits under the score.

**How it ships:** `sfx::write(out, name, Some(&mut meta), sfx::Write { seed, voice, element, .. })` after `ex::write`, then `sfx::check(out, &meta)` with the other checks. Files: `<name>_sound.wav` (the whole effect from frame 0) and one WAV per cue; each
act hit names its cue in `sound`. The first pass always brings two or three takes in `out/sound_takes/` for the
owner to pick by ear (SKILL.md, Sound).
Recordings: `sounds/` in the project (or `BEANFX_SOUNDS`) with `<element>_<kind>[_<weight>]*.wav`, such as
`metal_hit_heavy_01.wav`, `lightning_hit.wav`, `metal_whoosh.wav`; a matching cue uses the file (picked by seed,
onset on the hit, pitched by weight) and `sound.samples` lists the files. Only CC0 or the owner's own recordings
(Kenney's audio packs and OpenGameArt's CC0 sets fit); `sounds/` is gitignored.

**Preview:** give each option this ASCII `preview` of its wave (`#` loud, `.` quiet):

```
retro              real                soft               none
#_#_#_#_ _ _       ^!^~~~~~~-~-~ . .   ~^~^~.~.~ . .
#_#_ _             !ring~~~~~~~~ .     ~^~.~ .
```

**Default:** none; retro when the request asks for sound and names no voice; real when it names a metal or
thunder sound that should sound true to life.
