"""Actual PTY cells, real local synthesis, player muted; no desktop capture."""
import hashlib,importlib.util,json,os,select,subprocess,sys,tempfile,time
from pathlib import Path
repo=Path('/Users/michael/conductor/repos/godmode-cli'); binary=Path(sys.argv[1]).resolve()
out=Path(__file__).resolve().parent.parent/'final';out.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('record',repo/'scripts/record-v019.py'); record=importlib.util.module_from_spec(spec);spec.loader.exec_module(record)
font=record.NATIVE.DEMO.font_path(None)
pack=Path(sys.argv[2]).resolve()
songs='/Users/michael/Labs/darunias-joy-research/upstream/OoT-Custom-Sequences-1f08093f06aa81b20ef41d1f09af31451e61fde5/data/Music'
evidence={'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'pack_sha256':hashlib.sha256(pack.read_bytes()).hexdigest(),'method':__doc__,'screens':[]}
with tempfile.TemporaryDirectory(prefix='gm-shots-',dir='/private/tmp') as temp:
 root=Path(temp).resolve();env={'HOME':str(root),'PATH':os.environ['PATH'],'TERM':'xterm-256color','COLORTERM':'truecolor','COLORFGBG':'15;0','GODMODE_HOME':str(root/'.godmode')}
 def cli(*args):return subprocess.run([str(binary),'music',*args],env=env,capture_output=True,text=True,timeout=90,check=True)
 cli('install','--file',str(pack));cli('setup','--songs',songs)
 bridge=subprocess.Popen([str(binary),'music','__bridge'],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
 def rpc(action,**fields):
  bridge.stdin.write(json.dumps(dict(action=action,**fields))+'\n');bridge.stdin.flush()
  assert select.select([bridge.stdout],[],[],15)[0]
  r=json.loads(bridge.stdout.readline());assert r['ok'],r;return r['data']
 try:
  tracks=rpc('library')['tracks'];ids=[t['id'] for t in tracks if t['title'] in ('Corridors of Time','Secret of the Forest') and t['collection']=='Chrono Trigger']
  assert len(ids)==2
  rpc('enqueue',ids=ids);rpc('volume',value=0);rpc('repeat',value='all');rpc('play',ids=ids,index=0,seconds=8)
  deadline=time.monotonic()+20
  while time.monotonic()<deadline:
   status=rpc('status')
   if status['state']=='playing':break
   assert status['state']!='error',status['message'];time.sleep(.1)
  else:raise AssertionError('no playing state')
  sid=status['session_id'];roots=sorted({t['collection'].split('/')[0] for t in tracks},key=str.lower);index=roots.index('Chrono Trigger')+1
  for cols,rows in ((120,36),(80,24),(40,18)):
   term=record.NATIVE.NativeTerminal([str(binary),'music'],env,cols=cols,rows=rows)
   capture=record.NATIVE.Recorder(term,cols,rows,font,caption='GODMODE BEATZ · actual terminal output · player muted')
   capture.stream=record.CaptureStream(capture.screen)
   try:
    capture.wait_for('All tracks');term.send(b'\x1b[B'*index+b'\r');capture.wait_for('Library / Chrono Trigger');capture.capture(900)
    name=f'player-{cols}x{rows}';capture.frames[-1].save(out/(name+'.png'));(out/(name+'.txt')).write_text('\n'.join(capture.screen.display)+'\n');evidence['screens'].append(name+'.png')
    term.send(b'q');term.done(0)
    status=rpc('status');assert status['session_id']==sid and status['state'] in ('playing','preparing')
   finally:term.close()
  evidence['same_session_survived_three_ui_exits']=True
  evidence['state']=status['state'];evidence['clock_source']=status['clock_source']
 finally:
  rpc('stop');bridge.stdin.close();bridge.wait(timeout=5)
(out/'capture.json').write_text(json.dumps(evidence,indent=2)+'\n');print(json.dumps(evidence,indent=2))
