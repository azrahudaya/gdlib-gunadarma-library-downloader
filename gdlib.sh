#!/usr/bin/env bash
# Launcher: pakai venv proyek bila ada.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -x "$DIR/.venv/bin/python" ]; then
  PY="$DIR/.venv/bin/python"
else
  PY="$(command -v python3)"
fi
cd "$DIR"
exec "$PY" -m gdlib "$@"
