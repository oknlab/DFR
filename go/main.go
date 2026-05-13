package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/exec"
	"regexp"
	"strings"
	"sync"
	"time"
)

type PipelineRequest struct { Query string `json:"query"`; SeedURLs []string `json:"seed_urls"`; MaxURLs int `json:"max_urls"`; UseFirecrawl bool `json:"use_firecrawl"`; UseApify bool `json:"use_apify"` }
type FetchItem struct { URL string `json:"url"`; OK bool `json:"ok"`; Status int `json:"status,omitempty"`; Text string `json:"text,omitempty"`; Error string `json:"error,omitempty"` }

var (
	tagRe = regexp.MustCompile(`<[^>]+>`)
	firecrawlURL = getenv("FIRECRAWL_API_URL", "http://127.0.0.1:3002/v1")
	firecrawlAPIKey = os.Getenv("FIRECRAWL_API_KEY")
	apifyToken = os.Getenv("APIFY_TOKEN")
)

func getenv(k,d string) string { v:=os.Getenv(k); if v=="" {return d}; return v }
func stripHTML(s string) string { s = strings.Join(strings.Fields(tagRe.ReplaceAllString(s," "))," "); if len(s)>3000 {return s[:3000]}; return s }

func redis(args ...string) (string,error) { out, err := exec.Command("redis-cli", args...).Output(); return strings.TrimSpace(string(out)), err }
func redisGet(k string) string { v,_ := redis("GET",k); return v }
func redisSetEx(k,v string) { _,_ = redis("SETEX",k,getenv("CACHE_TTL_SEC","900"),v) }
func redisLPush(k,v string) { _,_ = redis("LPUSH",k,v) }
func redisPing() bool { v,_ := redis("PING"); return strings.Contains(v,"PONG") }

func fetchOne(url string) FetchItem { c:=http.Client{}; res,err:=c.Get(url); if err!=nil {return FetchItem{URL:url,OK:false,Error:err.Error()}}; defer res.Body.Close(); b,_:=io.ReadAll(io.LimitReader(res.Body,1_000_000)); return FetchItem{URL:url,OK:true,Status:res.StatusCode,Text:stripHTML(string(b))} }

func searchFirecrawl(query string, limit int) map[string]any {
	body,_ := json.Marshal(map[string]any{"query":query,"limit":limit})
	req,_ := http.NewRequest(http.MethodPost, firecrawlURL+"/search", bytes.NewReader(body)); req.Header.Set("Content-Type","application/json")
	if firecrawlAPIKey!="" { req.Header.Set("Authorization","Bearer "+firecrawlAPIKey) }
	res,err := http.DefaultClient.Do(req); if err!=nil {return map[string]any{"ok":false,"error":err.Error()}}; defer res.Body.Close(); var out any; _ = json.NewDecoder(res.Body).Decode(&out)
	return map[string]any{"ok":res.StatusCode<400,"status":res.StatusCode,"data":out}
}

func pipelineHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost { http.Error(w, "method not allowed", 405); return }
	var req PipelineRequest; if err:=json.NewDecoder(r.Body).Decode(&req); err!=nil { http.Error(w, err.Error(), 400); return }
	if req.MaxURLs<=0 {req.MaxURLs=10}
	raw,_:=json.Marshal(req); sum:=sha256.Sum256(raw); ck:="pipeline:"+hex.EncodeToString(sum[:])
	if c := redisGet(ck); c!="" { w.Header().Set("Content-Type","application/json"); _,_=w.Write([]byte(c)); return }
	search := map[string]any{}
	urls := append([]string{}, req.SeedURLs...)
	if req.UseFirecrawl && req.Query!="" {
		search["firecrawl"] = searchFirecrawl(req.Query, req.MaxURLs)
		if fc, ok := search["firecrawl"].(map[string]any); ok {
			if d, ok := fc["data"].(map[string]any); ok {
				if arr, ok := d["data"].([]any); ok {
					for _, it := range arr {
						if m, ok := it.(map[string]any); ok { if u, ok := m["url"].(string); ok { urls = append(urls, u) } }
					}
				}
			}
		}
	}
	uniq:=map[string]bool{}; final:=[]string{}
	for _,u := range urls { if !uniq[u] && u!="" { uniq[u]=true; final=append(final,u)}; if len(final)>=req.MaxURLs {break}}
	results:=make([]FetchItem,len(final)); wg:=sync.WaitGroup{}
	for i,u := range final { wg.Add(1); go func(i int, u string){ defer wg.Done(); results[i]=fetchOne(u)}(i,u)}; wg.Wait()
	resp:=map[string]any{"product":"distributed-web-data-os","timestamp":time.Now().UTC().Format(time.RFC3339),"stages":map[string]any{"search":search,"crawl":results,"scrape":results},"urls":final,"apify_enabled":apifyToken!=""}
	out,_:=json.Marshal(resp); redisSetEx(ck,string(out)); redisLPush("pipeline:jobs", fmt.Sprintf("%v",req.Query))
	w.Header().Set("Content-Type","application/json"); _,_=w.Write(out)
}

func health(w http.ResponseWriter, r *http.Request){ if r.Method != http.MethodGet { http.Error(w, "method not allowed", 405); return }; w.Header().Set("Content-Type","application/json"); _ = json.NewEncoder(w).Encode(map[string]any{"status":"ok","redis":redisPing()}) }
func openapi(w http.ResponseWriter, r *http.Request){ w.Header().Set("Content-Type","application/json"); _,_=w.Write([]byte(`{"openapi":"3.0.3","info":{"title":"Distributed Web Data OS","version":"1.0.0"},"paths":{"/pipeline":{"post":{"responses":{"200":{"description":"ok"}}}},"/health":{"get":{"responses":{"200":{"description":"ok"}}}},"/ui":{"get":{"responses":{"200":{"description":"ok"}}}},"/openapi.json":{"get":{"responses":{"200":{"description":"ok"}}}}}}`)) }
func ui(w http.ResponseWriter, r *http.Request){ w.Header().Set("Content-Type","text/html; charset=utf-8"); _,_=w.Write([]byte(`<html><body><h3>Distributed Web Data OS UI</h3><input id=q><button onclick='go()'>Run</button><pre id=o></pre><script>async function go(){let q=document.getElementById('q').value;let r=await fetch('/pipeline',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({query:q,seed_urls:['https://example.com'],max_urls:3,use_firecrawl:false})});document.getElementById('o').textContent=JSON.stringify(await r.json(),null,2)}</script></body></html>`)) }

func main(){
	port := getenv("PORT","10000")
	http.HandleFunc("/pipeline", pipelineHandler)
	http.HandleFunc("/health", health)
	http.HandleFunc("/openapi.json", openapi)
	http.HandleFunc("/ui", ui)
	log.Printf("listening on :%s", port)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}
