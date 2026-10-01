#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROM="${ROM:-$ROOT/roms/bootstrap_unscrambled.bin}"
HAWK="${HAWK:-../CenturionComputer/Software/Data Packs/CENTOS_12.IMG}"
BOOT_KEYS="${BOOT_KEYS:-H0\\r}"

exec dotnet run --project "$ROOT" -- \
  --boot-rom "$ROM" \
  --hawk "$HAWK" \
  --type "$BOOT_KEYS" \
  "$@"
