import sys,os,json,subprocess,importlib.util,time,hashlib,tempfile
from pathlib import Path
REPO=Path('/Users/michael/conductor/repos/godmode-cli')
OUT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('record_v019',REPO/'scripts/record-v019.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
root=Path(tempfile.mkdtemp(prefix='godmode-pack-fresh-review-',dir='/private/tmp')).resolve()
env={'HOME':str(root),'GODMODE_HOME':str(root/'.godmode'),'PATH':'/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin','TERM':'xterm-256color','COLORTERM':'truecolor','PYTHONUTF8':'1','GODMODE_NO_MOTION':'1','CODEX_HOME':str(root/'.codex'),'COPILOT_HOME':str(root/'.copilot')}
bin=REPO/'target/godmode-native'
font=r.NATIVE.DEMO.font_path(None)
t=None;rec=None
(OUT/'environment.json').write_text(json.dumps({'home':str(root),'binary_sha256':hashlib.sha256(bin.read_bytes()).hexdigest(),'pack_sha256':hashlib.sha256((REPO/'target/godmode-music-pack').read_bytes()).hexdigest()},indent=2))
def screen(name=None):
 t.settle(.3);rec.capture(1)
 text='\n'.join(rec.screen.display)
 if name:
  rec.frames[-1].save(OUT/(name+'.png'))
  (OUT/(name+'.txt')).write_text(text+'\n')
 return {'screen':text,'exit':t.process.poll()}
print(json.dumps({'ready':True,'home':str(root)}),flush=True)
for line in sys.stdin:
 try:
  c=json.loads(line);out={}
  with (OUT/'actions.jsonl').open('a') as log:log.write(json.dumps(c)+'\n')
  if c['op']=='launch':
   if t:t.close()
   cols=c.get('cols',80);rows=c.get('rows',24)
   t=r.NATIVE.NativeTerminal([str(bin),*c.get('args',['music'])],env,cols=cols,rows=rows)
   rec=r.NATIVE.Recorder(t,cols,rows,font,caption='Music Pack fresh review')
   rec.stream=r.CaptureStream(rec.screen)
   t.settle(c.get('wait',.7));out=screen(c.get('name'))
  elif c['op']=='key':
   t.send(c['key'].encode());t.settle(c.get('wait',.4));out=screen(c.get('name'))
  elif c['op']=='screen':out=screen(c.get('name'))
  elif c['op']=='command':
   p=subprocess.run([str(bin),*c['args']],env=env,text=True,capture_output=True,timeout=c.get('timeout',60))
   out={'stdout':p.stdout,'stderr':p.stderr,'exit':p.returncode}
  elif c['op']=='files':out={'files':sorted(str(x.relative_to(root)) for x in root.rglob('*'))}
  elif c['op']=='end':
   subprocess.run([str(bin),'music','stop'],env=env,capture_output=True,timeout=15)
   if t:t.close()
   print(json.dumps({'done':True}),flush=True);break
  with (OUT/'results.jsonl').open('a') as log:log.write(json.dumps(out)+'\n')
  print(json.dumps(out),flush=True)
 except Exception as e:print(json.dumps({'error':str(e)}),flush=True)
