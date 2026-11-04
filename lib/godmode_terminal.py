"""Small terminal prompts: hidden values, explicit Enter, and ordinary ANSI color."""
import os
import select
import shutil
import signal
import sys
import termios
import tty

TERM_MAX_INPUT = 1024 * 1024


class Cancelled(Exception):
    """The user left a prompt without submitting its value."""


def color_enabled(stream=None):
    stream = sys.stdout if stream is None else stream
    return (stream.isatty() and "NO_COLOR" not in os.environ
            and os.environ.get("CLICOLOR") != "0"
            and os.environ.get("TERM") != "dumb")


def style(text, role="accent"):
    codes = {"title": "1", "heading": "1", "accent": "36", "link": "4;36",
             "success": "32", "warning": "33", "error": "31"}
    if not color_enabled() or role not in codes:
        return str(text)
    return "\033[" + codes[role] + "m" + str(text) + "\033[0m"


def read_secret(label):
    """Return a hidden value. Pasting never submits a bracketed paste."""
    return _term_read(label, None)


def read_choice(label, choices):
    """Return a listed choice; never echo an unexpected pasted value."""
    return _term_read(label, {str(choice).casefold(): str(choice) for choice in choices})


def _term_read(label, choices):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError("This prompt needs a terminal.")
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    handlers = {}
    value = bytearray()
    pending = bytearray()
    pasting = False
    width_before = 0
    paste_start, paste_end = b"\x1b[200~", b"\x1b[201~"

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

    try:
        for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            handlers[number] = signal.signal(number, interrupted)
        tty.setraw(fd)
        sys.stdout.write("\033[?2004h" + style(label, "accent") + "\r\n")
        sys.stdout.flush()
        while True:
            columns = max(1, shutil.get_terminal_size((80, 24)).columns - 4)
            displayed = ("*" * min(len(value.decode("utf-8", "ignore")), columns)
                         if choices is None else value.decode("utf-8", "ignore")[:columns])
            padding = " " * max(0, width_before - len(displayed))
            sys.stdout.write("\r> " + displayed + padding + "\r> " + displayed)
            sys.stdout.flush()
            width_before = len(displayed)
            # An isolated Escape cancels; fragmented terminal sequences get time
            # to arrive before it is interpreted as the Escape key.
            timeout = 0.08 if pending.startswith(b"\x1b") and not pasting else None
            if not select.select([fd], [], [], timeout)[0]:
                raise Cancelled()
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
                    if choices is None:
                        return answer
                    if answer.casefold() in choices:
                        return choices[answer.casefold()]
                elif char == 21:
                    value.clear()
                elif char in (8, 127):
                    if value:
                        start = len(value) - 1
                        while start > 0 and (value[start] & 0xc0) == 0x80:
                            start -= 1
                        del value[start:]
                elif char >= 32:
                    append(bytes([char]))
    finally:
        # Flush unsaved input so a cancelled paste cannot become a shell command.
        termios.tcsetattr(fd, termios.TCSAFLUSH, saved)
        for number, previous in handlers.items():
            signal.signal(number, previous)
        value[:] = b"\0" * len(value)
        sys.stdout.write("\033[?2004l\r\n")
        sys.stdout.flush()
