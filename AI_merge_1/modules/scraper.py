import asyncio
import io
import re
import sys
from typing import Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import openpyxl
import pandas as pd
import requests
from bs4 import BeautifulSoup
from PIL import Image
from pypdf import PdfReader

from modules.crawl4ai_env import bootstrap_crawl4ai_env  # noqa: F401
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.filters import FilterChain, SEOFilter
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
from crawl4ai.processors.pdf import PDFCrawlerStrategy, PDFContentScrapingStrategy

from utils.logger import get_logger

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

AUX_MAX_FILES = 5
AUX_MAX_BYTES = 10 * 1024 * 1024
AUX_EXCEL_MAX_ROWS = 100


def clean_html(html: str) -> str:
    html = re.sub(r"<script.*?>.*?</script>", "", html, flags=re.DOTALL)
    html = re.sub(r"<style.*?>.*?</style>", "", html, flags=re.DOTALL)
    text = re.sub(r"\s+", " ", html)
    return text.strip()


def is_file_url(url: str) -> tuple[bool, str]:
    lower = url.lower().split("?")[0]
    if lower.endswith(".pdf"):
        return True, "pdf"
    if lower.endswith((".xlsx", ".xls")):
        return True, "excel"
    if lower.endswith((".jpg", ".jpeg", ".png")):
        return True, "image"
    return False, ""


def extract_pdf_bytes(content: bytes) -> str | None:
    try:
        reader = PdfReader(io.BytesIO(content))
        pages = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                pages.append(t)
        text = "\n".join(pages).strip()
        return text or None
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        return None


def extract_pdf_url(url: str) -> str | None:
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return extract_pdf_bytes(response.content)
    except Exception as e:
        logger.error(f"PDF download failed for {url}: {e}")
        return None


def extract_excel_url(url: str) -> str | None:
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        wb = openpyxl.load_workbook(io.BytesIO(response.content), data_only=True)
        lines = []
        for sheet in wb.worksheets:
            lines.append(f"Sheet: {sheet.title}")
            for row in sheet.iter_rows(values_only=True):
                row_text = "\t".join(str(c) if c is not None else "" for c in row)
                if row_text.strip():
                    lines.append(row_text)
        text = "\n".join(lines).strip()
        return text or None
    except Exception as e:
        logger.error(f"Excel extraction failed for {url}: {e}")
        return None


def extract_image_url(url: str) -> str | None:
    try:
        import pytesseract

        response = requests.get(url, timeout=30)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content))
        text = pytesseract.image_to_string(image).strip()
        return text or None
    except Exception as e:
        logger.error(f"Image OCR failed for {url}: {e}")
        return None


def _fetch_auxiliary_from_html(html: str, base_url: str) -> str:
    """
    Follow PDF / Excel links discovered in HTML (Kaleb-style), same-site preference.
    """
    if not html or not html.strip():
        return ""

    try:
        soup = BeautifulSoup(html, "html.parser")
        links = [a.get("href") for a in soup.find_all("a", href=True)]
        target: List[str] = []
        seed_host = urlparse(base_url).netloc

        for link in links:
            if not link:
                continue
            absolute = urljoin(base_url, link).split("#")[0]
            low = absolute.lower()
            if low.endswith((".pdf", ".xls", ".xlsx")):
                host = urlparse(absolute).netloc
                if not seed_host or host == seed_host or host.endswith("." + seed_host):
                    target.append(absolute)

        target = list(dict.fromkeys(target))[:AUX_MAX_FILES]
        if not target:
            return ""

        parts: List[str] = []
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (compatible; IncentivAI-merge/1.0; "
                    "+https://example.invalid)"
                )
            }
        )

        for file_url in target:
            try:
                resp = session.get(file_url, timeout=20)
                if resp.status_code != 200:
                    continue
                cl = int(resp.headers.get("Content-Length") or 0)
                if cl and cl > AUX_MAX_BYTES:
                    continue
                raw = resp.content
                if len(raw) > AUX_MAX_BYTES:
                    continue

                if file_url.lower().endswith(".pdf"):
                    text = extract_pdf_bytes(raw)
                    if text and text.strip():
                        parts.append(f"\n\n--- EMBEDDED FILE CONTENT: {file_url} ---\n\n{text}\n")
                elif file_url.lower().endswith((".xls", ".xlsx")):
                    try:
                        dfs = pd.read_excel(io.BytesIO(raw), sheet_name=None)
                    except Exception:
                        continue
                    chunk = ""
                    for sheet, df in dfs.items():
                        try:
                            chunk += (
                                f"\n### Sheet: {sheet}\n"
                                f"{df.head(AUX_EXCEL_MAX_ROWS).to_markdown(index=False)}\n"
                            )
                        except Exception:
                            chunk += (
                                f"\n### Sheet: {sheet}\n"
                                f"{df.head(AUX_EXCEL_MAX_ROWS).to_csv(index=False)}\n"
                            )
                    if chunk.strip():
                        parts.append(f"\n\n--- EMBEDDED FILE CONTENT: {file_url} ---\n{chunk}\n")
            except Exception as e:
                logger.warning(f"Auxiliary download failed for {file_url}: {e}")

        return "".join(parts)
    except Exception as e:
        logger.warning(f"Auxiliary link processing failed for {base_url}: {e}")
        return ""


def _build_deep_crawl_config(*, max_depth: int = 2) -> CrawlerRunConfig:
    scorer = KeywordRelevanceScorer(keywords=PDF_KEYWORDS, weight=0.8)
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
        max_depth=max(0, int(max_depth)),
        include_external=False,
        url_scorer=scorer,
        filter_chain=FilterChain([seo_filter]),
    )
    return CrawlerRunConfig(
        deep_crawl_strategy=strategy,
        scraping_strategy=LXMLWebScrapingStrategy(),
    )


def _build_pdf_run_config() -> CrawlerRunConfig:
    pdf_scraping_strategy = PDFContentScrapingStrategy(
        extract_images=False,
        save_images_locally=False,
        batch_size=4,
    )
    return CrawlerRunConfig(scraping_strategy=pdf_scraping_strategy)


def _extract_result_text(result) -> Tuple[str, str]:
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
    path = (urlparse(url).path or "").lower()
    if path.endswith(".pdf"):
        return True
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

    return list(dict.fromkeys(found))


def _score_pdf_url(url: str) -> int:
    lowered = url.lower()
    score = 0
    for kw in PDF_KEYWORDS:
        if kw in lowered:
            score += 2
    for kw in ["guide", "manual", "application", "form", "program", "terms", "eligibility"]:
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

        block = f"--- SOURCE: {source_header} ---\n{text}\n"

        html = getattr(r, "html", None)
        if html and str(html).strip():
            aux = _fetch_auxiliary_from_html(str(html), final_url or seed_url)
            if aux:
                block += aux

        parts.append(block)

        if sum(len(p) for p in parts) >= truncation_length:
            break

    if not parts:
        return None
    combined = "\n".join(parts)
    return combined[:truncation_length]


async def _async_deep_scrape(seed_url: str, *, timeout: int = 60, max_depth: int = 2):
    config = _build_deep_crawl_config(max_depth=max_depth)
    async with AsyncWebCrawler() as crawler:
        return await asyncio.wait_for(crawler.arun(url=seed_url, config=config), timeout=timeout)


async def _async_shallow_scrape(seed_url: str, timeout: int = 45):
    config = CrawlerRunConfig(scraping_strategy=LXMLWebScrapingStrategy())
    async with AsyncWebCrawler() as crawler:
        return await asyncio.wait_for(crawler.arun(url=seed_url, config=config), timeout=timeout)


async def _async_pdf_scrape(pdf_url: str, timeout: int = 60):
    config = _build_pdf_run_config()
    async with AsyncWebCrawler(crawler_strategy=PDFCrawlerStrategy()) as crawler:
        return await asyncio.wait_for(crawler.arun(url=pdf_url, config=config), timeout=timeout)


async def _async_scrape_pdf_candidates(
    pdf_urls: List[str],
    timeout_per_pdf: int = 60,
    max_pdfs: int = 3,
) -> List:
    if not pdf_urls:
        return []
    ranked = sorted(list(dict.fromkeys(pdf_urls)), key=_score_pdf_url, reverse=True)[:max_pdfs]
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
    seed_netloc = urlparse(seed_url).netloc
    found: List[str] = []
    for r in results:
        final_url = getattr(r, "url", None) or getattr(r, "final_url", None) or seed_url
        pdf_links = _extract_pdf_links_from_result(r, final_url)
        for pdf_url in pdf_links:
            pdf_netloc = urlparse(pdf_url).netloc
            if seed_netloc and pdf_netloc and (pdf_netloc == seed_netloc or _score_pdf_url(pdf_url) > 0):
                found.append(pdf_url)
            elif not pdf_netloc:
                found.append(pdf_url)
    return list(dict.fromkeys(found))


def _scrape_shallow_with_pdfs(
    url: str,
    truncation_length: int,
    shallow_timeout: int = 60,
    timeout_per_pdf: int = 60,
    max_pdfs: int = 3,
) -> Optional[str]:
    shallow = asyncio.run(_async_shallow_scrape(url, timeout=shallow_timeout))
    shallow_results = _coerce_results(shallow)
    pdf_candidates = _collect_pdf_candidates(url, shallow_results)
    pdf_results = asyncio.run(
        _async_scrape_pdf_candidates(
            pdf_candidates, timeout_per_pdf=timeout_per_pdf, max_pdfs=max_pdfs
        )
    )
    all_results = shallow_results + pdf_results
    combined = _concat_sources(url, all_results, truncation_length)
    if combined is None:
        logger.error(f"Shallow crawl and PDF fallback produced no content for {url}")
    return combined


def scrape_url(
    url: str,
    truncation_length: int = 30000,
    *,
    use_deep_crawl: bool = True,
    deep_crawl_timeout_sec: int = 120,
    max_depth: int = 2,
) -> tuple[Optional[str], str]:
    """
    Returns (text, url_type) where url_type is web | pdf | excel | image.
    """
    try:
        bootstrap_crawl4ai_env()

        is_file, file_type = is_file_url(url)
        if file_type == "pdf":
            content = extract_pdf_url(url)
            return (
                (content[:truncation_length] if content else None),
                "pdf",
            )
        if file_type == "excel":
            content = extract_excel_url(url)
            return (
                (content[:truncation_length] if content else None),
                "excel",
            )
        if file_type == "image":
            content = extract_image_url(url)
            return (
                (content[:truncation_length] if content else None),
                "image",
            )

        if _is_probably_pdf_url(url):
            logger.info(f"Direct PDF URL detected: {url}")
            pdf_result = asyncio.run(_async_pdf_scrape(url, timeout=120))
            combined = _concat_sources(url, _coerce_results(pdf_result), truncation_length)
            if combined is None:
                logger.error(f"PDF scrape produced no content for {url}")
            return combined, "pdf"

        if not use_deep_crawl:
            logger.info(f"Deep crawl disabled; shallow crawl for {url}")
            try:
                text = _scrape_shallow_with_pdfs(url, truncation_length)
                return text, "web"
            except Exception as e:
                logger.error(f"Shallow crawl failed for {url}: {e}")
                return None, "web"

        res = asyncio.run(_async_deep_scrape(url, timeout=deep_crawl_timeout_sec, max_depth=max_depth))
        html_results = _coerce_results(res)
        pdf_candidates = _collect_pdf_candidates(url, html_results)
        pdf_results = asyncio.run(
            _async_scrape_pdf_candidates(pdf_candidates, timeout_per_pdf=60, max_pdfs=3)
        )
        all_results = html_results + pdf_results
        combined = _concat_sources(url, all_results, truncation_length)
        if combined is None:
            logger.error(f"No relevant pages or PDFs successfully crawled for {url}")
            return None, "web"
        return combined, "web"

    except asyncio.TimeoutError:
        logger.error(f"Deep crawl timeout for {url}")
        try:
            text = _scrape_shallow_with_pdfs(url, truncation_length)
            return text, "web"
        except Exception as e:
            logger.error(f"Shallow crawl failed for {url}: {e}")
            return None, "web"

    except Exception as e:
        logger.error(f"Deep crawl failed for {url}: {e}")
        return None, "web"
