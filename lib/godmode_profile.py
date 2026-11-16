"""Optional, locally supplied facts. Plain JSON, separate from credentials."""
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

PROFILE_FIELDS = ("operator_name", "business_name", "legal_name", "website",
                  "public_email", "business_mailing_address")
PROFILE_MAX_SIZE = 64 * 1024


def _profile_stamp(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_mode, info.st_uid, info.st_nlink)


def _profile_directories(path, create=False):
    # As for keys: symlinks above the home are resolved; the home itself must be a real directory.
    path = Path(os.path.realpath(path.parent)) / path.name
    for directory in reversed((path,) + tuple(path.parents)):
        if create and not os.path.lexists(directory):
            directory.mkdir(mode=0o700)
        if os.path.lexists(directory) and not stat.S_ISDIR(directory.lstat().st_mode):
            home, text = os.path.expanduser("~").rstrip(os.sep), str(directory)
            shown = "~" + text[len(home):] if text.startswith(home + os.sep) else text
            raise ValueError(shown + " is a symlink or not a directory; Godmode needs a real directory "
                             "there. Use --home with the real path.")
    if path.exists():
        info = path.stat()
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("The profile directory must be yours and mode 0700.")


def _profile_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("The profile has duplicate JSON keys; fix it before editing.")
        result[key] = value
    return result


def _profile_constant(value):
    raise ValueError("The profile must contain standard JSON values.")


def _profile_encode(data):
    if not isinstance(data, dict):
        raise ValueError("The profile must be a JSON object.")
    for key in PROFILE_FIELDS:
        if key not in data:
            continue
        value = data[key]
        if not isinstance(value, str):
            raise ValueError("Profile field " + key + " must be text.")
        if any((ord(c) < 32 or 127 <= ord(c) < 160 or c in "\u2028\u2029")
               and not (key == "business_mailing_address" and c == "\n") for c in value):
            raise ValueError("Profile field " + key + " contains control characters.")
    try:
        encoded = (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True,
                              allow_nan=False) + "\n").encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError("The profile must contain valid UTF-8 JSON values.") from None
    if len(encoded) > PROFILE_MAX_SIZE:
        raise ValueError("The profile exceeds the 64 KiB limit.")
    return encoded


class Profile:
    def __init__(self, home, filename="profile.json"):
        self.home = Path(os.path.abspath(os.path.expanduser(str(home))))
        if filename not in ("profile.json", "context.json"):
            raise ValueError("Unknown profile file.")
        self.path = self.home / filename
        self._read_once = False
        self._snapshot = None

    def _load(self):
        try:
            _profile_directories(self.home)
            if not os.path.lexists(self.path):
                return {}, None
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as source:
                before = os.fstat(source.fileno())
                if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                        or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1):
                    raise ValueError("The profile file must be yours, regular, and mode 0600.")
                raw = source.read(PROFILE_MAX_SIZE + 1)
                if len(raw) > PROFILE_MAX_SIZE:
                    raise ValueError("The profile exceeds the 64 KiB limit.")
                snapshot = (_profile_stamp(before), raw)
                if (_profile_stamp(before) != _profile_stamp(os.fstat(source.fileno()))
                        or _profile_stamp(before) != _profile_stamp(self.path.lstat())):
                    raise ValueError("The profile changed while being read; retry.")
            try:
                data = json.loads(raw.decode("utf-8"), object_pairs_hook=_profile_pairs,
                                  parse_constant=_profile_constant)
            except (UnicodeError, json.JSONDecodeError, RecursionError):
                raise ValueError("The profile is not valid UTF-8 JSON; fix it before editing.") from None
            _profile_encode(data)
            return data, snapshot
        except OSError:
            raise ValueError("Cannot safely read the profile file.") from None

    def read(self):
        """Read all fields and remember the snapshot for the next write. Missing is {}."""
        data, snapshot = self._load()
        self._snapshot, self._read_once = snapshot, True
        return data

    def _git_guard(self):
        if not any((parent / ".git").exists() for parent in (self.home,) + tuple(self.home.parents)):
            return
        env = {"PATH": os.environ.get("PATH", ""), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
        command = ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-C", str(self.home)]
        def git(args):
            return subprocess.run(command + args, env=env, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
        if (git(["ls-files", "--error-unmatch", "--", self.path.name]) != 1
                or git(["check-ignore", "-q", "--", self.path.name]) != 0):
            raise ValueError("Keep " + self.path.name + " ignored and untracked by Git before saving.")

    def write(self, data):
        """Atomically replace the last-read snapshot; callers merge edits to keep unknown fields.

        Return False for unchanged data without rewriting or creating an empty profile.
        """
        encoded = _profile_encode(data)
        if not self._read_once:
            self.read()
        current, snapshot = self._load()
        if snapshot != self._snapshot:
            raise ValueError("The profile changed before saving; reopen it and retry.")
        if encoded == _profile_encode(current):
            return False
        directory, temporary = None, None
        try:
            _profile_directories(self.home, create=True)
            directory = os.open(self.home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise ValueError("Another editor is saving the profile; retry shortly.") from None
            self._git_guard()
            if self._load()[1] != self._snapshot:
                raise ValueError("The profile changed before saving; reopen it and retry.")
            fd, temporary = tempfile.mkstemp(prefix=".profile.", dir=self.home)
            with os.fdopen(fd, "wb") as target:
                os.fchmod(target.fileno(), 0o600)
                target.write(encoded)
                target.flush()
                os.fsync(target.fileno())
            if self._load()[1] != self._snapshot:
                raise ValueError("The profile changed before saving; reopen it and retry.")
            os.replace(temporary, self.path)
            os.fsync(directory)
            self.read()
            return True
        except OSError:
            raise ValueError("Could not save the profile file.") from None
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)
            if directory is not None:
                os.close(directory)
