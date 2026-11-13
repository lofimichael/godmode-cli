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
MENU = '↑↓ move'
SERVICE_ACCOUNT = {'type':'service_account','project_id':'demo-project','private_key_id':'abc123',
                   'private_key':'-----BEGIN PRIVATE KEY-----\nSYNTHETICKEYMATERIAL\n-----END PRIVATE KEY-----\n',
                   'client_email':'agent@demo-project.iam.gserviceaccount.com','client_id':'1',
                   'token_uri':'https://oauth2.googleapis.com/token','universe_domain':'googleapis.com'}


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

    def seed(self, name, value='seeded_DEMO_ONLY_value_0000'):
        value=json.dumps(dict(SERVICE_ACCOUNT,private_key_id='DEMO_ONLY')) if name.endswith('_JSON') else value
        subprocess.run(self.command+['set',name,'--stdin'],env=self.env,input=value.encode(),capture_output=True,check=True)

    def pointed(self, terminal, cols=100):
        """The row the menu pointer is on, read from the screen as drawn."""
        terminal.settle(.15)
        rows=[row for row in Screen(cols).feed(terminal.capture).lines() if row.startswith('❯ ')]
        self.assertEqual(len(rows),1,'the menu was not redrawn in place')
        return rows[0][2:]

    def assert_one_region(self, terminal, cols=100):
        screen=Screen(cols).feed(terminal.capture)
        self.assertEqual(screen.count(TITLE),1,'prompt region was not redrawn in place')
        self.assertEqual(screen.count('$ '),1)

    def test_masked_setup_keep_replace_and_plain_manual_file(self):
        terminal=self.terminal()
        terminal.expect('Type GODMODE to continue')
        self.assertFalse(self.file.exists())
        terminal.send(b'GODMODE\r');terminal.expect(MENU)
        self.assertTrue(self.pointed(terminal).startswith('GitHub'))
        token='github_pat_DEMO_ONLY_f62d34'
        terminal.paste(token)  # A paste into the menu is ignored and never shown.
        terminal.send(b'\r');terminal.expect('Paste your token:')
        terminal.wait(lambda: APPEND+"'GH_TOKEN=sealed(…)' >> ~/.godmode/.env.godmode" in plain(terminal.capture))
        before=self.file.read_bytes()
        terminal.paste(token)
        terminal.wait(lambda: APPEND+"'GH_TOKEN=sealed(git•••••d34)' >> ~/.godmode/.env.godmode" in plain(terminal.capture))
        self.assertIn('Paste your token: git•••••d34', plain(terminal.capture))
        self.assert_one_region(terminal)
        self.assertEqual(self.file.read_bytes(),before)
        mark=len(terminal.capture)
        terminal.send(b'\r');terminal.after(mark,'Saved GH_TOKEN=sealed(git•••••d34)')
        terminal.after(mark,MENU)
        # Saved: the pointer moves on to the next provider that lacks a key.
        self.assertTrue(self.pointed(terminal).startswith('Cloudflare'))
        self.assertRegex('\n'.join(Screen(100).feed(terminal.capture).lines()),r'\n  GitHub +✓ saved\n')
        terminal.send(b'\x1b');terminal.expect('Done. Your keys are in ~/.godmode/.env.godmode');terminal.done()
        # Every screen erased itself; one receipt line remains.
        screen=Screen(100).feed(terminal.capture)
        self.assertEqual((screen.count(TITLE),screen.count('Cloudflare'),screen.count('Create a GitHub token')),(0,0,0))
        self.assertEqual(screen.count('✓ Saved GH_TOKEN=sealed(git•••••d34)'),1)
        self.assertEqual(values(self.file)['GH_TOKEN'],token)
        self.assertNotIn(token.encode(),terminal.capture)
        self.assertNotIn(b'DEMO_ONLY',terminal.capture)
        self.assertEqual(self.file.stat().st_mode & 0o777,0o600)
        self.assertEqual(sorted(p.name for p in self.home.iterdir()),['.env.godmode','STOP_AND_READ_ME_FOR_KEYS.md','seal.key'])
        self.assertEqual((self.home/'seal.key').stat().st_mode & 0o777,0o600)
        again=self.terminal(['setup','github']);again.expect('Paste your token:')
        again.wait(lambda: SED+" 's/^GH_TOKEN=.*/GH_TOKEN=sealed(…)/' ~/.godmode/.env.godmode" in plain(again.capture))
        self.assertIn('Create a GitHub token  ✓ saved', plain(again.capture))
        again.send(b'\x1b');again.done(130)
        env,record=self.opener()
        keep=self.terminal(['set','GH_TOKEN'],env);keep.expect('Enter opens github.com')
        self.assertIn('Create a GitHub token',plain(keep.capture))
        self.assertIn('Resource owner',plain(keep.capture))
        keep.send(b'\r');keep.expect('Opened github.com')
        keep.send(b'\x1b');keep.done(130)
        self.assertEqual(record.read_text(),self.providers['github']['console']+'\n')
        self.assertEqual(values(self.file)['GH_TOKEN'],token)
        (self.home/'seal.key').unlink()  # A hand-written plain file, as before sealing existed.
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
        terminal=self.terminal(['set',key]);terminal.expect('Drag or paste the JSON file:')
        value=json.dumps({'private_key':'DEMO_ONLY_'+('x'*14000)},indent=2)
        terminal.paste(value);terminal.settle(.3)
        self.assertEqual(self.file.read_bytes(),before)
        terminal.send(b'\r');terminal.done()
        self.assertEqual(json.loads(values(self.file)[key]),json.loads(value))
        self.assertNotIn(b'DEMO_ONLY_',terminal.capture)
        original=self.file.read_bytes()
        cancel=self.terminal(['set',key]);cancel.expect('Drag or paste the JSON file:')
        cancel.paste('cancelled_DEMO_ONLY');cancel.send(b'\x03');cancel.done(130)
        self.assertEqual(self.file.read_bytes(),original)
        # Started for one provider there is no list, so Esc cancels like Ctrl-C.
        uncolored=self.terminal(['setup','github'],dict(self.env,NO_COLOR=''))
        uncolored.expect('Esc cancels');uncolored.send(b'\x1b');uncolored.done(130)
        self.assertIn('Cancelled.',plain(uncolored.capture))
        self.assertFalse(re.search(rb'\x1b\[[0-9;]*m',uncolored.capture))
        self.assertEqual(self.file.read_bytes(),original)
        # A terminal that cannot move the cursor gets a plain refusal, not broken redraws.
        for label, env in (('dumb',dict(self.env,TERM='dumb')),('empty',dict(self.env,TERM='')),
                           ('unset',{k:v for k,v in self.env.items() if k!='TERM'})):
            with self.subTest(TERM=label):
                dumb=self.terminal(['setup'],env)
                dumb.wait(lambda: dumb.process.poll() is not None);dumb.settle(.2)
                self.assertEqual(dumb.process.returncode,2)
                message=[row for row in plain(dumb.capture).splitlines() if row.startswith('godmode:')]
                self.assertEqual(message,['godmode: This terminal cannot redraw. Pipe a value to godmode set KEY --stdin'])
                self.assertNotIn(b'\x1b[',dumb.capture)

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

    def test_provider_guidance_stays_short(self):
        """The whole point of the key screen: a goal, a link, and at most three one-line steps."""
        for provider in self.providers.values():
            self.assertLessEqual(len(provider['about']),44,provider['id'])
            for key in provider['key']:
                with self.subTest(key=key['name']):
                    self.assertLessEqual(len(key['steps']),3)
                    self.assertLessEqual(len(key['goal']),48)
                    self.assertLessEqual(len(key['label']),24)
                    for text in key['steps']+[key.get('note','')]:
                        self.assertLessEqual(len(text.replace('**','')),74,text)
                        self.assertEqual(text.count('**')%2,0,text)
                    for step in key['steps']:
                        self.assertTrue(step.endswith('.') and step[0].isupper(),step)
                    page=key['console'] if 'console' in key else provider['console']
                    self.assertTrue(page is None or page.startswith('https://'),page)
        # The first screen for a 12-row provider fits an 80x24 window without scrolling.
        self.init()
        terminal=self.terminal(['setup'],cols=80,rows=24);terminal.expect(MENU)
        lines=[row for row in Screen(80).feed(terminal.capture).lines()]
        self.assertLessEqual(len(lines),24)
        path=next(index for index, row in enumerate(lines) if row.endswith('~/.godmode/.env.godmode'))
        self.assertEqual((lines[path+1],lines[path+2][:8]),('','❯ GitHub'),'one blank row under the banner')
        self.assertEqual(sum(row.strip()=='⋮' for row in lines),0)
        # A resize redraws the list at once, at the new width, without waiting for a key.
        mark=len(terminal.capture)
        fcntl.ioctl(terminal.slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 50, 0, 0))
        terminal.wait(lambda: b'\x1b[J' in terminal.capture[mark:]);terminal.settle(.15)
        fcntl.ioctl(terminal.slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
        terminal.settle(.3)
        self.assertIsNone(terminal.process.poll())
        terminal.send(b'cl\r');terminal.expect('Paste your token:');terminal.settle(.15)
        screen=[row for row in Screen(80).feed(terminal.capture).lines() if row]
        key_rows=screen[screen.index(next(r for r in screen if r.startswith('Create a Cloudflare API token'))):]
        self.assertLessEqual(len(key_rows),9,key_rows)
        self.assertTrue(all(len(row)<80 for row in key_rows))
        terminal.send(b'\x03');terminal.done(130)

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
        terminal.after(mark,APPEND+"'ACME_TOKEN=sealed(acm•••••456)' >>")
        terminal.send(b'\r');terminal.expect('Saved ACME_TOKEN');terminal.done()
        self.assertEqual(values(self.file)['ACME_TOKEN'],'acme_DEMO_ONLY_value_123456')
        self.assertNotIn(b'SYNTHETIC',terminal.capture)
        self.assertNotIn(b'DEMO_ONLY',terminal.capture)
        single=self.terminal(['set','ACME_SERVICE_JSON']);single.expect('Drag or paste the JSON file:')
        single.paste('/Users/someone/Downloads/key.json')
        single.expect("Can't save this yet: drag the key file here, or paste what is in it.")
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
        self.assertIn("ACME_TOKEN=sealed("+'•'*len(typed)+")",text)
        for leak in (typed[:3]+'•', '•'+typed[-3:], '•'+typed[-1], typed[0]+'•'):
            self.assertNotIn(leak,text)
        terminal.send(b'\r');terminal.expect('Saved ACME_TOKEN');terminal.done()
        self.assertEqual(values(self.file)['ACME_TOKEN'],typed)

    def test_key_screen_redraws_in_place_and_enter_opens_the_page(self):
        self.init()
        env,record=self.opener()
        terminal=self.terminal(['setup','github'],env)
        terminal.expect('Paste your token:')
        steps=[('paste',b'\x1b[200~github_pat_DEMO_ONLY_aaaa111\x1b[201~','git•••••111'),
               ('clear',b'\x15','Enter opens github.com'),
               ('paste again',b'\x1b[200~github_pat_DEMO_ONLY_bbbb222\x1b[201~','git•••••222'),
               ('paste replaces',b'\x1b[200~github_pat_DEMO_ONLY_cccc333\x1b[201~','git•••••333'),
               ('clear',b'\x15','Enter opens github.com'),
               ('open the page',b'\r','Opened github.com'),
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
                self.assertEqual(Screen(100).feed(terminal.capture).count('Create a GitHub token'),1)
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
            # The screen must stay where it is: a miscounted wrapped row would creep down one row per key.
            top=top if count>1 else screen.lines().index('ACME_TOKEN')
            self.assertEqual(screen.lines().index('ACME_TOKEN'),top,'screen moved after %d keys' % count)
            self.assertEqual(screen.lines().count('ACME_TOKEN'),1)
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

    def test_steps_show_browser_fallbacks_and_esc_returns_to_the_list(self):
        self.init()
        env,record=self.opener()
        github=self.providers['github']['console']
        terminal=self.terminal(['setup'],env)
        terminal.expect(MENU);terminal.send(b'\r');terminal.expect('Paste your token:')
        shown=plain(terminal.capture)
        for step in self.providers['github']['key'][0]['steps']:
            self.assertIn(step.replace('**',''),shown)
        self.assertNotIn(github[:40],shown)  # Too long for a row, so it is not on the screen yet.
        # Enter opens the page. An address with no room on screen is printed once, to copy if needed.
        for _ in range(2):
            mark=len(terminal.capture)
            terminal.send(b'\r');terminal.after(mark,'Opened github.com');terminal.settle(.2)
        self.assertEqual(record.read_text(),(github+'\n')*2)
        joined=''.join(Screen(100).feed(terminal.capture).lines())
        self.assertEqual(joined.count(github),1)
        self.assert_one_region(terminal)
        mark=len(terminal.capture)
        terminal.send(b'\x1b');terminal.after(mark,MENU)
        self.assertTrue(self.pointed(terminal).startswith('GitHub'))  # Nothing saved: the pointer stays.
        terminal.send(b'\x1b');terminal.expect('Done.');terminal.done()
        self.assertNotIn('GH_TOKEN',values(self.file))
        failing,_=self.opener('exit 1\n')
        empty=self.root/'no-opener';empty.mkdir()
        for label, path_env in (('failing opener',failing),('no opener',dict(self.env,PATH=str(empty)))):
            with self.subTest(label):
                session=self.terminal(['setup','github'],path_env)
                session.expect('Paste your token:')
                for _ in range(2):
                    mark=len(session.capture)
                    session.send(b'\r');session.after(mark,'No browser here: open the link above');session.settle(.2)
                screen=Screen(100).feed(session.capture)
                self.assertEqual(''.join(screen.lines()).count(github),1,'the address is printed once and stays')
                self.assertEqual((screen.count('Keys for your agents'),screen.count(TITLE)),(1,1))
                session.paste('github_pat_DEMO_ONLY_fallback_99');session.after(mark,'git•••••_99')
                session.send(b'\r');session.after(mark,'Saved GH_TOKEN');session.done()
                # An address already on screen is not repeated.
                shown=self.terminal(['setup','cloudflare'],path_env)
                shown.expect('Paste your token:')
                mark=len(shown.capture)
                shown.send(b'\r');shown.after(mark,'No browser here: open the link above');shown.settle(.2)
                self.assertEqual(Screen(100).feed(shown.capture).count(self.providers['cloudflare']['console']),1)
                shown.send(b'\x03');shown.done(130)

    def test_key_menu_for_a_multi_key_provider_and_each_key_has_its_own_page(self):
        self.init()
        env,record=self.opener()
        terminal=self.terminal(['setup'],env)
        terminal.expect(MENU);terminal.send(b'st')
        self.assertTrue(self.pointed(terminal).startswith('Stripe'))
        mark=len(terminal.capture)
        terminal.send(b'\r');terminal.after(mark,'Esc back')
        self.assertEqual(self.pointed(terminal),'Test secret key')
        terminal.send(b'\r');terminal.expect('Copy your Stripe test secret key')
        terminal.paste('sk_test_DEMO_ONLY_first_key_0001')
        mark=len(terminal.capture)
        terminal.send(b'\r');terminal.after(mark,'Saved STRIPE_TEST_SECRET_KEY=sealed(sk_•••••001)')
        terminal.after(mark,'Esc back')
        self.assertEqual(self.pointed(terminal),'Test publishable key')  # The next key still missing.
        self.assertRegex('\n'.join(Screen(100).feed(terminal.capture).lines()),r'\n  Test secret key +✓ saved\n')
        # Each key opens its own page: live keys are not on the sandbox page.
        mark=len(terminal.capture)
        terminal.send(b'\x1b[B\r');terminal.after(mark,'Create a Stripe live secret key')
        mark=len(terminal.capture)
        terminal.send(b'\r');terminal.after(mark,'Opened dashboard.stripe.com')
        self.assertEqual(record.read_text().splitlines(),['https://dashboard.stripe.com/apikeys'])
        mark=len(terminal.capture)
        terminal.send(b'\x1b');terminal.after(mark,'Esc back')           # Back to Stripe's keys...
        self.assertEqual(self.pointed(terminal),'Live secret key')
        mark=len(terminal.capture)
        terminal.send(b'\x1b');terminal.after(mark,'Esc done')           # ...and back to the providers.
        self.assertRegex('\n'.join(Screen(100).feed(terminal.capture).lines()),r'\n❯ Stripe +1 of 4 saved')
        terminal.send(b'\x03');terminal.done(130)
        self.assertEqual(sorted(values(self.file)),['STRIPE_TEST_SECRET_KEY'])

    def test_another_key_nano_and_where_the_pointer_starts(self):
        self.init()
        self.seed('GH_TOKEN');self.seed('CLOUDFLARE_API_TOKEN');self.seed('STRIPE_TEST_SECRET_KEY')
        stubs=self.root/'editor-bin';stubs.mkdir()
        (stubs/'nano').write_text('#!/bin/sh\nprintf "%s\\n" "$1" > '+shlex.quote(str(self.root/'nano.txt'))+'\n')
        (stubs/'nano').chmod(0o755)
        terminal=self.terminal(['setup'],dict(self.env,PATH=str(stubs)+os.pathsep+self.env['PATH']))
        terminal.expect(MENU)
        self.assertTrue(self.pointed(terminal).startswith('Vercel'))  # The first provider without a key.
        terminal.send(b'a')
        self.assertTrue(self.pointed(terminal).startswith('Another key'))
        mark=len(terminal.capture)
        terminal.send(b'\r');terminal.after(mark,'Type a name for the key')
        terminal.paste('sk_live_SYNTHETIC_PASTED_INTO_NAME_0001')  # Ignored: a name is typed, never pasted.
        terminal.wait(lambda: b'\a' in terminal.capture[mark:]);terminal.settle(.15)
        self.assertNotIn(b'SYNTHETIC_PASTED',terminal.capture)
        ring=len(terminal.capture)
        terminal.send(b'acme token\r');terminal.wait(lambda: b'\a' in terminal.capture[ring:])
        terminal.send(b'\x15ACME_API_TOKEN\r');terminal.after(mark,'Paste your token:')
        terminal.paste('acme_DEMO_ONLY_value_123456')
        mark=len(terminal.capture)
        terminal.send(b'\r');terminal.after(mark,'Saved ACME_API_TOKEN=sealed(acm•••••456)');terminal.after(mark,MENU)
        terminal.send(b'e')
        self.assertTrue(self.pointed(terminal).startswith('Edit the file in nano'))
        mark=len(terminal.capture)
        terminal.send(b'\r');terminal.after(mark,'Opening nano');terminal.after(mark,MENU)
        self.assertEqual((self.root/'nano.txt').read_text().strip(),str(self.file))
        # The same letter again moves to the next name that starts with it.
        for letter, name in ((b'g','GitHub'),(b'g','Gmail'),(b'g','Google'),(b'g','GitHub'),(b'p','PostHog'),(b'r','Prodigi')):
            terminal.send(letter)
            self.assertTrue(self.pointed(terminal).startswith(name),name)
        terminal.send(b'\x1b');terminal.expect('Done.');terminal.done()
        self.assertEqual(values(self.file)['ACME_API_TOKEN'],'acme_DEMO_ONLY_value_123456')

    def test_key_states_wording_receipt_after_save_and_short_windows(self):
        self.home.mkdir(mode=0o700)
        self.file.write_text('GH_TOKEN=\n');self.file.chmod(0o600)  # A plain file: no header, no seal.key.
        env,record=self.opener()
        blank=self.terminal(['set','GH_TOKEN'],env);blank.expect('Paste your token:')
        self.assertIn('Enter opens github.com',plain(blank.capture))
        blank.paste('\n');blank.settle(.2)
        blank.send(b'\r');blank.expect('Opened github.com')
        blank.send(b'\x1b');blank.done(130)
        self.assertEqual(self.file.read_text(),'GH_TOKEN=\n')
        self.file.write_text('GH_TOKEN=two words\n')
        broken=self.terminal(['set','GH_TOKEN'],env);broken.expect('Paste your token:')
        broken.expect("The saved GH_TOKEN line can't be read; paste to replace it.")
        broken.send(b'\x1b');broken.done(130)
        self.assertEqual(self.file.read_text(),'GH_TOKEN=two words\n')
        # A failed save shows the error and no receipt; the retry then leaves one.
        held=self.terminal(['set','ACME_TOKEN']);held.expect('Paste your token:')
        lock=os.open(self.home,os.O_RDONLY)
        try:
            fcntl.flock(lock,fcntl.LOCK_EX)
            held.paste('acme_DEMO_ONLY_value_123456');held.after(0,'acm•••••456')
            mark=len(held.capture);held.send(b'\r');held.after(mark,'Another editor is saving this file')
            self.assertNotIn('Saved',plain(held.capture))
        finally:
            os.close(lock)
        held.after(mark,'Paste your token:')
        held.paste('acme_DEMO_ONLY_value_123456');mark=len(held.capture);held.send(b'\r')
        held.after(mark,'Saved ACME_TOKEN=acm•••••456')  # This file was written as plain text.;held.done()
        # Six rows: the explanations give way, the command with the value stays.
        short=self.terminal(['set','SHORT_TOKEN'],cols=80,rows=6);short.expect('Paste your token:')
        short.paste('short_DEMO_ONLY_value_987654')
        short.wait(lambda: Screen(80).feed(short.capture).count("SHORT_TOKEN=sho•••••654")>=1)
        short.settle(.2)
        lines=[l for l in Screen(80).feed(short.capture).lines() if l]
        self.assertTrue(any('SHORT_TOKEN=sho•••••654' in l for l in lines[-3:]),'command not visible')
        self.assertTrue(lines[-1].startswith('Paste your token: sho•••••654'))
        short.send(b'\x03');short.done(130)

    def test_quote_note_identifiers_and_per_key_paste_rules(self):
        self.init()
        typed=self.terminal(['set','ACME_TOKEN']);typed.expect('Paste your token:')
        for char in "'SYNTHab'cd'":
            mark=len(typed.capture);typed.send(char.encode());typed.after(mark,'Paste your token: •')
        typed.settle(.2)
        self.assertNotIn('starts and ends with quote marks',plain(typed.capture))
        typed.send(b'\x15');typed.paste("'sk-DEMO_ONLY_quoted_0123'")
        typed.expect('This value starts and ends with quote marks; they are saved as part of it.')
        typed.send(b'\x03');typed.done(130)
        # An address is not a secret, so it is shown as it is typed. It has no page to open.
        env,record=self.opener()
        gmail=self.terminal(['setup','gmail'],env);gmail.expect('Esc done')
        self.assertEqual(self.pointed(gmail),'Mailbox address')
        gmail.send(b'\r');gmail.expect('Type the address:')
        self.assertNotIn('Enter opens',plain(gmail.capture))
        # A secret pasted here by mistake stays masked, whatever is typed or deleted around it.
        wrong='abcd efgh ijkl mnop SYNTHETIC'
        for before, after in ((b'',b''),(b'',b'\x7f'),(b'',b'x'),(b'x',b'')):
            mark=len(gmail.capture)
            gmail.send(b'\x15'+before);gmail.paste(wrong);gmail.send(after)
            gmail.after(mark,'Type the address: abc•••••TIC' if not before+after else 'Type the address: ••••')
            gmail.settle(.15)
        self.assertNotIn(b'efgh',gmail.capture)
        gmail.send(b'\x15')
        for char in 'demo@example.com':
            gmail.send(char.encode())
        gmail.after(0,'Type the address: demo@example.com')
        gmail.after(0,APPEND+"'GMAIL_USER=sealed(demo@example.com)' >>")
        mark=len(gmail.capture)
        gmail.send(b'\r');gmail.after(mark,'Saved GMAIL_USER=sealed(demo@example.com)');gmail.after(mark,'Esc done')
        self.assertEqual(self.pointed(gmail),'App password')
        # Google shows app passwords in groups of four; the spaces are not part of it.
        gmail.send(b'\r');gmail.expect('Create a Gmail app password')
        mark=len(gmail.capture)
        gmail.paste('  \xa0 ');gmail.after(mark,"Can't save this yet: there is nothing in it to save.")
        gmail.after(mark,'Ctrl-U clears')
        gmail.send(b'\r');gmail.wait(lambda: b'\a' in gmail.capture[mark:])
        self.assertFalse(record.exists(),'Enter must not open the page while the field holds text')
        gmail.paste('abcd efgh\xa0ijkl mnop')
        gmail.after(mark,APPEND+"'GMAIL_APP_PASSWORD=sealed(ab•••••op)' >>")
        mark=len(gmail.capture)
        gmail.send(b'\r');gmail.after(mark,'Saved GMAIL_APP_PASSWORD=sealed(ab•••••op)');gmail.after(mark,'Esc done')
        self.assertEqual(self.pointed(gmail),'Done')
        gmail.send(b'\r');gmail.done()
        self.assertEqual(values(self.file)['GMAIL_APP_PASSWORD'],'abcdefghijklmnop')
        # One copy from Higgsfield holds ID:SECRET; each entry keeps its own half.
        pair='11111111-2222-3333-4444-555555555555:hfsecret_DEMO_ONLY:abcdefghij0123456789'
        both=self.terminal(['setup','higgsfield'],env);both.expect('Esc done')
        for name, shown in (('HIGGSFIELD_API_KEY_ID','sealed(111•••••555)'),('HIGGSFIELD_API_KEY_SECRET','sealed(hfs•••••789)')):
            mark=len(both.capture)
            both.send(b'\r');both.after(mark,'Paste your')
            both.paste(pair);both.after(mark,name+'='+shown)
            both.send(b'\r');both.after(mark,'Saved '+name+'='+shown);both.after(mark,'Esc done')
        self.assertNotIn('Enter opens',plain(both.capture[mark:]))  # The secret has no page of its own.
        both.send(b'\x1b');both.done()
        saved=values(self.file)
        self.assertEqual((saved['HIGGSFIELD_API_KEY_ID'],saved['HIGGSFIELD_API_KEY_SECRET']),tuple(pair.split(':',1)))
        self.assertNotIn(b'hfsecret_DEMO',both.capture)
        # The same rules follow a bundled key entered by name.
        byname=self.terminal(['set','HIGGSFIELD_API_KEY_ID']);byname.expect('Paste your key ID:')
        byname.paste('99999999-2222-3333-4444-555555555000:other_DEMO_ONLY_secret')
        byname.after(0,"HIGGSFIELD_API_KEY_ID=sealed(999•••••000)")
        byname.send(b'\r');byname.expect('Saved HIGGSFIELD_API_KEY_ID');byname.done()
        self.assertEqual(values(self.file)['HIGGSFIELD_API_KEY_ID'],'99999999-2222-3333-4444-555555555000')

    def test_done_and_back_rows_and_where_the_pointer_goes(self):
        self.init()
        names=[key['name'] for provider in self.providers.values() for key in provider['key']]
        for name in names:
            if name not in ('GH_TOKEN','ZERNIO_API_KEY','STRIPE_TEST_PUBLISHABLE_KEY','STRIPE_LIVE_SECRET_KEY','STRIPE_LIVE_PUBLISHABLE_KEY'):
                self.seed(name)
        terminal=self.terminal(['setup']);terminal.expect(MENU)
        self.assertTrue(self.pointed(terminal).startswith('GitHub'))  # The first provider lacking a key.
        terminal.send(b'\x1b[B\x1b[B\x1b[B\x1b[B')
        self.assertRegex(self.pointed(terminal),r'^Stripe +1 of 4 saved +payments')
        # A provider with several keys opens its own list, which ends in Back.
        mark=len(terminal.capture)
        terminal.send(b'\r');terminal.after(mark,'Esc back');terminal.settle(.15)
        rows=[row for row in Screen(100).feed(terminal.capture).lines() if row]
        self.assertEqual((rows[-7],rows[-2].strip()),('Stripe','Back'))
        self.assertEqual(self.pointed(terminal),'Test publishable key')
        mark=len(terminal.capture)
        terminal.send(b'\x1b[A\x1b[A\r');terminal.after(mark,MENU)   # Up twice wraps to Back; Enter returns.
        self.assertTrue(self.pointed(terminal).startswith('Stripe'))
        # Saving the last missing provider further down wraps to the first one still missing.
        terminal.send(b'z')
        self.assertTrue(self.pointed(terminal).startswith('Zernio'))
        terminal.send(b'\r');terminal.expect('Create a Zernio API key')
        terminal.paste('zernio_DEMO_ONLY_value_123456')
        mark=len(terminal.capture)
        terminal.send(b'\r');terminal.after(mark,'Saved ZERNIO_API_KEY');terminal.after(mark,MENU)
        self.assertTrue(self.pointed(terminal).startswith('GitHub'))
        # Esc in the name prompt returns to the list.
        terminal.send(b'a\r');terminal.expect('Type a name for the key')
        mark=len(terminal.capture)
        terminal.send(b'acme-key\r');terminal.after(mark,'Use letters, digits and _ only')
        mark=len(terminal.capture)
        terminal.send(b'\x1b');terminal.after(mark,MENU)
        self.assertIsNone(terminal.process.poll())
        self.assertTrue(self.pointed(terminal).startswith('Another key'))
        # A bundled key typed by name keeps its paste rule.
        mark=len(terminal.capture)
        terminal.send(b'\r');terminal.after(mark,'Type a name for the key')  # Keys sent ahead of a screen are dropped.
        terminal.send(b'GMAIL_APP_PASSWORD\r');terminal.expect('Paste your password:')
        terminal.paste('wxyz efgh ijkl mnop')
        mark=len(terminal.capture)
        terminal.send(b'\r');terminal.after(mark,'Saved GMAIL_APP_PASSWORD=sealed(wx•••••op)');terminal.after(mark,MENU)
        self.assertEqual(values(self.file)['GMAIL_APP_PASSWORD'],'wxyzefghijklmnop')
        terminal.send(b'\x03');terminal.done(130)
        # With every key saved the pointer rests on Done, and Enter there ends setup.
        for name in names:
            self.seed(name)
        full=self.terminal(['setup']);full.expect(MENU)
        self.assertEqual(self.pointed(full),'Done')
        full.send(b'\r');full.expect('Done. Your keys are in ~/.godmode/.env.godmode');full.done()
        # No nano: the list says so and carries on.
        bare=self.root/'no-nano';bare.mkdir()
        without=self.terminal(['setup'],dict(self.env,PATH=str(bare)));without.expect(MENU)
        mark=len(without.capture)
        without.send(b'e\r')
        without.wait(lambda: MENU in plain(without.capture[mark:]).partition('nano was not found')[2])  # The list is back.
        without.send(b'\x1b');without.expect('Done.');without.done()

    def test_every_key_screen_shows_its_goal_link_steps_and_note(self):
        cli=load_cli()
        self.home.mkdir(mode=0o700)
        store=cli.Store(str(self.home));store.initialize()
        marked=lambda text, role='accent': '<%s>%s</>' % (role, text)
        with patch.object(cli,'style',marked), patch.object(cli,'glyph',lambda fancy, plain: fancy):
            for provider in self.providers.values():
                for key in provider['key']:
                    for width in (40,50,60,80,100):
                        with self.subTest(key=key['name'],width=width):
                            prompt=cli.KeyPrompt(store,key,provider,back=True)
                            rows=prompt.guide(width)
                            text=re.sub(r'<\w+>|</>','','\n'.join(rows))
                            flat=' '.join(text.split())
                            position=0
                            for step in key['steps']:
                                found=flat.find(step.replace('**',''),position)
                                self.assertGreaterEqual(found,0,step)
                                position=found+1
                            self.assertIn(key.get('note',''),flat)
                            self.assertTrue(flat.startswith(key['goal']))
                            page=key['console'] if 'console' in key else provider['console']
                            if page and len(key['goal'])+2+len(page)<width:
                                self.assertEqual(text.splitlines()[0],key['goal']+': '+page)
                            self.assertEqual(page is not None and len(page)<width, bool(page) and page in text)
                            # Exactly the labels marked ** in the data are bold, in order.
                            labels=[label for step in key['steps'] for label in step.split('**')[1::2]]
                            steps=[row for row in rows if row.startswith(('<accent>','  '))]  # Not the goal rows.
                            bold=[span for row in steps for span in re.findall(r'<title>(.*?)</>',row)]
                            if width>=80:
                                self.assertEqual(bold,labels)
                            else:  # A label may wrap onto the next row; each part stays bold.
                                self.assertEqual(''.join(bold).replace(' ',''),''.join(labels).replace(' ',''))

    def legacy(self, text):
        """A plain-text file in the old ~/.config/godmode home, as hand-written setups have it."""
        old=self.root/'.config'/'godmode';old.mkdir(parents=True,exist_ok=True,mode=0o700);(self.root/'.config').chmod(0o700)
        (old/'.env.godmode').write_text(text);(old/'.env.godmode').chmod(0o600)
        return old/'.env.godmode'

    def godmode(self, *args, **options):
        """The installed script with this test's HOME and no explicit home."""
        return subprocess.run([sys.executable,str(REPO/'target/godmode'),*args],env=self.env,capture_output=True,text=True,**options)

    def test_list_run_help_and_migrate_never_print_values(self):
        old=self.legacy('GH_TOKEN=ghp_SYNTHETIC_value_000000000001 \nGMAIL_USER=demo@example.com\nEMPTY=\n')
        self.assertEqual(self.godmode('list').stdout.split(),['GH_TOKEN','GMAIL_USER'])
        self.assertIn('Its values are plain text. Run godmode migrate',self.godmode('help').stdout)
        moved=self.godmode('migrate')
        self.assertEqual(moved.returncode,0)
        self.assertIn('Moved 2 keys to ~/.godmode and sealed them.',moved.stdout)
        for text in (self.file.read_text(),old.read_text()):
            self.assertNotIn('SYNTHETIC',text);self.assertNotIn('demo@example.com',text)
        self.assertIn('godmode run NAME -- command',old.read_text())  # The old file says where the keys went.
        self.assertEqual(self.godmode('list').stdout.split(),['GH_TOKEN','GMAIL_USER'])
        guide=self.godmode('help').stdout
        self.assertIn('one sealed file',guide);self.assertIn('godmode run GH_TOKEN -- gh repo list',guide)
        # run hands the keys to the command, and only the ones named; the stray space is gone.
        shown=self.godmode('run','GH_TOKEN','--','/bin/sh','-c','printf "%s|%s|%s" "${#GH_TOKEN}" "$GH_TOKEN" "${GMAIL_USER-unset}" | shasum -a 256')
        token='ghp_SYNTHETIC_value_000000000001'
        expected=subprocess.run(['shasum','-a','256'],input='%d|%s|unset' % (len(token),token),capture_output=True,text=True).stdout
        self.assertEqual(shown.stdout,expected)
        self.assertEqual(self.godmode('run','GH_TOKEN','--','/bin/sh','-c','exit 7').returncode,7)
        self.assertEqual(self.godmode('run','GH_TOKEN','GMAIL_USER','--','/bin/sh','-c','echo "$GODMODE_KEYS"').stdout,'GH_TOKEN,GMAIL_USER\n')
        for args, message in ((('run','GH_TOKEN','MISSING','--','true'),'MISSING is not saved'),
                              (('run','EMPTY','--','true'),'EMPTY is not saved'),
                              (('run','GH_TOKEN','--','no-such-program-SYNTHETIC'),'Cannot run'),
                              (('run','GH_TOKEN'),'Use: godmode run NAME... -- command'),
                              (('run','--','true'),'Use: godmode run')):
            with self.subTest(args=args):
                result=self.godmode(*args)
                self.assertEqual(result.returncode,2)
                self.assertIn(message,result.stderr)
                self.assertNotIn('SYNTHETIC_value',result.stdout+result.stderr)
        # --home and --config-dir work before run in every spelling.
        for prefix in (['--home',str(self.home)],['--config-dir',str(self.home)],['--home='+str(self.home)],['--config-dir='+str(self.home)]):
            spelled=self.godmode(*prefix,'run','GH_TOKEN','--','/bin/sh','-c','echo "$GODMODE_KEYS"')
            self.assertEqual((spelled.returncode,spelled.stdout),(0,'GH_TOKEN\n'),spelled.stderr)
        nothing=self.godmode('migrate')
        self.assertEqual((nothing.returncode,nothing.stdout),(0,'Nothing to seal: no plain-text keys in ~/.godmode/.env.godmode.\n'))
        # A damaged seal is refused by name, without guessing.
        (self.home/'seal.key').write_text('00'*32+'\n')
        self.assertIn("does not match this computer's seal.key",self.godmode('run','GH_TOKEN','--','true').stderr)

    def test_setup_offers_to_move_plain_text_keys_and_seal_them(self):
        old=self.legacy('GH_TOKEN=ghp_SYNTHETIC_value_000000000002\nCLOUDFLARE_API_TOKEN=cf_SYNTHETIC_value_00000000\n')
        command=[sys.executable,str(REPO/'target/godmode')]
        keep=Terminal(command,self.env,cols=100,rows=36);self.sessions.append(keep)
        keep.expect('Found 2 keys stored as plain text in ~/.config/godmode/.env.godmode.')
        self.assertEqual(self.pointed(keep),'Move them to ~/.godmode and seal them')
        mark=len(keep.capture)
        keep.send(b'\x1b');keep.after(mark,MENU)  # Esc keeps them; setup goes on as before.
        self.assertRegex('\n'.join(Screen(100).feed(keep.capture).lines()),r'GitHub +✓ saved')
        keep.send(b'\x03');keep.done(130)
        self.assertIn('SYNTHETIC',old.read_text())
        self.assertFalse(self.file.exists())
        move=Terminal(command,self.env,cols=100,rows=36);self.sessions.append(move)
        move.expect('stored as plain text');mark=len(move.capture)
        move.send(b'\r');move.after(mark,'Moved 2 keys to ~/.godmode and sealed them.')
        move.after(mark,MENU)
        self.assertTrue(self.pointed(move).startswith('Vercel'))  # The moved keys count as saved.
        move.send(b'\x1b');move.expect('Done. Your keys are in ~/.godmode/.env.godmode');move.done()
        self.assertNotIn('SYNTHETIC',old.read_text()+self.file.read_text())
        self.assertNotIn(b'SYNTHETIC',move.capture+keep.capture)
        self.assertEqual(values(self.file)['GH_TOKEN'],'ghp_SYNTHETIC_value_000000000002')
        # Sealed now, so the offer does not come back.
        again=Terminal(command,self.env,cols=100,rows=36);self.sessions.append(again)
        again.expect(MENU);self.assertNotIn('plain text',plain(again.capture))
        again.send(b'\x03');again.done(130)

    def test_migrate_finishes_an_interrupted_move_and_reports_kept_comments(self):
        old=self.legacy('# rotated: see vault\nGH_TOKEN=ghp_SYNTHETIC_value_000000000003\nNOTION_API_KEY=ntn_SYNTHETIC_value_0003\n')
        self.seed('NOTION_API_KEY','ntn_SYNTHETIC_value_0003')  # ~/.godmode already holds one of them.
        moved=self.godmode('migrate')
        self.assertEqual(moved.returncode,0,moved.stderr)
        self.assertIn('Moved 2 keys to ~/.godmode and sealed them.',moved.stdout)
        self.assertIn('1 comment line in ~/.config/godmode/.env.godmode is still plain text.',moved.stdout)
        self.assertTrue(old.read_text().endswith('# rotated: see vault\n'))
        self.assertEqual(self.godmode('list').stdout.split(),['GH_TOKEN','NOTION_API_KEY'])
        self.assertNotIn('SYNTHETIC',old.read_text()+self.file.read_text()+moved.stdout+moved.stderr)
        # A file that cannot be carried exactly is refused by line number, and nothing changes.
        old=self.legacy('GMAIL_USER=me@example.comGMAIL_APP_PASSWORD=SYNTHETICpass\n')
        refused=self.godmode('migrate')
        self.assertEqual(refused.returncode,2)
        self.assertIn('line 1 (GMAIL_USER) also holds GMAIL_APP_PASSWORD=',refused.stderr)
        self.assertNotIn('SYNTHETIC',refused.stdout+refused.stderr)
        self.assertIn('SYNTHETICpass',old.read_text())
        # A file whose every key line has a problem is still found, and the problem is named.
        old=self.legacy('GMAIL_USER=me@example.com # app password: SYNTHETIC\n')
        refused=self.godmode('migrate')
        self.assertEqual(refused.returncode,2)
        self.assertIn('line 1 (GMAIL_USER) has a comment after its value',refused.stderr)
        # Moving out of a rules checkout whose scripts still read this file is refused until they are updated.
        self.legacy('LATE_TOKEN=late_SYNTHETIC_value_0004\n')
        scripts=old.parent/'scripts';scripts.mkdir();(scripts/'git_credential.py').write_text('# reads the file\n')
        stale=self.godmode('migrate')
        self.assertEqual(stale.returncode,2)
        self.assertIn('Update the Godmode rules in ~/.config/godmode before moving keys',stale.stderr)
        (scripts/'godmode_keys.py').write_text('# reads keys through godmode\n')
        one=self.godmode('migrate')
        self.assertIn('Moved 1 key to ~/.godmode and sealed it.',one.stdout)

    def test_help_always_prints_the_guide(self):
        fresh=self.godmode('help')
        self.assertEqual(fresh.returncode,0)
        self.assertIn('Reading the file shows names, never keys.',fresh.stdout)  # The first file will be sealed.
        self.seed('GH_TOKEN')
        with open(self.file,'a') as extra:
            extra.write("BROKEN='SYNTHETIC unterminated\n")
        broken=self.godmode('help')
        self.assertEqual(broken.returncode,0)
        self.assertIn('The file cannot be read as it is; fix it with godmode edit.',broken.stdout)
        self.assertIn('never print one',broken.stdout)
        self.file.write_text(self.file.read_text().replace("BROKEN='SYNTHETIC unterminated\n","EXTRA=plain_SYNTHETIC # note\n"))
        loose=self.godmode('help')
        self.assertIn('1 line in it is still plain text; godmode migrate seals them or names what to delete.',loose.stdout)
        named=self.godmode('migrate')
        self.assertEqual(named.returncode,2)
        self.assertIn('(EXTRA) has a comment after its value',named.stderr)
        # list names a broken key on stderr and fails, so a check that relies on it cannot pass silently.
        self.file.write_text(self.file.read_text().replace('EXTRA=plain_SYNTHETIC # note\n','GH_TOKEN=rotated_SYNTHETIC\n'))
        listed=self.godmode('list')
        self.assertEqual((listed.returncode,listed.stdout),(1,''))
        self.assertIn('GH_TOKEN is saved more than once or unreadable; godmode migrate names the lines.',listed.stderr)
        self.assertNotIn('SYNTHETIC',loose.stdout+named.stdout+named.stderr)

    def test_google_key_check_also_applies_to_stdin(self):
        for value, message in ((json.dumps({'installed':{'client_id':'x'}}),'Not saved: this is an OAuth client file,'),
                               ('{"seeded":"DEMO_ONLY"}','Not saved: a service account key file says')):
            result=subprocess.run(self.command+['set','GOOGLE_ADS_SERVICE_ACCOUNT_JSON','--stdin'],env=self.env,input=value,capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertIn(message,result.stderr)
        self.assertFalse(self.file.exists())
        saved=subprocess.run(self.command+['set','GOOGLE_ADS_SERVICE_ACCOUNT_JSON','--stdin'],env=self.env,input=json.dumps(SERVICE_ACCOUNT),capture_output=True,text=True)
        self.assertEqual(saved.returncode,0,saved.stderr)
        self.assertIn('saved. Service account agent@demo-project.iam.gserviceaccount.com in project demo-project.',saved.stdout)
        self.assertNotIn('SYNTHETICKEYMATERIAL',saved.stdout+saved.stderr)
        self.assertEqual(json.loads(values(self.file)['GOOGLE_ADS_SERVICE_ACCOUNT_JSON']),SERVICE_ACCOUNT)
        # Other keys ending in _JSON keep accepting any JSON object.
        other=subprocess.run(self.command+['set','CUSTOM_JSON','--stdin'],env=self.env,input='{"a":1}',capture_output=True,text=True)
        self.assertEqual(other.returncode,0,other.stderr)

    def test_google_key_files_are_checked_and_can_be_dragged_in(self):
        self.init()
        good=SERVICE_ACCOUNT
        folder=self.root/'Down loads';folder.mkdir()
        dropped=folder/'demo key.json';dropped.write_text(json.dumps(good,indent=2))
        cases=[({'installed':{'client_id':'x'}},'this is an OAuth client file, not a service account key.'),
               ({'bindings':[{'role':'roles/viewer','members':[]}]},'this is a permissions policy, not a credential.'),
               ({'type':'authorized_user','client_id':'x'},'this is a personal sign-in file, not a service account key.'),
               (dict(good,type='other'),'a service account key file says "type": "service_account".'),
               ({k:v for k,v in good.items() if k!='client_email'},'the key file has no client_email.'),
               (dict(good,private_key='SYNTHETIC not pem'),'its private_key is not a PEM private key.'),
               (dict(good,client_email='me@gmail.com'),'its client_email is not a service account address.')]
        terminal=self.terminal(['setup','google']);terminal.expect('Esc done')
        terminal.send(b'\r');terminal.expect('Drag or paste the key file:')
        for bad, message in cases:
            with self.subTest(message=message):
                mark=len(terminal.capture)
                terminal.send(b'\x15');terminal.paste(json.dumps(bad));terminal.after(mark,"Can't save this yet: "+message)
        for path in ('/no/such/file.json','~zz_no_such_user_SYNTHETIC/key.json'):  # ~user that does not exist.
            mark=len(terminal.capture)
            terminal.send(b'\x15');terminal.paste(path)
            terminal.after(mark,"Can't save this yet: drag the key file here, or paste what is in it.")
        # Terminals type a dropped file's path with its spaces escaped.
        mark=len(terminal.capture)
        terminal.send(b'\x15');terminal.paste(str(dropped).replace(' ','\\ ')+' ')
        terminal.after(mark,"Read from ~/'Down loads/demo key.json'.")
        terminal.after(mark,'Service account agent@demo-project.iam.gserviceaccount.com in project demo-project.')
        mark=len(terminal.capture)
        terminal.send(b'\r');terminal.after(mark,'Saved GOOGLE_ADS_SERVICE_ACCOUNT_JSON=sealed(')
        terminal.after(mark,'Remove the imported file when no tool needs it: it may contain credentials.')
        terminal.after(mark,'Esc done')  # Back in Google's list of keys.
        terminal.send(b'\x03');terminal.done(130)
        self.assertEqual(json.loads(values(self.file)['GOOGLE_ADS_SERVICE_ACCOUNT_JSON']),good)
        self.assertNotIn(b'SYNTHETICKEYMATERIAL',terminal.capture)
        self.assertTrue(dropped.exists())  # Godmode reads the file; deleting it is left to you.

    def test_generic_oauth_json_import_replacement_and_delivery(self):
        self.init()
        name='EXAMPLE_OAUTH_JSON'
        grant={'type':'authorized_user','refresh_token':'SYNTHETIC_OLD_GRANT',
               'client_id':'demo.apps.googleusercontent.com','client_secret':'SYNTHETIC_CLIENT'}
        source=self.root/'OAuth grant.json';source.write_text(json.dumps(grant,indent=2))
        terminal=self.terminal(['set',name]);terminal.expect('Drag or paste the JSON file:')
        terminal.paste(shlex.quote(str(source)))
        terminal.expect('Read from ')
        terminal.send(b'\r');terminal.expect('Saved '+name);terminal.done()
        self.assertEqual(json.loads(values(self.file)[name]),grant)
        for secret in ('SYNTHETIC_OLD_GRANT','SYNTHETIC_CLIENT'):
            self.assertNotIn(secret.encode(),terminal.capture)
        replacement=dict(grant,refresh_token='SYNTHETIC_NEW_GRANT')
        saved=subprocess.run(self.command+['set',name,'--stdin'],env=self.env,
                             input=json.dumps(replacement,indent=2),capture_output=True,text=True)
        self.assertEqual(saved.returncode,0,saved.stderr)
        self.assertNotIn('SYNTHETIC_',saved.stdout+saved.stderr)
        verify='import json,os; assert json.loads(os.environ["EXAMPLE_OAUTH_JSON"])["refresh_token"] == "SYNTHETIC_NEW_GRANT"; print("verified")'
        used=subprocess.run(self.command+['run',name,'--',sys.executable,'-c',verify],
                            env=self.env,capture_output=True,text=True)
        self.assertEqual((used.returncode,used.stdout),(0,'verified\n'),used.stderr)
        self.assertTrue(source.exists())

    def test_import_saves_the_validated_snapshot_even_if_source_changes(self):
        cli=load_cli()
        self.init()
        source=self.root/'changing-key.json';source.write_text(json.dumps(SERVICE_ACCOUNT))
        def submit(prompt):
            text=shlex.quote(str(source))
            prompt.render(text,100)
            source.write_text('{"installed":{"client_id":"SYNTHETIC_WRONG_TYPE"}}')
            self.assertTrue(prompt.enter(text))
            source.write_text('{"type":"authorized_user","refresh_token":"SYNTHETIC_WRONG_GRANT"}')
            prompt.final(text,100,True,True)
            return text
        with patch.object(cli,'read_secret',submit), patch.object(cli,'line'):
            self.assertTrue(cli.populate(cli.Store(self.home),cli.named('GOOGLE_ADS_SERVICE_ACCOUNT_JSON')))
        self.assertEqual(json.loads(values(self.file)['GOOGLE_ADS_SERVICE_ACCOUNT_JSON']),SERVICE_ACCOUNT)

    def test_service_account_display_metadata_cannot_inject_terminal_controls(self):
        cli=load_cli()
        self.init()
        before=self.file.read_bytes()
        for field in ('project_id','client_email'):
            bad=dict(SERVICE_ACCOUNT,**{field:'\x1b[2JSYNTHETIC_CONTROL\n'+SERVICE_ACCOUNT[field]})
            raw=json.dumps(bad)
            prompt=cli.KeyPrompt(cli.Store(self.home),cli.named('GOOGLE_ADS_SERVICE_ACCOUNT_JSON'))
            self.assertFalse(prompt.enter(raw))
            rendered='\n'.join(prompt.render(raw,100))
            self.assertIn('contains control characters',rendered)
            self.assertNotIn('SYNTHETIC_CONTROL',rendered)
            result=subprocess.run(self.command+['set','GOOGLE_ADS_SERVICE_ACCOUNT_JSON','--stdin'],
                                  env=self.env,input=raw,capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertIn('contains control characters',result.stderr)
            self.assertNotIn('SYNTHETIC_CONTROL',result.stdout+result.stderr)
            self.assertEqual(self.file.read_bytes(),before)

    def test_ascii_terminal_uses_plain_glyphs(self):
        self.init()
        env=dict(self.env,PYTHONIOENCODING='ascii',LC_ALL='C')
        menu=self.terminal(['setup'],env);menu.expect('Up/Down move | Enter open | Esc done')
        menu.settle(.15)
        self.assertEqual(sum(row.startswith('> GitHub') for row in Screen(100).feed(menu.capture).lines()),1)
        menu.send(b'\x03');menu.done(130)
        terminal=self.terminal(['setup','github'],env)
        terminal.expect('GODMODE');terminal.expect('Paste your token:')
        terminal.paste('github_pat_DEMO_ONLY_ascii_0042')
        terminal.wait(lambda: "| "+APPEND+"'GH_TOKEN=sealed(git*****042)' >> ~/.godmode/.env.godmode" in plain(terminal.capture))
        self.assertIn('Enter saves | Esc cancels',plain(terminal.capture))
        terminal.send(b'\r');terminal.expect('Saved GH_TOKEN');terminal.done()
        self.assertNotIn(b'codec',terminal.capture)
        self.assertEqual(values(self.file)['GH_TOKEN'],'github_pat_DEMO_ONLY_ascii_0042')

    def test_preview_command_has_the_same_effect_as_saving(self):
        """Run each preview with the real value under /bin/sh and compare it with Store.set."""
        cli=load_cli()
        sys.path.insert(0,str(REPO/'lib'))
        from godmode_store import STORE_HEADER as sealed
        # '' is left out: an empty file is a new one, and setup writes its sealed header before any prompt.
        fixtures=[sealed, sealed+'A=1\n', sealed+'KEY=sealed:v1:AAAA\n', sealed+'A=1\nexport KEY=x\nKEY=y\n',
                  'A=1\n', 'A=1', '# note\nA=1\r\nB=2\r\n', 'KEY=old\n', 'A=1\nKEY=old', 'A=1\nKEY=old\r\nB=2\n',
                  '# KEY=commented\nKEYX=1\nXKEY=2\n\texport  KEY =tab\n',
                  'export KEY=old\nB=2\n', '  KEY = old  # comment\n', 'KEY=a\nB=2\nexport KEY=b\nKEY=c\n',
                  "KEY=\nOTHER='x # y'\n"]
        values_=['plain_token_DEMO_123', 'two words', "quote'inside", 'back\\slash $dollar `tick` & a/b',
                 'ünïcode-DEMO', "'wrapped in quotes'", '{"private_key": "-----BEGIN\\nDEMO\\n-----END\\n"}', 'trailing\\c']
        self.home.mkdir(mode=0o700)
        store=cli.Store(str(self.home))
        copy=self.root/'copy.env'
        checked=plain_runs=0
        for fixture in fixtures:
            for value in values_:
                with self.subTest(fixture=fixture, value=value):
                    self.file.write_text(fixture);self.file.chmod(0o600)
                    if not fixture.startswith(sealed) and (self.home/'seal.key').exists():
                        (self.home/'seal.key').unlink()  # A plain file stays plain only without a seal.key.
                    plan=store.plan('KEY')
                    if plan['kept_cr']:
                        continue  # Disclosed in a note: sed would not keep the CR.
                    copy.write_bytes(self.file.read_bytes())
                    store.set('KEY',value)
                    written=shlex.quote(cli.normalize(value,'KEY'))
                    if plan['sealed']:  # The preview's sealed(…) stands for the token Godmode writes.
                        written=[line for line in self.file.read_text().splitlines() if line.startswith('KEY=')][0][4:]
                        self.assertEqual(store.values(['KEY'])['KEY'],cli.normalize(value,'KEY'))
                    words=cli.save_command('KEY',written,plan,shlex.quote(str(copy)))
                    # The kind of command never depends on the value, so it reveals nothing hidden.
                    masked=cli.save_command('KEY',"'•••••'",plan,shlex.quote(str(copy)))
                    self.assertEqual([w for w in words if 'KEY=' not in w],[w for w in masked if 'KEY=' not in w])
                    subprocess.run(['/bin/sh','-c',' '.join(words)],check=True,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
                    self.assertEqual(copy.read_bytes(),self.file.read_bytes(),' '.join(words))
                    checked+=1
                    plain_runs+=not plan['sealed']
        self.assertGreater(checked,50)
        self.assertGreater(plain_runs,40)  # Plain fixtures were saved as plain text, byte for byte.

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
        self.assertEqual(cli.prompt_label(self.providers['gmail']['key'][0]),'Type the address:')
        prompt=object.__new__(cli.KeyPrompt);prompt.secret=True
        mask_of=lambda value: cli.mask(value,True)
        with patch.object(cli,'mask',lambda value,reveal=True: 'xx•••••yy' if reveal else '•'*len(value)):
            self.assertEqual(prompt.shown('plain_value',True),'xx•••••yy')
            self.assertEqual(prompt.shown('needs quotes',True),"'xx•••••yy'")
            self.assertEqual(prompt.shown('abc',False),"'•••'")
        prompt.secret=False
        self.assertEqual(prompt.shown('me@example.com',False),'me@example.com')
        self.assertEqual(prompt.shown('me@example.com',True),mask_of('me@example.com'))


if __name__=='__main__':
    unittest.main()
