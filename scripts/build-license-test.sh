#!/bin/sh
# Build a separate candidate that accepts only synthetic test receipts.
set -eu
cd "$(dirname "$0")/.."
python3 scripts/build.py --output internal/core/core.py
mkdir -p target
go build -mod=vendor -o target/license-fixture ./tests/license-fixture
license_test_key=$(target/license-fixture --public-key)
license_test_version=$(cat VERSION)
CGO_ENABLED=0 go build -mod=vendor -trimpath -buildvcs=false \
  -ldflags="-buildid= -X main.version=$license_test_version -X github.com/lofimichael/godmode-cli/internal/license.PublicKey=$license_test_key" \
  -o target/godmode-native-test ./cmd/godmode
