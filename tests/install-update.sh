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
# Output must not depend on an installed godmode on the developer's PATH.
clean_path=
old_ifs=$IFS
IFS=:
set -f
for dir in $PATH; do
    [ -e "$dir/godmode" ] || clean_path=${clean_path:+$clean_path:}$dir
done
set +f
IFS=$old_ifs
export PATH="$clean_path"
export HOME="$scratch/account"
export SHELL=/bin/zsh LC_ALL=C
unset GODMODE_HOME ZDOTDIR
check=$(printf '\342\234\223')
# zsh reads .zshenv in every shell. A .zshrc line from an older install stays as it is.
printf '%s\n' '# synthetic pre-existing shell config' '' '# Godmode' "[ ! -f '/older/env' ] || . '/older/env'" > "$HOME/.zshrc"
cp "$HOME/.zshrc" "$scratch/zshrc-before"
printf '%s\n' '# synthetic pre-existing zshenv' > "$HOME/.zshenv"
cp "$HOME/.zshenv" "$scratch/profile-before"
# shellcheck disable=SC2016 # Literal hostile-looking filename, never shell code.
custom="$scratch/custom ' home "'$(touch SHOULD_NOT_EXIST) `touch ALSO_NOT_EXIST`'
sh "$repo/install.sh" --home "$custom" --binary "$scratch/artifacts/one" --sha256 "$one" --path > "$scratch/first-output"
[ -x "$custom/bin/godmodeup" ]
[ -f "$custom/env" ]
[ -f "$custom/bin/.godmode-install-receipt" ]
[ "$(grep -c '# Godmode' "$HOME/.zshenv")" -eq 1 ]
head -1 "$HOME/.zshenv" | cmp - "$scratch/profile-before"
cmp "$scratch/zshrc-before" "$HOME/.zshrc"
grep -q "^  $check Added .* to PATH in ~/.zshenv\$" "$scratch/first-output"
# shellcheck disable=SC2016 # The child shell expands its own HOME and PATH.
(cd "$scratch" && sh -c '. "$HOME/.zshenv"; . "$HOME/.zshenv"; command -v godmode; command -v godmodeup') > "$scratch/resolved"
printf '%s\n' "$custom/bin/godmode" "$custom/bin/godmodeup" > "$scratch/expected"
cmp "$scratch/expected" "$scratch/resolved"
[ ! -e "$scratch/SHOULD_NOT_EXIST" ] && [ ! -e "$scratch/ALSO_NOT_EXIST" ]
printf '%s\n' 'SYNTHETIC_KEY=fixture-only' > "$custom/.env.godmode"
cp "$custom/.env.godmode" "$scratch/keys-before"
printf '%s\n' '{"business_name":"Example Studio","future":{"keep":true}}' > "$custom/profile.json"
cp "$custom/profile.json" "$scratch/facts-before"
cp "$HOME/.zshenv" "$scratch/profile-after"
cp "$custom/env" "$scratch/env-before"
# The installed updater targets its own directory, even with an unrelated HOME.
mkdir "$scratch/another-account"
HOME="$scratch/another-account" "$custom/bin/godmodeup" --binary "$scratch/artifacts/two" --sha256 "$two" > "$scratch/update-output"
cmp "$scratch/artifacts/two" "$custom/bin/godmode"
cmp "$scratch/artifacts/one" "$custom/bin/godmode.previous"
cmp "$scratch/keys-before" "$custom/.env.godmode"
cmp "$scratch/facts-before" "$custom/profile.json"
[ ! -e "$scratch/another-account/.godmode" ]
# An offline update prints one line and starts nothing.
[ "$(wc -l < "$scratch/update-output")" -eq 1 ]
grep -q "^  $check Updated " "$scratch/update-output"
# Repeating the same update and PATH setup does not duplicate rc lines or discard rollback.
"$custom/bin/godmodeup" --binary "$scratch/artifacts/two" --sha256 "$two" --path > "$scratch/repeat-output"
cmp "$scratch/artifacts/one" "$custom/bin/godmode.previous"
cmp "$scratch/profile-after" "$HOME/.zshenv"
cmp "$scratch/zshrc-before" "$HOME/.zshrc"
if grep -q 'Added' "$scratch/repeat-output"; then
    echo 'an unchanged startup file was reported as changed' >&2; exit 1
fi
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
if "$custom/bin/godmodeup" --binary "$scratch/artifacts/one" --sha256 "$one" > "$scratch/hand-edit-output" 2>&1; then
    echo 'manually changed binary accepted for update' >&2; exit 1
fi
cmp "$scratch/hand-edit" "$custom/bin/godmode"
grep -q 'was changed or installed another way; nothing replaced\.$' "$scratch/hand-edit-output"
grep -qx 'Use --force to replace it.' "$scratch/hand-edit-output"
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
ln -s "$HOME/.zshenv" "$scratch/symlink-account/.zshenv"
if HOME="$scratch/symlink-account" sh "$repo/install.sh" --home "$scratch/symlink-install" --binary "$scratch/artifacts/one" --sha256 "$one" --path >/dev/null 2>&1; then
    echo 'symlinked shell startup file was accepted' >&2; exit 1
fi
[ ! -e "$scratch/symlink-install" ]
cmp "$scratch/profile-after" "$HOME/.zshenv"
# ZDOTDIR and an unset SHELL are supported without reading existing shell code.
mkdir "$scratch/zdot"
ZDOTDIR="$scratch/zdot" sh "$repo/install.sh" --home "$scratch/zdot-install" --binary "$scratch/artifacts/one" --sha256 "$one" --path > /dev/null
[ -f "$scratch/zdot/.zshenv" ]
[ ! -e "$scratch/zdot/.zshrc" ]
( unset SHELL; sh "$repo/install.sh" --home "$scratch/unset-shell-install" --binary "$scratch/artifacts/one" --sha256 "$one" --path > /dev/null )
SHELL='' sh "$repo/install.sh" --home "$scratch/posix-install" --binary "$scratch/artifacts/one" --sha256 "$one" --path > /dev/null
[ -f "$HOME/.profile" ]
printf '%s\n' '# existing bash profile' > "$HOME/.bash_profile"
SHELL=/bin/bash sh "$repo/install.sh" --home "$scratch/bash-install" --binary "$scratch/artifacts/one" --sha256 "$one" --path > /dev/null
grep -q 'bash-install/env' "$HOME/.bash_profile"
grep -q 'bash-install/env' "$HOME/.bashrc"
# An unrecognized shell still installs; no startup file is written, and the note says what to add.
mkdir "$scratch/fish-account"
HOME="$scratch/fish-account" SHELL=/usr/bin/fish sh "$repo/install.sh" --binary "$scratch/artifacts/one" --sha256 "$one" --path > "$scratch/fish-output"
[ "$(ls -A "$scratch/fish-account")" = .godmode ]
[ -x "$scratch/fish-account/.godmode/bin/godmode" ]
printf '  %s\n' "$check Installed ~/.godmode/bin/godmode" "Add ~/.godmode/bin to PATH in your shell's startup file." \
    'To open your loadout, run:  godmode' | cmp - "$scratch/fish-output"
# Concurrency lock prevents mutations and is not removed by the losing process.
mkdir "$custom/bin/.godmode-install-lock"
if "$custom/bin/godmodeup" --binary "$scratch/artifacts/one" --sha256 "$one" >/dev/null 2>&1; then
    echo 'concurrent install lock was ignored' >&2; exit 1
fi
[ -d "$custom/bin/.godmode-install-lock" ]
cmp "$scratch/current" "$custom/bin/godmode"
rmdir "$custom/bin/.godmode-install-lock"
# Exercise the actual native executable when supplied by the local release build.
# The destination and all profile/key fixtures remain in this disposable home.
if [ -n "${GODMODE_TEST_NATIVE_BINARY:-}" ]; then
    [ -f "$GODMODE_TEST_NATIVE_BINARY" ] && [ -x "$GODMODE_TEST_NATIVE_BINARY" ]
    native_version=$("$GODMODE_TEST_NATIVE_BINARY" --version)
    case "$native_version" in 'godmode '*) ;; *) echo 'native binary has no Godmode version' >&2; exit 1 ;; esac
    cp "$HOME/.zshenv" "$scratch/native-startup-before"
    native_digest=$(shasum -a 256 < "$GODMODE_TEST_NATIVE_BINARY" | awk '{print $1}')
    "$custom/bin/godmodeup" --binary "$GODMODE_TEST_NATIVE_BINARY" --sha256 "$native_digest" > "$scratch/native-output"
    cmp "$GODMODE_TEST_NATIVE_BINARY" "$custom/bin/godmode"
    cmp "$scratch/artifacts/two" "$custom/bin/godmode.previous"
    [ "$("$custom/bin/godmode" --version)" = "$native_version" ]
    cmp "$scratch/keys-before" "$custom/.env.godmode"
    cmp "$scratch/facts-before" "$custom/profile.json"
    cmp "$scratch/native-startup-before" "$HOME/.zshenv"
    cmp "$scratch/env-before" "$custom/env"
    printf '%s\n' 'Native updater preservation passed.'
fi
printf '%s\n' 'Updater tests passed (managed updates, previous backup, checksum/refusal, env and startup file preservation, .zshenv, unknown shells, quoted PATH and concurrency).'
