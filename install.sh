#!/bin/sh
# Installs a verified local artifact. Never downloads or changes configuration.
set -eu
umask 077

usage() {
    cat <<'EOF'
Usage:
  sh install.sh --archive PATH --checksum SHA256SUMS [--home DIR | --bin-dir DIR] [--force]
  sh install.sh --binary PATH --sha256 HEX [--home DIR | --bin-dir DIR] [--force]

Default destination: ~/.godmode/bin/godmode (or $GODMODE_HOME/bin/godmode)
--home DIR selects a Godmode home and installs into DIR/bin.
--bin-dir DIR selects only an executable directory; it does not select a home.
An existing destination is refused unless --force is given. Symlinks are always
refused. No configuration, credentials, shell profiles or PATH settings change.
EOF
}
fail() { printf '%s\n' "godmode install: $*" >&2; exit 1; }
need_value() { [ "$#" -ge 2 ] && [ -n "$2" ] || fail "missing option value"; }
# Emit a literal POSIX-shell argument; paths may contain quotes or shell syntax.
shell_quote() {
    printf "'"
    printf '%s' "$1" | sed "s/'/'\\\\''/g"
    printf "'"
}

archive=
binary=
checksum=
expected=
godmode_home=${GODMODE_HOME:-${HOME:?HOME must be set}/.godmode}
bin_dir=
home_option=no
bin_option=no
force=no
previous_command=$(command -v godmode 2>/dev/null || :)
while [ "$#" -gt 0 ]; do
    case "$1" in
        --archive) need_value "$@"; archive=$2; shift 2 ;;
        --binary) need_value "$@"; binary=$2; shift 2 ;;
        --checksum) need_value "$@"; checksum=$2; shift 2 ;;
        --sha256) need_value "$@"; expected=$2; shift 2 ;;
        --home) need_value "$@"; godmode_home=$2; home_option=yes; shift 2 ;;
        --bin-dir) need_value "$@"; bin_dir=$2; bin_option=yes; shift 2 ;;
        --force) force=yes; shift ;;
        -h|--help) usage; exit 0 ;;
        *) fail "unknown option; use --help" ;;
    esac
done

[ "$home_option:$bin_option" != yes:yes ] || fail "--home and --bin-dir cannot be combined"
case "$godmode_home" in /*) ;; *) godmode_home=$PWD/$godmode_home ;; esac
[ "$bin_option" = yes ] || bin_dir=$godmode_home/bin

if [ -n "$archive" ]; then
    [ -z "$binary" ] && [ -z "$expected" ] && [ -n "$checksum" ] || fail "use --archive with --checksum only"
    [ -f "$archive" ] && [ -f "$checksum" ] || fail "archive or checksum file is missing"
    artifact=$archive
    # Literal filename comparison; never execute or source a checksum file.
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

# Prefix relative paths so filenames cannot be parsed as command options.
case "$bin_dir" in /*) ;; *) bin_dir=$PWD/$bin_dir ;; esac
[ ! -L "$bin_dir" ] || fail "destination directory must not be a symlink"
destination=$bin_dir/godmode
[ ! -L "$destination" ] || fail "destination is a symlink; nothing installed"
if [ -e "$destination" ]; then
    [ "$force" = yes ] || fail "destination already exists; use another --bin-dir or explicitly pass --force"
    [ -f "$destination" ] || fail "destination is not a regular file"
fi
mkdir -p "$bin_dir"
staged=$(mktemp "$bin_dir/.godmode-install.XXXXXX")
trap 'rm -f "$staged"' EXIT HUP INT TERM
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
    # Atomic create-if-absent: a concurrent install cannot overwrite a binary.
    ln "$staged" "$destination" || fail "destination appeared during install; nothing replaced"
fi
printf 'Installed %s\n' "$destination"
printf '%s\n' 'No configuration, credentials or shell profile changed.'
if [ -n "$previous_command" ] && [ "$previous_command" != "$destination" ]; then
    printf 'Another godmode command was already available: %s\n' "$previous_command"
    printf '%s\n' 'It was not changed. Use the full path below to select this installation.'
fi
printf '\nStart interactive setup:\n  '
shell_quote "$destination"
if [ "$home_option" = yes ] || [ -n "${GODMODE_HOME:-}" ]; then
    printf ' --home '
    shell_quote "$godmode_home"
fi
printf ' init\n'
case ":${PATH:-}:" in
    *:"$bin_dir":*) ;;
    *)
        case "$bin_dir" in
            *:*) printf '\nThis directory contains a colon; use the full executable path instead of adding it to PATH.\n' ;;
            *)
                printf '\nFor this shell, add the bin directory to PATH:\n  export PATH='
                shell_quote "$bin_dir"
                printf ':"$PATH"\n'
                printf '%s\n' 'To keep that setting, add the command to the startup file used by your shell.'
                ;;
        esac
        ;;
esac
