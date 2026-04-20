import asyncio
import sys
from typing import Iterable, List, Optional, Tuple, Set
from urllib.parse import urlparse, urljoin

from modules.crawl4ai_env import bootstrap_crawl4ai_env  # loads env before crawl4ai
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.filters import FilterChain, SEOFilter
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
from crawl4ai.processors.pdf import PDFCrawlerStrategy, PDFContentScrapingStrategy

from utils.logger import get_logger

# Windows-safe event loop
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

logger = get_logger()


PDF_KEYWORDS = [
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
]


def _build_deep_crawl_config() -> CrawlerRunConfig:
    """
    Best-first deep crawl configuration tuned for incentive content.
    """
    scorer = KeywordRelevanceScorer(
        keywords=PDF_KEYWORDS,
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


def _build_pdf_run_config() -> CrawlerRunConfig:
    """
    Config for extracting text/metadata from PDFs.
    """
    pdf_scraping_strategy = PDFContentScrapingStrategy(
        extract_images=False,
        save_images_locally=False,
        batch_size=4,
    )
    return CrawlerRunConfig(scraping_strategy=pdf_scraping_strategy)


def _extract_result_text(result) -> Tuple[str, str]:
    """
    Returns (final_url, extracted_text) from a crawl4ai result.
    Prefers fit_markdown when available, then raw_markdown, then html.
    """
    final_url = getattr(result, "url", None) or getattr(result, "final_url", None) or ""

    extracted = ""
    md = getattr(result, "markdown", None)
    if md:
        try:
            markdown_result = getattr(md, "_markdown_result", None)
            if markdown_result is not None:
                extracted = str(getattr(markdown_result, "fit_markdown", "") or "")
                if not extracted.strip():
                    extracted = str(getattr(markdown_result, "raw_markdown", "") or "")
            if not extracted.strip():
                extracted = str(md)
        except Exception:
            extracted = str(md)

    if not extracted:
        html = getattr(result, "html", None)
        if html:
            extracted = str(html)

    return final_url, extracted


def _extract_result_metadata(result) -> dict:
    metadata = getattr(result, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _is_probably_pdf_url(url: str) -> bool:
    if not url:
        return False

    parsed = urlparse(url)
    path = (parsed.path or "").lower()
    if path.endswith(".pdf"):
        return True

    # Some PDF endpoints do not end in .pdf, but expose download/file hints
    lowered = url.lower()
    pdf_markers = ["format=pdf", "/pdf", "download=1", "download=true", "file="]
    return any(marker in lowered for marker in pdf_markers)


def _is_pdf_result(result) -> bool:
    if result is None:
        return False

    final_url = getattr(result, "url", None) or getattr(result, "final_url", None) or ""
    if _is_probably_pdf_url(final_url):
        return True

    headers = getattr(result, "response_headers", None) or {}
    if isinstance(headers, dict):
        content_type = str(headers.get("content-type", "")).lower()
        if "application/pdf" in content_type:
            return True

    metadata = _extract_result_metadata(result)
    content_type = str(metadata.get("content_type", "")).lower()
    if "application/pdf" in content_type:
        return True

    return False


def _extract_pdf_links_from_result(result, base_url: str) -> List[str]:
    """
    Defensively extracts PDF URLs from crawl4ai result.links.

    crawl4ai link structures can vary, so this function tries multiple shapes:
    - {"internal": [...], "external": [...]}
    - {"urls": [...]}
    - lists of strings
    - lists of dicts with href/url/link
    """
    found: List[str] = []
    links = getattr(result, "links", None)

    if not links:
        return found

    candidates = []

    if isinstance(links, dict):
        for key in ("internal", "external", "urls"):
            value = links.get(key)
            if value:
                if isinstance(value, list):
                    candidates.extend(value)
                else:
                    candidates.append(value)
    elif isinstance(links, list):
        candidates.extend(links)

    for item in candidates:
        href = None

        if isinstance(item, str):
            href = item
        elif isinstance(item, dict):
            href = item.get("href") or item.get("url") or item.get("link")

        if not href:
            continue

        absolute = urljoin(base_url, href)
        if _is_probably_pdf_url(absolute):
            found.append(absolute)

    # preserve order while deduplicating
    deduped = list(dict.fromkeys(found))
    return deduped


def _score_pdf_url(url: str) -> int:
    """
    Simple relevance score so we prioritize PDFs likely to contain incentive details.
    """
    lowered = url.lower()
    score = 0

    for kw in PDF_KEYWORDS:
        if kw in lowered:
            score += 2

    bonus_terms = ["guide", "manual", "application", "form", "program", "terms", "eligibility"]
    for kw in bonus_terms:
        if kw in lowered:
            score += 1

    return score


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

            # Keep same-site HTML results, but allow PDFs even if they come from a file host/CDN.
            if not _is_pdf_result(r):
                result_netloc = urlparse(final_url).netloc
                if seed_netloc and result_netloc and result_netloc != seed_netloc:
                    continue

            seen_urls.add(final_url)

        metadata = _extract_result_metadata(r)
        title = metadata.get("title", "")
        source_header = final_url or seed_url
        if title:
            source_header = f"{source_header} | TITLE: {title}"

        parts.append(f"--- SOURCE: {source_header} ---\n{text}\n")

        if sum(len(p) for p in parts) >= truncation_length:
            break

    if not parts:
        return None

    combined = "\n".join(parts)
    return combined[:truncation_length]


async def _async_deep_scrape(seed_url: str, timeout: int = 60):
    config = _build_deep_crawl_config()
    async with AsyncWebCrawler() as crawler:
        return await asyncio.wait_for(crawler.arun(url=seed_url, config=config), timeout=timeout)


async def _async_shallow_scrape(seed_url: str, timeout: int = 45):
    """
    Fallback: single-page crawl using the same scraping strategy.
    """
    config = CrawlerRunConfig(scraping_strategy=LXMLWebScrapingStrategy())
    async with AsyncWebCrawler() as crawler:
        return await asyncio.wait_for(crawler.arun(url=seed_url, config=config), timeout=timeout)


async def _async_pdf_scrape(pdf_url: str, timeout: int = 60):
    """
    Scrape a PDF directly using Crawl4AI's PDF-specific strategies.
    """
    config = _build_pdf_run_config()
    async with AsyncWebCrawler(crawler_strategy=PDFCrawlerStrategy()) as crawler:
        return await asyncio.wait_for(crawler.arun(url=pdf_url, config=config), timeout=timeout)


async def _async_scrape_pdf_candidates(
    pdf_urls: List[str],
    timeout_per_pdf: int = 60,
    max_pdfs: int = 3,
) -> List:
    """
    Scrape a small number of the most relevant PDF links discovered on a page.
    """
    if not pdf_urls:
        return []

    ranked = sorted(
        list(dict.fromkeys(pdf_urls)),
        key=_score_pdf_url,
        reverse=True,
    )[:max_pdfs]

    results = []
    for pdf_url in ranked:
        try:
            logger.info(f"Scraping linked PDF: {pdf_url}")
            pdf_result = await _async_pdf_scrape(pdf_url, timeout=timeout_per_pdf)
            if pdf_result is not None:
                results.append(pdf_result)
        except Exception as e:
            logger.warning(f"Failed to scrape linked PDF {pdf_url}: {e}")

    return results


def _collect_pdf_candidates(seed_url: str, results: Iterable) -> List[str]:
    """
    Collect likely relevant PDFs from HTML crawl results.
    """
    seed_netloc = urlparse(seed_url).netloc
    found: List[str] = []

    for r in results:
        final_url = getattr(r, "url", None) or getattr(r, "final_url", None) or seed_url
        pdf_links = _extract_pdf_links_from_result(r, final_url)

        for pdf_url in pdf_links:
            pdf_netloc = urlparse(pdf_url).netloc
            # Prefer same-site PDFs, but allow obvious PDF links even if hosted elsewhere
            if seed_netloc and pdf_netloc and (pdf_netloc == seed_netloc or _score_pdf_url(pdf_url) > 0):
                found.append(pdf_url)
            elif not pdf_netloc:
                found.append(pdf_url)

    return list(dict.fromkeys(found))


def _combined_text_length(results: Iterable) -> int:
    total = 0
    for r in results:
        _, text = _extract_result_text(r)
        total += len(text or "")
    return total


def scrape_url(url: str, truncation_length: int = 30000) -> Optional[str]:
    """
    Scrapes HTML pages and linked PDFs for incentive content.

    Behavior:
    1. If the input URL is a PDF, scrape it directly with PDFCrawlerStrategy +
       PDFContentScrapingStrategy.
    2. Otherwise deep-crawl the site.
    3. Collect and scrape relevant linked PDFs discovered in the crawl results.
    4. If deep crawl times out, fall back to shallow crawl + linked-PDF scraping.
    """
    try:
        bootstrap_crawl4ai_env()

        # Direct PDF input: use PDF-specific pipeline immediately
        if _is_probably_pdf_url(url):
            logger.info(f"Direct PDF URL detected: {url}")
            pdf_result = asyncio.run(_async_pdf_scrape(url, timeout=120))
            combined = _concat_sources(url, _coerce_results(pdf_result), truncation_length)
            if combined is None:
                logger.error(f"PDF scrape produced no content for {url}")
            return combined

        # Deep crawl HTML first
        res = asyncio.run(_async_deep_scrape(url, timeout=120))
        html_results = _coerce_results(res)

        # Discover relevant PDFs from crawl results and scrape them
        pdf_candidates = _collect_pdf_candidates(url, html_results)
        pdf_results = asyncio.run(_async_scrape_pdf_candidates(pdf_candidates, timeout_per_pdf=60, max_pdfs=3))

        all_results = html_results + pdf_results
        combined = _concat_sources(url, all_results, truncation_length)

        if combined is None:
            logger.error(f"No relevant pages or PDFs successfully crawled for {url}")
            return None

        # If HTML was sparse but PDFs added useful text, this still succeeds
        return combined

    except asyncio.TimeoutError:
        logger.error(f"Deep crawl timeout for {url}")
        try:
            shallow = asyncio.run(_async_shallow_scrape(url, timeout=60))
            shallow_results = _coerce_results(shallow)

            pdf_candidates = _collect_pdf_candidates(url, shallow_results)
            pdf_results = asyncio.run(_async_scrape_pdf_candidates(pdf_candidates, timeout_per_pdf=60, max_pdfs=3))

            all_results = shallow_results + pdf_results
            combined = _concat_sources(url, all_results, truncation_length)

            if combined is None:
                logger.error(f"Shallow crawl and PDF fallback produced no content for {url}")
            return combined

        except Exception as e:
            logger.error(f"Shallow crawl failed for {url}: {e}")
            return None

    except Exception as e:
        logger.error(f"Deep crawl failed for {url}: {e}")
        return None