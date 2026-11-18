"""Core pack management and the companion remain separate from key selection."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class MusicIsolation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gm-music-isolation-")
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / ".godmode"
        self.home.mkdir(mode=0o700)
        self.env = {"HOME": str(self.root), "PATH": os.environ["PATH"], "TERM": "dumb",
                    "GODMODE_HOME": str(self.home), "GODMODE_ENV": "missing-keys",
                    "GODMODE_CONTEXT": "missing-business"}

    def tearDown(self):
        self.temp.cleanup()

    def command(self, *args, data=None):
        return subprocess.run([sys.executable, str(ROOT / "godmode.py"), "music", *args],
                              env=self.env, input=data, text=True, capture_output=True, timeout=10)

    def build(self, builder, name, *flags):
        script = self.root / name
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / builder), *flags,
                                 "--output", str(script)], text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return script

    def definitions(self, script):
        tree = ast.parse(script.read_text())
        names = {node.name for node in ast.walk(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        assignments = {target.id for node in ast.walk(tree) if isinstance(node, ast.Assign)
                       for target in node.targets if isinstance(target, ast.Name)}
        return tree, names, assignments

    def assert_no_player_or_assets(self, script):
        _, names, assignments = self.definitions(script)
        self.assertFalse(names & {"_MusicSession", "_MusicMPV", "music_session_bridge", "music_main",
                                  "music_setup", "_music_runtime_files", "jingle_main"})
        self.assertFalse(assignments & {"MUSIC_RUNTIME_BUNDLE", "MUSIC_RUNTIME_MANIFEST",
                                        "JINGLE_CATALOG", "JINGLES"})
        source = script.read_text()
        for module in ("godmode_music_player.py", "godmode_music_runtime.py", "godmode_jingle.py"):
            self.assertNotIn("# --- " + module + " ---", source)

    def test_stop_and_status_ignore_broken_selection_and_credentials(self):
        # Synthetic malformed files: only their metadata is inspected afterward.
        for name in ("active.json", "profile.json", ".env.godmode", "ui.json"):
            path = self.home / name
            path.write_text("synthetic invalid data")
            path.chmod(0o600)
        before = {p.name: p.stat() for p in self.home.iterdir()}
        for args in (("stop",), ("stop",), ("status", "--json")):
            result = self.command(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads(result.stdout)
        self.assertEqual(state["state"], "stopped")
        self.assertFalse(state["installed"])
        self.assertEqual({p.name for p in self.home.iterdir()}, set(before))
        for name, info in before.items():
            after = (self.home / name).stat()
            self.assertEqual((after.st_ino, after.st_mtime_ns, after.st_size),
                             (info.st_ino, info.st_mtime_ns, info.st_size))

    def test_music_manager_does_not_construct_key_store_or_resolve_business(self):
        spec = importlib.util.spec_from_file_location("music_test_cli", ROOT / "godmode.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with patch.dict(os.environ, self.env, clear=True), \
                patch.object(sys, "argv", ["godmode", "music", "stop"]), \
                patch.object(cli, "Store", side_effect=AssertionError("opened keys")), \
                patch.object(cli, "business_profile", side_effect=AssertionError("opened business")), \
                patch.object(cli, "selection_resolve", side_effect=AssertionError("resolved selection")), \
                patch("builtins.print"):
            self.assertEqual(cli.main(), 0)

    def test_core_manager_has_own_read_only_protocol(self):
        (self.home / "active.json").write_text("invalid selection")
        before = set(self.home.iterdir())
        result = self.command("__manager", data='{"action":"state"}\n{"action":"state"}\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(replies, [{"ok": True, "data": {"installed": False}}] * 2)
        self.assertEqual(set(self.home.iterdir()), before)
        self.assertFalse((self.home / "state").exists())
        self.assertFalse((self.home / "packs").exists())
        rejected = self.command("__manager", data='{"action":"play","ids":[]}\n')
        self.assertEqual(rejected.returncode, 0, rejected.stderr)
        self.assertFalse(json.loads(rejected.stdout)["ok"])
        self.assertEqual(set(self.home.iterdir()), before)

    def test_default_core_build_contains_manager_but_no_player_runtime_or_assets(self):
        script = self.build("build.py", "godmode-core")
        self.assert_no_player_or_assets(script)
        _, names, _ = self.definitions(script)
        self.assertIn("music_pack_main", names)
        result = subprocess.run([sys.executable, str(script), "music", "__manager"], env=self.env,
                                input='{"action":"state"}\n', text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"ok": True, "data": {"installed": False}})

    def test_companion_source_contains_music_assets_without_credential_dependencies(self):
        script = self.build("build-music.py", "music-player.py")
        tree, names, assignments = self.definitions(script)
        self.assertTrue({"music_main", "music_session_bridge", "music_setup", "jingle_main"} <= names)
        self.assertTrue({"MUSIC_RUNTIME_BUNDLE", "MUSIC_RUNTIME_MANIFEST"} <= assignments)
        self.assertFalse(names & {"Store", "business_profile", "selection_resolve", "provider_main",
                                  "setup_provider", "profile_main", "run_with_keys"})
        forbidden = ("godmode_store", "godmode_profile", "godmode_selection", "godmode_context",
                     "godmode_environment", "godmode_identity", "godmode_bridge")
        imports = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        imports.update(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
        self.assertFalse(any(name == module or name.startswith(module + ".")
                             for name in imports for module in forbidden))
        self.assertNotIn("PROVIDERS", assignments)
        # Exercise its own protocol with malformed root selection present.
        (self.home / "active.json").write_text("invalid selection")
        before = set(self.home.iterdir())
        result = subprocess.run([sys.executable, str(script), "music", "__bridge"], env=self.env,
                                input='{"action":"library"}\n{"action":"status"}\n{"action":"profile"}\n',
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(replies), 3)
        self.assertTrue(replies[0]["ok"])
        self.assertFalse(replies[0]["data"]["configured"])
        self.assertTrue(replies[1]["ok"])
        self.assertEqual(replies[1]["data"]["state"], "stopped")
        self.assertFalse(replies[2]["ok"])
        self.assertEqual(set(self.home.iterdir()), before)

    def test_without_music_build_omits_even_manager_and_other_commands_work(self):
        script = self.build("build.py", "godmode-minimal", "--without-music")
        self.assert_no_player_or_assets(script)
        _, names, _ = self.definitions(script)
        self.assertNotIn("music_pack_main", names)
        help_result = subprocess.run([sys.executable, str(script), "--help"], env=self.env,
                                     text=True, capture_output=True, timeout=10)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        result = subprocess.run([sys.executable, str(script), "music", "stop"], env=self.env,
                                text=True, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Music is not included", result.stderr)


if __name__ == "__main__":
    unittest.main()
