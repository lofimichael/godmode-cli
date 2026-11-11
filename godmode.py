#!/usr/bin/env python3
"""Godmode: choose a key, paste a value, see the edit it makes, save one local .env file."""
import sys
if sys.version_info < (3, 9):
    sys.exit('Godmode needs Python 3.9 or newer. No files changed.')

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import textwrap
from urllib.parse import urlsplit

# These imports become ordinary, readable source sections in the installed script.
sys.path.insert(0, str(Path(__file__).resolve().parent / 'lib'))
from godmode_store import Store, normalize, valid_key
from godmode_terminal import Back, Cancelled, Prompt, cells, columns, drawn_height, fit, glyph, mask
from godmode_terminal import read_choice, read_secret, screen_rows, style

VERSION = '0.8.0'
PROVIDERS = None  # The build script inserts the plain provider data here.
LOGO = ['╔═╗╔═╗╔╦╗╔╦╗╔═╗╔╦╗╔═╗', '║ ╦║ ║ ║║║║║║ ║ ║║║╣ ', '╚═╝╚═╝═╩╝╩ ╩╚═╝═╩╝╚═╝']


def catalog():
    if PROVIDERS is not None:
        return PROVIDERS
    return json.loads(Path(__file__).with_name('providers.json').read_text())


def line(text='', role=None):
    print(style(text, role) if role else text, flush=True)


def wrap(text, indent=''):
    return textwrap.wrap(text, max(20, min(76, columns() - 2)),
                         initial_indent=indent, subsequent_indent=indent) or ['']


def wrapped(text, role=None):
    for part in wrap(text):
        line(part, role)


def fit_words(text, width):
    """Wrap prose for a prompt region so no row reaches the terminal's last column."""
    return textwrap.wrap(text, max(1, width - 1)) or ['']


def home_path(path):
    """A path as one shell word, with ~ for the home directory."""
    home, text = str(Path.home()).rstrip(os.sep), str(path)
    if text.startswith(home + os.sep):
        return '~/' + shlex.quote(text[len(home) + 1:])
    return shlex.quote(text)


def banner(store):
    side = ['', 'Keys for your agents, in one local file.', home_path(store.env_path)]
    line()
    if glyph('art', '') and columns() >= 72:
        for art, text in zip(LOGO, side):
            line('  ' + style(art, 'accent') + '   ' + text)
        return
    for art in (LOGO if glyph('art', '') else ['GODMODE']):
        line('  ' + style(art, 'accent'))
    line()
    line(side[1])
    line(side[2])


def prepare(store, accepted=False):
    if not store.exists():
        line()
        line('No Godmode setup here yet', 'warning')
        wrapped('These keys let agents act as you. The provider does not give a shit whether a destructive request was a mistake. Check the account and permissions before handing over access.')
        wrapped('Values stay in one plaintext file, readable by programs running as you. Nothing here signs in to providers or proves a key works.')
        line()
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
    """Start the browser on an HTTPS page. False when there is no opener or it fails at once."""
    if not url.startswith('https://') or any(ord(c) < 32 for c in url):
        raise ValueError('Provider link must be HTTPS.')
    opener = shutil.which('open' if sys.platform == 'darwin' else 'xdg-open')
    if not opener:
        return False
    # Detached, so an opener that runs the browser in the foreground cannot freeze the prompt.
    process = subprocess.Popen(
        [opener, url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
        env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','USER','LANG','DISPLAY','WAYLAND_DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS')})
    try:
        return process.wait(timeout=2) == 0
    except subprocess.TimeoutExpired:
        return True


def browse(url):
    """Prompt action: open a key page, or show its address to open by hand."""
    try:
        if open_page(url):
            return [style('Opened ' + urlsplit(url).netloc + ' in your browser.', 'accent'), '']
    except (OSError, subprocess.SubprocessError):
        pass
    return ['Open this page in your browser:', url, '']


def key_page(provider, key):
    """Where Tab goes for this key: its own page when it has one, else the provider's."""
    return key['console'] if 'console' in key else provider['console']


def guide(provider, key):
    """Prompt action: print a key's steps and full links."""
    rows = []
    for number, step in enumerate(key.get('steps', []), 1):
        parts = wrap(step, '     ')
        rows += [style('%3d.' % number, 'accent') + parts[0][4:]] + parts[1:]
    rows.append('')
    links = (('Key page', key_page(provider, key)), ('Sign in', provider.get('login')), ('Docs', provider.get('docs')))
    rows += ['     ' + style(label.ljust(9), 'accent') + url for label, url in links if url]
    return rows + ['']


def shell_word(text):
    """Quote one shell word for display, preferring single quotes."""
    if "'" not in text:
        return "'" + text + "'"
    return '"' + re.sub(r'([\\"$`])', r'\\\1', text) + '"'


def save_command(name, shown, plan, path):
    """Shell words with the same effect on the file as saving. Godmode makes the edit itself.

    shown is the text after KEY= exactly as it is written, or a masked stand-in. The kind
    of command depends only on the file (plan is Store.plan(name)), never on the value,
    so the preview reveals nothing about hidden characters.
    """
    assignment = name + '=' + shown
    if not plan['lines']:
        # printf rather than echo: some shells' echo would turn a \n inside a key into a line break.
        newline = '\\r\\n' if plan['crlf'] else '\\n'
        layout = "'" + (newline if plan['separate'] else '') + '%s' + newline + "'"
        return ['printf', layout, shell_word(assignment), '>>', path]
    replacement = re.sub(r'([\\/&])', r'\\\1', assignment)
    sed = ['sed', '-i', "''"] if sys.platform == 'darwin' else ['sed', '-i']
    if plan['plain']:
        return sed + [shell_word('s/^' + name + '=.*/' + replacement + '/'), path]
    first, others = plan['lines'][0], plan['lines'][1:]
    edit = shell_word('%ds/.*/%s/' % (first, replacement))
    if not others:
        return sed + [edit, path]
    return sed + ['-e', edit] + [word for number in others for word in ('-e', "'%dd'" % number)] + [path]


def command_rows(words, width):
    """Lay out shell words as a person would, continuing long commands with a backslash."""
    rows, current = [], ''
    for word in words:
        joined = current + ' ' + word if current else word
        if current and cells(joined) + 2 > width - 1:
            rows.append(current + ' \\')
            current = '  ' + word
        else:
            current = joined
    rows.append(current)
    laid = []
    for row in rows:
        pieces = fit(row, width)
        laid.append(pieces[0])
        rest = row[len(pieces[0]):]
        while rest and width > 6:  # A word wider than the row continues indented.
            piece = fit('  ' + rest, width)[0]
            laid.append(piece)
            rest = rest[len(piece) - 2:]
        if rest:
            laid += fit(rest, width)
    return laid


def prompt_label(key):
    if key.get('prompt'):
        return key['prompt'] + ':'
    for suffix, word in (('_JSON', 'JSON key'), ('_PASSWORD', 'password'), ('_TOKEN', 'token'),
                         ('_SECRET', 'secret'), ('_KEY_ID', 'key ID'), ('_KEY', 'key')):
        if key['name'].endswith(suffix):
            return 'Paste your ' + word + ':'
    return 'Paste the value:'


def listed(numbers):
    words = [str(n) for n in numbers]
    return ', '.join(words[:-1]) + ' and ' + words[-1] if len(words) > 1 else words[0]


class KeyPrompt(Prompt):
    """The masked prompt, with a live preview of the edit Enter makes and where."""

    def __init__(self, store, key, provider=None, back=False):
        states = store.states()
        self.name, self.back = key['name'], back
        self.state = states.get(self.name)  # None, 'set', 'blank', 'duplicate' or 'malformed'
        self.saved = self.state == 'set'
        self.secret = key.get('secret', True)  # false for identifiers such as an email address
        self.typed = bool(key.get('prompt'))
        self.plan = store.plan(self.name)
        self.path = home_path(store.env_path)
        self.label = prompt_label(key)
        self.page = key_page(provider, key) if provider else None
        self.receipt = []
        self.actions = {}
        if self.page:
            self.actions['\t'] = lambda: browse(self.page)
        if provider:
            self.actions['?'] = lambda: guide(provider, key)

    def check(self, value):
        """Return (the value as it would be saved, or None; why it cannot be saved yet)."""
        if not value.rstrip('\r\n'):
            return None, None  # Nothing, or only a pasted line break: Enter skips.
        try:
            return normalize(value, self.name), None
        except ValueError as error:
            return None, str(error)

    def ready(self, value):
        return self.check(value)[1] is None

    def shown(self, clean, reveal):
        """The value in the command, quoted the way Store.set quotes the real one.

        Masked values that were typed are always quoted, so the quotes cannot hint at
        which keystroke added a character that needs them.
        """
        if not self.secret:
            return shlex.quote(clean)
        masked = mask(clean, reveal)
        if reveal and shlex.quote(clean) == clean:
            return masked
        return "'" + masked.replace("'", "'\"'\"'") + "'"

    def entry(self, value, clean, reveal):
        """What the input line shows after the label."""
        if not value.rstrip('\r\n'):
            return ''
        if not self.secret:
            return ''.join(c if c.isprintable() else '?' for c in (clean if clean is not None else value))
        return mask(clean if clean is not None else value, reveal)

    def command(self, shown, width):
        """The preview command as styled rows, and the index of the row holding the value."""
        words = ['$'] + save_command(self.name, shown, self.plan, self.path)
        rows, at = [], None
        for index, row in enumerate(command_rows(words, width)):
            if at is None and shown in row:
                at = index
            if row.startswith('$ '):
                row = style('$', 'accent') + row[1:]
            rows.append(row.replace(shown, style(shown, 'secret'), 1))
        return rows, at or 0

    def notes(self, clean, problem, reveal):
        plan, name, notes = self.plan, self.name, []
        if len(plan['lines']) > 1:
            notes.append(name + ' is on lines ' + listed(plan['lines']) + '. Saving keeps line '
                         + str(plan['lines'][0]) + ' and deletes the others.')
        elif plan['lines'] and not plan['plain']:
            notes.append('Line ' + str(plan['lines'][0]) + ' is rewritten as a plain ' + name + '= line.')
        if plan['kept_cr']:
            notes.append('Line ' + str(plan['lines'][0]) + ' keeps its Windows (CRLF) line ending.')
        if problem:
            return [(text, None) for text in notes] + [("Can't save this yet: " + problem, 'warning')]
        # Only when the ends are on screen anyway; otherwise this would describe hidden characters.
        if (clean and clean[0] == clean[-1] and clean[0] in '\'"' and len(clean) > 1
                and (not self.secret or (reveal and len(clean) >= 8))):
            notes.append('This value starts and ends with quote marks; they are saved as part of it.')
        if clean is not None:
            notes.append('Godmode makes this edit itself: one local file, mode 0600, nothing sent.')
        elif self.saved:
            notes.append('Your saved ' + name + ' stays unless you paste a new one.')
        elif self.state == 'malformed':
            notes.append('The saved ' + name + " line can't be read; paste to replace it.")
        elif self.state == 'duplicate':
            notes.append('Enter on its own leaves these lines as they are.')
        else:
            notes.append(('Type or paste' if self.typed else 'Paste') + ' to fill this in.')
        return [(text, None) for text in notes]

    def hint(self, value, ready):
        keys = []
        if not value.rstrip('\r\n'):
            keys += ['Tab opens ' + urlsplit(self.page).netloc] if self.page else []
            keys += ['? shows steps'] if '?' in self.actions else []
            keys.append('Enter keeps it' if self.saved else
                        'Enter leaves it' if self.state in ('duplicate', 'malformed') else 'Enter skips')
        else:
            keys += ['Enter saves'] if ready else []
            keys.append('Ctrl-U clears')
        keys.append('Esc ' + ('goes back' if self.back else 'cancels'))
        return glyph(' · ', ' | ').join(keys)

    def render(self, value, width, reveal=True):
        clean, problem = self.check(value)
        shown = self.shown(clean, reveal) if clean is not None else glyph('…', '...')
        bar = style(glyph('│ ', '| '), 'accent')
        command, at = self.command(shown, width - 2)
        command = [bar + row for row in command]
        label = fit_words(self.label, width)  # Long typed dots may wrap; the redraw counts that.
        entry = label[:-1] + [label[-1] + ' ' + style(self.entry(value, clean, reveal), 'secret')]
        rows = [style(row, 'title') for row in fit_words('What will be executed on your machine', width)]
        rows += command
        rows += [bar + style(row, role) for text, role in self.notes(clean, problem, reveal)
                 for row in fit_words(text, width - 2)]
        rows += [''] + [style(row, 'accent') for row in fit_words(self.hint(value, not problem), width)]
        # In a short window, give up the explanations first and keep the command with the value.
        room = screen_rows() - 1
        for choice in (rows + entry, command + entry, [command[at]] + entry):
            if drawn_height(choice, width) <= room:
                return choice
        return entry[-1:]

    def final(self, value, width, reveal, submitted):
        """Clear the preview. populate() prints the command as a receipt once the save succeeds."""
        clean, _ = self.check(value)
        self.receipt = []
        if submitted and clean is not None:
            bar = style(glyph('│ ', '| '), 'accent')
            self.receipt = [bar + row for row in self.command(self.shown(clean, reveal), width - 2)[0]]
        return []


def populate(store, key, provider=None, back=False):
    name = key['name']
    line()
    line(name, 'heading')
    if key.get('usage'):
        wrapped(key['usage'])
    line()
    while True:
        prompt = KeyPrompt(store, key, provider, back)
        try:
            value = read_secret(prompt)
        except Back:
            if back:
                line(('Not changed. Your saved ' + name + ' stays.') if prompt.saved else (name + ' was not saved.'))
            raise
        if not value.rstrip('\r\n'):
            line('Kept your saved ' + name + '.' if prompt.saved else
                 'Left ' + name + ' unchanged.' if prompt.state in ('duplicate', 'malformed') else
                 'Skipped ' + name + '.')
            return
        try:
            store.set(name, value)
        except ValueError as error:
            line(str(error), 'error')
            continue
        finally:
            value = None
        for row in prompt.receipt:
            line(row)
        line(glyph('✓ ', '') + 'Saved ' + name, 'success')
        return


def provider_setup(store, provider, back=True):
    line()
    line(provider['name'], 'title')
    wrapped(provider['purpose'])
    try:
        for key in provider['key']:
            populate(store, key, provider, back)
    except Back:
        if not back:
            raise  # Started for one provider: there is no list to go back to.


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
        provider_setup(store, selected, back=False)
        return
    while True:
        states = store.states()
        line()
        for index, provider in enumerate(providers, 1):
            names = [k['name'] for k in provider['key']]
            saved = sum(states.get(name) == 'set' for name in names)
            status = ''
            if saved == len(names):
                status = style(glyph('✓ ', '') + 'saved', 'success')
            elif saved:
                status = '%d of %d saved' % (saved, len(names))
            line(style('%4d  ' % index, 'accent') + provider['name'].ljust(30) + status)
        line()
        line(style('%4s  ' % 'e', 'accent') + 'Edit the file in nano')
        line('      Custom key: godmode set NAME')
        line()
        choices = ['','e'] + [str(i) for i in range(1,len(providers)+1)] + [p['id'] for p in providers]
        answer = read_choice('Choose a provider by number or name. Enter finishes.', choices)
        if not answer:
            line(glyph('✓ ', '') + 'Done. Your keys are in ' + home_path(store.env_path), 'success')
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
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='replace')  # A missed glyph prints as ? instead of failing.
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
            populate(store, {'name': args.name})
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
