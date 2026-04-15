import asyncio
import sys
from typing import Iterable, List, Optional, Tuple
from urllib.parse import urlparse

from modules.crawl4ai_env import bootstrap_crawl4ai_env  # loads env before crawl4ai
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.filters import FilterChain, SEOFilter
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer

from utils.logger import get_logger

# Windows-safe event loop
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

logger = get_logger()


def _build_deep_crawl_config() -> CrawlerRunConfig:
    """
    Kaleb-style best-first deep crawl configuration tuned for incentive content.

    NOTE: This is intentionally "opinionated" to discover relevant subpages
    without crawling the entire site.
    """
    scorer = KeywordRelevanceScorer(
        keywords=[
            "incentive",
            "rebate",
            "grant",
            "funding",
            "assistance",
            "opportunity",
            "application",
            "eligibility",
            "program",
            "efficiency",
            "solar",
            "ev",
            "charger",
        ],
        weight=0.8,
    )

    seo_filter = SEOFilter(
        threshold=0.3,
        keywords=[
            "rebate",
            "incentive",
            "grant",
            "funding",
            "assistance",
            "opportunity",
            "application",
            "eligibility",
            "program",
        ],
    )

    strategy = BestFirstCrawlingStrategy(
        max_depth=2,
        include_external=False,
        url_scorer=scorer,
        filter_chain=FilterChain([seo_filter]),
    )

    return CrawlerRunConfig(
        deep_crawl_strategy=strategy,
        scraping_strategy=LXMLWebScrapingStrategy(),
    )


def _extract_result_text(result) -> Tuple[str, str]:
    """
    Returns (final_url, extracted_text) from a crawl4ai result.
    Prefers fit_markdown when available (less boilerplate), falls back gracefully.
    """
    final_url = getattr(result, "url", None) or getattr(result, "final_url", None) or ""

    extracted = ""
    md = getattr(result, "markdown", None)
    if md:
        try:
            extracted = str(md._markdown_result.fit_markdown)
            if not extracted.strip():
                extracted = str(md._markdown_result.raw_markdown)
        except Exception:
            extracted = str(md)
    if not extracted:
        html = getattr(result, "html", None)
        if html:
            extracted = str(html)

    return final_url, extracted


async def _async_deep_scrape(seed_url: str, timeout: int = 60):
    config = _build_deep_crawl_config()
    async with AsyncWebCrawler() as crawler:
        return await asyncio.wait_for(crawler.arun(url=seed_url, config=config), timeout=timeout)


async def _async_shallow_scrape(seed_url: str, timeout: int = 45):
    """
    Fallback: single-page crawl using the same scraping strategy.
    This keeps the pipeline moving when deep crawl is too slow / blocked.
    """
    config = CrawlerRunConfig(scraping_strategy=LXMLWebScrapingStrategy())
    async with AsyncWebCrawler() as crawler:
        return await asyncio.wait_for(crawler.arun(url=seed_url, config=config), timeout=timeout)


def _coerce_results(res) -> List:
    if res is None:
        return []
    if isinstance(res, list):
        return res
    return [res]


def _concat_sources(seed_url: str, results: Iterable, truncation_length: int) -> Optional[str]:
    """
    Create a single text blob with SOURCE headers, truncated to truncation_length.
    """
    parts: List[str] = []
    seen_urls = set()
    seed_netloc = urlparse(seed_url).netloc

    for r in results:
        success = bool(getattr(r, "success", False))
        status_code = getattr(r, "status_code", 200)
        if not success or status_code != 200:
            continue

        final_url, text = _extract_result_text(r)
        if not text or not text.strip():
            continue

        if final_url:
            if final_url in seen_urls:
                continue
            # Defensive: best-first strategy should stay same-site, but guard anyway
            if seed_netloc and urlparse(final_url).netloc and urlparse(final_url).netloc != seed_netloc:
                continue
            seen_urls.add(final_url)

        parts.append(f"--- SOURCE: {final_url or seed_url} ---\n{text}\n")
        if sum(len(p) for p in parts) >= truncation_length:
            break

    if not parts:
        return None

    combined = "\n".join(parts)
    return combined[:truncation_length]


def scrape_url(url: str, truncation_length: int = 30000) -> Optional[str]:
    """
    Drop-in replacement for the previous single-page scrape:
    performs a Kaleb-style deep crawl and returns a combined text blob.
    """
    try:
        bootstrap_crawl4ai_env()
        # Deep crawl first (Kaleb-style). If it times out, fall back to shallow crawl.
        res = asyncio.run(_async_deep_scrape(url, timeout=120))
        results = _coerce_results(res)
        combined = _concat_sources(url, results, truncation_length)
        if combined is None:
            logger.error(f"No relevant pages successfully crawled for {url}")
        return combined
    except asyncio.TimeoutError:
        logger.error(f"Deep crawl timeout for {url}")
        try:
            shallow = asyncio.run(_async_shallow_scrape(url, timeout=60))
            combined = _concat_sources(url, _coerce_results(shallow), truncation_length)
            if combined is None:
                logger.error(f"Shallow crawl produced no content for {url}")
            return combined
        except Exception as e:
            logger.error(f"Shallow crawl failed for {url}: {e}")
            return None
    except Exception as e:
        logger.error(f"Deep crawl failed for {url}: {e}")
        return None
