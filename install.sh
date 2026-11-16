#!/bin/sh
# godmode-installer-format: 1
# Install the CLI; the installed copy of this script is the godmodeup command.
# Explicit local-artifact modes remain offline. Never reads stored credentials.
set -eu
umask 077

usage() {
    cat <<'USAGE'
Usage:
  sh install.sh [--version vX.Y.Z] [--home DIR | --bin-dir DIR] [--path] [--install-only]
  godmodeup [--version vX.Y.Z] [--setup] [--path]
  sh install.sh --archive PATH --checksum SHA256SUMS [--home DIR | --bin-dir DIR] [--setup]
  sh install.sh --binary PATH --sha256 HEX [--home DIR | --bin-dir DIR] [--setup]

With no artifact flags, download the newest compatible release from godmode.build,
verify its checksum, install it and start interactive masked setup. Python 3.9+
is required; no Python packages, account or activation are needed.
Default destination: ~/.godmode/bin/godmode (or $GODMODE_HOME/bin/godmode).
--home DIR selects a home; --bin-dir DIR changes only the executable directory.
--install-only (also --no-setup) installs only; --setup opens setup after install.
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
    [ "${#1}" -le 40 ] || return 1
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
    unset GODMODE_PREVIEW_PASSWORD
    [ -z "$updater_staged" ] || rm -f "$updater_staged"
    [ -z "$receipt_staged" ] || rm -f "$receipt_staged"
    [ -z "$env_staged" ] || rm -f "$env_staged"
    [ -z "$backup_staged" ] || rm -f "$backup_staged"
    [ -z "$lock_dir" ] || rmdir "$lock_dir" 2>/dev/null || :
    [ -z "$staged" ] || rm -f "$staged"
    [ -z "$download_dir" ] || rm -rf "$download_dir"
}

# Downloads use one fixed public HTTPS origin and never send account credentials.
fetch_release() {
    python3 -I - "$@" <<'GODMODE_DOWNLOAD_PY'
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import sys
import urllib.error
import urllib.request

ORIGIN = "https://godmode.build"
MAX_MANIFEST = 128 * 1024
MAX_ARCHIVE = 256 * 1024 * 1024
TARGETS = {
    "darwin-arm64": "aarch64-apple-darwin",
    "darwin-amd64": "x86_64-apple-darwin",
    "linux-amd64": "x86_64-unknown-linux-musl",
    "linux-arm64": "aarch64-unknown-linux-musl",
}

class DownloadError(Exception):
    pass

class RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DownloadError("release manifest contains duplicate fields")
        result[key] = value
    return result

def validate_entry(entry, version, platform=None):
    fields = {"filename", "sha256", "size"}
    if platform is not None:
        fields.add("platform")
    if not isinstance(entry, dict) or set(entry) != fields:
        raise DownloadError("release manifest has an invalid artifact")
    name = entry["filename"]
    pattern = r"godmode-" + re.escape(version) + r"(?:-[A-Za-z0-9][A-Za-z0-9._-]*)?\.tar\.gz"
    if not isinstance(name, str) or len(name) > 160 or ".." in name or not re.fullmatch(pattern, name):
        raise DownloadError("release manifest has an unsafe filename")
    if platform is not None and name != "godmode-" + version + "-" + TARGETS[platform] + ".tar.gz":
        raise DownloadError("release filename does not match its platform")
    digest = entry["sha256"]
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise DownloadError("release manifest has an invalid checksum")
    if type(entry["size"]) is not int or not 0 < entry["size"] <= MAX_ARCHIVE:
        raise DownloadError("release manifest has an invalid size")

def manifest(data, requested, platform):
    try:
        doc = json.loads(data.decode("utf-8"), object_pairs_hook=unique_object)
    except (ValueError, UnicodeError):
        raise DownloadError("release manifest is not valid JSON") from None
    if not isinstance(doc, dict) or set(doc) != {"version", "artifacts", "source"}:
        raise DownloadError("release manifest has an invalid schema")
    version = doc["version"]
    if not isinstance(version, str) or len(version) > 40 or not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", version):
        raise DownloadError("release manifest has an invalid version")
    if requested and version != requested:
        raise DownloadError("release manifest does not match the requested version")
    entries = doc["artifacts"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= len(TARGETS):
        raise DownloadError("release manifest has an invalid artifact list")
    seen = set()
    filenames = set()
    selected = None
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("platform"), str):
            raise DownloadError("release manifest has an invalid platform")
        target = entry["platform"]
        if target not in TARGETS or target in seen:
            raise DownloadError("release manifest has an unknown or duplicate platform")
        validate_entry(entry, version, target)
        seen.add(target)
        filenames.add(entry["filename"])
        if target == platform:
            selected = entry
    validate_entry(doc["source"], version)
    if doc["source"]["filename"] in filenames:
        raise DownloadError("release source and binary filenames must differ")
    if selected is None:
        raise DownloadError("this release has no artifact for this platform")
    return version, selected

class Downloads:
    def __init__(self):
        os.environ.pop("GODMODE_PREVIEW_PASSWORD", None)
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), RefuseRedirects(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()))

    def open(self, path):
        headers = {"User-Agent": "godmode-installer/3", "Accept-Encoding": "identity"}
        req = urllib.request.Request(ORIGIN + path, headers=headers)
        try:
            response = self.opener.open(req, timeout=30)
            if response.status != 200:
                response.close()
                raise DownloadError("release server returned an unexpected response")
            return response
        except urllib.error.HTTPError as error:
            status = error.code
            error.close()
            if 300 <= status < 400:
                raise DownloadError("release server redirected a request; redirects are refused") from None
            raise DownloadError("release download failed (HTTP " + str(status) + ")") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise DownloadError("cannot reach godmode.build over verified HTTPS") from None

def main():
    directory, requested, platform, installed, options = sys.argv[1:]
    directory = Path(directory)
    download = Downloads()
    route = "/releases/" + requested + "/manifest.json" if requested else "/releases/latest.json"
    with download.open(route) as response:
        data = response.read(MAX_MANIFEST + 1)
    if len(data) > MAX_MANIFEST:
        raise DownloadError("release manifest is too large")
    version, selected = manifest(data, requested, platform)
    if installed == version[1:] and options == "no:no:no":
        (directory / "release").write_text(version + "\ncurrent\n", encoding="utf-8")
        print("  Godmode " + installed + " is up to date.")
        return
    if installed and installed != version[1:]:
        locale = os.environ.get("LC_ALL") or os.environ.get("LC_CTYPE") or os.environ.get("LANG", "C")
        utf8 = locale in ("C", "POSIX") or "utf-8" in locale.lower() or "utf8" in locale.lower()
        arrow = "\u2192" if utf8 and os.environ.get("TERM") != "linux" else "->"
        print("  Godmode " + installed + " " + arrow + " " + version[1:], flush=True)
    else:
        print("  Downloading Godmode " + version[1:], flush=True)
    name = selected["filename"]
    digest = hashlib.sha256()
    count = 0
    with download.open("/releases/" + version + "/" + name) as response:
        length = response.headers.get("Content-Length")
        if length is not None and length != str(selected["size"]):
            raise DownloadError("release download size does not match the manifest")
        with (directory / name).open("xb") as output:
            while True:
                chunk = response.read(min(1024 * 1024, selected["size"] - count + 1))
                if not chunk:
                    break
                count += len(chunk)
                if count > selected["size"]:
                    raise DownloadError("release download exceeds its declared size")
                digest.update(chunk)
                output.write(chunk)
    if count != selected["size"]:
        raise DownloadError("release download is incomplete")
    if digest.hexdigest() != selected["sha256"]:
        raise DownloadError("checksum mismatch")
    (directory / "SHA256SUMS").write_text(selected["sha256"] + "  " + name + "\n", encoding="ascii")
    (directory / "release").write_text(version + "\n" + name + "\n", encoding="ascii")

try:
    main()
except KeyboardInterrupt:
    print("\ngodmode install: download cancelled; nothing installed", file=sys.stderr)
    sys.exit(130)
except (DownloadError, OSError, ValueError, http.client.HTTPException):
    # Only intentional DownloadError text is safe to show; other exceptions may
    # contain local inputs or URLs. Never print a response body or credentials.
    error = sys.exc_info()[1]
    message = str(error) if isinstance(error, DownloadError) else "release download failed"
    print("godmode install: " + message + "; nothing installed", file=sys.stderr)
    sys.exit(1)
GODMODE_DOWNLOAD_PY
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
        --install-only|--no-setup) setup=no; shift ;;
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
    case "$(uname -s):$(uname -m)" in
        Darwin:arm64|Darwin:aarch64) platform=darwin-arm64 ;;
        Darwin:x86_64) platform=darwin-amd64 ;;
        Linux:x86_64) platform=linux-amd64 ;;
        Linux:aarch64|Linux:arm64) platform=linux-arm64 ;;
        Darwin:*|Linux:*) fail "Godmode has no release for this CPU; use a verified local archive" ;;
        *) fail "Godmode supports macOS and Linux" ;;
    esac
    installed=
    [ "$update" != yes ] || installed=$(installed_version)
    download_dir=$(mktemp -d "${TMPDIR:-/tmp}/godmode-download.XXXXXX")
    fetch_release "$download_dir" "$version" "$platform" "$installed" "$force:$setup:$path_setup"
    unset GODMODE_PREVIEW_PASSWORD
    version=$(sed -n '1p' "$download_dir/release")
    name=$(sed -n '2p' "$download_dir/release")
    # The helper validates the public manifest before deciding that
    # a managed installation is current. No artifact is fetched in that case.
    [ "$name" != current ] || exit 0
    archive=$download_dir/$name
    checksum=$download_dir/SHA256SUMS
    release_url=https://godmode.build/releases/$version/manifest.json
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
    [ -z "$release_url" ] || printf '  Release: %s\n' "$release_url"
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
