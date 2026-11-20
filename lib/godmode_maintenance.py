"""Read-only local diagnostics and updates through the recorded installer."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys


def _maintenance_file(path, limit):
    """Read an owned, unlinked regular file without following a symlink."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as source:
            info = os.fstat(source.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o022 or info.st_nlink != 1 or info.st_size > limit):
                raise ValueError('The installed files must be yours, regular and not writable by other users.')
            data = source.read(limit + 1)
            after = os.fstat(source.fileno())
            current = path.lstat()
            stamp = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
            if len(data) > limit or stamp(info) != stamp(after) or stamp(info) != stamp(current):
                raise ValueError('An installed file changed during the check. Retry.')
            return data
    except OSError:
        raise ValueError('A recorded install is required. Install Godmode from https://get.godmode.build first.') from None


def managed_install():
    executable = os.environ.get('GODMODE_EXECUTABLE') or sys.argv[0]
    if not os.path.isabs(executable):
        executable = shutil.which(executable) or os.path.abspath(executable)
    executable = Path(executable)
    directory = executable.parent
    info = directory.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022):
        raise ValueError('The install directory must be yours and not writable by other users.')
    updater = directory / 'godmodeup'
    receipt = _maintenance_file(directory / '.godmode-install-receipt', 16384)
    try:
        lines = receipt.decode('utf-8').splitlines()
    except UnicodeError:
        raise ValueError('The install receipt is unreadable. Reinstall Godmode.') from None
    if lines.count('format 1') != 1:
        raise ValueError('The install receipt has an unknown format. Reinstall Godmode.')
    for name, path in (('godmode', executable), ('godmodeup', updater)):
        matches = [line.split() for line in lines if line.split()[:1] == [name]]
        if len(matches) != 1 or len(matches[0]) != 2 or not re.fullmatch('[a-f0-9]{64}', matches[0][1]):
            raise ValueError('The install receipt is incomplete. Reinstall Godmode.')
        digest = hashlib.sha256(_maintenance_file(path, 128 * 1024 * 1024)).hexdigest()
        if digest != matches[0][1]:
            raise ValueError('The installed ' + name + ' has changed. Godmode kept it in place; reinstall to replace it.')
    return updater


def doctor_report(store, profile, api, home=None):
    checks = []

    def shown(path):
        value, home = str(path), str(Path.home()) + os.sep
        return '~/' + value[len(home):] if value.startswith(home) else value

    def add(name, status, detail, action=None):
        item = dict(name=name, status=status, detail=detail)
        if action:
            item['action'] = action
        checks.append(item)

    context = api.get('ACTIVE_CONTEXT')
    environment = api.get('ACTIVE_ENVIRONMENT', 'default')
    prefix = 'godmode'
    selected_home = home or os.environ.get('GODMODE_HOME') or os.environ.get('GODMODE_CONFIG_DIR')
    if selected_home:
        prefix += ' --home ' + shlex.quote(str(selected_home))
    if environment != 'default':
        prefix += ' --env ' + environment
    if context is not None:
        prefix += ' --context ' + context.name
    add('Python', 'ok' if sys.version_info >= (3, 9) else 'error',
        '.'.join(str(part) for part in sys.version_info[:3]))
    try:
        base = getattr(store, 'store', store)
        if environment != 'default' and not base.exists():
            raise ValueError('The selected environment is not saved. Create it with godmode env create ' + environment + '.')
        states = base.states()
        broken = sorted(name for name, state in states.items() if state in ('duplicate', 'malformed'))
        if broken:
            add('Keys', 'error', 'Duplicate or unreadable names: ' + ', '.join(broken), prefix + ' migrate')
        else:
            names = [name for name, state in states.items() if state == 'set']
            # Authenticate sealed values in memory. No values enter the report.
            if names:
                base.values(names).clear()
            aliases = getattr(context, 'aliases', {})
            missing = sorted(name for name, target in aliases.items() if states.get(target) != 'set')
            if missing:
                add('Keys', 'error', 'Mapped keys are missing: ' + ', '.join(missing), prefix + ' loadout')
            else:
                add('Keys', 'ok' if names else 'warn', str(len(names)) + ' stored locally. ' + shown(store.env_path),
                    None if names else prefix + ' loadout')
            if aliases and not missing:
                add('Mappings', 'ok', str(len(aliases)) + ' aliases resolve inside this key file.')
        plain = store.plain_names() if store.exists() else []
        if plain:
            add('Sealing', 'warn', str(len(plain)) + ' values are plain text.', prefix + ' migrate')
        elif store.exists():
            add('Sealing', 'ok', 'Stored values are sealed or empty.')
    except (ValueError, OSError) as error:
        detail = str(error) if isinstance(error, ValueError) else 'The selected key file cannot be read safely.'
        add('Keys', 'error', detail,
            prefix + ' list')
    profile_path = ''
    try:
        profile = profile() if callable(profile) else profile
        profile_path = str(profile.path)
        data = profile.read()
        count = sum(bool(data.get(name)) for name in api['PROFILE_FIELDS'])
        add('Profile', 'ok', str(count) + ' optional fields; ' + shown(profile.path))
    except (ValueError, OSError) as error:
        detail = str(error) if isinstance(error, ValueError) else 'The business profile cannot be read safely.'
        add('Profile', 'error', detail, prefix + ' profile')
    try:
        targets = api['agent_targets']()
        count = sum(bool(target['added']) for target in targets)
        add('Agents', 'ok' if count else 'warn', str(count) + ' agent files contain Godmode instructions.',
            None if count else prefix + ' agents')
    except (ValueError, OSError):
        add('Agents', 'error', 'An agent instruction file cannot be checked.', prefix + ' agents')
    try:
        updater = managed_install()
        add('Updater', 'ok', 'Installed files match the receipt; ' + shown(updater))
    except (ValueError, OSError):
        add('Updater', 'warn', 'This executable has no matching install receipt.', 'https://get.godmode.build')
    return dict(ok=not any(item['status'] == 'error' for item in checks), checks=checks,
                version=api['VERSION'], environment=environment,
                context=context.name if context is not None else 'default',
                env_path=str(store.env_path), profile_path=profile_path)


def doctor_command(store, profile, api, args, home=None):
    if args not in ([], ['--json']):
        raise ValueError('Use: godmode doctor [--json].')
    report = doctor_report(store, profile, api, home=home)
    if args:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for check in report['checks']:
            print(check['status'].upper() + '  ' + check['name'] + ': ' + check['detail'])
            if check.get('action'):
                print('    ' + check['action'])
    return 0 if report['ok'] else 1


def update_command(args):
    if args and (len(args) != 2 or args[0] != '--version' or not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', args[1])):
        raise ValueError('Use: godmode update [--version vX.Y.Z].')
    updater = managed_install()
    # Updates need no provider keys, profile, auth token, shell hooks or selected
    # credential home. The sibling updater targets its own recorded installation.
    allowed = ('PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'LC_CTYPE',
               'TERM', 'COLORTERM', 'TMPDIR', 'NO_COLOR', 'CLICOLOR')
    environment = {name: os.environ[name] for name in allowed if name in os.environ}
    return subprocess.call(['/bin/sh', str(updater), '--install-only'] + args, env=environment)
