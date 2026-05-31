import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote_plus, urlencode, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from redis.asyncio import Redis as AsyncRedis

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "DNT": "1",
    "Sec-GPC": "1",
}

SEARCH_ENGINE_URL = "https://connectnet.onrender.com/search"
CONCURRENT_REQUESTS_LIMIT = int(os.getenv("CONCURRENT_REQUESTS_LIMIT", "5"))
SEARCH_CACHE_TTL = int(os.getenv("SEARCH_CACHE_TTL", "3600"))
STRICT_PRIVACY_MODE = os.getenv("STRICT_PRIVACY_MODE", "true").lower() == "true"
CACHE_SEARCH_RESULTS = os.getenv("CACHE_SEARCH_RESULTS", "false").lower() == "true"
HIDE_PROMOTED_RESULTS = os.getenv("HIDE_PROMOTED_RESULTS", "true").lower() == "true"
FALLBACK_ENGINE_KEY = os.getenv("SEARCH_FALLBACK_ENGINE", "bing")
ANONYMOUS_VIEW_PREFIX = os.getenv("ANONYMOUS_VIEW_PREFIX", "/api/anonymous?url=")
GOOGLE_PROXY_SEARCH_URL = os.getenv("GOOGLE_PROXY_SEARCH_URL")

ENGINE_ENV_MAPPINGS = [
    ("searxng", "SearXNG", "SEARXNG_SEARCH_URL", "SearXNG JSON endpoint"),
    ("google", "Google via anonymous proxy", "GOOGLE_SEARCH_URL", "Google-compatible JSON endpoint"),
    ("bing", "Bing fallback", "BING_SEARCH_URL", "Bing-compatible JSON endpoint"),
    ("duckduckgo", "DuckDuckGo", "DUCKDUCKGO_SEARCH_URL", "DuckDuckGo-compatible JSON endpoint"),
    ("brave", "Brave", "BRAVE_SEARCH_URL", "Brave-compatible JSON endpoint"),
    ("yahoo", "Yahoo", "YAHOO_SEARCH_URL", "Yahoo-compatible JSON endpoint"),
    ("yandex", "Yandex", "YANDEX_SEARCH_URL", "Yandex-compatible JSON endpoint"),
    ("baidu", "Baidu", "BAIDU_SEARCH_URL", "Baidu-compatible JSON endpoint"),
    ("ecosia", "Ecosia", "ECOSIA_SEARCH_URL", "Ecosia-compatible JSON endpoint"),
    ("qwant", "Qwant", "QWANT_SEARCH_URL", "Qwant-compatible JSON endpoint"),
    ("startpage", "Startpage", "STARTPAGE_SEARCH_URL", "Startpage-compatible JSON endpoint"),
    ("mojeek", "Mojeek", "MOJEEK_SEARCH_URL", "Mojeek-compatible JSON endpoint"),
]

DEFAULT_BANGS = {
    "!w": {"name": "Wikipedia", "url": "https://en.wikipedia.org/w/index.php?search={query}"},
    "!yt": {"name": "YouTube", "url": "https://www.youtube.com/results?search_query={query}"},
    "!amazon": {"name": "Amazon", "url": "https://www.amazon.com/s?k={query}"},
    "!gh": {"name": "GitHub", "url": "https://github.com/search?q={query}"},
    "!so": {"name": "Stack Overflow", "url": "https://stackoverflow.com/search?q={query}"},
    "!x": {"name": "X", "url": "https://x.com/search?q={query}"},
}

PROMOTED_MARKERS = ("ad", "ads", "sponsored", "promoted", "promotion", "advertisement")
DEFAULT_SOURCE_TYPES = ("web", "docs", "images", "news", "social")


@dataclass(frozen=True)
class SearchEngine:
    """A JSON-producing search provider exposed to the frontend."""

    key: str
    name: str
    url: str
    description: str = ""
    kind: str = "web"

    def public_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "kind": self.kind,
        }


def _load_bangs() -> dict[str, dict[str, str]]:
    bangs = dict(DEFAULT_BANGS)
    raw_config = os.getenv("SEARCH_BANGS_JSON")
    if not raw_config:
        return bangs
    try:
        configured = json.loads(raw_config)
    except json.JSONDecodeError as exc:
        logging.warning("Invalid SEARCH_BANGS_JSON; using defaults: %s", exc)
        return bangs
    if not isinstance(configured, dict):
        logging.warning("SEARCH_BANGS_JSON must be an object; using defaults")
        return bangs
    for trigger, value in configured.items():
        if not isinstance(value, dict) or not value.get("url"):
            logging.warning("Skipping invalid bang config for trigger: %s", trigger)
            continue
        safe_trigger = str(trigger).strip()
        if not safe_trigger.startswith("!"):
            safe_trigger = f"!{safe_trigger}"
        bangs[safe_trigger] = {
            "name": str(value.get("name") or safe_trigger),
            "url": str(value["url"]),
        }
    return bangs


def _load_search_engines() -> dict[str, SearchEngine]:
    engines = {
        "connectnet": SearchEngine(
            key="connectnet",
            name="Independent index",
            url=SEARCH_ENGINE_URL,
            description="Default independent JSON search index",
            kind="web",
        )
    }

    if GOOGLE_PROXY_SEARCH_URL:
        engines["google-proxy"] = SearchEngine(
            key="google-proxy",
            name="Google via anonymous proxy",
            url=GOOGLE_PROXY_SEARCH_URL,
            description="Google-compatible results fetched through the configured anonymous proxy",
            kind="web",
        )

    for key, name, env_var, description in ENGINE_ENV_MAPPINGS:
        configured_url = os.getenv(env_var)
        if not configured_url:
            continue
        engines[key] = SearchEngine(
            key=key,
            name=name,
            url=configured_url,
            description=f"{description} from {env_var}",
            kind="web",
        )

    raw_config = os.getenv("SEARCH_ENGINES_JSON")
    if not raw_config:
        return engines

    try:
        configured = json.loads(raw_config)
    except json.JSONDecodeError as exc:
        logging.warning("Invalid SEARCH_ENGINES_JSON; using defaults: %s", exc)
        return engines

    if not isinstance(configured, dict):
        logging.warning("SEARCH_ENGINES_JSON must be an object; using defaults")
        return engines

    for key, value in configured.items():
        if not isinstance(value, dict) or not value.get("url"):
            logging.warning("Skipping invalid search engine config for key: %s", key)
            continue
        safe_key = str(key).strip().lower().replace(" ", "-")
        engines[safe_key] = SearchEngine(
            key=safe_key,
            name=str(value.get("name") or key),
            url=str(value["url"]),
            description=str(value.get("description") or "Custom JSON search API"),
            kind=str(value.get("kind") or "web"),
        )
    return engines


SEARCH_BANGS = _load_bangs()
SEARCH_ENGINES = _load_search_engines()
DEFAULT_ENGINE_KEY = os.getenv("DEFAULT_SEARCH_ENGINE", "connectnet")
if DEFAULT_ENGINE_KEY not in SEARCH_ENGINES:
    logging.warning("Unknown DEFAULT_SEARCH_ENGINE '%s'; falling back to connectnet", DEFAULT_ENGINE_KEY)
    DEFAULT_ENGINE_KEY = "connectnet"


def list_search_engines() -> list[dict[str, str]]:
    """Return frontend-safe search engine metadata."""
    return [engine.public_dict() for engine in SEARCH_ENGINES.values()]


def list_bangs() -> list[dict[str, str]]:
    """Return frontend-safe bang metadata."""
    return [{"trigger": trigger, **details} for trigger, details in SEARCH_BANGS.items()]


def get_search_engine(engine_key: str | None = None) -> SearchEngine:
    """Resolve a search engine key or raise ValueError for unknown engines."""
    selected = engine_key or DEFAULT_ENGINE_KEY
    if selected not in SEARCH_ENGINES:
        raise ValueError(f"Unknown search engine: {selected}")
    return SEARCH_ENGINES[selected]


def resolve_bang(query: str) -> Optional[dict[str, str]]:
    """Resolve a DuckDuckGo-style bang query without storing a user profile."""
    parts = query.strip().split(maxsplit=1)
    if not parts:
        return None
    trigger = parts[0].lower()
    bang = SEARCH_BANGS.get(trigger)
    if not bang:
        return None
    bang_query = parts[1] if len(parts) > 1 else ""
    target_url = bang["url"].format(query=quote_plus(bang_query))
    return {
        "trigger": trigger,
        "name": bang["name"],
        "query": bang_query,
        "url": target_url,
        "anonymous_url": build_anonymous_url(target_url),
    }


def build_anonymous_url(url: str) -> str:
    """Build an Anonymous View URL without tracking the user or setting cookies."""
    if ANONYMOUS_VIEW_PREFIX.startswith("/"):
        return f"{ANONYMOUS_VIEW_PREFIX}{quote_plus(url)}"
    return f"{ANONYMOUS_VIEW_PREFIX}{quote_plus(url)}"


def clean_content(soup: BeautifulSoup) -> str:
    """Strip irrelevant tags and extract clean text from a BeautifulSoup object."""
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return " ".join(text.split())


def extract_images(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Extract and prioritize relevant image URLs from a BeautifulSoup object."""
    images = set()
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


def _result_is_promoted(result: dict) -> bool:
    if result.get("is_ad") or result.get("ad") or result.get("promoted") or result.get("sponsored"):
        return True
    marker_text = " ".join(str(result.get(key, "")) for key in ("type", "category", "badge", "label", "source"))
    return marker_text.strip().lower() in PROMOTED_MARKERS


def _detect_source_type(result: dict, url: str) -> str:
    raw_type = str(result.get("source_type") or result.get("type") or result.get("category") or "").lower()
    if raw_type in DEFAULT_SOURCE_TYPES:
        return raw_type
    host = urlparse(url).netloc.lower()
    if any(domain in host for domain in ("youtube.", "x.com", "twitter.", "reddit.", "facebook.", "instagram.", "tiktok.")):
        return "social"
    if any(domain in host for domain in ("news.", "bbc.", "cnn.", "reuters.", "apnews.", "nytimes.")):
        return "news"
    if any(url.lower().endswith(ext) for ext in (".pdf", ".doc", ".docx", ".ppt", ".pptx")):
        return "docs"
    if result.get("image") or result.get("thumbnail") or result.get("img_src"):
        return "images"
    return "web"


def parse_source_types(source_types: str | None = None) -> list[str]:
    if not source_types:
        return list(DEFAULT_SOURCE_TYPES)
    selected = [item.strip().lower() for item in source_types.split(",") if item.strip()]
    return [item for item in selected if item in DEFAULT_SOURCE_TYPES] or list(DEFAULT_SOURCE_TYPES)


def parse_ranking(ranking: str | None = None) -> dict[str, int]:
    """Parse stateless per-request ranking such as 'docs.python.org:10,example.com:-5'."""
    if not ranking:
        return {}
    parsed = {}
    for item in ranking.split(","):
        if ":" not in item:
            continue
        domain, weight = item.rsplit(":", 1)
        try:
            parsed[domain.strip().lower()] = int(weight.strip())
        except ValueError:
            continue
    return parsed


def normalize_search_results(
    data: dict,
    max_results: int,
    source_types: list[str],
    hide_promoted: bool = True,
) -> list[dict]:
    """Normalize common JSON search formats into the app's ad-free document shape."""
    raw_results = data.get("results") or data.get("items") or data.get("webPages", {}).get("value") or []
    initial_documents = []
    unique_urls = set()

    for result in raw_results[: max_results * 4]:
        if hide_promoted and _result_is_promoted(result):
            continue
        url = result.get("url") or result.get("link") or result.get("displayUrl")
        if not url or url in unique_urls:
            continue
        source_type = _detect_source_type(result, url)
        if source_type not in source_types:
            continue
        unique_urls.add(url)
        images = [value for value in (result.get("image"), result.get("thumbnail"), result.get("img_src")) if value]
        initial_documents.append(
            {
                "title": result.get("title") or result.get("name") or "Untitled",
                "url": url,
                "source_name": urlparse(url).netloc.replace("www.", ""),
                "content": result.get("content") or result.get("snippet") or result.get("description") or "",
                "images": images[:5],
                "source_type": source_type,
                "promoted": False,
                "anonymous_url": build_anonymous_url(url),
            }
        )
        if len(initial_documents) >= max_results:
            break
    return initial_documents


def apply_personalized_ranking(documents: list[dict], ranking: dict[str, int]) -> list[dict]:
    """Apply stateless, user-supplied ranking without creating a server-side profile."""
    if not ranking:
        return documents

    def score(document: dict) -> int:
        host = document.get("source_name", "").lower()
        return max((weight for domain, weight in ranking.items() if domain in host), default=0)

    return sorted(documents, key=score, reverse=True)


async def crawl_and_extract(
    session: httpx.AsyncClient,
    url: str,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Asynchronously fetch a URL without cookies and extract content/image metadata."""
    async with semaphore:
        try:
            logging.info("Crawling URL host: %s", urlparse(url).netloc)
            response = await session.get(url, timeout=15, follow_redirects=True)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            return {
                "content": clean_content(soup),
                "images": extract_images(soup, str(response.url)),
                "final_url": str(response.url),
            }
        except Exception as exc:
            logging.error("Failed to crawl or extract host %s: %s", urlparse(url).netloc, exc)
            return {"content": "", "images": [], "final_url": url}


async def _query_engine(
    engine: SearchEngine,
    query: str,
    max_results: int,
    source_types: list[str],
    hide_promoted: bool,
    extra_params: Optional[dict[str, str]] = None,
) -> list[dict]:
    search_params = {"q": query, "format": "json", "categories": ",".join(source_types)}
    if extra_params:
        search_params.update(extra_params)

    try:
        async with httpx.AsyncClient(headers=BROWSER_HEADERS, timeout=20, cookies={}) as client:
            logging.info("Querying %s search instance", engine.key)
            response = await client.get(engine.url, params=search_params)
            response.raise_for_status()
            documents = normalize_search_results(response.json(), max_results, source_types, hide_promoted)
            for document in documents:
                document["engine"] = engine.key
            return documents
    except Exception as exc:
        logging.error("Error during %s web search: %s", engine.key, exc)
        return []


async def get_search_context(
    query: str,
    max_results: int = 5,
    redis_client: Optional[AsyncRedis] = None,
    engine_key: str | None = None,
    crawl_pages: bool = True,
    extra_params: Optional[dict[str, str]] = None,
    hide_promoted: bool = HIDE_PROMOTED_RESULTS,
    source_types: Optional[list[str]] = None,
    ranking: Optional[dict[str, int]] = None,
    use_fallback: bool = True,
) -> list[dict]:
    """Perform a private, ad-free web search with optional crawling and fallback."""
    bang = resolve_bang(query)
    if bang:
        return [
            {
                "title": f"{bang['name']} bang search",
                "url": bang["url"],
                "source_name": bang["name"],
                "content": f"Open {bang['name']} for '{bang['query']}' using bang {bang['trigger']}.",
                "images": [],
                "engine": "bang",
                "source_type": "web",
                "promoted": False,
                "anonymous_url": bang["anonymous_url"],
            }
        ]

    selected_sources = source_types or list(DEFAULT_SOURCE_TYPES)
    if engine_key == "all":
        engines_to_query = list(SEARCH_ENGINES.values())
        engine = SearchEngine(
            key="all",
            name="All configured sources",
            url="",
            description="Merged web, docs, images, news, and social results",
        )
    else:
        engine = get_search_engine(engine_key)
        engines_to_query = [engine]
    cache_key = None
    allow_cache = CACHE_SEARCH_RESULTS and not STRICT_PRIVACY_MODE
    cache_payload = {
        "engine": engine.key,
        "query_hash": hashlib.sha256(query.encode()).hexdigest(),
        "max_results": max_results,
        "crawl_pages": crawl_pages,
        "extra_params": extra_params,
        "hide_promoted": hide_promoted,
        "source_types": selected_sources,
        "ranking": ranking,
    }
    if redis_client and allow_cache:
        query_hash = hashlib.sha256(json.dumps(cache_payload, sort_keys=True).encode()).hexdigest()
        cache_key = f"search:{query_hash}"
        try:
            cached_result = await redis_client.get(cache_key)
            if cached_result:
                logging.info("CACHE HIT for %s private search", engine.key)
                return json.loads(cached_result)
        except Exception as exc:
            logging.warning("Redis cache read error: %s", exc)

    engine_results = await asyncio.gather(
        *[
            _query_engine(engine_item, query, max_results, selected_sources, hide_promoted, extra_params)
            for engine_item in engines_to_query
        ]
    )
    initial_documents = []
    seen_urls = set()
    for documents in engine_results:
        for document in documents:
            if document["url"] in seen_urls:
                continue
            seen_urls.add(document["url"])
            initial_documents.append(document)
            if len(initial_documents) >= max_results:
                break
        if len(initial_documents) >= max_results:
            break

    if not initial_documents and use_fallback and FALLBACK_ENGINE_KEY in SEARCH_ENGINES and FALLBACK_ENGINE_KEY != engine.key:
        fallback_engine = get_search_engine(FALLBACK_ENGINE_KEY)
        initial_documents = await _query_engine(
            fallback_engine,
            query,
            max_results,
            selected_sources,
            hide_promoted,
            extra_params,
        )

    if not initial_documents:
        return []

    crawl_results = [{"content": "", "images": []} for _ in initial_documents]
    if crawl_pages:
        semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS_LIMIT)
        async with httpx.AsyncClient(headers=BROWSER_HEADERS, cookies={}) as crawl_client:
            tasks = [crawl_and_extract(crawl_client, doc["url"], semaphore) for doc in initial_documents]
            crawl_results = await asyncio.gather(*tasks)

    final_documents = []
    for doc, crawled in zip(initial_documents, crawl_results):
        content = crawled["content"] if crawled["content"] else doc["content"]
        if content:
            merged_images = crawled.get("images", []) if crawl_pages else []
            final_documents.append(
                {
                    "title": doc["title"],
                    "url": doc["url"],
                    "source_name": doc["source_name"],
                    "content": content,
                    "images": (merged_images or doc.get("images", []))[:5],
                    "engine": doc.get("engine", engine.key),
                    "source_type": doc["source_type"],
                    "promoted": False,
                    "anonymous_url": doc["anonymous_url"],
                }
            )

    final_documents = apply_personalized_ranking(final_documents, ranking or {})
    logging.info("Processed %s private documents for %s", len(final_documents), engine.key)

    if redis_client and cache_key and allow_cache:
        try:
            await redis_client.set(cache_key, json.dumps(final_documents), ex=SEARCH_CACHE_TTL)
            logging.info("Cached private search result for engine %s", engine.key)
        except Exception as exc:
            logging.warning("Redis cache write error: %s", exc)

    return final_documents[:max_results]
