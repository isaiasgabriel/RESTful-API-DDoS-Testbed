#!/usr/bin/env python3
"""Local bounded regression: smoke, contract suite, HTTP/2 load and recovery.

Run with lab/.venv/bin/python from any directory. Requires Docker access and
/tmp/tcc-gateway-validation-h2 built from diagnostics/http2_bounded.go.
Preserves volumes, writes a new result directory, leaves Kong running.
"""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
BIN = Path('/tmp/tcc-gateway-validation-h2')


def save(path, data):
    path.write_text(json.dumps(data, indent=2))


def command(args, path, timeout=180, env=None):
    with path.open('w') as output:
        result = subprocess.run(args, cwd=ROOT, env=env, stdout=output,
                                stderr=subprocess.STDOUT, timeout=timeout)
    return result.returncode


def snapshot(path):
    ids = subprocess.check_output(['docker', 'ps', '-aq', '--filter',
                                  'label=com.docker.compose.project=lab'], text=True).split()
    raw = json.loads(subprocess.check_output(['docker', 'inspect', *ids], text=True))
    states = [{ 'name': x['Name'], 'image': x['Config']['Image'],
                'image_id': x['Image'], 'status': x['State']['Status'],
                'restarts': x['RestartCount'], 'oom_killed': x['State']['OOMKilled'],
                'health': x['State'].get('Health', {}).get('Status')} for x in raw]
    save(path, states)
    return states


def smoke():
    rows = []
    for h2, base in [(False, 'http://127.0.0.1:8080'), (True, 'https://127.0.0.1:8443')]:
        with httpx.Client(http2=h2, verify=False, trust_env=False, timeout=5) as client:
            for path in ['/healthz', '/', '/catalogue']:
                r = client.get(base + path)
                valid = r.status_code == 200
                if path == '/catalogue':
                    try:
                        data = r.json()
                        valid = valid and isinstance(data, list) and bool(data) and all('id' in x and 'name' in x for x in data)
                    except (ValueError, TypeError):
                        valid = False
                rows.append({'url': base+path, 'status': r.status_code,
                             'protocol': r.http_version, 'valid': valid,
                             'body_bytes': len(r.content)})
                if h2 and r.http_version != 'HTTP/2':
                    rows[-1]['valid'] = False
    return rows


def main():
    if not BIN.exists():
        raise SystemExit('Build /tmp/tcc-gateway-validation-h2 first')
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT/'results'/('gateway-validation-'+stamp)
    out.mkdir(parents=True)
    print(f'Artifacts: {out}', flush=True)
    save(out/'metadata.json', {'scope': 'functional regression, not a rate-policy equivalence campaign',
         'tls_verification': False, 'load_requests_per_gateway': 400,
         'load_concurrency': 16, 'load_batch_pause': '100ms',
         'contract': 'existing five cases; existing stack reused; volumes preserved'})
    results = {}
    try:
        for gateway in ['kong', 'nginx', 'envoy']:
            folder = out/gateway
            folder.mkdir()
            print(f'{gateway}: starting', flush=True)
            start = command(['bash', 'start.sh'], folder/'startup.log',
                            env={**os.environ, 'API_GATEWAY': gateway})
            if start:
                results[gateway] = {'startup_exit': start}
                save(out/'summary.json', results)
                continue
            deadline = time.monotonic()+90
            rows = []
            while time.monotonic()<deadline:
                try:
                    rows = smoke()
                    if all(x['valid'] for x in rows):
                        break
                except httpx.HTTPError as exc:
                    rows = [{'valid': False, 'error': str(exc)}]
                time.sleep(3)
            save(folder/'smoke.json', rows)
            before = snapshot(folder/'before.json')
            if not rows or not all(x['valid'] for x in rows):
                results[gateway] = {'smoke_passed': False}
                command(['docker','logs','--tail','150','sockshop-gateway'], folder/'gateway.log')
                save(out/'summary.json', results)
                continue
            # Let startup probes drain from every policy before contract checks.
            print(f'{gateway}: smoke passed; waiting 61s before contract', flush=True)
            time.sleep(61)
            code = command([sys.executable,'-m','pytest','tests/test_rate_limiting.py',
                            '--gateway',gateway,'--reuse-stack','--report-dir',str(folder),'-v'],
                           folder/'pytest.log', timeout=180)
            print(f'{gateway}: contract exit={code}; bounded HTTP/2 load (400 requests, concurrency 16)', flush=True)
            command(['docker','stats','--no-stream','--format','{{json .}}'], folder/'resources-before.jsonl')
            load = command([str(BIN),'-concurrency','16','-requests','400','-pause','100ms',
                            '-run',stamp+'-'+gateway,'-out',str(folder/'requests.jsonl')], folder/'load-summary.json', timeout=55)
            command(['docker','stats','--no-stream','--format','{{json .}}'], folder/'resources-after.jsonl')
            print(f'{gateway}: load exit={load}; waiting 61s for recovery', flush=True)
            time.sleep(61)
            recovery = smoke()
            save(folder/'recovery.json', recovery)
            after = snapshot(folder/'after.json')
            command(['docker','logs','--tail','2000','sockshop-gateway'], folder/'gateway.log')
            command(['docker','logs','--tail','2000','sockshop-frontend'], folder/'frontend.log')
            stable = {x['name']:x['restarts'] for x in before} == {x['name']:x['restarts'] for x in after}
            running = all(x['status']=='running' and not x['oom_killed'] for x in after)
            results[gateway] = {'smoke_passed': True, 'contract_exit': code,
                'load_exit': load, 'recovery_passed': all(x['valid'] for x in recovery),
                'no_additional_restarts': stable, 'containers_running_no_oom': running}
            save(out/'summary.json',results)
            print(f'{gateway}: {json.dumps(results[gateway])}',flush=True)
    finally:
        print('Restoring Kong as the active gateway',flush=True)
        code = command(['bash','start.sh'], out/'restore-kong.log',env={**os.environ,'API_GATEWAY':'kong'})
        save(out/'restoration.json',{'gateway':'kong','exit_code':code})
    print(f'Finished: {out}',flush=True)
    return 0 if len(results)==3 and all(r.get('contract_exit')==0 and r.get('load_exit')==0 and r.get('recovery_passed') and r.get('no_additional_restarts') and r.get('containers_running_no_oom') for r in results.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
