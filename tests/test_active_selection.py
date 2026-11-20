"""Saved convenience and pinned automation, using synthetic isolated homes only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from godmode_store import Store


class ActiveSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='godmode-active-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / '.godmode'
        self.env = {'HOME': str(self.root), 'PATH': os.environ['PATH'], 'TERM': 'dumb'}
        self.entry = [sys.executable, str(ROOT / 'godmode.py')]

    def command(self, *args, input=None, expected=0, overrides=None, explicit_home=True):
        env = dict(self.env)
        env.update(overrides or {})
        result = subprocess.run(self.entry + (['--home', str(self.home)] if explicit_home else []) + list(args),
                                input=input, text=True, capture_output=True, env=env, timeout=10)
        self.assertEqual(result.returncode, expected, result.stderr)
        return result

    def active(self, *args, overrides=None, explicit_home=True):
        return json.loads(self.command(*args, 'active', '--json', overrides=overrides,
                                       explicit_home=explicit_home).stdout)

    def fixtures(self):
        self.command('set', 'TOKEN', '--stdin', input='synthetic-default')
        self.command('profile', 'set', 'business_name', '--stdin', input='Default business')
        for name in ('test', 'live'):
            self.command('env', 'create', name)
            self.command('--env', name, 'set', 'TOKEN', '--stdin', input='synthetic-' + name)
            self.command('--env', name, 'profile', 'set', 'business_name', '--stdin', input=name + ' business')
        self.command('context', 'create', 'acme')
        self.command('--context', 'acme', 'profile', 'set', 'business_name', '--stdin', input='Acme')

    def test_empty_install_is_read_only_and_explicit_defaults_are_available(self):
        data = self.active()
        self.assertEqual((data['environment'], data['context']), ('default', ''))
        self.assertEqual(data['sources'], {'environment': 'default', 'context': 'default'})
        self.assertIn('--env default --context -', data['command'])
        self.assertFalse(self.home.exists())
        self.assertEqual(self.command('active', '--command').stdout.strip(), data['command'])

    def test_saved_pair_routes_all_reads_and_writes_without_copying_files(self):
        self.fixtures()
        protected = {p: (p.read_bytes(), p.stat().st_ino, p.stat().st_mtime_ns)
                     for p in self.home.rglob('*') if p.is_file()}
        self.command('use', '--env', 'test', '--context', 'acme')
        self.assertEqual(self.command('profile', 'get', 'business_name').stdout.strip(), 'Acme')
        self.assertTrue(self.command('path').stdout.strip().endswith('.env.godmode.test'))
        self.command('run', 'TOKEN', '--', sys.executable, '-c',
                     'import os; assert os.environ["TOKEN"] == "synthetic-test"')
        for path, snapshot in protected.items():
            self.assertEqual((path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns), snapshot)
        data = json.loads((self.home / 'active.json').read_text())
        self.assertEqual(data, {'schema': 1, 'environment': 'test', 'context': 'acme'})
        self.assertEqual((self.home / 'active.json').stat().st_mode & 0o777, 0o600)
        self.assertNotIn('synthetic-', json.dumps(data))
        self.command('set', 'NEW_TOKEN', '--stdin', input='synthetic-new')
        self.assertNotIn('NEW_TOKEN', Store(self.home).names())
        self.assertIn('NEW_TOKEN', Store(self.home, environment='test').names())

    def test_flags_shell_saved_precedence_is_per_axis(self):
        self.fixtures()
        self.command('use', 'test', '--context', 'acme')
        data = self.active(overrides={'GODMODE_ENV': 'live'})
        self.assertEqual((data['environment'], data['context']), ('live', 'acme'))
        self.assertEqual(data['sources'], {'environment': 'shell', 'context': 'saved'})
        data = self.active('--env', 'default', '--context', '-',
                           overrides={'GODMODE_ENV': 'live', 'GODMODE_CONTEXT': 'acme'})
        self.assertEqual((data['environment'], data['context']), ('default', ''))
        self.assertEqual(data['selection_source'], 'command')
        self.assertEqual(self.active()['environment'], 'test')

    def test_default_named_business_is_not_reinterpreted(self):
        self.command('context', 'create', 'default')
        self.command('--context', 'default', 'profile', 'set', 'business_name', '--stdin', input='Named default')
        self.command('use', '--env', 'default', '--context', 'default')
        self.assertEqual(self.command('profile', 'get', 'business_name').stdout.strip(), 'Named default')
        self.command('use', '--context', '-')
        self.assertEqual(self.active()['context'], '')
        self.assertEqual(json.loads(self.command('profile', 'show').stdout), {})

    def test_copy_note_pins_both_default_axes(self):
        note = self.command('agents', '--print').stdout
        self.assertIn('--env default --context -', note)
        self.assertIn('--home ' + str(self.home), note)

    def test_missing_saved_selection_fails_closed_but_can_be_repaired(self):
        self.fixtures()
        self.command('use', 'test', '--context', 'acme')
        Store(self.home, environment='test').env_path.unlink()
        self.command('list', expected=2)
        self.command('profile', 'get', 'business_name', expected=2)
        self.command('set', 'TOKEN', '--stdin', input='synthetic-should-not-write', expected=2)
        self.command('env', 'list')
        self.command('use', '--env', 'default', '--context', '-')
        self.assertEqual(self.active()['environment'], 'default')
        self.command('use', '--context', 'acme')
        (self.home / 'contexts/acme/context.json').unlink()
        self.command('list', expected=2)
        self.command('profile', 'show', expected=2)
        self.command('use', '--context', '-')
        self.assertEqual(self.active()['context'], '')

    def test_invalid_choice_preserves_active_file(self):
        self.fixtures()
        self.command('use', 'test', '--context', 'acme')
        before = (self.home / 'active.json').read_bytes()
        self.command('use', 'missing', expected=2)
        self.command('use', '--context', 'missing', expected=2)
        self.command('use', 'test', '--env', 'live', expected=2)
        self.command('use', expected=2)
        self.command('--context=', 'active', expected=2)
        self.command('active', overrides={'GODMODE_ENV': ''}, expected=2)
        self.assertEqual((self.home / 'active.json').read_bytes(), before)

    def test_malformed_or_unsafe_active_file_never_changes_the_target(self):
        self.home.mkdir(mode=0o700)
        active = self.home / 'active.json'
        active.write_text('{broken')
        active.chmod(0o600)
        self.command('active', expected=2)
        self.assertEqual(self.active('--env', 'default', '--context', '-')['environment'], 'default')
        self.command('use', '--env', 'default', '--context', '-', expected=2)
        self.assertEqual(active.read_text(), '{broken')
        active.unlink()
        target = self.root / 'target'
        target.write_text('preserve')
        active.symlink_to(target)
        self.command('active', expected=2)
        self.command('use', '--env', 'default', '--context', '-', expected=2)
        self.assertEqual(target.read_text(), 'preserve')

    def test_semantically_invalid_selection_can_be_replaced_by_explicit_pair(self):
        self.home.mkdir(mode=0o700)
        active = self.home / 'active.json'
        active.write_text('{"schema": 100, "environment": "default", "context": ""}')
        active.chmod(0o600)
        self.command('active', expected=2)
        active.write_text('{}')
        self.command('active', expected=2)
        self.command('use', '--env', 'default', '--context', '-')
        self.assertEqual(self.active()['selection_source'], 'saved')

    def test_nested_run_keeps_scope_after_another_selection_write(self):
        self.fixtures()
        for environment, context in (('test', 'acme'), ('default', '-')):
            self.command('use', environment, '--context', context)
            child = '''import json, os, subprocess
entry = %r
assert os.environ['GODMODE_ENV'] == %r
assert os.environ['GODMODE_CONTEXT'] == %r
assert os.environ['GODMODE_HOME'] == %r
subprocess.run(entry + ['use', '--env', 'live', '--context', '-'], check=True, stdout=subprocess.DEVNULL)
result = subprocess.run(entry + ['active', '--json'], check=True, capture_output=True, text=True)
scope = json.loads(result.stdout)
assert (scope['environment'], scope['context']) == (%r, %r)
''' % (self.entry, environment, context, str(self.home), environment, '' if context == '-' else context)
            self.command('run', 'TOKEN', '--', sys.executable, '-c', child)
            self.assertEqual((self.active()['environment'], self.active()['context']), ('live', ''))
        self.command('run', 'GODMODE_ENV=TOKEN', '--', sys.executable, '-c', 'raise AssertionError()', expected=2)

    def test_child_pins_a_shell_selected_home_as_an_absolute_path(self):
        self.fixtures()
        child = 'import os; assert os.environ["GODMODE_HOME"] == ' + repr(str(self.home))
        self.command('run', 'TOKEN', '--', sys.executable, '-c', child, explicit_home=False,
                     overrides={'GODMODE_HOME': os.path.relpath(self.home)})

    def test_use_warns_about_existing_shell_pins(self):
        self.fixtures()
        result = self.command('use', 'test', '--context', 'acme', overrides={'GODMODE_ENV': 'live'})
        self.assertIn('shell has selection overrides', result.stdout)
        self.assertEqual(self.active(overrides={'GODMODE_ENV': 'live'})['environment'], 'live')
        self.assertEqual(self.active()['environment'], 'test')

    def test_bridge_sessions_keep_their_snapshot_and_invalidate_previews(self):
        self.fixtures()
        processes = [subprocess.Popen(self.entry + ['--home', str(self.home), '__ui'], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env)
                     for _ in range(2)]
        def call(process, action, **args):
            process.stdin.write(json.dumps(dict(action=action, **args)) + '\n')
            process.stdin.flush()
            return json.loads(process.stdout.readline())
        try:
            first, second = processes
            self.assertEqual(call(first, 'state')['data']['environment'], 'default')
            self.assertEqual(call(second, 'state')['data']['environment'], 'default')
            plan = call(first, 'key_plan', name='TOKEN')['data']
            self.assertTrue(call(first, 'key_check', id=plan['id'], value='synthetic-edited')['ok'])
            selected = call(first, 'environment_select', name='test')['data']
            self.assertEqual(selected['environment'], 'test')
            self.assertEqual(selected['environment_source'], 'saved')
            self.assertEqual(selected['startup_sources'], {'environment': 'default', 'context': 'default'})
            self.assertFalse(call(first, 'key_save', id=plan['id'], value='synthetic-edited')['ok'])
            self.assertEqual(call(second, 'state')['data']['environment'], 'default')
            self.assertEqual(self.active()['environment'], 'test')
        finally:
            for process in processes:
                process.stdin.close()
                process.wait(timeout=5)
                process.stdout.close()
                process.stderr.close()

    def test_startup_selection_errors_use_bounded_private_handshake(self):
        self.home.mkdir(mode=0o700)
        active = self.home / 'active.json'
        active.write_text('{broken')
        active.chmod(0o600)
        result = self.command('__ui', input='{"action":"state"}\n', expected=2)
        reply = json.loads(result.stdout)
        self.assertFalse(reply['ok'])
        self.assertIn('Repair the active selection file', reply['error'])
        self.assertEqual(result.stderr, '')
        result = self.command('__ui', input='synthetic_secret_not_JSON\n', expected=2)
        self.assertEqual(json.loads(result.stdout)['error'], 'Invalid UI request.')
        self.assertNotIn('synthetic_secret', result.stdout + result.stderr)
        result = self.command('__ui', input='x' * (8 * 1024 * 1024 + 1), expected=2)
        self.assertEqual(result.stdout + result.stderr, '')
        # __ui belongs to the child here, so a startup error keeps direct CLI output.
        result = self.command('run', 'TOKEN', '--', 'example', '__ui', expected=2)
        self.assertEqual(result.stdout, '')
        self.assertIn('Repair the active selection file', result.stderr)

    def test_live_bridge_refuses_deleted_named_targets_and_can_switch_away(self):
        self.fixtures()
        process = subprocess.Popen(self.entry + ['--home', str(self.home), '--env', 'test',
                                                '--context', 'acme', '__ui'], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env)
        def call(action, **args):
            process.stdin.write(json.dumps(dict(action=action, **args)) + '\n')
            process.stdin.flush()
            return json.loads(process.stdout.readline())
        try:
            call('state')
            profile = self.home / 'contexts/acme/profile.json'
            profile_before = profile.read_bytes()
            path = Store(self.home, environment='test').env_path
            path.unlink()
            self.assertFalse(call('key_plan', name='TOKEN')['ok'])
            self.assertFalse(call('profile_save', field='business_name', value='Should not save')['ok'])
            self.assertFalse(path.exists())
            self.assertEqual(profile.read_bytes(), profile_before)
            self.assertTrue(call('environment_list')['ok'])
            self.assertTrue(call('environment_select', name='default')['ok'])
            context_config = self.home / 'contexts/acme/context.json'
            context_config.unlink()
            self.assertFalse(call('key_plan', name='TOKEN')['ok'])
            self.assertFalse(call('profile_save', field='business_name', value='Should not save')['ok'])
            self.assertFalse(context_config.exists())
            self.assertEqual(profile.read_bytes(), profile_before)
            contexts = call('context_list')
            self.assertTrue(contexts['ok'])
            self.assertEqual([row['name'] for row in contexts['data']['contexts']], [''])
            self.assertTrue(call('context_select', name='')['ok'])
            self.assertTrue(call('key_plan', name='TOKEN')['ok'])
        finally:
            process.stdin.close()
            process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()

    def test_legacy_key_home_is_unchanged_by_saved_selection(self):
        legacy = self.root / '.config/godmode'
        env = dict(os.environ)
        try:
            os.environ['HOME'] = str(self.root)
            Store(legacy).set('TOKEN', 'synthetic-legacy')
        finally:
            os.environ.clear()
            os.environ.update(env)
        before = {p.name: p.read_bytes() for p in legacy.iterdir() if p.is_file()}
        self.command('use', '--env', 'default', '--context', '-', explicit_home=False)
        self.assertEqual(self.active(explicit_home=False)['env_path'], str(legacy / '.env.godmode'))
        self.assertEqual({p.name: p.read_bytes() for p in legacy.iterdir() if p.is_file()}, before)
        self.assertTrue((self.home / 'active.json').exists())

    def test_use_records_complete_recent_pairs_and_preserves_motion_and_unknown_settings(self):
        self.command('settings', 'motion', 'off')
        path = self.home / 'ui.json'
        path.write_text('{"motion":false,"future_setting":{"keep":"this"}}')
        for name in ('north', 'south'):
            self.command('env', 'create', name)
            self.command('context', 'create', name + '-business')
        north = {'environment': 'north', 'context': 'north-business'}
        south = {'environment': 'south', 'context': 'south-business'}
        automatic = {'environment': 'default', 'context': ''}
        for pair, expected in ((north, [north, automatic]), (south, [south, north, automatic]),
                               (north, [north, south, automatic])):
            self.command('use', '--env', pair['environment'], '--context', pair['context'])
            self.assertEqual(json.loads((self.home / 'active.json').read_text()), {'schema': 1, **pair})
            self.assertEqual(json.loads(path.read_text()),
                             {'motion': False, 'future_setting': {'keep': 'this'}, 'recent_setups': expected})
            self.assertEqual(json.loads(self.command('settings', '--json').stdout),
                             {'motion': False, 'path': str(path)})
        before = path.read_bytes(), path.stat().st_mtime_ns
        self.command('use', '--env', 'north', '--context', 'north-business')
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)
        self.command('settings', 'motion', 'on')
        data = json.loads(path.read_text())
        self.assertTrue(data['motion'])
        self.assertEqual(data['recent_setups'], [north, south, automatic])
        self.assertEqual(data['future_setting'], {'keep': 'this'})

    def test_use_recent_history_caps_five_without_duplicates(self):
        self.command('context', 'create', 'business')
        for name in ('one', 'two', 'three', 'four', 'five', 'six'):
            self.command('env', 'create', name)
            self.command('use', name, '--context', 'business')
        history = json.loads((self.home / 'ui.json').read_text())['recent_setups']
        self.assertEqual(history, [{'environment': name, 'context': 'business'}
                                   for name in ('six', 'five', 'four', 'three', 'two')])
        self.command('use', 'three', '--context', 'business')
        history = json.loads((self.home / 'ui.json').read_text())['recent_setups']
        self.assertEqual([pair['environment'] for pair in history], ['three', 'six', 'five', 'four', 'two'])

    def test_unapplied_and_failed_cli_choices_do_not_change_recent_history(self):
        self.command('use', '--env', 'default', '--context', '-')
        history_path, active_path = self.home / 'ui.json', self.home / 'active.json'
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (history_path, active_path)}
        self.command('env', 'create', 'pending')
        self.command('context', 'create', 'pending-business')
        self.command('--env', 'pending', '--context', 'pending-business', 'active', '--json')
        self.command('--env', 'pending', '--context', 'pending-business', 'agents', '--print')
        self.command('env', 'list')
        self.command('context', 'list')
        self.command('settings', '--json')
        self.command('use', 'missing', expected=2)
        self.command('use', 'pending', '--context', 'missing-business', expected=2)
        for path, snapshot in before.items():
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), snapshot)

    def test_use_history_warning_is_nonfatal_and_preserves_malformed_file(self):
        self.command('settings', 'motion', 'off')
        self.command('env', 'create', 'north')
        self.command('context', 'create', 'north-business')
        path = self.home / 'ui.json'
        for raw in ('{broken', '{"motion":false,"recent_setups":[{"environment":"../private-path","context":""}]}'):
            with self.subTest(raw=raw):
                path.write_text(raw)
                path.chmod(0o600)
                result = self.command('use', '--env', 'north', '--context', 'north-business')
                self.assertIn('Active loadout saved. Keys: north', result.stdout)
                self.assertIn('Active loadout saved, but recent loadouts were not updated.', result.stderr)
                self.assertNotIn('../private-path', result.stdout + result.stderr)
                self.assertEqual(path.read_text(), raw)
                active = self.active()
                self.assertEqual((active['environment'], active['context']), ('north', 'north-business'))

    def test_use_history_uses_previous_saved_pair_instead_of_shell_override(self):
        for name in ('north', 'south'):
            self.command('env', 'create', name)
            self.command('context', 'create', name + '-business')
        self.command('use', '--env', 'north', '--context', 'north-business')
        self.command('use', '--env', 'south', '--context', 'south-business',
                     overrides={'GODMODE_ENV': 'unselected-shell', 'GODMODE_CONTEXT': 'unselected-shell-business'})
        history = json.loads((self.home / 'ui.json').read_text())['recent_setups']
        self.assertEqual(history[:2], [{'environment': 'south', 'context': 'south-business'},
                                      {'environment': 'north', 'context': 'north-business'}])
        self.assertNotIn('unselected-shell', json.dumps(history))


if __name__ == '__main__':
    unittest.main()
