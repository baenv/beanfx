//! Helpers shared by the integration tests.
#![allow(dead_code)]

pub mod npy;

use std::path::PathBuf;

/// A fresh empty directory under the system temp dir, named by tag and process id.
pub fn tmpdir(tag: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("beanfx_{tag}_{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&d);
    std::fs::create_dir_all(&d).unwrap();
    d
}
