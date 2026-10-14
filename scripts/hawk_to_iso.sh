#!/usr/bin/env bash
# Export a cvit/Disk6 Hawk platter to a Windows-mountable ISO-9660 image.
#
# Usage:
#   scripts/hawk_to_iso.sh [hawk.img] [out.iso]
#
# Defaults:
#   hawk.img = out/data.img
#   out.iso  = out/data.iso
set -euo pipefail

img="${1:-out/data.img}"
iso="${2:-out/data.iso}"
label="${CVIT_ISO_LABEL:-CVIT_DATA}"

tmp="$(mktemp -d)"
cleanup() { rm -rf "$tmp"; }
trap cleanup EXIT

export_dir="$tmp/export"

scripts/hawk_export_tmp.py "$img" "$export_dir" --force >/dev/null
mkdir -p "$(dirname "$iso")"

nix shell nixpkgs#xorriso -c xorrisofs \
  -o "$iso" \
  -J -r \
  -V "$label" \
  "$export_dir"

printf 'wrote %s from %s\n' "$iso" "$img"
