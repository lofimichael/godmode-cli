"""Public onboarding commands, with isolated homes and synthetic facts/keys only."""
import fcntl
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import termios
import unittest

from pty_support import Screen, Terminal, plain
from test_simple_intro import complete_intro


REPO = Path(__file__).resolve().parents[1]
FIELDS = ("operator_name", "business_name", "legal_name", "website",
          "public_email", "business_mailing_address")
LABELS = ("Your name", "Business name", "Legal name", "Website",
          "Public email", "Mailing address")
FACTS = ("Zoë Example", "Example Studio", "Example LLC", "https://example.test",
         "hello@example.test", "123 Example Street\nExample City")

# Audit actual subprocess I/O rather than substituting a fake credential store.
# Guidance commands should work even when opening credential files is forbidden.
READ_ONLY_GUIDANCE = r"""
import os, runpy, sys
script = sys.argv[1]
sys.argv = sys.argv[1:]
def audit(event, args):
    if event == 'open':
        path, mode, flags = args
        if isinstance(path, (str, bytes, os.PathLike)):
            if os.path.basename(os.fsdecode(path)) in ('.env.godmode', 'seal.key'):
                raise RuntimeError('guidance attempted credential access')
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            raise RuntimeError('guidance attempted a file write')
    if event in ('os.mkdir', 'os.remove', 'os.rename', 'os.rmdir', 'os.chmod',
                 'os.link', 'os.symlink', 'os.truncate'):
        raise RuntimeError('guidance attempted a filesystem change')
sys.addaudithook(audit)
source = open(script).read()
exec(compile(source, script, 'exec'), {'__name__':'__main__','__file__':script})
"""


class ModularOnboardingTests(unittest.TestCase):
    """Run the same observable contract against source and the standalone build."""
    bundled = False

    @classmethod
    def setUpClass(cls):
        cls.script = REPO / "godmode.py"
        if cls.bundled:
            build = tempfile.TemporaryDirectory(prefix="godmode-onboarding-build-")
            cls.addClassCleanup(build.cleanup)
            cls.script = Path(build.name) / "godmode"
            subprocess.run([sys.executable, str(REPO / "scripts/build.py"),
                            "--output", str(cls.script)], check=True,
                           stdout=subprocess.DEVNULL)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="godmode-onboarding-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.home = self.root / ".godmode"
        self.profile = self.home / "profile.json"
        self.env = {"HOME": str(self.root), "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "TERM": "xterm-256color", "SHELL": "/bin/sh", "NO_COLOR": "1",
                    "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}

    def cli(self, *args, input=None, env=None, guidance=False):
        prefix = [sys.executable]
        if guidance:
            prefix += ["-c", READ_ONLY_GUIDANCE]
        else:
            prefix += [str(REPO / 'tests/engine_fixture.py')]
        return subprocess.run(prefix + [str(self.script), *args], input=input,
                              env=self.env if env is None else env, cwd=self.root,
                              capture_output=True, text=True, timeout=10)

    def okay(self, *args, **kwargs):
        result = self.cli(*args, **kwargs)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def terminal(self, *args):
        session = Terminal([sys.executable, str(REPO / 'tests/engine_fixture.py'), str(self.script), *args], self.env)
        self.addCleanup(session.close)
        return session

    def choice(self, session, label):
        session.wait(lambda: any(row.startswith("❯ " + label)
                                for row in Screen(110).feed(session.capture).lines()))

    def prompt(self, session, mark, label):
        """Wait for a field prompt: its label above the visible input row."""
        session.wait(lambda: any(row.strip() == label for row in Screen(110).feed(session.capture).lines())
                     and "› " in plain(session.capture[mark:]))

    def open_choice(self, session, label):
        self.choice(session, label)
        mark = len(session.capture)
        session.send(b"\r")
        self.prompt(session, mark, label)

    def seed(self, path, contents):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.parent.chmod(0o700)
        path.write_bytes(contents if isinstance(contents, bytes) else contents.encode())
        path.chmod(0o600)

    def snapshot(self):
        return {str(path.relative_to(self.root)):
                (stat.S_IMODE(path.stat().st_mode), path.stat().st_mtime_ns,
                 path.read_bytes() if path.is_file() else None)
                for path in self.root.rglob("*")}

    def test_default_menu_and_all_six_optional_fields_can_be_skipped(self):
        session = self.terminal()
        complete_intro(session)
        self.choice(session, "Business")
        screen = "\n".join(Screen(110).feed(session.capture).lines())
        for label in ("Business", "Providers", "Agents", "Done", "Environment default", "0 fields", "0 keys saved", "0 notes added"):
            self.assertIn(label, screen)
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), ["intro.seen"])
        session.send(b"\r")
        self.choice(session, "Edit profile")
        session.send(b"\r")
        self.open_choice(session, LABELS[0])
        # Enter on an empty field skips it and opens the next empty one: one Enter per field.
        for index, label in enumerate(LABELS):
            mark = len(session.capture)
            self.assertIn("Enter skips", plain(session.capture))
            session.send(b"\r")
            if index + 1 < len(LABELS):
                self.prompt(session, mark, LABELS[index + 1])
        # After the sixth field the pointer rests on Back, not a separator or the first field.
        self.choice(session, "Back")
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), ["intro.seen"])
        session.send(b"\r")
        self.choice(session, "Edit profile")
        session.send(b"\x1b")
        self.choice(session, "Business")  # Home keeps the section that was opened.
        session.send(b"\x1b")
        session.expect("Profile 0 optional fields")
        session.done()
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), ["intro.seen"])

    def test_visible_profile_entry_rejects_controls_and_accepts_multiline_address(self):
        session = self.terminal("profile")
        self.open_choice(session, "Your name")
        unsafe = "Example\x1b]0;UNSAFE_TITLE\x07"
        mark = len(session.capture)
        session.paste(unsafe)
        session.after(mark, r"\u001b]0;UNSAFE_TITLE\u0007")
        self.assertNotIn(unsafe.encode(), session.capture)
        session.send(b"\r")
        session.after(mark, "contains control characters")
        self.assertFalse(self.profile.exists())
        self.prompt(session, mark, "Your name")  # The same field opens again.
        mark = len(session.capture)
        session.send(FACTS[0].encode())
        session.after(mark, FACTS[0])  # Facts are visible while entered, unlike credentials.
        self.assertFalse(self.profile.exists())
        session.send(b"\r")
        self.prompt(session, mark, "Business name")  # Saving opens the next empty field.
        self.assertEqual(json.loads(self.profile.read_text()), {FIELDS[0]: FACTS[0]})
        session.send(b"\x1b")
        self.choice(session, "Business name")
        screen = "\n".join(Screen(110).feed(session.capture).lines())
        self.assertIn(FACTS[0], screen)  # The list shows saved values.
        session.send(b"\x1b[B" * 4)
        self.open_choice(session, "Mailing address")
        mark = len(session.capture)
        session.paste("123 Example Street\r\nExample City\r\n")
        session.after(mark, "123 Example Street ↵ Example City")
        session.send(b"\r")
        self.choice(session, "Done")
        self.assertIn("123 Example Street, Example City", "\n".join(Screen(110).feed(session.capture).lines()))
        session.send(b"\r")
        session.done()
        self.assertEqual(json.loads(self.profile.read_text()),
                         {FIELDS[0]: FACTS[0], FIELDS[-1]: FACTS[-1]})
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), ["profile.json"])

    def test_installer_init_enters_optional_onboarding_without_creating_a_store(self):
        session = self.terminal("init")
        complete_intro(session)
        self.choice(session, "Business")
        session.send(b"\x1b")
        session.done()
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), ["intro.seen"])

    def test_profile_read_commands_and_unsetting_missing_facts_create_nothing(self):
        self.assertEqual(self.okay("profile", "path").strip(), str(self.profile))
        self.assertEqual(json.loads(self.okay("profile", "show")), {})
        for field in FIELDS:
            with self.subTest(field=field):
                missing = self.cli("profile", "get", field)
                self.assertEqual(missing.returncode, 1)
                self.assertEqual(missing.stdout, "")
                self.assertIn(field, missing.stderr)
                self.okay("profile", "unset", field)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_profile_subcommands_preserve_unknown_json_and_read_only_requested_field(self):
        future = {"future": {"tags": ["synthetic", True, None, 7], "nested": {"a": 1}}}
        self.seed(self.profile, json.dumps(future))
        for field, fact in zip(FIELDS, FACTS):
            self.okay("profile", "set", field, "--stdin", input=fact + "\n")
        expected = dict(future, **dict(zip(FIELDS, FACTS)))
        self.assertEqual(json.loads(self.okay("profile", "show")), expected)
        self.assertEqual(json.loads(self.profile.read_text()), expected)
        for field, fact in zip(FIELDS, FACTS):
            self.assertEqual(self.okay("profile", "get", field), fact + "\n")
        self.assertEqual(stat.S_IMODE(self.home.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.profile.stat().st_mode), 0o600)
        self.okay("profile", "unset", "operator_name")
        expected.pop("operator_name")
        self.assertEqual(json.loads(self.profile.read_text()), expected)
        self.assertEqual(self.cli("profile", "get", "operator_name").returncode, 1)

    def test_profile_bad_input_does_not_create_or_replace_facts(self):
        for args, data in ((["profile", "set", "operator_name", "--stdin"], " \n"),
                           (["profile", "set", "website", "--stdin"], "bad\x1b[2J"),
                           (["profile", "set", "unknown_field", "--stdin"], "Example"),
                           (["profile", "get", "unknown_field"], None)):
            with self.subTest(args=args):
                self.assertEqual(self.cli(*args, input=data).returncode, 2)
                self.assertFalse(self.home.exists())
        self.okay("profile", "set", "operator_name", "--stdin", input="Example")
        before = self.profile.read_bytes()
        bad = self.cli("profile", "set", "operator_name", "a-value-is-not-an-argument")
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(self.profile.read_bytes(), before)

    def test_bad_profile_does_not_block_credentials_or_provider_guidance(self):
        malformed = b'{"operator_name":'
        self.seed(self.profile, malformed)
        self.assertEqual(self.cli("profile", "show").returncode, 2)
        self.okay("set", "SYNTHETIC_TOKEN", "--stdin", input="synthetic_fixture_token")
        self.assertEqual(self.okay("list"), "SYNTHETIC_TOKEN\n")
        child = ("import os,sys; "
                 "sys.exit(0 if os.environ['SYNTHETIC_TOKEN']=='synthetic_fixture_token' else 1)")
        self.okay("run", "SYNTHETIC_TOKEN", "--", sys.executable, "-c", child)
        self.assertIn("GH_TOKEN", self.okay("provider", "github", guidance=True))
        self.assertIn("profile get", self.okay("help"))
        self.assertEqual(self.profile.read_bytes(), malformed)

    def test_default_profile_keeps_legacy_credentials_in_their_existing_home(self):
        legacy = self.root / ".config" / "godmode"
        credential = legacy / ".env.godmode"
        original = b"# synthetic legacy fixture\nLEGACY_TOKEN='legacy_fixture_value'\n"
        self.seed(credential, original)
        self.assertEqual(self.okay("path").strip(), str(credential))
        self.okay("profile", "set", "business_name", "--stdin", input="Example Studio")
        self.assertEqual(self.okay("profile", "path").strip(), str(self.profile))
        self.assertEqual(self.okay("path").strip(), str(credential))
        self.assertEqual(self.okay("list"), "LEGACY_TOKEN\n")
        self.assertEqual(credential.read_bytes(), original)
        self.assertFalse((legacy / "profile.json").exists())
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), ["profile.json"])
        child = "import os; assert os.environ['LEGACY_TOKEN']=='legacy_fixture_value'"
        self.okay("run", "LEGACY_TOKEN", "--", sys.executable, "-c", child)
        self.assertEqual(credential.read_bytes(), original)

    def test_explicit_and_environment_homes_apply_to_profile_and_keys(self):
        environment_home = self.root / "environment home"
        explicit_home = self.root / "explicit home"
        env = dict(self.env, GODMODE_HOME=str(environment_home))
        self.okay("profile", "set", "operator_name", "--stdin", input="Environment", env=env)
        self.okay("set", "ENV_TOKEN", "--stdin", input="synthetic_env", env=env)
        self.assertEqual(self.okay("profile", "path", env=env).strip(), str(environment_home / "profile.json"))
        self.assertEqual(self.okay("path", env=env).strip(), str(environment_home / ".env.godmode"))
        prefix = ("--home", str(explicit_home))
        self.okay(*prefix, "profile", "set", "operator_name", "--stdin", input="Explicit", env=env)
        self.okay(*prefix, "set", "EXPLICIT_TOKEN", "--stdin", input="synthetic_explicit", env=env)
        self.assertEqual(self.okay(*prefix, "profile", "get", "operator_name", env=env), "Explicit\n")
        self.assertEqual(self.okay("profile", "get", "operator_name", env=env), "Environment\n")
        self.assertEqual(self.okay(*prefix, "list", env=env), "EXPLICIT_TOKEN\n")
        self.assertEqual(self.okay("list", env=env), "ENV_TOKEN\n")
        self.assertIn(str(explicit_home), self.okay(*prefix, "agents", env=env, guidance=True))
        self.assertFalse(self.home.exists())

    def test_agents_is_copyable_guidance_and_preserves_existing_global_files(self):
        files = (".codex/AGENTS.md", ".codex/AGENTS.override.md", ".claude/CLAUDE.md",
                 ".gemini/GEMINI.md", ".cursor/rules/custom.mdc",
                 ".copilot/copilot-instructions.md", ".config/opencode/AGENTS.md",
                 ".codeium/windsurf/memories/global_rules.md", ".config/devin/AGENTS.md",
                 ".config/godmode/AGENTS.md")
        for path in files:
            self.seed(self.root / path, "# Keep this custom instruction\n" + path + "\n")
        self.seed(self.home / ".env.godmode", "DO_NOT_READ='synthetic_fixture'\n")
        self.seed(self.home / "seal.key", "not a real key\n")
        before = self.snapshot()
        output = self.okay("agents", guidance=True)
        self.assertTrue(output.startswith("<!-- godmode:start -->\n"))
        self.assertTrue(output.endswith("<!-- godmode:end -->\n"))
        self.assertIn("`godmode help`", output)
        self.assertIn("`godmode run`", output)
        self.assertNotIn("synthetic_fixture", output)
        self.assertEqual(self.snapshot(), before)

    def seen(self):
        self.home.mkdir(mode=0o700, exist_ok=True)
        os.close(os.open(self.home / "intro.seen", os.O_WRONLY | os.O_CREAT, 0o600))

    def test_clearing_a_profile_value_and_saved_values_in_the_form(self):
        self.okay("profile", "set", "website", "--stdin", input=FACTS[3])
        session = self.terminal("profile")
        self.choice(session, "Your name")  # The first empty field.
        self.assertIn(FACTS[3], "\n".join(Screen(110).feed(session.capture).lines()))
        session.send(b"\x1b[B" * 3)
        self.open_choice(session, "Website")
        self.assertIn("Saved: " + FACTS[3], plain(session.capture))
        self.assertIn("Enter keeps it · /clear removes", plain(session.capture))
        mark = len(session.capture)
        session.send(b"/clear")
        session.after(mark, "Enter removes it")
        session.send(b"\r")
        self.prompt(session, mark, "Public email")
        session.send(b"\x1b")
        self.choice(session, "Public email")
        session.send(b"\x1b")
        session.done()
        self.assertEqual(json.loads(self.profile.read_text()), {})

    def test_agents_screen_adds_the_previewed_note_and_keeps_existing_text(self):
        self.seen()
        (self.root / ".claude").mkdir()
        codex = self.root / ".codex"
        codex.mkdir()
        dotfiles = self.root / "dotfiles"
        dotfiles.mkdir()
        (dotfiles / "AGENTS.md").write_bytes(b"# My rules\nno trailing newline")
        (codex / "AGENTS.md").symlink_to(dotfiles / "AGENTS.md")
        (self.root / ".gemini").mkdir()
        (self.root / ".gemini" / "GEMINI.md").write_text("Run godmode help when you need keys.\n")
        note = self.okay("agents")
        session = self.terminal("agents")
        session.expect("Add to Claude Code and Codex")
        screen = plain(session.capture)
        for text in ("These files will be created:", "~/.claude/rules/godmode.md",
                     "These files will be modified:", "~/.codex/AGENTS.md",
                     "✓ added", "~/.gemini/GEMINI.md", "<!-- godmode:start -->"):
            self.assertIn(text, screen)
        self.assertNotIn("I added it", screen)
        session.send(b"\r")
        session.expect("New agent sessions read the note.")
        session.done()
        self.assertEqual((self.root / ".claude/rules/godmode.md").read_text(), note)
        self.assertTrue((codex / "AGENTS.md").is_symlink())
        self.assertEqual((dotfiles / "AGENTS.md").read_text(), "# My rules\nno trailing newline\n\n" + note)
        self.assertEqual((self.root / ".gemini/GEMINI.md").read_text(), "Run godmode help when you need keys.\n")
        before = self.snapshot()
        again = self.terminal("agents")
        again.expect("✓ added")
        self.assertNotIn("Add to", plain(again.capture))
        again.send(b"\x1b")
        again.done()
        self.assertEqual(self.snapshot(), before)
        # A non-empty override is the file Codex reads, so it is the target.
        (codex / "AGENTS.override.md").write_text("# Override\n")
        override = self.terminal("agents")
        override.expect("Add to Codex")
        self.assertIn("~/.codex/AGENTS.override.md", plain(override.capture))
        override.send(b"\x1b")
        override.done()
        self.assertEqual((codex / "AGENTS.override.md").read_text(), "# Override\n")

    def test_long_saved_profile_value_remains_available_in_details_and_plain_output(self):
        value = "https://example.test/" + "long-path-segment/" * 10 + "final-value"
        self.okay("profile", "set", "website", "--stdin", input=value)
        before = self.snapshot()
        visual = Terminal([sys.executable, str(REPO / 'tests/engine_fixture.py'), str(self.script), "profile"], self.env, cols=80, rows=20)
        self.addCleanup(visual.close)
        visual.expect("Your name")
        visual.send(b"w")
        visual.expect("Tab details")
        mark = len(visual.capture)
        visual.send(b"\t")
        visual.after(mark, "final-value")
        self.assertIn(value, "".join(plain(visual.capture[mark:]).split()))
        visual.send(b"\t\x1b")
        visual.done()
        for route in (("profile",), ("profile", "set", "website")):
            with self.subTest(route=route):
                session = Terminal([sys.executable, str(REPO / 'tests/engine_fixture.py'), str(self.script), "--plain", *route],
                                   self.env, cols=40, rows=12)
                self.addCleanup(session.close)
                session.wait(lambda: value in "".join(plain(session.capture).split()))
                self.assertIn(value, "".join(plain(session.capture).split()))
                session.send(b"\x1b")
                session.done(130 if "set" in route else 0)
        self.assertEqual(self.snapshot(), before)

    def test_profile_save_waits_for_readable_form_after_tiny_resize(self):
        original = 'https://before.example.test'
        replacement = 'https://after.example.test'
        self.okay('profile', 'set', 'website', '--stdin', input=original)
        before = self.snapshot()
        session = Terminal([sys.executable, str(REPO / 'tests/engine_fixture.py'), str(self.script), 'profile', 'set', 'website'],
                           self.env, cols=80, rows=24)
        self.addCleanup(session.close)
        session.expect('Enter keeps it')
        session.send(replacement.encode())
        session.expect(replacement)
        mark = len(session.capture)
        fcntl.ioctl(session.slave, termios.TIOCSWINSZ, struct.pack('HHHH', 12, 2, 0, 0))
        session.wait(lambda: b'\x1b[J' in session.capture[mark:])
        session.send(b'\r')
        session.settle(.1)
        self.assertIsNone(session.process.poll())
        self.assertNotIn('Traceback', plain(session.capture))
        self.assertEqual(self.snapshot(), before)
        mark = len(session.capture)
        fcntl.ioctl(session.slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
        session.after(mark, 'Enter saves')
        session.after(mark, replacement)
        session.send(b'\r')
        session.done()
        self.assertEqual(self.okay('profile', 'get', 'website'), replacement + '\n')

    def test_agent_write_requires_readable_preview_after_resize(self):
        self.seen()
        (self.root / ".claude").mkdir()
        target = self.root / ".claude/rules/godmode.md"
        session = Terminal([sys.executable, str(REPO / 'tests/engine_fixture.py'), str(self.script), "agents"], self.env, cols=40, rows=12)
        self.addCleanup(session.close)
        session.expect("Enlarge the terminal")
        session.send(b"\r")
        session.settle(.1)
        self.assertFalse(target.exists())
        self.assertIsNone(session.process.poll())
        mark = len(session.capture)
        fcntl.ioctl(session.slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 80, 0, 0))
        session.after(mark, "Add to Claude Code")
        screen = "\n".join(Screen(80).feed(session.capture[mark:]).lines())
        self.assertIn("~/.claude/rules/godmode.md", screen)
        self.assertIn("<!-- godmode:start -->", screen)
        self.assertIn("<!-- godmode:end -->", screen)
        self.assertFalse(target.exists())
        session.send(b"\r")
        session.done()
        self.assertEqual(target.read_text(), self.okay("agents"))

    def test_all_agent_targets_and_full_note_fit_standard_terminal(self):
        for folder in (".claude", ".codex", ".gemini", ".copilot", ".config/opencode"):
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        session = Terminal([sys.executable, str(REPO / 'tests/engine_fixture.py'), str(self.script), "agents"], self.env, cols=80, rows=24)
        self.addCleanup(session.close)
        session.expect("Add to 5 agents")
        screen = "\n".join(Screen(80).feed(session.capture).lines())
        for name in ("~/.claude/rules/godmode.md", "~/.codex/AGENTS.md", "~/.gemini/GEMINI.md",
                     "~/.copilot/copilot-instructions.md", "~/.config/opencode/AGENTS.md",
                     "<!-- godmode:start -->", "<!-- godmode:end -->"):
            self.assertIn(name, screen)
        session.send(b"\x1b")
        session.done()
        self.assertFalse((self.root / ".claude/rules/godmode.md").exists())

    def test_agents_screen_without_agent_folders_marks_by_hand_and_esc_writes_nothing(self):
        self.seen()
        stub = self.root / "stub"
        stub.mkdir()
        env = dict(self.env, PATH=str(stub))  # No pbcopy, wl-copy or xclip: the item prints the note instead.
        session = Terminal([sys.executable, str(REPO / 'tests/engine_fixture.py'), str(self.script), "agents"], env)
        self.addCleanup(session.close)
        session.expect("I added it")
        self.assertIn("Print task instructions", plain(session.capture))
        before = self.snapshot()
        session.send(b"\x1b")
        session.done()
        self.assertEqual(self.snapshot(), before)
        marked = Terminal([sys.executable, str(REPO / 'tests/engine_fixture.py'), str(self.script), "agents"], env)
        self.addCleanup(marked.close)
        marked.expect("I added it")
        marked.send(b"\x1b[B\r")
        marked.expect("Marked as added")
        marked.done()
        marker = self.home / "agent.added"
        self.assertEqual((marker.read_bytes(), stat.S_IMODE(marker.stat().st_mode)), (b"", 0o600))

    def test_a_home_reached_through_a_symlink_works_and_a_symlinked_home_is_refused(self):
        real = self.root / "real"
        real.mkdir()
        linked = self.root / "linked"
        linked.symlink_to(real)
        env = dict(self.env, HOME=str(linked))
        self.okay("set", "LINKED_TOKEN", "--stdin", input="synthetic_linked", env=env)
        self.okay("profile", "set", "business_name", "--stdin", input="Example", env=env)
        self.assertEqual(self.okay("list", env=env), "LINKED_TOKEN\n")
        self.assertEqual(json.loads(self.okay("profile", "show", env=env)), {"business_name": "Example"})
        self.assertTrue((real / ".godmode" / ".env.godmode").is_file())
        target = self.root / "elsewhere"
        target.mkdir(mode=0o700)
        pointed = self.root / "pointed-home"
        pointed.symlink_to(target)
        for args in (("set", "POINTED_TOKEN", "--stdin"), ("profile", "show")):
            with self.subTest(args=args):
                result = self.cli("--home", str(pointed), *args, input="synthetic_pointed")
                self.assertEqual(result.returncode, 2)
                self.assertIn("is a symlink or not a directory", result.stderr)
        self.assertEqual(list(target.iterdir()), [])

    def test_provider_catalog_specific_guide_and_unknown_slug_never_access_keys(self):
        self.seed(self.home / ".env.godmode", "DO_NOT_READ='synthetic_fixture'\n")
        self.seed(self.home / "seal.key", "not a real key\n")
        before = self.snapshot()
        catalog = self.okay("provider", guidance=True)
        self.assertIn("github", catalog)
        self.assertIn("cloudflare", catalog)
        guide = self.okay("provider", "github", guidance=True)
        self.assertIn("GH_TOKEN", guide)
        self.assertIn("https://github.com/", guide)
        self.assertIn("Verify", guide)
        self.assertIn("Recover", guide)
        bad = self.cli("provider", "not-a-real-provider", guidance=True)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("Unknown provider", bad.stderr)
        self.assertNotIn("Traceback", bad.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertNotIn("synthetic_fixture", catalog + guide + bad.stdout + bad.stderr)


class BundledOnboardingTests(ModularOnboardingTests):
    bundled = True


if __name__ == "__main__":
    unittest.main()
