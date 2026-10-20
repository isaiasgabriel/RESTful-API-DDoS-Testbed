// Bounded local HTTP/2 diagnostic. Uses only the Go standard library.
// The endpoint is deliberately fixed to the local Kong catalogue route.
package main

import (
	"crypto/sha256"
	"crypto/tls"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"net/http/httptrace"
	"os"
	"sync"
	"sync/atomic"
	"time"
)

func main() {
	c := flag.Int("concurrency", 1, "requests per batch, 1..64")
	n := flag.Int("requests", 110, "total requests, 1..5000")
	pause := flag.Duration("pause", 100*time.Millisecond, "pause between completed batches, >=100ms")
	run := flag.String("run", "", "unique run identifier")
	output := flag.String("out", "", "new JSONL output file")
	flag.Parse()
	if *c < 1 || *c > 64 || *n < 1 || *n > 5000 || *pause < 100*time.Millisecond || *run == "" || *output == "" {
		fmt.Fprintln(os.Stderr, "invalid bounded diagnostic arguments")
		os.Exit(2)
	}
	f, err := os.OpenFile(*output, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0644)
	if err != nil {
		panic(err)
	}
	defer f.Close()
	encoder := json.NewEncoder(f)
	transport := &http.Transport{
		Proxy: nil, ForceAttemptHTTP2: true, MaxConnsPerHost: 1,
		MaxIdleConnsPerHost: 1, TLSHandshakeTimeout: 5 * time.Second,
		TLSClientConfig: &tls.Config{InsecureSkipVerify: true, MinVersion: tls.VersionTLS12}, // local laboratory only
	}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, Timeout: 5 * time.Second}
	var mu sync.Mutex
	var failures int32
	var active, peak int
	connections := map[string]int{}
	counts := map[int]int{}
	started := time.Now()
	deadline := started.Add(40 * time.Second)
	completed := 0
	for offset := 0; offset < *n && atomic.LoadInt32(&failures) < 5 && time.Now().Before(deadline); offset += *c {
		var wg sync.WaitGroup
		for j := offset; j < offset+*c && j < *n; j++ {
			wg.Add(1)
			go func(index int) {
				defer wg.Done()
				id := fmt.Sprintf("%s-%05d", *run, index+1)
				row := map[string]interface{}{"request_id": id, "send_ns": time.Now().UnixNano()}
				t0 := time.Now()
				mu.Lock()
				active++
				if active > peak {
					peak = active
				}
				mu.Unlock()
				trace := &httptrace.ClientTrace{
					GotConn: func(info httptrace.GotConnInfo) {
						key := fmt.Sprintf("%p", info.Conn)
						mu.Lock()
						if connections[key] == 0 {
							connections[key] = len(connections) + 1
						}
						row["connection_id"] = connections[key]
						mu.Unlock()
						row["local_addr"] = info.Conn.LocalAddr().String()
						row["remote_addr"] = info.Conn.RemoteAddr().String()
						row["connection_reused"] = info.Reused
					},
					WroteHeaders: func() { row["wrote_headers_ns"] = time.Now().UnixNano() },
				}
				req, _ := http.NewRequest("GET", "https://127.0.0.1:8443/catalogue?diagnostic_id="+id, nil)
				req.Header.Set("User-Agent", "tcc-bounded-http2/1.0")
				req = req.WithContext(httptrace.WithClientTrace(req.Context(), trace))
				response, err := client.Do(req)
				status := 0
				if err != nil {
					row["error"] = err.Error()
				} else {
					status = response.StatusCode
					row["status"] = status
					row["protocol"] = response.Proto
					if response.TLS != nil {
						row["alpn"] = response.TLS.NegotiatedProtocol
					}
					row["remaining"] = response.Header.Get("X-RateLimit-Remaining-Minute")
					row["limit"] = response.Header.Get("X-RateLimit-Limit-Minute")
					row["reset"] = response.Header.Get("RateLimit-Reset")
					row["kong_request_id"] = response.Header.Get("X-Kong-Request-Id")
					row["upstream_latency"] = response.Header.Get("X-Kong-Upstream-Latency")
					body, readErr := io.ReadAll(io.LimitReader(response.Body, 1<<20))
					response.Body.Close()
					row["body_bytes"] = len(body)
					row["body_sha256"] = fmt.Sprintf("%x", sha256.Sum256(body))
					if readErr != nil {
						row["error"] = readErr.Error()
					}
					if status == 200 {
						var catalogue []map[string]interface{}
						valid := json.Unmarshal(body, &catalogue) == nil && len(catalogue) > 0
						for _, item := range catalogue {
							if item["id"] == nil || item["name"] == nil {
								valid = false
							}
						}
						row["catalogue_valid"] = valid
						if !valid {
							row["error"] = "invalid catalogue"
						}
					}
					if response.ProtoMajor != 2 {
						row["error"] = "HTTP/2 not negotiated"
					}
				}
				row["receive_ns"] = time.Now().UnixNano()
				row["latency_ms"] = float64(time.Since(t0).Microseconds()) / 1000
				if row["error"] != nil || (status != 200 && status != 429) {
					atomic.AddInt32(&failures, 1)
				}
				mu.Lock()
				active--
				completed++
				counts[status]++
				if err := encoder.Encode(row); err != nil {
					fmt.Fprintln(os.Stderr, err)
					atomic.AddInt32(&failures, 5)
				}
				mu.Unlock()
			}(j)
		}
		wg.Wait()
		if offset+*c < *n {
			time.Sleep(*pause)
		}
	}
	json.NewEncoder(os.Stdout).Encode(map[string]interface{}{
		"run_id": *run, "completed": completed, "planned": *n, "status_counts": counts,
		"connections_observed": len(connections), "peak_client_inflight": peak,
		"unexpected_failures": failures, "elapsed_seconds": time.Since(started).Seconds(),
		"tls_verification_disabled": true,
	})
	if failures != 0 || completed != *n {
		os.Exit(1)
	}
}
