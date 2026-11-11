"""Small terminal prompts: partly masked values, a live preview, explicit Enter and plain ANSI color."""
import os
import re
import select
import shutil
import signal
import sys
import termios
import tty
import unicodedata

TERM_MAX_INPUT = 1024 * 1024
TERM_STYLE = re.compile(r"\033\[[0-9;]*m")


class Cancelled(Exception):
    """The user left a prompt without submitting its value."""


class Back(Cancelled):
    """Escape: leave this prompt for the previous menu, saving nothing."""


def color_enabled(stream=None):
    stream = sys.stdout if stream is None else stream
    return (stream.isatty() and "NO_COLOR" not in os.environ
            and os.environ.get("CLICOLOR") != "0"
            and os.environ.get("TERM") != "dumb")


def style(text, role="accent"):
    codes = {"title": "1", "heading": "1", "accent": "36", "link": "4;36", "secret": "1;36",
             "success": "32", "warning": "33", "error": "31"}
    if not color_enabled() or role not in codes:
        return str(text)
    return "\033[" + codes[role] + "m" + str(text) + "\033[0m"


def glyph(fancy, plain):
    """Use a Unicode symbol only when the terminal encoding can show it."""
    return fancy if "utf" in (getattr(sys.stdout, "encoding", "") or "").lower() else plain


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


def screen_rows():
    size = shutil.get_terminal_size((80, 24))
    return size.lines if size.lines > 0 else 24


class Prompt:
    """What a prompt draws. The last rendered row is the input line, where the cursor rests."""
    # key -> function returning rows to print above the prompt. Tab always works;
    # printable keys work only while nothing has been typed into the field.
    actions = {}

    def __init__(self, label, hidden=True):
        self.label, self.hidden = label, hidden

    def render(self, value, width, reveal=True):
        shown = mask(value, reveal) if self.hidden else value
        rows = fit(self.label, width)
        entry = glyph("› ", "> ")
        return rows[:-1] + [style(rows[-1], "accent"), entry + fit(shown, width - cells(entry))[-1]]

    def ready(self, value):
        """Whether Enter may submit this value."""
        return True

    def final(self, value, width, reveal, submitted):
        """Rows left on screen once the prompt ends."""
        return self.render(value, width, reveal)


def read_secret(prompt):
    """Return a hidden value. Pasting never submits; only Enter does."""
    return _term_read(prompt if isinstance(prompt, Prompt) else Prompt(prompt), None)


def read_choice(label, choices):
    """Return a listed choice; never echo an unexpected pasted value."""
    return _term_read(Prompt(label, hidden=False),
                      {str(choice).casefold(): str(choice) for choice in choices})


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


def _term_read(prompt, choices):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError("This prompt needs a terminal.")
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    handlers = {}
    value = bytearray()
    pending = bytearray()
    paste_value = bytearray()
    pasting = False
    # Ends are shown only for a value pasted into an empty field. Typing or deleting
    # would otherwise reveal every character as it passes through the visible end.
    reveal = True
    submitted = False
    drawn = []
    paste_start, paste_end = b"\x1b[200~", b"\x1b[201~"
    # A resize writes to this pipe so the region is redrawn at the new width at once.
    wake, wake_write = os.pipe()
    os.set_blocking(wake, False)
    os.set_blocking(wake_write, False)
    previous_wake = None

    def interrupted(_number, _frame):
        raise Cancelled()

    def append(data, pasted=False):
        if len(value) + len(data) > TERM_MAX_INPUT or b"\0" in data:
            raise ValueError("Input is too large or contains a NUL byte; nothing saved.")
        if choices is not None:
            try:
                candidate = (value + data).decode("utf-8").casefold()
            except UnicodeDecodeError:
                if not pasted and any(option.encode("utf-8").startswith(value + data)
                                      for option in choices):
                    value.extend(data)
                return
            # Pasting a credential into a menu must not put it in scrollback.
            if not (candidate in choices if pasted else
                    any(option.startswith(candidate) for option in choices)):
                return
        value.extend(data)

    def clear():
        value[:] = b"\0" * len(value)
        value.clear()

    def render(final=False):
        text = value.decode("utf-8", "ignore")
        if final:
            return prompt.final(text, columns(), reveal, submitted)
        return prompt.render(text, columns(), reveal)

    try:
        for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            handlers[number] = signal.signal(number, interrupted)
        handlers[signal.SIGWINCH] = signal.signal(signal.SIGWINCH, lambda *_: None)
        previous_wake = signal.set_wakeup_fd(wake_write)
        tty.setraw(fd)
        sys.stdout.write("\033[?2004h")
        while True:
            if not pasting:
                drawn = _draw(render(), drawn)
            # An isolated Escape goes back; fragmented terminal sequences get time
            # to arrive before it is interpreted as the Escape key.
            timeout = 0.08 if pending.startswith(b"\x1b") and not pasting else None
            ready = select.select([fd, wake], [], [], timeout)[0]
            if wake in ready:
                while True:
                    try:
                        if not os.read(wake, 512):
                            break
                    except BlockingIOError:
                        break
                if fd not in ready:
                    continue
            if not ready:
                raise Back()
            chunk = os.read(fd, 4096)
            if not chunk:
                raise Cancelled()
            pending.extend(chunk)
            while pending:
                if pasting:
                    end = pending.find(paste_end)
                    if end < 0:
                        # Retain a possible split end marker without interpreting
                        # any pasted control characters as terminal commands.
                        if len(pending) > len(paste_end):
                            if choices is None:
                                append(pending[:-len(paste_end)])
                            else:
                                paste_value.extend(pending[:-len(paste_end)])
                                if len(paste_value) > TERM_MAX_INPUT:
                                    raise ValueError("Input is too large; nothing saved.")
                            del pending[:-len(paste_end)]
                        break
                    if choices is None:
                        append(pending[:end], pasted=True)
                    else:
                        paste_value.extend(pending[:end])
                        append(paste_value, pasted=True)
                    del pending[:end + len(paste_end)]
                    pasting = False
                    continue
                if pending[0] == 27:
                    if len(pending) < len(paste_start) and paste_start.startswith(pending):
                        break
                    if pending.startswith(paste_start):
                        del pending[:len(paste_start)]
                        pasting = True
                        paste_value = bytearray()
                        if choices is None and reveal:
                            clear()  # Pasting again replaces a pasted value instead of doubling it.
                        continue
                    if len(pending) < 2:
                        break
                    if pending[1] in (ord("["), ord("O")):
                        end = next((i for i in range(2, len(pending))
                                    if 0x40 <= pending[i] <= 0x7e), None)
                        if end is None and len(pending) < 32:
                            break
                        del pending[:(end + 1 if end is not None else len(pending))]
                    else:
                        del pending[:2]  # Ignore an Alt-key sequence.
                    continue
                char = pending.pop(0)
                if char in (3, 4):
                    raise Cancelled()
                if char in (10, 13):
                    try:
                        answer = value.decode("utf-8")
                    except UnicodeDecodeError:
                        raise ValueError("Input is not valid UTF-8; nothing saved.") from None
                    if choices is None and prompt.ready(answer):
                        submitted = True
                        return answer
                    if choices is not None and answer.casefold() in choices:
                        submitted = True
                        return choices[answer.casefold()]
                    sys.stdout.write("\a")
                elif (choices is None and chr(char) in prompt.actions
                      and (char == 9 or not value or reveal)):
                    _draw([], drawn)
                    rows = prompt.actions[chr(char)]()
                    sys.stdout.write("".join(row + "\r\n" for row in rows))
                    drawn = []
                elif char == 21:
                    clear()
                elif char in (8, 127):
                    if value:
                        start = len(value) - 1
                        while start > 0 and (value[start] & 0xc0) == 0x80:
                            start -= 1
                        del value[start:]
                        reveal = False
                elif char >= 32:
                    append(bytes([char]))
                    reveal = False
                if not value:
                    reveal = True
    finally:
        left = []
        try:
            left = render(final=True)
            _draw(left, drawn)
        finally:
            # Flush unsaved input so a cancelled paste cannot become a shell command.
            termios.tcsetattr(fd, termios.TCSAFLUSH, saved)
            if previous_wake is not None:
                signal.set_wakeup_fd(previous_wake)
            for number, previous in handlers.items():
                signal.signal(number, previous)
            os.close(wake)
            os.close(wake_write)
            clear()
            # An empty final region leaves the cursor on a fresh line already.
            sys.stdout.write("\033[?2004l" + ("\r\n" if left else ""))
            sys.stdout.flush()
