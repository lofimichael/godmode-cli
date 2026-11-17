"""PTY checks use synthetic values only and never print the captured input."""
import fcntl
import hashlib
import os
from pathlib import Path
import select
import signal
import struct
import subprocess
import sys
import termios
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import godmode_terminal as terminal
from pty_support import Screen, Terminal

DOT = "•".encode()
DOTS = DOT * 5

TERM_HARNESS = '''
import hashlib, os, termios
import godmode_terminal
from godmode_terminal import read_secret, read_choice, read_menu, quiet, Cancelled, Prompt

class Strict(Prompt):
    def enter(self, value):
        return ['ROWS_PRINTED_ABOVE'] if not value else value != 'not yet'

class Disclosure(Prompt):
    def toggle(self):
        self.open = not getattr(self, 'open', False)
    def render(self, value, width, reveal=True):
        rows = super().render(value, width, reveal)
        return (['DETAILS_VISIBLE'] if getattr(self, 'open', False) else []) + rows

ITEMS = [('Alpha', 'saved', 'ABOUT_ALPHA'), ('Beta', '', 'ABOUT_BETA'), ('Bravo', 'saved', ''), None, ('Gamma', '', ''), ('Done', '', '')]

godmode_terminal.TERM_MAX_INPUT = int(os.environ.get("MAX_FIELD_SIZE", 1024 * 1024))
before = termios.tcgetattr(0)
try:
    if os.environ['PROMPT_MODE'] == 'choice':
        value = read_choice('Select provider:', ['', 'github', 'q', 'café'])
    elif os.environ['PROMPT_MODE'] == 'menu':
        value = str(read_menu(ITEMS, int(os.environ.get('MENU_START', 0)), 'MENU_HINT', 'MENU_TITLE'))
    elif os.environ['PROMPT_MODE'] == 'longmenu':
        value = str(read_menu([('Item %02d' % n, '', '') for n in range(40)], 0, 'MENU_HINT'))
    elif os.environ['PROMPT_MODE'] == 'searchmenu':
        value = str(read_menu(ITEMS, 0, 'MENU_HINT', 'MENU_TITLE', searchable=True))
    elif os.environ['PROMPT_MODE'] == 'requiredmenu':
        value = str(read_menu([('Add', '', '')], 0, 'MENU_HINT', header=lambda width: ['REQUIRED_%02d' % n for n in range(30)], header_required=True))
    elif os.environ['PROMPT_MODE'] == 'widemenu':
        value = str(read_menu([('Very long provider name ' * 5, 'Saved status ' * 10, 'Entire details ' * 10)], 0, 'MENU_HINT', 'MENU_TITLE'))
    elif os.environ['PROMPT_MODE'] == 'disclosure':
        value = read_secret(Disclosure('Paste key (hidden; Enter saves):'))
    elif os.environ['PROMPT_MODE'] == 'quiet':
        with quiet():
            first = read_secret('Paste key (hidden; Enter saves):')
            print('BETWEEN echo=' + str(bool(termios.tcgetattr(0)[3] & termios.ECHO)), flush=True)
            value = first + read_secret('Paste key again:')
    elif os.environ['PROMPT_MODE'] == 'strict':
        value = read_secret(Strict('Paste key (hidden; Enter saves):'))
    else:
        value = read_secret('Paste key (hidden; Enter saves):')
    print('ACCEPTED ' + hashlib.sha256(value.encode()).hexdigest())
except Cancelled:
    print('CANCELLED')
except ValueError:
    print('REJECTED')
finally:
    print('RESTORED ' + str(termios.tcgetattr(0) == before))
'''


class Session:
    def __init__(self, mode="secret", limit=1024 * 1024, rows=24, start=0, plain=False, term="xterm-256color", width=80):
        self.master, self.slave = os.openpty()
        # A new PTY starts at 0x0. Give it a real terminal geometry instead of
        # depending on Python-version-specific get_terminal_size fallbacks.
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, width, 0, 0))
        os.set_blocking(self.master, False)
        self.output = bytearray()
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
               "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "lib"),
               "TERM": term, "PROMPT_MODE": mode, "MAX_FIELD_SIZE": str(limit),
               "MENU_START": str(start), "GODMODE_PLAIN": "1" if plain else "0"}
        self.process = subprocess.Popen([sys.executable, "-c", TERM_HARNESS],
                                        stdin=self.slave, stdout=self.slave,
                                        stderr=self.slave, env=env)
        marker = {"choice": b"Select provider:", "menu": b"MENU_HINT", "longmenu": b"MENU_HINT",
                  "searchmenu": b"MENU_HINT", "widemenu": b"MENU_HINT", "requiredmenu": b"Enlarge"}.get(mode, b"Paste key")
        if (plain or term == "dumb") and "menu" in mode:
            marker = b"Number, then Enter"
        self.wait(marker)

    def send(self, data):
        pending = memoryview(data)
        deadline = time.monotonic() + 5
        while pending:
            if time.monotonic() > deadline:
                raise AssertionError("PTY write timed out; capture withheld")
            try:
                pending = pending[os.write(self.master, pending):]
            except BlockingIOError:
                self.drain(0.02)

    def drain(self, duration=0.1):
        end = time.monotonic() + duration
        while time.monotonic() < end:
            if select.select([self.master], [], [], 0.02)[0]:
                self.output.extend(os.read(self.master, 65536))

    def until(self, predicate):
        end = time.monotonic() + 5
        while not predicate():
            if time.monotonic() > end:
                raise AssertionError("prompt state timed out; capture withheld")
            self.drain(0.03)

    def wait(self, marker, start=0):
        end = time.monotonic() + 5
        while marker not in self.output[start:]:
            if time.monotonic() > end:
                raise AssertionError("prompt state timed out; capture withheld")
            self.drain(0.03)

    def accepted(self, expected):
        self.wait(b"RESTORED True")
        self.process.wait(timeout=5)
        digest = hashlib.sha256(expected.encode()).hexdigest().encode()
        assert b"ACCEPTED " + digest in self.output, "wrong value; capture withheld"
        assert b"\x1b[?2004l" in self.output
        assert self.process.returncode == 0

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=5)
        os.close(self.master)
        os.close(self.slave)


class TerminalTests(unittest.TestCase):
    def start(self, mode="secret", limit=1024 * 1024):
        session = Session(mode, limit)
        self.addCleanup(session.close)
        return session

    def test_multiline_bracketed_paste_waits_for_enter_and_stays_hidden(self):
        session = self.start()
        secret = '{\n  "key": "SYNTHETIC_ONLY_ä_42"\n}'
        # Deliberately split both bracketed-paste markers across reads.
        session.send(b"\x1b[20")
        time.sleep(0.02)
        session.send(b"0~" + secret.encode() + b"\x1b[20")
        time.sleep(0.02)
        session.send(b"1~")
        session.wait(DOTS)
        self.assertIsNone(session.process.poll())
        self.assertNotIn(b"ACCEPTED", session.output)
        self.assertNotIn(b"SYNTHETIC_ONLY", session.output)
        session.send(b"\r")
        session.accepted(secret)

    def test_large_json_and_input_limit(self):
        session = self.start()
        secret = '{\n "synthetic": "' + 'x' * 14000 + '"\n}'
        session.send(b"\x1b[200~" + secret.encode() + b"\x1b[201~")
        session.drain()
        self.assertNotIn(b"ACCEPTED", session.output)
        self.assertNotIn(b"synthetic", session.output)
        session.send(b"\r")
        session.accepted(secret)
        too_large = self.start(limit=32)
        too_large.send(b"\x1b[200~" + b"x" * 40 + b"\x1b[201~")
        too_large.wait(b"RESTORED True")
        self.assertIn(b"REJECTED", too_large.output)

    def test_editing_unicode_and_arrow_keys(self):
        session = self.start()
        session.send("éx".encode() + b"\x7f\x1b[D")
        session.send(b"\r")
        session.accepted("é")
        cleared = self.start()
        cleared.send("SYNTHETIC_DELETE_emoji_😀".encode() + b"\x15")
        cleared.send("new😀".encode() + b"\x7f\r")
        cleared.accepted("new")
        self.assertNotIn(b"SYNTHETIC_DELETE", cleared.output)

    def test_choice_rejects_accidental_secret_paste_without_echo(self):
        session = self.start("choice")
        accidental = b"SYNTHETIC_MISPLACED_credential_9437"
        session.send(b"\x1b[200~" + accidental + b"\x1b[201~github\r")
        session.accepted("github")
        self.assertNotIn(accidental, session.output)
        unicode_choice = self.start("choice")
        unicode_choice.send("café\r".encode())
        unicode_choice.accepted("café")

    def test_cancel_and_signal_restore_terminal(self):
        for cancel in (b"\x1b", b"\x03", b"\x04"):
            with self.subTest(cancel=cancel):
                session = self.start()
                session.send(b"SYNTHETIC_CANCEL" + cancel)
                session.wait(b"RESTORED True")
                self.assertIn(b"CANCELLED", session.output)
                self.assertNotIn(b"SYNTHETIC_CANCEL", session.output)
        for number in (signal.SIGTERM, signal.SIGHUP):
            session = self.start()
            os.kill(session.process.pid, number)
            session.wait(b"RESTORED True")
            self.assertIn(b"CANCELLED", session.output)

    def test_a_refused_paste_is_read_to_its_end_before_the_prompt_leaves(self):
        """Leaving mid-paste would hand the rest of the paste to the shell as commands."""
        for mode, limit, body in (("secret", 1024 * 1024, b"bad\0paste"), ("secret", 32, b"x" * 40)):
            session = self.start(mode, limit)
            session.send(b"\x1b[200~" + body)
            session.drain(0.4)
            self.assertIsNone(session.process.poll(), "left in the middle of a paste")
            self.assertNotIn(b"REJECTED", session.output)
            session.send(b"SYNTHETIC_REST_OF_PASTE; echo SYNTHETIC_COMMAND\r\n" * 20 + b"\x1b[201~")
            session.wait(b"RESTORED True")
            self.assertIn(b"REJECTED", session.output)
            self.assertNotIn(b"SYNTHETIC", session.output)
        menu = self.menu()
        menu.send(b"\x1b[200~bad\0" + b"SYNTHETIC_PASTE_LINE\r\n" * 2500 + b"\x1b[201~")  # About 50 KB.
        self.assertEqual(self.pointed(menu), "Alpha")
        self.assertIsNone(menu.process.poll(), "a menu ignores every paste, whatever is in it")
        self.assertNotIn(b"SYNTHETIC", menu.output)
        menu.send(b"\r")
        self.chosen(menu, 0)

    def test_invalid_utf8_and_nul_restore_terminal(self):
        for value in (b"\xff\r", b"\x1b[200~bad\0paste\x1b[201~"):
            session = self.start()
            session.send(value)
            session.wait(b"RESTORED True")
            self.assertIn(b"REJECTED", session.output)

    def test_mask_shows_at_most_a_quarter_and_three_characters_per_end(self):
        with patch.object(terminal, "glyph", lambda fancy, plain: fancy):
            self.assertEqual(terminal.mask(""), "")
            self.assertEqual(terminal.mask("short12"), "•••••")
            self.assertEqual(terminal.mask("abcdefgh"), "a•••••h")
            self.assertEqual(terminal.mask("abcdefghijklmnop"), "ab•••••op")
            self.assertEqual(terminal.mask("sk_test_" + "x" * 30 + "123"), "sk_•••••123")
            self.assertEqual(terminal.mask("sk_test_" + "x" * 30 + "123", reveal=False), "•" * 24)
            self.assertEqual(terminal.mask("abc", reveal=False), "•••")
            self.assertEqual(terminal.mask(" b\ncdefghijklm\tn"), "•b" + "•••••" + "•n")
            self.assertEqual(terminal.mask("é" * 30), "•" * 11)
        for length in range(0, 80):
            value = "".join(chr(65 + i % 26) for i in range(length))
            shown = terminal.mask(value).replace("•", "").replace("*", "")
            self.assertLessEqual(len(shown), min(6, length // 4))
            self.assertLessEqual(len(terminal.mask(value)), 11)
            self.assertEqual(terminal.mask(value, reveal=False).strip("•*"), "")

    def test_pasted_value_shows_its_ends_but_typing_and_editing_do_not(self):
        pasted = self.start()
        secret = "sk_live_SYNTHETIC_MIDDLE_ONLY_987"
        pasted.send(b"\x1b[200~" + secret.encode() + b"\x1b[201~")
        pasted.wait("sk_•••••987".encode())
        pasted.send(b"\r")
        pasted.accepted(secret)
        self.assertNotIn(b"SYNTHETIC_MIDDLE", pasted.output)
        typed = self.start()
        for char in b"typed_SYNTHETIC_only_42":
            typed.send(bytes([char]))
            typed.drain(0.02)
        typed.send(b"\r")
        typed.accepted("typed_SYNTHETIC_only_42")
        self.assertIn("•".encode() * 23, typed.output)
        for leak in (b"t" + DOT, DOT + b"2", b"typ", b"_42"):
            self.assertNotIn(leak, typed.output)
        edited = self.start()
        short = "sk_live_SYNTH_MID_9876"
        edited.send(b"\x1b[200~" + short.encode() + b"\x1b[201~")
        edited.wait("sk•••••76".encode())
        for count in range(1, 4):
            mark = len(edited.output)
            edited.send(b"\x7f")  # One at a time, so every intermediate state is drawn.
            edited.until(lambda: bytes(edited.output[mark:]).endswith(
                "› ".encode() + DOT * (len(short) - count)))
            drawn = bytes(edited.output[mark:])
            self.assertNotIn(b"sk", drawn)
            self.assertNotIn(DOT + short[-2 - count:-count].encode(), drawn)
        edited.send(b"\r")
        edited.accepted(short[:-3])

    def test_pasting_again_replaces_a_paste_and_appends_to_typing(self):
        session = self.start("strict")
        session.send(b"\x1b[200~first_SYNTHETIC_value_0001\x1b[201~")
        session.wait("fir•••••001".encode())
        session.send(b"\x1b[200~second_SYNTHETIC_value_0002\x1b[201~")
        session.wait("sec•••••002".encode())
        session.send(b"\r")
        session.accepted("second_SYNTHETIC_value_0002")
        self.assertNotIn(b"first_SYNTHETIC", session.output)
        typed = self.start()
        typed.send(b"ab")
        typed.drain(0.1)
        typed.send(b"\x1b[200~cd\x1b[201~\r")
        typed.accepted("abcd")  # A paste after typing appends, and stays fully masked.
        self.assertNotIn(b"ab" + DOTS, typed.output)

    def test_enter_can_refuse_or_print_rows_above_the_prompt(self):
        session = self.start("strict")
        session.send(b"\r")  # Nothing entered: this prompt answers with rows instead of submitting.
        session.wait(b"ROWS_PRINTED_ABOVE")
        session.send(b"not yet\r")
        session.drain(0.2)
        self.assertNotIn(b"ACCEPTED", session.output)
        self.assertIn(b"\a", session.output)
        session.send(b"!\r")
        session.accepted("not yet!")
        self.assertIn(b"\x1b[?2004l", session.output)
        # The rows stay on screen above the prompt through the later redraws.
        self.assertEqual(Screen(80).feed(session.output).count("ROWS_PRINTED_ABOVE"), 1)

    def test_no_echo_between_two_prompts_of_one_session(self):
        session = self.start("quiet")
        session.send(b"\x1b[200~first_SYNTHETIC_0001\x1b[201~\r")
        session.wait(b"BETWEEN echo=False")
        session.wait(b"Paste key again:")
        session.send(b"\x1b[200~second_SYNTHETIC_0002\x1b[201~\r")
        session.accepted("first_SYNTHETIC_0001second_SYNTHETIC_0002")
        self.assertNotIn(b"SYNTHETIC", session.output)

    def menu(self, **options):
        session = Session("menu", **options)
        self.addCleanup(session.close)
        return session

    def chosen(self, session, index):
        session.accepted(str(index))
        screen = Screen(80).feed(session.output)
        # The menu erases itself and shows the cursor again.
        self.assertEqual(screen.count("MENU_TITLE") + screen.count("MENU_HINT") + screen.count("Alpha"), 0)
        self.assertTrue(session.output.rstrip().endswith(b"RESTORED True"))
        self.assertIn(b"\x1b[?25l", session.output)  # Hidden while the menu is up, shown again after.
        self.assertLess(session.output.rfind(b"\x1b[?25l"), session.output.rfind(b"\x1b[?25h"))

    def pointed(self, session):
        """The name on the row the pointer is on, read from the screen as drawn."""
        session.drain(0.15)
        rows = [row for row in Screen(80).feed(session.output).lines() if row.startswith("❯ ")]
        self.assertEqual(len(rows), 1, "the menu was not redrawn in place")
        return rows[0][2:].split()[0]

    def test_menu_moves_with_arrows_wraps_and_skips_gaps(self):
        session = self.menu()
        self.assertEqual(self.pointed(session), "Alpha")
        for keys, name in ((b"\x1b[B", "Beta"), (b"\x1bOB", "Bravo"), (b"\x1b[B", "Gamma"), (b"\x1b[B", "Done"),
                           (b"\x1b[B", "Alpha"), (b"\x1b[A", "Done"), (b"\x1b[H", "Alpha"), (b"\x1b[F", "Done"),
                           (b"\x1b[1~", "Alpha"), (b"\x1b[1;5B", "Beta"), (b"\x10", "Alpha"), (b"\x0e", "Beta"),
                           (b"\x1b[6~", "Done"), (b"\x1b[5~", "Alpha")):
            session.send(keys)
            self.assertEqual(self.pointed(session), name)
        screen = Screen(80).feed(session.output)
        self.assertEqual((screen.count("MENU_TITLE"), screen.count("MENU_HINT"), screen.count("Alpha")), (1, 1, 1))
        # Status shows on every row in one column; the description only on the pointed row.
        rows = screen.lines()
        self.assertIn("❯ Alpha  saved  ABOUT_ALPHA", rows)
        self.assertIn("  Beta", rows)
        self.assertIn("  Bravo  saved", rows)
        self.assertEqual(screen.count("ABOUT_BETA"), 0)
        session.send(b"\x1b[B\x1b[B\r")
        self.chosen(session, 2)

    def test_menu_jumps_to_typed_letters_and_ignores_pastes(self):
        session = self.menu(start=4)
        self.assertEqual(self.pointed(session), "Gamma")
        for keys, name in ((b"b", "Beta"), (b"r", "Bravo"), (b"g", "Gamma"), (b"zz", "Gamma"), (b"D", "Done")):
            session.send(keys)
            self.assertEqual(self.pointed(session), name)
        session.send(b"\x1b[200~SYNTHETIC_MISPLACED_credential_9437\x1b[201~")
        self.assertEqual(self.pointed(session), "Done")
        self.assertNotIn(b"SYNTHETIC_MISPLACED", session.output)
        session.send(b"\x1b[200~gamma\x1b[201~")  # Even a pasted row name does not move the pointer.
        self.assertEqual(self.pointed(session), "Done")
        # An arrow ends a search: the next letter starts a new one instead of extending "d".
        session.send(b"b")
        self.assertEqual(self.pointed(session), "Beta")
        session.send(b"\x1b[B\x1b[A")
        session.send(b"r")
        self.assertEqual(self.pointed(session), "Beta")  # "r" alone matches nothing; "br" would be Bravo.
        session.send(b"\x1b[B\x1b[B\r")
        self.chosen(session, 4)

    def test_menu_survives_odd_key_sequences(self):
        session = self.menu()
        # Each case would move the pointer somewhere else if its bytes leaked through as typed letters.
        for keys, name, why in ((b"\x1b\x1b[A", "Done", "Alt+Up is Escape followed by Up"),
                                (b"\x1b[[A", "Done", "a Linux console function key is one unknown key"),
                                ("é".encode(), "Done", "a letter outside ASCII is not a search"),
                                (b"\x1b[1;", "Done", "a stalled fragment is dropped, not read as Escape"),
                                (b"\x1b[3~", "Done", "Delete does nothing"),
                                (b"g", "Gamma", "typing still works afterwards")):
            session.send(keys)
            time.sleep(0.15)
            self.assertEqual(self.pointed(session), name, why)
            self.assertIsNone(session.process.poll(), why)
        self.assertNotIn(b"CANCELLED", session.output)
        session.send(b"\r")
        self.chosen(session, 4)

    def test_menu_escape_goes_back_and_long_lists_scroll(self):
        for cancel in (b"\x1b", b"\x03"):
            session = self.menu()
            started = time.monotonic()
            session.send(cancel)
            session.wait(b"RESTORED True")
            self.assertLess(time.monotonic() - started, 1.5, "a lone Escape closes the menu promptly")
            self.assertIn(b"CANCELLED", session.output)
            self.assertEqual(Screen(80).feed(session.output).count("Alpha"), 0)
            self.assertLess(session.output.rfind(b"\x1b[?25l"), session.output.rfind(b"\x1b[?25h"))
        session = Session("longmenu", rows=10)
        self.addCleanup(session.close)

        def window():
            session.drain(0.3)
            return [row for row in Screen(80).feed(session.output).lines() if "Item" in row or row.strip() == "⋮"]
        # At the top the pointed first row is visible, with one marker below; at the end the reverse.
        self.assertEqual((window()[0], window()[-1].strip()), ("❯ Item 00", "⋮"))
        session.send(b"\x1b[6~")
        self.assertEqual(sum(row.startswith("❯ Item 05") for row in window()), 1)  # Page Down moves five rows.
        session.send(b"\x1b[F")
        self.assertEqual((window()[0].strip(), window()[-1]), ("⋮", "❯ Item 39"))
        session.send(b"\x1b[H")
        for _ in range(25):
            session.send(b"\x1b[B")
        rows = window()
        self.assertEqual(sum(row.startswith("❯ Item 25") for row in rows), 1)
        self.assertEqual(sum("Item" in row for row in rows), 5)  # 10 rows: gap, hint, two markers, five items.
        self.assertEqual(sum(row.strip() == "⋮" for row in rows), 2)
        session.send(b"\r")
        session.accepted("25")

    def test_color_opt_out_and_redirected_text(self):
        class Output:
            def __init__(self, tty):
                self.tty = tty
            def isatty(self):
                return self.tty
        with patch.dict(os.environ, {"TERM": "xterm-256color"}, clear=True):
            self.assertTrue(terminal.color_enabled(Output(True)))
            self.assertFalse(terminal.color_enabled(Output(False)))
            for name, value in (("NO_COLOR", ""), ("CLICOLOR", "0"), ("TERM", "dumb")):
                with patch.dict(os.environ, {name: value}):
                    self.assertFalse(terminal.color_enabled(Output(True)))

    def test_plain_secret_is_static_hidden_and_requires_review(self):
        for options in ({"plain": True}, {"term": "dumb"}):
            session = Session(**options)
            self.addCleanup(session.close)
            secret = "SYNTHETIC_PLAIN\nSECOND_LINE"
            session.send(b"\x1b[200~" + secret.encode() + b"\x1b[201~")
            session.drain()
            self.assertNotIn(b"ACCEPTED", session.output)
            self.assertNotIn(b"SYNTHETIC", session.output)
            session.send(b"\r")
            session.wait(b"Enter confirms")
            self.assertNotIn(b"ACCEPTED", session.output)
            session.send(b"\r")
            session.accepted(secret)
            clean = bytes(session.output).replace(b"\x1b[?2004h", b"").replace(b"\x1b[?2004l", b"")
            self.assertNotIn(b"\x1b", clean)
            self.assertNotIn(b"SYNTHETIC", clean)

    def test_plain_menu_numbers_and_keeps_required_review(self):
        session = Session("requiredmenu", rows=10, plain=True)
        self.addCleanup(session.close)
        self.assertIn(b"REQUIRED_00", session.output)
        self.assertIn(b"REQUIRED_29", session.output)
        self.assertIn(b"1. Add", session.output)
        session.send(b"\x1b[200~1\rSYNTHETIC_MISPLACED\x1b[201~")
        session.drain()
        self.assertNotIn(b"ACCEPTED", session.output)
        self.assertNotIn(b"SYNTHETIC", session.output)
        session.send(b"1\r")
        session.accepted("0")

    def test_plain_menu_invalid_whole_choice_never_selects_default_or_prefix(self):
        for entered in (b"9", b"12", b"1\xff", b"SYNTHETIC_TYPED_IN_WRONG_FIELD"):
            with self.subTest(entered=entered):
                session = Session("requiredmenu", rows=10, plain=True)
                self.addCleanup(session.close)
                session.send(entered + b"\r")
                session.wait(b"Invalid choice")
                self.assertIsNone(session.process.poll())
                self.assertNotIn(b"ACCEPTED", session.output)
                self.assertNotIn(b"SYNTHETIC", session.output)
                session.send(b"\x15")
                session.send(b"\x1b[200~SYNTHETIC_PASTED_SECRET\x1b[201~")
                session.drain()
                self.assertNotIn(b"SYNTHETIC", session.output)
                session.send(b"1\r")
                session.accepted("0")

    def test_plain_secret_cancel_and_edit_restore_terminal(self):
        for signal_number in (None, signal.SIGTERM):
            session = Session(plain=True)
            self.addCleanup(session.close)
            session.send(b"SYNTHETIC_HIDDEN")
            if signal_number:
                os.kill(session.process.pid, signal_number)
            else:
                session.send(b"\x1b")
            session.wait(b"RESTORED True")
            self.assertIn(b"CANCELLED", session.output)
            self.assertNotIn(b"SYNTHETIC", session.output)
        session = Session(plain=True)
        self.addCleanup(session.close)
        session.send(b"\x1b[200~first\x1b[201~")
        session.send(b"x\x1b[200~next\x1b[201~\r")
        session.wait(b"Enter confirms")
        session.send(b"\r")
        session.accepted("firstxnext")

    def test_plain_intro_and_key_review_work_in_eight_column_terminal(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="godmode-tiny-plain-") as directory:
            home = Path(directory) / ".godmode"
            env = {"HOME": directory, "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                   "TERM": "xterm-256color"}
            command = [sys.executable, str(repo / "tests/engine_fixture.py"), str(repo / "godmode.py"), "--home", str(home), "--plain"]
            intro = Terminal(command + ["intro"], env, cols=8, rows=12)
            try:
                intro.seen("can spend, publish and delete")
                intro.seen("Put your agent to fucking work.")
                intro.seen("Enter accept")
                self.assertNotIn(b"Enlarge", intro.capture)
                intro.send(b"\r")
                intro.done()
                self.assertTrue((home / "intro.seen").exists())
            finally:
                intro.close()
            entry = Terminal(command + ["set", "TINY_TOKEN"], env, cols=8, rows=12)
            try:
                entry.seen("Input hidden")
                before = (home / ".env.godmode").read_bytes()
                entry.paste("SYNTHETIC_TINY_SECRET_587141")
                entry.send(b"\r")
                entry.seen("Add TINY_TOKEN=sealed(")
                entry.seen("Enter saves")
                self.assertEqual((home / ".env.godmode").read_bytes(), before)
                self.assertNotIn(b"Enlarge", entry.capture)
                self.assertNotIn(b"SYNTHETIC_TINY_SECRET", entry.capture)
                entry.send(b"\r")
                entry.done()
                saved = subprocess.run(command + ["list"], env=env, capture_output=True, text=True, check=True)
                self.assertEqual(saved.stdout, "TINY_TOKEN\n")
                clean = bytes(entry.capture).replace(b"\x1b[?2004h", b"").replace(b"\x1b[?2004l", b"")
                self.assertNotIn(b"\x1b", clean)
            finally:
                entry.close()

    def test_required_menu_refuses_enter_until_review_fits(self):
        session = Session("requiredmenu", rows=10)
        self.addCleanup(session.close)
        session.send(b"\r")
        session.drain()
        self.assertNotIn(b"ACCEPTED", session.output)
        fcntl.ioctl(session.slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 80, 0, 0))
        os.kill(session.process.pid, signal.SIGWINCH)
        session.wait(b"REQUIRED_29")
        session.send(b"\r")
        session.accepted("0")

    def test_menu_search_filters_and_rejects_paste(self):
        session = Session("searchmenu")
        self.addCleanup(session.close)
        session.send(b"/br")
        session.drain()
        screen = Screen(80).feed(session.output)
        self.assertIn("Bravo", "\n".join(screen.lines()))
        self.assertNotIn("Alpha", "\n".join(screen.lines()))
        session.send(b"\x1b[200~SYNTHETIC_FILTER_SECRET\x1b[201~")
        session.drain()
        self.assertNotIn(b"SYNTHETIC", session.output)
        session.send(b"\r")
        session.accepted("2")

    def test_menu_search_with_no_matches_cannot_submit(self):
        session = Session("searchmenu")
        self.addCleanup(session.close)
        session.send(b"/zzzz\r")
        session.wait(b"No matches")
        self.assertNotIn(b"ACCEPTED", session.output)
        session.send(b"\x1b")
        session.drain()
        session.send(b"\r")
        session.accepted("0")

    def test_tab_discloses_without_submitting_or_interpreting_paste(self):
        session = Session("disclosure")
        self.addCleanup(session.close)
        session.send(b"\x1b[200~SYNTHETIC\tVALUE\x1b[201~")
        session.drain()
        self.assertNotIn(b"DETAILS_VISIBLE", session.output)
        session.send(b"\t")
        session.wait(b"DETAILS_VISIBLE")
        self.assertNotIn(b"ACCEPTED", session.output)
        session.send(b"\r")
        session.accepted("SYNTHETIC\tVALUE")

    def test_narrow_menu_keeps_rows_within_width_and_details_available(self):
        session = Session("widemenu", width=40)
        self.addCleanup(session.close)
        session.drain()
        rendered = bytes(session.output).split(b"\x1b[J")[-1].decode()
        for row in rendered.split("\r\n"):
            self.assertLess(terminal.cells(row), 40)
        session.send(b"\t")
        session.wait(b"Entire details")
        self.assertNotIn(b"ACCEPTED", session.output)
        session.send(b"\t\r")
        session.accepted("0")


if __name__ == "__main__":
    unittest.main()
