
import asyncio
import re
import sys
import io
import os
import requests
import pdfplumber
import openpyxl
import aiohttp
from urllib.parse import urlparse, urljoin
from io import BytesIO
from PIL import Image
import pytesseract
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig, CacheMode
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
from crawl4ai.deep_crawling.filters import FilterChain, SEOFilter, DomainFilter
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from crawl4ai.processors.pdf import PDFCrawlerStrategy, PDFContentScrapingStrategy
from utils.logger import get_logger

# FIX: Windows requires ProactorEventLoopPolicy for asyncio subprocesses
# (needed by Playwright/Chromium). Set this before any loop is created.
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

logger = get_logger()

INCENTIVE_KEYWORDS = [
    "incentive", "rebate", "grant", "funding", "assistance",
    "opportunity", "application", "eligibility", "program",
    "efficiency", "solar", "ev", "charger"
]

# Keywords to score PDF URLs by relevance — higher score = crawl first
PDF_SCORE_KEYWORDS = ["incentive", "rebate", "grant", "guide", "manual", "form", "terms", "efficiency"]


# ─────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────

def clean_html(html: str) -> str:
    """Strip scripts, styles, and collapse whitespace from raw HTML."""
    html = re.sub(r"<script.*?>.*?</script>", "", html, flags=re.DOTALL)
    html = re.sub(r"<style.*?>.*?</style>", "", html, flags=re.DOTALL)
    text = re.sub(r"\s+", " ", html)
    return text.strip()


def preprocess_content(text: str) -> str:
    """
    Remove common page noise before sending to LLM:
    navigation, cookie banners, excessive whitespace, inline URLs.
    """
    text = re.sub(r"(skip to|jump to|back to top|breadcrumb).*?\n", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(cookie|privacy policy|terms of use|accept all).*?\n", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"http\S+", "", text)
    return text.strip()


def extract_relevant_sentences(text: str, keywords: list, window: int = 2) -> str:
    """
    Keep only sentences containing incentive keywords plus a surrounding
    window of sentences for context. Falls back to full text if nothing matched.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)
    relevant_indices = set()

    for i, sentence in enumerate(sentences):
        if any(kw.lower() in sentence.lower() for kw in keywords):
            for j in range(max(0, i - window), min(len(sentences), i + window + 1)):
                relevant_indices.add(j)

    if not relevant_indices:
        return text

    return " ".join(sentences[i] for i in sorted(relevant_indices))


def is_file_url(url: str) -> tuple:
    """
    Check if a URL points directly to a file we handle.
    Also does a HEAD request to sniff Content-Type for URLs with no extension
    (e.g. /download?id=123 that serves a PDF).

    Returns (True, file_type) or (False, "").
    """
    lower = url.lower().split("?")[0]

    # Fast path: extension in URL
    if lower.endswith(".pdf"):
        return True, "pdf"
    if lower.endswith((".xlsx", ".xls")):
        return True, "excel"
    if lower.endswith((".jpg", ".jpeg", ".png")):
        return True, "image"

    # FIX: slow path — HEAD request to sniff Content-Type for extension-less file URLs.
    # Many utility portals serve PDFs from /download?id=123 with no .pdf in the URL.
    try:
        resp = requests.head(url, timeout=10, allow_redirects=True)
        ct = resp.headers.get("Content-Type", "").lower()
        if "pdf" in ct:
            return True, "pdf"
        if "spreadsheet" in ct or "excel" in ct or "xlsx" in ct:
            return True, "excel"
        if ct.startswith("image/"):
            return True, "image"
    except Exception:
        pass  # network error — treat as web page, scraper will handle it

    return False, ""


def _score_pdf_url(url: str) -> int:
    """Score a PDF URL by keyword relevance to prioritize the most useful ones."""
    lowered = url.lower()
    score = sum(2 for kw in PDF_SCORE_KEYWORDS if kw in lowered)
    score += sum(1 for kw in ["guide", "manual", "form", "terms"] if kw in lowered)
    return score


def _get_fit_markdown(page) -> str:
    """
    Extract fit_markdown from a crawl4ai result — this is crawl4ai's
    pre-cleaned markdown with navigation/boilerplate stripped.
    Falls back to raw_markdown then plain str(markdown).
    """
    try:
        content = str(page.markdown._markdown_result.fit_markdown)
        if not content.strip():
            content = str(page.markdown._markdown_result.raw_markdown)
        return content
    except AttributeError:
        return str(page.markdown)


# ─────────────────────────────────────────────
# FILE EXTRACTORS
# ─────────────────────────────────────────────

def extract_pdf(url: str) -> str | None:
    """Download and extract text from a PDF URL using pdfplumber."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        with pdfplumber.open(BytesIO(response.content)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        text = "\n".join(pages).strip()
        if not text:
            logger.warning(f"PDF had no extractable text: {url}")
            return None
        logger.info(f"Extracted PDF ({len(text)} chars): {url}")
        return text
    except Exception as e:
        logger.error(f"PDF extraction failed for {url}: {e}")
        return None


def extract_excel(url: str) -> str | None:
    """Download and extract text from an Excel file URL using openpyxl."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        wb = openpyxl.load_workbook(BytesIO(response.content), data_only=True)
        lines = []
        for sheet in wb.worksheets:
            lines.append(f"Sheet: {sheet.title}")
            for row in sheet.iter_rows(values_only=True):
                row_text = "\t".join(str(c) if c is not None else "" for c in row)
                if row_text.strip():
                    lines.append(row_text)
        text = "\n".join(lines).strip()
        if not text:
            logger.warning(f"Excel had no extractable content: {url}")
            return None
        logger.info(f"Extracted Excel ({len(text)} chars): {url}")
        return text
    except Exception as e:
        logger.error(f"Excel extraction failed for {url}: {e}")
        return None


def extract_image(url: str) -> str | None:
    """Download and OCR text from an image URL using pytesseract."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        image = Image.open(BytesIO(response.content))
        text = pytesseract.image_to_string(image).strip()
        if not text:
            logger.warning(f"Image had no extractable text: {url}")
            return None
        logger.info(f"Extracted image OCR ({len(text)} chars): {url}")
        return text
    except Exception as e:
        logger.error(f"Image OCR extraction failed for {url}: {e}")
        return None


# ─────────────────────────────────────────────
# AUXILIARY FILE DISCOVERY
# ─────────────────────────────────────────────

async def _scrape_pdf_with_crawl4ai(pdf_url: str) -> str:
    """
    Use crawl4ai's native PDF crawler strategy for robust PDF extraction.
    Handles image-based and complex layout PDFs better than pdfplumber.

    FIX: Uses explicit try/finally to guarantee browser cleanup even on timeout.
    """
    logger.info(f"Scraping PDF via crawl4ai: {pdf_url}")
    pdf_scraping_strategy = PDFContentScrapingStrategy(
        extract_images=False,
        save_images_locally=False,
        batch_size=4,
    )
    config = CrawlerRunConfig(
        scraping_strategy=pdf_scraping_strategy,
        cache_mode=CacheMode.BYPASS
    )
    crawler = AsyncWebCrawler(crawler_strategy=PDFCrawlerStrategy())
    try:
        await crawler.start()
        res = await asyncio.wait_for(crawler.arun(url=pdf_url, config=config), timeout=120)
        md = getattr(res, "markdown", None)
        extracted = ""
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
            html = getattr(res, "html", None)
            if html:
                extracted = str(html)
        return extracted
    except Exception as e:
        logger.error(f"crawl4ai PDF extraction failed for {pdf_url}: {e}")
        return ""
    finally:
        # FIX (Bug 4): guaranteed browser cleanup — runs even if asyncio.wait_for
        # raises CancelledError or TimeoutError, preventing zombie Chromium processes.
        try:
            await crawler.close()
        except Exception:
            pass


async def process_auxiliary_files(html: str, base_url: str) -> dict:
    """
    Scan a page's HTML for embedded PDF and Excel links and extract their content.
    Stays within the same domain. Prioritizes top 3 PDFs by keyword score.
    Returns dict of {url: extracted_text}.
    """
    extracted = {}
    try:
        soup = BeautifulSoup(html, "html.parser")
        links = [a.get("href") for a in soup.find_all("a", href=True)]

        base_netloc = urlparse(base_url).netloc
        pdf_links = set()
        excel_links = set()

        for link in links:
            url = urljoin(base_url, link).split("#")[0]
            link_netloc = urlparse(url).netloc
            if base_netloc and link_netloc and not link_netloc.endswith(base_netloc):
                continue
            lower = url.lower()
            if lower.endswith(".pdf"):
                pdf_links.add(url)
            elif lower.endswith((".xls", ".xlsx")):
                excel_links.add(url)

        # Take top 3 PDFs by relevance score
        ranked_pdfs = sorted(list(pdf_links), key=_score_pdf_url, reverse=True)[:3]

        for pdf_url in ranked_pdfs:
            text = await _scrape_pdf_with_crawl4ai(pdf_url)
            if text and text.strip():
                extracted[pdf_url] = text

        # FIX (Bug 5): aiohttp.ClientTimeout(total=N) is required — passing an
        # integer directly is silently ignored, resulting in no timeout at all.
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession() as session:
            for url in list(excel_links)[:2]:
                try:
                    async with session.get(url, timeout=timeout) as resp:
                        if resp.status == 200:
                            content_length = int(resp.headers.get("Content-Length", 0))
                            if content_length > 10 * 1024 * 1024:
                                logger.warning(f"Skipping large Excel file ({content_length} bytes): {url}")
                                continue
                            content = await resp.read()
                            import pandas as _pd
                            dfs = _pd.read_excel(io.BytesIO(content), sheet_name=None)
                            text = ""
                            for sheet, df in dfs.items():
                                try:
                                    text += f"\n### Sheet: {sheet}\n{df.head(100).to_markdown(index=False)}\n"
                                except ImportError:
                                    text += f"\n### Sheet: {sheet}\n{df.head(100).to_csv(index=False)}\n"
                            if text.strip():
                                extracted[url] = text
                except Exception as e:
                    logger.error(f"Excel auxiliary extraction failed for {url}: {e}")

    except Exception as e:
        logger.error(f"Auxiliary file discovery failed for {base_url}: {e}")

    return extracted


# ─────────────────────────────────────────────
# MAIN WEB SCRAPER
# ─────────────────────────────────────────────

async def async_scrape_all(
    url: str,
    timeout: int = 120,
    use_deep_crawl: bool = True,
    seen_urls: set = None,
) -> list[dict]:
    """
    Crawl a URL and return all successfully scraped pages with parent tracking.
    Uses BestFirstCrawlingStrategy with domain filtering and keyword scoring.
    Appends auxiliary PDF/Excel content found on each page.

    FIX (Bug 4): Uses explicit try/finally with crawler.close() to guarantee
    Chromium process cleanup even when asyncio.wait_for() raises CancelledError.

    FIX (deduplication): Accepts a shared seen_urls set from scrape_all_pages()
    so the same subpage isn't processed twice when multiple input URLs share a domain.

    Args:
        url:           seed URL to crawl
        timeout:       seconds before cancelling the crawl
        use_deep_crawl: if False, only crawls the single seed page (no BestFirst)
        seen_urls:     shared set of already-processed page URLs (mutated in place)

    Returns list of dicts:
        [{"url": str, "parent": str | None, "content": str, "url_type": "web"}]
    """
    if seen_urls is None:
        seen_urls = set()

    seed_netloc = urlparse(url).netloc

    if use_deep_crawl:
        scorer = KeywordRelevanceScorer(keywords=INCENTIVE_KEYWORDS, weight=0.8)
        seo_filter = SEOFilter(threshold=0.3, keywords=INCENTIVE_KEYWORDS)
        domain_filter = DomainFilter(allowed_domains=[seed_netloc])

        strategy = BestFirstCrawlingStrategy(
            max_depth=3,
            include_external=False,
            url_scorer=scorer,
            filter_chain=FilterChain([domain_filter, seo_filter]),
        )
        config = CrawlerRunConfig(
            deep_crawl_strategy=strategy,
            scraping_strategy=LXMLWebScrapingStrategy(),
            cache_mode=CacheMode.BYPASS,
        )
    else:
        config = CrawlerRunConfig(
            scraping_strategy=LXMLWebScrapingStrategy(),
            cache_mode=CacheMode.BYPASS,
        )

    pages = []

    # FIX (Bug 4): Explicit crawler lifecycle management instead of `async with`.
    # `async with` relies on __aexit__ which can be interrupted by CancelledError
    # from asyncio.wait_for(), leaving Chromium processes running.
    crawler = AsyncWebCrawler()
    try:
        await crawler.start()
        result = await asyncio.wait_for(
            crawler.arun(url=url, config=config), timeout
        )

        results = result if isinstance(result, list) else [result]

        for r in results:
            if not getattr(r, "success", False):
                continue
            if getattr(r, "status_code", 200) != 200:
                continue

            page_url = getattr(r, "url", url)

            # FIX (deduplication): skip pages already processed by a prior URL entry
            if page_url in seen_urls:
                logger.info(f"Skipping duplicate page (already processed): {page_url}")
                continue
            seen_urls.add(page_url)

            # Strict domain check — discard anything outside seed domain
            if seed_netloc:
                r_netloc = urlparse(page_url).netloc
                if r_netloc and not r_netloc.endswith(seed_netloc):
                    continue

            metadata = getattr(r, "metadata", {}) or {}
            depth = metadata.get("depth", 0)
            parent = url if depth > 0 else None

            # Use fit_markdown for cleaner content
            if hasattr(r, "markdown") and r.markdown:
                content = _get_fit_markdown(r)
            elif hasattr(r, "html") and r.html:
                content = clean_html(r.html)
            else:
                continue

            # Discover and append auxiliary PDF/Excel content
            raw_html = getattr(r, "html", "") or ""
            aux_content = await process_auxiliary_files(raw_html, page_url)
            for aux_url, aux_text in aux_content.items():
                content += f"\n\n--- EMBEDDED FILE CONTENT: {aux_url} ---\n\n{aux_text}\n"

            if not content.strip():
                logger.warning(f"No content extracted from {page_url}")
                continue

            pages.append({
                "url": page_url,
                "parent": parent,
                "content": content,
                "url_type": "web"
            })
            logger.info(f"Depth: {depth} | ✅ Crawled: {page_url} ({len(content)} chars)")

    except asyncio.TimeoutError:
        logger.error(f"Timeout reached for {url}")
    except Exception as e:
        logger.error(f"Scraping failed for {url}: {e}")
    finally:
        # Guaranteed cleanup — closes Chromium even if an exception was raised above
        try:
            await crawler.close()
        except Exception:
            pass

    return pages


# Global seen_urls set shared across all calls within a pipeline run.
# Reset by scrape_all_pages() at start of each pipeline call via the module-level
# reference. This prevents the same subpage from being LLM-processed multiple times
# when several input URLs from the same domain are in the Excel file.
_global_seen_urls: set = set()


def reset_seen_urls():
    """Call this at the start of each pipeline run to clear deduplication state."""
    global _global_seen_urls
    _global_seen_urls = set()


def scrape_all_pages(
    url: str,
    truncation_length: int = 8000,
    use_deep_crawl: bool = True,
) -> list[dict]:
    """
    Entry point for web page deep crawling.
    Returns all discovered pages with parent tracking and truncated content.

    FIX (asyncio.run guard): Uses the existing event loop if one is running
    (e.g. inside Streamlit + nest_asyncio), otherwise creates a new one.
    This prevents "This event loop is already running" errors in Streamlit.

    Each dict: {"url": str, "parent": str | None, "content": str, "url_type": "web"}
    """
    try:
        # Try to get the running loop (set by nest_asyncio in app.py)
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # nest_asyncio is active — run coroutine directly on the existing loop
            import concurrent.futures
            future = asyncio.ensure_future(
                async_scrape_all(url, timeout=120, use_deep_crawl=use_deep_crawl,
                                 seen_urls=_global_seen_urls)
            )
            # Block until complete using run_until_complete is not possible on a
            # running loop even with nest_asyncio for ensure_future; use asyncio.run
            # which nest_asyncio patches to work correctly in this context.
            pages = asyncio.run(
                async_scrape_all(url, timeout=120, use_deep_crawl=use_deep_crawl,
                                 seen_urls=_global_seen_urls)
            )
        else:
            pages = loop.run_until_complete(
                async_scrape_all(url, timeout=120, use_deep_crawl=use_deep_crawl,
                                 seen_urls=_global_seen_urls)
            )
    except RuntimeError:
        # Fallback: create a brand-new event loop
        pages = asyncio.run(
            async_scrape_all(url, timeout=120, use_deep_crawl=use_deep_crawl,
                             seen_urls=_global_seen_urls)
        )
    except Exception as e:
        logger.error(f"Deep scrape failed for {url}: {e}")
        return []

    for p in pages:
        content = preprocess_content(p["content"])
        content = extract_relevant_sentences(content, INCENTIVE_KEYWORDS)
        p["content"] = content[:truncation_length]

    return pages


def scrape_url(url: str, truncation_length: int = 8000) -> tuple:
    """
    Entry point for direct file URL scraping (PDF, Excel, image).
    For web pages use scrape_all_pages() instead.

    Returns:
        (content, url_type) where url_type is one of: pdf / excel / image
    """
    _, file_type = is_file_url(url)

    if file_type == "pdf":
        content = extract_pdf(url)
        return (content[:truncation_length] if content else None), "pdf"

    if file_type == "excel":
        content = extract_excel(url)
        return (content[:truncation_length] if content else None), "excel"

    if file_type == "image":
        content = extract_image(url)
        return (content[:truncation_length] if content else None), "image"

    return None, "web"
