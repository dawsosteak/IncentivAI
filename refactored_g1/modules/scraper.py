"""
modules/scraper.py — All web scraping, PDF extraction, and Excel extraction logic.
"""

import asyncio
import hashlib
import io
import os
from urllib.parse import urlparse, urljoin

import aiohttp
import pandas as pd
from bs4 import BeautifulSoup

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
from crawl4ai.deep_crawling.filters import FilterChain, SEOFilter, DomainFilter
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from crawl4ai.processors.pdf import PDFCrawlerStrategy, PDFContentScrapingStrategy

from config import (
    PDF_KEYWORDS, PDF_BONUS_TERMS,
    MAX_RANKED_PDFS, MAX_EXCEL_FILES,
    MAX_EXCEL_SIZE_BYTES, PDF_SCRAPE_TIMEOUT,
    SCRAPED_DATA_DIR, DEFAULT_TRUNCATION_LENGTH,
)


# ---------------------------------------------------------
# PDF HELPERS
# ---------------------------------------------------------

def _score_pdf_url(url: str) -> int:
    """Score a PDF URL by keyword relevance to prioritise which ones to scrape."""
    lowered = url.lower()
    score = sum(2 for kw in PDF_KEYWORDS if kw in lowered)
    score += sum(1 for kw in PDF_BONUS_TERMS if kw in lowered)
    return score


async def _scrape_pdf_with_crawl4ai(pdf_url: str) -> str:
    """Download and extract text from a PDF using Crawl4AI."""
    print(f"    -> Scraping PDF: {pdf_url}")
    pdf_scraping_strategy = PDFContentScrapingStrategy(
        extract_images=False,
        save_images_locally=False,
        batch_size=4,
    )
    config = CrawlerRunConfig(
        scraping_strategy=pdf_scraping_strategy,
        cache_mode=CacheMode.BYPASS,
    )
    try:
        async with AsyncWebCrawler(crawler_strategy=PDFCrawlerStrategy()) as crawler:
            res = await asyncio.wait_for(
                crawler.arun(url=pdf_url, config=config),
                timeout=PDF_SCRAPE_TIMEOUT,
            )
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
        print(f"    -> Failed to scrape PDF {pdf_url}: {e}")
        return ""


# ---------------------------------------------------------
# AUXILIARY FILE PROCESSING (PDFs + Excel linked from a page)
# ---------------------------------------------------------

async def process_auxiliary_files(html: str, base_url: str) -> dict:
    """
    Parse a page's HTML, find linked PDFs and Excel files,
    scrape/download them, and return a dict {url: text}.
    """
    extracted_content = {}
    try:
        soup = BeautifulSoup(html, "html.parser")
        links = [a.get("href") for a in soup.find_all("a", href=True)]

        pdf_links, excel_links = set(), set()
        base_netloc = urlparse(base_url).netloc

        for link in links:
            url = urljoin(base_url, link).split("#")[0]
            link_netloc = urlparse(url).netloc

            # Stay on parent domain
            if base_netloc and link_netloc and not link_netloc.endswith(base_netloc):
                continue

            lowered = url.lower()
            if lowered.endswith(".pdf"):
                pdf_links.add(url)
            elif lowered.endswith((".xls", ".xlsx")):
                excel_links.add(url)

        ranked_pdfs = sorted(pdf_links, key=_score_pdf_url, reverse=True)[:MAX_RANKED_PDFS]
        target_excels = list(excel_links)[:MAX_EXCEL_FILES]

        for pdf_url in ranked_pdfs:
            pdf_text = await _scrape_pdf_with_crawl4ai(pdf_url)
            if pdf_text and pdf_text.strip():
                extracted_content[pdf_url] = pdf_text

        if target_excels:
            async with aiohttp.ClientSession() as session:
                for url in target_excels:
                    try:
                        async with session.get(url, timeout=15) as resp:
                            if resp.status == 200:
                                if int(resp.headers.get("Content-Length", 0)) > MAX_EXCEL_SIZE_BYTES:
                                    continue
                                content = await resp.read()
                                dfs = pd.read_excel(io.BytesIO(content), sheet_name=None)
                                text = ""
                                for sheet, df in dfs.items():
                                    try:
                                        text += f"\n### Sheet: {sheet}\n{df.head(100).to_markdown(index=False)}\n"
                                    except ImportError:
                                        text += f"\n### Sheet: {sheet}\n{df.head(100).to_csv(index=False)}\n"
                                if text.strip():
                                    extracted_content[url] = text
                    except Exception as e:
                        print(f"    -> Failed to extract Excel {url}: {e}")

    except Exception as e:
        print(f"Error processing auxiliary links: {e}")

    return extracted_content


# ---------------------------------------------------------
# MAIN SCRAPE FUNCTION
# ---------------------------------------------------------

async def scrape_single_link(
    url: str,
    use_deep_crawl: bool,
    truncation_length: int = DEFAULT_TRUNCATION_LENGTH,
) -> list[str]:
    """
    Crawl a URL (optionally with deep crawl), save each page's
    markdown to scraped_data/, and return the list of saved file paths.
    """
    print(f"\n{'='*60}\nStarting crawl: {url}\n{'='*60}")
    seed_netloc = urlparse(url).netloc

    if use_deep_crawl:
        grant_scorer = KeywordRelevanceScorer(keywords=PDF_KEYWORDS, weight=0.8)
        seo_filter = SEOFilter(threshold=0.3, keywords=PDF_KEYWORDS)
        domain_filter = DomainFilter(allowed_domains=[seed_netloc])
        strategy = BestFirstCrawlingStrategy(
            max_depth=3,
            include_external=False,
            url_scorer=grant_scorer,
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

    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), SCRAPED_DATA_DIR)
    os.makedirs(output_dir, exist_ok=True)
    generated_files = []

    async with AsyncWebCrawler() as crawler:
        try:
            res = await crawler.arun(url=url, config=config)
            results = res if isinstance(res, list) else [res]

            for r in results:
                url_r = getattr(r, "url", "Unknown URL")

                if url_r != "Unknown URL":
                    r_netloc = urlparse(url_r).netloc
                    if seed_netloc and r_netloc and not r_netloc.endswith(seed_netloc):
                        continue

                metadata = getattr(r, "metadata", {})
                status_code = getattr(r, "status_code", 200)

                if getattr(r, "success", False) and status_code == 200:
                    score = metadata.get("score", 0)
                    depth = metadata.get("depth", 0)
                    print(f"Depth: {depth} | Score: {score:.2f} | ✅ {url_r}")

                    scraped_text = _extract_markdown(r)
                    aux_content = await process_auxiliary_files(getattr(r, "html", ""), url_r)
                    for aux_url, aux_text in aux_content.items():
                        scraped_text += f"\n\n--- EMBEDDED FILE CONTENT: {aux_url} ---\n\n{aux_text}\n"

                    if truncation_length and len(scraped_text) > truncation_length:
                        scraped_text = scraped_text[:truncation_length] + "\n\n...[TRUNCATED]"

                    file_path = _build_output_path(output_dir, url_r)
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(f"--- SOURCE: {url_r} ---\n\n")
                        f.write(scraped_text)
                    print(f"Saved: {file_path}")
                    generated_files.append(file_path)

        except Exception as e:
            print(f"Error crawling {url}: {e}")

    print(f"\nSaved {len(generated_files)} pages to {SCRAPED_DATA_DIR}/")
    return generated_files


# ---------------------------------------------------------
# PRIVATE HELPERS
# ---------------------------------------------------------

def _extract_markdown(result) -> str:
    """Pull the best available text out of a crawl result."""
    if hasattr(result, "markdown") and result.markdown:
        try:
            text = str(result.markdown._markdown_result.fit_markdown)
            if not text.strip():
                text = str(result.markdown._markdown_result.raw_markdown)
            return text
        except AttributeError:
            return str(result.markdown)
    if hasattr(result, "html") and result.html:
        return str(result.html)
    return ""


def _build_output_path(output_dir: str, url: str) -> str:
    """Create a deterministic, filesystem-safe output filename for a URL."""
    url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
    safe_domain = urlparse(url).netloc.replace(".", "_")
    return os.path.join(output_dir, f"{safe_domain}_{url_hash}.md")
