#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROM="${ROM:-$ROOT/roms/bootstrap_unscrambled.bin}"
HAWK="${HAWK:-../CenturionComputer/Software/Data Packs/CENTOS_12.IMG}"
HAWK1="${HAWK1:-}"
BOOT_KEYS="${BOOT_KEYS:-H0\\r}"

args=(
  --boot-rom "$ROM"
  --hawk "$HAWK"
)
if [[ -n "$HAWK1" ]]; then
  args+=(--hawk1 "$HAWK1")
fi
args+=(--type "$BOOT_KEYS")

exec dotnet run --project "$ROOT" -- "${args[@]}" "$@"
