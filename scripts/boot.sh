#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROM="${ROM:-$ROOT/roms/bootstrap_unscrambled.bin}"
FLOPPY="${FLOPPY:-$ROOT/roms/floppy.img}"
BOOT_KEYS="${BOOT_KEYS:-F0\\r}"

exec dotnet run --project "$ROOT" -- \
  --boot-rom "$ROM" \
  --floppy "$FLOPPY" \
  --floppy-sector-size 400 \
  --floppy-sectors-per-track 20 \
  --floppy-heads 1 \
  --floppy-tracks 77 \
  --type "$BOOT_KEYS" \
  "$@"
