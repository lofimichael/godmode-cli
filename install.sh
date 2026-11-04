#!/bin/sh
# Installs a verified local artifact. Never downloads or changes configuration.
set -eu
umask 077

usage() {
    cat <<'EOF'
Usage:
  sh install.sh --archive PATH --checksum SHA256SUMS [--bin-dir DIR] [--force]
  sh install.sh --binary PATH --sha256 HEX [--bin-dir DIR] [--force]

Default destination: ~/.local/bin/godmode
An existing destination is refused unless --force is given. Symlinks are always
refused. No configuration, credentials, shell profiles or PATH settings change.
EOF
}
fail() { printf '%s\n' "godmode install: $*" >&2; exit 1; }
need_value() { [ "$#" -ge 2 ] && [ -n "$2" ] || fail "missing option value"; }

archive=
binary=
checksum=
expected=
bin_dir=${HOME:?HOME must be set}/.local/bin
force=no
while [ "$#" -gt 0 ]; do
    case "$1" in
        --archive) need_value "$@"; archive=$2; shift 2 ;;
        --binary) need_value "$@"; binary=$2; shift 2 ;;
        --checksum) need_value "$@"; checksum=$2; shift 2 ;;
        --sha256) need_value "$@"; expected=$2; shift 2 ;;
        --bin-dir) need_value "$@"; bin_dir=$2; shift 2 ;;
        --force) force=yes; shift ;;
        -h|--help) usage; exit 0 ;;
        *) fail "unknown option; use --help" ;;
    esac
done

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
printf '%s\n' 'No configuration or shell profile changed. Use the full path if this directory is not on PATH.'
