//! The beanfx binary.
//!
//!     beanfx version    prints one JSON line: {"version": "<kit version>", "protocol": 2}
//!     beanfx gate ...   the brief gate (see gate.rs)
//!
//! protocol 2 means the kit is the Rust library: drafts link it directly and no JSON job travels on stdin.

mod gate;

pub const PROTOCOL: u32 = 2;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        Some("version") => println!("{{\"version\": \"{}\", \"protocol\": {PROTOCOL}}}", beanfx::VERSION),
        Some("gate") => std::process::exit(gate::run(&args[1..])),
        _ => {
            eprintln!("usage: beanfx version\n       beanfx gate");
            std::process::exit(2);
        }
    }
}
