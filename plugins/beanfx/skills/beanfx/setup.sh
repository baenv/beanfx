#!/usr/bin/env bash
# Checks the tools /beanfx needs and installs the missing ones into the project: the beanfx binary built by cargo into .beanfx/bin/beanfx; --draft <name> scaffolds drafts/<name>/ (a Cargo crate with its own copy of the kit); --pixelfx adds node and pixelfx for the benchmark and reuse.
# --kit-status lists the drafts whose pinned kit differs from this skill's kit; --draft <name> --refresh-kit copies the current kit over that draft's (asked for by name only, never by itself).
# Prints PIXELFX=<dir> when the benchmark tools are there and LAYERS=<script> when reuse works; exits 1 when something cannot be installed here.
set -u

SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"  # this skill (plugin install or the beanfx repo)
# the project the effects live in: BEANFX_PROJECT, else the git root of the current folder, else the current folder
ROOT="${BEANFX_PROJECT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
PIXELFX_URL="https://github.com/patch-gg/pixelfx"
want_pixelfx=0
draft=""
kit_status=0
refresh_kit=0
while [ $# -gt 0 ]; do
  case "$1" in
    --pixelfx) want_pixelfx=1 ;;
    --draft) draft="${2:-}"; [ -n "$draft" ] || { printf '%s\n' "--draft needs a name"; exit 1; }; shift ;;
    --kit-status) kit_status=1 ;;
    --refresh-kit) refresh_kit=1 ;;
    *) printf 'unknown option: %s\n' "$1"; exit 1 ;;
  esac
  shift
done
fail=0
if [ $refresh_kit -eq 1 ] && [ -z "$draft" ]; then
  printf '%s\n' "--refresh-kit needs --draft <name>"; exit 1
fi

say() { printf '%s\n' "$*"; }

# 1. The beanfx binary (gate, version), built from this skill's kit/ with cargo into the project's .beanfx/target and
# copied to .beanfx/bin/beanfx; rebuilt when the kit's src, Cargo.toml or Cargo.lock change. Drafts share the same
# target folder (drafts/<name>/.cargo/config.toml), so each crate builds once per project.
BEANFX="$ROOT/.beanfx"
BIN="$BEANFX/bin/beanfx"
if ! command -v cargo >/dev/null; then
  say "beanfx: needs cargo to build; install Rust from https://rustup.rs (curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh), then rerun"
  fail=1
else
  if command -v shasum >/dev/null; then SHA=shasum; else SHA=sha1sum; fi
  SUM="$(find "$SKILL/kit/src" "$SKILL/kit/Cargo.toml" "$SKILL/kit/Cargo.lock" -type f -print0 | sort -z | xargs -0 cat | $SHA | cut -c1-40)"
  [ -n "$SUM" ] || { say "beanfx: needs shasum or sha1sum to tell when the kit changed"; exit 1; }
  if [ -x "$BIN" ] && [ "$(cat "$BEANFX/beanfx.src" 2>/dev/null)" = "$SUM" ]; then
    say "beanfx: ok ($("$BIN" version))"
  else
    say "beanfx: building the binary (first build takes about a minute)"
    if cargo build --release --locked --quiet --manifest-path "$SKILL/kit/Cargo.toml" --target-dir "$BEANFX/target" \
        && mkdir -p "$BEANFX/bin" && cp "$BEANFX/target/release/beanfx" "$BIN"; then
      printf '%s\n' "$SUM" > "$BEANFX/beanfx.src"
      say "beanfx: ok ($("$BIN" version))"
    else
      say "beanfx: build failed"; fail=1
    fi
  fi
  # the binary and the shared build folder stay out of the project's git
  [ -d "$BEANFX" ] && [ ! -f "$BEANFX/.gitignore" ] && printf '*\n' > "$BEANFX/.gitignore"
  # where the binary finds the knob files (beanfx gate)
  [ -d "$BEANFX" ] && printf '%s\n' "$SKILL" > "$BEANFX/skill.txt"
fi

# 2. The kit: source of truth is this skill's kit/ crate. Each draft gets its own copy in drafts/<name>/kit/ (without
# target/, tests/ and the .md files), made once and never overwritten, so a plugin update leaves the kit of an
# existing draft as it was drawn with
copy_kit() {
  mkdir -p "$1" && (cd "$SKILL/kit" && tar --exclude='./target' --exclude='./tests' --exclude='*.md' -cf - .) | tar -C "$1" -xf -
}
kit_files() {
  (cd "$SKILL/kit" && find . -type f ! -path './target/*' ! -path './tests/*' ! -name '*.md' | sort)
}
if [ -n "$draft" ]; then
  case "$draft" in
    */*|.*) say "draft: bad name '$draft'"; exit 1 ;;
  esac
  DDIR="$ROOT/drafts/$draft"
  DKIT="$DDIR/kit"
  if [ -d "$DKIT" ] && [ $refresh_kit -eq 1 ]; then
    rm -rf "$DKIT/src" && copy_kit "$DKIT" && say "draft: refreshed drafts/$draft/kit from the skill's kit; run the draft again and compare its output" \
      || { say "draft: refreshing the kit failed"; fail=1; }
  elif [ -d "$DKIT" ]; then
    say "draft: drafts/$draft/kit kept as it is"
  else
    copy_kit "$DKIT" && say "draft: copied the kit into drafts/$draft/kit" \
      || { say "draft: copying the kit failed"; fail=1; }
  fi
  # where the preview page template lives (ex::page); a pointer, not part of the pinned kit, so it is rewritten
  [ -d "$DKIT" ] && printf '%s\n' "$SKILL" > "$DKIT/skill.txt"
  if [ ! -f "$DDIR/Cargo.toml" ]; then
    mkdir -p "$DDIR/src" "$DDIR/.cargo"
    cat > "$DDIR/Cargo.toml" <<TOML
[package]
name = "$draft"
version = "0.1.0"
edition = "2021"
publish = false

[dependencies]
beanfx = { path = "kit" }

[profile.release]
opt-level = 3
TOML
    cat > "$DDIR/.cargo/config.toml" <<'TOML'
# every draft builds into the project's one target folder, so the kit and its crates build once
[build]
target-dir = "../../.beanfx/target"
TOML
    # the kit's tested crate versions, so a new draft builds offline with what the kit was tested on
    [ -f "$DDIR/Cargo.lock" ] || cp "$SKILL/kit/Cargo.lock" "$DDIR/Cargo.lock"
    say "draft: wrote drafts/$draft/Cargo.toml and .cargo/config.toml"
  fi
  if [ ! -f "$DDIR/src/main.rs" ]; then
    cat > "$DDIR/src/main.rs" <<'RS'
//! Starter draft: a square that crosses a 24x16 cell in 8 frames. Replace it with the effect.
//! Run: cargo run --release -q (writes out/, exits 1 when a check fails).

use beanfx::ndarray::Array3;
use beanfx::{ex, pfx};
use std::path::PathBuf;
use std::process::ExitCode;

const NAME: &str = env!("CARGO_PKG_NAME");
const FPS: f64 = 12.0;
const W: usize = 24;
const H: usize = 16;
const N: usize = 8;

fn render(f: usize) -> Array3<u8> {
    let mut cell = Array3::<u8>::zeros((H, W, 4));
    for y in 5..11 {
        for x in (3 + 2 * f)..(9 + 2 * f) {
            for (c, v) in [255, 160 + 10 * f as u8, 40, 255].into_iter().enumerate() {
                cell[[y, x, c]] = v;
            }
        }
    }
    cell
}

fn run() -> Result<u8, String> {
    let out = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("out");
    let frames: Vec<Array3<u8>> = (0..N).map(render).collect();
    pfx::strip(&frames, out.join(format!("{NAME}_1x.png")))?;
    ex::write(out.join("sheets"), NAME, &frames, FPS, [(W / 2) as f64, (H / 2) as f64], false, Default::default())?;
    let bad = ex::check(&frames, ex::Check { hold: true, ..Default::default() })?;
    for line in &bad {
        println!("{line}");
    }
    println!("{}", if bad.is_empty() { "checks: clean".to_string() } else { format!("{} problems", bad.len()) });
    Ok(u8::from(!bad.is_empty()))
}

fn main() -> ExitCode {
    match run() {
        Ok(code) => ExitCode::from(code),
        Err(e) => {
            eprintln!("error: {e}");
            ExitCode::from(2)
        }
    }
}
RS
    say "draft: wrote drafts/$draft/src/main.rs"
  fi
fi

# 2b. Which drafts run on an older kit: a kit fix reaches a pinned draft only through --draft <name> --refresh-kit
if [ $kit_status -eq 1 ]; then
  seen=0
  for DK in "$ROOT"/drafts/*/kit; do
    [ -d "$DK" ] || continue
    seen=1
    name="$(basename "$(dirname "$DK")")"
    changed=""
    while IFS= read -r f; do
      cmp -s "$SKILL/kit/$f" "$DK/$f" || changed="$changed ${f#./}"
    done < <(kit_files)
    # files the draft's kit has and the skill's kit dropped
    while IFS= read -r f; do
      [ -e "$SKILL/kit/$f" ] || changed="$changed ${f#./}(gone)"
    done < <(cd "$DK" && find ./src -type f | sort)
    if [ -z "$changed" ]; then say "kit-status: $name current"; else say "kit-status: $name behind:$changed"; fi
  done
  [ $seen -eq 1 ] || say "kit-status: no draft has its own kit"
fi

# 3. pixelfx, only for reuse and the benchmark: a clone in the project
if [ $want_pixelfx -eq 1 ]; then
  if ! command -v node >/dev/null; then
    say "node: missing; install Node 18 or newer (brew install node, or fnm install 22)"
    fail=1
  elif [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 18 ]; then
    say "node: $(node --version) is older than 18"; fail=1
  else
    say "node: ok ($(node --version))"
  fi
  PIXELFX="$ROOT/pixelfx"
  if [ ! -f "$PIXELFX/tools/render.mjs" ]; then
    say "pixelfx: missing, cloning $PIXELFX_URL into $PIXELFX"
    git clone --depth 1 "$PIXELFX_URL" "$PIXELFX" >/dev/null 2>&1 || { say "pixelfx: clone failed"; fail=1; }
  fi
  # each use needs its own tools: the benchmark render.mjs and list.mjs, reuse (2b) the skill's tools/layers.mjs,
  # which runs on pixelfx's tools/lib/fxlib.mjs (pixelfx 0.3 dropped its own layers.mjs)
  if [ -f "$PIXELFX/tools/render.mjs" ] && [ -f "$PIXELFX/tools/list.mjs" ]; then
    say "pixelfx: benchmark ok ($(git -C "$PIXELFX" log -1 --format='%h %s' 2>/dev/null | cut -c1-60))"
    say "PIXELFX=$PIXELFX"
  else
    say "pixelfx: not usable at $PIXELFX (no tools/render.mjs or tools/list.mjs)"; fail=1
  fi
  if [ -f "$PIXELFX/tools/lib/fxlib.mjs" ]; then
    say "pixelfx: reuse ok"
    say "LAYERS=$SKILL/tools/layers.mjs"
  else
    say "pixelfx: reuse unavailable (no tools/lib/fxlib.mjs); the benchmark still works"
  fi
fi
exit $fail
