#!/bin/sh
# All state and executables in this test are synthetic and isolated.
set -eu
repo=$(CDPATH='' cd -P "$(dirname "$0")/.." && pwd)
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' 0 HUP INT TERM
mkdir -p "$scratch/account" "$scratch/artifacts"
printf '%s\n' '#!/bin/sh' 'printf "version-one\n"' > "$scratch/artifacts/one"
printf '%s\n' '#!/bin/sh' 'printf "version-two\n"' > "$scratch/artifacts/two"
one=$(shasum -a 256 < "$scratch/artifacts/one" | awk '{print $1}')
two=$(shasum -a 256 < "$scratch/artifacts/two" | awk '{print $1}')
export HOME="$scratch/account"
export SHELL=/bin/zsh
unset GODMODE_HOME ZDOTDIR
printf '%s\n' '# synthetic pre-existing shell config' > "$HOME/.zshrc"
cp "$HOME/.zshrc" "$scratch/profile-before"
# shellcheck disable=SC2016 # Literal hostile-looking filename, never shell code.
custom="$scratch/custom ' home "'$(touch SHOULD_NOT_EXIST) `touch ALSO_NOT_EXIST`'
sh "$repo/install.sh" --home "$custom" --binary "$scratch/artifacts/one" --sha256 "$one" --path > "$scratch/first-output"
[ -x "$custom/bin/godmodeup" ]
[ -f "$custom/env" ]
[ -f "$custom/bin/.godmode-install-receipt" ]
[ "$(grep -c '# Godmode' "$HOME/.zshrc")" -eq 1 ]
head -1 "$HOME/.zshrc" | cmp - "$scratch/profile-before"
# shellcheck disable=SC2016 # The child shell expands its own HOME and PATH.
(cd "$scratch" && sh -c '. "$HOME/.zshrc"; . "$HOME/.zshrc"; command -v godmode; command -v godmodeup') > "$scratch/resolved"
printf '%s\n' "$custom/bin/godmode" "$custom/bin/godmodeup" > "$scratch/expected"
cmp "$scratch/expected" "$scratch/resolved"
[ ! -e "$scratch/SHOULD_NOT_EXIST" ] && [ ! -e "$scratch/ALSO_NOT_EXIST" ]
printf '%s\n' 'SYNTHETIC_KEY=fixture-only' > "$custom/.env.godmode"
cp "$custom/.env.godmode" "$scratch/keys-before"
printf '%s\n' '{"business_name":"Example Studio","future":{"keep":true}}' > "$custom/profile.json"
cp "$custom/profile.json" "$scratch/facts-before"
cp "$HOME/.zshrc" "$scratch/profile-after"
cp "$custom/env" "$scratch/env-before"
# The installed updater targets its own directory, even with an unrelated HOME.
mkdir "$scratch/another-account"
HOME="$scratch/another-account" "$custom/bin/godmodeup" --binary "$scratch/artifacts/two" --sha256 "$two" > "$scratch/update-output"
cmp "$scratch/artifacts/two" "$custom/bin/godmode"
cmp "$scratch/artifacts/one" "$custom/bin/godmode.previous"
cmp "$scratch/keys-before" "$custom/.env.godmode"
cmp "$scratch/facts-before" "$custom/profile.json"
[ ! -e "$scratch/another-account/.godmode" ]
if grep -q 'Starting interactive setup' "$scratch/update-output"; then
    echo 'update started setup without request' >&2; exit 1
fi
# Repeating the same update and PATH setup does not duplicate rc lines or discard rollback.
"$custom/bin/godmodeup" --binary "$scratch/artifacts/two" --sha256 "$two" --path > /dev/null
cmp "$scratch/artifacts/one" "$custom/bin/godmode.previous"
cmp "$scratch/profile-after" "$HOME/.zshrc"
cmp "$scratch/env-before" "$custom/env"
cmp "$scratch/keys-before" "$custom/.env.godmode"
cmp "$scratch/facts-before" "$custom/profile.json"
# A bad download or manually changed executable is never replaced.
if "$custom/bin/godmodeup" --binary "$scratch/artifacts/one" --sha256 "$two" >/dev/null 2>&1; then
    echo 'bad update checksum accepted' >&2; exit 1
fi
cmp "$scratch/artifacts/two" "$custom/bin/godmode"
cp "$custom/bin/godmode" "$scratch/current"
printf '%s\n' '# hand edit' >> "$custom/bin/godmode"
cp "$custom/bin/godmode" "$scratch/hand-edit"
if "$custom/bin/godmodeup" --binary "$scratch/artifacts/one" --sha256 "$one" > /dev/null 2>&1; then
    echo 'manually changed binary accepted for update' >&2; exit 1
fi
cmp "$scratch/hand-edit" "$custom/bin/godmode"
cp "$scratch/current" "$custom/bin/godmode"
cp "$custom/bin/godmodeup" "$scratch/updater-before"
printf '%s\n' '# hand edit' >> "$custom/bin/godmodeup"
if "$custom/bin/godmodeup" --binary "$scratch/artifacts/one" --sha256 "$one" > /dev/null 2>&1; then
    echo 'manually changed updater accepted' >&2; exit 1
fi
cmp "$scratch/current" "$custom/bin/godmode"
cp "$scratch/updater-before" "$custom/bin/godmodeup"
# Unrelated env files and symlinked profiles remain untouched.
mkdir -p "$scratch/unowned-home"
printf '%s\n' 'unrelated env contents' > "$scratch/unowned-home/env"
cp "$scratch/unowned-home/env" "$scratch/unowned-env-before"
if sh "$repo/install.sh" --home "$scratch/unowned-home" --binary "$scratch/artifacts/one" --sha256 "$one" > /dev/null 2>&1; then
    echo 'unrelated env file was replaced' >&2; exit 1
fi
cmp "$scratch/unowned-env-before" "$scratch/unowned-home/env"
[ ! -e "$scratch/unowned-home/bin/godmode" ]
mkdir "$scratch/symlink-account"
ln -s "$HOME/.zshrc" "$scratch/symlink-account/.zshrc"
if HOME="$scratch/symlink-account" sh "$repo/install.sh" --home "$scratch/symlink-install" --binary "$scratch/artifacts/one" --sha256 "$one" --path >/dev/null 2>&1; then
    echo 'symlinked shell profile was accepted' >&2; exit 1
fi
[ ! -e "$scratch/symlink-install" ]
cmp "$scratch/profile-after" "$HOME/.zshrc"
# ZDOTDIR and an unset SHELL are supported without reading existing shell code.
mkdir "$scratch/zdot"
ZDOTDIR="$scratch/zdot" sh "$repo/install.sh" --home "$scratch/zdot-install" --binary "$scratch/artifacts/one" --sha256 "$one" --path > /dev/null
[ -f "$scratch/zdot/.zshrc" ]
( unset SHELL; sh "$repo/install.sh" --home "$scratch/unset-shell-install" --binary "$scratch/artifacts/one" --sha256 "$one" --path > /dev/null )
SHELL='' sh "$repo/install.sh" --home "$scratch/posix-install" --binary "$scratch/artifacts/one" --sha256 "$one" --path > /dev/null
[ -f "$HOME/.profile" ]
printf '%s\n' '# existing bash profile' > "$HOME/.bash_profile"
SHELL=/bin/bash sh "$repo/install.sh" --home "$scratch/bash-install" --binary "$scratch/artifacts/one" --sha256 "$one" --path > /dev/null
grep -q 'bash-install/env' "$HOME/.bash_profile"
grep -q 'bash-install/env' "$HOME/.bashrc"
# Concurrency lock prevents mutations and is not removed by the losing process.
mkdir "$custom/bin/.godmode-install-lock"
if "$custom/bin/godmodeup" --binary "$scratch/artifacts/one" --sha256 "$one" >/dev/null 2>&1; then
    echo 'concurrent install lock was ignored' >&2; exit 1
fi
[ -d "$custom/bin/.godmode-install-lock" ]
cmp "$scratch/current" "$custom/bin/godmode"
rmdir "$custom/bin/.godmode-install-lock"
printf '%s\n' 'Updater tests passed (managed updates, previous backup, checksum/refusal, env and profile preservation, quoted PATH, shell selection and concurrency).'
