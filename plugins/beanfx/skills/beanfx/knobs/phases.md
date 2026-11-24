---
name: phases
order: 5
group: fit
stated: Does the request give how long each phase of the cast takes (wind-up, release, travel, impact, recovery) in seconds or frames, or name a feel for the split such as "instant", "snappy" or "long charge"? A total length alone does not count.
applies: Is the effect cast or swung by someone (a skill, spell, attack or strike), or does it go from a caster to a target?
---
# Cast phases

How the length from `timing` splits across the phases of a cast. `timing` sets fps and the total; this knob sets
where that time goes, and it decides how the move feels in the hand more than the total does.

The phases, in the words of fighting games (startup, active, recovery), MOBAs (cast point, backswing) and Sakurai
(wind-up, strike, follow-through):

| phase | what plays | pose key (`ex::POSES`) |
|---|---|---|
| wind-up | the gather or charge before anything is thrown: the anticipation that says how strong it will be | `windup` |
| release | the cast point: the burst at the hand or the blade's smear, the 1 to 2 frame peak | `cast` / `release` |
| travel | the carrier crosses to the target (projectiles, beams, dashes only) | `release` |
| impact | the hit on the target, with its freeze from `timing` | (`act.hits`) |
| recovery | the follow-through and dissolve: wisps, embers, the caster settling | `follow` / `recover` |

**Fixed when** the prompt gives the seconds or frames of each phase, or names the feel ("instant", "snappy",
"heavy charge", "cinematic"). A total length alone ("1.5 s") is open: that is `timing`. An effect that `states`
already splits into named stages takes its phases from that state table and skips this question.

**Applies** to a cast, swing, strike or caster to target effect. An aura, ambient loop, pickup or a hit spark with
no caster leaves it out.

**Ask:** "How does the time split between charging, the hit and the fade?" (plain words: "how long before the
blow lands, and how long it lingers"). Options, the recommended one first, each with its split in seconds and
frames at the brief's fps:
- "Snappy (Recommended for a player skill)": wind-up 0.15 to 0.3 s, release 2 to 3 frames, impact on time,
  recovery 0.3 to 0.6 s. Responsive in the hand; the weight comes from the follow-through and the freeze.
- "Heavy charge": wind-up 0.5 to 1 s with a 0.1 to 0.2 s hold at full charge, release 3 to 4 frames, a heavy or
  finisher freeze, recovery 0.6 to 1 s. For a charged shot, a boss attack or anything the other side must see
  coming.
- "Instant": wind-up 0 to 2 frames, the release on frame 0 to 2, recovery 0.3 to 0.5 s. For a basic weapon hit, a
  bullet or a reflex skill; all the weight goes into the impact and the follow-through.
- "Cinematic": wind-up 1 to 2 s in stages, release 4 to 6 frames, recovery 1 to 1.5 s. For an ultimate or a
  finisher that pauses the play; it usually wants `states` too.
On a game character the release falls on the animation's contact frame (`r.contact(anim)`), so the wind-up is the
frames before it and the option names that frame.

**Recommendations for the best timing** (use them to pick the recommended option and to set the split when the
owner leaves it open):
- The wind-up sells the power: a bigger wind-up reads as a stronger blow (Sakurai). Give it at least 3 frames so it
  reads at all, and end it on a short hold or pull-back (2 to 4 frames, about 0.1 to 0.2 s) right before the
  release.
- The release is short: the peak frame 1 to 2 frames, held 1.5 to 2.5 times a build-up frame (`timing`). A release
  longer than 0.15 s reads as a slow push, not a blow.
- Recovery is longer than the wind-up for an effect and shorter than it for the player: the effect's dissolve takes
  50 to 65 percent of the one-shot, while the caster's own follow-through should hand control back fast, since a long
  recovery makes a character feel unresponsive (Cooper). Weight can skip the anticipation entirely if the
  follow-through is strong enough (Jungbluth), which is the "Instant" option.
- Travel is set by speed, not by a guess: frames = distance / speed. A carrier reads at about 4 to 12 px per frame at
  1x; above about 16 px per frame it needs a streak behind it, or it seems to jump. Keep travel under about 0.5 s
  for a player skill so the hit still feels caused by the press.
- Player skills stay under about 1 s from the press to the impact; enemy and boss attacks get longer wind-ups
  (0.5 to 1.5 s) because the player has to read and dodge them, the "tell" of fighting games and action RPGs.
- The impact freeze (`timing`) sits inside the impact phase and stops the effect too: hold the impact frame for the
  freeze, then let the recovery run.
- Ease in and out: slow into the hold at the end of the wind-up, snap out of it into the release, and let the
  recovery decelerate (`mo` drag) rather than fade linearly.

**Examples:**
- Fighting games list every attack as startup, active and recovery frames at 60 fps; a light punch is about 4
  startup and 3 active frames, a heavy one 10 to 15 startup with a long recovery.
- Dota 2 splits a spell into cast point (when it takes effect) and backswing (the animation after, which a player
  can cancel).
- Smash Bros. attacks have four phases: standby, wind-up, strike and follow-through; the follow-through is the
  window in which the attacker can be punished.

**Preview:** give each option an ASCII `preview` of the split, one mark per frame at the brief's fps (`.` wind-up,
`=` hold, `#` release and peak, `>` travel, `X` impact with its freeze, `-` recovery):

```
snappy        ....=##>>>XX----------
heavy charge  ..............===##>>>XXXX--------------
instant       ##>>XXX---------
```

**Writing it down:** keep each phase's start and length as named constants in the draft (like the state table in
`knobs/states.md`), put the split in the brief and the reply, set `Spec.windup` to the seconds of wind-up the game
plays before frame 0 (when the sheet starts at the release), and key `Spec.poses` with `ex::pose` on the phase
starts (`windup`, `cast`, `release`, `follow`, `recover`), so the engine can drive the caster from the same split.

**Default:** snappy for a player skill, heavy charge for an enemy or boss attack, instant for a basic weapon hit.
