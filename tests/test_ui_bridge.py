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
from godmode_bridge import UIBridge, record_recent_selection, ui_preferences


class BridgeTests(unittest.TestCase):
    def setUp(self):
        cli.ACTIVE_CONTEXT = None
        cli.ACTIVE_ENVIRONMENT = 'default'
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / '.godmode'
        self.env = patch.dict(os.environ, HOME=str(self.root), GODMODE_HOME=str(self.home),
                              CODEX_HOME=str(self.root / '.codex'), COPILOT_HOME=str(self.root / '.copilot'))
        self.env.start()
        self.bridge = UIBridge(vars(cli), self.home)

    def tearDown(self):
        cli.ACTIVE_CONTEXT = None
        cli.ACTIVE_ENVIRONMENT = 'default'
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

    def test_agent_selection_changes_only_reviewed_selected_target(self):
        selected = self.root / '.codex' / 'AGENTS.md'
        unselected = self.root / '.gemini' / 'GEMINI.md'
        for path in (selected, unselected):
            path.parent.mkdir()
            path.write_bytes(b'# Existing synthetic rules\r\nKeep these bytes.')
            path.chmod(0o640)
        # This detected agent would get a new nested file if all were applied.
        (self.root / '.claude').mkdir()
        plan = self.call('agents_plan')
        display = next(row['path'] for row in plan['targets'] if row['name'] == 'Codex')
        before = unselected.read_bytes(), unselected.stat()
        result = self.call('agents_apply', id=plan['id'], targets=[display])
        self.assertEqual(result['added'], [display])
        self.assertTrue(selected.read_bytes().startswith(before[0]))
        self.assertIn(b'godmode help', selected.read_bytes())
        self.assertEqual(unselected.read_bytes(), before[0])
        after = unselected.stat()
        for field in ('st_mode', 'st_uid', 'st_gid', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'):
            self.assertEqual(getattr(after, field), getattr(before[1], field), field)
        self.assertFalse((self.root / '.claude' / 'rules').exists())
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.call('agents_apply', id=plan['id'], targets=[display])

    def test_invalid_agent_selections_do_not_write_or_expire_preview(self):
        target = self.root / '.codex' / 'AGENTS.md'
        target.parent.mkdir()
        target.write_text('# Synthetic original\n')
        plan = self.call('agents_plan')
        display = plan['targets'][0]['path']
        original = target.read_bytes()
        invalid = ([], None, display, [display, display], [None], [False],
                   ['~/not-a-reviewed-target'], [display, '~/not-a-reviewed-target'],
                   [str(target)], [{'path': display}])
        with patch.dict(vars(cli), add_agent_text=unittest.mock.Mock(wraps=cli.add_agent_text)):
            for targets in invalid:
                with self.subTest(targets=targets):
                    with self.assertRaisesRegex(ValueError, 'reviewed agent preview'):
                        self.call('agents_apply', id=plan['id'], targets=targets)
                    self.assertIn(plan['id'], self.bridge.agents)
                    self.assertEqual(target.read_bytes(), original)
            cli.add_agent_text.assert_not_called()
        self.assertEqual(self.call('agents_apply', id=plan['id'], targets=[display])['added'], [display])

    def test_agent_selection_cannot_include_already_added_target(self):
        target = self.root / '.codex' / 'AGENTS.md'
        target.parent.mkdir()
        target.write_text('# Synthetic existing\ngodmode help\n')
        plan = self.call('agents_plan')
        self.assertTrue(plan['targets'][0]['added'])
        with self.assertRaisesRegex(ValueError, 'reviewed agent preview'):
            self.call('agents_apply', id=plan['id'], targets=[plan['targets'][0]['path']])
        self.assertIn(plan['id'], self.bridge.agents)
        self.assertEqual(target.read_text(), '# Synthetic existing\ngodmode help\n')

    def test_omitted_agent_targets_still_applies_all_pending_targets(self):
        for directory in ('.codex', '.gemini'):
            (self.root / directory).mkdir()
        plan = self.call('agents_plan')
        expected = [row['path'] for row in plan['targets']]
        self.assertEqual(self.call('agents_apply', id=plan['id'])['added'], expected)
        self.assertIn('godmode help', (self.root / '.codex' / 'AGENTS.md').read_text())
        self.assertIn('godmode help', (self.root / '.gemini' / 'GEMINI.md').read_text())

    def test_protocol_never_echoes_bad_requests(self):
        env = dict(os.environ)
        request = b'{"action":"synthetic_SECRET_BAD_JSON"\n'
        process = subprocess.run([sys.executable, str(ROOT / 'tests/engine_fixture.py'), str(ROOT / 'godmode.py'), '__ui'],
                                 input=request, capture_output=True, env=env)
        self.assertEqual(process.returncode, 0)
        self.assertNotIn(b'SECRET', process.stdout + process.stderr)
        self.assertFalse(json.loads(process.stdout)['ok'])

    def test_environment_switch_scopes_keys_profile_and_invalidates_previews(self):
        self.bridge.store.set('DEMO_KEY', 'synthetic-original')
        self.call('state')
        self.call('profile_save', field='business_name', value='Original business')
        plan = self.call('key_plan', name='DEMO_KEY')
        self.call('key_check', id=plan['id'], value='synthetic-new')
        state = self.call('environment_create', name='client-test', copy='default')
        self.assertEqual(state['environment'], 'client-test')
        self.assertEqual(state['profile'], {})
        self.assertEqual(state['states']['DEMO_KEY'], 'set')
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.call('key_save', id=plan['id'], value='synthetic-new')
        self.assertEqual(self.call('environment_list')['environments'][1]['keys'], 1)
        self.call('profile_save', field='business_name', value='Client business')
        state = self.call('environment_select', name='default')
        self.assertEqual(state['profile']['business_name'], 'Original business')
        with self.assertRaisesRegex(ValueError, 'not saved'):
            self.call('environment_select', name='not-here')
        self.assertEqual(self.call('state')['environment'], 'default')

    def test_business_reused_across_environments_and_mapped_write_preview_is_exact(self):
        self.call('environment_create', name='client-test')
        self.call('context_create', name='client')
        self.call('profile_save', field='business_name', value='Client Inc')
        cli.ACTIVE_CONTEXT.map('STRIPE_SECRET_KEY', 'CLIENT_STRIPE_KEY')
        self.call('context_select', name='client')
        plan = self.call('key_plan', name='STRIPE_SECRET_KEY')
        check = self.call('key_check', id=plan['id'], value='sk_test_synthetic', pasted=True)
        self.assertTrue(check['assignment'].startswith('CLIENT_STRIPE_KEY='))
        self.call('key_save', id=plan['id'], value='sk_test_synthetic', pasted=True)
        self.assertEqual(cli.Store(self.home, environment='client-test').names(), ['CLIENT_STRIPE_KEY'])
        self.call('environment_create', name='client-live')
        state = self.call('state')
        self.assertEqual(state['profile']['business_name'], 'Client Inc')
        self.assertNotEqual(state['states'].get('STRIPE_SECRET_KEY'), 'set')
        self.assertEqual(self.call('context_list')['contexts'][0]['name'], '')

    def test_profile_picker_previews_the_draft_environment_without_switching(self):
        self.call('environment_create', name='preview', select=False)
        automatic = self.call('context_list', environment='preview')['contexts'][0]
        self.assertEqual(automatic['profile_path'], str(self.home / 'environments/preview/profile.json'))
        self.assertEqual(self.call('state')['environment'], 'default')
        with self.assertRaises(ValueError):
            self.call('context_list', environment='../invalid')

    def test_agent_copy_is_scoped_but_global_append_stays_generic(self):
        target = self.root / '.codex' / 'AGENTS.md'
        target.parent.mkdir()
        self.call('environment_create', name='acme-live')
        self.call('context_create', name='acme')
        plan = self.call('agents_plan')
        self.assertIn('--env acme-live', plan['copy_block'])
        self.assertIn('--context acme', plan['copy_block'])
        self.assertNotIn('--env acme-live', plan['block'])
        self.call('agents_apply', id=plan['id'])
        self.assertNotIn('--env acme-live', target.read_text())
        installed = self.call('agents_plan')
        self.assertTrue(installed['targets'][0]['added'])
        self.assertEqual(installed['copy_block'], plan['copy_block'])
        with patch.dict(vars(cli), clipboard=lambda: ['/synthetic/clipboard']), \
                patch('godmode_bridge.subprocess.run') as copier:
            self.call('copy_agent', id=installed['id'])
            self.assertEqual(copier.call_args.kwargs['input'].decode(), plan['copy_block'])

    def test_staged_creates_leave_active_pair_and_previews_unchanged(self):
        self.bridge.store.set('DEMO_KEY', 'synthetic-original')
        self.call('selection_save', environment='default', context='')
        before = (self.home / 'active.json').read_bytes()
        plan = self.call('key_plan', name='DEMO_KEY')
        self.call('key_check', id=plan['id'], value='synthetic-replacement')
        agents = self.call('agents_plan')
        for action, name in [('environment_create', 'north'), ('context_create', 'north-business')]:
            state = self.call(action, name=name, select=False)
            self.assertEqual((state['environment'], state['context']), ('default', ''))
            self.assertEqual((self.home / 'active.json').read_bytes(), before)
        self.assertTrue(cli.Store(self.home, environment='north').exists())
        self.assertEqual(cli.Context(self.home, 'north-business').name, 'north-business')
        self.assertIn(agents['id'], self.bridge.agents)
        self.call('key_save', id=plan['id'], value='synthetic-replacement')
        self.assertEqual(cli.Store(self.home, environment='north').names(), [])

    def test_selection_save_commits_full_pair_and_expires_scoped_previews(self):
        self.call('environment_create', name='north', select=False)
        self.call('context_create', name='north-business', select=False)
        cli.Context(self.home, 'north-business').profile().write({'business_name': 'North Inc'})
        cli.Store(self.home, environment='north').set('NORTH_KEY', 'synthetic-north')
        key = self.call('key_plan', name='DEMO_KEY')
        self.call('key_check', id=key['id'], value='synthetic-pending')
        agents = self.call('agents_plan')
        with patch.object(cli, 'set_active_selection', wraps=cli.set_active_selection):
            state = self.call('selection_save', environment='north', context='north-business')
            cli.set_active_selection.assert_called_once_with(self.home, 'north', 'north-business')
        self.assertEqual((state['environment'], state['context']), ('north', 'north-business'))
        self.assertEqual(state['profile']['business_name'], 'North Inc')
        self.assertEqual(state['states'], {'NORTH_KEY': 'set'})
        self.assertEqual(json.loads((self.home / 'active.json').read_text()),
                         {'schema': 1, 'environment': 'north', 'context': 'north-business'})
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.call('key_save', id=key['id'], value='synthetic-pending')
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.call('agents_apply', id=agents['id'])
        state = self.call('selection_save', environment='north', context='-')
        self.assertEqual(state['context'], '')

    def test_invalid_staged_pair_does_not_save_a_partial_selection(self):
        self.call('selection_save', environment='default', context='')
        self.call('environment_create', name='north', select=False)
        before = (self.home / 'active.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'not saved'):
            self.call('selection_save', environment='north', context='missing-business')
        self.assertEqual((self.home / 'active.json').read_bytes(), before)
        state = self.call('state')
        self.assertEqual((state['environment'], state['context']), ('default', ''))
        with self.assertRaisesRegex(ValueError, 'true or false'):
            self.call('environment_create', name='bad', select='false')
        self.assertFalse(cli.Store(self.home, environment='bad').exists())

    def test_preferences_default_is_read_only_and_save_is_private_and_persistent(self):
        self.assertEqual(self.call('state')['preferences'], {'motion': True})
        self.assertFalse(self.home.exists())
        state = self.call('preferences_save', motion=False)
        self.assertEqual(state['preferences'], {'motion': False})
        self.assertEqual((self.home / 'ui.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.home.stat().st_mode & 0o777, 0o700)
        fresh = UIBridge(vars(cli), self.home)
        self.assertEqual(fresh.call({'action': 'state'})['preferences'], {'motion': False})
        self.assertFalse(self.bridge.store.exists())
        self.assertFalse(self.bridge.profile.path.exists())

    def test_preferences_reject_invalid_values_without_writes(self):
        for value in (None, 'false', 0, 1, []):
            with self.assertRaisesRegex(ValueError, 'true or false'):
                self.call('preferences_save', motion=value)
        self.assertFalse(self.home.exists())

    def test_bad_preferences_do_not_block_state_or_get_silently_overwritten(self):
        self.home.mkdir(mode=0o700)
        path = self.home / 'ui.json'
        for raw in ('not json', '{"motion":"no"}', '{"motion":false,"motion":true}'):
            path.write_text(raw)
            path.chmod(0o600)
            state = self.call('state')
            self.assertEqual(state['preferences'], {'motion': True})
            self.assertIn('ui.json', state['preferences_error'])
            self.assertIn('providers', state)
            with self.assertRaisesRegex(ValueError, 'ui.json'):
                self.call('preferences_save', motion=False)
            self.assertEqual(path.read_text(), raw)

    def test_preferences_preserve_unknown_fields_and_refuse_unsafe_files(self):
        self.call('preferences_save', motion=False)
        path = self.home / 'ui.json'
        path.write_text('{"motion":false,"future_setting":"preserved"}')
        self.call('preferences_save', motion=True)
        self.assertEqual(json.loads(path.read_text()), {'motion': True, 'future_setting': 'preserved'})
        path.chmod(0o644)
        self.assertIn('mode 0600', self.call('state')['preferences_error'])
        with self.assertRaisesRegex(ValueError, 'mode 0600'):
            self.call('preferences_save', motion=False)
        path.unlink()
        outside = self.root / 'outside.json'
        outside.write_text('{"motion":false}')
        outside.chmod(0o600)
        path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'ui.json'):
            self.call('preferences_save', motion=True)
        self.assertEqual(outside.read_text(), '{"motion":false}')

    def test_recent_setups_record_atomic_pair_then_previous_and_keep_five_mru(self):
        self.call('context_create', name='business', select=False)
        for name in ('one', 'two', 'three', 'four', 'five', 'six'):
            self.call('environment_create', name=name, select=False)
        self.assertEqual(self.call('state')['recent_setups'], [])
        for name in ('one', 'two', 'three', 'four', 'five', 'six'):
            with patch.object(cli, 'set_active_selection', wraps=cli.set_active_selection):
                state = self.call('selection_save', environment=name, context='business')
                cli.set_active_selection.assert_called_once_with(self.home, name, 'business')
            self.assertEqual(json.loads((self.home / 'active.json').read_text()),
                             {'schema': 1, 'environment': name, 'context': 'business'})
        expected = [{'environment': name, 'context': 'business'}
                    for name in ('six', 'five', 'four', 'three', 'two')]
        self.assertEqual(state['recent_setups'], expected)
        state = self.call('selection_save', environment='four', context='business')
        expected = [expected[2], expected[0], expected[1], expected[3], expected[4]]
        self.assertEqual(state['recent_setups'], expected)
        self.assertEqual(self.call('selection_save', environment='four', context='business')['recent_setups'], expected)
        self.assertEqual(json.loads((self.home / 'ui.json').read_text())['recent_setups'], expected)

    def test_failed_or_unapplied_choices_never_change_recent_setups(self):
        self.call('selection_save', environment='default', context='')
        path = self.home / 'ui.json'
        original, modified = path.read_bytes(), path.stat().st_mtime_ns
        self.call('environment_create', name='pending', select=False)
        self.call('context_create', name='pending-business', select=False)
        # Reading/visiting chooser data and abandoning it does not apply a pair.
        for action in ('state', 'environment_list', 'context_list'):
            self.call(action)
        with self.assertRaisesRegex(ValueError, 'not saved'):
            self.call('selection_save', environment='pending', context='missing-business')
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(path.stat().st_mtime_ns, modified)
        self.assertEqual(json.loads((self.home / 'active.json').read_text()),
                         {'schema': 1, 'environment': 'default', 'context': ''})

    def test_legacy_select_operations_record_applied_pairs(self):
        self.call('environment_create', name='other', select=False)
        self.call('context_create', name='business', select=False)
        state = self.call('environment_select', name='other')
        self.assertEqual(state['recent_setups'], [{'environment': 'other', 'context': ''},
                                                {'environment': 'default', 'context': ''}])
        state = self.call('context_select', name='business')
        self.assertEqual(state['recent_setups'][:2], [{'environment': 'other', 'context': 'business'},
                                                    {'environment': 'other', 'context': ''}])

    def test_history_schema_errors_do_not_hide_motion_or_fail_applied_selection(self):
        self.call('environment_create', name='other', select=False)
        path = self.home / 'ui.json'
        pair = {'environment': 'default', 'context': ''}
        invalid = (None, {}, [None], [dict(pair, path='/tmp/not-a-name')],
                   [{'environment': '../path', 'context': ''}],
                   [{'environment': 'default', 'context': '-'}],
                   [{'environment': 'default', 'context': False}],
                   [{'environment': 'x' * 97, 'context': ''}],
                   [pair, pair], [pair] * 6)
        for history in invalid:
            with self.subTest(history=history):
                raw = json.dumps({'motion': False, 'recent_setups': history})
                path.write_text(raw)
                path.chmod(0o600)
                state = self.call('state')
                self.assertEqual(state['preferences'], {'motion': False})
                self.assertEqual(state['recent_setups'], [])
                self.assertIn('ui.json', state['history_error'])
                state = self.call('selection_save', environment='other', context='')
                self.assertEqual((state['environment'], state['context']), ('other', ''))
                self.assertIn('Active loadout saved', state['history_error'])
                self.assertEqual(json.loads((self.home / 'active.json').read_text())['environment'], 'other')
                self.assertEqual(path.read_text(), raw)
                with self.assertRaisesRegex(ValueError, 'ui.json'):
                    self.call('preferences_save', motion=True)
                self.assertEqual(path.read_text(), raw)

    def test_history_write_failure_preserves_ui_file_and_successful_selection(self):
        self.call('selection_save', environment='default', context='')
        self.call('environment_create', name='other', select=False)
        path = self.home / 'ui.json'
        original = path.read_bytes()
        write = cli.Profile.write
        def fail_ui_only(config, data):
            if config.path.name == 'ui.json':
                raise ValueError('Synthetic history write failure.')
            return write(config, data)
        with patch.object(cli.Profile, 'write', fail_ui_only):
            state = self.call('selection_save', environment='other', context='')
        self.assertEqual(state['environment'], 'other')
        self.assertIn('Active loadout saved', state['history_error'])
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(json.loads((self.home / 'active.json').read_text())['environment'], 'other')

    def test_unsafe_history_file_is_preserved_after_active_pair_saved(self):
        self.call('environment_create', name='other', select=False)
        path = self.home / 'ui.json'
        path.write_text('{"motion":false}')
        path.chmod(0o644)
        state = self.call('selection_save', environment='other', context='')
        self.assertEqual(state['environment'], 'other')
        self.assertIn('mode 0600', state['history_error'])
        self.assertEqual(path.read_text(), '{"motion":false}')
        self.assertEqual(path.stat().st_mode & 0o777, 0o644)
        path.unlink()
        outside = self.root / 'outside-ui.json'
        outside.write_text('{"motion":true}')
        outside.chmod(0o600)
        path.symlink_to(outside)
        state = self.call('selection_save', environment='default', context='')
        self.assertEqual(state['environment'], 'default')
        self.assertIn('Active loadout saved', state['history_error'])
        self.assertTrue(path.is_symlink())
        self.assertEqual(outside.read_text(), '{"motion":true}')

    def test_recent_helper_preserves_preferences_and_never_opens_keys(self):
        self.call('preferences_save', motion=False)
        path = self.home / 'ui.json'
        path.write_text('{"motion":false,"future_setting":{"keep":"this"}}')
        selected = {'environment': 'applied', 'context': 'business'}
        previous = {'environment': 'default', 'context': ''}
        with patch.dict(vars(cli), Store=unittest.mock.Mock(side_effect=AssertionError('opened keys')),
                        effective_store=unittest.mock.Mock(side_effect=AssertionError('opened keys')),
                        business_profile=unittest.mock.Mock(side_effect=AssertionError('opened business'))):
            history = record_recent_selection(vars(cli), self.home, selected, previous)
            self.assertEqual(history, [selected, previous])
            self.assertEqual(ui_preferences(vars(cli), self.home), {'motion': False, 'path': str(path)})
            self.assertEqual(ui_preferences(vars(cli), self.home, motion=True), {'motion': True, 'path': str(path)})
        self.assertEqual(json.loads(path.read_text()),
                         {'motion': True, 'recent_setups': history, 'future_setting': {'keep': 'this'}})
        self.assertEqual({p.name for p in self.home.iterdir()}, {'ui.json'})

    def test_recording_applied_selection_does_not_unseal_or_modify_key_files(self):
        self.bridge.store.set('DEMO_KEY', 'synthetic_default_secret')
        self.call('environment_create', name='other', select=False)
        cli.Store(self.home, environment='other').set('DEMO_KEY', 'synthetic_other_secret')
        paths = [self.home / name for name in ('.env.godmode', '.env.godmode.other', 'seal.key')]
        before = {path: path.stat() for path in paths}
        with patch.object(cli.Store, '_key', side_effect=AssertionError('unsealed a key')):
            state = self.call('selection_save', environment='other', context='')
        self.assertNotIn('synthetic_', json.dumps(state))
        self.assertEqual(state['recent_setups'], [{'environment': 'other', 'context': ''},
                                                {'environment': 'default', 'context': ''}])
        for path in paths:
            after = path.stat()
            for field in ('st_mode', 'st_uid', 'st_gid', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'):
                self.assertEqual(getattr(after, field), getattr(before[path], field), (path.name, field))


if __name__ == '__main__':
    unittest.main()
