import hashlib,json,os,select,subprocess,sys,tempfile,time
from pathlib import Path
repo=Path('/Users/michael/conductor/repos/godmode-cli')
binary=Path(sys.argv[1]).resolve()
out=Path(__file__).resolve().parent
pack=Path(sys.argv[2]).resolve()
report_pack_hash=hashlib.sha256(pack.read_bytes()).hexdigest()
songs='/Users/michael/Labs/darunias-joy-research/upstream/OoT-Custom-Sequences-1f08093f06aa81b20ef41d1f09af31451e61fde5/data/Music'
report={'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'pack_sha256':report_pack_hash,'checks':[],'audio':'Actual default audio device at player volume 0; no perceptual listening claim.'}
with tempfile.TemporaryDirectory(prefix='gm-real-',dir='/private/tmp') as temp:
 root=Path(temp).resolve(); env={'HOME':str(root),'PATH':os.environ['PATH'],'TERM':'xterm-256color','GODMODE_HOME':str(root/'.godmode')}
 def cli(*args):
  return subprocess.run([str(binary),'music',*args],env=env,capture_output=True,text=True,timeout=90,check=True)
 cli('install','--file',str(pack),'--sha256',report_pack_hash)
 jingle=subprocess.run([str(binary),'jingle','play','--volume','0','--json'],env=env,capture_output=True,text=True,timeout=15,check=True)
 report['jingle_before_setup']=json.loads(jingle.stdout)
 start=time.monotonic();cli('setup','--songs',songs);report['cold_setup_seconds']=round(time.monotonic()-start,3)
 report['checks'].append('jingle works before synth setup; included synth builds offline')
 bridge=subprocess.Popen([str(binary),'music','__bridge'],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
 def rpc(action,**fields):
  bridge.stdin.write(json.dumps(dict(action=action,**fields))+'\n');bridge.stdin.flush()
  if not select.select([bridge.stdout],[],[],15)[0]: raise AssertionError('bridge timed out '+action)
  response=json.loads(bridge.stdout.readline())
  assert response['ok'],response
  return response['data']
 def until(predicate,timeout=25):
  start=time.monotonic()
  while time.monotonic()-start<timeout:
   s=rpc('status')
   if predicate(s): return s
   if s['state']=='error': raise AssertionError(s['message'])
   time.sleep(.08)
  raise AssertionError('status deadline: '+json.dumps(s))
 try:
  library=rpc('library')['tracks']; report['library_count']=len(library)
  first=next(t for t in library if t['title'].startswith('Lost Woods'))
  second=next(t for t in library if 'Corridors of Time' in t['title'])
  ids=[first['id'],second['id']];report['tracks']=ids
  rpc('enqueue',ids=ids);rpc('volume',value=0)
  start=time.monotonic();rpc('play',ids=ids,index=0,seconds=8)
  s=until(lambda x:x['state']=='playing' and x['position']>.3)
  report['first_ready_seconds']=round(time.monotonic()-start,3)
  jingle=subprocess.run([str(binary),'jingle','play','success','--volume','0','--json'],env=env,capture_output=True,text=True,timeout=15,check=True)
  after_jingle=rpc('status');assert after_jingle['session_id']==s['session_id'] and after_jingle['queue']==s['queue'] and after_jingle['volume']==0
  report['checks'].append('jingle preserves active music session, queue, and volume')
  sid=s['session_id']
  assert s['clock_source'].startswith('mpv:');report['checks'].append('actual mpv audio clock established')
  rpc('pause');until(lambda x:x['state']=='paused');time.sleep(.3);paused=rpc('status');time.sleep(.5);hold=rpc('status')
  assert abs(hold['position']-paused['position'])<.15,(paused['position'],hold['position'])
  assert not hold['levels'];report['checks'].append('pause clock holds and spectrum clears')
  rpc('seek',seconds=3);s=until(lambda x:x['position']>=2.8)
  report['paused_seek_position']=s['position'];rpc('resume')
  s=until(lambda x:x['state']=='playing');assert s['volume']==0
  bridge.stdin.close();bridge.wait(timeout=5)
  status=json.loads(cli('status','--json').stdout);assert status['session_id']==sid and status['state']=='playing'
  report['checks'].append('bridge disconnect leaves same session playing')
  bridge=subprocess.Popen([str(binary),'music','__bridge'],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
  rpc('repeat',value='all');rpc('next');s=until(lambda x:x['index']==1 and x['state']=='playing')
  report['checks'].append('next synthesizes and starts second queued track')
  rpc('previous');s=until(lambda x:x['index']==0 and x['state']=='playing')
  rpc('repeat',value='one');rpc('seek',seconds=7.8)
  s=until(lambda x:x['index']==0 and x['state']=='playing' and x['position']<2)
  report['checks'].append('repeat one restarts current track at EOF')
  rpc('repeat',value='all');rpc('next');until(lambda x:x['index']==1 and x['state']=='playing');rpc('seek',seconds=7.8)
  until(lambda x:x['index']==0 and x['state']=='playing' and x['position']<2)
  report['checks'].append('repeat all wraps queue at EOF')
  rpc('shuffle',value=True);s=rpc('status');assert s['shuffle']
  rpc('stop');bridge.stdin.close();bridge.wait(timeout=5)
  deadline=time.monotonic()+5
  while time.monotonic()<deadline:
   try: cli('clear');break
   except subprocess.CalledProcessError:time.sleep(.1)
  else:raise AssertionError('stop did not release music lock')
  report['checks'].append('explicit stop releases synth/player/cache lock')
  assert json.loads(cli('status','--json').stdout)['state']=='stopped'
  cli('play',ids[0],'--seconds','8')
  deadline=time.monotonic()+15
  while time.monotonic()<deadline:
   live=json.loads(cli('status','--json').stdout)
   if live['state']=='playing':break
   assert live['state']!='error',live;time.sleep(.1)
  else:raise AssertionError('restarted playback did not begin')
  source_count=sum(1 for p in Path(songs).rglob('*.ootrs'))
  cli('remove');assert not (root/'.godmode/packs/music').exists();assert not (root/'.godmode/state/music').exists()
  assert sum(1 for p in Path(songs).rglob('*.ootrs'))==source_count
  cli('install');assert (root/'.godmode/packs/music/godmode-music').exists()
  cli('remove');report['checks'].append('remove stops live playback, clears pack/runtime/cache and preserves source tracks; reinstall uses remembered artifact')
 finally:
  subprocess.run([str(binary),'music','stop'],env=env,capture_output=True,timeout=10)
  if bridge.poll() is None:
   bridge.terminate();bridge.wait(timeout=5)
(out/'real-session.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
