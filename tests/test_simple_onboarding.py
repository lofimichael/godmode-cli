"""Public onboarding commands, with isolated homes and synthetic facts/keys only."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

from pty_support import Screen, Terminal


REPO = Path(__file__).resolve().parents[1]
FIELDS = ("operator_name", "business_name", "legal_name", "website",
          "public_email", "business_mailing_address")
LABELS = ("Your name", "Business name", "Legal name", "Website",
          "Public contact email", "Business mailing address")
FACTS = ("Zoë Example", "Example Studio", "Example LLC", "https://example.test",
         "hello@example.test", "123 Example Street\nExample City")

# Audit actual subprocess I/O rather than substituting a fake credential store.
# Guidance commands should work even when opening credential files is forbidden.
READ_ONLY_GUIDANCE = """
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
runpy.run_path(script, run_name='__main__')
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
        return subprocess.run(prefix + [str(self.script), *args], input=input,
                              env=self.env if env is None else env, cwd=self.root,
                              capture_output=True, text=True, timeout=10)

    def okay(self, *args, **kwargs):
        result = self.cli(*args, **kwargs)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def terminal(self, *args):
        session = Terminal([sys.executable, str(self.script), *args], self.env)
        self.addCleanup(session.close)
        return session

    def choice(self, session, label):
        session.wait(lambda: any(row.startswith("❯ " + label)
                                for row in Screen(110).feed(session.capture).lines()))

    def open_choice(self, session, label):
        self.choice(session, label)
        mark = len(session.capture)
        session.send(b"\r")
        session.after(mark, "Enter saves")

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
        self.choice(session, "Your details")
        screen = "\n".join(Screen(110).feed(session.capture).lines())
        for label in ("Your details", "Credentials", "Agent instructions", "Done"):
            self.assertIn(label, screen)
        self.assertEqual(list(self.root.iterdir()), [])
        session.send(b"\r")
        for label in LABELS:
            self.open_choice(session, label)
            session.send(b"\r")
        # Finishing the sixth field must select Done, not a separator or the first field.
        self.choice(session, "Done")
        self.assertEqual(list(self.root.iterdir()), [])
        session.send(b"\r")
        self.choice(session, "Your details")
        session.send(b"\x1b")
        session.done()
        self.assertEqual(list(self.root.iterdir()), [])

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
        self.open_choice(session, "Your name")
        mark = len(session.capture)
        session.send(FACTS[0].encode())
        session.after(mark, FACTS[0])  # Facts are visible while entered, unlike credentials.
        self.assertFalse(self.profile.exists())
        session.send(b"\r")
        self.choice(session, "Business name")
        self.assertEqual(json.loads(self.profile.read_text()), {FIELDS[0]: FACTS[0]})
        session.send(b"\x1b[B" * 4)
        self.open_choice(session, "Business mailing address")
        session.paste("123 Example Street\r\nExample City\r\n")
        session.send(b"\r")
        self.choice(session, "Done")
        session.send(b"\r")
        session.done()
        self.assertEqual(json.loads(self.profile.read_text()),
                         {FIELDS[0]: FACTS[0], FIELDS[-1]: FACTS[-1]})
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), ["profile.json"])

    def test_installer_init_enters_optional_onboarding_without_creating_a_store(self):
        session = self.terminal("init")
        self.choice(session, "Your details")
        session.send(b"\x1b")
        session.done()
        self.assertEqual(list(self.root.iterdir()), [])

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
        self.assertIn("godmode help", output)
        self.assertIn("profile get", output)
        self.assertIn("Keep existing text", output)
        self.assertNotIn("synthetic_fixture", output)
        self.assertEqual(self.snapshot(), before)

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
