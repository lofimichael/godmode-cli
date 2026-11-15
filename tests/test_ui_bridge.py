"""The native UI uses private pipes and the same file writers as direct commands."""
import importlib.util
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bridge_test_cli', ROOT / 'godmode.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
from godmode_bridge import UIBridge


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / '.godmode'
        self.env = patch.dict(os.environ, HOME=str(self.root), GODMODE_HOME=str(self.home),
                              CODEX_HOME=str(self.root / '.codex'), COPILOT_HOME=str(self.root / '.copilot'))
        self.env.start()
        self.bridge = UIBridge(vars(cli), self.home)

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def call(self, action, **fields):
        return self.bridge.call(dict(action=action, **fields))

    def test_state_is_read_only_and_never_unseals(self):
        self.call('state')
        self.assertFalse(self.home.exists())
        self.bridge.store.set('DEMO_KEY', 'synthetic_EXISTING_SECRET_123456')
        with patch.object(self.bridge.store, '_key', side_effect=AssertionError('unseal')):
            state = self.call('state')
        self.assertNotIn('EXISTING_SECRET', json.dumps(state))
        self.assertEqual(state['states']['DEMO_KEY'], 'set')

    def test_key_requires_preview_and_old_plan_cannot_replay(self):
        plan = self.call('key_plan', name='DEMO_KEY')
        value = 'synthetic_NEW_SECRET_123456'
        with self.assertRaisesRegex(ValueError, 'Review'):
            self.call('key_save', id=plan['id'], value=value)
        checked = self.call('key_check', id=plan['id'], value=value, pasted=True)
        self.assertTrue(checked['valid'])
        self.assertNotIn('NEW_SECRET', json.dumps(checked))
        result = self.call('key_save', id=plan['id'], value=value, pasted=True)
        self.assertNotIn('NEW_SECRET', json.dumps(result))
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.call('key_save', id=plan['id'], value=value)

    def test_edited_paste_stays_masked_in_public_fields(self):
        plan = self.call('key_plan', name='GMAIL_USER')
        value = 'synthetic_PRIVATE_PASTED_VALUE@example.test'
        checked = self.call('key_check', id=plan['id'], value=value, pasted=False, from_paste=True)
        self.assertTrue(checked['valid'])
        self.assertNotIn('PRIVATE_PASTED', json.dumps(checked))
        saved = self.call('key_save', id=plan['id'], value=value, pasted=False, from_paste=True)
        self.assertNotIn('PRIVATE_PASTED', json.dumps(saved))

    def test_key_changed_after_preview_is_preserved(self):
        self.bridge.store.set('DEMO_KEY', 'synthetic_original')
        plan = self.call('key_plan', name='DEMO_KEY')
        self.call('key_check', id=plan['id'], value='synthetic_pending')
        self.bridge.store.set('OTHER_KEY', 'synthetic_concurrent')
        before = self.bridge.store.env_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'changed after the preview'):
            self.call('key_save', id=plan['id'], value='synthetic_pending')
        self.assertEqual(self.bridge.store.env_path.read_bytes(), before)

    def test_profile_uses_displayed_snapshot(self):
        self.call('state')
        cli.Profile(self.home).write({'business_name': 'Concurrent synthetic edit'})
        before = (self.home / 'profile.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'changed before saving'):
            self.call('profile_save', field='business_name', value='Pending synthetic edit')
        self.assertEqual((self.home / 'profile.json').read_bytes(), before)

    def test_agents_append_only_the_reviewed_note(self):
        target = self.root / '.codex' / 'AGENTS.md'
        target.parent.mkdir()
        original = b'# Existing synthetic rules\r\nKeep all text.'
        target.write_bytes(original)
        plan = self.call('agents_plan')
        self.assertNotIn('Existing synthetic rules', json.dumps(plan))
        self.assertEqual(plan['removed_lines'], 0)
        self.call('agents_apply', id=plan['id'])
        self.assertTrue(target.read_bytes().startswith(original))
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.call('agents_apply', id=plan['id'])

    def test_locked_agent_file_fails_without_hanging_or_writing(self):
        target = self.root / '.codex' / 'AGENTS.md'
        target.parent.mkdir()
        target.write_text('# Synthetic locked rules\n')
        plan = self.call('agents_plan')
        with target.open('rb') as held:
            fcntl.flock(held.fileno(), fcntl.LOCK_EX)
            with self.assertRaisesRegex(ValueError, 'Another editor'):
                self.call('agents_apply', id=plan['id'])
        self.assertEqual(target.read_text(), '# Synthetic locked rules\n')

    def test_protocol_never_echoes_bad_requests(self):
        env = dict(os.environ)
        request = b'{"action":"synthetic_SECRET_BAD_JSON"\n'
        process = subprocess.run([sys.executable, str(ROOT / 'tests/engine_fixture.py'), str(ROOT / 'godmode.py'), '__ui'],
                                 input=request, capture_output=True, env=env)
        self.assertEqual(process.returncode, 0)
        self.assertNotIn(b'SECRET', process.stdout + process.stderr)
        self.assertFalse(json.loads(process.stdout)['ok'])


if __name__ == '__main__':
    unittest.main()
