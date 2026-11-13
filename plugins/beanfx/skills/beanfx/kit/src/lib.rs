//! beanfx: the /beanfx kit in Rust. Short module names (see API.md):
//! `np` numpy helpers, `rng` numpy's Generator, `img` PNG and PIL, `ex` export, `fc` facing, `sfx` sound,
//! `pfx` preview writers and layers, `fl` fxlib, `lt` light, `fk` fxkit, `cs` caster, `tg` target, `rig`, `rf` ref,
//! `dv` derive.

pub mod color;
pub mod cs;
pub mod dv;
pub mod ex;
pub mod fc;
pub mod fk;
pub mod fl;
pub mod img;
pub mod lt;
pub mod np;
pub mod pfx;
pub mod rf;
pub mod rig;
pub mod rng;
pub mod sfx;
pub mod tg;

pub mod py;
mod stack;

pub use stack::{Light, Stack};

/// The array and JSON crates the kit is built on, so a draft needs only `beanfx` in its Cargo.toml
/// (`use beanfx::ndarray::{s, Array2, Array3};`, `beanfx::serde_json::json!`).
pub use ndarray;
pub use serde_json;

/// The kit version (Cargo.toml), written into `beanfx version`.
pub const VERSION: &str = env!("CARGO_PKG_VERSION");
