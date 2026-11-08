# Porting a beanfx effect into an engine

Two routes. Most games play the sheet (A). Port the draw code (B) only when the sheet cannot do the job.

## A. Play the sheet

Every engine needs the same five things from `<name>.json`:

- **Frames.** `frames[i].frame` is the rect of frame i in `<name>.png`; `meta.beanfx.frameSize` and `columns` give
  the same grid for engines that slice by cell. `meta.frameTags` names each state, and each heading row when there
  are several (`east`, `east/strike`).
- **Pixels.** Nearest filtering, no compression, no mipmaps. A smoothed or compressed sheet loses the pixel edges.
- **Pivot.** `meta.beanfx.pivot` is in px from the cell's top-left (y down). Place that point on the caster's feet,
  the projectile's centre or the target. Flipped for west: `mirror_pivot`.
- **Timing.** `fps` (or each frame's `duration` in ms), `loop` and `end`: `remove` the sprite after the last
  frame, `hold` keep the last frame showing (or hand over to a loop), `loop` play again.
- **Light.** Simplest: play `<name>.png` alone; the glow is baked in as colour with alpha, which reads well over
  dark and mid scenes. Better: play `<name>_color.png` and, above it on the same frame, `<name>_light.png` with
  additive blend, scaled by `light_gain` (dim it for a bright scene, drop it in a low-end mode).

The rest, when the JSON has it:

- **Directions.** `directions: 1`: drawn facing east; for west flip horizontally and use `mirror_pivot` (or the
  `sheets.west` file when `mirror` is false). 8 or 16: play the heading row `round(atan2(dy, dx) / tau * n) mod n`
  (y down), never rotate the sprite.
- **Parts.** `parts.cast` at the caster, `parts.travel` moved from caster to target at `speed` px/s, `parts.impact`
  at the target when the travel arrives.
- **Act.** `act.windup`: start the character's own animation that many seconds before frame 0. `act.poses`: at
  each key's `t` (s from frame 0) play the character's animation mapped to its `pose` name (idle, guard, windup,
  cast, channel, release, follow, recover); `snap` cuts to it, `smooth` blends. `act.hits[k]`: at `t` (frame
  `frame`) freeze everything, effect and characters, for `freeze` s, shake the camera `shake` px, push the target
  `push` px away from the caster and play its `react` (flinch, stagger, knockback, launch). When the hit has them:
  shake along `dir` (degrees, y down, 0 along the facing; mirror it to 180 - dir for a flipped sprite) for
  `shake_time` s, tint the target white for `flash` s then half for one frame, and play the `sound` cue (`hit_light`,
  `hit_heavy`, `hit_finisher`, `hit_blast`, mapped to the game's own sounds) on the contact frame. `act.target.x` is
  where the target stands, px from the pivot along the facing.
- **Pages.** A big effect splits into `<name>_p<k>.png`, each with its own Aseprite JSON. `<name>.json` lists every
  frame with its `page`, and `meta.beanfx.pages` lists the files. Load every page and build one animation whose
  frames come from the page each frame names.

- **Budget.** A sheet costs its decoded size in texture memory: frames x w x h x 4 bytes, twice that with the
  colour and light pair. `export.write` prints a note above 64 MB. Over it on phones: load the effect only when it
  plays and free it after, drop the light sheet and play `<name>.png`, or for a full-screen cutscene play a video.

### Browser, no engine

`runtime/beanfx.js` in this skill plays the export on a 2D canvas: one ES module, no dependencies. Copy it into the
game next to the exported files.

```js
import { loadFx, createFx } from "./beanfx.js";
const blast = await loadFx("fx/blast.json");          // loads the colour and light sheets (every page)
const fx = createFx(blast, { x: 160, y: 140, flip: false, state: "strike", heading: angle,
  lightGain: 1, onHit: (h) => target.react(h.react, h.push), onEnd: () => remove(fx) });
// each frame, dt in s
fx.update(dt);                                         // holds still by itself during a hit-stop
ctx.imageSmoothingEnabled = false;
ctx.save(); ctx.translate(...fx.shake); drawScene(); fx.draw(ctx); ctx.restore();
```

It follows the rules above: pivot on (x, y), flip about the pivot, `end` (remove sets `fx.done`, hold keeps the
last frame), states by tag, heading rows by `round(atan2(dy, dx) / tau * n) mod n`, pages, and each `act.hits`
entry as a freeze with a decaying shake. `docs/index.html` in the beanfx repo is a working page.

### Phaser 3 and 4

The JSON is the Aseprite array layout, so `load.aseprite` reads it and `createFromAseprite` makes one animation per
tag. Set `pixelArt: true` in the game config.

```js
// preload
this.load.aseprite("blast", "fx/blast.png", "fx/blast.json");
this.load.atlas("blast_light", "fx/blast_light.png", "fx/blast.json");   // same rects, JSON array layout
this.load.json("blast_meta", "fx/blast.json");
// create
this.anims.createFromAseprite("blast");
const { fps, pivot, frameSize: [w, h], frames } = this.cache.json.get("blast_meta").meta.beanfx;
this.anims.create({ key: "blast_glow", frameRate: fps,
  frames: this.anims.generateFrameNames("blast_light", { prefix: "blast ", start: 0, end: frames - 1 }) });
const fx = this.add.sprite(x, y, "blast").setOrigin(pivot[0] / w, pivot[1] / h).play("strike");
// a paged sheet: load.atlas each `pages[k].image` with `pages[k].json` as key `blast_p${k}`, then
// this.anims.create({ key: "blast", frameRate: fps,
//   frames: this.cache.json.get("blast_meta").frames.map((e) => ({ key: `blast_p${e.page}`, frame: e.filename })) });
const glow = this.add.sprite(x, y, "blast_light").setOrigin(pivot[0] / w, pivot[1] / h)
  .setBlendMode(Phaser.BlendModes.ADD).play("blast_glow");
```

Use `<name>_color.png` for the first sprite when the glow plays on its own sprite, or play `<name>.png` alone and
leave the glow sprite out.

### Godot 4

Set Project Settings > Rendering > Textures > Default Texture Filter to Nearest (or `texture_filter` on the node).
Build the `SpriteFrames` from the JSON once, then save it as a `.tres` or build it at load:

```gdscript
static func frames_from(json_path: String, png_path: String) -> SpriteFrames:
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(json_path))
	var bfx: Dictionary = data.meta.beanfx
	var dir := png_path.get_base_dir()
	var pages: Array = bfx.get("pages", [{"image": png_path.get_file()}])
	var texs: Array = pages.map(func(p): return load(dir.path_join(p.image)))
	var sf := SpriteFrames.new()
	sf.remove_animation("default")
	for tag in data.meta.frameTags:
		sf.add_animation(tag.name)
		sf.set_animation_speed(tag.name, bfx.fps)
		sf.set_animation_loop(tag.name, bfx.loop)
		for i in range(int(tag.from), int(tag.to) + 1):
			var e: Dictionary = data.frames[i]
			var r: Dictionary = e.frame
			var at := AtlasTexture.new()
			at.atlas = texs[int(e.get("page", 0))]
			at.region = Rect2(r.x, r.y, r.w, r.h)
			sf.add_frame(tag.name, at)
	return sf
```

On the `AnimatedSprite2D`: `centered = false`, `offset = -Vector2(pivot[0], pivot[1])` (with `flip_h`, use
`-mirror_pivot`). The glow: a child `AnimatedSprite2D` built from `<name>_light.png` with a `CanvasItemMaterial`
whose `blend_mode` is `BLEND_MODE_ADD`, playing the same animation, `modulate` set to `light_gain`.

### Unity

Unity's Aseprite Importer reads `.aseprite` files, not this JSON; slice the PNG by its grid. Import the sheet as
Texture Type Sprite, Sprite Mode Multiple, Filter Mode Point, Compression None. Sprite Editor > Slice > Grid By
Cell Size with `frameSize`, pivot Custom at (`pivot[0] / w`, `1 - pivot[1] / h`) since Unity's y points up. Make
an AnimationClip per tag at `fps` from frames `from` to `to`. The glow: a child SpriteRenderer with the light sheet
and a material whose shader blends additively (`Blend One One`).

### GameMaker, Defold, LÖVE

- GameMaker: Sprite Editor > Import Strip Image with the frame width, height, count and `columns` per row; origin
  at `pivot`; turn off colour interpolation for the texture group; draw the glow with `gpu_set_blendmode(bm_add)`.
- Defold: a tile source with tile size `frameSize`, one animation per tag (tiles count from 1, so `from + 1` to
  `to + 1`); the glow sprite's blend mode Add.
- LÖVE: `love.graphics.setDefaultFilter("nearest", "nearest")`, one `love.graphics.newQuad` per frame rect, the
  glow drawn under `love.graphics.setBlendMode("add")`.

## B. Port the draw code

Port when the sheet is too big or too many (a recolour per enemy, many sizes), when the effect must follow a
moving target or stretch to a changing distance, or when the engine draws pixels itself. A beanfx draft already has
the shape that ports: each frame is a pure function of the frame index and the seed, drawn into two buffers.

1. **Two buffers.** Colour is a shade map of palette indices (-1 empty) painted to RGBA; light is a float map summed
   from glows. Recolour at runtime by swapping the palette array. Keep both buffers separate in the port.
2. **Shapes are distance tests per pixel.** Each helper evaluates pixel centres (`x + 0.5 - pivot`): a disc is
   `hypot(dx, dy) < r`, `fxlib.stroke` is the distance to a polyline minus a half width that tapers along it,
   `fxkit.rot` turns the grid into the travel frame. Port them as functions over one pixel; run them over the cell
   on the CPU, or as a fragment shader where each pixel calls them.
3. **Light.** `L += k * (1 - d)^2` where `d = distance / r < 1`, summed over every glow; tint with the light ramp.
   On screen add it (`dst + light`). Over transparency: `alpha = max(a, max(light))`, `rgb = (rgb * a + light) /
   alpha`, as `pfx.composite` does.
4. **Dither.** The 4x4 Bayer matrix `[[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]] / 16`; a pixel
   shows where its threshold is below the fade.
5. **Randomness.** numpy's generator does not exist in the engine. Either bake what it gave (the noise lattice from
   `fxlib.lattice(nx, ny, seed)`, each particle's size, speed and delay) into a small table the port reads, or
   switch the draft to a hash (`fxkit.hsh(i, salt)`) that ports in a few lines, render the sheet again, and port
   that.
6. **Timing.** `f = floor(t * fps)`; a loop takes `f mod frames`. Keep the state starts as named constants.
7. **Budget.** A sheet costs nothing per frame to draw; a port does. Time the port's frame at the peak (the most
   particles and glows) on the slowest target device: keep one effect under 1 ms of a 16.7 ms frame at 60 fps, and
   under 0.25 ms when a dozen can play at once. Over budget: draw the light at half resolution, cap the particle
   count, bake the noise into a texture, or go back to the sheet.

Check the port against the sheet: render frames 0, the peak and the last from the port, and diff each with the
same cell of `<name>_color.png` and `<name>_light.png`. The colour should match pixel for pixel; the light within
1 / 255 of rounding. A difference is a bug in the port, not a new take.

```
python3 -c "import numpy as np, sys; from PIL import Image; a, b = (np.asarray(Image.open(p), int) for p in sys.argv[1:3]); print(np.abs(a - b).max(), (a != b).any(-1).sum(), 'px differ')" sheet_cell.png port_cell.png
```
