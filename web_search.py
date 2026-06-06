"""
web_search.py - Multi-source search engine with independent index,
Bing fallback, Google proxy, and anonymous proxy view.
No user tracking. No IP logging. No cookies.
"""

import hashlib
import json
import re
import time
import urllib.parse
from typing import Any

import httpx
from bs4 import BeautifulSoup


# ─── Independent Search Index ───────────────────────────────────────────────

class IndependentIndex:
    """Simple in-memory inverted index for independent search capability."""

    def __init__(self):
        self.documents: list[dict] = []
        self.inverted_index: dict[str, list[int]] = {}
        self._seed_index()

    def _seed_index(self):
        """Seed with initial documents to demonstrate independent indexing."""
        seed_docs = [
            {
                "title": "Python Programming Language",
                "url": "https://www.python.org",
                "snippet": "Python is a programming language that lets you work quickly and integrate systems more effectively. Open source and community-driven.",
                "source_type": "web",
                "promoted": False,
            },
            {
                "title": "FastAPI - Modern Python Web Framework",
                "url": "https://fastapi.tiangolo.com",
                "snippet": "FastAPI is a modern, fast (high-performance), web framework for building APIs with Python 3.7+ based on standard Python type hints.",
                "source_type": "web",
                "promoted": False,
            },
            {
                "title": "Vue.js - The Progressive JavaScript Framework",
                "url": "https://vuejs.org",
                "snippet": "Vue.js is an approachable, performant and versatile framework for building web user interfaces.",
                "source_type": "web",
                "promoted": False,
            },
            {
                "title": "Redis - In-Memory Data Store",
                "url": "https://redis.io",
                "snippet": "Redis is an open source, in-memory data structure store, used as a database, cache, and message broker.",
                "source_type": "web",
                "promoted": False,
            },
            {
                "title": "Tailwind CSS - Utility-First CSS Framework",
                "url": "https://tailwindcss.com",
                "snippet": "A utility-first CSS framework packed with classes that can be composed to build any design, directly in your markup.",
                "source_type": "web",
                "promoted": False,
            },
            {
                "title": "Docker - Container Platform",
                "url": "https://www.docker.com",
                "snippet": "Docker is a platform designed to help developers build, share, and run container applications.",
                "source_type": "web",
                "promoted": False,
            },
            {
                "title": "Mozilla Developer Network - Web Docs",
                "url": "https://developer.mozilla.org",
                "snippet": "Resources for developers, by developers. Documenting web technologies including CSS, HTML, and JavaScript.",
                "source_type": "docs",
                "promoted": False,
            },
            {
                "title": "GitHub - Code Hosting Platform",
                "url": "https://github.com",
                "snippet": "GitHub is where over 100 million developers shape the future of software together. Collaborate, review, manage projects.",
                "source_type": "web",
                "promoted": False,
            },
            {
                "title": "Hacker News - Tech News",
                "url": "https://news.ycombinator.com",
                "snippet": "Hacker News is a social news website focusing on computer science and entrepreneurship.",
                "source_type": "news",
                "promoted": False,
            },
            {
                "title": "Reddit - Social Media Platform",
                "url": "https://www.reddit.com",
                "snippet": "Reddit is a network of communities where people can dive into their interests, hobbies and passions.",
                "source_type": "social",
                "promoted": False,
            },
            {
                "title": "Stack Overflow - Developer Community",
                "url": "https://stackoverflow.com",
                "snippet": "Stack Overflow is the largest, most trusted online community for developers to learn and share knowledge.",
                "source_type": "web",
                "promoted": False,
            },
            {
                "title": "Linux Kernel Documentation",
                "url": "https://www.kernel.org/doc/html/latest/",
                "snippet": "Official documentation for the Linux kernel. Comprehensive guides for kernel development and configuration.",
                "source_type": "docs",
                "promoted": False,
            },
            {
                "title": "TechCrunch - Technology News",
                "url": "https://techcrunch.com",
                "snippet": "TechCrunch is a leading technology media property, dedicated to profiling startups and reviewing new Internet products.",
                "source_type": "news",
                "promoted": False,
            },
            {
                "title": "Twitter / X - Social Platform",
                "url": "https://x.com",
                "snippet": "X (formerly Twitter) is a social networking service for microblogging and social networking.",
                "source_type": "social",
                "promoted": False,
            },
            {
                "title": "Unsplash - Free Images",
                "url": "https://unsplash.com",
                "snippet": "Beautiful, free images and photos gifted by the world's most generous community of photographers.",
                "source_type": "images",
                "thumbnail": "https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=200",
                "promoted": False,
            },
            {
                "title": "Pexels - Free Stock Photos",
                "url": "https://www.pexels.com",
                "snippet": "Free stock photos and videos you can use everywhere. Browse millions of high-quality royalty free images.",
                "source_type": "images",
                "thumbnail": "https://images.pexels.com/photos/1287145/pexels-photo-1287145.jpeg?w=200",
                "promoted": False,
            },
            {
                "title": "Privacy Tools - Encryption Against Surveillance",
                "url": "https://www.privacytools.io",
                "snippet": "PrivacyTools provides services, tools and knowledge to protect your privacy against global mass surveillance.",
                "source_type": "web",
                "promoted": False,
            },
            {
                "title": "Electronic Frontier Foundation",
                "url": "https://www.eff.org",
                "snippet": "The leading nonprofit defending digital privacy, free speech, and innovation through impact litigation and activism.",
                "source_type": "news",
                "promoted": False,
            },
        ]
        for doc in seed_docs:
            self.add_document(doc)

    def _tokenize(self, text: str) -> list[str]:
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        tokens = text.split()
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'in', 'on', 'at',
                       'to', 'for', 'of', 'and', 'or', 'but', 'with', 'by', 'from', 'as'}
        return [t for t in tokens if t and t not in stop_words and len(t) > 1]

    def add_document(self, doc: dict):
        idx = len(self.documents)
        self.documents.append(doc)
        text = f"{doc.get('title', '')} {doc.get('snippet', '')} {doc.get('url', '')}"
        tokens = self._tokenize(text)
        for token in tokens:
            if token not in self.inverted_index:
                self.inverted_index[token] = []
            if idx not in self.inverted_index[token]:
                self.inverted_index[token].append(idx)

    def search(self, query: str, source_type: str = "web",
               hide_promoted: bool = True, limit: int = 20) -> list[dict]:
        tokens = self._tokenize(query)
        if not tokens:
            return []

        doc_scores: dict[int, float] = {}
        for token in tokens:
            matching_indices = self.inverted_index.get(token, [])
            for idx in matching_indices:
                doc_scores[idx] = doc_scores.get(idx, 0) + 1.0

        # Boost for exact phrase match
        query_lower = query.lower()
        for idx, score in list(doc_scores.items()):
            doc = self.documents[idx]
            full_text = f"{doc.get('title', '')} {doc.get('snippet', '')}".lower()
            if query_lower in full_text:
                doc_scores[idx] = score + 3.0
            # Title match gets extra boost
            if query_lower in doc.get('title', '').lower():
                doc_scores[idx] += 5.0

        scored = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in scored[:limit * 2]:  # Get more, then filter
            doc = self.documents[idx]

            if hide_promoted and doc.get("promoted", False):
                continue
            if source_type != "web" and doc.get("source_type", "web") != source_type:
                continue

            results.append({
                **doc,
                "score": round(score, 2),
                "index_source": "independent",
            })

            if len(results) >= limit:
                break

        return results


# ─── External Search Providers ──────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


async def search_bing(query: str, source_type: str = "web", limit: int = 20) -> list[dict]:
    """Search Bing as fallback provider via scraping (no API key needed)."""
    results = []
    try:
        params = {"q": query, "count": str(limit)}
        if source_type == "images":
            url = "https://www.bing.com/images/search"
        elif source_type == "news":
            url = "https://www.bing.com/news/search"
            params["qft"] = "sortbydate"
        else:
            url = "https://www.bing.com/search"

        async with httpx.AsyncClient(
            headers=HEADERS,
            follow_redirects=True,
            timeout=15.0
        ) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            if source_type == "images":
                for item in soup.select("a.iusc")[:limit]:
                    try:
                        m_data = json.loads(item.get("m", "{}"))
                        results.append({
                            "title": m_data.get("t", "Image"),
                            "url": m_data.get("purl", "#"),
                            "snippet": m_data.get("desc", ""),
                            "thumbnail": m_data.get("turl", ""),
                            "source_type": "images",
                            "promoted": False,
                            "index_source": "bing",
                        })
                    except (json.JSONDecodeError, AttributeError):
                        continue
            elif source_type == "news":
                for item in soup.select("div.news-card")[:limit]:
                    link = item.select_one("a.title")
                    snippet_el = item.select_one("div.snippet")
                    if link:
                        results.append({
                            "title": link.get_text(strip=True),
                            "url": link.get("href", "#"),
                            "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                            "source_type": "news",
                            "promoted": False,
                            "index_source": "bing",
                        })
            else:
                for item in soup.select("li.b_algo")[:limit]:
                    link = item.select_one("h2 a")
                    snippet_el = item.select_one("div.b_caption p") or item.select_one("p")
                    if link:
                        href = link.get("href", "")
                        if href and href.startswith("http"):
                            results.append({
                                "title": link.get_text(strip=True),
                                "url": href,
                                "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                                "source_type": "web",
                                "promoted": False,
                                "index_source": "bing",
                            })
    except Exception as e:
        print(f"[Bing] Search error: {e}")

    return results


async def search_google_proxy(query: str, source_type: str = "web", limit: int = 20) -> list[dict]:
    """Search Google via anonymous scraping proxy (no tracking passed through)."""
    results = []
    try:
        params = {"q": query, "num": str(limit), "hl": "en"}
        if source_type == "images":
            params["tbm"] = "isch"
        elif source_type == "news":
            params["tbm"] = "nws"

        async with httpx.AsyncClient(
            headers={**HEADERS, "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0"},
            follow_redirects=True,
            timeout=15.0,
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
                    target_url = "#"
                    if link:
                        href = link.get("href", "")
                        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                        target_url = parsed.get("imgurl", [href])[0]
                    results.append({
                        "title": title,
                        "url": target_url,
                        "snippet": "",
                        "thumbnail": thumb,
                        "source_type": "images",
                        "promoted": False,
                        "index_source": "google_proxy",
                    })
            else:
                for item in soup.select("div.g, div[data-sokoban-container]")[:limit]:
                    link = item.select_one("a[href^='http']")
                    title_el = item.select_one("h3")
                    snippet_el = (
                        item.select_one("div[data-sncf]")
                        or item.select_one("div.VwiC3b")
                        or item.select_one("span.aCOpRe")
                        or item.select_one("div.IsZvec")
                    )

                    if link and title_el:
                        href = link.get("href", "")
                        # Filter out Google internal links
                        if "google.com" in href and "/search" in href:
                            continue
                        # Filter promoted/ad results
                        parent_classes = " ".join(item.get("class", []))
                        is_promoted = "commercial" in parent_classes or "ads" in parent_classes

                        results.append({
                            "title": title_el.get_text(strip=True),
                            "url": href,
                            "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                            "source_type": source_type,
                            "promoted": is_promoted,
                            "index_source": "google_proxy",
                        })

    except Exception as e:
        print(f"[Google Proxy] Search error: {e}")

    return results


async def search_duckduckgo(query: str, source_type: str = "web", limit: int = 20) -> list[dict]:
    """Search DuckDuckGo HTML version (no tracking)."""
    results = []
    try:
        params = {"q": query, "kl": "us-en"}
        async with httpx.AsyncClient(
            headers=HEADERS,
            follow_redirects=True,
            timeout=15.0,
        ) as client:
            resp = await client.get("https://html.duckduckgo.com/html/", params=params)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            for item in soup.select("div.result")[:limit]:
                link = item.select_one("a.result__a")
                snippet_el = item.select_one("a.result__snippet")
                if link:
                    href = link.get("href", "")
                    # DuckDuckGo uses redirect URLs
                    if "duckduckgo.com" in href:
                        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                        href = parsed.get("uddg", [href])[0]

                    results.append({
                        "title": link.get_text(strip=True),
                        "url": urllib.parse.unquote(href),
                        "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                        "source_type": source_type,
                        "promoted": False,
                        "index_source": "duckduckgo",
                    })
    except Exception as e:
        print(f"[DuckDuckGo] Search error: {e}")

    return results


async def get_suggestions(query: str) -> list[str]:
    """Get search suggestions without tracking."""
    if len(query) < 2:
        return []
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=5.0) as client:
            resp = await client.get(
                "https://duckduckgo.com/ac/",
                params={"q": query, "type": "list"},
            )
            data = resp.json()
            if isinstance(data, list) and len(data) > 1:
                return data[1][:8] if isinstance(data[1], list) else []
            if isinstance(data, list):
                return [item.get("phrase", "") for item in data if isinstance(item, dict)][:8]
    except Exception:
        pass
    return []


async def proxy_fetch(url: str) -> dict[str, Any]:
    """Fetch a URL anonymously for the Anonymous View feature."""
    try:
        async with httpx.AsyncClient(
            headers={**HEADERS, "Referer": ""},
            follow_redirects=True,
            timeout=20.0,
        ) as client:
            resp = await client.get(url)
            content_type = resp.headers.get("content-type", "text/html")

            if "text/html" in content_type:
                soup = BeautifulSoup(resp.text, "html.parser")

                # Remove tracking scripts, ads, analytics
                for script in soup.find_all("script"):
                    src = script.get("src", "").lower()
                    text = script.string or ""
                    if any(tracker in src + text.lower() for tracker in [
                        "google-analytics", "googletagmanager", "facebook",
                        "analytics", "tracker", "pixel", "adsbygoogle",
                        "doubleclick", "hotjar", "mixpanel", "segment",
                    ]):
                        script.decompose()

                # Remove tracking pixels
                for img in soup.find_all("img"):
                    src = img.get("src", "")
                    if "1x1" in str(img) or "pixel" in src.lower() or "track" in src.lower():
                        img.decompose()

                # Remove ad containers
                for el in soup.find_all(class_=re.compile(r'ad[s_-]|sponsor|promoted|banner', re.I)):
                    el.decompose()

                # Inject base tag for relative URLs
                base_url = f"{urllib.parse.urlparse(url).scheme}://{urllib.parse.urlparse(url).netloc}"
                if soup.head:
                    existing_base = soup.head.find("base")
                    if not existing_base:
                        base_tag = soup.new_tag("base", href=base_url, target="_blank")
                        soup.head.insert(0, base_tag)

                # Add privacy notice bar
                notice = soup.new_tag("div")
                notice["style"] = ("position:fixed;top:0;left:0;right:0;z-index:99999;"
                                   "background:linear-gradient(135deg,#1e1b4b,#312e81);"
                                   "color:white;padding:8px 16px;font-size:12px;"
                                   "display:flex;align-items:center;justify-content:space-between;"
                                   "font-family:system-ui,sans-serif;box-shadow:0 2px 10px rgba(0,0,0,0.3);")
                notice.string = f"🔒 Anonymous View via OKNLAB Search — No tracking, no cookies | {url}"
                if soup.body:
                    soup.body.insert(0, notice)
                    # Add padding to body
                    body_style = soup.body.get("style", "")
                    soup.body["style"] = f"{body_style}; padding-top: 40px !important;"

                return {
                    "content": str(soup),
                    "content_type": "text/html; charset=utf-8",
                    "status": resp.status_code,
                }
            else:
                return {
                    "content": resp.content,
                    "content_type": content_type,
                    "status": resp.status_code,
                }
    except Exception as e:
        error_html = f"""<!DOCTYPE html><html><body style="font-family:system-ui;padding:40px;background:#1d1d2e;color:white;">
        <h2>⚠️ Anonymous View Error</h2><p>Could not load: {url}</p><p style="color:#f87171;">{str(e)}</p>
        <p style="opacity:0.6;margin-top:20px;">This may be due to the site blocking proxy requests.</p>
        </body></html>"""
        return {"content": error_html, "content_type": "text/html", "status": 500}


# ─── Unified Search Orchestrator ────────────────────────────────────────────

# Singleton index
_index = IndependentIndex()


def get_index() -> IndependentIndex:
    return _index


def generate_cache_key(query: str, source: str, provider: str, page: int) -> str:
    raw = f"{query}:{source}:{provider}:{page}"
    return f"search:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


async def unified_search(
    query: str,
    source_type: str = "web",
    hide_promoted: bool = True,
    fallback_provider: str = "bing",
    limit: int = 20,
    rankings: dict | None = None,
) -> dict[str, Any]:
    """
    Unified search: Independent index first, then fallback provider.
    Results are merged, deduplicated, and optionally re-ranked.
    """
    start = time.time()

    # 1. Search independent index
    independent_results = _index.search(
        query, source_type=source_type,
        hide_promoted=hide_promoted, limit=limit
    )

    # 2. Fallback provider search
    fallback_results = []
    provider_name = "independent"

    if fallback_provider == "bing":
        fallback_results = await search_bing(query, source_type, limit)
        provider_name = "independent + bing"
    elif fallback_provider == "google_proxy":
        fallback_results = await search_google_proxy(query, source_type, limit)
        provider_name = "independent + google (proxy)"
    elif fallback_provider == "duckduckgo":
        fallback_results = await search_duckduckgo(query, source_type, limit)
        provider_name = "independent + duckduckgo"

    # 3. Merge and deduplicate
    seen_urls = set()
    merged = []

    # Independent results first (priority)
    for r in independent_results:
        normalized = urllib.parse.urlparse(r["url"]).netloc.replace("www.", "")
        if normalized not in seen_urls:
            seen_urls.add(normalized)
            merged.append(r)

    # Then fallback results
    for r in fallback_results:
        normalized = urllib.parse.urlparse(r["url"]).netloc.replace("www.", "")
        if normalized not in seen_urls:
            seen_urls.add(normalized)
            if hide_promoted and r.get("promoted", False):
                continue
            merged.append(r)

    # 4. Apply personalized rankings (client-provided, never stored)
    if rankings:
        for result in merged:
            try:
                domain = urllib.parse.urlparse(result["url"]).netloc.replace("www.", "")
                boost = rankings.get(domain, 0)
                result["score"] = result.get("score", 0) + (boost * 2.0)
            except Exception:
                pass
        merged.sort(key=lambda x: x.get("score", 0), reverse=True)

    elapsed = round((time.time() - start) * 1000, 1)

    return {
        "results": merged[:limit],
        "meta": {
            "query": query,
            "source": source_type,
            "provider": provider_name,
            "total": len(merged),
            "time_ms": elapsed,
            "privacy": "strict",
        },
    }
