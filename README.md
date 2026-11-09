# beanfx

Pixel-art effects drawn as code. Describe an effect, and the `/beanfx` skill draws it in Python and exports a
sprite sheet with JSON that any engine plays.

See the effects and the live demo at https://beanfx.vhbien000.workers.dev/

## Install

```
/plugin marketplace add baenv/beanfx
/plugin install beanfx@beanfx
```

Then run `/beanfx <description | image>` in any project. It needs Python 3.10+; the first run creates `.venv/`
(numpy, pillow) in that project and writes each effect to `drafts/<name>/`, with its own copy of the drawing kit
in `drafts/<name>/kit/`. Plugin updates leave the kit of an existing draft as it was.

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

## License

MIT, see `LICENSE`.
