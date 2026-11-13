//! beanfx: the fixed tooling of the /beanfx skill, called by the Python kit (kit/bridge.py).
//!
//!     beanfx <area> <command> < job.json        areas: export, sfx, preview
//!     beanfx version
//!
//! Each call reads one JSON job on stdin and prints one JSON answer (job.rs).

mod job;
mod npy;
#[cfg(feature = "export")]
mod export;
#[cfg(feature = "sfx")]
mod sfx;
#[cfg(feature = "preview")]
mod preview;

use std::io::Read;

pub const PROTOCOL: u32 = 1;

fn dispatch(area: &str, cmd: &str, j: &job::Job) -> Result<job::Answer, String> {
    match area {
        #[cfg(feature = "export")]
        "export" => export::run(cmd, j),
        #[cfg(feature = "sfx")]
        "sfx" => sfx::run(cmd, j),
        #[cfg(feature = "preview")]
        "preview" => preview::run(cmd, j),
        _ => Err(format!("unknown area {area:?} (export, sfx, preview)")),
    }
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.first().map(String::as_str) == Some("version") {
        println!("{{\"version\": \"{}\", \"protocol\": {PROTOCOL}}}", env!("CARGO_PKG_VERSION"));
        return;
    }
    if args.len() != 2 {
        eprintln!("usage: beanfx <export|sfx|preview> <command> < job.json\n       beanfx version");
        std::process::exit(2);
    }
    let mut text = String::new();
    let res = std::io::stdin()
        .read_to_string(&mut text)
        .map_err(|e| e.to_string())
        .and_then(|_| job::Job::parse(&text))
        .and_then(|j| dispatch(&args[0], &args[1], &j).and_then(|a| j.finish(a)));
    match res {
        Ok(line) => println!("{line}"),
        Err(e) => {
            println!("{}", serde_json::json!({ "error": e }));
            std::process::exit(1);
        }
    }
}
