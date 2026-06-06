# app/web_search.py

import httpx
import logging
import asyncio
import json
import hashlib
from typing import Optional
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from redis.asyncio import Redis as AsyncRedis

BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
}

# Using your provided search engine
SEARCH_ENGINE_URL = "https://connectnet.onrender.com/search"

CONCURRENT_REQUESTS_LIMIT = 5
SEARCH_CACHE_TTL = 3600  # Cache search results for 1 hour


def clean_content(soup: BeautifulSoup) -> str:
    """Strips irrelevant tags and extracts clean text from a BeautifulSoup object."""
    for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form']):
        tag.decompose()
    text = soup.get_text(separator=' ', strip=True)
    return ' '.join(text.split())


def extract_images(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Extracts and prioritizes relevant image URLs from a BeautifulSoup object."""
    images = set()
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        images.add(urljoin(base_url, og_image["content"]))
    for img in soup.find_all("img", {"src": True}):
        src = img["src"]
        if src.startswith('data:'):
            continue
        try:
            width = int(img.get('width', '0'))
            height = int(img.get('height', '0'))
            if width > 100 and height > 100:
                images.add(urljoin(base_url, src))
        except (ValueError, TypeError):
            images.add(urljoin(base_url, src))
    return list(images)[:5]


async def crawl_and_extract(session: httpx.AsyncClient, url: str, semaphore: asyncio.Semaphore, depth: int = 0) -> dict:
    """Asynchronously fetches a URL and extracts content."""
    async with semaphore:
        try:
            logging.info(f"Crawling URL: {url}")
            response = await session.get(url, timeout=15, follow_redirects=True)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            return {
                "content": clean_content(soup),
                # Use the full final URL so urljoin can correctly resolve relative image paths.
                "images": extract_images(soup, str(response.url)),
                "final_url": str(response.url)
            }
        except Exception as e:
            logging.error(f"Failed to crawl or extract from {url}: {e}")
            return {"content": "", "images": [], "final_url": url}


async def get_search_context(query: str, max_results: int = 5, redis_client: Optional[AsyncRedis] = None):
    """
    Performs a web search, with caching, then crawls results to extract context.
    """
    cache_key = None
    if redis_client:
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        cache_key = f"search:{query_hash}"
        try:
            cached_result = await redis_client.get(cache_key)
            if cached_result:
                logging.info(f"CACHE HIT for search query: '{query}'")
                return json.loads(cached_result)
        except Exception as e:
            logging.warning(f"Redis cache read error: {e}")
        logging.info(f"CACHE MISS for search query: '{query}'")

    search_params = {'q': query, 'format': 'json'}
    initial_documents = []
    try:
        async with httpx.AsyncClient(headers=BROWSER_HEADERS, timeout=20) as client:
            logging.info(f"Querying search instance for: {query}")
            response = await client.get(SEARCH_ENGINE_URL, params=search_params)
            response.raise_for_status()
            data = response.json()
            unique_urls = set()
            for result in data.get("results", [])[:max_results * 2]:
                url = result.get("url")
                if url and url not in unique_urls:
                    unique_urls.add(url)
                    initial_documents.append({
                        'title': result.get('title', 'Untitled'),
                        'url': url,
                        'source_name': urlparse(url).netloc.replace('www.', ''),
                        'content': result.get('content', '')
                    })
                if len(initial_documents) >= max_results:
                    break
    except Exception as e:
        logging.error(f"Error during initial web search for '{query}': {e}")
        return []

    if not initial_documents:
        return []

    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS_LIMIT)
    async with httpx.AsyncClient(headers=BROWSER_HEADERS) as crawl_client:
        tasks = [crawl_and_extract(crawl_client, doc['url'], semaphore) for doc in initial_documents]
        crawl_results = await asyncio.gather(*tasks)

    final_documents = []
    for doc, crawled in zip(initial_documents, crawl_results):
        content = crawled['content'] if crawled['content'] else doc['content']
        if content:
            final_documents.append({
                'title': doc['title'],
                'url': doc['url'],
                'source_name': doc['source_name'],
                'content': content,
                'images': crawled.get('images', [])
            })

    logging.info(f"Processed {len(final_documents)} documents for query: '{query}'")

    if redis_client and cache_key:
        try:
            await redis_client.set(cache_key, json.dumps(final_documents), ex=SEARCH_CACHE_TTL)
            logging.info(f"CACHED search result for query: '{query}'")
        except Exception as e:
            logging.warning(f"Redis cache write error: {e}")

    return final_documents
