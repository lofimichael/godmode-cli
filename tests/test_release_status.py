"""Exercise the advisory with real Git history and a stubbed live manifest."""

from contextlib import redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/release_status.py"
SPEC = importlib.util.spec_from_file_location("release_status", SCRIPT)
release_status = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_status)


class ReleaseStatusTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="godmode-release-status-")
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name) / "repo"
        self.repo.mkdir()
        self.environment = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        self.git("init", "-q", "--initial-branch=main")
        self.git("config", "user.name", "Release Test")
        self.git("config", "user.email", "release@example.invalid")
        self.commit("release", {"VERSION": "0.20.0\n", "godmode.py": "live\n", "lib/removed.py": "live\n"})
        self.git("tag", "-a", "v0.20.0", "-m", "released")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, env=self.environment,
                              capture_output=True, check=True, timeout=10).stdout

    def commit(self, message, files):
        for name, contents in files.items():
            path = self.repo / name
            if contents is None:
                path.unlink()
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", message)

    def advisory(self, version="v0.20.0", error=None):
        output = io.StringIO()
        with mock.patch.object(release_status, "live_version", return_value=version, side_effect=error), \
                redirect_stdout(output):
            release_status.main(self.repo)
        return output.getvalue()

    def test_warns_for_net_runtime_updates_from_the_exact_live_tag(self):
        self.commit("another tag", {"VERSION": "0.20.1\n", "godmode.py": "new\n"})
        self.git("tag", "v0.20.1")
        self.commit("more changes", {"cmd/godmode/runtime.go": "new\n", "lib/removed.py": None,
                                     "internal/core/core.py": "new\n", "docs/README.md": "new\n"})
        self.assertIn("::warning title=Unreleased CLI runtime::4 runtime files differ from live v0.20.0.",
                      self.advisory())
        self.assertIn("3 runtime files differ from live v0.20.1.", self.advisory("v0.20.1"))

    def test_ignores_docs_tests_metadata_and_reverted_runtime_changes(self):
        self.commit("transient", {"godmode.py": "transient\n"})
        self.commit("docs and tests", {"godmode.py": "live\n", "VERSION": "0.21.0\n",
                                      "README.md": "new\n", "docs/commands.md": "new\n",
                                      "tests/test_runtime.py": "new\n", "cmd/godmode/main_test.go": "new\n",
                                      "internal/ui/testdata/display.json": "new\n", "lib/test_example.py": "new\n",
                                      "vendor/example/README.md": "new\n", "vendor/example/.github/check.yml": "new\n",
                                      "scripts/check.py": "new\n"})
        self.assertEqual(self.advisory(), "No runtime changes since live v0.20.0.\n")

    def test_includes_installer_embedded_catalog_and_build_inputs(self):
        self.commit("build inputs", {"scripts/build-native.sh": "new\n", "providers.json": "{}\n",
                                     "install.sh": "new\n", "go.mod": "new\n", "vendor/modules.txt": "new\n",
                                     "vendor/example/native.s": "new\n"})
        self.assertIn("6 runtime files differ from live v0.20.0.", self.advisory())

    def test_missing_mislabeled_and_unrelated_tags_are_advisory_only(self):
        missing = self.advisory("v0.20.1")
        self.assertIn("::notice", missing)
        self.assertNotIn("::warning", missing)

        self.git("tag", "v0.20.1")
        self.assertEqual(self.advisory("v0.20.1"), missing)

        self.git("checkout", "-q", "--detach")
        self.commit("unrelated to main tip", {"VERSION": "0.20.2\n"})
        self.git("tag", "v0.20.2")
        self.git("checkout", "-q", "main")
        output = self.advisory("v0.20.2")
        self.assertIn("::notice", output)
        self.assertNotIn("::warning", output)

    def test_timeout_is_advisory_only(self):
        output = self.advisory(error=subprocess.TimeoutExpired("curl", 5))
        self.assertIn("::notice", output)
        self.assertNotIn("::warning", output)

    def test_live_manifest_requires_a_canonical_stable_version(self):
        with mock.patch.object(release_status.subprocess, "run") as curl:
            curl.return_value.stdout = b'{"version":"v0.20.0"}'
            self.assertEqual(release_status.live_version(), "v0.20.0")
            self.assertEqual(curl.call_args.args[0][-1], "https://godmode.build/releases/latest.json")
            self.assertEqual(curl.call_args.kwargs["timeout"], 5)
            for payload in (b"not JSON", b"[]", b'{"version":"v0.20.0-rc.1"}',
                            b'{"version":"v0.020.0"}', b'{"version":"v0.20.0\\n::warning"}'):
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    curl.return_value.stdout = payload
                    release_status.live_version()


if __name__ == "__main__":
    unittest.main()
