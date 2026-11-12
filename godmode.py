#!/usr/bin/env python3
"""Godmode: pick a key with the arrow keys, paste it, see the edit it makes, save one local .env file."""
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
from godmode_terminal import quiet, read_choice, read_menu, read_secret, screen_rows, style

VERSION = '0.9.0'
PROVIDERS = None  # The build script inserts the plain provider data here.
LOGO = ['╔═╗╔═╗╔╦╗╔╦╗╔═╗╔╦╗╔═╗', '║ ╦║ ║ ║║║║║║ ║ ║║║╣ ', '╚═╝╚═╝═╩╝╩ ╩╚═╝═╩╝╚═╝']
PRINTED = {'blank': False, 'pages': set()}  # Whether the last line was empty; long addresses printed.


def catalog():
    if PROVIDERS is not None:
        return PROVIDERS
    return json.loads(Path(__file__).with_name('providers.json').read_text())


def line(text='', role=None):
    print(style(text, role) if role else text, flush=True)
    PRINTED['blank'] = not text


def gap():
    """A screen starts with a blank row unless the line above it is already blank."""
    return [] if PRINTED['blank'] else ['']


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
    else:
        for art in (LOGO if glyph('art', '') else ['GODMODE']):
            line('  ' + style(art, 'accent'))
        line()
        line(side[1])
        line(side[2])
    line()


def prepare(store, accepted=False):
    if not store.exists():
        line('No Godmode setup here yet', 'warning')
        wrapped('These keys let agents act as you. The provider does not give a shit whether a destructive request was a mistake. Check the account and permissions before handing over access.')
        wrapped('Values stay in one plaintext file, readable by programs running as you. Nothing here signs in to providers or proves a key works.')
        line()
        if not accepted:
            read_choice('Type GODMODE to continue', ['GODMODE'])
            line()
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


def key_page(provider, key):
    """The page Enter opens for this key: its own when it has one, else the provider's."""
    return key['console'] if 'console' in key else provider['console']


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
    """One key's whole screen: its steps, a live preview of the edit Enter makes, and the masked input."""

    def __init__(self, store, key, provider=None, back=False):
        self.name, self.key, self.back = key['name'], key, back
        self.state = store.states().get(self.name)  # None, 'set', 'blank', 'duplicate' or 'malformed'
        self.saved = self.state == 'set'
        self.secret = key.get('secret', True)  # false shows an address as you type it; pastes stay masked
        self.plan = store.plan(self.name)
        self.path = home_path(store.env_path)
        self.page = key_page(provider, key) if provider else None
        self.opened = None  # None until Enter tries the browser, then whether it opened
        self.shown_link = False  # whether the page's address has been put on screen
        self.receipt = ''

    def tidy(self, value):
        """Apply this key's own paste rules from the provider data.

        drop: characters the value never contains, such as the spaces Google shows in
        an app password. split: the key is copied as one ID:SECRET pair, and this entry
        keeps one half of it.
        """
        for char in self.key.get('drop', ''):
            value = value.replace(char, '')
        separator, index = self.key.get('split', ('', 0))
        halves = value.strip().split(separator, 1) if separator else []
        return halves[index] if len(halves) == 2 else value

    def check(self, value):
        """Return (the value as it would be saved, or None; why it cannot be saved yet)."""
        entered, value = value.rstrip('\r\n'), self.tidy(value)
        if not value.rstrip('\r\n'):
            # Nothing, or only a pasted line break; or text that this key's paste rule emptied.
            return None, 'there is nothing in it to save.' if entered else None
        try:
            return normalize(value, self.name), None
        except ValueError as error:
            return None, str(error)

    def enter(self, value):
        """Save a valid value. With nothing entered, open the key's page instead."""
        clean, problem = self.check(value)
        if problem:
            return False
        if clean is not None or not self.page:
            return True
        try:
            self.opened = open_page(self.page)
        except (OSError, subprocess.SubprocessError):
            self.opened = False
        if self.shown_link or self.page in PRINTED['pages']:
            return []
        # The address had no room on screen: print it once, to copy if the browser is elsewhere.
        self.shown_link = True
        PRINTED['pages'].add(self.page)
        rows = gap() + [self.page]
        PRINTED['blank'] = False
        return rows

    def plain(self, reveal):
        """Whether to show the value as it is: an address typed by hand, with nothing pasted in."""
        return not self.secret and not reveal and not self.pasted

    def shown(self, clean, reveal):
        """The value in the command, quoted the way Store.set quotes the real one.

        Masked values that were typed are always quoted, so the quotes cannot hint at
        which keystroke added a character that needs them.
        """
        if self.plain(reveal):
            return shlex.quote(clean)
        masked = mask(clean, reveal)
        if reveal and shlex.quote(clean) == clean:
            return masked
        return "'" + masked.replace("'", "'\"'\"'") + "'"

    def entry(self, value, clean, reveal):
        """What the input line shows after the label."""
        if not value.rstrip('\r\n'):
            return ''
        if self.plain(reveal):
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

    def link(self, width):
        """The page's address when it fits on one row, so it stays one clickable, copyable piece."""
        return self.page if self.page and len(self.page) < width else ''

    def guide(self, width):
        """What to do and where: the goal, the page's address, and the few steps to take there."""
        goal = self.key.get('goal', self.name) + ('  ' + glyph('✓ ', '') + 'saved' if self.saved else '')
        link = self.link(width)
        if link and not self.saved and len(goal) + 2 + len(link) < width:
            rows = [style(goal + ':', 'title') + ' ' + link]
        else:
            rows = [style(row, 'title') for row in fit_words(goal, width)] + ([link] if link else [])
        for number, step in enumerate(self.key.get('steps', []), 1):
            plain, spans = '', []
            for index, piece in enumerate(step.split('**')):
                if index % 2:  # Names to look for on the page are bold, also where one wraps.
                    spans.append((len(plain), len(plain) + len(piece)))
                plain += piece
            end = 0
            for index, part in enumerate(textwrap.wrap(plain, max(10, width - 5)) or ['']):
                start = plain.find(part, end)
                end = start + len(part)
                for low, high in reversed(spans if start >= 0 else []):
                    low, high = max(low, start) - start, min(high, end) - start
                    if low < high:
                        part = part[:low] + style(part[low:high], 'title') + part[high:]
                rows.append((style('%2d' % number, 'accent') if not index else '  ') + '  ' + part)
        if self.key.get('note'):
            rows += ['    ' + part for part in textwrap.wrap(self.key['note'], max(10, width - 5))]
        return rows + ['']

    def notes(self, clean, problem, reveal):
        """Only what the command alone does not say."""
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
        if self.state == 'malformed' and clean is None:
            notes.append('The saved ' + name + " line can't be read; paste to replace it.")
        # Only when the ends are on screen anyway; otherwise this would describe hidden characters.
        if (clean and clean[0] == clean[-1] and clean[0] in '\'"' and len(clean) > 1
                and (self.plain(reveal) or (reveal and len(clean) >= 8))):
            notes.append('This value starts and ends with quote marks; they are saved as part of it.')
        if clean is not None:
            notes.append('Godmode makes this edit itself. Nothing is sent.')
        return [(text, None) for text in notes]

    def hint(self, value, problem):
        leave = 'Esc ' + ('back' if self.back else 'cancels')
        if value.rstrip('\r\n'):
            return glyph(' · ', ' | ').join(['Ctrl-U clears' if problem else 'Enter saves', leave])
        if not self.page:
            return glyph(' · ', ' | ').join(['Enter keeps it' if self.saved else 'Enter skips', leave])
        host = urlsplit(self.page).netloc
        action = {None: 'Enter opens ' + host, True: 'Opened ' + host, False: 'No browser here: open the link above'}
        return glyph(' · ', ' | ').join([action[self.opened], leave])

    def render(self, value, width, reveal=True):
        clean, problem = self.check(value)
        shown = self.shown(clean, reveal) if clean is not None else glyph('…', '...')
        bar = style(glyph('│ ', '| '), 'accent')
        command, at = self.command(shown, width - 2)
        command = [bar + row for row in command]
        label = fit_words(prompt_label(self.key), width)  # Long typed dots may wrap; the redraw counts that.
        entry = label[:-1] + [label[-1] + ' ' + style(self.entry(value, clean, reveal), 'secret')]
        preview = [style(row, 'title') for row in fit_words('What will be executed on your machine', width)]
        preview += command
        preview += [bar + style(row, role) for text, role in self.notes(clean, problem, reveal)
                    for row in fit_words(text, width - 2)]
        preview += [''] + [style(row, 'accent') for row in fit_words(self.hint(value, problem), width)]
        # In a short window, give up the explanations first and keep the command with the value.
        room = screen_rows() - 1
        layouts = (gap() + self.guide(width) + preview + entry, preview + entry, command + entry, [command[at]] + entry)
        for index, choice in enumerate(layouts):
            if drawn_height(choice, width) <= room:
                self.shown_link = self.shown_link or (index == 0 and bool(self.link(width)))
                return choice
        return entry[-1:]

    def final(self, value, width, reveal, submitted):
        """Erase the screen. populate() prints a one-line receipt once the save succeeds."""
        clean, _ = self.check(value)
        self.receipt = self.name + '=' + self.shown(clean, reveal) if submitted and clean is not None else ''
        return []


class NamePrompt(Prompt):
    """A plain prompt for the name of a key that is not in the list. It is typed, not pasted."""
    pastes = False

    def __init__(self):
        Prompt.__init__(self, 'Type a name for the key, like ACME_API_TOKEN. Esc goes back.', hidden=False)
        self.refused = False

    def enter(self, value):
        self.refused = not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value)
        return not self.refused

    def render(self, value, width, reveal=True):
        rows = Prompt.render(self, value, width, reveal)
        why = fit_words('Use letters, digits and _ only, not starting with a digit.', width)
        return rows[:-1] + ([style(row, 'warning') for row in why] if self.refused else []) + rows[-1:]

    def final(self, value, width, reveal, submitted):
        return []


def menu_hint(leave):
    return glyph('↑↓ move · Enter open · Esc ', 'Up/Down move | Enter open | Esc ') + leave


def named(name):
    """A key entered by name alone. A bundled key keeps its own input rules, without its steps."""
    known = next((key for provider in catalog() for key in provider['key'] if key['name'] == name), {})
    return dict({field: known[field] for field in ('prompt', 'secret', 'drop', 'split') if field in known}, name=name)


def populate(store, key, provider=None, back=False):
    """Ask for one key. True when it was saved."""
    name = key['name']
    while True:
        prompt = KeyPrompt(store, key, provider, back)
        value = read_secret(prompt)
        if not value.rstrip('\r\n'):
            line('Kept your saved ' + name + '.' if prompt.saved else
                 'Left ' + name + ' unchanged.' if prompt.state in ('duplicate', 'malformed') else
                 'Skipped ' + name + '.')
            return False
        try:
            store.set(name, prompt.tidy(value))
        except ValueError as error:
            line(str(error), 'error')
            continue
        finally:
            value = None
        line(style(glyph('✓ ', '') + 'Saved ', 'success') + prompt.receipt)
        return True


def provider_setup(store, provider, back=True):
    """One provider: its only key, or a list of its keys. True when this visit completed it."""
    keys = provider['key']
    if len(keys) == 1:
        return populate(store, keys[0], provider, back)
    at, saved, advance = None, False, True
    while True:
        states = store.states()
        done = [states.get(key['name']) == 'set' for key in keys]
        if advance:  # Start on, and after a save move to, the next key that is still missing.
            missing = [index for index, ok in enumerate(done) if not ok]
            at = next((index for index in missing if at is None or index > at), (missing or [len(keys) + 1])[0])
            advance = False
        items = [(key.get('label', key['name']), glyph('✓ ', '') + 'saved' if ok else '', '') for key, ok in zip(keys, done)]
        items += [None, ('Back' if back else 'Done', '', '')]
        try:
            at = read_menu(items, at, menu_hint('back' if back else 'done'), provider['name'], bool(gap()))
        except Back:
            at = len(keys) + 1
        if at > len(keys):
            return saved and all(done)
        try:
            advance = populate(store, keys[at], provider, back=True)
            saved = saved or advance
        except Back:
            continue


def setup(store, provider_id=None):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError('Setup needs a terminal. Use set KEY --stdin for redirected input.')
    providers = catalog()
    selected = next((p for p in providers if p['id'] == provider_id), None)
    if provider_id and selected is None:
        raise ValueError('Unknown provider. Run godmode to see the list.')
    with quiet():  # Nothing typed or pasted between two screens is echoed.
        banner(store)
        prepare(store)
        if selected:
            provider_setup(store, selected, back=False)
        else:
            provider_list(store, providers)


def provider_list(store, providers):
    at, advance = None, True
    other, edit, done = len(providers) + 1, len(providers) + 2, len(providers) + 3
    while True:
        states = store.states()
        items = []
        for provider in providers:
            names = [key['name'] for key in provider['key']]
            saved = sum(states.get(name) == 'set' for name in names)
            mark = glyph('✓ ', '') + 'saved' if saved == len(names) else '%d of %d saved' % (saved, len(names)) if saved else ''
            items.append((provider['name'], mark, provider.get('about', '')))
        if advance:  # Start on, and after a save move to, the next provider that still lacks a key.
            missing = [index for index, item in enumerate(items) if item[1] != glyph('✓ ', '') + 'saved']
            at = next((index for index in missing if at is None or index > at), (missing or [done])[0])
            advance = False
        items += [None, ('Another key', '', 'any NAME=value you want agents to have'),
                  ('Edit the file in nano', '', ''), ('Done', '', '')]
        try:
            at = read_menu(items, at, menu_hint('done'), gap=bool(gap()))
        except Back:
            at = done
        if at == done:
            line('Done. Your keys are in ' + home_path(store.env_path))
            return
        try:
            if at == edit:
                try:
                    edit_file(store)
                except ValueError as error:
                    line(str(error), 'warning')
            elif at == other:
                populate(store, named(read_secret(NamePrompt())), back=True)
            else:
                advance = provider_setup(store, providers[at])
        except Back:
            pass


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
            with quiet():
                populate(store, named(args.name))
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
