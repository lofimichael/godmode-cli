"""The complete populator, using only synthetic credentials in isolated homes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from pty_support import Terminal, values

REPO = Path(__file__).resolve().parents[1]


class CLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable, str(REPO/'scripts/build.py'), '--output', str(REPO/'target/godmode')], check=True, stdout=subprocess.DEVNULL)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='godmode-cli-')
        self.root = Path(self.temp.name).resolve()
        self.home = self.root/'.godmode'
        self.file = self.home/'.env.godmode'
        self.env = {'HOME':str(self.root),'PATH':os.environ.get('PATH','/usr/bin:/bin'),'TERM':'xterm-256color','SHELL':'/bin/sh'}
        self.command = [sys.executable,str(REPO/'target/godmode'),'--home',str(self.home)]
        self.sessions=[]

    def tearDown(self):
        for session in self.sessions:
            session.close()
        self.temp.cleanup()

    def terminal(self, args=None, env=None):
        session = Terminal(self.command+(args or []), env or self.env, cols=100, rows=36)
        self.sessions.append(session)
        return session

    def test_masked_setup_keep_replace_and_plain_manual_file(self):
        terminal=self.terminal()
        terminal.expect('Type GODMODE to continue')
        self.assertFalse(self.file.exists())
        terminal.send(b'GODMODE\r');terminal.expect('Provider number or name')
        token='github_pat_DEMO_ONLY_f62d34'
        terminal.paste(token)
        terminal.send(b'github\r');terminal.expect('Enter to add keys;')
        terminal.send(b'\r');terminal.expect('Paste GH_TOKEN (masked;')
        before=self.file.read_bytes()
        terminal.paste(token)
        terminal.drain(.2)
        self.assertEqual(self.file.read_bytes(),before)
        after_save = len(terminal.capture)
        terminal.send(b'\r');terminal.expect('GH_TOKEN saved.')
        terminal.wait(lambda: b'Provider number or name' in terminal.capture[after_save:])
        terminal.send(b'\r');terminal.done()
        self.assertEqual(values(self.file)['GH_TOKEN'],token)
        self.assertNotIn(token.encode(),terminal.capture)
        self.assertEqual(self.file.stat().st_mode & 0o777,0o600)
        self.assertEqual(sorted(p.name for p in self.home.iterdir()),['.env.godmode'])
        again=self.terminal(['setup','github']);again.expect('Enter to add keys;')
        again.send(b'\r');again.expect('Paste GH_TOKEN (masked;')
        again.send(b'\r');again.done()
        self.assertEqual(values(self.file)['GH_TOKEN'],token)
        self.file.write_text("# manual comment\nCUSTOM_KEY='manual value'\n")
        update=self.terminal(['set','CUSTOM_KEY']);update.expect('Paste CUSTOM_KEY (masked;')
        replacement="synthetic ' quotes $literal"
        update.paste(replacement);update.send(b'\r');update.done()
        self.assertNotIn(replacement.encode(),update.capture)
        self.assertTrue(self.file.read_text().startswith('# manual comment\n'))
        check=subprocess.run(['/bin/sh','-c','. "$1"; test "$CUSTOM_KEY" = "$2"','sh',str(self.file),replacement],capture_output=True)
        self.assertEqual(check.returncode,0)

    def test_multiline_json_cancel_and_plain_output(self):
        key='CUSTOM_SERVICE_JSON'
        subprocess.run(self.command+['init','--accept-disclaimer'],env=self.env,capture_output=True,check=True)
        before=self.file.read_bytes()
        terminal=self.terminal(['set',key]);terminal.expect('Paste '+key)
        value=json.dumps({'private_key':'DEMO_ONLY_'+('x'*14000)},indent=2)
        terminal.paste(value);terminal.drain(.2)
        self.assertEqual(self.file.read_bytes(),before)
        terminal.send(b'\r');terminal.done()
        self.assertEqual(json.loads(values(self.file)[key]),json.loads(value))
        self.assertNotIn(b'DEMO_ONLY_',terminal.capture)
        original=self.file.read_bytes()
        cancel=self.terminal(['set',key]);cancel.expect('Paste '+key)
        cancel.paste('cancelled_DEMO_ONLY');cancel.send(b'\x03');cancel.done(130)
        self.assertEqual(self.file.read_bytes(),original)
        plain=self.terminal(['setup','github'],dict(self.env,NO_COLOR=''))
        plain.expect('Enter to add keys;');plain.send(b's\r');plain.done()
        import re
        self.assertFalse(re.search(rb'\x1b\[[0-9;]*m',plain.capture))

    def test_cli_requires_no_catalog_or_init_state_and_never_accepts_value_arguments(self):
        result=subprocess.run(self.command+['set','ARBITRARY_TOKEN','--stdin'],env=self.env,input='fixture_value',capture_output=True,text=True)
        self.assertEqual(result.returncode,0)
        self.assertEqual(values(self.file)['ARBITRARY_TOKEN'],'fixture_value')
        self.assertFalse((self.home/'state').exists())
        marker='NOT_A_COMMAND_ARGUMENT_SECRET'
        bad=subprocess.run(self.command+['set','ARBITRARY_TOKEN',marker],env=self.env,capture_output=True,text=True)
        self.assertEqual(bad.returncode,2)
        self.assertNotIn(marker,bad.stdout+bad.stderr)
        self.assertEqual(subprocess.check_output(self.command+['path'],env=self.env,text=True).strip(),str(self.file))
        script=(REPO/'target/godmode').read_text()
        self.assertTrue(script.startswith('#!/usr/bin/env python3'))
        self.assertIn('class Store:',script)
        self.assertIn('def read_secret(',script)
        self.assertNotIn('from godmode_store import',script)


if __name__=='__main__':
    unittest.main()
