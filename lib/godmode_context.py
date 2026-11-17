"""Named business profiles and key-name aliases; credential values stay in the base store."""
import json
import os
from pathlib import Path
import re
import stat

from godmode_profile import Profile, _profile_directories
from godmode_store import normalize, valid_key


def context_name(name):
    if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,47}', name):
        raise ValueError('Use a context name starting with a lowercase letter, then letters, numbers, _ or - (48 characters maximum).')
    return name


def context_directory(home, name=None):
    base = Path(home)
    _profile_directories(base)
    directory = base / 'contexts'
    paths = [directory]
    if name is not None:
        directory = directory / context_name(name)
        paths.append(directory)
    for path in paths:
        if os.path.lexists(path):
            info = path.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o700):
                raise ValueError('Context directories must be yours, real directories and mode 0700.')
    return directory


class Context:
    def __init__(self, home, name):
        self.name = context_name(name)
        self.home = context_directory(home, name)
        self.config = Profile(self.home, filename='context.json')
        if not self.config.path.exists():
            raise ValueError('Context is not saved. Create it with godmode context create NAME.')
        self.data = self.config.read()
        if (set(self.data) != {'schema', 'aliases'} or type(self.data['schema']) is not int
                or self.data['schema'] != 1 or not isinstance(self.data['aliases'], dict)):
            raise ValueError('The context configuration is invalid.')
        self.aliases = self.data['aliases']
        for variable, saved in self.aliases.items():
            if not isinstance(saved, str):
                raise ValueError('Context mappings contain saved key names only.')
            valid_key(variable)
            valid_key(saved)

    def profile(self):
        return Profile(self.home)

    def map(self, variable, saved):
        aliases = dict(self.aliases)
        variable = valid_key(variable)
        if saved is None:
            aliases.pop(variable, None)
        else:
            aliases[variable] = valid_key(saved)
        self.config.write({'schema': 1, 'aliases': aliases})
        self.aliases = aliases
        self.data = {'schema': 1, 'aliases': aliases}


class ContextStore:
    def __init__(self, store, context):
        self.store, self.context = store, context

    def __getattr__(self, name):
        return getattr(self.store, name)

    def resolve(self, name):
        valid_key(name)
        return self.context.aliases.get(name, name)

    def plan(self, name):
        return self.store.plan(self.resolve(name))

    def set(self, name, value, expected_digest=None):
        self.store.set(self.resolve(name), normalize(value, name), expected_digest=expected_digest)

    def values(self, names):
        selected = {name: self.resolve(name) for name in names}
        # Resolve once. A missing override fails in the base store; it never
        # falls through to a shared value under the original variable name.
        values = self.store.values(list(dict.fromkeys(selected.values())))
        return {name: values[saved] for name, saved in selected.items()}

    def states(self):
        states = self.store.states() if self.store.exists() else {}
        result = dict(states)
        for variable, saved in self.context.aliases.items():
            result[variable] = states.get(saved, 'empty')
        return result

    def names(self):
        return sorted(name for name, state in self.states().items() if state == 'set')


def context_list(home, missing_selected=None):
    directory = context_directory(home)
    result = []
    if directory.exists():
        for path in sorted(directory.iterdir()):
            if re.fullmatch(r'[a-z][a-z0-9_-]{0,47}', path.name):
                if path.name == missing_selected and not os.path.lexists(path / 'context.json'):
                    context_directory(home, path.name)  # Missing metadata, not an unsafe directory.
                    continue  # Let a live session select Automatic or another saved business.
                context = Context(home, path.name)
                result.append({'name': context.name, 'profile_path': str(context.profile().path),
                               'keys': dict(context.aliases)})
    return result


def context_create(home, name):
    directory = context_directory(home, name)
    config = Profile(directory, filename='context.json')
    if os.path.lexists(config.path):
        raise ValueError('Context already exists; its files were not changed.')
    config.read()
    config.write({'schema': 1, 'aliases': {}})
    return Context(home, name)


def context_command(home, args):
    if not args or args == ['list']:
        for context in context_list(home):
            print(context['name'])
        return 0
    action = args[0]
    if action == 'create' and len(args) == 2:
        context_create(home, args[1])
        print('Context ' + args[1] + ' created. Its business profile is empty; unmapped keys use the selected store.')
        return 0
    if action in ('show', 'map', 'unmap') and len(args) >= 2:
        context = Context(home, args[1])
        if action == 'show' and len(args) == 2:
            print(json.dumps({'name': context.name, 'profile_path': str(context.profile().path),
                              'keys': context.aliases}, indent=2, sort_keys=True))
            return 0
        if action == 'map' and len(args) == 4:
            context.map(args[2], args[3])
            print(args[2] + ' uses ' + args[3] + ' in ' + context.name + '.')
            return 0
        if action == 'unmap' and len(args) == 3:
            context.map(args[2], None)
            print(args[2] + ' uses the shared store in ' + context.name + '.')
            return 0
    raise ValueError('Use: godmode context [list | create NAME | show NAME | map NAME VARIABLE SAVED_KEY | unmap NAME VARIABLE].')
