#!/bin/sh
# Exercise installer refusal and replacement paths with synthetic executables.
set -eu
repo=$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)
scratch=$(mktemp -d)
# All files here are synthetic and the directory was allocated by this test.
trap 'rm -rf "$scratch"' EXIT HUP INT TERM
# Output must not depend on the developer's machine: no installed godmode on
# PATH, a POSIX shell, and a locale the CLI reads as UTF-8.
clean_path=
old_ifs=$IFS
IFS=:
set -f
for dir in $PATH; do
    [ -e "$dir/godmode" ] || clean_path=${clean_path:+$clean_path:}$dir
done
set +f
IFS=$old_ifs
export PATH="$clean_path" SHELL=/bin/sh LC_ALL=C
unset GODMODE_HOME ZDOTDIR
check=$(printf '\342\234\223')
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
cp "$repo/install.sh" "$scratch/artifact/install.sh"
tar -czf "$scratch/godmode-test.tar.gz" -C "$scratch/artifact" godmode install.sh
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
# Another godmode on PATH is named, and hints use this installation's full path.
printf '  %s\n' "$check Installed ~/.godmode/bin/godmode" \
    "Another godmode is on PATH at $scratch/old-bin/godmode; it was not changed." \
    "Add ~/.godmode/bin to PATH in your shell's startup file." \
    'For this shell, run:  . ~/.godmode/env' \
    'To set up, run:  ~/.godmode/bin/godmode' | cmp - "$scratch/default-output"
[ -f "$scratch/home/.godmode/env" ]
[ -x "$scratch/home/.godmode/bin/godmodeup" ]

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

# Copyable commands show HOME as ~ and keep shell metacharacters literal.
# shellcheck disable=SC2016 # Shell syntax is deliberately literal test data.
odd_dir="$scratch/space ' quote "'$(touch SHOULD_NOT_EXIST) `touch ALSO_NOT_EXIST`'
HOME="$scratch" sh "$repo/install.sh" --binary "$scratch/artifact/godmode" --sha256 "$digest" \
    --home "$odd_dir" > "$scratch/quoted-output"
env_line=$(sed -n 's/^  For this shell, run:  //p' "$scratch/quoted-output")
start_line=$(sed -n 's/^  To set up, run:  //p' "$scratch/quoted-output")
case "$env_line|$start_line" in
    ". ~/'space "*"|godmode --home ~/'space "*) ;;
    *) echo 'copyable commands are not in the expected ~ form' >&2; exit 1 ;;
esac
# Run only the commands produced for this synthetic path.
printf '%s\n' "$env_line" 'command -v godmode' "$start_line" > "$scratch/check-path.sh"
(cd "$scratch" && HOME="$scratch" sh "$scratch/check-path.sh") > "$scratch/started-output"
printf '%s\n' "$odd_dir/bin/godmode" synthetic-version-two | cmp - "$scratch/started-output"
[ ! -e "$scratch/SHOULD_NOT_EXIST" ]
[ ! -e "$scratch/ALSO_NOT_EXIST" ]
# A --bin-dir without --path has no env file; the note names the directory.
sh "$repo/install.sh" --binary "$scratch/artifact/godmode" --sha256 "$digest" \
    --bin-dir "$odd_dir/only-bin" > "$scratch/bin-only-output"
grep -Fq "to PATH in your shell's startup file." "$scratch/bin-only-output"
if grep -q 'run:  \.' "$scratch/bin-only-output"; then
    echo 'a bin-only install suggested an env file' >&2; exit 1
fi

# PATH notes are omitted when the directory is already a component.
PATH="$scratch/on-path:$PATH" sh "$repo/install.sh" --binary "$scratch/artifact/godmode" \
    --sha256 "$digest" --bin-dir "$scratch/on-path" > "$scratch/on-path-output"
printf '  %s\n' "$check Installed $scratch/on-path/godmode" 'To set up, run:  godmode' | cmp - "$scratch/on-path-output"


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
set -e
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
grep -qx '  Downloading Godmode 7.6.5' "$scratch/automatic-output"
grep -qx '  To set up, run:  godmode' "$scratch/automatic-output"
[ ! -e "$scratch/automatic-home/.godmode/.env.godmode" ]
[ ! -e "$scratch/automatic-home/.godmode/state" ]
[ -z "$(ls -A "$scratch/downloads")" ]

# The README install prints three lines; the PATH note and next command follow.
mkdir "$scratch/fresh-account"
HOME="$scratch/fresh-account" SHELL=/bin/zsh PATH="$mock_path" sh "$repo/install.sh" --path --no-setup > "$scratch/fresh-output"
printf '  %s\n' 'Downloading Godmode 7.6.5' "$check Installed ~/.godmode/bin/godmode" \
    "$check Added ~/.godmode/bin to PATH in ~/.zshenv" \
    'Open a new terminal, or run:  . ~/.godmode/env' 'To set up, run:  godmode' | cmp - "$scratch/fresh-output"
[ -f "$scratch/fresh-account/.zshenv" ]
[ ! -e "$scratch/fresh-account/.zshrc" ]

# A portable archive is preferred when both new and legacy asset names exist.
universal_name=godmode-v7.6.5-unix.tar.gz
cp "$scratch/godmode-test.tar.gz" "$scratch/fixtures/$universal_name"
printf '%s  %s\n%s  %s\n' "$archive_digest" "$fixture_name" "$archive_digest" "$universal_name" > "$scratch/fixtures/SHA256SUMS"
: > "$GODMODE_TEST_NETWORK_LOG"
PATH="$mock_path" sh "$repo/install.sh" --no-setup --home "$scratch/universal-home" > /dev/null
cmp "$scratch/artifact/godmode" "$scratch/universal-home/bin/godmode"
grep -q -- "--pattern $universal_name" "$GODMODE_TEST_NETWORK_LOG"
if grep -q -- "--pattern $fixture_name" "$GODMODE_TEST_NETWORK_LOG"; then
    echo 'legacy archive was downloaded despite an available portable script' >&2; exit 1
fi
# A portable script does not depend on a known native CPU architecture.
GODMODE_TEST_ARCH=riscv64 PATH="$mock_path" sh "$repo/install.sh" --no-setup --home "$scratch/universal-cpu-home" > /dev/null
cmp "$scratch/artifact/godmode" "$scratch/universal-cpu-home/bin/godmode"
rm "$scratch/fixtures/$universal_name"
printf '%s  %s\n' "$archive_digest" "$fixture_name" > "$scratch/fixtures/SHA256SUMS"

# Re-running never fetches or replaces an existing installation.
: > "$GODMODE_TEST_NETWORK_LOG"
if HOME="$scratch/automatic-home" GODMODE_HOME='' PATH="$mock_path" sh "$repo/install.sh" --no-setup > "$scratch/repeat-output" 2>&1; then
    echo 'automatic install replaced an existing binary' >&2; exit 1
fi
[ ! -s "$GODMODE_TEST_NETWORK_LOG" ]
printf '%s\n' 'godmode install: ~/.godmode/bin/godmode already exists; nothing replaced.' \
    'Run godmode to set up, or godmodeup to update.' | cmp - "$scratch/repeat-output"
cmp "$scratch/artifact/godmode" "$scratch/automatic-home/.godmode/bin/godmode"

# An executable that reports no version is downloaded again, without setup.
HOME="$scratch/automatic-home" PATH="$mock_path" "$scratch/automatic-home/.godmode/bin/godmodeup" > "$scratch/update-output"
cmp "$scratch/artifact/godmode" "$scratch/automatic-home/.godmode/bin/godmode"
printf '  %s\n' 'Downloading Godmode 7.6.5' "$check Updated ~/.godmode/bin/godmode" \
    'Changes: https://github.com/lofimichael/godmode-cli/releases/tag/v7.6.5' | cmp - "$scratch/update-output"
[ -z "$(ls -A "$scratch/downloads")" ]

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

# godmodeup compares the installed version with the selected release first.
mkdir -p "$scratch/versioned/release" "$scratch/versioned-account" "$scratch/ascii-account"
for version in 7.6.3 7.6.4 7.6.5; do
    printf '%s\n' '#!/bin/sh' "printf 'godmode $version\\n'" > "$scratch/versioned/godmode-$version"
done
cp "$scratch/versioned/godmode-7.6.5" "$scratch/versioned/release/godmode"
cp "$repo/install.sh" "$scratch/versioned/release/install.sh"
tar -czf "$scratch/fixtures/$fixture_name" -C "$scratch/versioned/release" godmode install.sh
printf '%s  %s\n' "$(shasum -a 256 < "$scratch/fixtures/$fixture_name" | awk '{print $1}')" "$fixture_name" > "$scratch/fixtures/SHA256SUMS"
for pair in versioned-account:7.6.4 ascii-account:7.6.3; do
    old=$scratch/versioned/godmode-${pair#*:}
    HOME="$scratch/${pair%%:*}" sh "$repo/install.sh" --binary "$old" \
        --sha256 "$(shasum -a 256 < "$old" | awk '{print $1}')" --no-setup > /dev/null
done
updater=$scratch/versioned-account/.godmode/bin/godmodeup
HOME="$scratch/versioned-account" PATH="$mock_path" TERM=xterm-256color "$updater" > "$scratch/version-change-output"
printf '  %s\n' "Godmode 7.6.4 $(printf '\342\206\222') 7.6.5" "$check Updated ~/.godmode/bin/godmode" \
    'Changes: https://github.com/lofimichael/godmode-cli/releases/tag/v7.6.5' | cmp - "$scratch/version-change-output"
cmp "$scratch/versioned/godmode-7.6.5" "$scratch/versioned-account/.godmode/bin/godmode"
cmp "$scratch/versioned/godmode-7.6.4" "$scratch/versioned-account/.godmode/bin/godmode.previous"
# The same version downloads nothing, through the GitHub CLI or public HTTPS.
cp "$scratch/versioned-account/.godmode/bin/.godmode-install-receipt" "$scratch/receipt-before"
for gh_mode in success fail; do
    : > "$GODMODE_TEST_NETWORK_LOG"
    HOME="$scratch/versioned-account" GODMODE_TEST_GH_MODE=$gh_mode PATH="$mock_path" "$updater" > "$scratch/current-output"
    printf '  %s\n' 'Godmode 7.6.5 is up to date.' | cmp - "$scratch/current-output"
    if grep -q -e '^release download' -e '/releases/download/' "$GODMODE_TEST_NETWORK_LOG"; then
        echo 'an up-to-date godmodeup downloaded a release' >&2; exit 1
    fi
done
cmp "$scratch/receipt-before" "$scratch/versioned-account/.godmode/bin/.godmode-install-receipt"
cmp "$scratch/versioned/godmode-7.6.4" "$scratch/versioned-account/.godmode/bin/godmode.previous"
[ -z "$(ls -A "$scratch/downloads")" ]
# --force reinstalls the same version on request.
: > "$GODMODE_TEST_NETWORK_LOG"
HOME="$scratch/versioned-account" PATH="$mock_path" "$updater" --force > "$scratch/forced-output"
grep -q '^release download' "$GODMODE_TEST_NETWORK_LOG"
grep -qx '  Downloading Godmode 7.6.5' "$scratch/forced-output"
# Without Unicode, the arrow and check mark are ASCII.
HOME="$scratch/ascii-account" PATH="$mock_path" TERM=linux "$scratch/ascii-account/.godmode/bin/godmodeup" > "$scratch/ascii-output"
printf '  %s\n' 'Godmode 7.6.3 -> 7.6.5' '+ Updated ~/.godmode/bin/godmode' \
    'Changes: https://github.com/lofimichael/godmode-cli/releases/tag/v7.6.5' | cmp - "$scratch/ascii-output"

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
tty > "$GODMODE_TEST_SETUP_LOG.tty"
printf 'SETUP_WAITING\\n'
read -r reply
[ "$reply" = finish ] || exit 92
printf 'SETUP_FINISHED\\n'
''')
digest = hashlib.sha256(program.read_bytes()).hexdigest()
archive = scratch/'fixtures/godmode-v7.6.5-aarch64-apple-darwin.tar.gz'
with tarfile.open(archive, 'w:gz') as tar:
    tar.add(program, arcname='godmode')
    tar.add(repo/'install.sh', arcname='install.sh')
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
for mode in ['offline', 'automatic', 'no-color', 'dumb', 'bin-only-update', 'legacy-bin-update', 'explicit-home-update']:
    master, slave = os.openpty()
    device_name = os.ttyname(slave)
    root = scratch / ('tty-home-'+mode)
    env = dict(os.environ, GODMODE_TEST_SETUP_LOG=str(scratch/'setup-args'),
               PATH=str(scratch/'mock-bin')+':'+os.environ['PATH'])
    env.pop('GODMODE_HOME', None)
    env.pop('NO_COLOR', None)
    env['TERM'] = 'dumb' if mode == 'dumb' else 'xterm-256color'
    if mode == 'no-color':
        env['NO_COLOR'] = ''
    args = ['--home', str(root)]
    expected_args = ['--home', str(root), 'init']
    if mode == 'automatic':
        # The README command: a download with --path into a fresh account.
        account = scratch / 'account-automatic'
        account.mkdir()
        env['HOME'], env['SHELL'] = str(account), '/bin/zsh'
        root = account / '.godmode'
        args, expected_args = ['--path'], ['init']
    else:
        args += ['--binary', str(program), '--sha256', digest, '--setup']
    command = [sys.executable, '-c', wrapper, str(repo/'install.sh'), *args]
    if mode.endswith('-update'):
        account = scratch / ('account-'+mode)
        legacy = account / '.config/godmode'
        legacy.mkdir(parents=True)
        (legacy/'.env.godmode').write_text('SYNTHETIC_KEY=unchanged\n')
        env['HOME'] = str(account)
        selection = ['--home', str(root)] if mode == 'explicit-home-update' else ['--bin-dir', str(root/'bin')]
        subprocess.run(['sh', str(repo/'install.sh'), *selection, '--binary', str(program), '--sha256', digest],
                       env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        if mode == 'legacy-bin-update':
            receipt = root/'bin/.godmode-install-receipt'
            receipt.write_text(''.join(line for line in receipt.read_text().splitlines(True) if not line.startswith('home ')))
        command = [str(root/'bin/godmodeup'), '--binary', str(program), '--sha256', digest, '--setup']
        if mode != 'explicit-home-update':
            expected_args = ['init']
    process = subprocess.Popen(command,
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
        # Keep reading: the installer prints its PATH note after setup returns.
        deadline = time.monotonic() + 8
        while True:
            ready = select.select([master], [], [], .05)[0]
            chunk = os.read(master, 65536) if ready else b''
            output.extend(chunk)
            if process.poll() is not None and not chunk:
                break
            assert time.monotonic() < deadline, 'installer did not finish after setup'
        assert process.returncode == 0
        assert (scratch/'setup-args').read_text().splitlines() == expected_args, 'updater selected the wrong configuration home'
        assert (scratch/'setup-args.tty').read_text().strip() == device_name, 'setup used a controlling-TTY alias instead of the concrete device'
        assert not (root/'.env.godmode').exists()
        if mode in ['no-color', 'dumb']:
            assert b'\x1b[' not in output, 'color opt-out was ignored'
        else:
            assert b'\x1b[32m\xe2\x9c\x93\x1b[0m ' in output, 'interactive check mark was not green'
        before_setup = [line for line in output.split(b'SETUP_WAITING')[0].splitlines() if line.strip()]
        installed = b' '.join([b'Updated' if mode.endswith('-update') else b'Installed', str(root/'bin/godmode').encode()])
        if mode == 'automatic':
            # Exactly three lines before setup, the check marks green, paths through ~.
            done = b'  \x1b[32m\xe2\x9c\x93\x1b[0m '
            assert before_setup == [b'  Downloading Godmode 7.6.5', done + b'Installed ~/.godmode/bin/godmode',
                                    done + b'Added ~/.godmode/bin to PATH in ~/.zshenv'], before_setup
            assert (account/'.zshenv').is_file() and not (account/'.zshrc').exists()
        else:
            assert [line.replace(b'\x1b[32m', b'').replace(b'\x1b[0m', b'') for line in before_setup][-1] == b'  \xe2\x9c\x93 ' + installed
        if mode in ['bin-only-update', 'legacy-bin-update']:
            assert (legacy/'.env.godmode').read_text() == 'SYNTHETIC_KEY=unchanged\n'
            assert not (root/'env').exists(), 'bin-only update created a configuration home'
        # Install prints one PATH command after setup; an update without --path prints none.
        commands = [line for line in output.splitlines() if b'run:  ' in line]
        if mode.endswith('-update'):
            assert not commands, 'update printed setup or PATH commands'
        else:
            assert len(commands) == 1 and b'\x1b' not in commands[0], 'copyable command was styled'
            assert output.index(b'SETUP_FINISHED') < output.index(commands[0]), 'PATH note printed before setup'
        if mode == 'automatic':
            assert commands == [b'  Open a new terminal, or run:  . ~/.godmode/env'], commands
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
    assert b'\x1b[31m' in error and b'nothing replaced' in error
finally:
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    os.close(master); os.close(slave)
for name in ['automatic-output', 'public-output', 'repeat-output', 'fresh-output', 'version-change-output']:
    assert b'\x1b[' not in (scratch/name).read_bytes(), 'redirected output contained styling'

PY

# Missing/old Python fails before download, directory creation or replacement.
mkdir "$scratch/old-python"
printf '%s\n' '#!/bin/sh' 'exit 1' > "$scratch/old-python/python3"
chmod 755 "$scratch/old-python/python3"
: > "$GODMODE_TEST_NETWORK_LOG"
if PATH="$scratch/old-python:$mock_path" sh "$repo/install.sh" --no-setup --home "$scratch/python-home" > "$scratch/python-error" 2>&1; then
    echo 'unsupported Python was accepted' >&2; exit 1
fi
grep -q 'Python 3.9 or later is required' "$scratch/python-error"
[ ! -e "$scratch/python-home" ]
[ ! -s "$GODMODE_TEST_NETWORK_LOG" ]

mkdir "$scratch/no-python"
if PATH="$scratch/no-python" /bin/sh "$repo/install.sh" --no-setup --home "$scratch/no-python-home" > /dev/null 2>&1; then
    echo 'missing Python was accepted' >&2; exit 1
fi
[ ! -e "$scratch/no-python-home" ]
printf '%s\n' 'Installer tests passed (portable/native downloads, version check, Python requirement, checksums, no-clobber, quoted ~ commands, three-line output, piped setup and plain/color output).'
