#!/usr/bin/env node
// Split a pixelfx effect into its colour and light layers, for reuse in a beanfx draft (kit/pfx.py load).
// pixelfx 0.3 dropped its own tools/layers.mjs; this one keeps the same output on top of its renderFrames.
//
//   node <skill>/tools/layers.mjs <id> --out <dir> [--pixelfx DIR] [--opts JSON] [--seed N] [--fps N]
//
// Writes <name>_color.png (RGBA, the effect alone on transparency) and <name>_light.png (RGB additive light),
// frames left to right, and <name>.json {id, w, h, fps, frames, loop, pivot}. The pixelfx dir is --pixelfx,
// else $PIXELFX, else ./pixelfx.

import { resolve, join } from "node:path";
import { pathToFileURL } from "node:url";

const args = process.argv.slice(2), flags = {}, pos = [];
for (let i = 0; i < args.length; i++) args[i].startsWith("--") ? (flags[args[i].slice(2)] = args[++i]) : pos.push(args[i]);
const id = pos[0];
if (!id || !flags.out) {
  console.error("usage: layers.mjs <id> --out <dir> [--pixelfx DIR] [--opts JSON] [--seed N] [--fps N]");
  process.exit(2);
}
const dir = resolve(flags.pixelfx ?? process.env.PIXELFX ?? "pixelfx");
const lib = await import(pathToFileURL(join(dir, "tools", "lib", "fxlib.mjs")).href);
const { encodePNG } = await import(pathToFileURL(join(dir, "tools", "lib", "png.mjs")).href);

const fx = await lib.loadEffect(id);
const opts = { bg: "none", actor: false };
if (flags.opts) opts.options = JSON.parse(flags.opts);
if (flags.seed !== undefined) opts.seed = +flags.seed;
if (flags.fps !== undefined) opts.fps = +flags.fps;
const r = lib.renderFrames(fx, opts);
if (!r.frames[0].raw || !r.frames[0].light) {
  console.error("layers: this pixelfx renderFrames gives no raw colour or light per frame");
  process.exit(1);
}

// pixelfx packs colour as ABGR and light as xBGR in Uint32, so the little-endian bytes read r, g, b, a
const W = r.w * r.n, color = new Uint8Array(W * r.h * 4), light = new Uint8Array(W * r.h * 4);
r.frames.forEach((f, k) => {
  const c = new Uint8Array(f.raw.buffer, f.raw.byteOffset, f.raw.byteLength);
  const l = new Uint8Array(f.light.buffer, f.light.byteOffset, f.light.byteLength);
  for (let y = 0; y < r.h; y++)
    for (let x = 0; x < r.w; x++) {
      const s = (y * r.w + x) * 4, d = (y * W + k * r.w + x) * 4;
      color[d] = c[s]; color[d + 1] = c[s + 1]; color[d + 2] = c[s + 2]; color[d + 3] = c[s + 3];
      light[d] = l[s]; light[d + 1] = l[s + 1]; light[d + 2] = l[s + 2]; light[d + 3] = 255;
    }
});
const name = id.split("/").pop(), out = resolve(flags.out);
lib.save(join(out, `${name}_color.png`), encodePNG(W, r.h, color));
lib.save(join(out, `${name}_light.png`), encodePNG(W, r.h, light));
const [ox, oy] = fx.meta.origin;
const meta = { id, w: r.w, h: r.h, fps: r.fps, frames: r.n, loop: !!fx.meta.loop, pivot: [ox + r.margin, oy + r.margin] };
lib.save(join(out, `${name}.json`), JSON.stringify(meta, null, 1) + "\n");
console.log(`${id}: ${r.n} frames ${r.w}x${r.h} at ${r.fps} fps to ${out}`);
