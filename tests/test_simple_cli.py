"""The complete populator, using only synthetic credentials in isolated homes."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess
import sys
import tempfile
import termios
import unittest
from unittest.mock import patch
from pty_support import Screen, Terminal, plain, values

REPO = Path(__file__).resolve().parents[1]
SED = "sed -i ''" if sys.platform == 'darwin' else 'sed -i'
TITLE = 'What will be executed on your machine'
APPEND = "$ printf '%s\\n' "
DOTS = '•••••'


def load_cli():
    spec = importlib.util.spec_from_file_location('godmode_cli', REPO/'godmode.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable, str(REPO/'scripts/build.py'), '--output', str(REPO/'target/godmode')], check=True, stdout=subprocess.DEVNULL)
        cls.providers = {p['id']: p for p in json.loads((REPO/'providers.json').read_text())}

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

    def terminal(self, args=None, env=None, cols=100, rows=36):
        session = Terminal(self.command+(args or []), env or self.env, cols=cols, rows=rows)
        self.sessions.append(session)
        return session

    def init(self):
        subprocess.run(self.command+['init','--accept-disclaimer'],env=self.env,capture_output=True,check=True)

    def opener(self, script='printf "%s\\n" "$1" >> {record}\n'):
        """Stub browser openers. Browsers get an allowlisted environment, so paths are literal."""
        stubs=self.root/('bin-%d' % len(list(self.root.glob('bin-*'))))
        stubs.mkdir()
        record=self.root/'opened.txt'
        for name in ('open','xdg-open'):
            (stubs/name).write_text('#!/bin/sh\n'+script.format(record=shlex.quote(str(record))))
            (stubs/name).chmod(0o755)
        return dict(self.env,PATH=str(stubs)+os.pathsep+self.env['PATH']), record

    def assert_one_region(self, terminal, cols=100):
        screen=Screen(cols).feed(terminal.capture)
        self.assertEqual(screen.count(TITLE),1,'prompt region was not redrawn in place')
        self.assertEqual(screen.count('$ '),1)

    def test_masked_setup_keep_replace_and_plain_manual_file(self):
        terminal=self.terminal()
        terminal.expect('Type GODMODE to continue')
        self.assertFalse(self.file.exists())
        terminal.send(b'GODMODE\r');terminal.expect('Choose a provider')
        token='github_pat_DEMO_ONLY_f62d34'
        terminal.paste(token)
        terminal.send(b'github\r');terminal.expect('Paste your token:')
        terminal.wait(lambda: APPEND+"'GH_TOKEN=…' >> ~/.godmode/.env.godmode" in plain(terminal.capture))
        before=self.file.read_bytes()
        terminal.paste(token)
        terminal.wait(lambda: APPEND+"'GH_TOKEN=git•••••d34' >> ~/.godmode/.env.godmode" in plain(terminal.capture))
        self.assertIn('Paste your token: git•••••d34', plain(terminal.capture))
        self.assert_one_region(terminal)
        self.assertEqual(self.file.read_bytes(),before)
        mark=len(terminal.capture)
        terminal.send(b'\r');terminal.after(mark,'Saved GH_TOKEN')
        terminal.after(mark,'Choose a provider')
        terminal.send(b'\r');terminal.done()
        # After saving, the region collapses to a one-line receipt of the command.
        screen=Screen(100).feed(terminal.capture)
        self.assertEqual(screen.count(TITLE),0)
        self.assertEqual(screen.count(APPEND+"'GH_TOKEN=git•••••d34' >> ~/.godmode/.env.godmode"),1)
        self.assertEqual(values(self.file)['GH_TOKEN'],token)
        self.assertNotIn(token.encode(),terminal.capture)
        self.assertNotIn(b'DEMO_ONLY',terminal.capture)
        self.assertEqual(self.file.stat().st_mode & 0o777,0o600)
        self.assertEqual(sorted(p.name for p in self.home.iterdir()),['.env.godmode'])
        again=self.terminal(['setup','github']);again.expect('Paste your token:')
        again.wait(lambda: SED+" 's/^GH_TOKEN=.*/GH_TOKEN=…/' ~/.godmode/.env.godmode" in plain(again.capture))
        self.assertIn('Your saved GH_TOKEN stays unless you paste a new one.', plain(again.capture))
        again.send(b'\r');again.expect('Kept your saved GH_TOKEN.');again.done()
        self.assertEqual(values(self.file)['GH_TOKEN'],token)
        self.file.write_text("# manual comment\nCUSTOM_KEY='manual value'\n")
        update=self.terminal(['set','CUSTOM_KEY']);update.expect('Paste your key:')
        replacement="synthetic ' quotes $literal"
        update.paste(replacement)
        update.wait(lambda: SED+' "s/^CUSTOM_KEY=.*/CUSTOM_KEY=\'syn•••••ral\'/"' in plain(update.capture))
        update.send(b'\r');update.done()
        self.assertNotIn(replacement.encode(),update.capture)
        self.assertTrue(self.file.read_text().startswith('# manual comment\n'))
        check=subprocess.run(['/bin/sh','-c','. "$1"; test "$CUSTOM_KEY" = "$2"','sh',str(self.file),replacement],capture_output=True)
        self.assertEqual(check.returncode,0)

    def test_multiline_json_cancel_and_plain_output(self):
        key='CUSTOM_SERVICE_JSON'
        self.init()
        before=self.file.read_bytes()
        terminal=self.terminal(['set',key]);terminal.expect('Paste your JSON key:')
        value=json.dumps({'private_key':'DEMO_ONLY_'+('x'*14000)},indent=2)
        terminal.paste(value);terminal.settle(.3)
        self.assertEqual(self.file.read_bytes(),before)
        terminal.send(b'\r');terminal.done()
        self.assertEqual(json.loads(values(self.file)[key]),json.loads(value))
        self.assertNotIn(b'DEMO_ONLY_',terminal.capture)
        original=self.file.read_bytes()
        cancel=self.terminal(['set',key]);cancel.expect('Paste your JSON key:')
        cancel.paste('cancelled_DEMO_ONLY');cancel.send(b'\x03');cancel.done(130)
        self.assertEqual(self.file.read_bytes(),original)
        # Started for one provider there is no list, so Esc cancels like Ctrl-C.
        uncolored=self.terminal(['setup','github'],dict(self.env,NO_COLOR=''))
        uncolored.expect('Esc cancels');uncolored.send(b'\x1b');uncolored.done(130)
        self.assertIn('Cancelled.',plain(uncolored.capture))
        self.assertFalse(re.search(rb'\x1b\[[0-9;]*m',uncolored.capture))
        self.assertEqual(self.file.read_bytes(),original)

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

    def test_invalid_value_is_explained_live_and_enter_does_not_save_it(self):
        self.init()
        before=self.file.read_bytes()
        terminal=self.terminal(['set','ACME_TOKEN']);terminal.expect('Paste your token:')
        terminal.paste('first SYNTHETIC line\nsecond SYNTHETIC line')
        terminal.expect("Can't save this yet: Multiline credentials must be a valid JSON object.")
        mark=len(terminal.capture)
        terminal.send(b'\r')
        terminal.wait(lambda: b'\a' in terminal.capture[mark:])
        terminal.settle(.5)
        self.assertNotIn(b'\x1b[?2004l',terminal.capture[mark:],'Enter left the prompt')
        self.assertEqual(self.file.read_bytes(),before)
        terminal.send(b'\x15');terminal.paste('acme_DEMO_ONLY_value_123456')
        terminal.after(mark,APPEND+"'ACME_TOKEN=acm•••••456' >>")
        terminal.send(b'\r');terminal.expect('Saved ACME_TOKEN');terminal.done()
        self.assertEqual(values(self.file)['ACME_TOKEN'],'acme_DEMO_ONLY_value_123456')
        self.assertNotIn(b'SYNTHETIC',terminal.capture)
        self.assertNotIn(b'DEMO_ONLY',terminal.capture)
        single=self.terminal(['set','ACME_SERVICE_JSON']);single.expect('Paste your JSON key:')
        single.paste('/Users/someone/Downloads/key.json')
        single.expect("Can't save this yet: This key needs the JSON key file's contents, starting with {.")
        single.send(b'\x03');single.done(130)

    def test_typed_values_show_one_dot_per_character_and_no_ends(self):
        self.init()
        terminal=self.terminal(['set','ACME_TOKEN']);terminal.expect('Paste your token:')
        typed='typed!SYNTH_only_42'
        for count, char in enumerate(typed, 1):
            mark=len(terminal.capture)
            terminal.send(char.encode())
            terminal.after(mark,'Paste your token: '+'•'*count)
        text=plain(terminal.capture)
        # Typed values are always quoted, so the quotes cannot reveal which key needed them.
        self.assertNotIn('ACME_TOKEN=•',text)
        self.assertIn("ACME_TOKEN='"+'•'*len(typed)+"'",text)
        for leak in (typed[:3]+'•', '•'+typed[-3:], '•'+typed[-1], typed[0]+'•'):
            self.assertNotIn(leak,text)
        terminal.send(b'\r');terminal.expect('Saved ACME_TOKEN');terminal.done()
        self.assertEqual(values(self.file)['ACME_TOKEN'],typed)

    def test_prompt_region_redraws_in_place_after_every_action(self):
        self.init()
        env,record=self.opener()
        terminal=self.terminal(['setup','github'],env)
        terminal.expect('Paste your token:')
        steps=[('paste',b'\x1b[200~github_pat_DEMO_ONLY_aaaa111\x1b[201~','git•••••111'),
               ('clear',b'\x15','Tab opens github.com'),
               ('paste again',b'\x1b[200~github_pat_DEMO_ONLY_bbbb222\x1b[201~','git•••••222'),
               ('paste replaces',b'\x1b[200~github_pat_DEMO_ONLY_cccc333\x1b[201~','git•••••333'),
               ('steps',b'?','Docs'),
               ('browser',b'\t','Opened github.com in your browser.'),
               ('clear',b'\x15','Tab opens github.com'),
               ('type',b'a','Paste your token: •'),
               ('type',b'b','Paste your token: ••'),
               ('delete',b'\x7f','Paste your token: •')]
        for name, data, shown in steps:
            with self.subTest(step=name):
                mark=len(terminal.capture)
                terminal.send(data)
                terminal.after(mark,shown)
                terminal.settle(.15)
                self.assert_one_region(terminal)
        screen=Screen(100).feed(terminal.capture)
        self.assertEqual(screen.count('Name it godmode'),1)
        self.assertEqual(screen.count('Opened github.com in your browser.'),1)
        self.assertEqual(record.read_text(),self.providers['github']['console']+'\n')
        terminal.send(b'\x03');terminal.done(130)
        self.assertNotIn('GH_TOKEN',values(self.file))

    def test_narrow_terminal_long_key_and_resize_redraw_cleanly(self):
        self.init()
        narrow=self.terminal(['set','ACME_TOKEN'],cols=34)
        narrow.expect('Paste your token:')
        for data in (b'\x1b[200~acme_DEMO_ONLY_value_123456\x1b[201~', b'\x15', b'x', b'y'):
            mark=len(narrow.capture)
            narrow.send(data);narrow.wait(lambda: b'\x1b[J' in narrow.capture[mark:]);narrow.settle(.15)
            screen=Screen(34).feed(narrow.capture)
            self.assertEqual(screen.count('What will be executed on'),1)
            self.assertEqual(screen.count('Paste your token:'),1)
        # Typed dots outgrow a narrow row; the terminal wraps them and the redraw must count that.
        narrow.send(b'\x15')
        for count in range(1, 23):
            mark=len(narrow.capture)
            narrow.send(b'k');narrow.after(mark,'•'*count);narrow.settle(.05)
            screen=Screen(34).feed(narrow.capture)
            self.assertEqual(screen.count('Paste your token:'),1,'stale input rows after %d keys' % count)
            self.assertEqual(screen.count('What will be executed on'),1)
        narrow.send(b'\x03');narrow.done(130)
        name='ACME_'+'WAREHOUSE_'*9+'TOKEN'
        long=self.terminal(['set',name],cols=80)
        long.expect('Paste your token:')
        for data in (b'\x1b[200~acme_DEMO_ONLY_value_123456\x1b[201~', b'\x15', b'z'):
            mark=len(long.capture)
            long.send(data);long.wait(lambda: b'\x1b[J' in long.capture[mark:]);long.settle(.15)
            self.assertEqual(Screen(80).feed(long.capture).count(TITLE),1)
        # A resize redraws at once, without waiting for a key.
        mark=len(long.capture)
        fcntl.ioctl(long.slave, termios.TIOCSWINSZ, struct.pack('HHHH', 36, 60, 0, 0))
        long.wait(lambda: b'\x1b[J' in long.capture[mark:])
        long.send(b'\x03');long.done(130)

    def test_provider_steps_browser_fallbacks_and_esc_back_to_list(self):
        self.init()
        env,record=self.opener()
        terminal=self.terminal(['setup'],env)
        terminal.expect('Choose a provider');terminal.send(b'1\r');terminal.expect('Paste your token:')
        terminal.send(b'?');terminal.expect('Name it godmode')
        terminal.send(b'\t');terminal.expect('Opened github.com in your browser.')
        self.assertEqual(record.read_text(),self.providers['github']['console']+'\n')
        mark=len(terminal.capture)
        terminal.send(b'\x1b')
        terminal.after(mark,'GH_TOKEN was not saved.')
        terminal.after(mark,'Choose a provider')
        terminal.send(b'\r');terminal.expect('Done.');terminal.done()
        self.assertNotIn('GH_TOKEN',values(self.file))
        failing,_=self.opener('exit 1\n')
        empty=self.root/'no-opener';empty.mkdir()
        for label, path_env in (('failing opener',failing),('no opener',dict(self.env,PATH=str(empty)))):
            with self.subTest(label):
                session=self.terminal(['setup','github'],path_env)
                session.expect('Paste your token:')
                mark=len(session.capture)
                session.send(b'\t')
                session.after(mark,'Open this page in your browser:')
                session.after(mark,self.providers['github']['console'][:60])
                session.paste('github_pat_DEMO_ONLY_fallback_99');session.after(mark,'git•••••_99')
                session.send(b'\r');session.after(mark,'Saved GH_TOKEN');session.done()

    def test_multi_key_provider_esc_and_key_specific_pages(self):
        self.init()
        env,record=self.opener()
        terminal=self.terminal(['setup'],env)
        terminal.expect('Choose a provider');terminal.send(b'stripe\r');terminal.expect('Paste your key:')
        terminal.paste('sk_test_DEMO_ONLY_first_key_0001')
        mark=len(terminal.capture)
        terminal.send(b'\r');terminal.after(mark,'Saved STRIPE_TEST_SECRET_KEY')
        terminal.after(mark,'STRIPE_TEST_PUBLISHABLE_KEY');terminal.after(mark,'Paste your key:')
        mark=len(terminal.capture)
        terminal.send(b'\x1b')
        terminal.after(mark,'STRIPE_TEST_PUBLISHABLE_KEY was not saved.')
        terminal.after(mark,'Choose a provider');terminal.after(mark,'1 of 4 saved')
        self.assertNotIn('STRIPE_LIVE_SECRET_KEY',plain(terminal.capture[mark:]))
        self.assertEqual(sorted(values(self.file)),['STRIPE_TEST_SECRET_KEY'])
        # Each key's Tab opens its own page: live keys are not on the sandbox page.
        terminal.send(b'stripe\r');terminal.expect('Enter keeps it')
        for _ in range(2):
            mark=len(terminal.capture)
            terminal.send(b'\r');terminal.after(mark,'Paste your key:')
        terminal.expect('STRIPE_LIVE_SECRET_KEY')
        mark=len(terminal.capture)
        terminal.send(b'\t');terminal.after(mark,'Opened dashboard.stripe.com in your browser.')
        self.assertEqual(record.read_text().splitlines(),['https://dashboard.stripe.com/apikeys'])
        terminal.send(b'\x03');terminal.done(130)
        gmail=self.terminal(['setup','gmail'],env);gmail.expect('Enter your Gmail address:')
        self.assertNotIn('Tab opens',plain(gmail.capture))
        gmail.send(b'\x03');gmail.done(130)

    def test_key_states_wording_receipt_after_save_and_short_windows(self):
        self.init()
        self.file.write_text('GH_TOKEN=\n')
        blank=self.terminal(['setup','github']);blank.expect('Paste your token:')
        self.assertIn('Enter skips',plain(blank.capture));self.assertIn('Paste to fill this in.',plain(blank.capture))
        blank.paste('\n');blank.settle(.2)
        blank.send(b'\r');blank.expect('Skipped GH_TOKEN.');blank.done()
        self.file.write_text('GH_TOKEN=two words\n')
        broken=self.terminal(['setup','github']);broken.expect('Paste your token:')
        broken.expect("The saved GH_TOKEN line can't be read; paste to replace it.")
        self.assertIn('Enter leaves it',plain(broken.capture))
        broken.send(b'\r');broken.expect('Left GH_TOKEN unchanged.');broken.done()
        self.file.write_text('GH_TOKEN=github_pat_DEMO_ONLY_old_0001\n')
        mark_env,_=self.opener()
        menu=self.terminal(['setup'],mark_env);menu.expect('Choose a provider');menu.send(b'1\r');menu.expect('Paste your token:')
        mark=len(menu.capture);menu.send(b'\x1b')
        menu.after(mark,'Not changed. Your saved GH_TOKEN stays.');menu.after(mark,'Choose a provider')
        menu.send(b'\x03');menu.done(130)
        # A failed save shows the error, not a receipt of a command that did not complete.
        held=self.terminal(['set','ACME_TOKEN']);held.expect('Paste your token:')
        lock=os.open(self.home,os.O_RDONLY)
        try:
            fcntl.flock(lock,fcntl.LOCK_EX)
            held.paste('acme_DEMO_ONLY_value_123456');held.after(0,'acm•••••456')
            mark=len(held.capture);held.send(b'\r');held.after(mark,'Another editor is saving this file')
            self.assertNotIn('$ printf',plain(held.capture[mark:]).split('Another editor')[0])
        finally:
            os.close(lock)
        held.after(mark,'Paste your token:')
        held.paste('acme_DEMO_ONLY_value_123456');mark=len(held.capture);held.send(b'\r')
        held.after(mark,APPEND+"'ACME_TOKEN=acm•••••456' >>");held.after(mark,'Saved ACME_TOKEN');held.done()
        # Six rows: the explanations give way, the command with the value stays.
        short=self.terminal(['set','SHORT_TOKEN'],cols=80,rows=6);short.expect('Paste your token:')
        short.paste('short_DEMO_ONLY_value_987654')
        short.wait(lambda: Screen(80).feed(short.capture).count("SHORT_TOKEN=sho•••••654")>=1)
        short.settle(.2)
        lines=[l for l in Screen(80).feed(short.capture).lines() if l]
        self.assertTrue(any('SHORT_TOKEN=sho•••••654' in l for l in lines[-3:]),'command not visible')
        self.assertTrue(lines[-1].startswith('Paste your token: sho•••••654'))
        short.send(b'\x03');short.done(130)

    def test_quote_note_and_identifiers(self):
        self.init()
        typed=self.terminal(['set','ACME_TOKEN']);typed.expect('Paste your token:')
        for char in "'SYNTHab'cd'":
            mark=len(typed.capture);typed.send(char.encode());typed.after(mark,'Paste your token: •')
        typed.settle(.2)
        self.assertNotIn('starts and ends with quote marks',plain(typed.capture))
        typed.send(b'\x15');typed.paste("'sk-DEMO_ONLY_quoted_0123'")
        typed.expect('This value starts and ends with quote marks; they are saved as part of it.')
        typed.send(b'\x03');typed.done(130)
        gmail=self.terminal(['setup','gmail']);gmail.expect('Enter your Gmail address:')
        self.assertIn('Type or paste to fill this in.',plain(gmail.capture))
        for char in 'demo@example.com':
            gmail.send(char.encode())
        gmail.after(0,'Enter your Gmail address: demo@example.com')
        gmail.after(0,APPEND+"'GMAIL_USER=demo@example.com' >>")
        gmail.send(b'\r');gmail.expect('Saved GMAIL_USER');gmail.expect('Paste your password:')
        gmail.send(b'\x03');gmail.done(130)
        self.assertEqual(values(self.file)['GMAIL_USER'],'demo@example.com')

    def test_ascii_terminal_uses_plain_glyphs(self):
        self.init()
        env=dict(self.env,PYTHONIOENCODING='ascii',LC_ALL='C')
        terminal=self.terminal(['setup','github'],env)
        terminal.expect('GODMODE');terminal.expect('Paste your token:')
        terminal.paste('github_pat_DEMO_ONLY_ascii_0042')
        terminal.wait(lambda: "| "+APPEND+"'GH_TOKEN=git*****042' >> ~/.godmode/.env.godmode" in plain(terminal.capture))
        self.assertIn('Enter saves | Ctrl-U clears | Esc cancels',plain(terminal.capture))
        terminal.send(b'\r');terminal.expect('Saved GH_TOKEN');terminal.done()
        self.assertNotIn(b'codec',terminal.capture)
        self.assertEqual(values(self.file)['GH_TOKEN'],'github_pat_DEMO_ONLY_ascii_0042')

    def test_preview_command_has_the_same_effect_as_saving(self):
        """Run each preview with the real value under /bin/sh and compare it with Store.set."""
        cli=load_cli()
        fixtures=['', 'A=1\n', 'A=1', '# note\nA=1\r\nB=2\r\n', 'KEY=old\n', 'A=1\nKEY=old', 'A=1\nKEY=old\r\nB=2\n',
                  '# KEY=commented\nKEYX=1\nXKEY=2\n\texport  KEY =tab\n',
                  'export KEY=old\nB=2\n', '  KEY = old  # comment\n', 'KEY=a\nB=2\nexport KEY=b\nKEY=c\n',
                  "KEY=\nOTHER='x # y'\n"]
        values_=['plain_token_DEMO_123', 'two words', "quote'inside", 'back\\slash $dollar `tick` & a/b',
                 'ünïcode-DEMO', "'wrapped in quotes'", '{"private_key": "-----BEGIN\\nDEMO\\n-----END\\n"}', 'trailing\\c']
        self.home.mkdir(mode=0o700)
        store=cli.Store(str(self.home))
        copy=self.root/'copy.env'
        checked=0
        for fixture in fixtures:
            for value in values_:
                with self.subTest(fixture=fixture, value=value):
                    self.file.write_text(fixture);self.file.chmod(0o600)
                    plan=store.plan('KEY')
                    if plan['kept_cr']:
                        continue  # Disclosed in a note: sed would not keep the CR.
                    copy.write_bytes(self.file.read_bytes())
                    words=cli.save_command('KEY',shlex.quote(cli.normalize(value,'KEY')),plan,shlex.quote(str(copy)))
                    # The kind of command never depends on the value, so it reveals nothing hidden.
                    masked=cli.save_command('KEY',"'•••••'",plan,shlex.quote(str(copy)))
                    self.assertEqual([w for w in words if 'KEY=' not in w],[w for w in masked if 'KEY=' not in w])
                    subprocess.run(['/bin/sh','-c',' '.join(words)],check=True,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
                    store.set('KEY',value)
                    self.assertEqual(copy.read_bytes(),self.file.read_bytes(),' '.join(words))
                    checked+=1
        self.assertGreater(checked,50)

    def test_preview_helpers(self):
        cli=load_cli()
        with patch.object(sys,'platform','linux'):
            plan={'lines':[],'plain':False,'kept_cr':False,'crlf':False,'separate':False}
            self.assertEqual(cli.save_command('GH_TOKEN','git•••••d34',plan,'~/.godmode/.env.godmode'),
                             ['printf',"'%s\\n'","'GH_TOKEN=git•••••d34'",'>>','~/.godmode/.env.godmode'])
            self.assertEqual(cli.save_command('K','v',dict(plan,separate=True),'p'),['printf',"'\\n%s\\n'","'K=v'",'>>','p'])
            self.assertEqual(cli.save_command('K','v',dict(plan,crlf=True),'p')[1],"'%s\\r\\n'")
            self.assertEqual(cli.save_command('PASS',"'ab•••••op'",dict(plan,lines=[3],plain=True),'~/x'),
                             ['sed','-i','"s/^PASS=.*/PASS=\'ab•••••op\'/"','~/x'])
            self.assertEqual(cli.save_command('K','v',dict(plan,lines=[2,5]),'p'),
                             ['sed','-i','-e',"'2s/.*/K=v/'",'-e',"'5d'",'p'])
        with patch.object(sys,'platform','darwin'):
            self.assertEqual(cli.save_command('K','v',{'lines':[1],'plain':True,'kept_cr':False,'crlf':False,'separate':False},'p')[:3],['sed','-i',"''"])
        rows=cli.command_rows(['$','printf',"'%s\\n'","'STRIPE_TEST_PUBLISHABLE_KEY=pk_•••••abc'",'>>','~/.godmode/.env.godmode'],48)
        self.assertTrue(all(cli.cells(row)<48 for row in rows))
        self.assertTrue(all(row.endswith(' \\') for row in rows[:-1]))
        self.assertEqual(' '.join(r.rstrip(' \\').strip() for r in rows),
                         "$ printf '%s\\n' 'STRIPE_TEST_PUBLISHABLE_KEY=pk_•••••abc' >> ~/.godmode/.env.godmode")
        # A word wider than the row continues on indented rows, so it does not read as a new command.
        script="'s/^GOOGLE_SEARCH_CONSOLE_SERVICE_ACCOUNT_JSON=.*/GOOGLE_SEARCH_CONSOLE_SERVICE_ACCOUNT_JSON=\\'{\"t•••••\"}\\'/'"
        rows=cli.command_rows(['$','sed','-i',script,'~/.godmode/.env.godmode'],78)
        self.assertTrue(all(cli.cells(row)<78 for row in rows))
        self.assertTrue(all(row.startswith('  ') for row in rows[1:]))
        self.assertEqual(''.join(row[2:] if i else row for i, row in enumerate(rows)).replace(' \\','').count('GOOGLE_SEARCH_CONSOLE_SERVICE_ACCOUNT_JSON'),2)
        with patch.dict(os.environ,{'HOME':str(self.root)}):
            self.assertEqual(cli.home_path(self.home/'.env.godmode'),'~/.godmode/.env.godmode')
            self.assertEqual(cli.home_path(self.root/'my keys'/'.env.godmode'),"~/'my keys/.env.godmode'")
            self.assertEqual(cli.home_path(Path('/opt/godmode/.env.godmode')),'/opt/godmode/.env.godmode')
        labels=[cli.prompt_label({'name':n}) for n in ('GH_TOKEN','A_JSON','GMAIL_APP_PASSWORD','X_KEY','X_KEY_ID','SERVICE_URL')]
        self.assertEqual(labels,['Paste your token:','Paste your JSON key:','Paste your password:','Paste your key:',
                                 'Paste your key ID:','Paste the value:'])
        self.assertEqual(cli.prompt_label(self.providers['gmail']['key'][0]),'Enter your Gmail address:')
        prompt=object.__new__(cli.KeyPrompt);prompt.secret=True
        with patch.object(cli,'mask',lambda value,reveal=True: 'xx•••••yy' if reveal else '•'*len(value)):
            self.assertEqual(prompt.shown('plain_value',True),'xx•••••yy')
            self.assertEqual(prompt.shown('needs quotes',True),"'xx•••••yy'")
            self.assertEqual(prompt.shown('abc',False),"'•••'")
        prompt.secret=False
        self.assertEqual(prompt.shown('me@example.com',True),'me@example.com')


if __name__=='__main__':
    unittest.main()
