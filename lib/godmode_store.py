"""One .env.godmode file whose values are sealed. No shell evaluation, database or setup state."""
import base64
import contextlib
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import tempfile

STORE_MAX_SIZE = 1024 * 1024
STORE_ASSIGNMENT = re.compile(r"^[ \t]*(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*=(.*)$")
STORE_SEALED = "# godmode-sealed v1"
STORE_HEADER = (STORE_SEALED + "\n"
                "# Godmode keys. Values are sealed: reading this file shows names, never keys.\n"
                "#   godmode list                    the names of saved keys\n"
                "#   godmode run NAME -- command     run a command with that key in its environment\n"
                "#   godmode help                    how to use keys without exposing them\n")
SEAL_PREFIX = "sealed:v1:"
STORE_KEY_PROVIDERS = {}  # Catalog key name -> provider slug, filled in by the command line.
STORE_GUIDE_NAME = "STOP_AND_READ_ME_FOR_KEYS.md"
STORE_GUIDE = """# Looking for a credential? Stop here.

The keys in this folder are sealed. Do not open, cat, grep or copy .env.godmode or
seal.key: the file shows names and ciphertext, and seal.key is what unseals it.

Use the godmode command instead:

    godmode list                                   names of the saved keys
    godmode run GH_TOKEN -- gh repo list           a command with that key in its environment
    godmode run GMAIL_USER GMAIL_APP_PASSWORD -- python3 check_inbox.py
    godmode set NAME                               save or replace a key
    godmode set ACME_AUTH_JSON --stdin < credential.json
    godmode help                                   the whole guide

The program reads each key from its environment, for example os.environ["GH_TOKEN"].
Pass only the keys it needs, and never print one: no echo, printenv, env or set -x.
A name missing from godmode list is not saved. Saved means stored, not verified.
Keys, passwords and provider credential JSON use the same set/run commands.
Choose the JSON type the consuming tool expects; a permissions policy is not a login.

If a key is rejected or has expired, run godmode help: it explains how to replace it.
"""


def _seal_parts(key, nonce, data):
    """Keystream and tag for one value: HMAC-SHA256 in counter mode, then HMAC-SHA256 over the result.

    Sealing keeps values out of anything that reads the file as text (cat, grep, editors,
    transcripts, copies of the file). It is not a lock against programs running as you,
    which can ask godmode for a key, or read seal.key and the file together.
    """
    stream_key = hmac.new(key, b"godmode stream", hashlib.sha256).digest()
    mac_key = hmac.new(key, b"godmode mac", hashlib.sha256).digest()
    blocks = (hmac.new(stream_key, nonce + n.to_bytes(8, "big"), hashlib.sha256).digest()
              for n in range(-(-len(data) // 32)))
    stream = b"".join(blocks)[:len(data)]
    return stream, mac_key


def seal(key, name, value):
    """Encrypt one value, bound to its name so it cannot be moved to another key."""
    nonce, data = os.urandom(16), value.encode("utf-8")
    stream, mac_key = _seal_parts(key, nonce, data)
    body = nonce + bytes(a ^ b for a, b in zip(data, stream))
    tag = hmac.new(mac_key, b"v1:" + name.encode() + b":" + body, hashlib.sha256).digest()[:16]
    return SEAL_PREFIX + base64.urlsafe_b64encode(body + tag).decode().rstrip("=")


def unseal(key, name, token):
    try:
        text = token[len(SEAL_PREFIX):]
        raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (ValueError, TypeError):
        raise ValueError("A sealed value for " + name + " is damaged.") from None
    body, tag = raw[:-16], raw[-16:]
    if len(body) < 16:
        raise ValueError("A sealed value for " + name + " is damaged.")
    stream, mac_key = _seal_parts(key, body[:16], body[16:])
    expected = hmac.new(mac_key, b"v1:" + name.encode() + b":" + body, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(tag, expected):
        raise ValueError("The sealed value for " + name + " does not match this computer's seal.key.")
    return bytes(a ^ b for a, b in zip(body[16:], stream)).decode("utf-8")


def valid_key(key):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        raise ValueError("Use a key name containing letters, numbers and underscores.")
    return key


def normalize(value, key=""):
    try:
        if len(value.encode("utf-8")) > STORE_MAX_SIZE:
            raise ValueError("Credential exceeds the 1 MiB limit.")
    except UnicodeError:
        raise ValueError("Credential is not valid UTF-8.") from None
    value = value.rstrip("\r\n")
    if key.endswith("_JSON") or "\n" in value or "\r" in value:
        try:
            parsed = json.loads(value)
            if not isinstance(parsed, dict):
                raise ValueError()
            value = json.dumps(parsed, separators=(",", ":"), ensure_ascii=False)
        except (ValueError, RecursionError):
            if "\n" in value or "\r" in value:
                raise ValueError("Multiline credentials must be a valid JSON object.") from None
            raise ValueError("This key needs the JSON key file's contents, starting with {.") from None
    if not value:
        raise ValueError("Nothing entered; the existing value was kept.")
    if any(ord(c) < 32 or 127 <= ord(c) < 160 or c in "\u2028\u2029" for c in value):
        raise ValueError("Credentials cannot contain control characters.")
    if len(value.encode("utf-8")) > STORE_MAX_SIZE:
        raise ValueError("Credential exceeds the 1 MiB limit.")
    return value


def _store_lines(text):
    """Leave multiline or unfinished manual shell quoting to the user's editor."""
    lines = []
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        if line[len(line.splitlines()[0]):] not in ("", "\n", "\r\n"):
            # A lone CR, form feed or Unicode line separator would merge lines on rewrite.
            raise ValueError("Existing file has unusual line breaks. Use godmode edit to edit it in nano.")
        quote, escaped, word = None, False, False
        for index, char in enumerate(content):
            if escaped:
                escaped, word = False, True
            elif quote == "'":
                if char == "'":
                    quote = None
            elif char == "\\":
                escaped = True
            elif quote == '"':
                if char == '"':
                    quote = None
            elif char in "'\"":
                quote, word = char, True
            elif char == "#" and not word:
                content = content[:index]
                break  # A shell comment starts between words, not inside one.
            else:
                word = not char.isspace()
        if quote or escaped:
            raise ValueError("Existing file has multiline or unfinished quoting. Use godmode edit to edit it in nano.")
        lines.append((line, content))
    return lines


def _store_newline(text):
    """The file's dominant line ending, used for an appended line."""
    return "\r\n" if text.count("\r\n") > text.count("\n") - text.count("\r\n") else "\n"


def _store_stamp(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_mode, info.st_uid, info.st_nlink)


def _store_directories(path, create=False):
    # Symlinks above the home (a linked /home, macOS /var and /tmp) belong to the system and
    # are resolved. The home and everything Godmode creates must be real directories.
    path = Path(os.path.realpath(path.parent)) / path.name
    for directory in reversed((path,) + tuple(path.parents)):
        if create and not os.path.lexists(directory):
            directory.mkdir(mode=0o700)
        if os.path.lexists(directory) and not stat.S_ISDIR(directory.lstat().st_mode):
            raise ValueError(_store_shown(directory) + " is a symlink or not a directory; Godmode needs a "
                             "real directory there. Use --home with the real path.")
    if path.exists():
        info = path.stat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise ValueError("The Godmode directory must be yours and not writable by other users.")


def _store_shown(path):
    home, text = os.path.expanduser("~").rstrip(os.sep), str(path)
    return "~" + text[len(home):] if text.startswith(home + os.sep) else text


def _holds_values(path):
    """Whether a key file assigns at least one value. An unreadable file counts, so its error shows."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as source:
            data = source.read(STORE_MAX_SIZE + 1)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return re.search(rb"(?m)^[ \t]*(?:export[ \t]+)?[A-Za-z_][A-Za-z0-9_]*[ \t]*=(?:[^\s]|[ \t]+[^\s#])", data) is not None


class Store:
    def __init__(self, home=None):
        selected = home or os.environ.get("GODMODE_HOME") or os.environ.get("GODMODE_CONFIG_DIR")
        if selected is None:
            selected = Path.home() / ".godmode"
            legacy = Path.home() / ".config/godmode"
            markers = (".env.godmode", "providers.toml", "AGENTS.md")
            if not any(os.path.lexists(selected / name) for name in markers) and _holds_values(legacy / ".env.godmode"):
                selected = legacy  # Keys saved before ~/.godmode existed. New files never start here.
        self.config_dir = Path(os.path.abspath(os.path.expanduser(str(selected))))
        self.env_path = self.config_dir / ".env.godmode"
        self.key_path = self.config_dir / "seal.key"

    def exists(self):
        return os.path.lexists(self.env_path)

    def _read(self):
        _store_directories(self.config_dir)
        if not self.exists():
            return "", None
        try:
            fd = os.open(self.env_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as source:
                before = os.fstat(source.fileno())
                if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                        or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1):
                    raise ValueError("The credential file must be yours, regular, and mode 0600.")
                data = source.read(STORE_MAX_SIZE + 1)
                if len(data) > STORE_MAX_SIZE:
                    raise ValueError("Credential file exceeds the 1 MiB limit.")
                if _store_stamp(before) != _store_stamp(os.fstat(source.fileno())) or _store_stamp(before) != _store_stamp(self.env_path.lstat()):
                    raise ValueError("The credential file changed while being read; retry.")
                return data.decode("utf-8"), _store_stamp(before)
        except (OSError, UnicodeError):
            raise ValueError("Cannot safely read the credential file.") from None

    def sealed(self, text=None):
        """Whether this file keeps its values sealed: new or emptied files, files with the
        header or any sealed value, and every home that has a seal.key."""
        text = self._read()[0] if text is None else text
        return (not text.strip() or SEAL_PREFIX in text or os.path.lexists(self.key_path)
                or any(line.rstrip("\r\n") == STORE_SEALED for line in text.splitlines()))

    def plain_names(self):
        """Names assigned a value that is not sealed, on any line, even one too odd to seal. Never values."""
        names = set()
        for _, content in _store_lines(self._read()[0].lstrip("\ufeff")):
            match = STORE_ASSIGNMENT.match(content)
            raw = match.group(2).strip().strip("'\"") if match else ""
            if raw and not raw.startswith(SEAL_PREFIX):
                names.add(match.group(1))
        return sorted(names)

    def loose(self):
        """How many lines show more than a name: plain values, your own comments, other text."""
        count = 0
        for line, content in _store_lines(self._read()[0].lstrip("\ufeff")):
            bare = line.rstrip("\r\n")
            if not bare.strip() or _own_line(bare):
                continue
            match = STORE_ASSIGNMENT.match(content)
            raw = match.group(2).strip().strip("'\"") if match else None
            if raw is not None and bare.rstrip() == content.rstrip() and (not raw or raw.startswith(SEAL_PREFIX)):
                continue
            count += 1
        return count

    def _key(self, create=False):
        """The 32-byte key in seal.key, beside the file: private, never printed."""
        try:
            fd = os.open(self.key_path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            if not create:
                raise ValueError("seal.key is missing from " + str(self.config_dir) + "; sealed values cannot be read without it.") from None
            key = os.urandom(32)
            fd = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w") as target:
                target.write(key.hex() + "\n")
                target.flush()
                os.fsync(target.fileno())
            return key
        except OSError:
            raise ValueError("Cannot safely read seal.key.") from None
        with os.fdopen(fd) as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise ValueError("seal.key must be yours, regular, and mode 0600.")
            try:
                key = bytes.fromhex(source.read(200).strip())
            except ValueError:
                key = b""
        if len(key) != 32:
            raise ValueError("seal.key is damaged; sealed values cannot be read.")
        return key

    def _assignments(self, text):
        """Every assignment as (name, raw text after =), in file order."""
        for _, content in _store_lines(text):
            match = STORE_ASSIGNMENT.match(content)
            if match:
                yield match.group(1), match.group(2)

    def values(self, names):
        """The values of the named keys, unsealed. Missing or unreadable names are refused together."""
        text, _ = self._read()
        found, problems = {}, []
        for name, raw in self._assignments(text):
            if name in names:
                found.setdefault(name, []).append(raw)
        key = None
        result = {}
        for name in names:
            raws = found.get(name, [])
            try:
                words = shlex.split(raws[0], comments=False) if len(raws) == 1 else None
            except ValueError:
                words = None
            if not raws or words in ([], [""]):
                problems.append(name + " is not saved")
            elif words is None or len(words) != 1:
                problems.append(name + (" is saved more than once" if len(raws) > 1 else " is unreadable"))
            elif words[0].startswith(SEAL_PREFIX):
                key = key or self._key()
                result[name] = unseal(key, name, words[0])
            else:
                result[name] = words[0]
        if problems:
            raise ValueError("; ".join(problems) + ". " + self._next(names, found))
        return result

    def _next(self, names, found):
        """One next step for a failed lookup: the provider to set up, a near name, or the list."""
        missing = [name for name in names if name not in found]
        saved = {name.casefold(): name for name in self.names()} if missing else {}
        for name in missing:
            if name.casefold() in saved:
                return "Did you mean " + saved[name.casefold()] + "?"
        slug = STORE_KEY_PROVIDERS.get(missing[0]) if missing else None
        return ("Ask the user to run: godmode setup " + slug) if slug else "See: godmode list"

    def names(self):
        """Names of the keys that have a value, sorted. Never values."""
        return sorted(name for name, state in self.states().items() if state == "set")

    def states(self):
        """Return key names and local presence only, never credential values."""
        text, _ = self._read()
        result = {}
        for _, content in _store_lines(text):
            match = STORE_ASSIGNMENT.match(content)
            if not match:
                continue
            key, raw = match.groups()
            if key in result:
                result[key] = "duplicate"
                continue
            try:
                words = shlex.split(raw, comments=False)
                if not words or words == [""]:
                    result[key] = "blank"
                else:
                    result[key] = "set" if len(words) == 1 else "malformed"
            except ValueError:
                result[key] = "malformed"
        return result

    def _in_git(self):
        return any((parent / ".git").exists() for parent in (self.config_dir,) + tuple(self.config_dir.parents))

    def _guide(self):
        """Leave a signpost beside a sealed file for agents that look in the folder. Never overwrites,
        and never adds an untracked file to a Git checkout. Best effort: the keys are already saved."""
        if self._in_git():
            return
        try:
            fd = os.open(self.config_dir / STORE_GUIDE_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
            with os.fdopen(fd, "w") as target:
                target.write(STORE_GUIDE)
        except OSError:
            pass

    def _git_guard(self, *names):
        """Refuse to write inside a Git checkout unless these files are ignored and untracked."""
        names = names or (".env.godmode",)
        if not self._in_git():
            return
        env = {"PATH": os.environ.get("PATH", ""), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
        base = ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-C", str(self.config_dir)]
        def git(args):
            return subprocess.run(base + args, env=env, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
        try:
            for name in names:
                if git(["ls-files", "--error-unmatch", "--", name]) != 1 or git(["check-ignore", "-q", "--", name]) != 0:
                    raise ValueError("Keep " + name + " ignored and untracked by Git before saving.")
        except OSError:
            raise ValueError("Git is required to check credential exclusion in this checkout.") from None

    @contextlib.contextmanager
    def _writer(self):
        try:
            _store_directories(self.config_dir, create=True)
            directory = os.open(self.config_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError:
            raise ValueError("Cannot open the Godmode directory for writing.") from None
        try:
            try:
                fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise ValueError("Another editor is saving this file; retry shortly.") from None
            self._git_guard()
            yield directory
        finally:
            os.close(directory)

    def _write(self, text, previous, directory):
        data = text.encode("utf-8")
        if len(data) > STORE_MAX_SIZE:
            raise ValueError("Credential file would exceed the 1 MiB limit.")
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(prefix=".env.godmode.", dir=self.config_dir)
            with os.fdopen(fd, "wb") as target:
                os.fchmod(target.fileno(), 0o600)
                target.write(data)
                target.flush()
                os.fsync(target.fileno())
            current = _store_stamp(self.env_path.lstat()) if self.exists() else None
            if current != previous:
                raise ValueError("The credential file changed before saving; retry.")
            os.replace(temporary, self.env_path)
            os.fsync(directory)
        except OSError:
            raise ValueError("Could not save the credential file.") from None
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)

    def initialize(self):
        """Create an empty file, sealed from the start, with its seal.key."""
        with self._writer() as directory:
            text, previous = self._read()
            if previous is None:
                self._git_guard("seal.key")
                self._key(create=True)
                self._write(STORE_HEADER, previous, directory)
            if self.sealed():
                self._guide()

    def plan(self, key):
        """Describe what set(key, value) changes, without reading any value.

        lines: 1-based numbers of the lines assigning key; set() rewrites the first
        as KEY=value and deletes the others. plain: there is exactly one, already
        written as KEY=... with a Unix line ending. kept_cr: the first one ends in
        CRLF, which set() keeps. crlf: a new key is appended with CRLF, the file's
        usual ending. separate: a new key needs a line break first because the file
        does not end with one.
        """
        valid_key(key)
        text, _ = self._read()
        rows = _store_lines(text)
        numbers = [number for number, (line, _) in enumerate(rows, 1)
                   if (STORE_ASSIGNMENT.match(line.rstrip("\r\n")) or [None, None])[1] == key]
        first = rows[numbers[0] - 1][0] if numbers else ""
        return {"lines": numbers, "sealed": self.sealed(text),
                "plain": len(numbers) == 1 and first.startswith(key + "=") and not first.endswith("\r\n"),
                "kept_cr": first.endswith("\r\n"),
                "crlf": _store_newline(text) == "\r\n",
                "separate": bool(text) and not text.endswith("\n")}

    def set(self, key, value, expected_digest=None):
        valid_key(key)
        value = normalize(value, key)
        with self._writer() as directory:
            text, previous = self._read()
            if expected_digest is not None and hashlib.sha256(text.encode("utf-8")).hexdigest() != expected_digest:
                raise ValueError("The key file changed after the preview. Open the key again.")
            if self.sealed(text):
                self._git_guard("seal.key")
                # A new seal.key only for a file holding no sealed values: never a second key.
                value = seal(self._key(create=SEAL_PREFIX not in text), key, value)
                if not any(line.rstrip("\r\n") == STORE_SEALED for line in text.splitlines()):
                    text = STORE_HEADER + (text if text.strip() else "")  # The header says how to use the file.
            newline = _store_newline(text)
            lines, replaced = [], False
            for line, _ in _store_lines(text):
                match = STORE_ASSIGNMENT.match(line.rstrip("\r\n"))
                if not match or match[1] != key:
                    lines.append(line)
                elif not replaced:
                    ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
                    lines.append(key + "=" + shlex.quote(value) + ending)
                    replaced = True
            if not replaced:
                if lines and not lines[-1].endswith("\n"):
                    lines.append(newline)
                lines.append(key + "=" + shlex.quote(value) + newline)
            self._write("".join(lines), previous, directory)
            if SEAL_PREFIX in value:
                self._guide()


STORE_MOVED = ("# Godmode keys moved to {target} and are sealed there.\n"
               "#   godmode list                    the names of saved keys\n"
               "#   godmode run NAME -- command     run a command with that key in its environment\n"
               "#   godmode help                    how to use keys without exposing them\n")
STORE_NOTES = "#\n# Comments from the old file, kept as they were:\n"
STORE_OWN_LINES = set((STORE_HEADER + STORE_MOVED + STORE_NOTES).splitlines())


def _own_line(bare):
    """A comment line Godmode itself writes: the header, or the note in a file whose keys moved."""
    return bare in STORE_OWN_LINES or (bare.startswith("# Godmode keys moved to ")
                                        and bare.endswith(" and are sealed there."))


def _sealing_rows(text, known=()):
    """Read a file for sealing: (keys, notes, problems).

    keys: {name: (line number, value)} for each assignment with a value, plain or sealed.
    notes: line numbers of the user's own # comment lines. problems: what blocks sealing,
    naming lines and keys only, never values.
    """
    rows = _store_lines(text.lstrip("\ufeff"))
    names = set(known) | {match.group(1) for match in (STORE_ASSIGNMENT.match(c) for _, c in rows) if match}
    keys, notes, problems = {}, [], []
    for number, (line, content) in enumerate(rows, 1):
        bare = line.rstrip("\r\n")
        if not bare.strip():
            continue
        match = STORE_ASSIGNMENT.match(content)
        if not match:
            if not bare.lstrip().startswith("#"):
                problems.append("line %d is not NAME=value" % number)
            elif not _own_line(bare):
                notes.append(number)
            continue
        name, raw = match.groups()
        where = "line %d (%s)" % (number, name)
        try:
            words = shlex.split(raw, comments=False)
        except ValueError:
            words = None
        value = words[0] if words else ""
        inside = sorted(other for other in names if "_" in other and other + "=" in value)  # Two lines run together.
        if bare.rstrip() != content.rstrip():
            problems.append(where + " has a comment after its value")
        elif name in keys:
            problems.append(name + " is saved more than once")
        elif words is None or len(words) > 1:
            problems.append(where + " has unquoted spaces in its value")
        elif inside:
            problems.append(where + " also holds " + inside[0] + "=, so put each key on its own line")
        elif value:
            if not value.startswith(SEAL_PREFIX):
                try:
                    value = normalize(value, name)
                except ValueError as error:
                    problems.append(where + ": " + str(error).rstrip("."))
                    continue
            keys[name] = (number, value)
    return keys, notes, problems


def _refuse(problems, store):
    raise ValueError("Nothing was changed. In " + str(store.env_path) + ", " + "; ".join(problems)
                     + ". Fix it in an editor, then try again.")


def _seal_file(store, directory, add, known=()):
    """Seal every plain value in store's file and add the keys in add, then read all back.

    A name already saved there must hold the same value as in add. Writes nothing on any
    problem. Returns how many plain values were sealed.
    """
    store._git_guard("seal.key")
    original, previous = store._read()
    text = original.lstrip("\ufeff")
    keys, notes, problems = _sealing_rows(text, known)
    if notes:  # Free text cannot be sealed, and the header says the file shows no keys.
        problems.insert(0, ("line %d is a comment" % notes[0] if len(notes) == 1 else
                            "lines " + ", ".join(map(str, notes)) + " are comments") + ", which a sealed file cannot keep")
    if problems:
        _refuse(problems, store)
    plain = {name: value for name, (_, value) in keys.items() if not value.startswith(SEAL_PREFIX)}
    differ = sorted(name for name in add if name in plain and plain[name] != add[name])
    created = not os.path.lexists(store.key_path)
    key = store._key(create=len(plain) == len(keys))  # Never a second key beside sealed values.
    written = False
    try:
        differ += sorted(name for name in add if name in keys and name not in plain
                         and unseal(key, name, keys[name][1]) != add[name])
        if differ:
            raise ValueError("Nothing was moved: " + ", ".join(differ) + (" has" if len(differ) == 1 else " have")
                             + " a different value in " + str(store.env_path) + ". Keep one of them, then try again.")
        _seal_lines(store, directory, text, previous, key, keys, plain, add)
        written = True
        expected = dict(plain, **add)
        try:
            same = store.values(sorted(expected)) == expected
        except ValueError:
            same = False
        if not same:
            raise ValueError("The sealed copy did not read back correctly, so nothing was changed.")
    except BaseException:
        if written:  # Put the file back as it was; the caller changes nothing else.
            if previous is None:
                os.unlink(store.env_path)
            else:
                store._write(original, _store_stamp(store.env_path.lstat()), directory)
        if created and os.path.lexists(store.key_path):
            os.unlink(store.key_path)
        raise
    store._guide()
    return len(plain)


def _seal_lines(store, directory, text, previous, key, keys, plain, add):
    """Write text with every plain value sealed and the keys in add appended, under the header."""
    pending = {name: value for name, value in add.items() if name not in keys}
    newline = _store_newline(text)
    lines = [] if any(line.rstrip("\r\n") == STORE_SEALED for line in text.splitlines()) else [STORE_HEADER]
    added = set()
    for number, (line, content) in enumerate(_store_lines(text), 1):
        match = STORE_ASSIGNMENT.match(content)
        name = match.group(1) if match else None
        ending = "\r\n" if line.endswith("\r\n") else "\n"
        if (name in keys and number != keys[name][0]) or name in added:
            continue  # A blank NAME= beside the saved value: dropped, so the name is saved once.
        if name in plain:
            lines.append(name + "=" + seal(key, name, plain[name]) + ending)
        elif name in pending:
            lines.append(name + "=" + seal(key, name, pending.pop(name)) + ending)
            added.add(name)
        else:
            lines.append(line)
    if lines and not lines[-1].endswith("\n"):
        lines.append(newline)
    lines += [name + "=" + seal(key, name, value) + newline for name, value in sorted(pending.items())]
    store._write("".join(lines), previous, directory)


def plain_source(store, explicit=False):
    """(source, target) for sealing plain-text keys, or None when there are none.

    Plain keys in ~/.config/godmode move to ~/.godmode, joining any keys already sealed
    there, unless a home was chosen explicitly. Plain values anywhere else are sealed
    where they are.
    """
    legacy = Store(Path.home() / ".config/godmode")
    if not explicit and _holds_values(legacy.env_path):
        try:
            found = not legacy.sealed() and legacy.plain_names()
        except ValueError as error:  # Say which file, since it may not be the one in use.
            raise ValueError(str(legacy.env_path) + ": " + str(error)) from None
        if found:
            return legacy, Store(Path.home() / ".godmode")
    if store.exists() and (store.plain_names() or (store.sealed() and store.loose())):
        return store, store  # Sealing in place names any line it cannot seal.
    return None


def move_and_seal(source, target, known=()):
    """Seal every plain-text value, in place or by moving it from source to target.

    Moving joins the keys already in target, where a name both files hold must have the
    same value, so an interrupted move can simply run again. Nothing changes unless every
    value parses and the sealed file reads back identically; then source is rewritten to
    a note saying where its keys went, followed by its own # comment lines. known: key
    names that must not appear inside another key's value. Returns (keys sealed, comment
    lines left as plain text).
    """
    if target.env_path == source.env_path:
        with source._writer() as directory:
            keys, notes, problems = _sealing_rows(source._read()[0], known)
            if not problems and not notes and all(value.startswith(SEAL_PREFIX) for _, value in keys.values()):
                raise ValueError(str(source.env_path) + " has no plain-text keys to seal.")
            return _seal_file(source, directory, {}, known), 0  # A sealed file keeps no comments.
    with source._writer() as source_directory:  # Held until the source is rewritten.
        text, stamp = source._read()
        keys, notes, problems = _sealing_rows(text, known)
        if problems:
            _refuse(problems, source)
        if any(value.startswith(SEAL_PREFIX) for _, value in keys.values()) or source.sealed(text):
            raise ValueError(str(source.env_path) + " is already sealed. Seal it where it is: godmode --home "
                             + str(source.config_dir) + " migrate")
        moving = {name: value for name, (_, value) in keys.items()}
        with target._writer() as target_directory:
            _seal_file(target, target_directory, moving, known)
        rows = _store_lines(text.lstrip("\ufeff"))
        kept = "".join(rows[number - 1][0].rstrip("\r\n") + "\n" for number in notes)
        source._write(STORE_MOVED.format(target=str(target.env_path)) + (STORE_NOTES + kept if kept else ""),
                      stamp, source_directory)
    return len(moving), len(notes)
