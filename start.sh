#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

PORT="${PORT:-8081}"
BUILD_DIR="${BUILD_DIR:-build}"
PYTHON="${PYTHON:-$ROOT_DIR/venv/bin/python}"

BIND_HOST="${BIND_HOST:-0.0.0.0}"

if [[ -z "$BIND_HOST" ]]; then
  printf 'no active Tailscale IPv4 address; set BIND_HOST in %s\n' "$ENV_FILE" >&2
  exit 1
fi

if [[ ! "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
  printf 'invalid PORT: %s\n' "$PORT" >&2
  exit 1
fi

if [[ "$BUILD_DIR" != /* ]]; then
  BUILD_DIR="$ROOT_DIR/$BUILD_DIR"
fi

if [[ ! -f "$BUILD_DIR/index.html" ]]; then
  printf 'frontend build is missing: %s/index.html\n' "$BUILD_DIR" >&2
  exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
  printf 'python executable is unavailable: %s\n' "$PYTHON" >&2
  exit 1
fi

printf 'Serving %s at https://%s:%s/\n' "$BUILD_DIR" "$BIND_HOST" "$PORT"
exec "$PYTHON" "$ROOT_DIR/scripts/serve_https.py" --port "$PORT" --host "$BIND_HOST" --directory "$BUILD_DIR"
