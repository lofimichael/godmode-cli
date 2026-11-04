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
# The default home bin is created without initializing configuration or profiles.
mkdir -p "$scratch/home" "$scratch/old-bin"
printf '%s\n' '#!/bin/sh' 'printf "existing-godmode\n"' > "$scratch/old-bin/godmode"
chmod 755 "$scratch/old-bin/godmode"
cp "$scratch/old-bin/godmode" "$scratch/old-before"
HOME="$scratch/home" GODMODE_HOME= PATH="$scratch/old-bin:$PATH" sh "$repo/install.sh" \
    --binary "$scratch/artifact/godmode" --sha256 "$digest" > "$scratch/default-output"
[ -x "$scratch/home/.godmode/bin/godmode" ]
cmp "$scratch/artifact/godmode" "$scratch/home/.godmode/bin/godmode"
cmp "$scratch/old-before" "$scratch/old-bin/godmode"
[ ! -e "$scratch/home/.config" ]
[ ! -e "$scratch/home/.zshrc" ]
[ ! -e "$scratch/home/.profile" ]
grep -q 'Another godmode command was already available:' "$scratch/default-output"
grep -q 'Start interactive setup:' "$scratch/default-output"
grep -q 'export PATH=' "$scratch/default-output"

# A custom home is self-contained; configuration stays absent until init.
sh "$repo/install.sh" --binary "$scratch/artifact/godmode" --sha256 "$digest" \
    --home "$scratch/custom home" > "$scratch/custom-home-output"
cmp "$scratch/artifact/godmode" "$scratch/custom home/bin/godmode"
[ ! -e "$scratch/custom home/.env.godmode" ]
grep -q -- '--home ' "$scratch/custom-home-output"
GODMODE_HOME="$scratch/env-home" sh "$repo/install.sh" --binary "$scratch/artifact/godmode" \
    --sha256 "$digest" > "$scratch/env-home-output"
cmp "$scratch/artifact/godmode" "$scratch/env-home/bin/godmode"
if sh "$repo/install.sh" --binary "$scratch/artifact/godmode" --sha256 "$digest" \
    --home "$scratch/conflicting-home" --bin-dir "$scratch/conflicting-bin" 2>/dev/null; then
    echo 'conflicting home/bin options were accepted' >&2; exit 1
fi
[ ! -e "$scratch/conflicting-home" ]
[ ! -e "$scratch/conflicting-bin" ]

# The handoff commands must preserve shell metacharacters as literal filenames.
odd_dir="$scratch/space ' quote "'$(touch SHOULD_NOT_EXIST) `touch ALSO_NOT_EXIST`'
sh "$repo/install.sh" --binary "$scratch/artifact/godmode" --sha256 "$digest" \
    --bin-dir "$odd_dir" > "$scratch/quoted-output"
start_line=$(awk 'next_line { print; exit } /^Start interactive setup:/ { next_line=1 }' "$scratch/quoted-output")
[ -n "$start_line" ]
(cd "$scratch" && sh -c "$start_line") > "$scratch/started-output"
grep -q '^synthetic-version-two$' "$scratch/started-output"
path_line=$(awk '/^  export PATH=/ { sub(/^  /, ""); print; exit }' "$scratch/quoted-output")
[ -n "$path_line" ]
# Run only the command produced for this synthetic path, then inspect its value.
printf '%s\n' "$path_line" 'printf "%s\n" "$PATH"' > "$scratch/check-path.sh"
(cd "$scratch" && sh "$scratch/check-path.sh") > "$scratch/path-output"
actual_path=$(cat "$scratch/path-output")
[ "$actual_path" = "$odd_dir:$PATH" ]
[ ! -e "$scratch/SHOULD_NOT_EXIST" ]
[ ! -e "$scratch/ALSO_NOT_EXIST" ]

# PATH instructions are omitted when the directory is already a component.
PATH="$scratch/on-path:$PATH" sh "$repo/install.sh" --binary "$scratch/artifact/godmode" \
    --sha256 "$digest" --bin-dir "$scratch/on-path" > "$scratch/on-path-output"
if grep -q 'export PATH=' "$scratch/on-path-output"; then
    echo 'redundant PATH instruction for an existing component' >&2; exit 1
fi
printf '%s\n' 'Installer tests passed (binary/archive, checksum, overwrite, symlink, home/bin, home selection, PATH handoff, footprint).'
