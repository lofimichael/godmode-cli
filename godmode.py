#!/usr/bin/env python3
"""Godmode: choose a key, paste a value, save one local .env file."""
import sys
if sys.version_info < (3, 9):
    sys.exit('Godmode needs Python 3.9 or newer. No files changed.')

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import textwrap
from urllib.parse import urlsplit

# These imports become ordinary, readable source sections in the installed script.
sys.path.insert(0, str(Path(__file__).resolve().parent / 'lib'))
from godmode_store import Store, valid_key
from godmode_terminal import Cancelled, read_choice, read_secret, style

VERSION = '0.7.0'
PROVIDERS = None  # The build script inserts the plain provider data here.


def catalog():
    if PROVIDERS is not None:
        return PROVIDERS
    return json.loads(Path(__file__).with_name('providers.json').read_text())


def line(text='', role=None):
    print(style(text, role) if role else text, flush=True)


def rule():
    line('─' * min(76, shutil.get_terminal_size((80, 24)).columns - 2), 'accent')


def wrapped(text):
    for part in textwrap.wrap(text, max(30, min(76, shutil.get_terminal_size((80, 24)).columns - 2))):
        line(part)


def banner(store):
    line()
    line('  ╔═╗╔═╗╔╦╗╔╦╗╔═╗╔╦╗╔═╗', 'accent')
    line('  ║ ╦║ ║ ║║║║║║ ║ ║║║╣ ', 'accent')
    line('  ╚═╝╚═╝═╩╝╩ ╩╚═╝═╩╝╚═╝', 'accent')
    line()
    line('Godmode setup', 'title')
    line(str(store.env_path))
    line('One local file. Enter keeps an existing key; Ctrl-C leaves setup.')
    rule()


def prepare(store, accepted=False):
    if not store.exists():
        line('No existing Godmode setup found', 'warning')
        wrapped('These keys let agents act as you. The provider does not give a shit whether a destructive request was a mistake. Check the account and permissions before handing over access.')
        wrapped('Values stay in one plaintext file, readable by programs running as you. Nothing here signs in to providers or proves a key works.')
        if not accepted:
            read_choice('Type GODMODE to continue', ['GODMODE'])
    store.initialize()


def edit_file(store):
    if not sys.stdin.isatty():
        raise ValueError('Open the editor from a terminal.')
    editor = shutil.which('nano')
    if not editor:
        raise ValueError('nano was not found. Open the path printed by godmode path in your editor.')
    prepare(store)
    line('Opening nano; values are visible inside the editor.', 'warning')
    context = {k: v for k, v in os.environ.items()
               if k in ('PATH', 'HOME', 'USER', 'LOGNAME', 'SHELL', 'TERM',
                        'COLORTERM', 'LANG', 'TMPDIR') or k.startswith('LC_')}
    return subprocess.call([editor, str(store.env_path)], env=context)


def open_page(url):
    if not url.startswith('https://') or any(ord(c) < 32 for c in url):
        raise ValueError('Provider link must be HTTPS.')
    opener = shutil.which('open' if sys.platform == 'darwin' else 'xdg-open')
    if not opener:
        line(url)
        return
    subprocess.run([opener, url], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','USER','LANG','DISPLAY','WAYLAND_DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS')})


def populate(store, key):
    name = key['name']
    line()
    line(name, 'title')
    if key.get('usage'):
        wrapped(key['usage'])
    if store.states().get(name) == 'set':
        line('Already saved. Enter keeps it; paste to replace it.')
    while True:
        value = read_secret('Paste ' + name + ' (masked; Enter saves, empty skips):')
        if not value:
            line('Kept existing value.' if store.states().get(name) == 'set' else 'Skipped.')
            return
        try:
            store.set(name, value)
        except ValueError as error:
            line(str(error), 'error')
            continue
        finally:
            value = None
        line(name + ' saved.', 'success')
        return


def provider_setup(store, provider):
    line()
    line(provider['name'], 'title')
    wrapped(provider['purpose'])
    links = {'l': provider.get('login', provider['console']), 'o': provider['console'], 'd': provider['docs']}
    for key, label in [('l','Sign in'), ('o','API keys'), ('d','Documentation')]:
        line('  [' + key + '] ' + label.ljust(15) + urlsplit(links[key]).netloc, 'accent')
    line('  [?] Full links and instructions')
    while True:
        choice = read_choice('Enter to add keys; l sign in / o API keys / d docs / s skip provider:', ['', 'l','o','d','s','?'])
        if choice in links:
            open_page(links[choice])
        elif choice == '?':
            for label, url in [('Sign in',links['l']),('API keys',links['o']),('Docs',links['d'])]:
                line(label + ': ' + url)
            for key in provider['key']:
                line(key['name'], 'title')
                for step in key.get('steps',[]):
                    wrapped(step)
        elif choice == 's':
            return
        else:
            break
    for key in provider['key']:
        populate(store, key)


def setup(store, provider_id=None):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError('Setup needs a terminal. Use set KEY --stdin for redirected input.')
    providers = catalog()
    selected = next((p for p in providers if p['id'] == provider_id), None)
    if provider_id and selected is None:
        raise ValueError('Unknown provider. Run godmode to see the list.')
    banner(store)
    prepare(store)
    if selected:
        provider_setup(store, selected)
        return
    while True:
        states = store.states()
        line()
        line('PROVIDERS', 'title')
        for index, provider in enumerate(providers, 1):
            saved = sum(states.get(k['name']) == 'set' for k in provider['key'])
            total = len(provider['key'])
            line(style('  %2d  ' % index, 'accent') + provider['name'].ljust(30) + '  ' +
                 style('%d/%d saved' % (saved, total), 'success' if saved == total else None))
        line()
        line('  e  Edit the file in nano       Custom key: godmode set NAME')
        choices = ['','e'] + [str(i) for i in range(1,len(providers)+1)] + [p['id'] for p in providers]
        answer = read_choice('Provider number or name (Enter finishes):', choices)
        if not answer:
            line('Setup finished. ' + str(store.env_path), 'success')
            return
        if answer == 'e':
            edit_file(store)
            continue
        selected = providers[int(answer)-1] if answer.isdigit() else next(p for p in providers if p['id']==answer)
        provider_setup(store, selected)


class Arguments(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'godmode: invalid arguments; use --help. Paste values at the prompt, never in a command.\n')


def main():
    parser = Arguments(description='Masked key entry for one ordinary .env.godmode file.')
    parser.add_argument('command', nargs='?', default='setup', help='setup, set KEY, edit, path, or picard')
    parser.add_argument('name', nargs='?', help='provider, key name, or Picard action')
    parser.add_argument('--home', '--config-dir', dest='home', help='Godmode home; existing legacy home is detected')
    parser.add_argument('--stdin', action='store_true', help='read one value from a pipe instead of the masked prompt')
    parser.add_argument('--version', action='version', version='godmode ' + VERSION)
    parser.add_argument('--accept-disclaimer', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--state-dir', help=argparse.SUPPRESS)
    parser.add_argument('--no-motion', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.command == 'picard':
        # Optional media code never receives a Store or opens the credential file.
        from godmode_picard import picard
        media_state = args.state_dir or (str(Path(args.home) / 'state') if args.home else None)
        return picard(args.name or 'link', media_state)
    store = Store(args.home)
    if args.command == 'path' and not args.name:
        line(str(store.env_path))
    elif args.command == 'edit' and not args.name:
        return edit_file(store)
    elif args.command in ('setup','onboard'):
        setup(store, args.name)
    elif args.command == 'init' and not args.name:
        prepare(store, accepted=True) if args.accept_disclaimer else setup(store)
    elif args.command == 'set' and args.name:
        valid_key(args.name)
        if args.stdin:
            if sys.stdin.isatty():
                raise ValueError('--stdin requires a pipe. Omit it for masked entry.')
            value = sys.stdin.read(1_048_577)
            store.set(args.name, value)
            line(args.name + ' saved.', 'success')
        else:
            prepare(store)
            populate(store, {'name':args.name})
    else:
        parser.error('unknown command')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (Cancelled, KeyboardInterrupt):
        line('\nCancelled. Previously saved keys were kept.')
        sys.exit(130)
    except ValueError as error:
        print('godmode: ' + str(error), file=sys.stderr)
        sys.exit(2)
    except (OSError, subprocess.SubprocessError):
        print('godmode: could not complete the local operation. No credential details displayed.', file=sys.stderr)
        sys.exit(2)
