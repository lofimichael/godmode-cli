#!/usr/bin/env python3
"""Private real-PTY measurements of the optional Music Pack; never play audio."""
from pathlib import Path
import codecs
import gzip
import hashlib
import importlib.util
import json
import os
import select
import statistics
import subprocess
import tempfile
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent
REPO = Path('/Users/michael/conductor/repos/godmode-cli')
BIN = REPO / 'target/godmode-native'
PACK = REPO / 'target/godmode-music-pack'
SONGS = Path('/Users/michael/Labs/darunias-joy-research/upstream/OoT-Custom-Sequences-1f08093f06aa81b20ef41d1f09af31451e61fde5/data/Music')
run = tempfile.TemporaryDirectory(prefix='run-', dir=FIX)
WORK = Path(run.name).resolve()
for name in ('home', 'godmode', 'codex', 'agents'):
    (WORK / name).mkdir(mode=0o700)
env = {'HOME': str(WORK / 'home'), 'GODMODE_HOME': str(WORK / 'godmode'),
       'CODEX_HOME': str(WORK / 'codex'), 'COPILOT_HOME': str(WORK / 'agents'),
       'PATH': '/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin', 'TERM': 'xterm-256color',
       'COLORTERM': 'truecolor', 'PYTHONUTF8': '1', 'COLORFGBG': '15;0'}
spec = importlib.util.spec_from_file_location('capture', REPO / 'scripts/record-v019.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def sizes(path):
    data = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
            'gzip_level_6_bytes': len(gzip.compress(data, compresslevel=6, mtime=0))}


def load_snapshot():
    rows = subprocess.check_output(['/bin/ps', '-Ao', 'pcpu=,comm='], text=True).splitlines()
    result = []
    for row in rows:
        fields = row.strip().split(None, 1)
        if len(fields) == 2:
            result.append({'cpu_percent': float(fields[0]), 'process': Path(fields[1]).name})
    return sorted(result, key=lambda item: item['cpu_percent'], reverse=True)[:12]


def disk_bytes(path):
    return sum(item.stat().st_size for item in path.rglob('*') if item.is_file()) if path.exists() else 0


def command(*args, timeout=20):
    return subprocess.run([str(BIN), *args], env=env, text=True, capture_output=True, timeout=timeout)


def timed_command(*args, timeout=20):
    start = time.monotonic_ns()
    result = command(*args, timeout=timeout)
    elapsed = (time.monotonic_ns() - start) / 1e9
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return {'seconds': round(elapsed, 4), 'stdout': result.stdout.strip(), 'stderr': result.stderr.strip()}


def summary(values):
    return {'count': len(values), 'min_ms': round(min(values), 3),
            'median_ms': round(statistics.median(values), 3), 'max_ms': round(max(values), 3),
            'samples_ms': [round(v, 3) for v in values]}


class Session:
    def __init__(self):
        self.t = r.NATIVE.NativeTerminal([str(BIN), 'music'], env, cols=80, rows=24)
        self.screen = r.NATIVE.NativeScreen(80, 24)
        self.stream = r.CaptureStream(self.screen)
        self.decoder = codecs.getincrementaldecoder('utf8')('replace')
        self.offset = 0

    def read(self, timeout=.005):
        self.t.drain(timeout)
        data = bytes(self.t.capture[self.offset:])
        self.offset = len(self.t.capture)
        self.stream.feed(self.decoder.decode(data))
        return '\n'.join(self.screen.display)

    def wait(self, predicate, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            text = self.read()
            if predicate(text):
                return text
            if self.t.process.poll() is not None:
                raise RuntimeError('UI exited before condition: ' + text)
        raise RuntimeError('UI condition timed out: ' + text)

    def action(self, data, predicate):
        start = time.monotonic_ns()
        self.t.send(data)
        text = self.wait(predicate)
        return (time.monotonic_ns() - start) / 1e6, text

    def close(self):
        try:
            if self.t.process.poll() is None:
                self.t.send(b'\x03')
                self.t.done()
        finally:
            self.t.close()


def cpu_time(pid):
    text = subprocess.check_output(['/bin/ps', '-p', str(pid), '-o', 'time='], text=True).strip()
    return sum(float(x) * 60 ** i for i, x in enumerate(reversed(text.split(':'))))


def descendants(pid):
    got = []
    proc = subprocess.run(['/usr/bin/pgrep', '-P', str(pid)], text=True, capture_output=True)
    for word in proc.stdout.split():
        got.append(int(word))
        got.extend(descendants(int(word)))
    return got


def request(payload):
    start = time.monotonic_ns()
    bridge.stdin.write((json.dumps(payload) + '\n').encode())
    bridge.stdin.flush()
    out = bytearray()
    deadline = time.monotonic() + 15
    while not out.endswith(b'\n'):
        if time.monotonic() > deadline:
            raise RuntimeError('bridge timeout')
        if select.select([bridge.stdout], [], [], .02)[0]:
            data = os.read(bridge.stdout.fileno(), 65536)
            if not data:
                raise RuntimeError('bridge exited')
            out.extend(data)
    transport = (time.monotonic_ns() - start) / 1e6
    parsed = json.loads(out)
    total = (time.monotonic_ns() - start) / 1e6
    if not parsed.get('ok'):
        raise RuntimeError(parsed.get('error'))
    return parsed['data'], len(out), transport, total


receipt = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'core': sizes(BIN), 'pack': sizes(PACK),
           'audio_started': False, 'terminal': {'columns': 80, 'rows': 24}, 'startup_ms': [],
           'navigation_ms': [], 'search_ms': [], 'checks': [], 'host_load_before': load_snapshot(),
           'method': 'Real PTY and incremental terminal reconstruction; monotonic elapsed times; private home; normal motion. '
                     'Local pack install and offline owned setup (including silent render validation), then queue-only UI. '
                     'No playback requests. Host caches were not flushed. Competing host load recorded; this is not an idle-host benchmark.'}
term = bridge = None
socket_dir = Path('/tmp').resolve() / ('godmode-music-' + str(os.geteuid())) / hashlib.sha256(os.fsencode(WORK / 'godmode/state/music')).hexdigest()[:24]
try:
    receipt['install'] = timed_command('music', 'install', '--file', str(PACK), '--sha256', receipt['pack']['sha256'])
    print('install', receipt['install']['seconds'], flush=True)
    receipt['owned_setup'] = timed_command('music', 'setup', '--songs', str(SONGS), timeout=180)
    print('owned_setup', receipt['owned_setup']['seconds'], flush=True)
    receipt['repeat_setup'] = timed_command('music', 'setup', '--songs', str(SONGS), timeout=30)
    receipt['runtime_bytes'] = disk_bytes(WORK / 'godmode/state/music/runtime')
    receipt['installed_pack_bytes'] = disk_bytes(WORK / 'godmode/packs/music')
    receipt['host_load_at_ui_start'] = load_snapshot()
    for n in range(5):
        start = time.monotonic_ns()
        term = Session()
        text = term.wait(lambda t: '1620 tracks' in t and 'All tracks' in t and 'opens collection' in t)
        receipt['startup_ms'].append((time.monotonic_ns() - start) / 1e6)
        print('startup', n, round(receipt['startup_ms'][-1], 2), flush=True)
        if n < 4:
            term.close()
            term = None
    (FIX / 'library-screen.txt').write_text(text + '\n')
    for n in range(4):
        ms, _ = term.action(b'\x1b[B', lambda t: '2 / 492' in t)
        receipt['navigation_ms'].append(ms)
        ms, _ = term.action(b'\x1b[A', lambda t: '1 / 492' in t)
        receipt['navigation_ms'].append(ms)
    for query, count in [('lost woods', '2 found'), ('ocarina of time', '7 found'), ('unlikelynomatchperformance', '0 found')]:
        ms, _ = term.action(('/' + query).encode(), lambda t: ('/ ' + query) in t and count in t)
        receipt['search_ms'].append(ms)
        term.action(b'\x1b', lambda t: 'Collections' in t and '1 / 492' in t)
    receipt['checks'].append('Search timings include full query key burst to filtered rendered results; no Enter/play used.')
    ms, text = term.action(b'a', lambda t: 'QUEUE 1620' in t and 'Added to queue' in t)
    receipt['enqueue_all_ms'] = round(ms, 3)
    if 'STOPPED' not in text:
        raise RuntimeError('unexpected non-stopped queue state')
    print('enqueue_all', round(ms, 2), flush=True)
    bridge = subprocess.Popen([str(BIN), 'music', '__bridge'], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    initial = request({'action': 'status'})
    receipt['bridge_first_status_ms'] = round(initial[3], 3)
    statuses = [request({'action': 'status'}) for _ in range(10)]
    for state, size, transport, total in statuses:
        if state['state'] != 'stopped' or len(state['queue']) != 1620:
            raise RuntimeError('unexpected player state/queue')
    receipt['status_ipc'] = {'queue_tracks': 1620, 'encoded_reply_bytes': statuses[-1][1],
                             'wire_roundtrip': summary([x[2] for x in statuses]),
                             'roundtrip_and_json_decode': summary([x[3] for x in statuses]),
                             'scope': 'Persistent core router -> companion music __bridge -> private daemon; first startup request excluded.'}
    pids = descendants(term.t.process.pid)
    socket_owners = subprocess.run(['/usr/sbin/lsof', '-t', str(socket_dir / 'control.sock')],
                                  capture_output=True, text=True)
    daemon_pids = sorted({int(word) for word in socket_owners.stdout.split() if word.isdecimal()} - set(pids))
    before = {pid: cpu_time(pid) for pid in pids}
    daemon_before = {pid: cpu_time(pid) for pid in daemon_pids}
    output_mark = len(term.t.capture)
    start = time.monotonic()
    while time.monotonic() - start < 10.3:
        term.read(.025)
    elapsed = time.monotonic() - start
    after = {pid: cpu_time(pid) for pid in pids}
    delta = sum(after[pid] - before[pid] for pid in pids)
    daemon_delta = sum(cpu_time(pid) - daemon_before[pid] for pid in daemon_pids)
    receipt['idle'] = {'observation_seconds': round(elapsed, 3), 'ui_and_bridge_cpu_seconds': round(delta, 3),
                       'approx_one_core_percent': round(100 * delta / elapsed, 2),
                       'pty_output_bytes': len(term.t.capture) - output_mark,
                       'process_count': len(pids), 'scope': 'Own native core/router, companion UI and private bridge descendants; '
                       'detached daemon and recorder excluded. ps CPU time has 0.01-second resolution; short sample.'}
    receipt['idle_daemon'] = {'identified_by_owned_socket': bool(daemon_pids), 'process_count': len(daemon_pids),
                              'cpu_seconds': round(daemon_delta, 3) if daemon_pids else None,
                              'approx_one_core_percent': round(100 * daemon_delta / elapsed, 2) if daemon_pids else None,
                              'note': 'Unavailable when socket ownership lookup returns no PID; this does not imply zero daemon CPU.'}
    ms, _ = term.action(b'\t', lambda t: '[ QUEUE 1620 ]' in t and 'Enter plays this queued track' in t)
    receipt['queue_open_after_idle_ms'] = round(ms, 3)
    samples = []
    for n in range(3):
        ms, _ = term.action(b'\x1b[B', lambda t: '2 / 1620' in t)
        samples.append(ms)
        ms, text = term.action(b'\x1b[A', lambda t: '1 / 1620' in t)
        samples.append(ms)
    receipt['queue_navigation_1620'] = summary(samples)
    (FIX / 'queue-screen.txt').write_text(text + '\n')
    final = request({'action': 'status'})[0]
    receipt['final_state'] = {'state': final['state'], 'queue_tracks': len(final['queue']), 'position': final['position'], 'track': final['track']}
    if final['state'] != 'stopped' or final['position'] != 0:
        raise RuntimeError('Unexpected audio state')
    receipt['checks'].append('All 1620 tracks enqueued through All tracks; final transport stayed stopped at zero; no play request sent.')
    receipt['cache_bytes'] = disk_bytes(WORK / 'godmode/state/music/cache')
    for name in ('startup_ms', 'navigation_ms', 'search_ms'):
        receipt[name.replace('_ms', '')] = summary(receipt.pop(name))
except Exception as exc:
    receipt['error'] = str(exc)
    raise
finally:
    if term:
        try:
            term.close()
        except Exception as exc:
            receipt['terminal_cleanup_error'] = str(exc)
    if bridge:
        bridge.stdin.close()
        try:
            bridge.wait(timeout=5)
        except subprocess.TimeoutExpired:
            bridge.kill()
            bridge.wait()
    stop = command('music', 'stop')
    remove = command('music', 'remove')
    receipt['cleanup'] = {'stop_exit': stop.returncode, 'remove_exit': remove.returncode,
                           'remove_message': remove.stdout.strip(),
                           'socket_absent': not (socket_dir / 'control.sock').exists(),
                           'managed_state_absent': not (WORK / 'godmode/state/music').exists()}
    if socket_dir.exists():
        try:
            socket_dir.rmdir()
        except OSError:
            receipt['cleanup']['socket_directory_not_empty'] = True
    receipt['host_load_after'] = load_snapshot()
    receipt['binaries_unchanged'] = (hashlib.sha256(BIN.read_bytes()).hexdigest() == receipt['core']['sha256']
                                    and hashlib.sha256(PACK.read_bytes()).hexdigest() == receipt['pack']['sha256'])
    run.cleanup()
    receipt['cleanup']['isolated_home_removed'] = not WORK.exists()
    (ROOT / 'pack-performance.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('saved', ROOT / 'pack-performance.json', flush=True)
