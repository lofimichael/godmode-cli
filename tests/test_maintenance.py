import hashlib
import importlib.util
import json
import os
import shlex
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from godmode_maintenance import doctor_report, managed_install, update_command
from godmode_profile import Profile, PROFILE_FIELDS
from godmode_store import Store
from godmode_context import context_create, ContextStore


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.bin = self.root / 'bin'
        self.bin.mkdir(mode=0o700)
        self.exe = self.bin / 'godmode'
        self.exe.write_text('synthetic CLI\n')
        self.up = self.bin / 'godmodeup'
        self.up.write_text('#!/bin/sh\nexit 0\n')
        self.api = dict(VERSION='test', PROFILE_FIELDS=PROFILE_FIELDS, agent_targets=lambda: [])
        self.scope = patch.dict(os.environ, {'GODMODE_EXECUTABLE': str(self.exe)}, clear=False)
        self.scope.start()
        self.receipt()

    def tearDown(self):
        self.scope.stop()
        self.tmp.cleanup()

    def receipt(self):
        entries = ['format 1', 'home -']
        for name in ('godmode', 'godmodeup'):
            entries.append(name + ' ' + hashlib.sha256((self.bin / name).read_bytes()).hexdigest())
        (self.bin / '.godmode-install-receipt').write_text('\n'.join(entries) + '\n')

    def test_installed_update_is_sibling_and_no_credentials_or_home_selection_leak(self):
        self.assertEqual(managed_install(), self.up)
        with patch.dict(os.environ, {'STRIPE_SECRET_KEY': 'synthetic-not-forwarded', 'GODMODE_HOME': '/wrong',
                                     'ENV': '/shell-hook', 'BASH_ENV': '/shell-hook'}), \
                patch('godmode_maintenance.subprocess.call', return_value=7) as child:
            self.assertEqual(update_command(['--version', 'v0.18.0']), 7)
        args, kwargs = child.call_args
        self.assertEqual(args[0], ['/bin/sh', str(self.up), '--install-only', '--version', 'v0.18.0'])
        for name in ('STRIPE_SECRET_KEY', 'GODMODE_HOME', 'ENV', 'BASH_ENV'):
            self.assertNotIn(name, kwargs['env'])

    def test_changed_updater_is_never_executed(self):
        self.up.write_text('malicious replacement\n')
        with patch('godmode_maintenance.subprocess.call') as child:
            with self.assertRaisesRegex(ValueError, 'has changed'):
                update_command([])
            child.assert_not_called()

    def test_changed_binary_is_never_replaced(self):
        self.exe.write_text('local edit\n')
        with self.assertRaisesRegex(ValueError, 'has changed'):
            managed_install()

    def test_symlink_or_hardlinked_updater_refused(self):
        other = self.root / 'other'
        other.write_bytes(self.up.read_bytes())
        self.up.unlink()
        self.up.symlink_to(other)
        with self.assertRaises(ValueError):
            managed_install()
        self.up.unlink()
        os.link(other, self.up)
        with self.assertRaises(ValueError):
            managed_install()

    def test_receipt_ambiguity_and_unsafe_permissions_refused(self):
        path = self.bin / '.godmode-install-receipt'
        path.write_text(path.read_text() + path.read_text().splitlines()[2] + '\n')
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            managed_install()
        self.receipt()
        self.up.chmod(0o666)
        with self.assertRaisesRegex(ValueError, 'not writable'):
            managed_install()

    def test_update_no_force_shell_or_unknown_flag(self):
        for args in (['--force'], ['--version', 'v1.2.3;true'], ['--binary', '/tmp/a'], ['--setup']):
            with self.subTest(args=args), self.assertRaises(ValueError):
                update_command(args)

    def test_doctor_fresh_home_is_read_only(self):
        home = self.root / 'fresh'
        report = doctor_report(Store(home), Profile(home), self.api)
        self.assertTrue(report['ok'])
        self.assertFalse(home.exists())
        self.assertEqual(next(c for c in report['checks'] if c['name'] == 'Keys')['status'], 'warn')

    def test_doctor_reports_unsafe_profile_construction_and_missing_named_file(self):
        def profile():
            raise ValueError('Environment profile directories must be yours, real directories and mode 0700.')
        report = doctor_report(Store(self.root / 'missing', environment='acme'), profile,
                               dict(self.api, ACTIVE_ENVIRONMENT='acme'))
        self.assertFalse(report['ok'])
        self.assertEqual({item['name'] for item in report['checks'] if item['status'] == 'error'}, {'Keys', 'Profile'})

    def test_doctor_actions_preserve_custom_home_and_shell_literals(self):
        home = self.root / "Client's $(never-execute) home"
        api = dict(self.api, ACTIVE_ENVIRONMENT='acme')
        report = doctor_report(Store(home, environment='acme'), Profile(home), api, home=home)
        for check in report['checks']:
            action = check.get('action', '')
            if action.startswith('godmode '):
                words = shlex.split(action)
                self.assertEqual(words[:5], ['godmode', '--home', str(home), '--env', 'acme'])

    def test_doctor_authenticates_seals_without_disclosing_or_mutating(self):
        store = Store(self.root / 'home')
        store.set('DEMO', 'synthetic-private-do-not-print')
        before = store.env_path.read_bytes()
        report = doctor_report(store, Profile(store.config_dir), self.api)
        self.assertTrue(report['ok'])
        self.assertNotIn('synthetic-private', json.dumps(report))
        self.assertEqual(store.env_path.read_bytes(), before)
        store.key_path.unlink()
        report = doctor_report(store, Profile(store.config_dir), self.api)
        self.assertFalse(report['ok'])
        self.assertNotIn('synthetic-private', json.dumps(report))

    def test_doctor_duplicate_names_and_profile_permissions(self):
        store = Store(self.root / 'home')
        store.set('DEMO', 'synthetic-only')
        with store.env_path.open('a') as target:
            target.write('DEMO=synthetic-duplicate\n')
        profile = Profile(store.config_dir)
        profile.write({'business_name': 'Fixture'})
        profile.path.chmod(0o644)
        report = doctor_report(store, profile, self.api)
        self.assertFalse(report['ok'])
        self.assertEqual({item['name'] for item in report['checks'] if item['status'] == 'error'}, {'Keys', 'Profile'})
        self.assertNotIn('synthetic-duplicate', json.dumps(report))

    def test_doctor_authenticates_shadowed_raw_keys_and_counts_file_not_aliases(self):
        store = Store(self.root / 'home')
        store.set('SAVED', 'synthetic-one')
        context = context_create(store.config_dir, 'acme')
        context.map('LOGICAL', 'SAVED')
        api = dict(self.api, ACTIVE_CONTEXT=context)
        mapped = ContextStore(store, context)
        report = doctor_report(mapped, context.profile(), api)
        self.assertTrue(report['ok'])
        self.assertTrue(next(c for c in report['checks'] if c['name'] == 'Keys')['detail'].startswith('1 stored locally.'))
        store.set('LOGICAL', 'synthetic-shadowed')
        raw = store.env_path.read_text()
        rows = raw.splitlines()
        rows = [row[:len('LOGICAL=')] + 'sealed:v1:broken' if row.startswith('LOGICAL=') else row for row in rows]
        store.env_path.write_text('\n'.join(rows) + '\n')
        self.assertFalse(doctor_report(mapped, context.profile(), api)['ok'])


if __name__ == '__main__':
    unittest.main()
