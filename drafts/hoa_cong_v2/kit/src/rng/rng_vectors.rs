// numpy 2.5.4 draws, written by .parity/sfx/rng_vectors.py.
const WORDS_1: [u32; 4] = [1835504127, 1731038949, 1320224556, 2330041505];
const WORDS_301: [u32; 4] = [3578933982, 2260443800, 1783213810, 2743873350];
const WORDS_BIG: [u32; 4] = [2231384047, 684522114, 1418500701, 1730604306];
const STATE_1: (u128, u128) = (207833532711051698738587646355624148094, 194290289479364712180083596243593368443);
const RANDOM_521: [f64; 6] = [f64::from_bits(0x3fe975cb9415495b), f64::from_bits(0x3fe1d1a8894bf2cb), f64::from_bits(0x3fc67b2e5519cac0), f64::from_bits(0x3fe50db003e61cd2), f64::from_bits(0x3fcd42f989eb69a0), f64::from_bits(0x3fb86a0a2bba0608)];
const UNIFORM_7: [f64; 5] = [f64::from_bits(0x3fd00320d4f8f2a4), f64::from_bits(0x3fe96bf36f2bc99a), f64::from_bits(0x3fe1a4d597e502be), f64::from_bits(0xbfe19634950aa578), f64::from_bits(0xbfd99426b378e458)];
const INTS_7_A: [i64; 7] = [5028, 15409, 16098, 92, 8816, 14486, 2318];
const INTS_7_B: i64 = 326;
const UNI_7_C: f64 = f64::from_bits(0x4007957be3339a0e);
const INTS_7_D: i64 = 2;
const EXP_9: [f64; 4] = [f64::from_bits(0x3fa29f62ff3838a6), f64::from_bits(0x3f8b69c4615e34cb), f64::from_bits(0x3f999e0f2358f917), f64::from_bits(0x3f65d3cf1faf85df)];
const BETA_9: [f64; 4] = [f64::from_bits(0x3f9b05b035998296), f64::from_bits(0x3fd1896ec27e694d), f64::from_bits(0x3fd8611e01ca83ef), f64::from_bits(0x3f8410c6feafce4d)];
const AFTER_9: f64 = f64::from_bits(0x3fa30dbb8e2a0d30);
const EXP_FOLD: u64 = 12616774243579581604;
const BETA_FOLD: u64 = 6731042661668828870;
const INT_FOLD: u64 = 3254915985743806464;
const NORMAL_FOLD: u64 = 7304780077276751158;
