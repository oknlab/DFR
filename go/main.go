package main

import (
	"encoding/json"
	"io"
	"log"
	"net/http"
	"regexp"
	"strings"
	"sync"
	"time"
)

type FetchRequest struct {
	Urls []string `json:"urls"`
}

type FetchItem struct {
	URL    string `json:"url"`
	OK     bool   `json:"ok"`
	Status int    `json:"status,omitempty"`
	Text   string `json:"text,omitempty"`
	Error  string `json:"error,omitempty"`
}

var tagRe = regexp.MustCompile(`<[^>]+>`)

func stripHTML(s string) string {
	s = tagRe.ReplaceAllString(s, " ")
	s = strings.Join(strings.Fields(s), " ")
	if len(s) > 2000 {
		return s[:2000]
	}
	return s
}

func fetchOne(client *http.Client, url string) FetchItem {
	resp, err := client.Get(url)
	if err != nil {
		return FetchItem{URL: url, OK: false, Error: err.Error()}
	}
	defer resp.Body.Close()
	b, err := io.ReadAll(io.LimitReader(resp.Body, 2_000_000))
	if err != nil {
		return FetchItem{URL: url, OK: false, Status: resp.StatusCode, Error: err.Error()}
	}
	return FetchItem{URL: url, OK: true, Status: resp.StatusCode, Text: stripHTML(string(b))}
}

func fetchHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var req FetchRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	client := &http.Client{Timeout: 12 * time.Second}
	results := make([]FetchItem, len(req.Urls))
	wg := sync.WaitGroup{}
	for i, url := range req.Urls {
		wg.Add(1)
		go func(i int, u string) {
			defer wg.Done()
			results[i] = fetchOne(client, u)
		}(i, url)
	}
	wg.Wait()

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"count": len(results), "results": results})
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(`{"status":"ok"}`))
}

func main() {
	http.HandleFunc("/health", healthHandler)
	http.HandleFunc("/fetch", fetchHandler)
	log.Println("go-fetch listening on :8081")
	log.Fatal(http.ListenAndServe(":8081", nil))
}
