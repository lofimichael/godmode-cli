#!/bin/sh
# Optional companion; no credential or business engine is linked into this file.
set -eu
cd "$(dirname "$0")/.."
pack_output=target/godmode-music-pack
if [ "$#" -gt 0 ]; then
  [ "$#" -eq 2 ] && [ "$1" = --output ] || { echo 'Usage: scripts/build-music-native.sh [--output PATH]' >&2; exit 2; }
  pack_output=$2
fi
python3 scripts/build-music.py --output internal/musiccore/player.py
pack_version=$(cat VERSION)
pack_go=$(awk '$1 == "go" { print "go" $2; exit }' go.mod)
mkdir -p "$(dirname "$pack_output")"
CGO_ENABLED=0 GOTOOLCHAIN="$pack_go" go build -mod=vendor -trimpath -buildvcs=false \
  -ldflags="-buildid= -X main.version=$pack_version" -o "$pack_output" ./cmd/godmode-music
printf '%s\n' "$pack_output"
