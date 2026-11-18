import os,sys,json,hashlib,subprocess,importlib.util
from pathlib import Path
out=Path(__file__).resolve().parent
repo=Path('/Users/michael/conductor/repos/godmode-cli')
spec=importlib.util.spec_from_file_location('record_v019',repo/'scripts/record-v019.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
receipt=json.loads((out/'environment.json').read_text());root=Path(receipt['home'])
env={'HOME':str(root),'GODMODE_HOME':str(root/'.godmode'),'PATH':'/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin','TERM':'xterm-256color','GODMODE_NO_MOTION':'1','CODEX_HOME':str(root/'.codex'),'COPILOT_HOME':str(root/'.copilot')}
checks=[]
for cols,rows in [(40,18),(80,24)]:
 t=r.NATIVE.NativeTerminal([str(repo/'target/godmode-native'),'music'],env,cols=cols,rows=rows)
 rec=r.NATIVE.Recorder(t,cols,rows,r.NATIVE.DEMO.font_path(None),caption='Music Pack focused retake')
 rec.stream=r.CaptureStream(rec.screen)
 try:
  rec.wait_for('SETUP GUIDE'); t.send(b'?');rec.wait_for('PLAYER KEYS')
  pages=[]
  for i in range(8):
   t.send(b'\x1b[6~');t.settle(.15);rec.capture(1);s='\n'.join(rec.screen.display);pages.append(s)
   assert '…' not in s,s
   name=f'18-help-paged-{cols}-{i+1}'
   rec.frames[-1].save(out/(name+'.png'));(out/(name+'.txt')).write_text(s+'\n')
  all_pages='\n'.join(pages)
  assert 'JINGLES' in all_pages and 'No track library or synth setup' in all_pages
  t.send(b'\x1b[5~');t.settle(.2);rec.capture(1)
  assert 'PLAYER KEYS' in '\n'.join(rec.screen.display)
  t.send(b'\x1b');t.settle(.2);rec.wait_for('SETUP GUIDE')
  t.send(b'q');t.done(0)
  checks.append(f'{cols}x{rows}: help paging, back, q exit, termios ECHO/ICANON/ISIG restoration, bracketed-paste off and alternate-screen off passed')
 finally:t.close()
for words in [('music','stop'),('music','remove')]:
 p=subprocess.run([str(repo/'target/godmode-native'),*words],env=env,text=True,capture_output=True,timeout=15);assert p.returncode==0,(p.stdout,p.stderr)
 checks.append(' '.join(words)+': '+p.stdout.strip())
receipt['checks']=checks
receipt['binary_unchanged']=receipt['binary_sha256']==hashlib.sha256((repo/'target/godmode-native').read_bytes()).hexdigest()
receipt['pack_unchanged']=receipt['pack_sha256']==hashlib.sha256((repo/'target/godmode-music-pack').read_bytes()).hexdigest()
receipt['screens']=len(list(out.glob('*.png')))
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
