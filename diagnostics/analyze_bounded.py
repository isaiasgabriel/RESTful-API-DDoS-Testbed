#!/usr/bin/env python3
"""Analyze bounded diagnostics, including evidence of overlapping HTTP/2 streams."""
from collections import Counter
import csv
import json
from pathlib import Path
import re
import statistics
import sys


def percentile(values, fraction):
    ordered=sorted(values)
    return ordered[min(len(ordered)-1, int((len(ordered)-1)*fraction))]


def main(root):
    result=[]
    for directory in sorted(root.glob('c[0-9]*'),key=lambda p:int(p.name[1:])):
        rows=[json.loads(x) for x in (directory/'requests.jsonl').read_text().splitlines()]
        client=json.loads((directory/'client-summary.json').read_text())
        gateway=(directory/'sockshop-gateway.log').read_text()
        frontend=(directory/'sockshop-frontend.log').read_text()
        ids=Counter(r['request_id'] for r in rows)
        gw_ids=Counter(re.findall(r'diagnostic_id=([^\s\"]+)',gateway))
        fe_ids=Counter(re.findall(r'diagnostic_id=([^\s\"]+)',frontend))
        accesses=re.findall(r'(\S+) - - \[([^\]]+)\] "GET /catalogue\?diagnostic_id=([^\s]+) HTTP/2.0" (\d+)',gateway)
        gw_status={x[2]:int(x[3]) for x in accesses}
        minutes=sorted(set(x[1].rsplit(':',1)[0] for x in accesses))
        ips=sorted(set(x[0] for x in accesses))
        active=set(); started=set(); ended=set(); max_pending=0; resets=[]; framers=set()
        for line in (directory/'http2-frames.log').read_text().splitlines():
            match=re.search(r'Framer (0x[0-9a-f]+): (wrote|read) (\w+).*?stream=(\d+)',line)
            if not match: continue
            framer,direction,kind,stream=match.groups()
            key=(framer,int(stream)); framers.add(framer)
            if direction=='wrote' and kind=='HEADERS':
                active.add(key); started.add(key); max_pending=max(max_pending,len(active))
            if direction=='read' and ((kind in ('HEADERS','DATA') and 'END_STREAM' in line) or kind=='RST_STREAM'):
                active.discard(key); ended.add(key)
                if kind=='RST_STREAM': resets.append(line)
        checks={
            'planned_requests_completed':len(rows)==client['planned'],
            'unique_client_ids':all(v==1 for v in ids.values()),
            'all_http2_h2_alpn':all(r.get('protocol')=='HTTP/2.0' and r.get('alpn')=='h2' for r in rows),
            'no_client_errors':all(not r.get('error') for r in rows),
            'only_200_or_429':all(r.get('status') in (200,429) for r in rows),
            'catalogue_valid_for_200':all(r.get('catalogue_valid') for r in rows if r.get('status')==200),
            'one_tcp_connection':len(set(r.get('connection_id') for r in rows))==1 and client['connections_observed']==1,
            'one_gateway_ip_and_minute':len(ips)==len(minutes)==1,
            'gateway_ids_match':gw_ids==ids,
            'gateway_status_match':len(accesses)==len(rows) and all(gw_status.get(r['request_id'])==r.get('status') for r in rows),
            'frontend_matches_200':fe_ids==Counter(r['request_id'] for r in rows if r.get('status')==200),
            'no_competing_access_in_captured_window':all('HTTP/' not in line or 'diagnostic_id=' in line for line in gateway.splitlines()),
            'single_framer':len(framers)==1,
            'all_streams_observed_and_ended':len(started)==len(rows) and started==ended and not active,
            'no_stream_resets':not resets,
        }
        samples=[json.loads(x) for x in (directory/'resources.jsonl').read_text().splitlines()]
        cpu={}; memory={}
        with (directory/'resources.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=['sample_start_ns','sample_end_ns','container','cpu_percent','memory_usage_raw'])
            writer.writeheader()
            for sample in samples:
                for container in sample.get('containers',[]):
                    name=container['Name']; value=float(container['CPUPerc'].rstrip('%'))
                    cpu.setdefault(name,[]).append(value)
                    memory.setdefault(name,[]).append(container['MemUsage'])
                    writer.writerow({'sample_start_ns':sample['start_ns'],'sample_end_ns':sample['end_ns'],
                                     'container':name,'cpu_percent':value,'memory_usage_raw':container['MemUsage']})
        host_busy=[]
        for previous,current in zip(samples,samples[1:]):
            a=list(map(int,previous['host_cpu'].split()[1:9])); b=list(map(int,current['host_cpu'].split()[1:9]))
            total=sum(b)-sum(a); idle=b[3]+b[4]-a[3]-a[4]
            if total>0:host_busy.append(100*(total-idle)/total)
        fields=sorted(set().union(*(r.keys() for r in rows)))
        with (directory/'requests.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader(); writer.writerows(rows)
        valid=all(checks.values())
        count200=sum(r.get('status')==200 for r in rows)
        summary={'stage':directory.name,'checks':checks,'evidence_consistent':valid,
                 'requests':len(rows),'status_counts':dict(Counter(r.get('status') for r in rows)),
                 'gateway_minute':minutes,'gateway_ips':ips,'frontend_receipts':sum(fe_ids.values()),
                 'connection_count':client['connections_observed'], 'streams_seen':len(started),
                 'max_streams_pending_response_in_frame_log':max_pending,
                 'elapsed_seconds':client['elapsed_seconds'],
                 'latency_ms_mean':statistics.mean(r['latency_ms'] for r in rows),
                 'latency_ms_p95':percentile([r['latency_ms'] for r in rows],.95),
                 'latency_by_status':{str(status):{'mean':statistics.mean(r['latency_ms'] for r in rows if r.get('status')==status),
                     'p95':percentile([r['latency_ms'] for r in rows if r.get('status')==status],.95)} for status in set(r.get('status') for r in rows)},
                 'cpu_percent_sampled_max':{name:max(v) for name,v in cpu.items()},
                 'host_busy_percent_max_between_samples':max(host_busy) if host_busy else None,
                 'resource_samples':len(samples),'resource_errors':[s.get('error') for s in samples if s.get('error')],
                 'spillover_excess_over_100_observed':max(0,count200-100) if valid else None,
                 'false_positive_rate':None,
                 'limitations':'One diagnostic run, batched load, frame logging overhead; frame pending count is not server processing concurrency; concurrent per-request oracle not established.'}
        if directory.name=='c1' and valid:
            ordered=sorted(rows,key=lambda r:r['send_ns'])
            summary['sequential_expected_status_sequence']=all(r['status']==(200 if i<100 else 429) for i,r in enumerate(ordered))
            summary['false_positive_rate']=sum(r['status']==429 for r in ordered[:100])/100
        (directory/'analysis.json').write_text(json.dumps(summary,indent=2))
        result.append(summary)
    (root/'analysis.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Usage: analyze_bounded.py results/restart-stress-RUN')
    main(Path(sys.argv[1]))
