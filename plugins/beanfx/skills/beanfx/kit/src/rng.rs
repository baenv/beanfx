//! numpy's np.random.default_rng, bit for bit: SeedSequence hashing into a PCG64 (XSL-RR 128/64) and the Generator
//! draws the kit uses (random, uniform, integers, choice, normal, beta, standard_exponential, permutation, shuffle).
//! `default_rng(7)` or `default_rng([3, 4])`; a draw of n values is the same stream as n scalar draws.

mod zig;

use ndarray::{Array, ArrayD, ArrayViewD, Dimension, IntoDimension, IxDyn};
use zig::*;

const INIT_A: u32 = 0x43b0d7e5;
const MULT_A: u32 = 0x931e8875;
const INIT_B: u32 = 0x8b51f9dd;
const MULT_B: u32 = 0x58f38ded;
const MIX_MULT_L: u32 = 0xca01f9dd;
const MIX_MULT_R: u32 = 0x4973f715;
const XSHIFT: u32 = 16;
const POOL: usize = 4;
/// a * b + c as numpy's C computes it: clang fuses it into one rounding on arm64; x86-64 wheels have no FMA.
#[inline]
pub fn madd(a: f64, b: f64, c: f64) -> f64 {
    if cfg!(target_arch = "aarch64") {
        a.mul_add(b, c)
    } else {
        a * b + c
    }
}

const PCG_MULT: u128 = (2549297995355413924u128 << 64) | 4865540595714422341u128;

fn hashmix(value: u32, hash_const: &mut u32) -> u32 {
    let mut v = value ^ *hash_const;
    *hash_const = hash_const.wrapping_mul(MULT_A);
    v = v.wrapping_mul(*hash_const);
    v ^ (v >> XSHIFT)
}

fn mix(x: u32, y: u32) -> u32 {
    let r = MIX_MULT_L.wrapping_mul(x).wrapping_sub(MIX_MULT_R.wrapping_mul(y));
    r ^ (r >> XSHIFT)
}

/// The 32-bit words numpy makes of a non-negative int (little end first, 0 is one word).
fn int_words(mut n: u64) -> Vec<u32> {
    if n == 0 {
        return vec![0];
    }
    let mut out = Vec::new();
    while n > 0 {
        out.push(n as u32);
        n >>= 32;
    }
    out
}

/// SeedSequence(entropy).generate_state(n_words, uint32).
pub fn seed_sequence(entropy: &[u64], n_words: usize) -> Vec<u32> {
    let ent: Vec<u32> = entropy.iter().flat_map(|&e| int_words(e)).collect();
    let mut pool = [0u32; POOL];
    let mut hc = INIT_A;
    for (i, p) in pool.iter_mut().enumerate() {
        *p = hashmix(ent.get(i).copied().unwrap_or(0), &mut hc);
    }
    for s in 0..POOL {
        for d in 0..POOL {
            if s != d {
                let h = hashmix(pool[s], &mut hc);
                pool[d] = mix(pool[d], h);
            }
        }
    }
    for &e in ent.iter().skip(POOL) {
        for d in 0..POOL {
            let h = hashmix(e, &mut hc);
            pool[d] = mix(pool[d], h);
        }
    }
    let mut hc = INIT_B;
    (0..n_words)
        .map(|i| {
            let mut v = pool[i % POOL] ^ hc;
            hc = hc.wrapping_mul(MULT_B);
            v = v.wrapping_mul(hc);
            v ^ (v >> XSHIFT)
        })
        .collect()
}

/// numpy's PCG64 with its 32-bit half buffer, so integers() and the doubles interleave as in numpy.
#[derive(Clone, Debug, PartialEq)]
pub struct Rng {
    pub state: u128,
    pub inc: u128,
    pub has_uint32: bool,
    pub uinteger: u32,
}

impl Rng {
    /// np.random.default_rng(seed) for an int (one entry) or a list of ints.
    pub fn new(entropy: &[u64]) -> Rng {
        let w = seed_sequence(entropy, 8);
        let v: Vec<u64> = (0..4).map(|i| (w[2 * i] as u64) | ((w[2 * i + 1] as u64) << 32)).collect();
        let initstate = ((v[0] as u128) << 64) | v[1] as u128;
        let initseq = ((v[2] as u128) << 64) | v[3] as u128;
        let mut r = Rng { state: 0, inc: (initseq << 1) | 1, has_uint32: false, uinteger: 0 };
        r.step();
        r.state = r.state.wrapping_add(initstate);
        r.step();
        r
    }

    fn step(&mut self) {
        self.state = self.state.wrapping_mul(PCG_MULT).wrapping_add(self.inc);
    }

    pub fn next_u64(&mut self) -> u64 {
        self.step();
        let hi = (self.state >> 64) as u64;
        let lo = self.state as u64;
        (hi ^ lo).rotate_right((self.state >> 122) as u32)
    }

    pub fn next_u32(&mut self) -> u32 {
        if self.has_uint32 {
            self.has_uint32 = false;
            return self.uinteger;
        }
        let n = self.next_u64();
        self.has_uint32 = true;
        self.uinteger = (n >> 32) as u32;
        n as u32
    }

    /// rng.random(): 53 bits in [0, 1).
    pub fn random(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 * (1.0 / 9007199254740992.0)
    }

    /// rng.uniform(low, high).
    pub fn uniform(&mut self, low: f64, high: f64) -> f64 {
        let range = high - low;
        madd(range, self.random(), low)
    }

    pub fn uniform_n(&mut self, low: f64, high: f64, n: usize) -> Vec<f64> {
        (0..n).map(|_| self.uniform(low, high)).collect()
    }

    fn lemire32(&mut self, rng: u32) -> u32 {
        let excl = rng.wrapping_add(1);
        let mut m = self.next_u32() as u64 * excl as u64;
        let mut left = m as u32;
        if left < excl {
            let threshold = (u32::MAX - rng) % excl;
            while left < threshold {
                m = self.next_u32() as u64 * excl as u64;
                left = m as u32;
            }
        }
        (m >> 32) as u32
    }

    fn lemire64(&mut self, rng: u64) -> u64 {
        let excl = rng.wrapping_add(1);
        let mut m = self.next_u64() as u128 * excl as u128;
        let mut left = m as u64;
        if left < excl {
            let threshold = (u64::MAX - rng) % excl;
            while left < threshold {
                m = self.next_u64() as u128 * excl as u128;
                left = m as u64;
            }
        }
        (m >> 64) as u64
    }

    /// rng.integers(low, high): numpy's bounded draw (Lemire, the 32-bit path when the range fits).
    pub fn integers(&mut self, low: i64, high: i64) -> i64 {
        let rng = (high - 1).wrapping_sub(low) as u64;
        let v = if rng == 0 {
            0
        } else if rng < 0xFFFF_FFFF {
            self.lemire32(rng as u32) as u64
        } else if rng == 0xFFFF_FFFF {
            self.next_u32() as u64
        } else if rng == u64::MAX {
            self.next_u64()
        } else {
            self.lemire64(rng)
        };
        low.wrapping_add(v as i64)
    }

    /// rng.integers(low, high, n): the same draws as n scalar ones.
    pub fn integers_n(&mut self, low: i64, high: i64, n: usize) -> Vec<i64> {
        (0..n).map(|_| self.integers(low, high)).collect()
    }

    pub fn standard_exponential(&mut self) -> f64 {
        loop {
            let mut ri = self.next_u64() >> 3;
            let idx = (ri & 0xFF) as usize;
            ri >>= 8;
            let x = ri as f64 * WE_DOUBLE[idx];
            if ri < KE_DOUBLE[idx] {
                return x;
            }
            if idx == 0 {
                return ZIGGURAT_EXP_R - (-self.random()).ln_1p();
            }
            if madd(FE_DOUBLE[idx - 1] - FE_DOUBLE[idx], self.random(), FE_DOUBLE[idx]) < (-x).exp() {
                return x;
            }
        }
    }

    /// rng.exponential(scale, n).
    pub fn exponential_n(&mut self, scale: f64, n: usize) -> Vec<f64> {
        (0..n).map(|_| scale * self.standard_exponential()).collect()
    }

    pub fn standard_normal(&mut self) -> f64 {
        loop {
            let mut r = self.next_u64();
            let idx = (r & 0xff) as usize;
            r >>= 8;
            let rabs = (r >> 1) & 0x000f_ffff_ffff_ffff;
            let x = rabs as f64 * WI_DOUBLE[idx] * if r & 1 == 1 { -1.0 } else { 1.0 };
            if rabs < KI_DOUBLE[idx] {
                return x;
            }
            if idx == 0 {
                loop {
                    let xx = -ZIGGURAT_NOR_INV_R * (-self.random()).ln_1p();
                    let yy = -(-self.random()).ln_1p();
                    if yy + yy > xx * xx {
                        return if (rabs >> 8) & 1 == 1 { -(ZIGGURAT_NOR_R + xx) } else { ZIGGURAT_NOR_R + xx };
                    }
                }
            } else if madd(FI_DOUBLE[idx - 1] - FI_DOUBLE[idx], self.random(), FI_DOUBLE[idx]) < (-0.5 * x * x).exp() {
                return x;
            }
        }
    }

    pub fn standard_gamma(&mut self, shape: f64) -> f64 {
        if shape == 1.0 {
            return self.standard_exponential();
        }
        if shape == 0.0 {
            return 0.0;
        }
        if shape < 1.0 {
            loop {
                let u = self.random();
                let v = self.standard_exponential();
                if u <= 1.0 - shape {
                    let x = u.powf(1. / shape);
                    if x <= v {
                        return x;
                    }
                } else {
                    let y = -((1. - u) / shape).ln();
                    let x = (1.0 - shape + shape * y).powf(1. / shape);
                    if x <= v + y {
                        return x;
                    }
                }
            }
        }
        let b = shape - 1. / 3.;
        let c = 1. / (9. * b).sqrt();
        loop {
            let (mut x, mut v);
            loop {
                x = self.standard_normal();
                v = madd(c, x, 1.0);
                if v > 0.0 {
                    break;
                }
            }
            v = v * v * v;
            let u = self.random();
            if u < madd(-(0.0331 * (x * x)), x * x, 1.0) {
                return b * v;
            }
            if u.ln() < madd(b, 1. - v + v.ln(), 0.5 * x * x) {
                return b * v;
            }
        }
    }

    /// rng.beta(a, b): Johnk's algorithm when both are at most 1, else the gamma ratio.
    pub fn beta(&mut self, a: f64, b: f64) -> f64 {
        if a <= 1.0 && b <= 1.0 {
            loop {
                let u = self.random();
                let v = self.random();
                let x = u.powf(1.0 / a);
                let y = v.powf(1.0 / b);
                let xpy = x + y;
                if xpy <= 1.0 && u + v > 0.0 {
                    if xpy > 0.0 {
                        return x / xpy;
                    }
                    let (mut lx, mut ly) = (u.ln() / a, v.ln() / b);
                    let lm = if lx > ly { lx } else { ly };
                    lx -= lm;
                    ly -= lm;
                    return (lx - (lx.exp() + ly.exp()).ln()).exp();
                }
            }
        }
        let ga = self.standard_gamma(a);
        let gb = self.standard_gamma(b);
        ga / (ga + gb)
    }

    pub fn beta_n(&mut self, a: f64, b: f64, n: usize) -> Vec<f64> {
        (0..n).map(|_| self.beta(a, b)).collect()
    }
}

/// The seed of `default_rng`: one non-negative int or a list of them.
pub struct Seed(pub Vec<u64>);

impl From<u64> for Seed {
    fn from(v: u64) -> Self {
        Seed(vec![v])
    }
}
impl From<i64> for Seed {
    fn from(v: i64) -> Self {
        assert!(v >= 0, "default_rng: a seed must be non-negative");
        Seed(vec![v as u64])
    }
}
impl From<i32> for Seed {
    fn from(v: i32) -> Self {
        Seed::from(v as i64)
    }
}
impl From<usize> for Seed {
    fn from(v: usize) -> Self {
        Seed(vec![v as u64])
    }
}
impl From<&[u64]> for Seed {
    fn from(v: &[u64]) -> Self {
        Seed(v.to_vec())
    }
}
impl From<Vec<u64>> for Seed {
    fn from(v: Vec<u64>) -> Self {
        Seed(v)
    }
}
impl<const N: usize> From<[u64; N]> for Seed {
    fn from(v: [u64; N]) -> Self {
        Seed(v.to_vec())
    }
}

/// np.random.default_rng(seed).
pub fn default_rng(seed: impl Into<Seed>) -> Rng {
    Rng::new(&seed.into().0)
}

/// Options of `choice`: replace true, no p, shuffle true.
#[derive(Clone, Debug)]
pub struct Choice {
    pub replace: bool,
    pub p: Option<Vec<f64>>,
    pub shuffle: bool,
}

impl Default for Choice {
    fn default() -> Self {
        Choice { replace: true, p: None, shuffle: true }
    }
}

/// cdf.searchsorted(x, side="right"): the count of entries at most x.
fn search_right(cdf: &[f64], x: f64) -> usize {
    cdf.partition_point(|&c| c <= x)
}

fn cdf_of(p: &[f64]) -> Vec<f64> {
    let mut acc = 0.0;
    let mut c: Vec<f64> = p.iter().map(|&v| {
        acc += v;
        acc
    }).collect();
    let last = *c.last().expect("choice: empty p");
    c.iter_mut().for_each(|v| *v /= last);
    c
}

impl Rng {
    fn fill<D: Dimension>(&mut self, shape: impl IntoDimension<Dim = D>, mut f: impl FnMut(&mut Rng) -> f64) -> Array<f64, D> {
        let d = shape.into_dimension();
        let n = d.size();
        let v: Vec<f64> = (0..n).map(|_| f(self)).collect();
        Array::from_shape_vec(d, v).unwrap()
    }

    /// rng.random(n).
    pub fn random_n(&mut self, n: usize) -> Vec<f64> {
        (0..n).map(|_| self.random()).collect()
    }

    /// rng.random(shape), for example `random_shape((h, w))`.
    pub fn random_shape<D: Dimension>(&mut self, shape: impl IntoDimension<Dim = D>) -> Array<f64, D> {
        self.fill(shape, Rng::random)
    }

    /// rng.uniform(low, high, shape).
    pub fn uniform_shape<D: Dimension>(&mut self, low: f64, high: f64, shape: impl IntoDimension<Dim = D>) -> Array<f64, D> {
        self.fill(shape, |r| r.uniform(low, high))
    }

    /// rng.uniform(low, high) with array bounds, broadcast together (use `arr0(x).into_dyn()` for a scalar bound).
    pub fn uniform_arr(&mut self, low: ArrayViewD<f64>, high: ArrayViewD<f64>) -> Result<ArrayD<f64>, String> {
        let shape = crate::np::broadcast_shape(low.shape(), high.shape())?;
        let l = low.broadcast(IxDyn(&shape)).ok_or("uniform: shapes do not broadcast")?;
        let h = high.broadcast(IxDyn(&shape)).ok_or("uniform: shapes do not broadcast")?;
        let v: Vec<f64> = l.iter().zip(h.iter()).map(|(&a, &b)| self.uniform(a, b)).collect();
        Ok(ArrayD::from_shape_vec(IxDyn(&shape), v).unwrap())
    }

    /// rng.integers(high): one argument is the high end, from 0.
    pub fn integers1(&mut self, high: i64) -> i64 {
        self.integers(0, high)
    }

    /// One draw in [0, max] the way numpy's random_bounded_uint64 makes it (Floyd's choice, the tail shuffle).
    fn bounded(&mut self, max: u64) -> u64 {
        if max == 0 {
            0
        } else if max < 0xFFFF_FFFF {
            self.lemire32(max as u32) as u64
        } else if max == 0xFFFF_FFFF {
            self.next_u32() as u64
        } else if max == u64::MAX {
            self.next_u64()
        } else {
            self.lemire64(max)
        }
    }

    /// numpy's random_interval: a masked draw in [0, max] with rejection (shuffle and permutation).
    fn interval(&mut self, max: u64) -> u64 {
        if max == 0 {
            return 0;
        }
        let mut mask = max;
        for s in [1, 2, 4, 8, 16, 32] {
            mask |= mask >> s;
        }
        if max <= 0xFFFF_FFFF {
            loop {
                let v = (self.next_u32() as u64) & mask;
                if v <= max {
                    return v;
                }
            }
        }
        loop {
            let v = self.next_u64() & mask;
            if v <= max {
                return v;
            }
        }
    }

    fn shuffle_int(&mut self, data: &mut [usize], first: usize) {
        for i in (first.max(1)..data.len()).rev() {
            let j = self.bounded(i as u64) as usize;
            data.swap(i, j);
        }
    }

    /// rng.choice(pop, size, ...): indices into a population of pop. Index the array yourself for choice(array).
    /// A scalar choice is `choice(pop, 1, ..)[0]`, the same draws.
    pub fn choice(&mut self, pop: usize, size: usize, o: Choice) -> Result<Vec<usize>, String> {
        if let Some(p) = &o.p {
            if p.len() != pop {
                return Err("choice: a and p must have same size".into());
            }
        }
        if o.replace {
            return Ok(match &o.p {
                Some(p) => {
                    let cdf = cdf_of(p);
                    (0..size).map(|_| search_right(&cdf, self.random())).collect()
                }
                None => (0..size).map(|_| self.integers(0, pop as i64) as usize).collect(),
            });
        }
        if size > pop {
            return Err("choice: cannot take a larger sample than population when replace is false".into());
        }
        if let Some(p0) = &o.p {
            if p0.iter().filter(|&&v| v > 0.0).count() < size {
                return Err("choice: fewer non-zero entries in p than size".into());
            }
            let mut p = p0.clone();
            let mut found: Vec<usize> = Vec::with_capacity(size);
            while found.len() < size {
                let x = self.random_n(size - found.len());
                for &f in &found {
                    p[f] = 0.0;
                }
                let cdf = cdf_of(&p);
                let new: Vec<usize> = x.iter().map(|&u| search_right(&cdf, u)).collect();
                let mut seen = std::collections::HashSet::new();
                found.extend(new.into_iter().filter(|v| seen.insert(*v)));
            }
            return Ok(found);
        }
        let cutoff = if o.shuffle { 50 } else { 20 };
        if pop > 10000 && size > pop / cutoff {
            let mut idx: Vec<usize> = (0..pop).collect();
            self.shuffle_int(&mut idx, (pop - size).max(1));
            return Ok(idx[pop - size..].to_vec());
        }
        let set_size = (1.2 * size as f64) as u64;
        let mut mask = set_size;
        for s in [1, 2, 4, 8, 16, 32] {
            mask |= mask >> s;
        }
        let mut hash = vec![u64::MAX; (mask + 1) as usize];
        let mut idx = vec![0usize; size];
        for j in (pop - size) as u64..pop as u64 {
            let val = self.bounded(j);
            let mut loc = (val & mask) as usize;
            while hash[loc] != u64::MAX && hash[loc] != val {
                loc = (loc + 1) & mask as usize;
            }
            let k = (j as usize) + size - pop;
            if hash[loc] == u64::MAX {
                hash[loc] = val;
                idx[k] = val as usize;
            } else {
                let mut loc = (j & mask) as usize;
                while hash[loc] != u64::MAX {
                    loc = (loc + 1) & mask as usize;
                }
                hash[loc] = j;
                idx[k] = j as usize;
            }
        }
        if o.shuffle {
            self.shuffle_int(&mut idx, 1);
        }
        Ok(idx)
    }

    /// rng.normal(loc, scale).
    pub fn normal(&mut self, loc: f64, scale: f64) -> f64 {
        let z = self.standard_normal();
        madd(scale, z, loc)
    }

    /// rng.normal(loc, scale, n).
    pub fn normal_n(&mut self, loc: f64, scale: f64, n: usize) -> Vec<f64> {
        (0..n).map(|_| self.normal(loc, scale)).collect()
    }

    /// rng.normal(loc, scale, shape).
    pub fn normal_shape<D: Dimension>(&mut self, loc: f64, scale: f64, shape: impl IntoDimension<Dim = D>) -> Array<f64, D> {
        self.fill(shape, |r| r.normal(loc, scale))
    }

    /// rng.standard_exponential(n).
    pub fn standard_exponential_n(&mut self, n: usize) -> Vec<f64> {
        (0..n).map(|_| self.standard_exponential()).collect()
    }

    /// rng.shuffle(x) for a 1-d sequence (Fisher-Yates from the end, numpy's masked interval draw).
    pub fn shuffle<T>(&mut self, x: &mut [T]) {
        for i in (1..x.len()).rev() {
            let j = self.interval(i as u64) as usize;
            x.swap(i, j);
        }
    }

    /// rng.permutation(n).
    pub fn permutation(&mut self, n: usize) -> Vec<usize> {
        let mut v: Vec<usize> = (0..n).collect();
        self.shuffle(&mut v);
        v
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn seed_sequence_matches_numpy() {
        // np.random.SeedSequence(...).generate_state(4)
        assert_eq!(seed_sequence(&[1], 4), WORDS_1);
        assert_eq!(seed_sequence(&[3, 0, 1], 4), WORDS_301);
        assert_eq!(seed_sequence(&[12345678901, 7, 2, 9, 4], 4), WORDS_BIG);
    }

    #[test]
    fn pcg64_state_matches_numpy() {
        let r = Rng::new(&[1]);
        assert_eq!(r.state, STATE_1.0);
        assert_eq!(r.inc, STATE_1.1);
    }

    #[test]
    fn draws_match_numpy() {
        // the sequence printed by the generator script in .parity/sfx/rng_vectors.py
        let mut r = Rng::new(&[5, 2, 1]);
        for (i, v) in RANDOM_521.iter().enumerate() {
            assert_eq!(r.random().to_bits(), v.to_bits(), "random {i}");
        }
        let mut r = Rng::new(&[7]);
        assert_eq!(r.uniform_n(-1.0, 1.0, 5).iter().map(|x| x.to_bits()).collect::<Vec<_>>(),
                   UNIFORM_7.iter().map(|x| x.to_bits()).collect::<Vec<_>>());
        assert_eq!(r.integers_n(0, 17640, 7), INTS_7_A);
        assert_eq!(r.integers(40, 400), INTS_7_B);
        assert_eq!(r.uniform(0.0, 6.3).to_bits(), UNI_7_C.to_bits());
        assert_eq!(r.integers(0, 3), INTS_7_D);
        let mut r = Rng::new(&[9, 1, 0]);
        for (i, v) in EXP_9.iter().enumerate() {
            close(0.015 * r.standard_exponential(), *v, &format!("exponential {i}"));
        }
        for (i, v) in BETA_9.iter().enumerate() {
            close(r.beta(1.4, 3.0), *v, &format!("beta {i}"));
        }
        assert_eq!(r.uniform(0.0, 1.0).to_bits(), AFTER_9.to_bits());
    }

    /// The vectors come from numpy on macOS arm64 (FMA, Apple libm). There the draws match bit for bit; on other
    /// platforms numpy's own build rounds log, pow and a * b + c differently, so a few ulp is all that can be asked.
    const EXACT: bool = cfg!(all(target_arch = "aarch64", target_os = "macos"));

    fn close(got: f64, want: f64, what: &str) {
        if EXACT {
            assert_eq!(got.to_bits(), want.to_bits(), "{what}");
        } else {
            assert!((got - want).abs() <= 1e-12 * want.abs().max(1e-300), "{what}: {got} vs {want}");
        }
    }

    fn fold(xs: impl Iterator<Item = f64>) -> u64 {
        xs.enumerate().fold(0u64, |h, (i, x)| h.wrapping_add(x.to_bits().wrapping_mul(i as u64 + 1)))
    }

    #[test]
    #[cfg_attr(not(all(target_arch = "aarch64", target_os = "macos")), ignore = "bit-exact folds hold on macOS arm64 only")]
    fn long_runs_match_numpy() {
        // 50000 draws each, so the ziggurat's rare branches and Lemire's rejections are crossed too
        let mut r = Rng::new(&[11]);
        assert_eq!(fold((0..50000).map(|_| r.standard_exponential())), EXP_FOLD);
        assert_eq!(fold((0..50000).map(|_| r.beta(1.4, 3.0))), BETA_FOLD);
        assert_eq!(fold((0..50000).map(|_| r.integers(0, 1000003) as f64)), INT_FOLD);
        assert_eq!(fold((0..50000).map(|_| r.standard_normal())), NORMAL_FOLD);
    }

    include!("rng/rng_vectors.rs");
    include!("rng/gen_vectors.rs");

    fn same(got: &[f64], want: &[u64], what: &str) {
        assert_eq!(got.len(), want.len(), "{what}: length");
        for (i, (g, w)) in got.iter().zip(want).enumerate() {
            close(*g, f64::from_bits(*w), &format!("{what} {i}"));
        }
    }

    fn idx(v: Vec<usize>) -> Vec<i64> {
        v.into_iter().map(|x| x as i64).collect()
    }

    #[test]
    fn generator_matches_numpy() {
        let mut r = default_rng([3, 4]);
        let mut g = vec![r.random()];
        g.extend(r.random_n(5));
        g.extend(r.random_shape((2, 3)).iter());
        same(&g, G_RANDOM, "random");
        let mut g = vec![r.uniform(-2.0, 5.0)];
        g.extend(r.uniform_n(0.5, 1.5, 4));
        g.extend(r.uniform_shape(-1.0, 1.0, (2, 2)).iter());
        same(&g, G_UNIFORM, "uniform");
        let low = ndarray::arr2(&[[0.0], [1.0], [-3.0]]).into_dyn();
        let high = ndarray::arr1(&[1.0, 2.0, 4.0, 8.0]).into_dyn();
        let bc = r.uniform_arr(low.view(), high.view()).unwrap();
        assert_eq!(bc.shape(), &[3, 4]);
        same(&bc.iter().copied().collect::<Vec<_>>(), G_UNIFORM_BC, "uniform broadcast");
        let sa = r.uniform_arr(ndarray::arr0(0.25).into_dyn().view(), high.view()).unwrap();
        same(&sa.iter().copied().collect::<Vec<_>>(), G_UNIFORM_SA, "uniform scalar-array");

        let mut r = default_rng(42);
        let mut g = vec![r.integers1(9)];
        g.extend(r.integers_n(2, 50, 6));
        g.push(r.integers(-5, 5));
        g.extend(r.integers_n(0, 1 << 40, 3));
        g.push(r.integers(0, 1 << 32));
        g.extend(r.integers_n(0, 7, 4));
        assert_eq!(g, G_INTS);

        let mut r = default_rng(5);
        let pm = [-1i64, 1];
        let mut g = vec![pm[r.choice(2, 1, Choice::default()).unwrap()[0]]];
        g.extend(idx(r.choice(7, 6, Choice::default()).unwrap()));
        g.extend(idx(r.choice(3, 1, Choice::default()).unwrap()));
        assert_eq!(g, G_CHOICE_R);
        let p = Some(vec![0.1, 0.2, 0.3, 0.15, 0.25]);
        assert_eq!(idx(r.choice(5, 8, Choice { p, ..Default::default() }).unwrap()), G_CHOICE_P);
        let nr = Choice { replace: false, ..Default::default() };
        assert_eq!(idx(r.choice(10, 4, nr.clone()).unwrap()), G_CHOICE_NR);
        assert_eq!(idx(r.choice(12, 1, nr.clone()).unwrap()), G_CHOICE_NR1);
        let p = Some(vec![0.3, 0.05, 0.25, 0.1, 0.2, 0.1]);
        assert_eq!(idx(r.choice(6, 4, Choice { p, ..nr.clone() }).unwrap()), G_CHOICE_NRP);
        assert_eq!(idx(r.choice(30, 9, Choice { shuffle: false, ..nr.clone() }).unwrap()), G_CHOICE_NS);
        assert_eq!(idx(r.choice(20000, 500, nr).unwrap()), G_CHOICE_TAIL);
        same(&[r.random()], G_CHOICE_AFTER, "after choice");

        let mut r = default_rng(8);
        let mut g = vec![r.normal(0.0, 1.0)];
        g.extend(r.normal_n(0.0, 1.0, 5));
        g.extend(r.normal_n(2.5, 0.3, 6));
        g.extend(r.normal_shape(-1.0, 3.0, (2, 2)).iter());
        g.push(r.standard_normal());
        same(&g, G_NORMAL, "normal");
        let mut g = r.beta_n(0.5, 0.7, 6);
        g.extend(r.beta_n(2.0, 3.0, 4));
        g.extend(r.beta_n(0.4, 2.5, 4));
        g.push(r.beta(1.0, 1.0));
        same(&g, G_BETA, "beta");
        let mut g = vec![r.standard_exponential()];
        g.extend(r.standard_exponential_n(4));
        same(&g, G_EXP, "standard_exponential");

        let mut r = default_rng(13);
        let mut g = idx(r.permutation(10));
        g.extend(idx(r.permutation(1)));
        g.extend(idx(r.permutation(37)));
        assert_eq!(g, G_PERM);
        let mut a: Vec<f64> = (0..12).map(|i| i as f64).collect();
        r.shuffle(&mut a);
        same(&a, G_SHUFFLE, "shuffle");
        same(&[r.random()], G_PERM_AFTER, "after shuffle");
        let mut r = default_rng(99);
        same(&r.beta_n(0.3, 1.5, 6), G_GAMMA_SMALL, "beta small shape");
    }
}
