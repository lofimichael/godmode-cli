#!/bin/sh
# Build the native terminal UI around its readable embedded Python engine.
set -eu
cd "$(dirname "$0")/.."

native_output=target/godmode-native
native_music=yes
native_tags=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output)
      [ "$#" -ge 2 ] || { echo 'build-native: --output needs a path' >&2; exit 2; }
      native_output=$2
      shift 2
      ;;
    --without-music) native_music=no; shift ;;
    *) echo 'Usage: scripts/build-native.sh [--output PATH] [--without-music]' >&2; exit 2 ;;
  esac
done

if [ "$native_music" = no ]; then
  native_tags=nomusic
  python3 scripts/build.py --without-music --output internal/core/core.py
else
  python3 scripts/build.py --output internal/core/core.py
fi
native_version=$(cat VERSION)
native_go=$(awk '$1 == "go" { print "go" $2; exit }' go.mod)
mkdir -p "$(dirname "$native_output")"
if [ -d vendor ]; then
  native_modules=vendor
else
  native_modules='readonly'
fi
CGO_ENABLED=0 GOTOOLCHAIN="$native_go" go build -mod="$native_modules" -tags="$native_tags" -trimpath -buildvcs=false \
  -ldflags="-buildid= -X main.version=$native_version" -o "$native_output" ./cmd/godmode
printf '%s\n' "$native_output"
