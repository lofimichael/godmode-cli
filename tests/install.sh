#!/bin/sh
# Exercise installer refusal and replacement paths with synthetic executables.
set -eu
repo=$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)
scratch=$(mktemp -d)
# All files here are synthetic and the directory was allocated by this test.
trap 'rm -rf "$scratch"' EXIT HUP INT TERM
mkdir -p "$scratch/artifact" "$scratch/bin"
printf '%s\n' '#!/bin/sh' 'printf "synthetic-version-one\n"' > "$scratch/artifact/godmode"
digest=$(shasum -a 256 < "$scratch/artifact/godmode" | awk '{print $1}')
sh "$repo/install.sh" --binary "$scratch/artifact/godmode" --sha256 "$digest" --bin-dir "$scratch/bin" >/dev/null
[ -x "$scratch/bin/godmode" ]
cmp "$scratch/artifact/godmode" "$scratch/bin/godmode"
if sh "$repo/install.sh" --binary "$scratch/artifact/godmode" --sha256 "$digest" --bin-dir "$scratch/bin" 2>/dev/null; then
    echo 'existing binary was overwritten without --force' >&2; exit 1
fi
cmp "$scratch/artifact/godmode" "$scratch/bin/godmode"
if sh "$repo/install.sh" --binary "$scratch/artifact/godmode" --sha256 0000000000000000000000000000000000000000000000000000000000000000 --bin-dir "$scratch/bad" 2>/dev/null; then
    echo 'bad digest was accepted' >&2; exit 1
fi
[ ! -e "$scratch/bad" ]
printf '%s\n' '#!/bin/sh' 'printf "synthetic-version-two\n"' > "$scratch/artifact/godmode"
digest=$(shasum -a 256 < "$scratch/artifact/godmode" | awk '{print $1}')
sh "$repo/install.sh" --binary "$scratch/artifact/godmode" --sha256 "$digest" --bin-dir "$scratch/bin" --force >/dev/null
cmp "$scratch/artifact/godmode" "$scratch/bin/godmode"
mkdir "$scratch/link-bin"
ln -s "$scratch/nonexistent" "$scratch/link-bin/godmode"
if sh "$repo/install.sh" --binary "$scratch/artifact/godmode" --sha256 "$digest" --bin-dir "$scratch/link-bin" --force 2>/dev/null; then
    echo 'symlink destination was accepted' >&2; exit 1
fi
[ -L "$scratch/link-bin/godmode" ]
[ ! -e "$scratch/nonexistent" ]
tar -czf "$scratch/godmode-test.tar.gz" -C "$scratch/artifact" godmode
archive_digest=$(shasum -a 256 < "$scratch/godmode-test.tar.gz" | awk '{print $1}')
printf '%s  %s\n' "$archive_digest" 'godmode-test.tar.gz' > "$scratch/SHA256SUMS"
sh "$repo/install.sh" --archive "$scratch/godmode-test.tar.gz" --checksum "$scratch/SHA256SUMS" --bin-dir "$scratch/archive-bin" >/dev/null
cmp "$scratch/artifact/godmode" "$scratch/archive-bin/godmode"
cat "$scratch/SHA256SUMS" "$scratch/SHA256SUMS" > "$scratch/duplicates"
if sh "$repo/install.sh" --archive "$scratch/godmode-test.tar.gz" --checksum "$scratch/duplicates" --bin-dir "$scratch/duplicate-bin" 2>/dev/null; then
    echo 'ambiguous checksums were accepted' >&2; exit 1
fi
[ ! -e "$scratch/duplicate-bin" ]
printf '%s\n' 'Installer tests passed (binary/archive, checksum, overwrite, symlink, footprint).'
