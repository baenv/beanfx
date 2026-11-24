//! mo: motion in closed form and the particles built on it.
//! Every call is a pure function of the time, so a draw stays a pure function of (frame, seed): no state, no steps.
//! Times are in seconds (`f as f64 / fps`), positions in world px, y down, gravity in px/s^2.

use crate::dr::{hash01, vnoise, Canvas, Rgb, P};

/// Where a particle is at time t, and its velocity, flung from p0 at v0 under gravity g (px/s^2, y down) with
/// exponential drag k (1/s; 0 is plain ballistic). With drag the speed eases to the terminal g / k, so sparks and
/// chunks slow down the way air slows them, instead of flying on at launch speed.
pub fn fly(p0: P, v0: P, g: f64, drag: f64, t: f64) -> (P, P) {
    if t <= 0.0 {
        return (p0, v0);
    }
    if drag <= 1e-9 {
        return ([p0[0] + v0[0] * t, p0[1] + v0[1] * t + 0.5 * g * t * t], [v0[0], v0[1] + g * t]);
    }
    let e = (-drag * t).exp();
    let term = g / drag; // terminal fall speed
    let x = p0[0] + v0[0] * (1.0 - e) / drag;
    let y = p0[1] + term * t + (v0[1] - term) * (1.0 - e) / drag;
    ([x, y], [v0[0] * e, term + (v0[1] - term) * e])
}

/// `fly_ground` options: the floor y, the share of the vertical speed kept on a bounce, the share of the
/// horizontal speed kept, and the vertical speed (px/s) under which it stops bouncing and rests.
#[derive(Clone, Copy, Debug)]
pub struct Ground {
    pub y: f64,
    pub bounce: f64,
    pub slide: f64,
    pub rest: f64,
}

impl Default for Ground {
    fn default() -> Self {
        Ground { y: 0.0, bounce: 0.45, slide: 0.7, rest: 12.0 }
    }
}

/// `fly` that bounces on a floor (keeping 0.45 of the vertical speed by default) and comes to rest on it.
/// Returns position, velocity and the number of landings so far (0 while still in the first flight).
pub fn fly_ground(p0: P, v0: P, g: f64, drag: f64, t: f64, gr: Ground) -> (P, P, usize) {
    let (mut p, mut v, mut left, mut hits) = (p0, v0, t.max(0.0), 0usize);
    for _ in 0..16 {
        let (q, w) = fly(p, v, g, drag, left);
        if q[1] < gr.y {
            return (q, w, hits);
        }
        // the first time it reaches the floor: sample at 1/240 s, then halve the step 24 times
        let (mut lo, mut hi) = (0.0, left);
        let mut s = 1.0 / 240.0;
        while s < left {
            if fly(p, v, g, drag, s).0[1] >= gr.y {
                hi = s;
                break;
            }
            lo = s;
            s += 1.0 / 240.0;
        }
        for _ in 0..24 {
            let m = 0.5 * (lo + hi);
            if fly(p, v, g, drag, m).0[1] >= gr.y { hi = m } else { lo = m }
        }
        let (q, w) = fly(p, v, g, drag, hi);
        hits += 1;
        left -= hi;
        p = [q[0], gr.y];
        v = [w[0] * gr.slide, -w[1] * gr.bounce];
        if v[1].abs() < gr.rest {
            return ([p[0] + v[0] * (1.0 - (-3.0 * left).exp()) / 3.0, gr.y], [0.0, 0.0], hits);
        }
    }
    (p, [0.0, 0.0], hits)
}

/// Particle `i` of an endless stream (`cycle`): its age 0..1 at time t when one is born every `every` s and
/// each lives `life` s, with a seeded jitter on its birth. None while particle i is not alive. Loops seamlessly
/// when the loop length is a whole multiple of `every`.
pub fn cycle(seed: u64, i: u64, t: f64, every: f64, life: f64) -> Option<f64> {
    let born = i as f64 * every + 0.6 * every * hash01(seed, i);
    let a = (t - born) / life;
    (0.0..1.0).contains(&a).then_some(a)
}

/// A spark: a two-tone streak whose length follows its speed (`stretch` px per 100 px/s, at least 1 px, at most
/// `max`), the hot head on the point and the cool tail behind, with a small glow on the head. A slow spark is a
/// dot; a fast one a dash, so speed reads without a smear.
pub fn spark(cv: &mut Canvas, p: P, v: P, stretch: f64, max: f64, hot: Rgb, tail: Rgb, a: f64, glow: f64) {
    let sp = (v[0] * v[0] + v[1] * v[1]).sqrt();
    let len = (sp / 100.0 * stretch).clamp(1.0, max.max(1.0));
    let (dx, dy) = if sp > 1e-6 { (v[0] / sp, v[1] / sp) } else { (0.0, 0.0) };
    let back = [p[0] - dx * len, p[1] - dy * len];
    let mid = [p[0] - dx * len * 0.45, p[1] - dy * len * 0.45];
    cv.line(back, mid, tail, a);
    cv.line(mid, p, hot, a);
    cv.put(p[0], p[1], hot, a);
    if glow > 0.0 {
        cv.glow(p[0], p[1], 3.0, glow);
    }
}

/// A flame puff at age 0..1 on a fire ramp (dark to white-hot): a dark rim, a lit core offset up and left
/// toward the light, a tongue on top. It walks down the ramp as it ages, so it cools while it rises.
pub fn flame(cv: &mut Canvas, x: f64, y: f64, r: f64, age: f64, ramp: &[Rgb], a: f64, glow: f64) {
    if ramp.is_empty() || r <= 0.0 {
        return;
    }
    let n = ramp.len() as f64 - 1.0;
    let tone = |k: f64| ramp[(k.clamp(0.0, n)).round() as usize];
    let age = age.clamp(0.0, 1.0);
    let heat = n * (1.0 - age * age); // white-hot for the first part, then cooling faster to the darkest tone
    let r = r * (1.0 - 0.45 * age);
    cv.ellipse(x, y, r, r, tone(heat - 2.0), a);
    cv.ellipse(x - 0.2 * r, y - 0.25 * r, 0.62 * r, 0.62 * r, tone(heat - 1.0), a);
    cv.ellipse(x - 0.25 * r, y - 0.35 * r, 0.3 * r, 0.3 * r, tone(heat), a);
    cv.ellipse(x, y - 0.95 * r, 0.32 * r, 0.55 * r, tone(heat - 1.0), a); // the tongue
    if glow > 0.0 {
        cv.glow(x, y, 2.2 * r, glow * (1.0 - age));
    }
}

/// A smoke puff at age 0..1 on a smoke ramp (dark to light): a body disc that swells, a denser low core, and a
/// lit cap on the top left while it is young; it walks down the ramp and thins out as it ages.
pub fn smoke(cv: &mut Canvas, x: f64, y: f64, r: f64, age: f64, ramp: &[Rgb], a: f64) {
    if ramp.is_empty() || r <= 0.0 {
        return;
    }
    let age = age.clamp(0.0, 1.0);
    let n = ramp.len() as f64 - 1.0;
    let tone = |k: f64| ramp[(k.clamp(0.0, n)).round() as usize];
    let r = r * (0.6 + 0.8 * age);
    let k = a * (1.0 - age * age);
    let top = n * (1.0 - 0.6 * age);
    cv.ellipse(x, y, r, r, tone(top - 1.0), 0.75 * k);
    cv.ellipse(x + 0.1 * r, y + 0.25 * r, 0.6 * r, 0.5 * r, tone(top - 2.0), 0.85 * k);
    if age < 0.5 {
        cv.ellipse(x - 0.25 * r, y - 0.3 * r, 0.45 * r, 0.4 * r, tone(top), k * (1.0 - 2.0 * age));
    }
}

/// `burst` options: puff count, launch speed range (px/s), gravity (negative rises), drag, the flame's share of a
/// puff's life, puff radius and the light on the flames.
#[derive(Clone, Debug)]
pub struct Burst {
    pub n: u64,
    pub speed: (f64, f64),
    pub g: f64,
    pub drag: f64,
    pub life: (f64, f64),
    pub flame_share: f64,
    pub r: (f64, f64),
    pub glow: f64,
}

impl Default for Burst {
    fn default() -> Self {
        Burst { n: 22, speed: (12.0, 70.0), g: -40.0, drag: 4.0, life: (0.7, 1.4), flame_share: 0.45, r: (3.5, 6.5), glow: 0.25 }
    }
}

/// A fire burst that cools into smoke: `o.n` puffs flung from `at` at time 0 (`t` in s since the burst), each a
/// flame for the first `flame_share` of its life and a smoke puff after, rising and slowing with drag. Smoke
/// draws first, so the flames sit on top of it.
pub fn burst(cv: &mut Canvas, seed: u64, at: P, t: f64, fire: &[Rgb], smoke_ramp: &[Rgb], o: &Burst) {
    if t < 0.0 {
        return;
    }
    let puffs: Vec<(P, f64, f64)> = (0..o.n).map(|i| {
        let h = |k: u64| hash01(seed, i * 8 + k);
        let ang = std::f64::consts::TAU * (i as f64 + 0.7 * h(0)) / o.n as f64;
        let s = o.speed.0 + (o.speed.1 - o.speed.0) * h(1);
        let life = o.life.0 + (o.life.1 - o.life.0) * h(2);
        let r = o.r.0 + (o.r.1 - o.r.0) * h(3);
        let (p, _) = fly(at, [s * ang.cos(), s * ang.sin() * 0.8], o.g, o.drag, t);
        (p, t / life, r)
    }).collect();
    for &(p, age, r) in &puffs {
        if age >= o.flame_share && age < 1.0 {
            smoke(cv, p[0], p[1], r * 1.2, (age - o.flame_share) / (1.0 - o.flame_share), smoke_ramp, 0.9);
        }
    }
    for &(p, age, r) in &puffs {
        if age < o.flame_share {
            flame(cv, p[0], p[1], r, age / o.flame_share, fire, 1.0, o.glow);
        }
    }
}

/// The time of the first landing of `fly_ground` (None when it has not landed by `t_max`).
pub fn landed_at(p0: P, v0: P, g: f64, drag: f64, gr: Ground, t_max: f64) -> Option<f64> {
    if fly_ground(p0, v0, g, drag, t_max, gr).2 == 0 {
        return None;
    }
    let (mut lo, mut hi) = (0.0, t_max);
    for _ in 0..40 {
        let m = 0.5 * (lo + hi);
        if fly_ground(p0, v0, g, drag, m, gr).2 == 0 { lo = m } else { hi = m }
    }
    Some(hi)
}

/// A tumbling chunk (rock, wood, debris): a diamond of half-size `r` turned by `angle`, lit on the top left and
/// dark on the bottom right, with a dark rim. `shades` = (rim, dark, mid, lit).
pub fn chunk(cv: &mut Canvas, p: P, r: f64, angle: f64, shades: [Rgb; 4], a: f64) {
    if r <= 0.0 {
        return;
    }
    let (c, s) = (angle.cos(), angle.sin());
    let corner = |k: usize| {
        let (u, v) = [(r, 0.0), (0.0, r * 0.8), (-r, 0.0), (0.0, -r * 0.8)][k];
        [p[0] + u * c - v * s, p[1] + u * s + v * c]
    };
    let pts: Vec<P> = (0..4).map(corner).collect();
    cv.poly(&pts, shades[0], a);
    let inner: Vec<P> = pts.iter().map(|q| [p[0] + (q[0] - p[0]) * 0.7, p[1] + (q[1] - p[1]) * 0.7]).collect();
    cv.poly(&inner, shades[2], a);
    // each half of the inner diamond shaded by which way it faces: toward the top left lit, away dark
    for k in 0..4 {
        let (q0, q1) = (inner[k], inner[(k + 1) % 4]);
        let n = [(q0[0] + q1[0]) * 0.5 - p[0], (q0[1] + q1[1]) * 0.5 - p[1]];
        let facing = -(n[0] + n[1]); // dot with the light from the top left
        if facing.abs() > 0.2 * r {
            cv.poly(&[p, q0, q1], if facing > 0.0 { shades[3] } else { shades[1] }, a);
        }
    }
}

/// `chunks` options: count, launch speed range (px/s), gravity, drag, size range, spin (turns per second at full
/// speed) and the floor. Each chunk stops turning when it rests and kicks up dust where it first lands.
#[derive(Clone, Debug)]
pub struct Chunks {
    pub n: u64,
    pub speed: (f64, f64),
    pub g: f64,
    pub drag: f64,
    pub r: (f64, f64),
    pub spin: f64,
    pub ground: Ground,
    /// Seconds a landing's dust lives (0: no dust).
    pub dust: f64,
}

impl Default for Chunks {
    fn default() -> Self {
        Chunks { n: 8, speed: (60.0, 140.0), g: 360.0, drag: 1.0, r: (1.5, 3.0), spin: 2.0, ground: Ground::default(), dust: 0.5 }
    }
}

/// Debris flung up from `at` at time 0 over the upper half circle: tumbling `chunk`s that bounce and rest on
/// `o.ground`, each with a `dust` puff where it first lands. Dust draws first, under the chunks.
pub fn chunks(cv: &mut Canvas, seed: u64, at: P, t: f64, shades: [Rgb; 4], dust_ramp: &[Rgb], o: &Chunks) {
    if t < 0.0 {
        return;
    }
    let mut drawn = vec![];
    for i in 0..o.n {
        let h = |k: u64| hash01(seed, i * 8 + k);
        let ang = -std::f64::consts::PI * (0.12 + 0.76 * (i as f64 + h(0)) / o.n as f64);
        let sp = o.speed.0 + (o.speed.1 - o.speed.0) * h(1);
        let v0 = [sp * ang.cos(), sp * ang.sin()];
        let r = o.r.0 + (o.r.1 - o.r.0) * h(2);
        let (p, v, hits) = fly_ground(at, v0, o.g, o.drag, t, o.ground);
        if o.dust > 0.0 && hits > 0 {
            if let Some(tl) = landed_at(at, v0, o.g, o.drag, o.ground, t) {
                let landing = fly_ground(at, v0, o.g, o.drag, tl, o.ground).0;
                dust(cv, seed + i, [landing[0], o.ground.y], (t - tl) / o.dust, r * 2.0, dust_ramp);
            }
        }
        // the turn follows the distance flown, so a resting chunk keeps its last angle
        let still = v == [0.0, 0.0];
        let turn = if still { landed_at(at, v0, o.g, o.drag, o.ground, t).unwrap_or(t) } else { t };
        let spin = o.spin * std::f64::consts::TAU * (if h(3) < 0.5 { -1.0 } else { 1.0 }) * (0.6 + 0.8 * h(4));
        drawn.push((p, r, spin * turn + h(5) * 6.0));
    }
    for (p, r, angle) in drawn {
        chunk(cv, p, r, angle, shades, 1.0);
    }
}

/// A landing's dust at age 0..1: three small puffs that roll out sideways along the floor and rise a little,
/// on a dust ramp (dark to light), gone by age 1.
pub fn dust(cv: &mut Canvas, seed: u64, at: P, age: f64, size: f64, ramp: &[Rgb]) {
    if !(0.0..1.0).contains(&age) || ramp.is_empty() {
        return;
    }
    let out = 1.0 - (1.0 - age) * (1.0 - age);
    for k in 0..3u64 {
        let side = [-1.0, 1.0, 0.0][k as usize];
        let x = at[0] + side * size * (0.4 + 1.6 * out) * (0.8 + 0.4 * hash01(seed, k));
        let y = at[1] - size * (0.2 + 0.8 * out) * if side == 0.0 { 1.4 } else { 0.6 };
        smoke(cv, x, y, size * (0.5 + 0.25 * hash01(seed, k + 7)), age, ramp, 0.8);
    }
}

/// `brands` options: burning chunks flung from the blast, a flame trail while they fly, and a small fire where
/// each lands that burns `burn` s and dies to embers.
#[derive(Clone, Debug)]
pub struct Brands {
    pub n: u64,
    pub speed: (f64, f64),
    pub g: f64,
    pub drag: f64,
    pub ground: Ground,
    pub burn: f64,
    pub glow: f64,
}

impl Default for Brands {
    fn default() -> Self {
        Brands { n: 4, speed: (70.0, 130.0), g: 300.0, drag: 0.8, ground: Ground { bounce: 0.2, ..Ground::default() }, burn: 0.9, glow: 0.2 }
    }
}

/// Burning brands: each arcs out of `at` trailing flame puffs, lands, and leaves a small fire on the floor that
/// flares, burns down and dies to a few embers. Pair with `scorch` under the blast for a one-shot that leaves a mark.
pub fn brands(cv: &mut Canvas, seed: u64, at: P, t: f64, fire: &[Rgb], o: &Brands) {
    if t < 0.0 || fire.is_empty() {
        return;
    }
    for i in 0..o.n {
        let h = |k: u64| hash01(seed, i * 8 + k);
        let ang = -std::f64::consts::PI * (0.2 + 0.6 * (i as f64 + h(0)) / o.n.max(1) as f64);
        let sp = o.speed.0 + (o.speed.1 - o.speed.0) * h(1);
        let v0 = [sp * ang.cos(), sp * ang.sin()];
        let land = landed_at(at, v0, o.g, o.drag, o.ground, t);
        match land {
            None => {
                // in flight: the brand and a trail of puffs at earlier times, younger ones hotter
                for k in (0..4).rev() {
                    let tk = t - k as f64 * 0.035;
                    if tk < 0.0 {
                        continue;
                    }
                    let (q, _) = fly(at, v0, o.g, o.drag, tk);
                    flame(cv, q[0], q[1], 2.2 - 0.35 * k as f64, 0.15 + 0.2 * k as f64, fire, 1.0, if k == 0 { o.glow } else { 0.0 });
                }
            }
            Some(tl) => {
                let x = fly(at, v0, o.g, o.drag, tl).0[0];
                let age = (t - tl) / o.burn;
                if age < 1.0 {
                    // a small fire: two tongues that flicker on a seeded beat, shrinking as it burns down
                    for k in 0..2u64 {
                        let fl = 0.5 + 0.5 * (t * 23.0 + 6.0 * hash01(seed + i, k)).sin();
                        let r = (2.6 - 0.8 * k as f64) * (1.0 - 0.7 * age) * (0.85 + 0.15 * fl);
                        flame(cv, x + (k as f64 - 0.5) * 2.0, o.ground.y - r * 0.9, r, 0.25 + 0.6 * age, fire, 1.0, o.glow * (1.0 - age));
                    }
                } else if age < 1.6 {
                    // embers: a few dark-red specks that go out one by one
                    for k in 0..3u64 {
                        if (age - 1.0) / 0.6 < hash01(seed + i, k + 20) {
                            cv.put(x - 2.0 + 2.0 * k as f64, o.ground.y - 1.0, fire[1.min(fire.len() - 1)], 1.0);
                        }
                    }
                }
            }
        }
    }
}

/// A scorch mark on the floor at age 0..1 since the blast, an ellipse `rx` x `ry` round `at`: white-hot at first,
/// cooling down the fire ramp (bright to dark) and ending as soot that stays (age >= 1 holds the soot). The edge
/// breaks up in seeded noise, so it never reads as a stamped oval.
pub fn scorch(cv: &mut Canvas, seed: u64, at: P, rx: f64, ry: f64, age: f64, fire: &[Rgb], soot: Rgb) {
    if age < 0.0 || rx <= 0.0 || ry <= 0.0 {
        return;
    }
    let age = age.min(1.0);
    let n = fire.len();
    let x0 = (at[0] - rx - 1.0).floor() as i64;
    let x1 = (at[0] + rx + 1.0).ceil() as i64;
    let y0 = (at[1] - ry - 1.0).floor() as i64;
    let y1 = (at[1] + ry + 1.0).ceil() as i64;
    for yi in y0..=y1 {
        for xi in x0..=x1 {
            let (x, y) = (xi as f64 + 0.5, yi as f64 + 0.5);
            let d = (((x - at[0]) / rx).powi(2) + ((y - at[1]) / ry).powi(2)).sqrt();
            let edge = 0.75 + 0.35 * vnoise(x / 3.0, y / 2.0, seed);
            if d >= edge {
                continue;
            }
            // the middle stays hot longest; the rim cools first
            let heat = ((1.0 - age * 1.6) + 0.6 * (1.0 - d / edge)).clamp(0.0, 1.0) * (1.0 - age);
            if heat > 0.08 && n > 0 {
                let i = ((heat * n as f64) as usize).min(n - 1);
                cv.put(x - 0.5, y - 0.5, fire[i], 1.0); // colour only: the blast's own glow lights it
            } else {
                let a = 0.55 + 0.35 * (1.0 - d / edge);
                cv.put(x - 0.5, y - 0.5, soot, a);
            }
        }
    }
}
