# Light: style, sparkle, glow level and clarity

Read before drawing the light of a draft. `knobs/glow.md` and `knobs/clarity.md` hold the questions; this file
holds the values.

**The light follows the style.** Sum the glows into one float map `l` (`Array2<f64>`), repeat it to three
channels (`l3`), then colour it with `pfx::tint(&l3, &[deep, hue, pale, "#ffffff"])?` and pass that to
`pfx::composite`. Soft and painterly pass `l` as it is: smooth light, a bloom of hundreds of colours. Hard retro
passes `lt::steps(&l, lt::Steps { levels: 4.0, ..Default::default() })`: flat steps with hard edges inside the light and a 4x4 ordered dither only in
the outer step, so the halo thins to single pixels and a frame keeps to a few dozen colours, the way a
hand-drawn pixel effect does. Smooth bloom over crisp sprites is what reads as "not pixel art" to pixel artists;
the stepped light trades some of the brightness at a pop for that read. The owner can swap either way ("smooth
glow" on hard retro, "pixel light" on soft). With stepped light keep the pools tight (pool radius at the low end
of `lt::glow_level`) so the dithered halo stays a few px wide, never a dotted disc round the whole cell, and give the
flash its read by a 1 to 2 frame white core instead. Light only what
emits: hot cores, eyes, bolt heads, blade edges, the landing flash, sparks and embers. Stack two lights on
each of those, the way pixelfx does: a tight core (r 4 to 15) and a pool along it. Dark space between the
lit parts is what makes the light read; a glow over the whole cell reads as haze.

**Sparkle is light that lives a few frames.** Give every spark, glint, sword entry and hit a `lt::Flashes`
light that starts at its k and dies in 3 to 8 frames (`lt::flash_at(&mut l, &c, f, f0, x, y, r, k, life)` draws it
from the frame alone, so `render(f, seed)` stays per frame for `ex::check_seeds`; `Flashes` keeps state between
frames and suits only a loop that draws frames in order), and multiply the k of lasting glints by
`lt::flicker(i, f, lt::Flicker { seed, ..Default::default() })` so they blink out of step. Draw the glint itself as opaque pixels (`fk::twinkle`,
a white heart). A big move wants dozens of these at its peak; pixelfx myriad-swords carries 400 to 800 bright
points a frame and its light changes about three times as much between frames as a draft lit by still pools.

**Glow level** (a brief knob: subtle, medium, strong; medium when the owner leaves it open) sets how
bright the lit parts are (`lt::glow_level(name)` holds the table):

| level | core k | pool along a part | mean |
|---|---|---|---|
| subtle | 0.25 to 0.5 | r 2x, k 0.2 x core | 0.04 to 0.07 |
| medium | 0.3 to 0.7 | r 2.5x, k 0.4 x core | 0.06 to 0.10 |
| strong | 0.3 to 0.7 | r 3x, k 0.45 x core | 0.08 to 0.14 |

**Clarity** (a brief knob: clear, balanced, hazy; clear when open) sets where light and colour may spread:

| clarity | scene pool k (peak) | colour alpha | cover |
|---|---|---|---|
| clear | none | solid: alpha 1 except smoke, mist and fades | 5 to 20 % |
| balanced | 0.05 (0.2), r 1.5x the focal part | mist at 0.3 to 0.7 | 20 to 40 % |
| hazy | 0.12 (0.4), r 50 to 70 | translucent volumes | 40 to 80 % |

When the effect is itself the light source (a torch, a portal, an orb, an aura round a body), its cover runs
60 to 100 % at any clarity; then judge clarity by the dark ground round it and by solid colour pixels.

Cover is the share of the drawing's box (the colour alpha's bounding box, per frame, median over frames) with
light above 0.03; mean is the median light of those pixels. Measured on pixelfx: myriad-swords 15 % at 0.09,
lightning-call 6 % at 0.06, meteor-call 8 % at 0.07, hit-spark 5 % at 0.06; torch 97 % at 0.19 and portal
100 % at 0.12 are light sources. A sword-rain draft lit by one old table for every level read hazy at 70 % and 0.13.
Strength above medium goes into the pools round emitters, never the core or the pool along a stroke: past about
0.45 x core along a 1 px line the light sums to white and buries the line (tested on a thunder aura).

## The light measure

The runner prints the light measure every run (a draft writes none of the code below; it shows what the two
numbers mean). It is taken for the glow level and clarity (on `l` before any `lt::steps`), from each frame's colour `col`
and summed light `l`:

```
let nz = np::nonzero(&col.slice(s![.., .., 3]).mapv(|a| a > 0));            // rows, columns of the colour
let span = |v: &[usize]| (*v.iter().min().unwrap(), *v.iter().max().unwrap());
let ((y0, y1), (x0, x1)) = (span(&nz[0]), span(&nz[1]));
let bx = l.slice(s![y0..=y1, x0..=x1]);                                       // l is clipped to 0..1
let lit: Array1<f64> = bx.iter().copied().filter(|&v| v > 0.03).collect();
let (cover, mean) = (lit.len() as f64 / bx.len() as f64, np::mean(&lit));    // median of each over frames, printed
```

When mean falls outside the glow row or cover outside the clarity row, retune the pools once in the same pass.
These numbers are a floor: a draft inside both rows can still lose by eye (void_pop had cover 19 % and mean 0.118
and lost to pixelfx implosion), which is what the benchmark upgrade (`pixelfx.md`) finds.
