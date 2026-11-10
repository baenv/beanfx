# Output JSON

`<name>.json` is the Aseprite "array" layout, so tools that read Aseprite exports read it. Everything beanfx adds
sits under `meta.beanfx`.

```json
{
  "frames": [
    { "filename": "fire_burst 0", "frame": { "x": 0, "y": 0, "w": 64, "h": 64 }, "duration": 42 }
  ],
  "meta": {
    "image": "fire_burst.png",
    "size": { "w": 320, "h": 256 },
    "frameTags": [{ "name": "strike", "from": 6, "to": 19, "direction": "forward" }],
    "beanfx": {
      "name": "fire_burst", "fps": 24, "frames": 20, "rows": 1,
      "frameSize": [64, 64], "columns": 5, "pivot": [32, 56],
      "loop": false, "end": "remove",
      "sheet": "fire_burst.png", "color": "fire_burst_color.png", "light": "fire_burst_light.png",
      "blend_light": "add", "light_gain": 1.0,
      "states": { "charge": [0, 5], "strike": [6, 19] },
      "view": "side", "directions": 1, "facing": "east", "mirror": true, "mirror_pivot": [32, 56],
      "act": { "windup": 0.0, "hits": [{ "frame": 8, "t": 0.3333, "freeze": 0.12, "shake": 3 }] }
    }
  }
}
```

Always present in `meta.beanfx`:

| field | meaning |
|---|---|
| `fps`, `frames`, `rows` | playback rate, frames per row, and heading rows (1, 8 or 16) |
| `frameSize`, `columns` | the cell `[w, h]` and the grid width, for engines that slice by cell |
| `pivot` | `[x, y]` in px from the cell's top-left, y down: the point to place on the feet, the projectile or the target |
| `loop`, `end` | `end` is `loop`, `remove` (drop the sprite after the last frame) or `hold` (keep the last frame) |
| `sheet` | the sheet file; a large effect has `pages` instead, a list of page files with their frame ranges |

Present when the effect uses them:

| field | meaning |
|---|---|
| `color`, `light`, `blend_light`, `light_gain` | the colour sheet and the light sheet to add over it on the same frame |
| `states` | named frame ranges `[from, to]`, also in `meta.frameTags` |
| `view`, `directions`, `facing`, `mirror`, `mirror_pivot` | the direction: one row drawn facing east and flipped for west, or 8 or 16 heading rows (`row_of` gives the row for an angle) |
| `act` | timing round the effect: `windup`, `hits` (contact frame, freeze, shake, push, react), `poses`, `target` |
| `parts` | `cast`, `travel` and `impact` sheets of a caster to target effect, each with its own size, pivot and anchor |
| `caster` | the game character the effect rides on: animation, layer, offset per direction, aura parts |

[`porting.md`](../plugins/beanfx/skills/beanfx/porting.md) gives the rules an engine follows for each field.
