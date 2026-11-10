// Checks runtime/beanfx.js without a browser: timing, end modes, states, loops, hit-stop, heading rows, pages and
// what draw() asks of the canvas.
//
//   node <skill>/tests/test_runtime.mjs      # exits 0 when every check passes
import { createFx, fromJson, rowOf } from "../runtime/beanfx.js";

const fails = [];
// BEANFX_CHECKS=1 (set by conftest.py) prints one line per check so pytest reports each one apart
const ok = (cond, msg) => {
  if (process.env.BEANFX_CHECKS) console.log(`CHECK ${cond ? "ok" : "fail"} ${String(msg).replace(/\s+/g, " ")}`);
  return cond || fails.push(msg);
};
const near = (a, b) => Math.abs(a - b) < 1e-6;

// the JSON export.write makes: frames row-major in a grid, tags, meta.beanfx
function sheet({ n = 10, rows = 1, fps = 10, loop = false, end = "remove", states = {}, hits = [], perPage = 0 }) {
  const w = 8, h = 6, cols = 4, names8 = ["east", "south-east", "south", "south-west", "west", "north-west", "north", "north-east"];
  const frames = [], tags = [];
  for (let i = 0; i < n * rows; i++) {
    const page = perPage ? Math.floor(i / perPage) : 0, j = perPage ? i % perPage : i;
    frames.push({ filename: "fx " + i, frame: { x: (j % cols) * w, y: Math.floor(j / cols) * h, w, h }, duration: 100, ...(perPage ? { page } : {}) });
  }
  for (let r = 0; r < rows; r++) {
    if (rows > 1) tags.push({ name: names8[r], from: r * n, to: r * n + n - 1 });
    for (const [s, [a, b]] of Object.entries(states)) tags.push({ name: rows > 1 ? names8[r] + "/" + s : s, from: r * n + a, to: r * n + b });
  }
  const bfx = { name: "fx", fps, loop, end, frames: n, rows, frameSize: [w, h], pivot: [3, 5], columns: cols, light_gain: 1 };
  if (hits.length) bfx.act = { windup: 0, hits };
  return { frames, meta: { image: "fx.png", frameTags: tags, beanfx: bfx } };
}

const run = (fx, s, step = 0.05) => { for (let t = 0; t < s - 1e-9; t += step) fx.update(Math.min(step, s - t)); return fx; };

// one-shot: plays at fps, removes itself after the last frame
let fx = run(createFx(fromJson(sheet({}))), 0.35);
ok(fx.frame === 3 && !fx.done, "frame 3 at 0.35 s: " + fx.frame);
let ended = 0;
fx = run(createFx(fromJson(sheet({})), { onEnd: () => ended++ }), 1.2);
ok(fx.done && ended === 1, "remove: done once after the last frame");
fx.update(0.5);
ok(ended === 1, "onEnd fires once");

// hold keeps the last frame; a state plays its own range and holds by default
fx = run(createFx(fromJson(sheet({ end: "hold" }))), 3);
ok(fx.frame === 9 && !fx.done, "hold keeps frame 9");
const st = { charge: [0, 3], strike: [4, 6], fade: [7, 9] };
fx = createFx(fromJson(sheet({ states: st })), { state: "strike" });
ok(fx.frame === 4, "state starts on its first frame");
run(fx, 1);
ok(fx.frame === 6 && !fx.done, "state holds its last frame: " + fx.frame);
let threw = false;
try { createFx(fromJson(sheet({ states: st })), { state: "nope" }); } catch { threw = true; }
ok(threw, "an unknown state throws");

// loop wraps; a looping state wraps inside its range
fx = run(createFx(fromJson(sheet({ loop: true }))), 1.25);
ok(fx.frame === 2 && !fx.done, "loop wraps to frame 2: " + fx.frame);
fx = run(createFx(fromJson(sheet({ states: st })), { state: "charge", loop: true }), 0.5);
ok(fx.frame === 1, "looping state wraps in its range: " + fx.frame);

// hit-stop: time stops on the hit frame for `freeze` s, the camera shakes, onHit fires once
const hit = { frame: 5, t: 0.5, freeze: 0.2, shake: 4, push: 2, react: "flinch" };
let hitsSeen = [];
fx = createFx(fromJson(sheet({ hits: [hit] })), { onHit: (h) => hitsSeen.push(h.frame) });
run(fx, 0.55);
ok(fx.frame === 5 && fx.frozen > 0, "stops on the hit frame: " + fx.frame);
ok(hitsSeen.length === 1 && hitsSeen[0] === 5, "onHit once with the hit");
fx.update(0.05);
ok(fx.shake[0] !== 0, "shakes during the freeze");
run(fx, 0.1);
ok(fx.frame === 5, "still on the hit frame inside the freeze");
run(fx, 0.2);
ok(fx.frame > 5, "moves on after the freeze: " + fx.frame);
run(fx, 0.3);
ok(fx.shake[0] === 0 && fx.shake[1] === 0, "shake settles");
ok(hitsSeen.length === 1, "the hit does not fire twice");
fx = createFx(fromJson(sheet({ hits: [hit] })));
fx.update(2);
ok(fx.frame === 5 && !fx.done, "a long step stops on the hit instead of skipping it: " + fx.frame);
fx = run(createFx(fromJson(sheet({ hits: [hit], states: st })), { state: "charge" }), 1);
ok(fx.frozen === 0 && fx.frame === 3, "a hit outside the state does not play");
fx = run(createFx(fromJson(sheet({ hits: [hit] })), { speed: 2 }), 0.25);
ok(fx.frame === 5, "speed 2 reaches the hit in half the time: " + fx.frame);

// the shake runs along the blow (mirrored when flipped) for shake_time; the target flash is 1, then 0.5, then 0
const down = { frame: 2, t: 0.2, freeze: 0.1, shake: 4, dir: 90, shake_time: 0.3, flash: 0.1, sound: "hit_heavy" };
let cue = null;
fx = createFx(fromJson(sheet({ hits: [down] })), { onHit: (h) => (cue = h.sound) });
run(fx, 0.25, 0.01);
ok(cue === "hit_heavy", "onHit carries the sound cue");
ok(fx.shake[0] === 0 && fx.shake[1] !== 0, "a 90 degree blow shakes up and down: " + fx.shake);
const side = { ...down, dir: 0 };
const sx = (flip) => { const f = createFx(fromJson(sheet({ hits: [side] })), { flip }); run(f, 0.25, 0.01); return f.shake[0]; };
ok(sx(false) !== 0 && Math.sign(sx(false)) === -Math.sign(sx(true)), "flip mirrors the shake: " + sx(false) + " " + sx(true));
fx = createFx(fromJson(sheet({ hits: [down] })));
run(fx, 0.21, 0.01);
ok(fx.flash === 1, "flash on contact: " + fx.flash);
run(fx, 0.1, 0.01);
ok(fx.flash === 0.5, "half flash for the last frame: " + fx.flash);
run(fx, 0.1, 0.01);
ok(fx.flash === 0, "flash ends");
run(fx, 0.2, 0.01);
ok(fx.shake[0] === 0 && fx.shake[1] === 0, "shake ends after shake_time");

// heading rows: row k faces tau * k / n, y down
ok(rowOf(0, 8) === 0 && rowOf(Math.PI / 2, 8) === 2 && rowOf(Math.PI, 8) === 4 && rowOf(-Math.PI / 2, 8) === 6, "rowOf");
ok(rowOf(2 * Math.PI - 0.1, 8) === 0, "rowOf wraps near tau");
const multi = fromJson(sheet({ rows: 8, states: st }));
fx = createFx(multi, { heading: Math.PI / 2, state: "strike" });
ok(fx.frame === 4, "row state starts on the row's own frame 4: " + fx.frame);

// draw: pivot on (x, y), flipped about it, colour then additive light at light_gain; the baked sheet otherwise
function mockCtx() {
  const calls = [];
  const ctx = { globalCompositeOperation: "source-over", globalAlpha: 1, calls,
    save: () => calls.push(["save"]), restore: () => calls.push(["restore"]),
    translate: (x, y) => calls.push(["translate", x, y]), scale: (x, y) => calls.push(["scale", x, y]),
    drawImage: (img, ...a) => calls.push(["draw", img, ctx.globalCompositeOperation, ctx.globalAlpha, ...a]) };
  return ctx;
}
const split = fromJson(sheet({}), { color: ["C"], light: ["L"] });
fx = createFx(split, { x: 100, y: 50, flip: true, lightGain: 0.5 });
fx.update(0.25);
let ctx = mockCtx();
fx.draw(ctx);
const draws = ctx.calls.filter((c) => c[0] === "draw");
ok(ctx.calls.some((c) => c[0] === "translate" && c[1] === 100 && c[2] === 50), "translates to the pivot point");
ok(ctx.calls.some((c) => c[0] === "scale" && c[1] === -1 && c[2] === 1), "flip mirrors about the pivot");
ok(draws.length === 2 && draws[0][1] === "C" && draws[1][1] === "L", "colour then light");
ok(draws[1][2] === "lighter" && near(draws[1][3], 0.5), "light is additive at light_gain");
ok(draws[0][4] === 16 && draws[0][5] === 0 && draws[0][8] === -3 && draws[0][9] === -5, "frame 2 rect, pivot offset: " + draws[0].slice(4));
fx = createFx(split, { lightGain: 0 });
ctx = mockCtx(); fx.draw(ctx);
ok(ctx.calls.filter((c) => c[0] === "draw").length === 1, "light gain 0 skips the light");
fx = createFx(fromJson(sheet({}), { sheet: ["S"] }));
ctx = mockCtx(); fx.draw(ctx);
ok(ctx.calls.filter((c) => c[0] === "draw").map((c) => c[1]).join() === "S", "no light sheet: the baked sheet");
fx = run(createFx(fromJson(sheet({}), { sheet: ["S"] })), 2);
ctx = mockCtx(); fx.draw(ctx);
ok(ctx.calls.length === 0, "a removed effect draws nothing");

// pages: each frame comes from the page its entry names
const paged = fromJson(sheet({ perPage: 4 }), { sheet: ["P0", "P1", "P2"] });
fx = run(createFx(paged), 0.65);
ctx = mockCtx(); fx.draw(ctx);
const d = ctx.calls.find((c) => c[0] === "draw");
ok(d[1] === "P1" && d[4] === 16, "frame 6 from page 1, cell 2: " + d.slice(1, 6));

// uneven frame times (a sheet locked to a game character's ms): frames hold for their own duration
const uneven = sheet({ n: 4, fps: 10 });
uneven.frames.forEach((f, i) => (f.duration = [50, 200, 50, 100][i]));
uneven.meta.beanfx.act = { windup: 0, hits: [{ frame: 2, freeze: 0, shake: 0 }] };
let hitT = null;
fx = createFx(fromJson(uneven, {}), { onHit: (h, f) => (hitT = Math.round(f.t * 1000) / 1000) });
run(fx, 0.06, 0.01); ok(fx.frame === 1, "50 ms frame 0, then frame 1 at 0.06 s: " + fx.frame);
run(fx, 0.18, 0.01); ok(fx.frame === 1, "frame 1 holds 200 ms (0.24 s): " + fx.frame);
run(fx, 0.03, 0.01); ok(fx.frame === 2 && hitT === 0.25, "hit frame 2 lands at 0.25 s: " + fx.frame + " at " + hitT);
run(fx, 0.2, 0.01); ok(fx.done, "one-shot ends after 400 ms of frames");
fx = createFx(fromJson(uneven, {}), { fps: 10 });
run(fx, 0.15, 0.01); ok(fx.frame === 1, "opts.fps forces even steps: " + fx.frame);

for (const f of fails) console.log("FAIL", f);
console.log((fails.length ? fails.length : "ok") + " runtime checks");
process.exit(fails.length ? 1 : 0);
