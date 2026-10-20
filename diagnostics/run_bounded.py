#!/usr/bin/env python3
"""Run three bounded local diagnostic stages; no restart or configuration changes.

Build first: go build -o /tmp/tcc-http2-bounded diagnostics/http2_bounded.go
Run from any directory: python3 lab/diagnostics/run_bounded.py
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
BIN = Path('/tmp/tcc-http2-bounded')


def cmd(args, timeout=30):
    r = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    return {'command': args, 'exit_code': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr}


def save(path, value):
    path.write_text(json.dumps(value, indent=2))


def state():
    ids = cmd(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=lab'])
    if ids['exit_code'] or not ids['stdout'].split():
        raise RuntimeError('Docker unavailable or no lab containers')
    raw = cmd(['docker', 'inspect', *ids['stdout'].split()])
    return [{'name': x['Name'].lstrip('/'), 'image': x['Config']['Image'], 'image_id': x['Image'],
             'started_at': x['State']['StartedAt'], 'status': x['State']['Status'],
             'health': x['State'].get('Health', {}).get('Status'),
             'restart_count': x['RestartCount'], 'oom_killed': x['State']['OOMKilled']}
            for x in json.loads(raw['stdout'])]


def wait_minute():
    start = (int(time.time()) // 60 + 1) * 60 + 2
    print(f'Waiting {start-time.time():.1f}s for fresh minute', flush=True)
    while time.time() < start:
        time.sleep(min(1, start-time.time()))
    return dt.datetime.fromtimestamp(start-2, dt.timezone.utc).isoformat()


def main():
    if not BIN.exists():
        raise SystemExit('Compile /tmp/tcc-http2-bounded first')
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT / 'results' / ('restart-stress-' + stamp)
    out.mkdir()
    print(f'Artifacts: {out}', flush=True)
    initial = state()
    gateway = next(x for x in initial if x['name'] == 'sockshop-gateway')
    if gateway['image'] != 'kong:3.7.1' or gateway['health'] != 'healthy':
        raise SystemExit('Expected healthy Kong 3.7.1')
    if any(x['status'] != 'running' for x in initial):
        raise SystemExit('A lab container is not running')
    save(out/'state-before.json', initial)
    save(out/'docker-host.json', cmd(['docker','info','--format','{"cpus":{{.NCPU}},"memory":{{.MemTotal}},"version":{{json .ServerVersion}}}']))
    config = cmd(['docker','exec','sockshop-gateway','cat','/kong.yml'])
    if config['exit_code']: raise SystemExit('Cannot read Kong configuration')
    (out/'kong.yml').write_text(config['stdout'])
    for source in [Path(__file__), Path(__file__).with_name('http2_bounded.go')]:
        (out/source.name).write_bytes(source.read_bytes())
    save(out/'metadata.json', {'run_id':stamp, 'binary_sha256':hashlib.sha256(BIN.read_bytes()).hexdigest(),
         'go_version':cmd(['go','version'])['stdout'].strip(),
         'source_sha256':hashlib.sha256(Path(__file__).with_name('http2_bounded.go').read_bytes()).hexdigest(),
         'scope':'diagnostic, one repetition per stage; TLS trust verification disabled; same host generator and target',
         'trace':'GODEBUG=http2debug=2; logging overhead included',
         'restart':'Runner itself does not restart; see report for preceding Compose restart.',
         'abort':'Stop subsequent batches after five unexpected failures or 40 seconds; max 64 requests in current batch; per-request timeout 5s'})
    targets=[x['name'] for x in initial]
    stages=[]
    for c,n,pause in [(1,110,'100ms'),(16,1600,'150ms'),(64,3200,'300ms')]:
        stage=out/f'c{c}'
        stage.mkdir()
        since=wait_minute()
        stop=threading.Event()

        def monitor():
            with (stage/'resources.jsonl').open('w') as f:
                while not stop.is_set():
                    sample={'start_ns':time.time_ns(),
                            'host_cpu':Path('/proc/stat').read_text().splitlines()[0],
                            'host_meminfo':Path('/proc/meminfo').read_text(),
                            'host_loadavg':Path('/proc/loadavg').read_text()}
                    try:
                        r=cmd(['docker','stats','--no-stream','--format','{{json .}}',*targets])
                        sample.update(end_ns=time.time_ns(),exit_code=r['exit_code'],
                                      containers=[json.loads(x) for x in r['stdout'].splitlines()],error=r['stderr'])
                    except Exception as e:
                        sample['error']=str(e)
                    f.write(json.dumps(sample)+'\n'); f.flush()
                    stop.wait(1)

        thread=threading.Thread(target=monitor)
        thread.start()
        args=[str(BIN),'-concurrency',str(c),'-requests',str(n),'-pause',pause,
              '-run',f'{stamp}-c{c}','-out',str(stage/'requests.jsonl')]
        print(f'Start c={c}, requests={n}, batch pause={pause}',flush=True)
        before=resource.getrusage(resource.RUSAGE_CHILDREN)
        try:
            with (stage/'http2-frames.log').open('w') as err:
                process=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=err,
                                       env={**os.environ,'GODEBUG':'http2debug=2'},timeout=50)
            (stage/'client-summary.json').write_text(process.stdout)
            after=resource.getrusage(resource.RUSAGE_CHILDREN)
            save(stage/'execution.json',{'command':args,'exit_code':process.returncode,
                 'children_user_cpu_delta_s':after.ru_utime-before.ru_utime,
                 'children_system_cpu_delta_s':after.ru_stime-before.ru_stime,
                 'cpu_note':'Includes diagnostic child processes such as docker stats, not generator alone.'})
        finally:
            stop.set(); thread.join(timeout=35)
            for name in ['sockshop-gateway','sockshop-frontend','sockshop-catalogue']:
                r=cmd(['docker','logs','--since',since,'--timestamps',name])
                (stage/(name+'.log')).write_text(r['stdout']+r['stderr'])
            snapshot=state(); save(stage/'state-after.json',snapshot)
        result=json.loads(process.stdout)
        stages.append(result)
        print(json.dumps(result),flush=True)
        save(out/'stages.json',stages)
        if process.returncode or any(x['status']!='running' or x['oom_killed'] for x in snapshot):
            raise SystemExit('Stopped: workload failure or unhealthy container state')
    wait_minute()
    recovery=cmd(['curl','--http2','--insecure','--noproxy','*','--max-time','10','--silent','--show-error',
                  '--dump-header',str(out/'recovery.headers'),'--output',str(out/'recovery.body'),
                  '--write-out','%{json}',f'https://127.0.0.1:8443/catalogue?recovery_id={stamp}'])
    save(out/'recovery.json',recovery)
    save(out/'state-after.json',state())
    print('Finished; recovery saved. Analyze logs before drawing conclusions.',flush=True)


if __name__=='__main__':
    main()
