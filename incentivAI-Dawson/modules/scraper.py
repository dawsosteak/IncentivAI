import asyncio
import re
import sys
import io
import hashlib
import os
import pdfplumber
import openpyxl
import aiohttp
import requests
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

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

logger = get_logger()

INCENTIVE_KEYWORDS = [
    "incentive", "rebate", "grant", "funding", "assistance",
    "opportunity", "application", "eligibility", "program",
    "efficiency", "solar", "ev", "charger"
]

# File extensions to score when discovering auxiliary links
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
    Keep only sentences containing incentive keywords plus
    a surrounding window of sentences for context.
    Falls back to full text if nothing matched.
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
    Returns (True, file_type) or (False, "").
    """
    lower = url.lower().split("?")[0]
    if lower.endswith(".pdf"):
        return True, "pdf"
    if lower.endswith((".xlsx", ".xls")):
        return True, "excel"
    if lower.endswith((".jpg", ".jpeg", ".png")):
        return True, "image"
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
    try:
        async with AsyncWebCrawler(crawler_strategy=PDFCrawlerStrategy()) as crawler:
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

        # Take top 3 PDFs by relevance score — use crawl4ai native PDF extractor
        ranked_pdfs = sorted(list(pdf_links), key=_score_pdf_url, reverse=True)[:3]

        for pdf_url in ranked_pdfs:
            text = await _scrape_pdf_with_crawl4ai(pdf_url)
            if text and text.strip():
                extracted[pdf_url] = text

        # Take top 2 Excel files via aiohttp
        async with aiohttp.ClientSession() as session:
            for url in list(excel_links)[:2]:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status == 200:
                            # Skip files over 10MB
                            if int(resp.headers.get("Content-Length", 0)) > 10 * 1024 * 1024:
                                continue
                            content = await resp.read()
                            dfs = __import__("pandas").read_excel(
                                io.BytesIO(content), sheet_name=None
                            )
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

async def async_scrape_all(url: str, timeout: int = 120, use_deep_crawl: bool = True) -> list[dict]:
    """
    Crawl a URL and return all successfully scraped pages with parent tracking.
    Uses BestFirstCrawlingStrategy with domain filtering and keyword scoring.
    Appends auxiliary PDF/Excel content found on each page.

    Returns list of dicts:
        [{"url": str, "parent": str | None, "content": str, "url_type": "web"}]
    """
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

    try:
        async with AsyncWebCrawler() as crawler:
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

    return pages


def scrape_all_pages(url: str, truncation_length: int = 8000, use_deep_crawl: bool = True) -> list[dict]:
    """
    Entry point for web page deep crawling.
    Returns all discovered pages with parent tracking and truncated content.

    Each dict: {"url": str, "parent": str | None, "content": str, "url_type": "web"}
    """
    try:
        pages = asyncio.run(async_scrape_all(url, timeout=120, use_deep_crawl=use_deep_crawl))
        for p in pages:
            content = preprocess_content(p["content"])
            content = extract_relevant_sentences(content, INCENTIVE_KEYWORDS)
            p["content"] = content[:truncation_length]
        return pages
    except Exception as e:
        logger.error(f"Deep scrape failed for {url}: {e}")
        return []


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
