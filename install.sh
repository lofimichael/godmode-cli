#!/bin/sh
# Download a native release, verify it, install it and open masked setup.
# Explicit local-artifact modes remain offline. Never reads stored credentials.
set -eu
umask 077

usage() {
    cat <<'USAGE'
Usage:
  sh install.sh [--version vX.Y.Z] [--home DIR | --bin-dir DIR] [--no-setup]
  sh install.sh --archive PATH --checksum SHA256SUMS [--home DIR | --bin-dir DIR] [--setup]
  sh install.sh --binary PATH --sha256 HEX [--home DIR | --bin-dir DIR] [--setup]

With no artifact flags, download the newest compatible native GitHub release,
verify its checksum, install it and start interactive masked setup. An existing
GitHub CLI login can access private/draft releases; public releases use HTTPS.
Default destination: ~/.godmode/bin/godmode (or $GODMODE_HOME/bin/godmode).
--home DIR selects a home; --bin-dir DIR changes only the executable directory.
--no-setup installs only; --setup also opens setup for an offline installation.
An existing destination is refused unless --force is explicitly given. Symlinks
are always refused. The installer never migrates credentials or edits profiles.
USAGE
}
# Styling follows the destination descriptor, including stderr redirections.
# Copyable commands stay plain; NO_COLOR (even empty) and TERM=dumb opt out.
paint() {
    if [ -t 1 ] && [ "${NO_COLOR+x}" != x ] && [ "${TERM:-}" != dumb ]; then
        printf '\033[%sm%s\033[0m' "$1" "$2"
    else
        printf '%s' "$2"
    fi
}
say() { paint "$1" "$2"; printf '\n'; }
fail() { say '1;31' "godmode install: $*" >&2; exit 1; }
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
cleanup() {
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
download_dir=
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
        -h|--help) usage; exit 0 ;;
        *) fail "unknown option; use --help" ;;
    esac
done

[ "$home_option:$bin_option" != yes:yes ] || fail "--home and --bin-dir cannot be combined"
case "$godmode_home" in /*) ;; *) godmode_home=$PWD/$godmode_home ;; esac
[ "$bin_option" = yes ] || bin_dir=$godmode_home/bin
case "$bin_dir" in /*) ;; *) bin_dir=$PWD/$bin_dir ;; esac
[ ! -L "$bin_dir" ] || fail "destination directory must not be a symlink"
destination=$bin_dir/godmode
[ ! -L "$destination" ] || fail "destination is a symlink; nothing installed"
if [ -e "$destination" ]; then
    if [ "$force" != yes ]; then
        say '1;31' "godmode install: $destination already exists; nothing replaced." >&2
        say '1;35' 'If this is your Godmode installation, start it with:' >&2
        printf '  ' >&2
        setup_command init >&2
        fail "use another --home/--bin-dir for a separate install, or --force for an intentional executable replacement"
    fi
    [ -f "$destination" ] || fail "destination is not a regular file"
fi

trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
if [ -z "$archive$binary$checksum$expected" ]; then
    [ "$setup" != auto ] || setup=yes
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
    say '1;36' "Downloading Godmode $version for $target..."
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
if command -v sha256sum >/dev/null 2>&1; then
    actual=$(sha256sum < "$artifact" | awk '{print $1}')
elif command -v shasum >/dev/null 2>&1; then
    actual=$(shasum -a 256 < "$artifact" | awk '{print $1}')
else
    fail "sha256sum or shasum is required"
fi
expected=$(printf '%s' "$expected" | tr 'A-F' 'a-f')
[ "$actual" = "$expected" ] || fail "checksum mismatch; nothing installed"

mkdir -p "$bin_dir"
staged=$(mktemp "$bin_dir/.godmode-install.XXXXXX")
if [ -n "$archive" ]; then
    # Stream only this member into a file we created; never extract archive paths.
    tar -xOzf "$archive" godmode > "$staged" || fail "archive must contain a root-level godmode binary"
else
    cat "$binary" > "$staged"
fi
[ -s "$staged" ] || fail "binary is empty"
chmod 755 "$staged"
if [ "$force" = yes ]; then
    [ ! -L "$destination" ] || fail "destination became a symlink"
    mv -f "$staged" "$destination"
else
    ln "$staged" "$destination" || fail "destination appeared during install; nothing replaced"
fi
paint '1;32' 'Installed '
paint '1;33' "$destination"
printf '\n'
printf '%s\n' 'No configuration, credentials or shell profile changed.'
if [ -n "$previous_command" ] && [ "$previous_command" != "$destination" ]; then
    printf 'Another godmode command was already available: '
    paint '1;33' "$previous_command"
    printf '\n'
    printf '%s\n' 'It was not changed. Use the full path below to select this installation.'
fi
printf '\n'
say '1;35' 'Start interactive setup:'
printf '  '
setup_command
case ":${PATH:-}:" in
    *:"$bin_dir":*) ;;
    *)
        case "$bin_dir" in
            *:*) printf '\nThis directory contains a colon; use the full executable path instead of adding it to PATH.\n' ;;
            *)
                printf '\n'
                say '1;35' 'For this shell, add the bin directory to PATH:'
                printf '  export PATH='
                shell_quote "$bin_dir"
                # shellcheck disable=SC2016 # Print a command for the user's shell.
                printf ':"$PATH"\n'
                printf '%s\n' 'To keep that setting, add the command to the startup file used by your shell.'
                ;;
        esac
        ;;
esac
if [ "$setup" = yes ]; then
    if ( : </dev/tty >/dev/tty ) 2>/dev/null; then
        printf '\n'
        say '1;36' 'Starting interactive setup...'
        if [ "$home_option" = yes ] || [ -n "${GODMODE_HOME:-}" ]; then
            "$destination" --home "$godmode_home" init </dev/tty >/dev/tty 2>&1
        else
            "$destination" init </dev/tty >/dev/tty 2>&1
        fi
    else
        printf '\nNo interactive terminal is attached; run the setup command above in a terminal.\n'
    fi
fi
}
main "$@"
