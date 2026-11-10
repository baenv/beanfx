# beanfx

Pixel-art effects drawn as code. Describe an effect, and the `/beanfx` skill draws it in Python and exports a
sprite sheet with JSON that any engine plays.

See the effects and the live demo at https://beanfx.vhbien000.workers.dev/

Used in a game: [Nine Heavens](https://play.nineheavens.online/) draws its skill effects with beanfx.

## Install

```
/plugin marketplace add baenv/beanfx
/plugin install beanfx@beanfx
```

Then run `/beanfx <description | image>` in any project. It needs Python 3.10+; the first run creates `.venv/`
(numpy, pillow) in that project and writes each effect to `drafts/<name>/`, with its own copy of the drawing kit
in `drafts/<name>/kit/`. Plugin updates leave the kit of an existing draft as it was.

## Quick start

```
/beanfx a fire burst, 64x64, side view, one-shot, strong glow
```

The skill asks about whatever the prompt leaves open (role, view, size, timing, palette, glow and so on), draws
the effect and writes it to `drafts/fire_burst/`:

| file | what it is |
|---|---|
| `fire_burst.py` | the effect as code; run it again with `.venv/bin/python fire_burst.py` after an edit |
| `out/sheets/fire_burst.png`, `.json` | the sprite sheet (glow baked in) and its JSON, the files a game loads |
| `out/sheets/fire_burst_color.png`, `_light.png` | colour and additive light as separate sheets, when the effect has a glow |
| `out/fire_burst.html` | a preview page that opens from disk with a double click |
| `out/*.gif`, strips | 4x previews on dark and mid grounds |

A reference image works the same way: `/beanfx path/to/reference.png make this a looping aura`.

Play it in a browser with the bundled runtime (`runtime/beanfx.js` in the skill, one ES module):

```js
import { loadFx, createFx } from "./beanfx.js";
const data = await loadFx("fx/fire_burst.json");
const fx = createFx(data, { x: 160, y: 140, onEnd: () => remove(fx) });
// each frame: fx.update(dt); fx.draw(ctx);
```

Phaser reads the JSON with `load.aseprite`. Other engines, and porting the draw code itself, are covered in
[`porting.md`](plugins/beanfx/skills/beanfx/porting.md).

## Output JSON

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

`porting.md` gives the rules an engine follows for each field.

## Game character casters

Two ready-made characters ship with the plugin, so an effect can be drawn on a real game sprite with no setup: a
robed cultivator with a straight sword and one with a staff. Each comes as a side view (east and west) and a
top-down view with 8 directions, with idle, run, cast, three attacks, hurt and dead.

| caster | weapon | view |
|---|---|---|
| `nghich_tien_kiem`, `nghich_tien_kiem_topdown` | sword | side, top-down (8 directions) |
| `nghich_tien_truong`, `nghich_tien_truong_topdown` | staff | side, top-down (8 directions) |

Pick "Game character" when `/beanfx` asks about a caster and name one. The effect is drawn in the character's
frame space: its pivot sits on the character's feet, its fps is a whole multiple of the animation's, and the hits
land on the animation's contact frames. The JSON records the caster, the cast offset and any aura parts, so the
engine places the effect and the character together.

<p>
  <img src="docs/media/caster_staff_thien_kiep.gif" width="48%" alt="Heavenly tribulation cast by the staff caster">
  <img src="docs/media/caster_sword_thap_tram.gif" width="48%" alt="Ten-slash combo on the sword caster">
</p>

Left: a summoned lightning tribulation that lands 110 px in front of the staff caster, with an aura round the
body. Right: a ten-slash combo on the sword caster, facing south.

## Credits

The light layer and the reuse path learn from [pixelfx](https://github.com/patch-gg/pixelfx) (MIT, Patch). beanfx
reimplements them in Python and ships no pixelfx code.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for where to edit, the tests and the release steps, and
[`CHANGELOG.md`](CHANGELOG.md) for what changed.

## License

MIT, see `LICENSE`.
