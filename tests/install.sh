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
HOME="$scratch/home" GODMODE_HOME='' PATH="$scratch/old-bin:$PATH" sh "$repo/install.sh" \
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
# shellcheck disable=SC2016 # Shell syntax is deliberately literal test data.
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
# shellcheck disable=SC2016 # The generated script must expand its own PATH.
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


# Automatic downloads are exercised with local fixtures. No GitHub authentication
# or network access is used by this test, even if the developer is signed in.
mkdir -p "$scratch/mock-bin" "$scratch/downloads" "$scratch/fixtures"
cat > "$scratch/mock-bin/uname" <<'MOCK'
#!/bin/sh
case "$1" in
    -s) printf '%s\n' "${GODMODE_TEST_OS:-Darwin}" ;;
    -m) printf '%s\n' "${GODMODE_TEST_ARCH:-arm64}" ;;
    *) exit 1 ;;
esac
MOCK
cat > "$scratch/mock-bin/gh" <<'MOCK'
#!/bin/sh
printf '%s\n' "$*" >> "$GODMODE_TEST_NETWORK_LOG"
case "$1" in
    api)
        [ "${GODMODE_TEST_GH_MODE:-success}" != fail ] || exit 1
        [ "${GODMODE_TEST_GH_MODE:-success}" != empty ] || exit 0
        printf '%s\n' "${GODMODE_TEST_TAG:-v7.6.5}"
        ;;
    release)
        shift 3
        name=; dir=
        while [ "$#" -gt 0 ]; do
            case "$1" in
                --repo) [ "$2" = github.com/lofimichael/godmode-cli ] || exit 1; shift 2 ;;
                --pattern) [ "$2" = SHA256SUMS ] || name=$2; shift 2 ;;
                --dir) dir=$2; shift 2 ;;
                *) exit 1 ;;
            esac
        done
        cp "$GODMODE_TEST_FIXTURES/$name" "$dir/$name"
        cp "$GODMODE_TEST_FIXTURES/SHA256SUMS" "$dir/SHA256SUMS"
        ;;
    *) exit 1 ;;
esac
MOCK
cat > "$scratch/mock-bin/curl" <<'MOCK'
#!/bin/sh
printf '%s\n' "$*" >> "$GODMODE_TEST_NETWORK_LOG"
output=; url=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --output) output=$2; shift 2 ;;
        --write-out|--proto|--proto-redir) shift 2 ;;
        https://*) url=$1; shift ;;
        --disable|--fail|--silent|--show-error|--location|--tlsv1.2) shift ;;
        *) exit 1 ;;
    esac
done
case "$url" in
    https://github.com/lofimichael/godmode-cli/releases/latest)
        printf '%s' 'https://github.com/lofimichael/godmode-cli/releases/tag/v7.6.5'
        ;;
    https://github.com/lofimichael/godmode-cli/releases/download/v7.6.5/*)
        cp "$GODMODE_TEST_FIXTURES/${url##*/}" "$output"
        ;;
    *) exit 1 ;;
esac
MOCK
chmod 755 "$scratch/mock-bin/gh" "$scratch/mock-bin/curl" "$scratch/mock-bin/uname"
fixture_name=godmode-v7.6.5-aarch64-apple-darwin.tar.gz
cp "$scratch/godmode-test.tar.gz" "$scratch/fixtures/$fixture_name"
printf '%s  %s\n' "$archive_digest" "$fixture_name" > "$scratch/fixtures/SHA256SUMS"
export GODMODE_TEST_FIXTURES="$scratch/fixtures"
export GODMODE_TEST_NETWORK_LOG="$scratch/network-log"
export TMPDIR="$scratch/downloads"
mock_path=$scratch/mock-bin:$PATH
HOME="$scratch/automatic-home" GODMODE_HOME='' PATH="$mock_path" sh "$repo/install.sh" --no-setup > "$scratch/automatic-output"
cmp "$scratch/artifact/godmode" "$scratch/automatic-home/.godmode/bin/godmode"
grep -q 'Downloading Godmode v7.6.5 for aarch64-apple-darwin' "$scratch/automatic-output"
grep -q -- ' init$' "$scratch/automatic-output"
[ ! -e "$scratch/automatic-home/.godmode/.env.godmode" ]
[ ! -e "$scratch/automatic-home/.godmode/state" ]
[ -z "$(ls -A "$scratch/downloads")" ]

# Re-running never fetches or replaces an existing installation.
: > "$GODMODE_TEST_NETWORK_LOG"
if HOME="$scratch/automatic-home" GODMODE_HOME='' PATH="$mock_path" sh "$repo/install.sh" --no-setup > "$scratch/repeat-output" 2>&1; then
    echo 'automatic install replaced an existing binary' >&2; exit 1
fi
[ ! -s "$GODMODE_TEST_NETWORK_LOG" ]
grep -q -- ' init$' "$scratch/repeat-output"
cmp "$scratch/artifact/godmode" "$scratch/automatic-home/.godmode/bin/godmode"

# Private API failure falls back to a public HTTPS release; pinning is optional.
GODMODE_TEST_GH_MODE=fail PATH="$mock_path" sh "$repo/install.sh" --no-setup --home "$scratch/public-home" > "$scratch/public-output"
cmp "$scratch/artifact/godmode" "$scratch/public-home/bin/godmode"
grep -q -- '--proto =https --proto-redir =https' "$GODMODE_TEST_NETWORK_LOG"
PATH="$mock_path" sh "$repo/install.sh" --no-setup --version v7.6.5 --home "$scratch/pinned-home" >/dev/null
cmp "$scratch/artifact/godmode" "$scratch/pinned-home/bin/godmode"

# Missing/unsupported targets, untrusted tags and bad hashes leave no home behind.
: > "$GODMODE_TEST_NETWORK_LOG"
if GODMODE_TEST_OS=FreeBSD PATH="$mock_path" sh "$repo/install.sh" --no-setup --home "$scratch/unsupported-home" 2>/dev/null; then
    echo 'unsupported target was accepted' >&2; exit 1
fi
[ ! -e "$scratch/unsupported-home" ]
[ ! -s "$GODMODE_TEST_NETWORK_LOG" ]
if GODMODE_TEST_GH_MODE=empty PATH="$mock_path" sh "$repo/install.sh" --no-setup --home "$scratch/missing-home" 2>/dev/null; then
    echo 'empty release selection was accepted' >&2; exit 1
fi
[ ! -e "$scratch/missing-home" ]
if GODMODE_TEST_TAG='v7.6.5/../../bad' PATH="$mock_path" sh "$repo/install.sh" --no-setup --home "$scratch/tag-home" 2>/dev/null; then
    echo 'unsafe release metadata was accepted' >&2; exit 1
fi
[ ! -e "$scratch/tag-home" ]
if GODMODE_TEST_TAG='v7.6.5
../../bad' PATH="$mock_path" sh "$repo/install.sh" --no-setup --home "$scratch/multiline-tag-home" 2>/dev/null; then
    echo 'multiline release metadata was accepted' >&2; exit 1
fi
[ ! -e "$scratch/multiline-tag-home" ]
printf '%064d  %s\n' 0 "$fixture_name" > "$scratch/fixtures/SHA256SUMS"
if PATH="$mock_path" sh "$repo/install.sh" --no-setup --home "$scratch/corrupt-home" >/dev/null 2>&1; then
    echo 'corrupt download was installed' >&2; exit 1
fi
[ ! -e "$scratch/corrupt-home" ]
[ -z "$(ls -A "$scratch/downloads")" ]
printf '%s  %s\n' "$archive_digest" "$fixture_name" > "$scratch/fixtures/SHA256SUMS"

# A piped installer must reconnect setup to the controlling terminal, not leave
# it reading the installer stream. The fake CLI checks all three descriptors.
python3 - "$repo" "$scratch" <<'PY'
import hashlib, os, select, signal, subprocess, sys, tarfile, termios, time
from pathlib import Path
repo, scratch = map(Path, sys.argv[1:])
program = scratch / 'tty-fixture'
program.write_text('''#!/bin/sh
[ -t 0 ] && [ -t 1 ] && [ -t 2 ] || exit 91
printf '%s\\n' "$@" > "$GODMODE_TEST_SETUP_LOG"
printf 'SETUP_WAITING\\n'
read -r reply
[ "$reply" = finish ] || exit 92
printf 'SETUP_FINISHED\\n'
''')
digest = hashlib.sha256(program.read_bytes()).hexdigest()
archive = scratch/'fixtures/godmode-v7.6.5-aarch64-apple-darwin.tar.gz'
with tarfile.open(archive, 'w:gz') as tar:
    tar.add(program, arcname='godmode')
(scratch/'fixtures/SHA256SUMS').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
# Only the wrapper owns stdin from the PTY. Installer stdin is a separate pipe.
wrapper = '''import subprocess,sys
from pathlib import Path
p=subprocess.Popen(['sh','-s','--',*sys.argv[2:]],stdin=subprocess.PIPE)
p.communicate(Path(sys.argv[1]).read_bytes())
sys.exit(p.returncode)
'''
def session():
    import fcntl
    os.setsid()
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)
for mode in ['offline', 'automatic', 'no-color', 'dumb']:
    master, slave = os.openpty()
    root = scratch / ('tty-home-'+mode)
    env = dict(os.environ, GODMODE_TEST_SETUP_LOG=str(scratch/'setup-args'),
               PATH=str(scratch/'mock-bin')+':'+os.environ['PATH'])
    env.pop('NO_COLOR', None)
    env['TERM'] = 'dumb' if mode == 'dumb' else 'xterm-256color'
    if mode == 'no-color':
        env['NO_COLOR'] = ''
    args = ['--home', str(root)]
    if mode != 'automatic':
        args += ['--binary', str(program), '--sha256', digest, '--setup']
    process = subprocess.Popen([sys.executable, '-c', wrapper, str(repo/'install.sh'), *args],
                               stdin=slave, stdout=slave, stderr=slave, env=env, preexec_fn=session)
    output = bytearray()
    def wait_for(expected):
        deadline = time.monotonic() + 8
        while expected not in output:
            if time.monotonic() > deadline:
                raise AssertionError('installer PTY handoff timed out')
            if select.select([master], [], [], .05)[0]:
                output.extend(os.read(master, 65536))
    try:
        wait_for(b'SETUP_WAITING')
        os.write(master, b'finish\n')
        wait_for(b'SETUP_FINISHED')
        assert process.wait(timeout=5) == 0
        assert (scratch/'setup-args').read_text().splitlines() == ['--home', str(root), 'init']
        assert not (root/'.env.godmode').exists()
        if mode in ['no-color', 'dumb']:
            assert b'\x1b[' not in output, 'color opt-out was ignored'
        else:
            for color in [b'\x1b[1;32m', b'\x1b[1;33m', b'\x1b[1;35m']:
                assert color in output, 'interactive installer styling missing'
            if mode == 'automatic':
                assert b'\x1b[1;36mDownloading' in output
        commands = [line for line in output.splitlines() if line.startswith(b"  '") and line.endswith(b' init')]
        assert len(commands) == 1 and b'\x1b' not in commands[0], 'copyable setup command was styled'
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        os.close(master); os.close(slave)

# Refusal uses bold red on an interactive stderr, while redirected output is plain.
master, slave = os.openpty()
env.pop('NO_COLOR', None); env['TERM'] = 'xterm-256color'
process = subprocess.Popen([sys.executable, '-c', wrapper, str(repo/'install.sh'), '--home', str(root)],
                           stdin=slave, stdout=slave, stderr=slave, env=env, preexec_fn=session)
error = bytearray()
try:
    deadline = time.monotonic()+8
    while process.poll() is None:
        assert time.monotonic() < deadline, 'installer refusal did not exit'
        if select.select([master], [], [], .05)[0]:
            error.extend(os.read(master, 65536))
    if select.select([master], [], [], .05)[0]:
        error.extend(os.read(master, 65536))
    assert process.returncode != 0
    assert b'\x1b[1;31m' in error and b'nothing replaced' in error
finally:
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    os.close(master); os.close(slave)
for name in ['automatic-output', 'public-output', 'repeat-output']:
    assert b'\x1b[' not in (scratch/name).read_bytes(), 'redirected output contained styling'

PY
printf '%s\n' 'Installer tests passed (offline artifacts, automatic GitHub/public download, platform/tag/checksum refusal, no-clobber, symlinks, home/PATH, piped PTY setup, TTY colors and opt-outs).'
