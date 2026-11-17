"""Complete named files: synthetic credentials, isolated temporary homes only."""
import concurrent.futures
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from godmode_context import ContextStore, context_create
from godmode_environment import environment_create, environment_list, environment_profile, environment_show
from godmode_store import STORE_HEADER, Store, environment_name


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='godmode-environments-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / '.godmode'
        self.env = dict(HOME=str(self.root), PATH=os.environ['PATH'], TERM='dumb')

    def command(self, *args, input=None, expected=0, home=True):
        command = [sys.executable, str(ROOT / 'godmode.py')]
        if home:
            command += ['--home', str(self.home)]
        result = subprocess.run(command + list(args), input=input, text=True,
                                capture_output=True, env=self.env, timeout=15)
        self.assertEqual(result.returncode, expected, result.stderr)
        return result

    def test_exact_snapshot_and_independent_edits(self):
        source = Store(self.home)
        source.set('STRIPE_SECRET_KEY', 'synthetic-original')
        source.set('SHARED_TOKEN', 'synthetic-common')
        # Include preserved manual comments and mixed line endings without any real secrets.
        source.env_path.write_bytes(source.env_path.read_bytes() + b'# kept comment\r\nBLANK=\r\n')
        original, seal_key = source.env_path.read_bytes(), source.key_path.read_bytes()
        self.command('env', 'create', 'acme-staging', '--copy', 'default')
        target = Store(self.home, environment='acme-staging')
        self.assertEqual(target.env_path.read_bytes(), original)
        self.assertEqual(target.env_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(target.env_path.stat().st_nlink, 1)
        self.assertNotEqual(source.env_path.stat().st_ino, target.env_path.stat().st_ino)
        self.command('--env', 'acme-staging', 'set', 'STRIPE_SECRET_KEY', '--stdin', input='synthetic-acme')
        self.assertEqual(source.env_path.read_bytes(), original)
        self.assertEqual(source.key_path.read_bytes(), seal_key)
        self.assertEqual(target.values(['STRIPE_SECRET_KEY', 'SHARED_TOKEN']),
                         {'STRIPE_SECRET_KEY': 'synthetic-acme', 'SHARED_TOKEN': 'synthetic-common'})
        source.set('SHARED_TOKEN', 'synthetic-rotated')
        self.assertEqual(target.values(['SHARED_TOKEN']), {'SHARED_TOKEN': 'synthetic-common'})
        self.command('env', 'create', 'acme-staging', '--copy', 'default', expected=2)
        self.assertEqual(target.values(['STRIPE_SECRET_KEY']), {'STRIPE_SECRET_KEY': 'synthetic-acme'})

    def test_empty_file_never_falls_back_and_named_missing_refuses(self):
        self.command('set', 'STRIPE_SECRET_KEY', '--stdin', input='synthetic-base')
        self.command('env', 'create', 'empty')
        self.assertEqual(Store(self.home, environment='empty').env_path.read_text(), STORE_HEADER)
        marker = self.root / 'child-ran'
        failure = self.command('--env', 'empty', 'run', 'STRIPE_SECRET_KEY', '--', sys.executable,
                               '-c', 'from pathlib import Path; Path(' + repr(str(marker)) + ').touch()', expected=2)
        self.assertFalse(marker.exists())
        self.assertNotIn('synthetic-base', failure.stdout + failure.stderr)
        self.command('--env', 'missing', 'list', expected=2)
        self.command('--env', 'missing', 'set', 'TOKEN', '--stdin', input='synthetic', expected=2)
        self.command('--env', 'missing', 'profile', 'show', expected=2)
        self.assertFalse(Store(self.home, environment='missing').exists())

    def test_profiles_are_independent_and_context_can_be_shared(self):
        self.command('profile', 'set', 'legal_name', '--stdin', input='Default private business')
        self.command('env', 'create', 'acme-staging')
        self.command('env', 'create', 'acme-live')
        self.assertEqual(json.loads(self.command('--env', 'acme-staging', 'profile', 'show').stdout), {})
        self.command('--env', 'acme-staging', 'profile', 'set', 'business_name', '--stdin', input='Staging only')
        self.assertEqual(json.loads(self.command('--env', 'acme-live', 'profile', 'show').stdout), {})
        self.command('context', 'create', 'acme')
        self.command('--env', 'acme-staging', '--context', 'acme', 'profile', 'set', 'business_name', '--stdin', input='Acme')
        self.assertEqual(self.command('--env', 'acme-live', '--context', 'acme', 'profile', 'get', 'business_name').stdout.strip(), 'Acme')
        self.assertEqual(self.command('profile', 'get', 'legal_name').stdout.strip(), 'Default private business')
        self.assertEqual(self.command('--env', 'acme-staging', 'profile', 'get', 'business_name').stdout.strip(), 'Staging only')
        self.assertEqual(environment_profile(self.home, 'acme-staging').path,
                         self.home / 'environments/acme-staging/profile.json')

    def test_aliases_and_preview_resolve_only_inside_selected_store(self):
        base = Store(self.home)
        base.set('ACME_STRIPE', 'synthetic-base-acme')
        context = context_create(self.home, 'acme')
        context.map('STRIPE_SECRET_KEY', 'ACME_STRIPE')
        environment_create(self.home, 'staging')
        wrapped = ContextStore(Store(self.home, environment='staging'), context)
        with self.assertRaisesRegex(ValueError, 'ACME_STRIPE is not saved'):
            wrapped.values(['STRIPE_SECRET_KEY'])
        self.command('--env', 'staging', '--context', 'acme', 'set', 'STRIPE_SECRET_KEY', '--stdin', input='synthetic-staging')
        self.assertEqual(wrapped.values(['STRIPE_SECRET_KEY']), {'STRIPE_SECRET_KEY': 'synthetic-staging'})
        self.assertEqual(base.values(['ACME_STRIPE']), {'ACME_STRIPE': 'synthetic-base-acme'})
        self.assertEqual(wrapped.plan('STRIPE_SECRET_KEY'), wrapped.store.plan('ACME_STRIPE'))
        spec = importlib.util.spec_from_file_location('environment_test_cli', ROOT / 'godmode.py')
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        prompt = cli.KeyPrompt(wrapped, {'name': 'STRIPE_SECRET_KEY'})
        self.assertEqual(prompt.saved_name, 'ACME_STRIPE')
        rendered = '\n'.join(prompt.command('sealed(...)', 100)[0])
        self.assertIn('ACME_STRIPE', rendered)
        self.assertNotIn('STRIPE_SECRET_KEY=', rendered)

    def test_sealing_is_a_whole_file_operation_even_with_aliases(self):
        self.home.mkdir(mode=0o700)
        path = self.home / '.env.godmode.plain'
        path.write_text('A=synthetic-a\nB=synthetic-b\n')
        path.chmod(0o600)
        context = context_create(self.home, 'acme')
        context.map('A', 'B')
        self.command('--env', 'plain', '--context', 'acme', 'migrate')
        self.assertEqual(Store(self.home, environment='plain').values(['A', 'B']),
                         {'A': 'synthetic-a', 'B': 'synthetic-b'})

    def test_selection_is_per_command_and_child_owns_flags(self):
        for name in ('a', 'b'):
            environment_create(self.home, name)
            Store(self.home, environment=name).set('TOKEN', 'synthetic-' + name)
        def run(name):
            self.command('--env', name, 'run', 'TOKEN', '--', sys.executable, '-c',
                         'import os,sys; assert os.environ["TOKEN"] == ' + repr('synthetic-' + name)
                         + '; assert sys.argv[1:] == ["--env", "untouched", "--context", "child"]',
                         '--env', 'untouched', '--context', 'child')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(run, ['a', 'b']))
        self.assertFalse(Store(self.home).exists())
        self.command('--env', 'a', '--env', 'b', 'list', expected=2)
        self.assertEqual(self.command('--env=default', 'path').stdout.strip(), str(self.home / '.env.godmode'))

    def test_safe_metadata_and_task_instruction_do_not_expose_values(self):
        environment_create(self.home, 'acme')
        Store(self.home, environment='acme').set('TOKEN', 'synthetic-secret-value')
        self.command('--env', 'acme', 'profile', 'set', 'legal_name', '--stdin', input='Private company name')
        details = json.loads(self.command('env', 'show', 'acme').stdout)
        self.assertEqual(details['keys'], ['TOKEN'])
        self.assertEqual(details['key_count'], 1)
        self.assertEqual(details['profile_fields'], ['legal_name'])
        self.assertNotIn('synthetic-secret-value', json.dumps(details))
        self.assertNotIn('Private company name', json.dumps(details))
        rows = json.loads(self.command('env', 'list', '--json').stdout)
        self.assertEqual([row['name'] for row in rows], ['default', 'acme'])
        self.command('context', 'create', 'business')
        copied = self.command('--env', 'acme', '--context', 'business', 'agents', '--print').stdout
        self.assertIn('--env acme --context business', copied)
        self.assertIn('.env.godmode.acme', copied)
        self.assertIn('contexts/business/profile.json', copied)
        generic = self.command('--env', 'acme', '--context', 'business', 'agents').stdout
        self.assertNotIn('--env acme', generic)
        self.assertFalse((self.root / '.codex/AGENTS.md').exists())

    def test_names_and_unsafe_files_are_refused_without_changes(self):
        for name in ('', '../escape', 'UPPER', '1abc', 'a/b', 'a.b', 'a' * 97):
            with self.assertRaises(ValueError):
                environment_name(name)
        longest = 'a' + '1-_' * 31 + 'zz'
        self.assertEqual(len(longest), 96)
        environment_create(self.home, longest)
        source = Store(self.home)
        source.set('TOKEN', 'synthetic')
        outside = self.root / 'outside'
        outside.write_text('unchanged')
        target = Store(self.home, environment='symlink')
        target.env_path.symlink_to(outside)
        with self.assertRaises(ValueError):
            environment_create(self.home, 'symlink', 'default')
        self.assertEqual(outside.read_text(), 'unchanged')
        target.env_path.unlink()
        source.env_path.chmod(0o644)
        with self.assertRaises(ValueError):
            environment_create(self.home, 'unsafe', 'default')
        self.assertFalse(Store(self.home, environment='unsafe').exists())
        source.env_path.chmod(0o600)
        os.link(source.env_path, self.root / 'hardlink')
        with self.assertRaises(ValueError):
            environment_create(self.home, 'linked', 'default')
        self.assertFalse(Store(self.home, environment='linked').exists())

    def test_copy_rechecks_source_and_create_never_overwrites_racing_destination(self):
        source = Store(self.home)
        source.set('TOKEN', 'synthetic')
        original_write = Store._write
        def changed(target, text, previous, directory, **kwargs):
            source.env_path.write_bytes(source.env_path.read_bytes() + b'# external change\n')
            return original_write(target, text, previous, directory, **kwargs)
        with mock.patch.object(Store, '_write', changed):
            with self.assertRaisesRegex(ValueError, 'source environment changed'):
                environment_create(self.home, 'changed', 'default')
        self.assertFalse(Store(self.home, environment='changed').exists())
        destination = Store(self.home, environment='raced').env_path
        real_link = os.link
        def racing_link(src, dst, **kwargs):
            destination.write_bytes(b'OTHER=synthetic-racer\n')
            destination.chmod(0o600)
            return real_link(src, dst, **kwargs)
        with mock.patch('godmode_store.os.link', side_effect=racing_link):
            with self.assertRaises(ValueError):
                environment_create(self.home, 'raced', 'default')
        self.assertEqual(destination.read_bytes(), b'OTHER=synthetic-racer\n')
        self.assertFalse(list(self.home.glob('.godmode-write-*')))

    def test_writer_lock_and_git_guards_cover_named_files(self):
        source = Store(self.home)
        source.set('TOKEN', 'synthetic')
        fd = os.open(self.home, os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, 'Another editor'):
                environment_create(self.home, 'locked', 'default')
        finally:
            os.close(fd)
        subprocess.run(['git', 'init', '-q', str(self.home)], check=True, env=self.env)
        (self.home / '.gitignore').write_text('.env.godmode*\nseal.key\n')
        environment_create(self.home, 'allowed', 'default')
        subprocess.run(['git', '-C', str(self.home), 'add', '-f', '.env.godmode.allowed'], check=True, env=self.env)
        with self.assertRaisesRegex(ValueError, 'ignored and untracked'):
            Store(self.home, environment='allowed').set('TOKEN', 'synthetic-new')
        with self.assertRaisesRegex(ValueError, 'ignored and untracked'):
            environment_create(self.home, 'copy-tracked', 'allowed')

    def test_all_environments_resolve_one_home_without_value_fallback(self):
        legacy = Store(self.root / '.config/godmode')
        legacy.set('TOKEN', 'synthetic-legacy')
        with mock.patch.dict(os.environ, self.env, clear=True):
            self.assertEqual(Store().env_path, legacy.env_path)
            self.assertEqual(Store(environment='client').env_path, legacy.config_dir / '.env.godmode.client')
            environment_create(None, 'client')
            rows = environment_list(None)
            self.assertEqual(rows[0]['path'], str(legacy.env_path))
            self.assertEqual(rows[0]['profile_path'], str(self.home / 'profile.json'))
            self.assertEqual(rows[1]['path'], str(legacy.config_dir / '.env.godmode.client'))
            self.assertEqual(rows[1]['profile_path'], str(legacy.config_dir / 'environments/client/profile.json'))
            with self.assertRaisesRegex(ValueError, 'TOKEN is not saved'):
                Store(environment='client').values(['TOKEN'])
            environment_create(None, 'copy', 'default')
            self.assertEqual(Store(environment='copy').values(['TOKEN']), {'TOKEN': 'synthetic-legacy'})
            # A canonical named file is a home marker, independent of which name is selected.
            environment_create(self.home, 'canonical')
            self.assertEqual(Store().config_dir, self.home)
            self.assertEqual(Store(environment='client').config_dir, self.home)
            self.assertFalse(Store(environment='client').exists())


if __name__ == '__main__':
    unittest.main()
