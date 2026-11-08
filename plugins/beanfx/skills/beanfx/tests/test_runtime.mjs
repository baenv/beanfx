// Checks runtime/beanfx.js without a browser: timing, end modes, states, loops, hit-stop, heading rows, pages and
// what draw() asks of the canvas.
//
//   node <skill>/tests/test_runtime.mjs      # exits 0 when every check passes
import { createFx, fromJson, rowOf } from "../runtime/beanfx.js";

const fails = [];
const ok = (cond, msg) => cond || fails.push(msg);
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

for (const f of fails) console.log("FAIL", f);
console.log((fails.length ? fails.length : "ok") + " runtime checks");
process.exit(fails.length ? 1 : 0);
