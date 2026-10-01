#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROM="${ROM:-$ROOT/roms/bootstrap_unscrambled.bin}"
FLOPPY="${FLOPPY:-$ROOT/roms/floppy.img}"
BOOT_KEYS="${BOOT_KEYS:-F0\\r}"
FLOPPY_HEADS="${FLOPPY_HEADS:-1}"
FFC_LINEAR_EXPERIMENTAL_ARGS=()
if [[ "${FFC_LINEAR_EXPERIMENTAL:-0}" == "1" ]]; then
  FFC_LINEAR_EXPERIMENTAL_ARGS=(--ffc-linear-experimental)
fi

exec dotnet run --project "$ROOT" -- \
  --boot-rom "$ROM" \
  --floppy "$FLOPPY" \
  --floppy-sector-size 400 \
  --floppy-sectors-per-track 20 \
  --floppy-heads "$FLOPPY_HEADS" \
  --floppy-tracks 77 \
  "${FFC_LINEAR_EXPERIMENTAL_ARGS[@]}" \
  --type "$BOOT_KEYS" \
  "$@"
