//! The beanfx binary.
//!
//!     beanfx version              prints one JSON line: {"version": "<kit version>", "protocol": 2}
//!     beanfx gate ...             the brief gate (see gate.rs)
//!     beanfx check <sheet.json>   run craft, framing, budget, act and sound checks on an exported sheet
//!     beanfx sfx <sheet.json>     synthesise WAV track and cues for an exported sheet JSON
//!     beanfx palette [dir]        the host project's palette as JSON (hp.rs), for the palette knob
//!
//! protocol 2 means the kit is the Rust library: drafts link it directly and no JSON job travels on stdin.

mod cli;
mod gate;

pub const PROTOCOL: u32 = 2;

const USAGE: &str = "usage: beanfx version
       beanfx gate <prompt|-> [--context <text>]
       beanfx check <sheet.json> [--max-colours N] [--max-mb M] [--no-trim] [--json]
       beanfx sfx <sheet.json> [--out <dir>] [--voice retro|soft|real] [--element <el>] [--seed N] [--sounds <dir|auto|none>] [--json]
       beanfx palette [dir]";

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        Some("version") => println!("{{\"version\": \"{}\", \"protocol\": {PROTOCOL}}}", beanfx::VERSION),
        Some("gate") => std::process::exit(gate::run(&args[1..])),
        Some("check") => std::process::exit(cli::check(&args[1..])),
        Some("sfx") => std::process::exit(cli::sfx(&args[1..])),
        Some("-h") | Some("--help") | Some("help") => println!("{USAGE}"),
        Some("palette") => println!("{}", beanfx::hp::scan(&project(args.get(1)))),
        _ => {
            eprintln!("{USAGE}");
            std::process::exit(2);
        }
    }
}

/// The project to read: the given folder, else BEANFX_PROJECT, else the git root above the working folder, else it.
fn project(dir: Option<&String>) -> std::path::PathBuf {
    if let Some(d) = dir {
        return d.into();
    }
    if let Ok(p) = std::env::var("BEANFX_PROJECT") {
        return p.into();
    }
    let cwd = std::env::current_dir().unwrap_or_else(|_| ".".into());
    cwd.ancestors().find(|a| a.join(".git").exists()).map(|a| a.to_path_buf()).unwrap_or(cwd)
}
