"""Complete named credential files. No global selection, inheritance or value output."""
import json
import os
from pathlib import Path
import stat

from godmode_profile import Profile, _profile_directories
from godmode_store import SEAL_PREFIX, STORE_HEADER, Store, _store_directories, environment_name


def environment_profile(home, name="default"):
    name = environment_name(name)
    selected = home or os.environ.get("GODMODE_HOME") or os.environ.get("GODMODE_CONFIG_DIR")
    base = (Path(os.path.abspath(os.path.expanduser(str(selected or Path.home() / ".godmode"))))
            if name == "default" else Store(home, environment=name).config_dir)
    if name == "default":
        _profile_directories(base)
        return Profile(base)
    _store_directories(base)
    directory = base / "environments"
    for path in (directory, directory / name):
        if os.path.lexists(path):
            info = path.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o700):
                raise ValueError("Environment profile directories must be yours, real directories and mode 0700.")
    return Profile(directory / name)


def environment_show(home, name="default"):
    """Paths, saved names and profile field names only; no key or profile values."""
    store = Store(home, environment=name)
    states = store.states()
    profile = environment_profile(home, name)
    fields = sorted(profile.read())
    return {"name": store.environment, "path": str(store.env_path), "exists": store.exists(),
            "keys": sorted(key for key, state in states.items() if state == "set"),
            "key_count": sum(state == "set" for state in states.values()),
            "states": states, "profile_path": str(profile.path), "profile_fields": fields,
            "profile_count": len(fields)}


def environment_list(home):
    """List complete files in this home; default is shown even before first setup."""
    base = Store(home).config_dir
    _store_directories(base)
    names = ["default"]
    if base.exists():
        for path in sorted(base.iterdir()):
            if not path.name.startswith(".env.godmode."):
                continue
            name = path.name[len(".env.godmode."):]
            try:
                environment_name(name)
            except ValueError:
                continue
            if name != "default":
                names.append(name)
    return [environment_show(home, name) for name in names]


def environment_create(home, name, copy_from=None):
    """Create only: empty sealed file or an exact same-home snapshot, under one lock."""
    name = environment_name(name)
    source_name = environment_name(copy_from) if copy_from is not None else None
    # Every environment resolves the same physical home and shared seal.key.
    target = Store(home, environment=name)
    source = Store(target.config_dir, environment=source_name) if source_name is not None else None
    environment_profile(home, name).read()  # Refuse unsafe profile paths before any credential write.
    with target._writer() as directory:
        if target.exists():
            raise ValueError("Environment already exists; its file was not changed.")
        text, snapshot = STORE_HEADER, None
        if source is not None:
            source._git_guard()
            text, snapshot = source._read()
            if snapshot is None:
                raise ValueError("Source environment is not saved in this home. See godmode env list; use --home for a different home.")
            # Validate the readable structure before creating anything; never decrypt.
            source.states()
            if SEAL_PREFIX in text:
                target._git_guard("seal.key")
                source._key()  # Validate the shared seal file, without generating a replacement.
        else:
            target._git_guard("seal.key")
            target._key(create=True)

        def check_source():
            if source is not None and source._read()[1] != snapshot:
                raise ValueError("The source environment changed before copying; retry.")

        target._write(text, None, directory, create_only=True, source_check=check_source)
        if target.sealed(text):
            target._guide()
    return environment_show(home, name)


def environment_command(home, args):
    if not args or args in (["list"], ["list", "--json"]):
        rows = environment_list(home)
        if args == ["list", "--json"]:
            print(json.dumps(rows, indent=2, sort_keys=True))
        else:
            for row in rows:
                print(row["name"])
        return 0
    if args[0] == "show" and len(args) == 2:
        details = environment_show(home, args[1])
        if not details["exists"]:
            raise ValueError("Environment is not saved. Create it with godmode env create NAME.")
        print(json.dumps(details, indent=2, sort_keys=True))
        return 0
    if args[0] == "create" and (len(args) == 2 or (len(args) == 4 and args[2] == "--copy")):
        details = environment_create(home, args[1], args[3] if len(args) == 4 else None)
        print("Environment " + details["name"] + " created at " + details["path"] + "."
              + (" Its keys are an independent snapshot; later changes do not carry over." if len(args) == 4 else " Its key file is empty.")
              + " Business profile: " + details["profile_path"] + ".")
        return 0
    raise ValueError("Use: godmode env [list [--json] | create NAME [--copy SOURCE] | show NAME].")
