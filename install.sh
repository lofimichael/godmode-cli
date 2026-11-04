#!/bin/sh
# godmode-installer-format: 1
# Install a native release; the installed copy is the godmodeup command.
# Explicit local-artifact modes remain offline. Never reads stored credentials.
set -eu
umask 077

usage() {
    cat <<'USAGE'
Usage:
  sh install.sh [--version vX.Y.Z] [--home DIR | --bin-dir DIR] [--path] [--no-setup]
  godmodeup [--version vX.Y.Z] [--setup] [--path]
  sh install.sh --archive PATH --checksum SHA256SUMS [--home DIR | --bin-dir DIR] [--setup]
  sh install.sh --binary PATH --sha256 HEX [--home DIR | --bin-dir DIR] [--setup]

With no artifact flags, download the newest compatible native GitHub release,
verify its checksum, install it and start interactive masked setup. An existing
GitHub CLI login can access private/draft releases; public releases use HTTPS.
Default destination: ~/.godmode/bin/godmode (or $GODMODE_HOME/bin/godmode).
--home DIR selects a home; --bin-dir DIR changes only the executable directory.
--no-setup installs only; --setup also opens setup for an offline installation.
godmodeup updates only binaries matching its install receipt; setup is opt-in.
Unknown existing binaries require --force. Symlinks are always refused.
--path adds one source line for the generated env file to your shell startup file.
Without --path, shell profiles stay unchanged. Credentials are never migrated.
USAGE
}
# Styling follows the destination descriptor, including stderr redirections.
# Copyable commands stay plain; NO_COLOR (even empty) and TERM=dumb opt out.
paint() {
    if [ -t 1 ] && [ "${NO_COLOR+x}" != x ] && [ "${TERM:-}" != dumb ] && [ "${CLICOLOR:-}" != 0 ]; then
        printf '\033[%sm%s\033[0m' "$1" "$2"
    else
        printf '%s' "$2"
    fi
}
say() { paint "$1" "$2"; printf '\n'; }
fail() { say '31' "godmode install: $*" >&2; exit 1; }
need_value() { [ "$#" -ge 2 ] && [ -n "$2" ] || fail "missing option value"; }
valid_version() {
    # grep alone accepts a valid line followed by a newline and unsafe text.
    case "$1" in *[!v0-9.]*|'') return 1 ;; esac
    printf '%s\n' "$1" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+$'
}
shell_quote() {
    printf "'"
    printf '%s' "$1" | sed "s/'/'\\\\''/g"
    printf "'"
}
setup_command() {
    shell_quote "$destination"
    if [ "$home_option" = yes ] || [ -n "${GODMODE_HOME:-}" ]; then
        printf ' --home '
        shell_quote "$godmode_home"
    fi
    printf ' %s\n' "${1:-init}"
}
tty_device() {
    # Descriptor 3 holds the caller's stdout before command substitution captures
    # descriptor 1. tty only inspects it; the wizard reopens the device for reads.
    for descriptor in 0 3 2; do
        case "$descriptor" in
            0) device=$(tty 2>/dev/null) || device= ;;
            3) device=$(tty <&3 2>/dev/null) || device= ;;
            2) device=$(tty <&2 2>/dev/null) || device= ;;
        esac
        case "$device" in
            /dev/tty|'') ;; # macOS kqueue cannot poll the controlling-TTY alias.
            /dev/*) if [ -c "$device" ]; then printf '%s\n' "$device"; return 0; fi ;;
        esac
    done
    return 1
}
hash_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum < "$1" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 < "$1" | awk '{print $1}'
    else
        fail "sha256sum or shasum is required"
    fi
}
managed_file() {
    [ -f "$receipt" ] && [ ! -L "$receipt" ] || return 1
    recorded=$(awk -v name="$2" '$1 == name { digest=$2; count++ } END { if (count != 1) exit 1; print digest }' "$receipt") || return 1
    [ "${#recorded}" -eq 64 ] || return 1
    case "$recorded" in *[!0-9a-f]*) return 1 ;; esac
    [ "$(hash_file "$1")" = "$recorded" ]
}
cleanup() {
    [ -z "$updater_staged" ] || rm -f "$updater_staged"
    [ -z "$receipt_staged" ] || rm -f "$receipt_staged"
    [ -z "$env_staged" ] || rm -f "$env_staged"
    [ -z "$backup_staged" ] || rm -f "$backup_staged"
    [ -z "$lock_dir" ] || rmdir "$lock_dir" 2>/dev/null || :
    [ -z "$staged" ] || rm -f "$staged"
    [ -z "$download_dir" ] || rm -rf "$download_dir"
}

# A piped installer only starts once its whole function definition has arrived.
main() {
archive=
binary=
checksum=
expected=
version=
setup=auto
godmode_home=${GODMODE_HOME:-${HOME:?HOME must be set}/.godmode}
bin_dir=
home_option=no
bin_option=no
force=no
update=no
path_setup=no
case "${0##*/}" in godmodeup) update=yes ;; esac
download_dir=
updater_staged=
receipt_staged=
env_staged=
backup_staged=
lock_dir=
staged=
repository=lofimichael/godmode-cli
previous_command=$(command -v godmode 2>/dev/null || :)
while [ "$#" -gt 0 ]; do
    case "$1" in
        --archive) need_value "$@"; archive=$2; shift 2 ;;
        --binary) need_value "$@"; binary=$2; shift 2 ;;
        --checksum) need_value "$@"; checksum=$2; shift 2 ;;
        --sha256) need_value "$@"; expected=$2; shift 2 ;;
        --version) need_value "$@"; version=$2; shift 2 ;;
        --home) need_value "$@"; godmode_home=$2; home_option=yes; shift 2 ;;
        --bin-dir) need_value "$@"; bin_dir=$2; bin_option=yes; shift 2 ;;
        --setup) setup=yes; shift ;;
        --no-setup) setup=no; shift ;;
        --force) force=yes; shift ;;
        --update) update=yes; shift ;;
        --path) path_setup=yes; shift ;;
        -h|--help) usage; exit 0 ;;
        *) fail "unknown option; use --help" ;;
    esac
done

[ "$home_option:$bin_option" != yes:yes ] || fail "--home and --bin-dir cannot be combined"
case "$godmode_home" in /*) ;; *) godmode_home=$PWD/$godmode_home ;; esac
if [ "$bin_option:$home_option:$update" = no:no:yes ]; then
    bin_dir=$(CDPATH='' cd -L "$(dirname "$0")" && pwd -L)
    bin_option=yes
    # The installed command remains attached to its own home after PATH changes.
    case "$bin_dir" in
        */bin)
            godmode_home=${bin_dir%/bin}
            [ "$godmode_home" = "$HOME/.godmode" ] || home_option=yes
            ;;
    esac
fi
[ "$bin_option" = yes ] || bin_dir=$godmode_home/bin
case "$bin_dir" in /*) ;; *) bin_dir=$PWD/$bin_dir ;; esac
[ ! -L "$bin_dir" ] || fail "destination directory must not be a symlink"
destination=$bin_dir/godmode
updater=$bin_dir/godmodeup
receipt=$bin_dir/.godmode-install-receipt
[ ! -L "$destination" ] || fail "destination is a symlink; nothing installed"
[ ! -L "$updater" ] || fail "updater is a symlink; nothing installed"
[ ! -L "$receipt" ] || fail "install receipt is a symlink; nothing installed"
[ ! -e "$receipt" ] || [ -f "$receipt" ] || fail "install receipt is not a regular file"
existing=no
if [ -e "$destination" ]; then
    existing=yes
    [ -f "$destination" ] || fail "destination is not a regular file"
    if [ "$force" != yes ] && { [ "$update" != yes ] || ! managed_file "$destination" godmode; }; then
        say '31' "godmode install: $destination already exists; nothing replaced." >&2
        say '36' 'Start the existing installation with:' >&2
        printf '  ' >&2
        setup_command init >&2
        fail "use godmodeup for managed updates; an unknown or modified binary requires explicit --force"
    fi
fi
existing_updater=no
if [ -e "$updater" ]; then
    existing_updater=yes
    [ -f "$updater" ] || fail "updater is not a regular file"
    if [ "$force" != yes ] && ! managed_file "$updater" godmodeup; then
        fail "godmodeup is not the recorded updater; nothing replaced (use --force to adopt it explicitly)"
    fi
fi
# PATH setup is a separate, explicit action. Never source the existing profile.
env_file=$godmode_home/env
case "$bin_dir" in *:*) [ "$path_setup" != yes ] || fail "a bin directory containing a colon cannot be added to PATH" ;; esac
profile=
profile_extra=
if [ "$path_setup" = yes ]; then
    shell_name=${SHELL:-sh}
    case "${shell_name##*/}" in
        zsh) profile=${ZDOTDIR:-$HOME}/.zshrc ;;
        bash)
            profile=$HOME/.bashrc
            if [ -e "$HOME/.bash_profile" ]; then profile_extra=$HOME/.bash_profile
            elif [ -e "$HOME/.bash_login" ]; then profile_extra=$HOME/.bash_login
            else profile_extra=$HOME/.profile
            fi
            ;;
        sh|dash|ksh) profile=$HOME/.profile ;;
        *) fail "unknown shell; omit --path and source the generated env file in your shell" ;;
    esac
    for candidate in "$profile" "$profile_extra"; do
        [ -n "$candidate" ] || continue
        [ ! -L "$candidate" ] || fail "shell startup file is a symlink; add the env source line yourself"
        [ ! -e "$candidate" ] || [ -f "$candidate" ] || fail "shell startup file is not a regular file"
    done
fi

trap cleanup 0
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
if [ -z "$archive$binary$checksum$expected" ]; then
    [ "$setup" != auto ] || { if [ "$update" = yes ]; then setup=no; else setup=yes; fi; }
    if [ -n "$version" ]; then
        valid_version "$version" || fail "version must be vX.Y.Z"
    fi
    case "$(uname -s):$(uname -m)" in
        Darwin:arm64|Darwin:aarch64) target=aarch64-apple-darwin ;;
        Darwin:x86_64) target=x86_64-apple-darwin ;;
        Linux:x86_64) target=x86_64-unknown-linux-musl ;;
        Linux:aarch64|Linux:arm64) target=aarch64-unknown-linux-musl ;;
        *) fail "no prebuilt release target for this operating system/architecture" ;;
    esac
    download_dir=$(mktemp -d "${TMPDIR:-/tmp}/godmode-download.XXXXXX")
    transport=curl
    if command -v gh >/dev/null 2>&1; then
        # gh owns authentication. No token is requested, captured or logged here.
        query='sort_by(.created_at) | reverse | map(select(.prerelease == false)) | map(select(.tag_name | test("^v[0-9]+\\.[0-9]+\\.[0-9]+$")))'
        if [ -n "$version" ]; then
            query="$query | map(select(.tag_name == \"$version\"))"
        fi
        query="$query | map(. as \$r | select(any(.assets[]; .name == (\"godmode-\" + \$r.tag_name + \"-$target.tar.gz\"))) | select(any(.assets[]; .name == \"SHA256SUMS\"))) | .[0].tag_name // empty"
        if selected=$(gh api --hostname github.com "repos/$repository/releases?per_page=100" --jq "$query" 2>/dev/null); then
            [ -n "$selected" ] || fail "no compatible $target release archive and checksum are available to your GitHub login"
            version=$selected
            transport=gh
        fi
    fi
    if [ "$transport" = curl ]; then
        command -v curl >/dev/null 2>&1 || fail "curl is required for public downloads; private releases need an authenticated GitHub CLI"
        if [ -z "$version" ]; then
            latest=$(curl --disable --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --tlsv1.2 --output /dev/null --write-out '%{url_effective}' "https://github.com/$repository/releases/latest" 2>/dev/null) || fail "cannot find a public release; for private releases, sign in with gh auth login first"
            prefix="https://github.com/$repository/releases/tag/"
            case "$latest" in "$prefix"*) version=${latest#"$prefix"} ;; *) fail "GitHub did not return a release tag" ;; esac
        fi
    fi
    # Validate remote metadata before it can become a URL, pattern or filename.
    valid_version "$version" || fail "release tag must be vX.Y.Z"
    name=godmode-$version-$target.tar.gz
    say '36' "Downloading Godmode $version for $target..."
    if [ "$transport" = gh ]; then
        gh release download "$version" --repo "github.com/$repository" --pattern "$name" --pattern SHA256SUMS --dir "$download_dir" >/dev/null 2>&1 || fail "cannot download the release archive and checksum; nothing installed"
    else
        base=https://github.com/$repository/releases/download/$version
        curl --disable --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --tlsv1.2 --output "$download_dir/$name" "$base/$name" 2>/dev/null || fail "no downloadable $target archive for $version; nothing installed"
        curl --disable --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --tlsv1.2 --output "$download_dir/SHA256SUMS" "$base/SHA256SUMS" 2>/dev/null || fail "cannot download the release checksum; nothing installed"
    fi
    archive=$download_dir/$name
    checksum=$download_dir/SHA256SUMS
else
    [ -z "$version" ] || fail "--version cannot be combined with local artifact flags"
    [ "$setup" != auto ] || setup=no
fi

if [ -n "$archive" ]; then
    [ -z "$binary" ] && [ -z "$expected" ] && [ -n "$checksum" ] || fail "use --archive with --checksum only"
    [ -f "$archive" ] && [ -f "$checksum" ] || fail "archive or checksum file is missing"
    artifact=$archive
    expected=$(awk -v name="$(basename "$archive")" '
        { filename=$2; sub(/^\*/, "", filename) }
        filename == name { digest=$1; matches++ }
        END { if (matches != 1) exit 1; print digest }
    ' "$checksum") || fail "checksum file must contain exactly one entry for the archive"
else
    [ -n "$binary" ] && [ -n "$expected" ] && [ -z "$checksum" ] || fail "use --binary with --sha256, or --archive with --checksum"
    [ -f "$binary" ] || fail "binary file is missing"
    artifact=$binary
fi
case "$expected" in *[!0-9a-fA-F]*|'') fail "invalid SHA-256 digest" ;; esac
[ "${#expected}" -eq 64 ] || fail "invalid SHA-256 digest"
actual=$(hash_file "$artifact")
expected=$(printf '%s' "$expected" | tr 'A-F' 'a-f')
[ "$actual" = "$expected" ] || fail "checksum mismatch; nothing installed"

mkdir -p "$bin_dir"
lock_candidate=$bin_dir/.godmode-install-lock
mkdir "$lock_candidate" 2>/dev/null || fail "another installation is in progress ($lock_candidate)"
lock_dir=$lock_candidate
# Recheck under the lock before changing a managed executable.
[ ! -L "$destination" ] && [ ! -L "$updater" ] && [ ! -L "$receipt" ] || fail "an install destination became a symlink"
if [ "$existing" = yes ] && [ "$force" != yes ]; then
    managed_file "$destination" godmode || fail "binary changed during download; nothing replaced"
fi
if [ "$force" != yes ]; then
    if [ "$existing_updater" = yes ]; then
        managed_file "$updater" godmodeup || fail "updater changed during download; nothing replaced"
    else
        [ ! -e "$updater" ] || fail "updater appeared during download; nothing replaced"
    fi
fi
staged=$(mktemp "$bin_dir/.godmode-install.XXXXXX")
updater_staged=$(mktemp "$bin_dir/.godmode-updater.XXXXXX")
if [ -n "$archive" ]; then
    # Stream only these members into files we created; never extract archive paths.
    tar -xOzf "$archive" godmode > "$staged" || fail "archive must contain a root-level godmode binary"
    tar -xOzf "$archive" install.sh > "$updater_staged" 2>/dev/null || :
else
    cat "$binary" > "$staged"
fi
# Current archives carry the updater. Offline binaries and older archives can
# reuse this script when it was run from a file, keeping old releases installable.
if ! grep -qx '# godmode-installer-format: 1' "$updater_staged"; then
    if [ -f "$0" ] && grep -qx '# godmode-installer-format: 1' "$0"; then
        cat "$0" > "$updater_staged"
    else
        # A legacy archive without an updater is still a valid binary-only install.
        : > "$updater_staged"
    fi
fi
[ -s "$staged" ] || fail "binary is empty"
chmod 755 "$staged"
if [ -s "$updater_staged" ]; then
    sh -n "$updater_staged" || fail "release updater is not valid shell"
    chmod 755 "$updater_staged"
fi
receipt_staged=$(mktemp "$bin_dir/.godmode-receipt.XXXXXX")
printf 'format 1\ngodmode %s\n' "$(hash_file "$staged")" > "$receipt_staged"
if [ -s "$updater_staged" ]; then
    printf 'godmodeup %s\n' "$(hash_file "$updater_staged")" >> "$receipt_staged"
fi
# Do not add files outside an explicitly selected --bin-dir unless requested.
if [ "$bin_option" != yes ] || [ "$path_setup" = yes ]; then
    case "$bin_dir" in
        *:*) : ;; # A colon cannot be represented as a single PATH component.
        *)
            [ ! -L "$env_file" ] || fail "env file is a symlink; nothing replaced"
            [ ! -e "$env_file" ] || [ -f "$env_file" ] || fail "env file is not a regular file"
            mkdir -p "$godmode_home"
            env_staged=$(mktemp "$godmode_home/.godmode-env.XXXXXX")
            {
                printf '%s\n' '# Godmode PATH. Generated by godmodeup.'
                # shellcheck disable=SC2016 # Write literal syntax for the sourced file.
                printf 'case ":${PATH:-}:" in\n  *:'
                shell_quote "$bin_dir"
                printf ':*) ;;\n  *) PATH='
                shell_quote "$bin_dir"
                # shellcheck disable=SC2016 # Write literal syntax for the sourced file.
                printf '"${PATH:+:$PATH}"; export PATH ;;\nesac\n'
            } > "$env_staged"
            if [ -e "$env_file" ]; then
                cmp -s "$env_file" "$env_staged" || fail "existing env file differs; nothing replaced"
            fi
            ;;
    esac
fi
backup=$bin_dir/godmode.previous
if [ "$existing" = yes ]; then
    [ ! -L "$backup" ] || fail "backup is a symlink; nothing replaced"
    if [ -e "$backup" ]; then
        if [ ! -f "$backup" ] || ! managed_file "$backup" previous; then
            fail "previous backup is not recorded; nothing replaced"
        fi
    fi
    if ! cmp -s "$destination" "$staged"; then
        backup_staged=$(mktemp "$bin_dir/.godmode-previous.XXXXXX")
        cp "$destination" "$backup_staged"
        chmod 755 "$backup_staged"
        printf 'previous %s\n' "$(hash_file "$backup_staged")" >> "$receipt_staged"
    elif [ -f "$backup" ]; then
        printf 'previous %s\n' "$(hash_file "$backup")" >> "$receipt_staged"
    fi
fi

# Everything is staged and verified before changing executables. Each rename is
# atomic. The previous executable remains usable if a later write is interrupted.
if [ "$existing" = yes ]; then
    if [ -n "$backup_staged" ]; then
        mv -f "$backup_staged" "$backup"
        backup_staged=
    fi
    mv -f "$staged" "$destination"
else
    ln "$staged" "$destination" || fail "destination appeared during install; nothing replaced"
fi
if [ -s "$updater_staged" ]; then
    if [ "$existing_updater" = yes ] || [ "$force" = yes ]; then
        mv -f "$updater_staged" "$updater"
        updater_staged=
    else
        ln "$updater_staged" "$updater" || fail "updater appeared during install; nothing replaced"
    fi
fi
if [ -n "$env_staged" ]; then
    if [ ! -e "$env_file" ]; then
        ln "$env_staged" "$env_file" || fail "env file appeared during install"
    fi
fi
mv -f "$receipt_staged" "$receipt"
receipt_staged=
if [ "$path_setup" = yes ]; then
    source_line="[ ! -f $(shell_quote "$env_file") ] || . $(shell_quote "$env_file")"
    for candidate in "$profile" "$profile_extra"; do
        [ -n "$candidate" ] || continue
        [ ! -L "$candidate" ] || fail "shell startup file became a symlink; profile unchanged"
        [ ! -e "$candidate" ] || [ -f "$candidate" ] || fail "shell startup file is no longer a regular file"
        if [ ! -f "$candidate" ] || ! grep -Fqx "$source_line" "$candidate"; then
            if [ -f "$candidate" ]; then
                profile_backup=$(mktemp "$candidate.godmode-backup.XXXXXX")
                cp -p "$candidate" "$profile_backup"
            fi
            mkdir -p "$(dirname "$candidate")"
            printf '\n# Godmode\n%s\n' "$source_line" >> "$candidate"
            printf 'Added Godmode to %s\n' "$candidate"
        fi
    done
fi
paint '32' 'Installed '
paint '0' "$destination"
printf '\n'
if [ "$path_setup" = yes ]; then
    printf '%s\n' 'Configuration and credentials unchanged.'
else
    printf '%s\n' 'No configuration, credentials or shell profile changed.'
fi
if [ -x "$updater" ]; then
    printf 'Update with: '
    shell_quote "$updater"
    printf '\n'
fi
if [ -n "$previous_command" ] && [ "$previous_command" != "$destination" ]; then
    printf 'Another godmode command was already available: '
    paint '0' "$previous_command"
    printf '\n'
    printf '%s\n' 'It was not changed. Use the full path below to select this installation.'
fi
printf '\n'
if [ "$update" = yes ]; then
    say '36' 'Run:'
    printf '  '
    shell_quote "$destination"
    if [ "$home_option" = yes ]; then
        printf ' --home '
        shell_quote "$godmode_home"
    fi
    printf '\n'
else
    say '36' 'Start interactive setup:'
    printf '  '
    setup_command
fi
case ":${PATH:-}:" in
    *:"$bin_dir":*) ;;
    *)
        case "$bin_dir" in
            *:*) printf '\nThis directory contains a colon; use the full executable path instead of adding it to PATH.\n' ;;
            *)
                printf '\n'
                say '36' 'For this shell, add the bin directory to PATH:'
                if [ -f "$env_file" ]; then
                    printf '  . '
                    shell_quote "$env_file"
                    printf '\n'
                else
                    printf '  export PATH='
                    shell_quote "$bin_dir"
                    # shellcheck disable=SC2016 # Print a command for the user's shell.
                    printf ':"$PATH"\n'
                fi
                [ "$path_setup" = yes ] || printf '%s\n' 'Use --path to add it to your shell startup file.'
                ;;
        esac
        ;;
esac
if [ "$setup" = yes ]; then
    exec 3>&1
    setup_tty=$(tty_device) || setup_tty=
    exec 3>&-
    if [ -n "$setup_tty" ]; then
        printf '\n'
        say '36' 'Starting interactive setup...'
        if [ "$home_option" = yes ] || [ -n "${GODMODE_HOME:-}" ]; then
            # shellcheck disable=SC2094 # A character device is intentionally opened both ways.
            "$destination" --home "$godmode_home" init <"$setup_tty" >"$setup_tty" 2>&1
        else
            # shellcheck disable=SC2094 # A character device is intentionally opened both ways.
            "$destination" init <"$setup_tty" >"$setup_tty" 2>&1
        fi
    else
        printf '\nNo usable terminal device was found; run the setup command above in a terminal.\n'
    fi
fi
}
main "$@"
