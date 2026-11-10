#!/usr/bin/env bash
# Checks the tools /beanfx needs and installs the missing ones into the project (.venv/); --draft <name> gives drafts/<name>/ its own copy of the kit; --pixelfx adds node and pixelfx for the benchmark and reuse.
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
    --draft) draft="${2:-}"; shift ;;
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

# 1. Python with numpy and pillow
PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
  say "venv: missing, creating $ROOT/.venv"
  if command -v uv >/dev/null; then
    uv venv "$ROOT/.venv" >/dev/null
  else
    python3 -m venv "$ROOT/.venv"
  fi
fi
if "$PY" -c "import numpy, PIL" 2>/dev/null; then
  say "venv: ok ($("$PY" -c 'import numpy, PIL; print("numpy", numpy.__version__, "pillow", PIL.__version__)'))"
else
  say "venv: installing numpy and pillow"
  if command -v uv >/dev/null; then
    uv pip install --python "$PY" numpy pillow >/dev/null
  else
    "$PY" -m pip install -q numpy pillow
  fi
  "$PY" -c "import numpy, PIL" 2>/dev/null && say "venv: ok" || { say "venv: install failed"; fail=1; }
fi

# 2. The drawing kit: source of truth is this skill's kit/. Each draft gets its own copy in drafts/<name>/kit/,
# made once and never overwritten, so a plugin update leaves the kit of an existing draft as it was drawn with
if [ $fail -eq 0 ] && (cd "$SKILL/kit" && "$PY" -B -c "import fxkit, fxlib, light, pfx, caster, facing, derive, export, target, ref, rig" 2>/dev/null); then
  say "kit: ok"
else
  say "kit: does not import"; fail=1
fi
if [ -n "$draft" ]; then
  case "$draft" in
    */*|.*|"") say "draft: bad name '$draft'"; exit 1 ;;
  esac
  DKIT="$ROOT/drafts/$draft/kit"
  if [ -d "$DKIT" ] && [ $refresh_kit -eq 1 ]; then
    cp "$SKILL"/kit/*.py "$DKIT"/ && say "draft: refreshed drafts/$draft/kit from the skill's kit; run the draft again and compare its output" \
      || { say "draft: refreshing the kit failed"; fail=1; }
  elif [ -d "$DKIT" ]; then
    say "draft: drafts/$draft/kit kept as it is"
  else
    mkdir -p "$DKIT" && cp "$SKILL"/kit/*.py "$DKIT"/ && say "draft: copied the kit into drafts/$draft/kit" \
      || { say "draft: copying the kit failed"; fail=1; }
  fi
  # where the preview page template lives (export.page); a pointer, not part of the pinned kit, so it is rewritten
  [ -d "$DKIT" ] && printf '%s\n' "$SKILL" > "$DKIT/skill.txt"
fi

# 2b. Which drafts run on an older kit: a kit fix reaches a pinned draft only through --draft <name> --refresh-kit
if [ $kit_status -eq 1 ]; then
  seen=0
  for DK in "$ROOT"/drafts/*/kit; do
    [ -d "$DK" ] || continue
    seen=1
    name="$(basename "$(dirname "$DK")")"
    changed=""
    for f in "$SKILL"/kit/*.py; do
      cmp -s "$f" "$DK/$(basename "$f")" || changed="$changed $(basename "$f")"
    done
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
