// beanfx.js: play an exported beanfx effect on a 2D canvas. No dependencies, one ES module.
//
//   import { loadFx, createFx } from "./beanfx.js";
//   const blast = await loadFx("fx/blast.json");            // the <name>.json export writes, sheets beside it
//   const fx = createFx(blast, { x: 160, y: 140, flip: false, state: "strike", onHit: (h) => shakeCamera(h) });
//   function tick(dt) {                                      // dt in seconds
//     fx.update(dt);
//     ctx.imageSmoothingEnabled = false;
//     fx.draw(ctx);                                          // colour, then the light added on top
//     if (fx.done) dropIt(fx);
//   }
// Hits (meta.beanfx.act.hits) freeze the effect, set fx.shake (px along the blow; translate the scene by it) and
// fx.flash (0 to 1; tint the struck target white by it), and call onHit with the hit: react, push, dir, weight and
// sound (the cue to play now).
//
// The JSON is the Aseprite array layout; everything beanfx adds sits in meta.beanfx (porting.md, route A).

const TAU = Math.PI * 2;

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("beanfx: cannot load " + src));
    img.src = src;
  });
}

// Fetches <name>.json and its sheets (every page when the sheet splits). light: false skips the light sheet and
// draws the baked <name>.png instead.
export async function loadFx(url, { light = true } = {}) {
  const res = await fetch(url);
  if (!res.ok) throw new Error("beanfx: cannot load " + url);
  const json = await res.json();
  const base = new URL(".", new URL(url, location.href)).href;
  const bfx = json.meta.beanfx;
  const pages = bfx.pages || [{ image: bfx.sheet || json.meta.image, color: bfx.color, light: bfx.light }];
  const split = light && pages.every((p) => p.color && p.light);
  const load = (key) => Promise.all(pages.map((p) => loadImage(base + p[key])));
  const images = split ? { color: await load("color"), light: await load("light") } : { sheet: await load("image") };
  return fromJson(json, images);
}

// The asset from parsed JSON and loaded images; loadFx calls it, tests and custom loaders may too.
export function fromJson(json, images = {}) {
  const bfx = json.meta.beanfx;
  const tags = {};
  for (const t of json.meta.frameTags || []) tags[t.name] = [t.from, t.to];
  const frames = json.frames.map((e) => ({ ...e.frame, page: e.page || 0, ms: e.duration }));
  return { meta: bfx, tags, frames, images };
}

// The heading row for a direction (radians, y down: 0 east, tau/4 south), as facing.py picks it.
export function rowOf(angle, rows) {
  return ((Math.round((angle / TAU) * rows) % rows) + rows) % rows;
}

export function createFx(asset, opts = {}) {
  const m = asset.meta;
  const fps = opts.fps || m.fps;
  const n = m.frames;
  // sheets written before facing.meta's row_rule carry a text `rows`; directions then gives the row count
  const rows = Number.isInteger(m.rows) ? m.rows : Number.isInteger(m.directions) ? m.directions : 1;
  const row = opts.row ?? (opts.heading != null && rows > 1 ? rowOf(opts.heading, rows) : 0);
  // a heading row's tag spans the whole row; its states are tagged "<row>/<state>"
  const rowTag = rows > 1 ? Object.keys(asset.tags).find((k) => !k.includes("/") && asset.tags[k][0] === row * n) : null;
  let range = [0, n - 1];
  if (opts.state) {
    const r = asset.tags[rowTag ? rowTag + "/" + opts.state : opts.state];
    if (!r) throw new Error("beanfx: no state " + opts.state);
    range = [r[0] - row * n, r[1] - row * n];
  }
  const [a, b] = range;
  const len = b - a + 1;
  const loop = opts.loop ?? (opts.state ? false : m.loop);
  const end = opts.end || (loop ? "loop" : opts.state ? "hold" : m.end || "remove");
  // frame times: each frame's own duration (a sheet locked to a game character's uneven frame times) when they
  // differ from 1 / fps, else even steps at fps; opts.fps forces even steps
  const ms = asset.frames.slice(row * n + a, row * n + b + 1).map((f) => f.ms);
  const even = opts.fps || ms.some((x) => !x) || ms.every((x) => Math.abs(x - 1000 / fps) < 1.01);
  const starts = [0];
  for (let i = 0; i < len; i++) starts.push(starts[i] + (even ? 1 / fps : ms[i] / 1000));
  const total = starts[len];
  const timeOf = (f) => Math.floor(f / len) * total + starts[f % len];  // start of played frame f
  function frameAt(t) {
    if (even) return Math.floor(t * fps + 1e-9);
    const lap = Math.floor((t + 1e-9) / total), r = t - lap * total;
    let i = 0;
    while (i < len - 1 && starts[i + 1] <= r + 1e-9) i++;
    return lap * len + i;
  }
  // hits as frames local to the range; only the ones inside it play
  const hits = ((m.act && m.act.hits) || []).filter((h) => h.frame >= a && h.frame <= b).map((h) => ({ ...h, at: h.frame - a }));

  const fx = {
    x: opts.x || 0,
    y: opts.y || 0,
    flip: !!opts.flip,
    scale: opts.scale || 1,
    lightGain: opts.lightGain ?? m.light_gain ?? 1,
    speed: opts.speed ?? 1,
    t: 0,               // effect time in s, freezes excluded
    frame: a,           // the sheet frame within the row (0 to frames - 1)
    done: false,
    frozen: 0,          // s of hit-stop left
    shake: [0, 0],      // px to throw the camera this frame, along the blow
    flash: 0,           // 0 to 1: how white to tint the target this frame (the hit's flash, then half for a frame)
    _abs: 0,            // frames played since the start
    _shakeAmp: 0,
    _shakeLeft: 0,
    _shakeTotal: 0,
    _dir: [1, 0],
    _flashLeft: 0,
    _flashTotal: 0,
  };

  // a hit starts its freeze, its shake along the blow (mirrored when flipped) and the target flash
  function strike(h) {
    fx.frozen = h.freeze || 0;
    fx._shakeAmp = h.shake || 0;
    fx._shakeTotal = fx._shakeLeft = h.shake_time ?? (h.freeze || 0) + 0.1;
    const a = ((h.dir || 0) * Math.PI) / 180;
    fx._dir = [Math.cos(a) * (fx.flip ? -1 : 1), Math.sin(a)];
    fx._flashTotal = fx._flashLeft = (h.flash ?? 1 / fps) + 1 / fps;
    fx.flash = 1;
  }

  fx.update = function (dt) {
    if (fx.done) return fx;
    dt *= fx.speed;
    if (fx._shakeLeft > 0) {
      fx._shakeLeft = Math.max(0, fx._shakeLeft - dt);
      const d = fx._shakeAmp * (fx._shakeLeft / fx._shakeTotal);
      const odd = Math.floor(fx._shakeLeft * 60) % 2 ? 1 : -1;
      fx.shake = [Math.round(d * fx._dir[0]) * odd, Math.round(d * fx._dir[1]) * odd];
    } else fx.shake = [0, 0];
    if (fx._flashLeft > 0) {
      fx._flashLeft = Math.max(0, fx._flashLeft - dt);
      fx.flash = fx._flashLeft <= 0 ? 0 : fx._flashLeft < 1 / fps ? 0.5 : 1;
    } else fx.flash = 0;
    if (fx.frozen > 0) {
      const used = Math.min(fx.frozen, dt);
      fx.frozen -= used;
      dt -= used;
      if (dt <= 0) return fx;
    }
    const prev = fx._abs;
    let abs = frameAt(fx.t + dt);
    // the first hit crossed this step stops time on its frame
    for (let f = prev + 1; f <= abs; f++) {
      const local = loop ? f % len : f;
      const h = hits.find((x) => x.at === local);
      if (h) {
        abs = f;
        fx.t = timeOf(f);
        strike(h);
        if (opts.onHit) opts.onHit(h, fx);
        dt = 0;
        break;
      }
    }
    if (dt > 0) fx.t += dt;
    fx._abs = abs;
    if (loop) fx.frame = a + (abs % len);
    else if (abs < len) fx.frame = a + abs;
    else if (end === "hold") fx.frame = b;
    else {
      fx.frame = b;
      fx.done = true;
      if (opts.onEnd) opts.onEnd(fx);
    }
    return fx;
  };
  // the first hit can sit on the range's first frame
  const h0 = hits.find((x) => x.at === 0);
  if (h0) {
    strike(h0);
    if (opts.onHit) queueMicrotask(() => opts.onHit(h0, fx));
  }

  // Draws the current frame with its pivot on (x, y). Flipped, it mirrors about the pivot (mirror_pivot in the
  // JSON is the same point on the flipped cell).
  fx.draw = function (ctx) {
    if (fx.done) return;
    const r = asset.frames[row * n + fx.frame];
    const [px, py] = m.pivot;
    const s = fx.scale;
    ctx.save();
    ctx.translate(fx.x, fx.y);
    ctx.scale(fx.flip ? -s : s, s);
    const blit = (img) => ctx.drawImage(img, r.x, r.y, r.w, r.h, -px, -py, r.w, r.h);
    const im = asset.images;
    if (im.color) {
      blit(im.color[r.page]);
      if (fx.lightGain > 0) {
        ctx.globalCompositeOperation = "lighter";
        ctx.globalAlpha = Math.min(1, fx.lightGain);
        blit(im.light[r.page]);
      }
    } else if (im.sheet) blit(im.sheet[r.page]);
    ctx.restore();
  };

  return fx;
}
