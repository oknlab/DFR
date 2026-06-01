import asyncio
import hashlib
import json
import logging
import os
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

SEARCH_ENGINE_URL = os.getenv("SEARCH_ENGINE_URL", "https://connectnet.onrender.com/search")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID", "014662525286492529401:2upbuo2qpni")
GOOGLE_CSE_URL = os.getenv(
    "GOOGLE_CSE_URL",
    "https://cse.google.com/cse?cx=014662525286492529401%3A2upbuo2qpni",
)
BING_ENDPOINT = os.getenv("BING_ENDPOINT", "https://api.bing.microsoft.com/v7.0/search")
BING_API_KEY = os.getenv("BING_API_KEY", "")
ENABLE_BING_FALLBACK = os.getenv("ENABLE_BING_FALLBACK", "false").lower() == "true"

CONCURRENT_REQUESTS_LIMIT = 5
SEARCH_CACHE_TTL = 3600
PROMOTED_MARKERS = ("ad", "ads", "sponsored", "promoted")


def clean_content(soup: BeautifulSoup) -> str:
    """Strips irrelevant tags and extracts clean text from a BeautifulSoup object."""
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return " ".join(text.split())


def extract_images(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Extracts and prioritizes relevant image URLs from a BeautifulSoup object."""
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


async def crawl_and_extract(
    session: httpx.AsyncClient,
    url: str,
    semaphore: asyncio.Semaphore,
    depth: int = 0,
) -> dict:
    """Asynchronously fetches a URL and extracts content."""
    del depth
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


async def query_independent_index(query: str, max_results: int) -> list[dict]:
    search_params = {"q": query, "format": "json"}
    initial_documents = []
    async with httpx.AsyncClient(headers=BROWSER_HEADERS, timeout=20) as client:
        logging.info("Querying search instance for: %s", query)
        response = await client.get(SEARCH_ENGINE_URL, params=search_params)
        response.raise_for_status()
        data = response.json()
        unique_urls = set()
        for result in data.get("results", [])[: max_results * 2]:
            url = result.get("url")
            if url and url not in unique_urls:
                unique_urls.add(url)
                initial_documents.append(
                    {
                        "title": result.get("title", "Untitled"),
                        "url": url,
                        "source_name": urlparse(url).netloc.replace("www.", ""),
                        "content": result.get("content", ""),
                        "is_promoted": _is_promoted(result),
                        "source_type": result.get("category", "web"),
                    }
                )
            if len(initial_documents) >= max_results:
                break
    return initial_documents


async def query_bing_fallback(query: str, max_results: int) -> list[dict]:
    if not ENABLE_BING_FALLBACK or not BING_API_KEY:
        return []
    headers = {"Ocp-Apim-Subscription-Key": BING_API_KEY}
    params = {"q": query, "count": max_results, "textDecorations": False, "textFormat": "Raw"}
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(BING_ENDPOINT, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
    docs = []
    for item in data.get("webPages", {}).get("value", []):
        url = item.get("url")
        if not url:
            continue
        docs.append(
            {
                "title": item.get("name", "Untitled"),
                "url": url,
                "source_name": urlparse(url).netloc.replace("www.", ""),
                "content": item.get("snippet", ""),
                "is_promoted": False,
                "source_type": "web",
            }
        )
    return docs


def _is_promoted(result: dict) -> bool:
    haystack = " ".join(
        str(result.get(key, "")).lower() for key in ("type", "category", "class", "label")
    )
    return any(marker in haystack for marker in PROMOTED_MARKERS)


def _cache_key(query: str, max_results: int, hide_promoted: bool) -> str:
    normalized = json.dumps(
        {"q": query, "max": max_results, "hide_promoted": hide_promoted},
        sort_keys=True,
    )
    query_hash = hashlib.sha256(normalized.encode()).hexdigest()
    return f"search:{query_hash}"


def _shape_multisource(documents: list[dict]) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {"web": [], "documents": [], "images": [], "news": [], "social": []}
    for doc in documents:
        url = doc.get("url", "")
        domain = doc.get("source_name", "")
        lower_url = url.lower()
        content_type = doc.get("source_type", "web")
        if lower_url.endswith((".pdf", ".doc", ".docx", ".ppt", ".pptx")):
            buckets["documents"].append(doc)
        elif any(news in domain for news in ("news", "reuters", "apnews", "bbc", "cnn")):
            buckets["news"].append(doc)
        elif any(social in domain for social in ("x.com", "twitter", "reddit", "facebook", "instagram", "linkedin")):
            buckets["social"].append(doc)
        else:
            buckets.setdefault(content_type, buckets["web"]).append(doc)
            if content_type not in buckets:
                buckets["web"].append(doc)
        for image in doc.get("images", []):
            buckets["images"].append(
                {
                    "title": doc.get("title", "Image result"),
                    "url": url,
                    "image_url": image,
                    "source_name": domain,
                    "content": doc.get("content", "")[:180],
                }
            )
    return buckets


async def get_search_context(
    query: str,
    max_results: int = 5,
    redis_client: Optional[AsyncRedis] = None,
    hide_promoted: bool = False,
) -> dict:
    """Performs a web search, with caching, then crawls results to extract context."""
    cache_key = None
    if redis_client:
        cache_key = _cache_key(query, max_results, hide_promoted)
        try:
            cached_result = await redis_client.get(cache_key)
            if cached_result:
                logging.info("CACHE HIT for search query: %r", query)
                return json.loads(cached_result)
        except Exception as exc:
            logging.warning("Redis cache read error: %s", exc)
        logging.info("CACHE MISS for search query: %r", query)

    fallback_used = False
    try:
        initial_documents = await query_independent_index(query, max_results)
    except Exception as exc:
        logging.error("Error during initial web search for %r: %s", query, exc)
        initial_documents = []

    if not initial_documents:
        try:
            initial_documents = await query_bing_fallback(query, max_results)
            fallback_used = bool(initial_documents)
        except Exception as exc:
            logging.error("Error during Bing fallback search for %r: %s", query, exc)
            initial_documents = []

    if hide_promoted:
        initial_documents = [doc for doc in initial_documents if not doc.get("is_promoted")]

    if not initial_documents:
        return {"results": [], "sources": _shape_multisource([]), "fallback_used": False}

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
                    "images": crawled.get("images", []),
                    "is_promoted": doc.get("is_promoted", False),
                    "source_type": doc.get("source_type", "web"),
                }
            )

    payload = {
        "results": final_documents,
        "sources": _shape_multisource(final_documents),
        "fallback_used": fallback_used,
        "google_cse_url": GOOGLE_CSE_URL,
    }
    logging.info("Processed %s documents for query: %r", len(final_documents), query)

    if redis_client and cache_key:
        try:
            await redis_client.set(cache_key, json.dumps(payload), ex=SEARCH_CACHE_TTL)
            logging.info("CACHED search result for query: %r", query)
        except Exception as exc:
            logging.warning("Redis cache write error: %s", exc)

    return payload
