"""
app/web_search.py — All-In-One web search & retrieval module.

Combines four capabilities behind one coherent interface:

  1. IndependentIndex     — in-memory inverted index (zero external deps)
  2. External providers    — connectnet, Bing, Google (proxy), DuckDuckGo
  3. Shared async crawler  — fetches + cleans full page text and images
  4. Anonymous proxy view  — re-serves a page with trackers/ads stripped

Two top-level entry points:

  • unified_search(...)      -> ranked result LINKS + metadata   (for a results UI)
  • get_search_context(...)  -> crawled full TEXT of results      (for RAG / LLMs)

Plus a bridge, enrich_with_content(...), that crawls full text for an
existing unified_search() result set on demand.

Privacy: no user tracking, no IP logging, no cookies.
All Redis usage is OPTIONAL and fault-tolerant.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
import urllib.parse
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

try:  # Redis is optional — module works fully without it.
    from redis.asyncio import Redis as AsyncRedis
except Exception:  # pragma: no cover
    AsyncRedis = Any  # type: ignore

logger = logging.getLogger(__name__)

# ─── Configuration ──────────────────────────────────────────────────────────

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Your provided independent search engine.
CONNECTNET_URL = "https://connectnet.onrender.com/search"

CONCURRENT_REQUESTS_LIMIT = 5
SEARCH_CACHE_TTL = 3600  # seconds


# ─── HTML extraction helpers ────────────────────────────────────────────────

def clean_content(soup: BeautifulSoup) -> str:
    """Strip irrelevant tags and extract clean text from a BeautifulSoup object."""
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return " ".join(text.split())


def extract_images(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Extract and prioritize relevant image URLs. `base_url` MUST be a full URL."""
    images: set[str] = set()
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        images.add(urljoin(base_url, og_image["content"]))
    for img in soup.find_all("img", {"src": True}):
        src = img["src"]
        if src.startswith("data:"):
            continue
        try:
            width = int(img.get("width", "0"))
            height = int(img.get("height", "0"))
            if width > 100 and height > 100:
                images.add(urljoin(base_url, src))
        except (ValueError, TypeError):
            images.add(urljoin(base_url, src))
    return list(images)[:5]


async def crawl_and_extract(
    session: httpx.AsyncClient,
    url: str,
    semaphore: asyncio.Semaphore,
    depth: int = 0,
) -> dict:
    """Asynchronously fetch a URL and extract clean content + images."""
    async with semaphore:
        try:
            logger.info(f"Crawling URL: {url}")
            response = await session.get(url, timeout=15, follow_redirects=True)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            return {
                "content": clean_content(soup),
                # Full final URL so urljoin resolves relative image paths correctly.
                "images": extract_images(soup, str(response.url)),
                "final_url": str(response.url),
            }
        except Exception as e:
            logger.error(f"Failed to crawl or extract from {url}: {e}")
            return {"content": "", "images": [], "final_url": url}


# ─── Independent in-memory index ────────────────────────────────────────────

class IndependentIndex:
    """Simple in-memory inverted index for independent search capability."""

    _STOP_WORDS = {
        "the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
        "to", "for", "of", "and", "or", "but", "with", "by", "from", "as",
    }

    def __init__(self):
        self.documents: list[dict] = []
        self.inverted_index: dict[str, list[int]] = {}
        self._seed_index()

    def _seed_index(self):
        seed_docs = [
            {"title": "Python Programming Language", "url": "https://www.python.org",
             "snippet": "Python is a programming language that lets you work quickly and integrate systems more effectively.",
             "source_type": "web", "promoted": False},
            {"title": "FastAPI - Modern Python Web Framework", "url": "https://fastapi.tiangolo.com",
             "snippet": "FastAPI is a modern, fast, web framework for building APIs with Python 3.7+ based on standard type hints.",
             "source_type": "web", "promoted": False},
            {"title": "Vue.js - The Progressive JavaScript Framework", "url": "https://vuejs.org",
             "snippet": "Vue.js is an approachable, performant and versatile framework for building web user interfaces.",
             "source_type": "web", "promoted": False},
            {"title": "Redis - In-Memory Data Store", "url": "https://redis.io",
             "snippet": "Redis is an open source, in-memory data structure store, used as a database, cache, and message broker.",
             "source_type": "web", "promoted": False},
            {"title": "Tailwind CSS - Utility-First CSS Framework", "url": "https://tailwindcss.com",
             "snippet": "A utility-first CSS framework packed with classes to build any design directly in your markup.",
             "source_type": "web", "promoted": False},
            {"title": "Docker - Container Platform", "url": "https://www.docker.com",
             "snippet": "Docker helps developers build, share, and run container applications.",
             "source_type": "web", "promoted": False},
            {"title": "Mozilla Developer Network - Web Docs", "url": "https://developer.mozilla.org",
             "snippet": "Resources for developers, by developers. Documenting CSS, HTML, and JavaScript.",
             "source_type": "docs", "promoted": False},
            {"title": "GitHub - Code Hosting Platform", "url": "https://github.com",
             "snippet": "GitHub is where over 100 million developers shape the future of software together.",
             "source_type": "web", "promoted": False},
            {"title": "Hacker News - Tech News", "url": "https://news.ycombinator.com",
             "snippet": "Hacker News is a social news website focusing on computer science and entrepreneurship.",
             "source_type": "news", "promoted": False},
            {"title": "Reddit - Social Media Platform", "url": "https://www.reddit.com",
             "snippet": "Reddit is a network of communities where people dive into their interests, hobbies and passions.",
             "source_type": "social", "promoted": False},
            {"title": "Stack Overflow - Developer Community", "url": "https://stackoverflow.com",
             "snippet": "Stack Overflow is the largest, most trusted online community for developers to learn and share knowledge.",
             "source_type": "web", "promoted": False},
            {"title": "Linux Kernel Documentation", "url": "https://www.kernel.org/doc/html/latest/",
             "snippet": "Official documentation for the Linux kernel. Guides for kernel development and configuration.",
             "source_type": "docs", "promoted": False},
            {"title": "TechCrunch - Technology News", "url": "https://techcrunch.com",
             "snippet": "TechCrunch profiles startups and reviews new Internet products.",
             "source_type": "news", "promoted": False},
            {"title": "Twitter / X - Social Platform", "url": "https://x.com",
             "snippet": "X (formerly Twitter) is a social networking service for microblogging.",
             "source_type": "social", "promoted": False},
            {"title": "Unsplash - Free Images", "url": "https://unsplash.com",
             "snippet": "Beautiful, free images and photos gifted by the world's most generous community of photographers.",
             "source_type": "images",
             "thumbnail": "https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=200",
             "promoted": False},
            {"title": "Pexels - Free Stock Photos", "url": "https://www.pexels.com",
             "snippet": "Free stock photos and videos you can use everywhere. Millions of high-quality royalty free images.",
             "source_type": "images",
             "thumbnail": "https://images.pexels.com/photos/1287145/pexels-photo-1287145.jpeg?w=200",
             "promoted": False},
            {"title": "Privacy Tools - Encryption Against Surveillance", "url": "https://www.privacytools.io",
             "snippet": "PrivacyTools provides services, tools and knowledge to protect your privacy against mass surveillance.",
             "source_type": "web", "promoted": False},
            {"title": "Electronic Frontier Foundation", "url": "https://www.eff.org",
             "snippet": "The leading nonprofit defending digital privacy, free speech, and innovation.",
             "source_type": "news", "promoted": False},
        ]
        for doc in seed_docs:
            self.add_document(doc)

    def _tokenize(self, text: str) -> list[str]:
        text = re.sub(r"[^\w\s]", " ", text.lower())
        return [t for t in text.split() if t and t not in self._STOP_WORDS and len(t) > 1]

    def add_document(self, doc: dict):
        idx = len(self.documents)
        self.documents.append(doc)
        text = f"{doc.get('title', '')} {doc.get('snippet', '')} {doc.get('url', '')}"
        for token in self._tokenize(text):
            bucket = self.inverted_index.setdefault(token, [])
            if idx not in bucket:
                bucket.append(idx)

    def search(self, query: str, source_type: str = "web",
               hide_promoted: bool = True, limit: int = 20) -> list[dict]:
        tokens = self._tokenize(query)
        if not tokens:
            return []

        doc_scores: dict[int, float] = {}
        for token in tokens:
            for idx in self.inverted_index.get(token, []):
                doc_scores[idx] = doc_scores.get(idx, 0) + 1.0

        query_lower = query.lower()
        for idx, score in list(doc_scores.items()):
            doc = self.documents[idx]
            full_text = f"{doc.get('title', '')} {doc.get('snippet', '')}".lower()
            if query_lower in full_text:
                doc_scores[idx] = score + 3.0
            if query_lower in doc.get("title", "").lower():
                doc_scores[idx] += 5.0

        scored = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)

        results: list[dict] = []
        for idx, score in scored[:limit * 2]:
            doc = self.documents[idx]
            if hide_promoted and doc.get("promoted", False):
                continue
            if source_type != "web" and doc.get("source_type", "web") != source_type:
                continue
            results.append({**doc, "score": round(score, 2), "index_source": "independent"})
            if len(results) >= limit:
                break
        return results


# ─── External search providers (all return a common result shape) ───────────

async def search_connectnet(query: str, source_type: str = "web", limit: int = 20) -> list[dict]:
    """Query the connectnet independent search engine (JSON API)."""
    results: list[dict] = []
    try:
        async with httpx.AsyncClient(headers=BROWSER_HEADERS, timeout=20.0) as client:
            resp = await client.get(CONNECTNET_URL, params={"q": query, "format": "json"})
            resp.raise_for_status()
            data = resp.json()
            for r in data.get("results", [])[:limit]:
                url = r.get("url")
                if not url:
                    continue
                results.append({
                    "title": r.get("title", "Untitled"),
                    "url": url,
                    "snippet": r.get("content", ""),
                    "source_type": source_type,
                    "source_name": urlparse(url).netloc.replace("www.", ""),
                    "promoted": False,
                    "index_source": "connectnet",
                })
    except Exception as e:
        logger.warning(f"[connectnet] Search error: {e}")
    return results


async def search_bing(query: str, source_type: str = "web", limit: int = 20) -> list[dict]:
    """Search Bing as a fallback provider via scraping (no API key)."""
    results: list[dict] = []
    try:
        params = {"q": query, "count": str(limit)}
        if source_type == "images":
            url = "https://www.bing.com/images/search"
        elif source_type == "news":
            url = "https://www.bing.com/news/search"
            params["qft"] = "sortbydate"
        else:
            url = "https://www.bing.com/search"

        async with httpx.AsyncClient(headers=BROWSER_HEADERS, follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            if source_type == "images":
                for item in soup.select("a.iusc")[:limit]:
                    try:
                        m = json.loads(item.get("m", "{}"))
                        results.append({
                            "title": m.get("t", "Image"), "url": m.get("purl", "#"),
                            "snippet": m.get("desc", ""), "thumbnail": m.get("turl", ""),
                            "source_type": "images", "promoted": False, "index_source": "bing",
                        })
                    except (json.JSONDecodeError, AttributeError):
                        continue
            elif source_type == "news":
                for item in soup.select("div.news-card")[:limit]:
                    link = item.select_one("a.title")
                    snip = item.select_one("div.snippet")
                    if link:
                        results.append({
                            "title": link.get_text(strip=True), "url": link.get("href", "#"),
                            "snippet": snip.get_text(strip=True) if snip else "",
                            "source_type": "news", "promoted": False, "index_source": "bing",
                        })
            else:
                for item in soup.select("li.b_algo")[:limit]:
                    link = item.select_one("h2 a")
                    snip = item.select_one("div.b_caption p") or item.select_one("p")
                    if link:
                        href = link.get("href", "")
                        if href.startswith("http"):
                            results.append({
                                "title": link.get_text(strip=True), "url": href,
                                "snippet": snip.get_text(strip=True) if snip else "",
                                "source_type": "web", "promoted": False, "index_source": "bing",
                            })
    except Exception as e:
        logger.warning(f"[Bing] Search error: {e}")
    return results


async def search_google_proxy(query: str, source_type: str = "web", limit: int = 20) -> list[dict]:
    """Search Google via anonymous scraping proxy (no tracking passed through)."""
    results: list[dict] = []
    try:
        params = {"q": query, "num": str(limit), "hl": "en"}
        if source_type == "images":
            params["tbm"] = "isch"
        elif source_type == "news":
            params["tbm"] = "nws"

        async with httpx.AsyncClient(
            headers={**BROWSER_HEADERS, "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0"},
            follow_redirects=True, timeout=15.0,
        ) as client:
            resp = await client.get("https://www.google.com/search", params=params)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            if source_type == "images":
                for item in soup.select("div[data-id]")[:limit]:
                    img = item.select_one("img")
                    link = item.select_one("a[href*='imgurl']")
                    title = img.get("alt", "Image") if img else "Image"
                    thumb = img.get("src", "") if img else ""
                    target = "#"
                    if link:
                        href = link.get("href", "")
                        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                        target = parsed.get("imgurl", [href])[0]
                    results.append({
                        "title": title, "url": target, "snippet": "", "thumbnail": thumb,
                        "source_type": "images", "promoted": False, "index_source": "google_proxy",
                    })
            else:
                for item in soup.select("div.g, div[data-sokoban-container]")[:limit]:
                    link = item.select_one("a[href^='http']")
                    title_el = item.select_one("h3")
                    snip = (item.select_one("div[data-sncf]") or item.select_one("div.VwiC3b")
                            or item.select_one("span.aCOpRe") or item.select_one("div.IsZvec"))
                    if link and title_el:
                        href = link.get("href", "")
                        if "google.com" in href and "/search" in href:
                            continue
                        klasses = " ".join(item.get("class", []))
                        promoted = "commercial" in klasses or "ads" in klasses
                        results.append({
                            "title": title_el.get_text(strip=True), "url": href,
                            "snippet": snip.get_text(strip=True) if snip else "",
                            "source_type": source_type, "promoted": promoted,
                            "index_source": "google_proxy",
                        })
    except Exception as e:
        logger.warning(f"[Google Proxy] Search error: {e}")
    return results


async def search_duckduckgo(query: str, source_type: str = "web", limit: int = 20) -> list[dict]:
    """Search DuckDuckGo HTML endpoint (no tracking)."""
    results: list[dict] = []
    try:
        async with httpx.AsyncClient(headers=BROWSER_HEADERS, follow_redirects=True, timeout=15.0) as client:
            resp = await client.get("https://html.duckduckgo.com/html/", params={"q": query, "kl": "us-en"})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for item in soup.select("div.result")[:limit]:
                link = item.select_one("a.result__a")
                snip = item.select_one("a.result__snippet")
                if link:
                    href = link.get("href", "")
                    if "duckduckgo.com" in href:
                        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                        href = parsed.get("uddg", [href])[0]
                    results.append({
                        "title": link.get_text(strip=True),
                        "url": urllib.parse.unquote(href),
                        "snippet": snip.get_text(strip=True) if snip else "",
                        "source_type": source_type, "promoted": False, "index_source": "duckduckgo",
                    })
    except Exception as e:
        logger.warning(f"[DuckDuckGo] Search error: {e}")
    return results


# Registry so callers can pass a provider name as a string.
PROVIDERS = {
    "connectnet": search_connectnet,
    "bing": search_bing,
    "google_proxy": search_google_proxy,
    "duckduckgo": search_duckduckgo,
}


async def get_suggestions(query: str) -> list[str]:
    """Search suggestions without tracking (DuckDuckGo autocomplete)."""
    if len(query) < 2:
        return []
    try:
        async with httpx.AsyncClient(headers=BROWSER_HEADERS, timeout=5.0) as client:
            resp = await client.get("https://duckduckgo.com/ac/", params={"q": query, "type": "list"})
            data = resp.json()
            if isinstance(data, list) and len(data) > 1:
                return data[1][:8] if isinstance(data[1], list) else []
            if isinstance(data, list):
                return [i.get("phrase", "") for i in data if isinstance(i, dict)][:8]
    except Exception:
        pass
    return []


# ─── Anonymous proxy view ───────────────────────────────────────────────────

async def proxy_fetch(url: str) -> dict[str, Any]:
    """Fetch a URL anonymously, stripping trackers/ads, for an Anonymous View."""
    try:
        async with httpx.AsyncClient(headers={**BROWSER_HEADERS, "Referer": ""},
                                     follow_redirects=True, timeout=20.0) as client:
            resp = await client.get(url)
            content_type = resp.headers.get("content-type", "text/html")
            if "text/html" not in content_type:
                return {"content": resp.content, "content_type": content_type, "status": resp.status_code}

            soup = BeautifulSoup(resp.text, "html.parser")

            for script in soup.find_all("script"):
                blob = (script.get("src", "") + (script.string or "")).lower()
                if any(t in blob for t in [
                    "google-analytics", "googletagmanager", "facebook", "analytics",
                    "tracker", "pixel", "adsbygoogle", "doubleclick", "hotjar",
                    "mixpanel", "segment",
                ]):
                    script.decompose()

            for img in soup.find_all("img"):
                src = img.get("src", "")
                if "1x1" in str(img) or "pixel" in src.lower() or "track" in src.lower():
                    img.decompose()

            for el in soup.find_all(class_=re.compile(r"ad[s_-]|sponsor|promoted|banner", re.I)):
                el.decompose()

            parsed = urllib.parse.urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            if soup.head and not soup.head.find("base"):
                soup.head.insert(0, soup.new_tag("base", href=base_url, target="_blank"))

            notice = soup.new_tag("div")
            notice["style"] = ("position:fixed;top:0;left:0;right:0;z-index:99999;"
                               "background:linear-gradient(135deg,#1e1b4b,#312e81);"
                               "color:white;padding:8px 16px;font-size:12px;"
                               "display:flex;align-items:center;justify-content:space-between;"
                               "font-family:system-ui,sans-serif;box-shadow:0 2px 10px rgba(0,0,0,0.3);")
            notice.string = f"🔒 Anonymous View — No tracking, no cookies | {url}"
            if soup.body:
                soup.body.insert(0, notice)
                soup.body["style"] = f"{soup.body.get('style', '')}; padding-top: 40px !important;"

            return {"content": str(soup), "content_type": "text/html; charset=utf-8", "status": resp.status_code}
    except Exception as e:
        error_html = (
            f'<!DOCTYPE html><html><body style="font-family:system-ui;padding:40px;'
            f'background:#1d1d2e;color:white;"><h2>⚠️ Anonymous View Error</h2>'
            f'<p>Could not load: {url}</p><p style="color:#f87171;">{e}</p>'
            f'<p style="opacity:0.6;margin-top:20px;">The site may block proxy requests.</p>'
            f'</body></html>'
        )
        return {"content": error_html, "content_type": "text/html", "status": 500}


# ─── Singleton index + cache helpers ────────────────────────────────────────

_index = IndependentIndex()


def get_index() -> IndependentIndex:
    return _index


def _search_cache_key(query: str, source: str, provider: str, page: int) -> str:
    raw = f"{query}:{source}:{provider}:{page}"
    return f"search:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


def _context_cache_key(query: str, max_results: int) -> str:
    raw = f"{query}:{max_results}"
    return f"context:{hashlib.sha256(raw.encode()).hexdigest()}"


def _dedup_key(url: str) -> str:
    """Dedupe on normalized full URL so multiple pages per domain are kept."""
    p = urllib.parse.urlparse(url)
    netloc = p.netloc.replace("www.", "")
    return f"{netloc}{p.path.rstrip('/')}?{p.query}".rstrip("?")


# ─── Public entry point #1: ranked LINKS for a results UI ───────────────────

async def unified_search(
    query: str,
    source_type: str = "web",
    hide_promoted: bool = True,
    fallback_provider: str = "bing",
    limit: int = 20,
    page: int = 1,
    rankings: Optional[dict] = None,
    redis_client: Optional["AsyncRedis"] = None,
) -> dict[str, Any]:
    """
    Independent index first, then a fallback provider; merged, deduped, ranked.
    Returns {"results": [...], "meta": {...}} — links + metadata, no full text.
    """
    start = time.time()

    cache_key = None
    if redis_client and not rankings:  # rankings make results user-specific
        cache_key = _search_cache_key(query, source_type, fallback_provider, page)
        try:
            cached = await redis_client.get(cache_key)
            if cached:
                logger.info(f"CACHE HIT (search): '{query}'")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Redis read error: {e}")

    independent = _index.search(query, source_type=source_type,
                                hide_promoted=hide_promoted, limit=limit)

    provider_fn = PROVIDERS.get(fallback_provider)
    fallback = await provider_fn(query, source_type, limit) if provider_fn else []
    provider_name = f"independent + {fallback_provider}" if provider_fn else "independent"

    seen: set[str] = set()
    merged: list[dict] = []
    for r in independent:
        k = _dedup_key(r["url"])
        if k not in seen:
            seen.add(k)
            merged.append(r)
    for r in fallback:
        if hide_promoted and r.get("promoted", False):
            continue
        k = _dedup_key(r["url"])
        if k not in seen:
            seen.add(k)
            merged.append(r)

    if rankings:
        for r in merged:
            try:
                domain = urllib.parse.urlparse(r["url"]).netloc.replace("www.", "")
                r["score"] = r.get("score", 0) + (rankings.get(domain, 0) * 2.0)
            except Exception:
                pass
        merged.sort(key=lambda x: x.get("score", 0), reverse=True)

    payload = {
        "results": merged[:limit],
        "meta": {
            "query": query, "source": source_type, "provider": provider_name,
            "total": len(merged), "time_ms": round((time.time() - start) * 1000, 1),
            "privacy": "strict",
        },
    }

    if redis_client and cache_key:
        try:
            await redis_client.set(cache_key, json.dumps(payload), ex=SEARCH_CACHE_TTL)
            logger.info(f"CACHED (search): '{query}'")
        except Exception as e:
            logger.warning(f"Redis write error: {e}")

    return payload


# ─── Bridge: enrich existing search results with full crawled text ──────────

async def enrich_with_content(results: list[dict], top_n: Optional[int] = None) -> list[dict]:
    """
    Crawl full page text + images for an existing result list (e.g. from
    unified_search). Adds 'content' and 'images' to each crawled result.
    Only the first `top_n` results are crawled (default: all).
    """
    targets = results if top_n is None else results[:top_n]
    if not targets:
        return results

    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS_LIMIT)
    async with httpx.AsyncClient(headers=BROWSER_HEADERS) as client:
        crawled = await asyncio.gather(
            *[crawl_and_extract(client, r["url"], semaphore) for r in targets]
        )
    for r, c in zip(targets, crawled):
        r["content"] = c["content"] or r.get("snippet", "")
        r["images"] = c.get("images", [])
        r["final_url"] = c.get("final_url", r["url"])
    return results


# ─── Public entry point #2: crawled full TEXT for RAG / LLMs ────────────────

async def get_search_context(
    query: str,
    max_results: int = 5,
    provider: str = "connectnet",
    redis_client: Optional["AsyncRedis"] = None,
) -> list[dict]:
    """
    Search, then crawl results to extract clean full-text context.
    Returns [{title, url, source_name, content, images}] for RAG pipelines.
    """
    cache_key = None
    if redis_client:
        cache_key = _context_cache_key(query, max_results)
        try:
            cached = await redis_client.get(cache_key)
            if cached:
                logger.info(f"CACHE HIT (context): '{query}'")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Redis read error: {e}")
        logger.info(f"CACHE MISS (context): '{query}'")

    provider_fn = PROVIDERS.get(provider, search_connectnet)
    raw = await provider_fn(query, "web", max_results * 2)

    # Dedupe + cap to max_results.
    initial: list[dict] = []
    seen: set[str] = set()
    for r in raw:
        url = r.get("url")
        if url and url not in seen:
            seen.add(url)
            initial.append({
                "title": r.get("title", "Untitled"),
                "url": url,
                "source_name": r.get("source_name", urlparse(url).netloc.replace("www.", "")),
                "content": r.get("snippet", ""),
            })
        if len(initial) >= max_results:
            break

    if not initial:
        return []

    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS_LIMIT)
    async with httpx.AsyncClient(headers=BROWSER_HEADERS) as client:
        crawled = await asyncio.gather(
            *[crawl_and_extract(client, doc["url"], semaphore) for doc in initial]
        )

    final: list[dict] = []
    for doc, c in zip(initial, crawled):
        content = c["content"] or doc["content"]
        if content:
            final.append({
                "title": doc["title"], "url": doc["url"], "source_name": doc["source_name"],
                "content": content, "images": c.get("images", []),
            })

    logger.info(f"Processed {len(final)} documents for query: '{query}'")

    if redis_client and cache_key:
        try:
            await redis_client.set(cache_key, json.dumps(final), ex=SEARCH_CACHE_TTL)
            logger.info(f"CACHED (context): '{query}'")
        except Exception as e:
            logger.warning(f"Redis write error: {e}")

    return final



