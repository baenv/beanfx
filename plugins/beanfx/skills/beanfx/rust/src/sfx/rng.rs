//! numpy's np.random.default_rng, bit for bit: SeedSequence hashing into a PCG64 (XSL-RR 128/64) and the draws
//! sfx uses (random, uniform, integers, exponential, beta). The seeded sound stays the sound the Python kit made.

use super::zig::*;

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

    /// rng.beta(a, b) for a or b above 1 (the gamma ratio; sfx uses no other).
    pub fn beta(&mut self, a: f64, b: f64) -> f64 {
        if a <= 1.0 && b <= 1.0 {
            loop {
                let u = self.random();
                let v = self.random();
                let x = u.powf(1.0 / a);
                let y = v.powf(1.0 / b);
                let xpy = x + y;
                if xpy <= 1.0 && u + v > 0.0 && x > 0.0 && y > 0.0 {
                    return x / xpy;
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
            assert_eq!((0.015 * r.standard_exponential()).to_bits(), v.to_bits(), "exponential {i}");
        }
        for (i, v) in BETA_9.iter().enumerate() {
            assert_eq!(r.beta(1.4, 3.0).to_bits(), v.to_bits(), "beta {i}");
        }
        assert_eq!(r.uniform(0.0, 1.0).to_bits(), AFTER_9.to_bits());
    }

    fn fold(xs: impl Iterator<Item = f64>) -> u64 {
        xs.enumerate().fold(0u64, |h, (i, x)| h.wrapping_add(x.to_bits().wrapping_mul(i as u64 + 1)))
    }

    #[test]
    fn long_runs_match_numpy() {
        // 50000 draws each, so the ziggurat's rare branches and Lemire's rejections are crossed too
        let mut r = Rng::new(&[11]);
        assert_eq!(fold((0..50000).map(|_| r.standard_exponential())), EXP_FOLD);
        assert_eq!(fold((0..50000).map(|_| r.beta(1.4, 3.0))), BETA_FOLD);
        assert_eq!(fold((0..50000).map(|_| r.integers(0, 1000003) as f64)), INT_FOLD);
        assert_eq!(fold((0..50000).map(|_| r.standard_normal())), NORMAL_FOLD);
    }

    include!("rng_vectors.rs");
}
