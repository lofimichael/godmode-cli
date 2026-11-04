"""One ordinary .env.godmode file. No shell evaluation, database or setup state."""
import contextlib
import fcntl
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
            raise ValueError("Multiline credentials must be a valid JSON object.") from None
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


def _store_stamp(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_mode, info.st_uid, info.st_nlink)


def _store_directories(path, create=False):
    for directory in reversed((path,) + tuple(path.parents)):
        if create and not os.path.lexists(directory):
            directory.mkdir(mode=0o700)
        if os.path.lexists(directory) and not stat.S_ISDIR(directory.lstat().st_mode):
            raise ValueError("Godmode paths must not contain symlinks or non-directories.")
    if path.exists():
        info = path.stat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise ValueError("The Godmode directory must be yours and not writable by other users.")


class Store:
    def __init__(self, home=None):
        selected = home or os.environ.get("GODMODE_HOME") or os.environ.get("GODMODE_CONFIG_DIR")
        if selected is None:
            selected = Path.home() / ".godmode"
            legacy = Path.home() / ".config/godmode"
            markers = (".env.godmode", "providers.toml", "AGENTS.md")
            if not any(os.path.lexists(selected / name) for name in markers) and os.path.lexists(legacy):
                selected = legacy
        self.config_dir = Path(os.path.abspath(os.path.expanduser(str(selected))))
        self.env_path = self.config_dir / ".env.godmode"

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

    def _git_guard(self):
        if not any((parent / ".git").exists() for parent in (self.config_dir,) + tuple(self.config_dir.parents)):
            return
        env = {"PATH": os.environ.get("PATH", ""), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
        base = ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-C", str(self.config_dir)]
        def git(args):
            return subprocess.run(base + args, env=env, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
        try:
            if git(["ls-files", "--error-unmatch", "--", ".env.godmode"]) != 1 or git(["check-ignore", "-q", "--", ".env.godmode"]) != 0:
                raise ValueError("Keep .env.godmode ignored and untracked by Git before saving.")
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
        with self._writer() as directory:
            text, previous = self._read()
            if previous is None:
                self._write(text, previous, directory)

    def set(self, key, value):
        valid_key(key)
        value = normalize(value, key)
        with self._writer() as directory:
            text, previous = self._read()
            newline = "\r\n" if text.count("\r\n") > text.count("\n") - text.count("\r\n") else "\n"
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
