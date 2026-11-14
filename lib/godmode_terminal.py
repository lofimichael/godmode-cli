"""Small terminal prompts: an arrow-key menu, partly masked input with a live preview, plain ANSI color."""
import contextlib
import os
import re
import select
import shutil
import signal
import sys
import termios
import textwrap
import time
import tty
import unicodedata

TERM_MAX_INPUT = 1024 * 1024
TERM_STYLE = re.compile(r"\033\[[0-9;]*m")
TERM_PASTE = (b"\x1b[200~", b"\x1b[201~")
TERM_KEYS = {3: "cancel", 4: "cancel", 9: "tab", 10: "enter", 13: "enter", 8: "backspace", 127: "backspace",
             14: "down", 16: "up", 21: "clear"}
TERM_ARROWS = {"A": "up", "B": "down", "C": "right", "D": "left", "H": "home", "F": "end",
               "1~": "home", "7~": "home", "4~": "end", "8~": "end", "5~": "pageup", "6~": "pagedown"}


class Cancelled(Exception):
    """The user left a prompt without submitting its value."""


class Back(Cancelled):
    """Escape: leave this prompt for the previous menu, saving nothing."""


def plain_enabled():
    """Sequential prompts for screen readers and terminals without cursor controls."""
    return (os.environ.get("GODMODE_PLAIN", "").lower() not in ("", "0", "false", "no")
            or os.environ.get("TERM", "dumb") in ("", "dumb"))


plain_mode = plain_enabled


def color_enabled(stream=None):
    stream = sys.stdout if stream is None else stream
    return (stream.isatty() and not plain_enabled() and "NO_COLOR" not in os.environ
            and os.environ.get("CLICOLOR") != "0"
            and os.environ.get("TERM", "dumb") not in ("", "dumb"))


def style(text, role="accent"):
    # dim is faint (SGR 2), not bright black (SGR 90), which some themes draw in the background color.
    codes = {"title": "1", "heading": "1", "accent": "36", "link": "4;36", "secret": "1;36",
             "success": "32", "warning": "33", "error": "31", "dim": "2", "brand": "1;36", "risk": "1;33",
             "nfo": "1;35", "nfo_edge": "36", "diff_add": "32", "diff_remove": "31"}
    if not color_enabled() or role not in codes or not str(text):
        return str(text)
    return "\033[" + codes[role] + "m" + str(text) + "\033[0m"


def meter(points, total, width):
    """A progress bar of width cells for points out of total, never fuller than it is.

    Color draws a heavy line on a faint one, green when full. Without color, solid blocks
    on shaded ones keep the two parts apart; without Unicode, # on -.
    """
    filled = width * max(0, min(points, total)) // total if total else 0
    if not glyph("u", ""):
        return "#" * filled + "-" * (width - filled)
    if not color_enabled():
        return "\u2588" * filled + "\u2591" * (width - filled)
    return style("\u2501" * filled, "success" if points >= total else "accent") + style("\u2500" * (width - filled), "dim")


def glyph(fancy, plain):
    """Use a Unicode symbol only when the terminal can show it (the Linux console font cannot)."""
    unicode = "utf" in (getattr(sys.stdout, "encoding", "") or "").lower() and os.environ.get("TERM") != "linux"
    return fancy if unicode and not plain_enabled() else plain


def mask(value, reveal=True):
    """Hide a value, keeping a few characters at each end of a pasted value to recognize it.

    A pasted value shows at most three characters at each end, never more than a quarter
    of it: 24+ characters show 3+3, 16-23 show 2+2, 8-15 show 1+1, shorter ones only dots.
    Spaces, control and non-ASCII characters at the ends stay hidden too. A typed or edited
    value (reveal=False) shows one dot per character, like an ordinary password field.
    """
    if not value:
        return ""
    dot = glyph("•", "*")
    if not reveal:
        return dot * min(len(value), 24)
    visible = min(3, len(value) // 8)
    if not visible:
        return dot * 5

    def edge(text):
        return "".join(c if " " < c < "\x7f" else dot for c in text)
    return edge(value[:visible]) + dot * 5 + edge(value[-visible:])


def cells(text):
    """Terminal columns a string occupies, ignoring color codes."""
    width = 0
    for char in TERM_STYLE.sub("", text):
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return width


def drawn_height(rows, width):
    """Screen rows these rows take once the terminal wraps anything wider than width."""
    return sum(max(1, -(-cells(row) // width)) for row in rows)


def fit(text, columns):
    """Split plain text into rows that stay clear of the terminal's last column."""
    size, rows, row = max(1, columns - 1), [], ""
    for char in text:
        if row and cells(row + char) > size:
            rows.append(row)
            row = ""
        row += char
    return rows + [row]


def columns():
    """Terminal width. Some terminals report 0 columns; treat that as unknown."""
    size = shutil.get_terminal_size((80, 24))
    return size.columns if size.columns > 0 else 80


def plain_columns():
    """Static output wraps in scrollback; it does not need to fit the viewport."""
    return max(40, columns())


def screen_rows():
    size = shutil.get_terminal_size((80, 24))
    return size.lines if size.lines > 0 else 24


class Prompt:
    """What a text prompt draws. The last rendered row is the input line, where the cursor rests."""
    pastes = True  # False for a field shown as typed, so a secret pasted there by mistake never appears.
    pasted = False  # read_secret sets this while the field holds any pasted text.
    reviewing = False  # Static mode has displayed the value and awaits confirmation.

    def __init__(self, label, hidden=True):
        self.label, self.hidden = label, hidden

    def render(self, value, width, reveal=True):
        shown = mask(value, reveal) if self.hidden else value
        rows = textwrap.wrap(self.label, max(1, width - 3)) or [""]
        entry = "  " + glyph("› ", "> ")
        return ["  " + row for row in rows[:-1]] + ["  " + style(rows[-1], "dim"),
                                                     entry + fit(shown, width - cells(entry))[-1]]

    def enter(self, value):
        """What Enter does: True submits, False refuses, a list of rows is printed above the prompt."""
        return True

    def toggle(self):
        """Tab may disclose detail without changing the field or submitting it."""
        return False

    def final(self, value, width, reveal, submitted):
        """Rows left on screen once the prompt ends."""
        return self.render(value, width, reveal)


def _draw(rows, previous):
    """Redraw the prompt region in place and return the width of each row drawn.

    `previous` holds the widths last drawn, so the region's height is recomputed at the
    current width even after the terminal was resized and reflowed its lines.
    """
    width, height = columns(), screen_rows()

    def tall(widths):
        return sum(max(1, -(-w // width)) for w in widths)
    widths = [cells(row) for row in rows]
    while len(rows) > 1 and tall(widths) > height - 1:
        rows, widths = rows[1:], widths[1:]  # Last resort; prompts condense themselves first.
    # Assumes the terminal reflowed earlier rows after a resize, as most current ones do.
    up = tall(previous) - 1 if previous else 0
    sys.stdout.write("\r" + ("\033[%dA" % up if up > 0 else "") + "\033[J" + "\r\n".join(rows))
    sys.stdout.flush()
    return widths


@contextlib.contextmanager
def quiet():
    """Keep the terminal from echoing between prompts, for a whole interactive session.

    Each prompt reads in raw mode, but between two prompts the terminal would be back
    to normal and would print a paste that lands in that moment. With echo off for the
    session, such input is dropped unseen. The terminal is restored at the end.
    """
    if not sys.stdin.isatty():
        yield
        return
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    silent = termios.tcgetattr(fd)
    silent[3] &= ~termios.ECHO

    def interrupted(_number, _frame):
        raise Cancelled()
    handlers = {number: signal.signal(number, interrupted) for number in (signal.SIGTERM, signal.SIGHUP)}
    try:
        termios.tcsetattr(fd, termios.TCSADRAIN, silent)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSAFLUSH, saved)
        for number, previous in handlers.items():
            signal.signal(number, previous)


def _key_name(code):
    """Name the key for the body of an escape sequence, such as "A", "1;5B" or "5~"."""
    if code.endswith("~"):
        return TERM_ARROWS.get(code[:-1].split(";")[0] + "~")
    return TERM_ARROWS.get(code[-1:])


class _Keyboard:
    """Raw terminal input for one prompt, restored on every way out.

    read() waits for the next event:
      ("text", bytes)    typed characters
      ("paste", bytes)   one whole bracketed paste, never interpreted as keys
      ("reject", None)   a paste that was too large or held a NUL byte, once all of it has arrived
      ("key", name)      enter, esc, tab, backspace, clear, up, down, left, right, home, end, pageup, pagedown
      ("resize", None)   the window changed size
    Ctrl-C, Ctrl-D and termination signals raise Cancelled.
    """

    def __enter__(self):
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise ValueError("This prompt needs a terminal.")
        self.fd = sys.stdin.fileno()
        self.saved = termios.tcgetattr(self.fd)
        self.events, self.pending, self.paste, self.rejected = [], bytearray(), None, False
        self.handlers, self.previous_wake = {}, None
        # A resize writes to this pipe, so select() wakes up and the prompt redraws at once.
        self.wake, self.wake_write = os.pipe()
        os.set_blocking(self.wake, False)
        os.set_blocking(self.wake_write, False)

        def interrupted(_number, _frame):
            raise Cancelled()
        try:
            for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                self.handlers[number] = signal.signal(number, interrupted)
            self.handlers[signal.SIGWINCH] = signal.signal(signal.SIGWINCH, lambda *_: None)
            self.previous_wake = signal.set_wakeup_fd(self.wake_write)
            tty.setraw(self.fd)
            sys.stdout.write("\033[?2004h")
        except BaseException:
            self.__exit__()
            raise
        return self

    def __exit__(self, *_):
        # Flush unread input so a cancelled paste cannot become a shell command.
        termios.tcsetattr(self.fd, termios.TCSAFLUSH, self.saved)
        if self.previous_wake is not None:
            signal.set_wakeup_fd(self.previous_wake)
        for number, previous in self.handlers.items():
            signal.signal(number, previous)
        os.close(self.wake)
        os.close(self.wake_write)
        sys.stdout.write("\033[?2004l" + ("" if plain_enabled() else "\033[?25h"))
        sys.stdout.flush()

    def read(self):
        while not self.events:
            # An isolated Escape is the Escape key; a fragmented sequence gets time to arrive.
            waiting = self.pending.startswith(b"\x1b") and self.paste is None
            ready = select.select([self.fd, self.wake], [], [], 0.08 if waiting else None)[0]
            if not ready:
                alone = self.pending == b"\x1b"
                self.pending.clear()  # A stalled fragment of a longer sequence is dropped, not a key.
                if alone:
                    return ("key", "esc")
                continue
            if self.wake in ready:
                with contextlib.suppress(BlockingIOError):
                    while os.read(self.wake, 512):
                        pass
                return ("resize", None)
            chunk = os.read(self.fd, 4096)
            if not chunk:
                raise Cancelled()
            self.pending.extend(chunk)
            self._parse()
        return self.events.pop(0)

    def poll(self, timeout=0):
        """Return one event or None without waiting for a complete paste.

        Animations use the same hidden, bounded paste parser as ordinary prompts.
        Partial pastes stay buffered; Escape alone needs the same 80 ms grace.
        """
        deadline = time.monotonic() + max(0, timeout)
        for _ in range(64):  # Drain at most 256 KiB before letting an animation draw.
            if self.events:
                return self.events.pop(0)
            waiting = self.pending.startswith(b"\x1b") and self.paste is None
            now = time.monotonic()
            since = getattr(self, "poll_escape_since", None)
            if waiting:
                if since is None:
                    self.poll_escape_since = since = now
                if now - since >= 0.08:
                    alone = self.pending == b"\x1b"
                    self.pending.clear()
                    self.poll_escape_since = None
                    return ("key", "esc") if alone else None
            else:
                self.poll_escape_since = None
            delay = max(0, deadline - now)
            if waiting:
                delay = min(delay, max(0, 0.08 - (now - since)))
            ready = select.select([self.fd, self.wake], [], [], delay)[0]
            if not ready:
                if waiting and time.monotonic() - since >= 0.08:
                    continue
                return None
            if self.wake in ready:
                with contextlib.suppress(BlockingIOError):
                    while os.read(self.wake, 512):
                        pass
                return ("resize", None)
            chunk = os.read(self.fd, 4096)
            if not chunk:
                raise Cancelled()
            self.pending.extend(chunk)
            self._parse()
            if not self.pending.startswith(b"\x1b") or self.paste is not None:
                self.poll_escape_since = None
        return self.events.pop(0) if self.events else None

    def _parse(self):
        """Turn complete input into events; leave an unfinished sequence for the next read."""
        pending, start, end = self.pending, TERM_PASTE[0], TERM_PASTE[1]
        while pending:
            if self.paste is not None:
                found = pending.find(end)
                # Hold back a possibly split end marker; pasted bytes are data, never keys.
                take = found if found >= 0 else max(0, len(pending) - len(end))
                if not self.rejected:
                    self.paste.extend(pending[:take])
                del pending[:take]
                if len(self.paste) > TERM_MAX_INPUT or b"\0" in self.paste:
                    # Keep reading to the end of the paste before refusing it. Leaving now would
                    # let the terminal deliver the rest of it to the shell as commands.
                    self.rejected = True
                    self.paste[:] = b""
                if found < 0:
                    return
                del pending[:len(end)]
                self.events.append(("reject", None) if self.rejected else ("paste", bytes(self.paste)))
                self.paste, self.rejected = None, False
            elif pending[0] != 27:
                char = pending.pop(0)
                if TERM_KEYS.get(char) == "cancel":
                    raise Cancelled()
                if char in TERM_KEYS:
                    self.events.append(("key", TERM_KEYS[char]))
                elif char >= 32:
                    self.events.append(("text", bytes([char])))
            elif pending.startswith(start):
                del pending[:len(start)]
                self.paste = bytearray()
            elif len(pending) < 2 or start.startswith(bytes(pending)):
                return  # Only an Escape so far; read() decides after a short wait.
            elif pending[1] == 27:
                del pending[:1]  # Alt+arrow arrives as Escape, then the arrow's own sequence.
            elif pending[1] not in b"[O":
                del pending[:2]  # Ignore an Alt-key sequence.
            elif pending[1:3] == b"[[":
                if len(pending) < 4:
                    return
                del pending[:4]  # A Linux console function key.
            else:
                last = next((i for i in range(2, len(pending)) if 0x40 <= pending[i] <= 0x7e), None)
                if last is None and len(pending) < 32:
                    return
                last = len(pending) - 1 if last is None else last
                name = _key_name(bytes(pending[2:last + 1]).decode("ascii", "ignore"))
                del pending[:last + 1]
                if name:
                    self.events.append(("key", name))


def read_secret(prompt):
    """Return a hidden value. Pasting never submits; only Enter does."""
    prompt = prompt if isinstance(prompt, Prompt) else Prompt(prompt)
    if plain_enabled():
        return _plain_secret(prompt)
    value, drawn, submitted = bytearray(), [], False
    # Ends are shown only for a value pasted into an empty field. Typing or deleting
    # would otherwise reveal every character as it passes through the visible end.
    reveal = True

    def text():
        return value.decode("utf-8", "ignore")

    def clear():
        value[:] = b"\0" * len(value)
        value.clear()

    def add(data):
        if len(value) + len(data) > TERM_MAX_INPUT:
            raise ValueError("Input is too large; nothing saved.")
        value.extend(data)

    with _Keyboard() as keyboard:
        try:
            while True:
                drawn = _draw(prompt.render(text(), columns(), reveal), drawn)
                kind, key = keyboard.read()
                if kind == "reject":
                    raise ValueError("Input is too large or contains a NUL byte; nothing saved.")
                elif kind == "paste" and not prompt.pastes:
                    sys.stdout.write("\a")
                elif kind == "paste":
                    if reveal:
                        clear()  # Pasting again replaces a pasted value instead of doubling it.
                    add(key)
                    prompt.pasted = True
                elif kind == "text":
                    add(key)
                    reveal = False
                elif key == "backspace" and value:
                    start = len(value) - 1
                    while start > 0 and (value[start] & 0xc0) == 0x80:
                        start -= 1
                    del value[start:]
                    reveal = False
                elif key == "clear":
                    clear()
                elif kind == "key" and key == "tab":
                    prompt.toggle()
                elif key == "esc":
                    raise Back()
                elif key == "enter":
                    try:
                        answer = value.decode("utf-8")
                    except UnicodeDecodeError:
                        raise ValueError("Input is not valid UTF-8; nothing saved.") from None
                    outcome = prompt.enter(answer)
                    if outcome is True:
                        submitted = True
                        return answer
                    if outcome is False:
                        sys.stdout.write("\a")
                    else:
                        _draw([], drawn)
                        sys.stdout.write("".join(row + "\r\n" for row in outcome))
                        drawn = []
                if not value:
                    reveal, prompt.pasted = True, False
        finally:
            left = prompt.final(text(), columns(), reveal, submitted)
            _draw(left, drawn)
            clear()
            sys.stdout.write("\r\n" if left else "")


def _plain_rows(rows):
    """Append static rows without terminal drawing or color sequences."""
    sys.stdout.write("\r\n".join(TERM_STYLE.sub("", str(row)) for row in rows) + "\r\n")
    sys.stdout.flush()


def _plain_secret(prompt):
    """Hidden input followed by a static review; a separate Enter submits it.

    Bracketed paste remains enabled, so pasted newlines never act as Enter keys.
    This mode emits no cursor movement, erase codes, color, or per-key redraws.
    """
    value, submitted, reviewed, paste_only = bytearray(), False, False, True

    def text():
        return value.decode("utf-8", "ignore")

    with _Keyboard() as keyboard:
        try:
            _plain_rows(prompt.render("", plain_columns(), False))
            _plain_rows(["  Input hidden. Enter reviews."])
            while True:
                kind, key = keyboard.read()
                if kind == "reject":
                    raise ValueError("Input is too large or contains a NUL byte; nothing saved.")
                if kind == "paste" and not prompt.pastes:
                    _plain_rows(["  Paste ignored. Type the name."])
                    continue
                if kind in ("text", "paste"):
                    if kind == "paste" and paste_only:
                        value[:] = b"\0" * len(value)
                        value.clear()
                    if len(value) + len(key) > TERM_MAX_INPUT:
                        raise ValueError("Input is too large; nothing saved.")
                    value.extend(key)
                    prompt.pasted = kind == "paste" or prompt.pasted
                    reviewed = False
                    if kind == "text":
                        paste_only = False
                elif kind == "key" and key == "backspace":
                    if value:
                        start = len(value) - 1
                        while start > 0 and (value[start] & 0xc0) == 0x80:
                            start -= 1
                        del value[start:]
                    reviewed = False
                    paste_only = False
                elif kind == "key" and key == "clear":
                    value[:] = b"\0" * len(value)
                    value.clear()
                    reviewed = False
                elif kind == "key" and key == "tab":
                    prompt.toggle()
                    prompt.reviewing = reviewed
                    _plain_rows(prompt.render(text(), plain_columns(), False))
                elif kind == "key" and key == "esc":
                    raise Back()
                elif kind == "key" and key == "enter":
                    try:
                        answer = value.decode("utf-8")
                    except UnicodeDecodeError:
                        raise ValueError("Input is not valid UTF-8; nothing saved.") from None
                    if answer and not reviewed:
                        prompt.reviewing = True
                        _plain_rows(prompt.render(answer, plain_columns(), False))
                        if not hasattr(prompt, "hint"):
                            _plain_rows(["  Enter confirms. Ctrl-U clears. Esc back."])
                        reviewed = True
                        continue
                    outcome = prompt.enter(answer)
                    if outcome is True:
                        submitted = True
                        return answer
                    if outcome is False:
                        prompt.reviewing = False
                        _plain_rows(prompt.render(answer, plain_columns(), False))
                    else:
                        _plain_rows(outcome)
                        prompt.reviewing = False
                        _plain_rows(prompt.render(answer, plain_columns(), False))
                    reviewed = False
                if not value:
                    prompt.pasted = False
                    paste_only = True
                prompt.reviewing = reviewed
        finally:
            prompt.final(text(), plain_columns(), False, submitted)
            value[:] = b"\0" * len(value)
            value.clear()
            sys.stdout.write("\r\n")


def _plain_choice(label, choices, keyboard=None):
    options = {str(choice).casefold(): str(choice) for choice in choices}
    value = bytearray()
    with (_Keyboard() if keyboard is None else contextlib.nullcontext(keyboard)) as keyboard:
        _plain_rows([label])
        while True:
            kind, key = keyboard.read()
            if kind == "text":
                # Input stays hidden. Validate the whole choice on Enter: dropping
                # an invalid digit could turn "12" into "1", or "9" into a default.
                if len(value) + len(key) > TERM_MAX_INPUT:
                    raise ValueError("Input is too large; no choice selected.")
                value.extend(key)
            elif kind == "key" and key == "backspace":
                if value:
                    start = len(value) - 1
                    while start > 0 and (value[start] & 0xc0) == 0x80:
                        start -= 1
                    del value[start:]
            elif kind == "key" and key == "clear":
                value.clear()
            elif kind == "key" and key == "esc":
                raise Back()
            elif kind == "key" and key == "enter":
                try:
                    answer = value.decode("utf-8").casefold()
                except UnicodeDecodeError:
                    answer = None
                if answer in options:
                    _plain_rows([options[answer]])
                    return options[answer]
                _plain_rows(["  Invalid choice. Ctrl-U clears. Type a listed choice, then Enter."])


def read_choice(label, choices):
    """Return a listed choice typed in full; never echo an unexpected pasted value."""
    if plain_enabled():
        return _plain_choice(label, choices)
    options = {str(choice).casefold(): str(choice) for choice in choices}
    prompt, value, drawn = Prompt(label, hidden=False), bytearray(), []

    def fits(data, pasted):
        try:
            candidate = (value + data).decode("utf-8").casefold()
        except UnicodeDecodeError:  # The first bytes of a character still being typed.
            return not pasted and any(option.encode("utf-8").startswith(value + data) for option in options)
        # Pasting a credential into a confirmation must not put it in scrollback.
        return candidate in options if pasted else any(option.startswith(candidate) for option in options)

    with _Keyboard() as keyboard:
        try:
            while True:
                drawn = _draw(prompt.render(value.decode("utf-8", "ignore"), columns()), drawn)
                kind, key = keyboard.read()
                if kind in ("text", "paste"):
                    if fits(key, kind == "paste"):
                        value.extend(key)
                elif key == "backspace" and value:
                    del value[-1:]
                    while value and (value[-1] & 0xc0) == 0x80:
                        del value[-1:]
                elif key == "clear":
                    value.clear()
                elif key == "esc":
                    raise Back()
                elif key == "enter":
                    answer = value.decode("utf-8", "ignore").casefold()
                    if answer in options:
                        return options[answer]
                    sys.stdout.write("\a")
        finally:
            sys.stdout.write("\r\n")


def read_page(render):
    """An Enter-paced page. Text and pastes are ignored; Esc goes back."""
    if plain_enabled():
        with _Keyboard() as keyboard:
            rows, ready = render(plain_columns(), 1000000)
            _plain_rows(rows)
            while True:
                kind, key = keyboard.read()
                if kind == "key" and key == "esc":
                    raise Back()
                if kind == "key" and key == "enter" and ready:
                    return
                if kind == "resize" and not ready:
                    rows, ready = render(plain_columns(), 1000000)
                    _plain_rows(rows)
    drawn = []
    with _Keyboard() as keyboard:
        try:
            sys.stdout.write("\033[?25l")
            while True:
                rows, ready = render(columns(), screen_rows())
                drawn = _draw(rows, drawn)
                kind, key = keyboard.read()
                if kind == "key" and key == "esc":
                    raise Back()
                if kind == "key" and key == "enter" and ready:
                    return
        finally:
            _draw([], drawn)


def read_menu(items, start=0, hint="", title="", gap=False, header=None, status_width=0, abouts=False,
              searchable=False, header_required=False, row_spacing=0):
    """Choose a row with the arrow keys and return its index; Escape raises Back.

    items are (name, status, about) rows; None leaves a gap that cannot be chosen.
    A status is text or (text, role) and shows on every row in one column. The
    description shows on the row the pointer is on, or faintly on every row with
    abouts. Typing letters jumps to the first name that starts with them, and the same
    letter again moves to the next such name. searchable adds a slash filter; pastes
    never enter a search. Tab opens the full selected row when its text is clipped.
    header(width) returns rows above the title. A required header blocks selection
    until it fits; optional headers may collapse. Plain mode prints every row and
    accepts a number. Visual menus erase their own region when they end.
    """
    choices = [index for index, item in enumerate(items) if item]
    if not choices:
        raise ValueError("This menu has no choices.")
    if plain_enabled():
        return _plain_menu(items, start, title, header)
    at = start if start in choices else choices[0]
    typed, drawn = "", []
    filtering, query, blocked, details, detail_offset = False, "", False, False, 0
    pointer, more = glyph("❯ ", "> "), glyph("  ⋮", "  :")
    dot = glyph(" · ", " | ")

    def status(item):
        mark = item[1]
        return (mark, None) if isinstance(mark, str) else (mark[0], mark[1])
    # Columns are sized by the rows that have something to show beside their name.
    names = max([cells(items[i][0]) for i in choices if status(items[i])[0] or items[i][2] or status_width] or [0]) + 2
    marks = max([status_width] + [cells(status(items[index])[0]) for index in choices])
    marks += 2 if marks else 0

    def starting(letters):
        return [index for index in choices if items[index][0].casefold().startswith(letters)]

    def matches():
        return [i for i in choices if query.casefold() in (items[i][0] + " " + items[i][2]).casefold()] if query else choices

    def short(text, size):
        text = TERM_STYLE.sub("", text)
        if cells(text) <= size:
            return text
        end = glyph("…", "...")
        return fit(text, max(2, size - cells(end) + 1))[0] + end if size > cells(end) else ""

    def heading(width):
        if not title:
            return []
        rows = []
        for row in textwrap.wrap(title, max(1, width - 3), break_on_hyphens=False):
            lead, sep, rest = row.partition(dot) if not rows else ("", "", row)
            rows.append("  " + (style(lead, "title") + style(sep + rest, "dim") if lead else style(rest, "dim")))
        return rows

    def render():
        nonlocal blocked, detail_offset
        width = columns()
        if details:
            name, about = items[at][0], items[at][2]
            mark = TERM_STYLE.sub("", status(items[at])[0])
            full = []
            for text in (name, mark, about):
                if text:
                    full += ["  " + row for row in textwrap.wrap(TERM_STYLE.sub("", text), max(1, width - 3))]
            room = max(1, screen_rows() - 4)
            detail_offset = min(detail_offset, max(0, len(full) - room))
            return full[detail_offset:detail_offset + room] + ["", "  " + short("Up/Down scroll | Tab back", width - 3)]
        top_rows = list(header(width)) if header else []
        titled = heading(width)
        selected_name, selected_about = items[at][0], items[at][2]
        selected_mark = status(items[at])[0]
        available = max(1, width - 3)
        mark_width = min(marks, max(0, available // 2))
        name_width = min(names, max(1, available - mark_width)) if selected_mark or selected_about else available
        name_limit = max(1, name_width - 2) if selected_mark or selected_about else available
        cut = (cells(selected_name) > name_limit or cells(selected_mark) > max(0, mark_width - 2)
               or cells(selected_about) > max(0, available - name_width - mark_width))
        help_text = hint + ("  / search" if searchable else "") + ("  Tab details" if cut else "")
        below = [""] + ["  " + style(row, "dim") for row in textwrap.wrap(help_text, max(1, width - 3))] if help_text else []
        above = ([""] if gap else []) + top_rows + ([""] if top_rows else []) + titled + ([""] if titled else [])
        blocked = header_required and drawn_height(above + below, width) + min(3, len(items)) > screen_rows() - 1
        if blocked:
            return ["  " + row for row in textwrap.wrap("Enlarge the terminal to review all changes. Esc back.", max(1, width - 3))]
        if top_rows and not header_required and len(above) + min(5, len(items)) + len(below) > screen_rows() - 1:
            above = ([""] if gap else []) + titled + ([""] if titled else [])  # A short window drops the header first.
        if filtering:
            above += ["  / " + (short(query, max(1, width - 5)) if matches() else "No matches"), ""]
        room = max(3, screen_rows() - 1 - len(above) - len(below))
        indices = matches() if filtering else list(range(len(items)))
        if not indices:
            return above + ["  No matches"] + below
        position = indices.index(at) if at in indices else 0
        top = 0 if len(indices) <= room else min(max(0, position - room // 2), len(indices) - room)
        rows = []
        for slot in range(top, min(len(indices), top + room)):
            index = indices[slot]
            if (slot == top and top > 0) or (slot == top + room - 1 and slot < len(indices) - 1):
                rows.append(more)  # The list is taller than the window and continues.
            elif not items[index]:
                rows.append("")
            else:
                name, about = items[index][0], items[index][2]
                mark, role = status(items[index])
                focus = index == at
                note = about if (focus or abouts) else ""
                available = max(1, width - 3)
                mark_width = min(marks, max(0, available // 2))
                name_width = min(names, max(1, available - mark_width)) if mark or note else available
                name_limit = max(1, name_width - 2) if mark or note else available
                name = short(name, name_limit) if cells(name) > name_limit else name
                mark = short(mark, max(0, mark_width - 2)) if cells(mark) > max(0, mark_width - 2) else mark
                room_left = available - name_width - mark_width
                if note and cells(note) > room_left:
                    note = (fit(note, room_left)[0].rstrip() + glyph("…", "")
                            if room_left > 4 and not note.startswith("godmode ") else "")
                row = style(name, "title") if focus else name
                if mark or note:
                    row += " " * max(0, name_width - cells(name)) + (style(mark, role) if role else mark)
                if note:
                    row += " " * max(0, mark_width - cells(mark)) + (note if focus else style(note, "dim"))
                rows.append((style(pointer, "accent") if focus else "  ") + row)
        if row_spacing and drawn_height(above + rows + below, width) + row_spacing * (len(rows) - 1) <= screen_rows() - 1:
            rows = [part for index, row in enumerate(rows)
                    for part in (([""] * row_spacing if index else []) + [row])]
        return above + rows + below

    with _Keyboard() as keyboard:
        try:
            sys.stdout.write("\033[?25l")
            while True:
                drawn = _draw(render(), drawn)
                kind, key = keyboard.read()
                if details:
                    if kind == "key" and key in ("tab", "esc"):
                        details, detail_offset = False, 0
                    elif kind == "key" and key in ("up", "pageup"):
                        detail_offset = max(0, detail_offset - (5 if key == "pageup" else 1))
                    elif kind == "key" and key in ("down", "pagedown"):
                        detail_offset += 5 if key == "pagedown" else 1
                    continue
                if blocked:
                    if kind == "key" and key == "esc":
                        raise Back()
                    continue
                if kind == "key" and key == "tab":
                    details, detail_offset = True, 0
                    continue
                if searchable and kind == "text" and key == b"/" and not filtering:
                    filtering, query, typed = True, "", ""
                    continue
                if filtering:
                    if kind == "text" and len(query) < 64:
                        letter = key.decode("ascii", "ignore")
                        if letter and letter.isprintable():
                            query += letter
                    elif kind == "key" and key == "backspace":
                        query = query[:-1]
                    elif kind == "key" and key == "clear":
                        query = ""
                    elif kind == "key" and key == "esc":
                        filtering, query = False, ""
                        continue
                    found = matches()
                    if found and at not in found:
                        at = found[0]
                    if kind != "key" or key not in ("up", "down", "pageup", "pagedown", "home", "end", "enter"):
                        continue
                    if not found:
                        continue
                if kind == "text":
                    letter = key.decode("utf-8", "ignore").casefold()
                    if not letter:
                        continue  # Part of a character outside ASCII.
                    found = starting(typed + letter)
                    if found:
                        typed += letter
                    elif typed and set(typed) == {letter}:
                        found = starting(letter)  # The same letter again: the next name with it.
                        found = [index for index in found if index > at] or found
                    else:
                        typed, found = letter, starting(letter)
                    at = found[0] if found else at
                    continue
                typed = ""
                active = matches() if filtering else choices
                step = {"up": -1, "down": 1, "pageup": -5, "pagedown": 5}.get(key) if kind == "key" else None
                if step in (-1, 1):
                    at = active[(active.index(at) + step) % len(active)]  # Wraps around.
                elif step:
                    at = active[min(max(0, active.index(at) + step), len(active) - 1)]
                elif key in ("home", "end"):
                    at = active[0 if key == "home" else -1]
                elif key == "enter":
                    return at
                elif key == "esc":
                    raise Back()
        finally:
            _draw([], drawn)


def _plain_menu(items, start, title, header):
    choices = [i for i, item in enumerate(items) if item]
    rows = list(header(plain_columns())) if header else []
    if title:
        rows += [title]
    for number, index in enumerate(choices, 1):
        name, mark, about = items[index]
        mark = mark if isinstance(mark, str) else mark[0]
        rows.append("%d. %s%s" % (number, name, ": " + TERM_STYLE.sub("", mark) if mark else ""))
        if about:
            rows.append("   " + about)
    default = choices.index(start) + 1 if start in choices else 1
    with _Keyboard() as keyboard:
        _plain_rows(rows)
        answer = _plain_choice("Number, then Enter (%d). Esc back." % default,
                               [""] + [str(i) for i in range(1, len(choices) + 1)], keyboard)
    return choices[int(answer or default) - 1]


def read_document(title, paragraphs):
    """Read local prose with scrolling. Enter or Esc returns; pasted input stays hidden."""
    def rows(width):
        result = ["  " + style(title, "title"), ""]
        for paragraph in paragraphs:
            result += ["  " + row for row in textwrap.wrap(paragraph, max(1, width - 4),
                       break_on_hyphens=False)] + [""]
        return result
    if plain_enabled():
        with _Keyboard() as keyboard:
            _plain_rows(rows(plain_columns()) + ["Enter back."])
            while True:
                kind, key = keyboard.read()
                if kind == "key" and key in ("esc", "enter"):
                    return
    offset, drawn = 0, []
    with _Keyboard() as keyboard:
        try:
            sys.stdout.write("\033[?25l")
            while True:
                width, height = columns(), screen_rows()
                content, room = rows(width), max(1, height - 4)
                offset = min(offset, max(0, len(content) - room))
                hint = "Up/Down scroll | Enter back" if len(content) > room else "Enter back"
                footer = ["  " + style(row, "dim") for row in fit(hint, max(2, width - 2))]
                drawn = _draw(content[offset:offset + room] + [""] + footer, drawn)
                kind, key = keyboard.read()
                if kind == "key" and key in ("esc", "enter"):
                    return
                if kind == "key" and key in ("up", "pageup", "home"):
                    offset = 0 if key == "home" else max(0, offset - (room if key == "pageup" else 1))
                if kind == "key" and key in ("down", "pagedown", "end"):
                    offset = len(content) if key == "end" else offset + (room if key == "pagedown" else 1)
        finally:
            _draw([], drawn)


def motion_enabled():
    return (color_enabled() and os.environ.get("GODMODE_NO_MOTION", "").lower() in ("", "0", "false", "no"))


def animate_entrance(rows):
    """A brief logo reveal, only in a color terminal. No work or progress is implied."""
    if not motion_enabled() or not sys.stdin.isatty():
        return
    if drawn_height(rows, columns()) >= screen_rows() - 2:
        return
    drawn = []
    with _Keyboard() as keyboard:
        try:
            sys.stdout.write("\033[?25l")
            for count in range(1, len(rows) + 1):
                drawn = _draw(rows[:count], drawn)
                # Any input ends the reveal; it cannot submit the next screen.
                if select.select([keyboard.fd, keyboard.wake], [], [], 0.025)[0]:
                    return
        finally:
            _draw([], drawn)
