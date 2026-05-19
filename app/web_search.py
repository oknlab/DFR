import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from redis.asyncio import Redis as AsyncRedis

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

# JSON-compatible search endpoint. It is expected to return a payload containing a
# top-level "results" array with title, url, and content/snippet fields.
SEARCH_ENGINE_URL = "https://connectnet.onrender.com/search"
SEARCH_ENGINE_ID = "014662525286492529401:2upbuo2qpni"
GOOGLE_CSE_URL = "https://cse.google.com/cse?cx=014662525286492529401%3A2upbuo2qpni"

CONCURRENT_REQUESTS_LIMIT = 5
SEARCH_CACHE_TTL = 3600  # Cache search results for 1 hour

ENGINE_ENV_MAPPINGS = [
    ("searxng", "SearXNG", "SEARXNG_SEARCH_URL", "SearXNG JSON endpoint"),
    ("google", "Google JSON", "GOOGLE_SEARCH_URL", "Google-compatible JSON endpoint"),
    ("bing", "Bing JSON", "BING_SEARCH_URL", "Bing-compatible JSON endpoint"),
    ("duckduckgo", "DuckDuckGo JSON", "DUCKDUCKGO_SEARCH_URL", "DuckDuckGo-compatible JSON endpoint"),
    ("brave", "Brave JSON", "BRAVE_SEARCH_URL", "Brave-compatible JSON endpoint"),
    ("yahoo", "Yahoo JSON", "YAHOO_SEARCH_URL", "Yahoo-compatible JSON endpoint"),
    ("yandex", "Yandex JSON", "YANDEX_SEARCH_URL", "Yandex-compatible JSON endpoint"),
    ("baidu", "Baidu JSON", "BAIDU_SEARCH_URL", "Baidu-compatible JSON endpoint"),
    ("ecosia", "Ecosia JSON", "ECOSIA_SEARCH_URL", "Ecosia-compatible JSON endpoint"),
    ("qwant", "Qwant JSON", "QWANT_SEARCH_URL", "Qwant-compatible JSON endpoint"),
    ("startpage", "Startpage JSON", "STARTPAGE_SEARCH_URL", "Startpage-compatible JSON endpoint"),
    ("mojeek", "Mojeek JSON", "MOJEEK_SEARCH_URL", "Mojeek-compatible JSON endpoint"),
]


@dataclass(frozen=True)
class SearchEngine:
    """A JSON-producing search provider exposed to the frontend."""

    key: str
    name: str
    url: str
    description: str = ""

    def public_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
        }


DEFAULT_SEARCH_ENGINES = {
    "connectnet": SearchEngine(
        key="connectnet",
        name="ConnectNet",
        url=SEARCH_ENGINE_URL,
        description="Default JSON search API",
    ),
}


def _load_search_engines() -> dict[str, SearchEngine]:
    """Load configured engines from SEARCH_ENGINES_JSON and merge with defaults.

    SEARCH_ENGINES_JSON accepts a JSON object such as:
    {
      "local": {"name": "Local SearXNG", "url": "http://searxng:8080/search"},
      "company": {"name": "Company Search", "url": "https://example.com/search"}
    }
    """
    engines = dict(DEFAULT_SEARCH_ENGINES)
    for key, name, env_var, description in ENGINE_ENV_MAPPINGS:
        configured_url = os.getenv(env_var)
        if not configured_url:
            continue
        engines[key] = SearchEngine(
            key=key,
            name=name,
            url=configured_url,
            description=f"{description} from {env_var}",
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
        )
    return engines


SEARCH_ENGINES = _load_search_engines()
DEFAULT_ENGINE_KEY = os.getenv("DEFAULT_SEARCH_ENGINE", "connectnet")
if DEFAULT_ENGINE_KEY not in SEARCH_ENGINES:
    logging.warning("Unknown DEFAULT_SEARCH_ENGINE '%s'; falling back to connectnet", DEFAULT_ENGINE_KEY)
    DEFAULT_ENGINE_KEY = "connectnet"


def list_search_engines() -> list[dict[str, str]]:
    """Return frontend-safe search engine metadata."""
    return [engine.public_dict() for engine in SEARCH_ENGINES.values()]


def get_search_engine(engine_key: str | None = None) -> SearchEngine:
    """Resolve a search engine key or raise ValueError for unknown engines."""
    selected = engine_key or DEFAULT_ENGINE_KEY
    if selected not in SEARCH_ENGINES:
        raise ValueError(f"Unknown search engine: {selected}")
    return SEARCH_ENGINES[selected]


def clean_content(soup: BeautifulSoup) -> str:
    """Strip irrelevant tags and extract clean text from a BeautifulSoup object."""
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
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


def normalize_search_results(data: dict, max_results: int) -> list[dict]:
    """Normalize common JSON search formats into the app's document shape."""
    raw_results = data.get("results") or data.get("items") or []
    initial_documents = []
    unique_urls = set()

    for result in raw_results[: max_results * 2]:
        url = result.get("url") or result.get("link")
        if not url or url in unique_urls:
            continue
        unique_urls.add(url)
        initial_documents.append(
            {
                "title": result.get("title") or result.get("name") or "Untitled",
                "url": url,
                "source_name": urlparse(url).netloc.replace("www.", ""),
                "content": result.get("content") or result.get("snippet") or result.get("description") or "",
            }
        )
        if len(initial_documents) >= max_results:
            break
    return initial_documents


async def crawl_and_extract(
    session: httpx.AsyncClient,
    url: str,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Asynchronously fetch a URL and extract content and image metadata."""
    async with semaphore:
        try:
            logging.info("Crawling URL: %s", url)
            response = await session.get(url, timeout=15, follow_redirects=True)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            return {
                "content": clean_content(soup),
                "images": extract_images(soup, str(response.url)),
                "final_url": str(response.url),
            }
        except Exception as exc:
            logging.error("Failed to crawl or extract from %s: %s", url, exc)
            return {"content": "", "images": [], "final_url": url}


async def get_search_context(
    query: str,
    max_results: int = 5,
    redis_client: Optional[AsyncRedis] = None,
    engine_key: str | None = None,
    crawl_pages: bool = True,
    extra_params: Optional[dict[str, str]] = None,
) -> list[dict]:
    """Perform a web search, optionally crawl results, and cache normalized documents."""
    engine = get_search_engine(engine_key)
    cache_key = None
    if redis_client:
        query_hash = hashlib.sha256(f"{engine.key}:{query}:{max_results}:{crawl_pages}:{extra_params}".encode()).hexdigest()
        cache_key = f"search:{query_hash}"
        try:
            cached_result = await redis_client.get(cache_key)
            if cached_result:
                logging.info("CACHE HIT for %s search query: '%s'", engine.key, query)
                return json.loads(cached_result)
        except Exception as exc:
            logging.warning("Redis cache read error: %s", exc)
        logging.info("CACHE MISS for %s search query: '%s'", engine.key, query)

    search_params = {"q": query, "format": "json"}
    if extra_params:
        search_params.update(extra_params)

    try:
        async with httpx.AsyncClient(headers=BROWSER_HEADERS, timeout=20) as client:
            logging.info("Querying %s search instance for: %s", engine.key, query)
            response = await client.get(engine.url, params=search_params)
            response.raise_for_status()
            initial_documents = normalize_search_results(response.json(), max_results)
    except Exception as exc:
        logging.error("Error during %s web search for '%s': %s", engine.key, query, exc)
        return []

    if not initial_documents:
        return []

    crawl_results = [{"content": "", "images": []} for _ in initial_documents]
    if crawl_pages:
        semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS_LIMIT)
        async with httpx.AsyncClient(headers=BROWSER_HEADERS) as crawl_client:
            tasks = [crawl_and_extract(crawl_client, doc["url"], semaphore) for doc in initial_documents]
            crawl_results = await asyncio.gather(*tasks)

    final_documents = []
    for doc, crawled in zip(initial_documents, crawl_results):
        content = crawled["content"] if crawled["content"] else doc["content"]
        if content:
            final_documents.append(
                {
                    "title": doc["title"],
                    "url": doc["url"],
                    "source_name": doc["source_name"],
                    "content": content,
                    "images": crawled.get("images", []) if crawl_pages else [],
                    "engine": engine.key,
                }
            )

    logging.info("Processed %s documents for %s query: '%s'", len(final_documents), engine.key, query)

    if redis_client and cache_key:
        try:
            await redis_client.set(cache_key, json.dumps(final_documents), ex=SEARCH_CACHE_TTL)
            logging.info("CACHED %s search result for query: '%s'", engine.key, query)
        except Exception as exc:
            logging.warning("Redis cache write error: %s", exc)

    return final_documents
