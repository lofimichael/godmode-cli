"""Append-only agent integration, with synthetic instructions and isolated homes."""
import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tests'))
from pty_support import Screen, Terminal, plain

spec = importlib.util.spec_from_file_location('godmode_agent_tests', REPO / 'godmode.py')
godmode = importlib.util.module_from_spec(spec)
spec.loader.exec_module(godmode)


class AgentAppendTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='godmode-agent-append-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.path = self.root / 'AGENTS.md'
        self.block = godmode.AGENT_START + '\n## Godmode\nRun godmode help.\n' + godmode.AGENT_END + '\n'

    def test_existing_bytes_inode_and_mode_survive_append(self):
        cases = (b'# Rules\nKeep me.\n', b'# Rules\r\nKeep me.\r\n', b'No final newline',
                 b'\xff\xfePrivate bytes\x00', b'', b'Line\r\nother\n')
        for before in cases:
            with self.subTest(before=before):
                self.path.write_bytes(before)
                self.path.chmod(0o640)
                initial = self.path.stat()
                plan = godmode.agent_plan(self.path, self.block)
                self.assertTrue(godmode.add_agent_text(self.path, self.block, plan))
                after = self.path.read_bytes()
                final = self.path.stat()
                self.assertEqual(after, before + plan['addition'])
                self.assertEqual((final.st_dev, final.st_ino, stat.S_IMODE(final.st_mode)),
                                 (initial.st_dev, initial.st_ino, 0o640))
                if before == b'# Rules\r\nKeep me.\r\n':
                    self.assertEqual(after.count(b'\r\n'), after.count(b'\n'))

    def test_new_file_is_created_once(self):
        self.path = self.root / 'rules' / 'godmode.md'
        self.assertTrue(godmode.add_agent_text(self.path, self.block))
        self.assertEqual(self.path.read_text(), self.block)
        info = self.path.stat()
        self.assertFalse(godmode.add_agent_text(self.path, self.block))
        self.assertEqual(self.path.stat().st_mtime_ns, info.st_mtime_ns)

    def test_edited_manual_or_incomplete_godmode_text_is_never_replaced(self):
        for before in (b'Edited\n<!-- godmode:start -->\nMy own rules\n',
                       b'Run godmode help only when I say so.\n',
                       b'Missing start\n<!-- godmode:end -->\n',
                       self.block.encode() + b'Custom instructions after the block\n'):
            with self.subTest(before=before):
                self.path.write_bytes(before)
                self.assertFalse(godmode.add_agent_text(self.path, self.block))
                self.assertEqual(self.path.read_bytes(), before)

    def test_preview_change_is_refused_without_losing_user_edit(self):
        self.path.write_text('# First\n')
        plan = godmode.agent_plan(self.path, self.block)
        self.path.write_text('# Edited after preview\n')
        with self.assertRaisesRegex(ValueError, 'changed'):
            godmode.add_agent_text(self.path, self.block, plan)
        self.assertEqual(self.path.read_text(), '# Edited after preview\n')

    def test_replaced_inode_or_mode_after_preview_is_refused(self):
        self.path.write_text('# First\n')
        plan = godmode.agent_plan(self.path, self.block)
        moved = self.path.with_name('old.md')
        self.path.rename(moved)
        self.path.write_text('# First\n')
        with self.assertRaisesRegex(ValueError, 'changed'):
            godmode.add_agent_text(self.path, self.block, plan)
        plan = godmode.agent_plan(self.path, self.block)
        self.path.chmod(0o600)
        with self.assertRaisesRegex(ValueError, 'changed'):
            godmode.add_agent_text(self.path, self.block, plan)
        self.assertEqual(self.path.read_text(), '# First\n')
        self.assertEqual(moved.read_text(), '# First\n')

    def test_preview_for_missing_file_cannot_overwrite_a_racing_create(self):
        plan = godmode.agent_plan(self.path, self.block)
        self.path.write_bytes(b'Arrived later\n')
        with self.assertRaisesRegex(ValueError, 'changed'):
            godmode.add_agent_text(self.path, self.block, plan)
        self.assertEqual(self.path.read_bytes(), b'Arrived later\n')

    def test_visible_symlink_keeps_its_target_and_link(self):
        real = self.root / 'dotfile.md'
        real.write_bytes(b'Owned dotfile\n')
        self.path.symlink_to(real)
        plan = godmode.agent_plan(self.path, self.block)
        self.assertEqual(plan['real'], real)
        self.assertTrue(godmode.add_agent_text(self.path, self.block, plan))
        self.assertTrue(self.path.is_symlink())
        self.assertEqual(real.read_bytes(), b'Owned dotfile\n' + plan['addition'])

    def test_changed_symlink_target_is_refused(self):
        first, second = self.root / 'first.md', self.root / 'second.md'
        first.write_bytes(b'First\n')
        second.write_bytes(b'Second\n')
        self.path.symlink_to(first)
        plan = godmode.agent_plan(self.path, self.block)
        self.path.unlink()
        self.path.symlink_to(second)
        with self.assertRaisesRegex(ValueError, 'changed'):
            godmode.add_agent_text(self.path, self.block, plan)
        self.assertEqual(first.read_bytes(), b'First\n')
        self.assertEqual(second.read_bytes(), b'Second\n')

    def test_broken_links_hardlinks_and_special_files_are_refused(self):
        self.path.symlink_to(self.root / 'missing.md')
        with self.assertRaisesRegex(ValueError, 'broken symlink'):
            godmode.add_agent_text(self.path, self.block)
        self.path.unlink()
        real = self.root / 'real.md'
        real.write_bytes(b'Hard linked\n')
        os.link(real, self.path)
        with self.assertRaisesRegex(ValueError, 'hard links'):
            godmode.add_agent_text(self.path, self.block)
        self.path.unlink()
        os.mkfifo(self.path)
        with self.assertRaisesRegex(ValueError, 'regular file'):
            godmode.add_agent_text(self.path, self.block)
        self.assertFalse(godmode.has_agent_text(self.path))
        self.assertEqual(real.read_bytes(), b'Hard linked\n')

    def test_last_component_symlink_swap_during_open_is_refused(self):
        self.path.write_bytes(b'Original\n')
        other = self.root / 'other.md'
        other.write_bytes(b'Other\n')
        plan = godmode.agent_plan(self.path, self.block)
        original_open = os.open
        def swap(path, flags, *args, **kwargs):
            if Path(path) == self.path and flags & os.O_APPEND:
                self.path.unlink()
                self.path.symlink_to(other)
            return original_open(path, flags, *args, **kwargs)
        with mock.patch.object(godmode.os, 'open', side_effect=swap), self.assertRaises(OSError):
            godmode.add_agent_text(self.path, self.block, plan)
        self.assertEqual(other.read_bytes(), b'Other\n')

    def test_parent_symlink_is_resolved_in_plan_and_kept(self):
        directory = self.root / 'dotfiles'
        directory.mkdir()
        linked = self.root / 'linked'
        linked.symlink_to(directory, target_is_directory=True)
        self.path = linked / 'AGENTS.md'
        (directory / 'AGENTS.md').write_bytes(b'Parent link\n')
        plan = godmode.agent_plan(self.path, self.block)
        self.assertEqual(plan['real'], directory / 'AGENTS.md')
        self.assertTrue(godmode.add_agent_text(self.path, self.block, plan))
        self.assertTrue(linked.is_symlink())
        self.assertTrue((directory / 'AGENTS.md').read_bytes().startswith(b'Parent link\n'))

    def test_concurrent_previews_cannot_duplicate_the_note(self):
        import concurrent.futures
        import threading
        self.path.write_bytes(b'Existing\n')
        plans = [godmode.agent_plan(self.path, self.block) for _ in range(2)]
        barrier = threading.Barrier(2)
        def append(plan):
            barrier.wait(timeout=5)
            try:
                return godmode.add_agent_text(self.path, self.block, plan)
            except ValueError:
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(append, plans))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(self.path.read_bytes(), b'Existing\n' + plans[0]['addition'])

    def test_files_over_size_limit_are_never_read_or_written(self):
        before = b'x' * ((1 << 20) + 1)
        self.path.write_bytes(before)
        with self.assertRaisesRegex(ValueError, '1 MiB'):
            godmode.add_agent_text(self.path, self.block)
        self.assertEqual(self.path.read_bytes(), before)


class AgentDiffTerminalTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='godmode-agent-diff-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.env = {'HOME': str(self.root), 'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
                    'TERM': 'xterm-256color', 'SHELL': '/bin/sh'}
        (self.root / '.claude').mkdir()
        (self.root / '.codex').mkdir()
        self.existing = self.root / '.codex' / 'AGENTS.md'
        self.existing.write_bytes(b'# My rules\r\nKeep all of them.\r\n')

    def terminal(self, *args, **kwargs):
        terminal = Terminal([sys.executable, str(REPO / 'tests/engine_fixture.py'), str(REPO / 'godmode.py'), *args], self.env, **kwargs)
        self.addCleanup(terminal.close)
        return terminal

    def test_diff_preview_groups_changes_and_appends_only_after_enter(self):
        before = self.existing.read_bytes()
        session = self.terminal('agents')
        session.expect('These files will be created:')
        session.expect('These files will be modified:')
        session.expect('Add to Claude Code and Codex')
        session.expect('+ <!-- godmode:start -->')
        self.assertIn(b'\x1b[32m', session.capture)
        self.assertIn(b'\x1b[31m-0', session.capture)
        self.assertFalse((self.root / '.claude/rules/godmode.md').exists())
        self.assertEqual(self.existing.read_bytes(), before)
        session.send(b'\r')
        session.done()
        self.assertTrue(self.existing.read_bytes().startswith(before))
        self.assertEqual(self.existing.read_bytes().count(b'\r\n'), self.existing.read_bytes().count(b'\n'))

    def test_preview_edit_race_preserves_later_user_content(self):
        session = self.terminal('agents')
        session.expect('Add to Claude Code and Codex')
        self.existing.write_bytes(b'Edited while reviewing\n')
        session.send(b'\r')
        session.expect('changed; open Agents again. Nothing written.')
        session.done()
        self.assertEqual(self.existing.read_bytes(), b'Edited while reviewing\n')

    def test_narrow_preview_cannot_write_unseen_note(self):
        session = self.terminal('agents', cols=40, rows=12)
        session.expect('Enlarge the terminal')
        session.send(b'\r')
        session.settle(.1)
        self.assertFalse((self.root / '.claude/rules/godmode.md').exists())
        session.send(b'\x1b')
        session.done()

    def test_five_new_files_fit_standard_terminal(self):
        self.existing.unlink()
        for folder in ('.gemini', '.copilot', '.config/opencode'):
            (self.root / folder).mkdir(parents=True)
        session = self.terminal('agents', cols=80, rows=24)
        session.expect('Add to 5 agents')
        screen = '\n'.join(Screen(80).feed(session.capture).lines())
        for text in ('These files will be created:', '~/.claude/rules/godmode.md', '~/.codex/AGENTS.md',
                     '~/.gemini/GEMINI.md', '~/.copilot/copilot-instructions.md',
                     '~/.config/opencode/AGENTS.md', '+ <!-- godmode:start -->', '+ <!-- godmode:end -->'):
            self.assertIn(text, screen)
        session.send(b'\x1b')
        session.done()


if __name__ == '__main__':
    unittest.main()
