#!/bin/sh
# godmode-installer-format: 1
# Install the CLI; the installed copy of this script is the godmodeup command.
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

With no artifact flags, download the newest compatible GitHub release,
verify its checksum, install it and start interactive masked setup. Python 3.9+
is required; no Python packages are installed. An existing
GitHub CLI login can access private/draft releases; public releases use HTTPS.
Default destination: ~/.godmode/bin/godmode (or $GODMODE_HOME/bin/godmode).
--home DIR selects a home; --bin-dir DIR changes only the executable directory.
--no-setup installs only; --setup also opens setup for an offline installation.
godmodeup updates only files matching its install receipt and downloads nothing
when the installed version is current; setup is opt-in.
Unknown existing files require --force. Symlinks are always refused.
--path adds one source line for the generated env file to ~/.zshenv (zsh),
~/.bashrc and the bash login file, or ~/.profile (sh, dash, ksh). Other shells
are left unchanged. Without --path, shell startup files stay unchanged.
Credentials are never migrated.
USAGE
}
# Styling follows the destination descriptor, including stderr redirections.
# Copyable commands stay plain; NO_COLOR (even empty), CLICOLOR=0 and an empty
# or dumb TERM opt out, as in the CLI.
paint() {
    if [ -t 1 ] && [ "${NO_COLOR+x}" != x ] && [ "${TERM:-dumb}" != dumb ] && [ "${CLICOLOR:-}" != 0 ]; then
        printf '\033[%sm%s\033[0m' "$1" "$2"
    else
        printf '%s' "$2"
    fi
}
say() { paint "$1" "$2"; printf '\n'; }
# The CLI's glyph rule: Unicode for UTF-8 locales and the C locale (which Python
# reads as UTF-8), never on the Linux console. The file itself stays ASCII.
unicode() {
    [ "${TERM:-}" != linux ] || return 1
    case "${LC_ALL:-${LC_CTYPE:-${LANG:-C}}}" in
        C|POSIX|*[Uu][Tt][Ff]-8*|*[Uu][Tt][Ff]8*) return 0 ;;
    esac
    return 1
}
# Progress and notes share the CLI's two-column gutter; errors stay flush left.
check() {
    if unicode; then mark=$(printf '\342\234\223'); else mark=+; fi
    printf '  '
    paint '32' "$mark"
    printf ' %s\n' "$1"
}
# Show a path as it would be typed: ~ for HOME, quoted only when a shell needs it.
show_path() {
    shown_prefix=
    shown_rest=$1
    shown_home=${HOME%/}
    if [ -n "$shown_home" ]; then
        # shellcheck disable=SC2088 # The ~ is printed for the reader's shell to expand.
        case "$1" in
            "$shown_home") printf '~'; return 0 ;;
            "$shown_home"/*) shown_prefix='~/'; shown_rest=${1#"$shown_home"/} ;;
        esac
    fi
    case "$shown_rest" in
        ''|*[!A-Za-z0-9_./+:@%,=-]*) printf '%s' "$shown_prefix"; shell_quote "$shown_rest" ;;
        *) printf '%s%s' "$shown_prefix" "$shown_rest" ;;
    esac
}
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
# The command a person types to open Godmode. It is the bare name unless another
# godmode would run instead or the directory cannot be on PATH.
godmode_command() {
    if [ "$direct" = yes ]; then show_path "$destination"; else printf 'godmode'; fi
    if { [ "$home_option" = yes ] || [ -n "${GODMODE_HOME:-}" ]; } && [ "$godmode_home" != "${HOME%/}/.godmode" ]; then
        printf ' --home '
        show_path "$godmode_home"
    fi
}
# Prints X.Y.Z for a recorded executable that reports a version, otherwise nothing.
installed_version() {
    [ "$existing" = yes ] && managed_file "$destination" godmode || return 0
    reported=$("$destination" --version </dev/null 2>/dev/null) || return 0
    case "$reported" in "godmode "*) reported=${reported#godmode } ;; *) return 0 ;; esac
    if valid_version "v$reported"; then printf '%s' "$reported"; fi
}
path_note() {
    case ":${PATH:-}:" in *:"$bin_dir":*) return 0 ;; esac
    case "$bin_dir" in
        *:*) printf '  %s\n' 'A directory with a colon cannot be on PATH; run godmode by its full path.'; return 0 ;;
    esac
    if [ -n "$startup" ]; then
        printf '  Open a new terminal, or run:  . %s\n' "$(show_path "$env_file")"
        return 0
    fi
    printf "  Add %s to PATH in your shell's startup file.\n" "$(show_path "$bin_dir")"
    if [ "$env_ready" = yes ] && [ "$shell_known" = yes ]; then
        printf '  For this shell, run:  . %s\n' "$(show_path "$env_file")"
    fi
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
home_record=automatic
force=no
update=no
path_setup=no
case "${0##*/}" in godmodeup) update=yes ;; esac
download_dir=
updater_staged=
receipt_staged=
env_staged=
env_ready=no
backup_staged=
lock_dir=
staged=
release_url=
setup_tty=
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
if ! command -v python3 >/dev/null 2>&1 || ! python3 -I -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
    fail "Python 3.9 or later is required; nothing installed"
fi
case "$godmode_home" in /*) ;; *) godmode_home=$PWD/$godmode_home ;; esac
if [ "$bin_option" = no ] && { [ "$home_option" = yes ] || [ -n "${GODMODE_HOME:-}" ]; }; then
    home_record=explicit
fi
if [ "$bin_option:$home_option:$update" = no:no:yes ]; then
    bin_dir=$(CDPATH='' cd -L "$(dirname "$0")" && pwd -L)
    bin_option=yes
    home_record=automatic
    # --bin-dir never selects a configuration home, even when it ends in /bin.
    # Only a recorded --home (or GODMODE_HOME) preserves an explicit selection.
    if [ -f "$bin_dir/.godmode-install-receipt" ] && [ ! -L "$bin_dir/.godmode-install-receipt" ]; then
        recorded_home=$(awk '$1 == "home" { value=$2; count++ } END { if (count == 1) print value }' "$bin_dir/.godmode-install-receipt")
        if [ "$recorded_home" = explicit ]; then
            case "$bin_dir" in
                */bin) godmode_home=${bin_dir%/bin}; home_option=yes; home_record=explicit ;;
            esac
        elif [ -z "$recorded_home" ] && [ "$bin_dir" != "$godmode_home/bin" ]; then
            printf '  '
            say '33' 'Older install receipt: using normal configuration discovery. Select a home with godmode --home DIR if needed.'
        fi
    fi
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
shadow=
[ -z "$previous_command" ] || [ "$previous_command" = "$destination" ] || shadow=$previous_command
direct=no
[ -z "$shadow" ] || direct=yes
case "$bin_dir" in *:*) direct=yes ;; esac
existing=no
if [ -e "$destination" ]; then
    existing=yes
    [ -f "$destination" ] || fail "destination is not a regular file"
    if [ "$force" != yes ] && { [ "$update" != yes ] || ! managed_file "$destination" godmode; }; then
        if managed_file "$destination" godmode; then
            say '31' "godmode install: $(show_path "$destination") already exists; nothing replaced." >&2
            printf 'Run %s to set up, or godmodeup to update.\n' "$(godmode_command)" >&2
        else
            say '31' "godmode install: $(show_path "$destination") was changed or installed another way; nothing replaced." >&2
            printf '%s\n' 'Use --force to replace it.' >&2
        fi
        exit 1
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
# PATH setup is a separate, explicit action. Never source an existing startup file.
env_file=$godmode_home/env
case "$bin_dir" in *:*) [ "$path_setup" != yes ] || fail "a bin directory containing a colon cannot be added to PATH" ;; esac
# Every zsh reads .zshenv, including agents' non-interactive shells. An existing
# .zshrc line from an older install stays as it is. Other shells get a note.
startup=
startup_extra=
shell_name=${SHELL:-sh}
shell_known=yes
case "${shell_name##*/}" in
    zsh) startup=${ZDOTDIR:-$HOME}/.zshenv ;;
    bash)
        startup=$HOME/.bashrc
        if [ -e "$HOME/.bash_profile" ]; then startup_extra=$HOME/.bash_profile
        elif [ -e "$HOME/.bash_login" ]; then startup_extra=$HOME/.bash_login
        else startup_extra=$HOME/.profile
        fi
        ;;
    sh|dash|ksh) startup=$HOME/.profile ;;
    *) shell_known=no ;;
esac
if [ "$path_setup" = yes ]; then
    for candidate in "$startup" "$startup_extra"; do
        [ -n "$candidate" ] || continue
        [ ! -L "$candidate" ] || fail "shell startup file is a symlink; add the env source line yourself"
        [ ! -e "$candidate" ] || [ -f "$candidate" ] || fail "shell startup file is not a regular file"
    done
else
    startup=
    startup_extra=
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
    # Native releases take priority. Older portable Python releases remain installable.
    case "$(uname -s):$(uname -m)" in
        Darwin:arm64|Darwin:aarch64) target=aarch64-apple-darwin ;;
        Darwin:x86_64) target=x86_64-apple-darwin ;;
        Linux:x86_64) target=x86_64-unknown-linux-musl ;;
        Linux:aarch64|Linux:arm64) target=aarch64-unknown-linux-musl ;;
        Darwin:*|Linux:*) target=unix ;;
        *) fail "Godmode supports macOS and Linux" ;;
    esac
    transport=curl
    if command -v gh >/dev/null 2>&1; then
        # gh owns authentication. No token is requested, captured or logged here.
        query='sort_by(.created_at) | reverse | map(select(.prerelease == false)) | map(select(.tag_name | test("^v[0-9]+\\.[0-9]+\\.[0-9]+$")))'
        if [ -n "$version" ]; then
            query="$query | map(select(.tag_name == \"$version\"))"
        fi
        query="$query | map(. as \$r | select(any(.assets[]; .name == (\"godmode-\" + \$r.tag_name + \"-unix.tar.gz\") or .name == (\"godmode-\" + \$r.tag_name + \"-$target.tar.gz\"))) | select(any(.assets[]; .name == \"SHA256SUMS\"))) | .[0].tag_name // empty"
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
    release_url=https://github.com/$repository/releases/tag/$version
    installed=
    [ "$update" != yes ] || installed=$(installed_version)
    # An explicit --force, --setup or --path still runs in full on the same version.
    if [ "$installed" = "${version#v}" ] && [ "$force:$setup:$path_setup" = no:no:no ]; then
        printf '  Godmode %s is up to date.\n' "$installed"
        exit 0
    fi
    if [ -n "$installed" ] && [ "$installed" != "${version#v}" ]; then
        if unicode; then arrow=$(printf '\342\206\222'); else arrow='->'; fi
        printf '  Godmode %s %s %s\n' "$installed" "$arrow" "${version#v}"
    else
        printf '  Downloading Godmode %s\n' "${version#v}"
    fi
    download_dir=$(mktemp -d "${TMPDIR:-/tmp}/godmode-download.XXXXXX")
    fetch_archive() {
        name=$1
        if [ "$transport" = gh ]; then
            gh release download "$version" --repo "github.com/$repository" --pattern "$name" --pattern SHA256SUMS --dir "$download_dir" >/dev/null 2>&1
        else
            base=https://github.com/$repository/releases/download/$version
            curl --disable --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --tlsv1.2 --output "$download_dir/$name" "$base/$name" 2>/dev/null &&
            curl --disable --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --tlsv1.2 --output "$download_dir/SHA256SUMS" "$base/SHA256SUMS" 2>/dev/null
        fi
    }
    if ! fetch_archive "godmode-$version-$target.tar.gz"; then
        [ "$target" != unix ] || fail "no compatible archive for $version on this CPU; nothing installed"
        rm -f "$download_dir/SHA256SUMS"
        fetch_archive "godmode-$version-unix.tar.gz" || fail "cannot download the release archive and checksum; nothing installed"
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
printf 'format 1\nhome %s\ngodmode %s\n' "$home_record" "$(hash_file "$staged")" > "$receipt_staged"
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
    env_ready=yes
fi
mv -f "$receipt_staged" "$receipt"
receipt_staged=
if [ "$update" = yes ]; then
    check "Updated $(show_path "$destination")"
    [ -z "$release_url" ] || printf '  Changes: %s\n' "$release_url"
else
    check "Installed $(show_path "$destination")"
fi
if [ -n "$startup" ]; then
    source_line="[ ! -f $(shell_quote "$env_file") ] || . $(shell_quote "$env_file")"
    added=
    for candidate in "$startup" "$startup_extra"; do
        [ -n "$candidate" ] || continue
        [ ! -L "$candidate" ] || fail "shell startup file became a symlink; it was not changed"
        [ ! -e "$candidate" ] || [ -f "$candidate" ] || fail "shell startup file is no longer a regular file"
        if [ ! -f "$candidate" ] || ! grep -Fqx "$source_line" "$candidate"; then
            if [ -f "$candidate" ]; then
                startup_backup=$(mktemp "$candidate.godmode-backup.XXXXXX")
                cp -p "$candidate" "$startup_backup"
            fi
            mkdir -p "$(dirname "$candidate")"
            printf '\n# Godmode\n%s\n' "$source_line" >> "$candidate"
            added=${added:+$added and }$(show_path "$candidate")
        fi
    done
    [ -z "$added" ] || check "Added $(show_path "$bin_dir") to PATH in $added"
fi
if [ "$setup" = yes ]; then
    exec 3>&1
    setup_tty=$(tty_device) || setup_tty=
    exec 3>&-
fi
if [ -n "$setup_tty" ]; then
    # The install is complete. Leaving setup early (Esc, Ctrl-C) does not undo it.
    trap : INT
    if [ "$home_option" = yes ] || [ -n "${GODMODE_HOME:-}" ]; then
        # shellcheck disable=SC2094 # A character device is intentionally opened both ways.
        "$destination" --home "$godmode_home" init <"$setup_tty" >"$setup_tty" 2>&1 || :
    else
        # shellcheck disable=SC2094 # A character device is intentionally opened both ways.
        "$destination" init <"$setup_tty" >"$setup_tty" 2>&1 || :
    fi
    trap 'exit 130' INT
fi
[ -z "$shadow" ] || printf '  Another godmode is on PATH at %s; it was not changed.\n' "$(show_path "$shadow")"
if [ "$update" != yes ] || [ "$path_setup" = yes ]; then
    path_note
fi
if [ -z "$setup_tty" ]; then
    if [ "$setup" = yes ]; then
        printf '  To set up, run this in a terminal:  %s\n' "$(godmode_command)"
    elif [ "$update" != yes ]; then
        printf '  To set up, run:  %s\n' "$(godmode_command)"
    fi
fi
}
main "$@"
