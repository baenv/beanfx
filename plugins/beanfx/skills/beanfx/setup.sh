#!/usr/bin/env bash
# Checks the tools /beanfx needs and installs the missing ones into the project (.venv/, kit/, drafts/); --pixelfx adds node and pixelfx for reuse.
# Prints PIXELFX=<dir> when pixelfx is ready; exits 1 when something cannot be installed here.
set -u

SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"  # this skill (plugin install or the beanfx repo)
# the project the effects live in: BEANFX_PROJECT, else the git root of the current folder, else the current folder
ROOT="${BEANFX_PROJECT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
PIXELFX_URL="https://github.com/patch-gg/pixelfx"
want_pixelfx=0
[ "${1:-}" = "--pixelfx" ] && want_pixelfx=1
fail=0

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

# 2. The drawing kit: source of truth is this skill's kit/, copied into the project's kit/ when a file differs
mkdir -p "$ROOT/kit"
for src in "$SKILL"/kit/*.py; do
  [ -f "$src" ] || continue
  dst="$ROOT/kit/$(basename "$src")"
  cmp -s "$src" "$dst" || { cp "$src" "$dst"; say "kit: copied $(basename "$src") from the skill kit"; }
done
if [ $fail -eq 0 ] && (cd "$ROOT/kit" && "$PY" -c "import fxkit, fxlib, light, pfx, caster, facing, derive, export, target, ref" 2>/dev/null); then
  say "kit: ok"
else
  say "kit: does not import"; fail=1
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
  if [ -f "$PIXELFX/tools/render.mjs" ] && [ -f "$PIXELFX/tools/layers.mjs" ]; then
    say "pixelfx: ok"
    say "PIXELFX=$PIXELFX"
  else
    say "pixelfx: not usable at $PIXELFX"; fail=1
  fi
fi

exit $fail
