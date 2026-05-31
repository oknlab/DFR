# DFR Search Frontend

A privacy-first FastAPI search frontend for JSON search APIs with bangs, anonymous view links, ad-free filtering, optional Redis caching, independent-index defaults, and maximum provider extensibility.

## Run locally

```bash
docker compose up --build
```

Open <http://localhost:8000> for the web UI, or query the JSON API directly:

```bash
curl 'http://localhost:8000/api/search?q=!w%20fastapi&max_results=5&engine=all&crawl=true&lang=en-US&safe=moderate&hide_promoted=true&source_types=web,docs,images,news,social'
```

## Endpoints

- `GET /` — HTML/CSS/JS search UI.
- `GET /api/search?q=<query>&max_results=<1-10>&engine=<key|all>` — private JSON search results.
- `GET /api/engines` — enabled JSON search engines.
- `GET /api/bangs` — configured bang shortcuts such as `!w`, `!yt`, and `!amazon`.
- `GET /api/privacy` — privacy guarantees advertised by the service.
- `GET /api/anonymous?url=<http-url>` — redirect through the configured anonymous-view proxy.
- `GET /health` — health check including Redis and strict privacy status.

## Privacy-first features

- **No tracking / no user profiles:** the app does not create accounts, profile IDs, or tracking cookies.
- **Strict privacy mode:** enabled by default with `STRICT_PRIVACY_MODE=true`; response cookies are stripped and search-result caching is disabled unless explicitly opted in.
- **No IP storage:** app logs avoid client IP addresses and only log target hosts for crawl diagnostics.
- **Ad-free results:** `hide_promoted=true` filters common `ad`, `sponsored`, and `promoted` markers.
- **Anonymous View:** each result includes an `anonymous_url` for opening through a configured proxy (`ANONYMOUS_VIEW_PREFIX`).
- **Google via proxy:** set `GOOGLE_PROXY_SEARCH_URL` or `GOOGLE_SEARCH_URL` to use Google-compatible JSON results through your own anonymous proxy.

## Configure more search engines

The app ships with the provided independent ConnectNet JSON search endpoint. Add SearXNG-style, Google-compatible, Bing fallback, or custom providers with environment variables:

```bash
export BING_SEARCH_URL='https://your-bing-proxy.example/search'
export GOOGLE_PROXY_SEARCH_URL='https://your-google-proxy.example/search'
export SEARXNG_SEARCH_URL='https://your-searxng.example/search'
export SEARCH_ENGINES_JSON='{"company":{"name":"Company Search","url":"https://search.example.com/search","description":"Internal JSON search","kind":"docs"}}'
```

Each configured engine must accept `q` and `format=json` query parameters and return either a `results` array (`url`, `title`, `content`) or an `items` array (`link`, `title`, `snippet`).

## Bangs

Built-in bangs include `!w`, `!yt`, `!amazon`, `!gh`, `!so`, and `!x`. Add new bangs without code changes:

```bash
export SEARCH_BANGS_JSON='{"!mdn":{"name":"MDN","url":"https://developer.mozilla.org/search?q={query}"}}'
```

## Level-MAX API controls

- `engine=all`: merge all configured sources.
- `fallback=true`: use the configured Bing fallback (`SEARCH_FALLBACK_ENGINE=bing`) when the primary independent index is empty.
- `crawl=true|false`: enable/disable page crawling for speed-vs-richness.
- `lang` and `safe`: forwarded to providers as locale and safe-search hints.
- `hide_promoted=true|false`: hide promoted/ad/sponsored results.
- `source_types=web,docs,images,news,social`: merge multiple source categories.
- `ranking=docs.python.org:10,example.com:-5`: stateless per-request ranking; nothing is stored server-side.
