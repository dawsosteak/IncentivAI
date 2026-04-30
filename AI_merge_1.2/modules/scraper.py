import asyncio
import io
import re
import sys
import zipfile
from typing import Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import openpyxl
import requests
from bs4 import BeautifulSoup
from PIL import Image
from pypdf import PdfReader

from modules.crawl4ai_env import bootstrap_crawl4ai_env  # noqa: F401
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.filters import FilterChain, URLPatternFilter
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
from crawl4ai.processors.pdf import PDFCrawlerStrategy, PDFContentScrapingStrategy

from utils.logger import get_logger

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

logger = get_logger()

AUX_MAX_BYTES = 10 * 1024 * 1024
DEEP_CRAWL_MAX_PAGES = 25
DEEP_CRAWL_DOWNLOAD_PATTERNS = ["*.pdf", "*.xls", "*.xlsx", "*.docx"]

# Ranking only: these words decide crawl order under the page budget. They do
# not reject URLs or extracted content.
DEEP_CRAWL_PRIORITY_KEYWORDS = [
    "rebate",
    "rebates",
    "incentive",
    "incentives",
    "program",
    "programs",
    "application",
    "eligibility",
    "efficiency",
    "energy",
    "electric",
    "residential",
    "solar",
    "ev",
    "charger",
    "heating",
    "cooling",
    "heat-pump",
    "heatpump",
    "hvac",
    "lighting",
    "appliance",
    "battery",
    "storage",
    "pool",
    "water-heater",
]

# Keep this list deliberately boring: these are site chrome / utility pages,
# not incentive-content heuristics. Downloadable files are handled separately.
DEEP_CRAWL_UTILITY_PATTERNS = [
    re.compile(
        r"/(?:\d+/)?(?:employment|jobs|careers|volunteer)(?:[-_/][^/?#]*)?(?:[/?#]|$)",
        re.I,
    ),
    re.compile(r"/(?:search/results|directory\.aspx)(?:[/?#]|$)", re.I),
    re.compile(r"/(?:login|sign-in|my-account)(?:[/?#]|$)", re.I),
    re.compile(
        r"/(?:privacy-policy|privacy|accessibility|conditions-of-use|terms(?:-of-use)?)(?:[/?#]|$)",
        re.I,
    ),
    re.compile(r"/(?:error-pages/404|404)(?:[/?#]|$)", re.I),
]


def _normalize_host(host: str) -> str:
    host = (host or "").strip().lower()
    if not host:
        return ""
    host = host.split(":", 1)[0].strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def _same_site(host_a: str, host_b: str) -> bool:
    a = _normalize_host(host_a)
    b = _normalize_host(host_b)
    if not a or not b:
        return False
    return a == b or a.endswith("." + b) or b.endswith("." + a)


def _url_key(url: str) -> tuple[str, str, str]:
    parsed = urlparse(url or "")
    path = (parsed.path or "/").rstrip("/") or "/"
    return _normalize_host(parsed.netloc), path, parsed.query


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
    if lower.endswith(".docx"):
        return True, "docx"
    if lower.endswith((".jpg", ".jpeg", ".png")):
        return True, "image"
    return False, ""


def extract_pdf_bytes(content: bytes) -> str | None:
    try:
        reader = PdfReader(io.BytesIO(content))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
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


def extract_excel_bytes(content: bytes) -> str | None:
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
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
        logger.error(f"Excel extraction failed: {e}")
        return None


def extract_excel_url(url: str) -> str | None:
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return extract_excel_bytes(response.content)
    except Exception as e:
        logger.error(f"Excel download failed for {url}: {e}")
        return None


def extract_docx_bytes(content: bytes) -> str | None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as docx_zip:
            names = [
                name
                for name in docx_zip.namelist()
                if name == "word/document.xml"
                or (name.startswith("word/header") and name.endswith(".xml"))
                or (name.startswith("word/footer") and name.endswith(".xml"))
            ]
            if not names:
                return None

            lines = []
            for name in names:
                root = ET.fromstring(docx_zip.read(name))
                for para in root.findall(
                    ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"
                ):
                    words = [
                        node.text
                        for node in para.findall(
                            ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
                        )
                        if node.text
                    ]
                    if words:
                        lines.append("".join(words))

        text = "\n".join(lines).strip()
        return text or None
    except Exception as e:
        logger.error(f"DOCX extraction failed: {e}")
        return None


def extract_docx_url(url: str) -> str | None:
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return extract_docx_bytes(response.content)
    except Exception as e:
        logger.error(f"DOCX download failed for {url}: {e}")
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


def _trim_text(text: str, truncation_length: int) -> str:
    if truncation_length and truncation_length > 0:
        return text[:truncation_length]
    return text


def _make_source(
    *,
    url: str,
    url_type: str,
    text: str | None,
    parent_url: str | None = None,
    title: str = "",
    truncation_length: int = 0,
) -> Optional[dict]:
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    return {
        "url": url,
        "parent_url": parent_url,
        "url_type": url_type,
        "title": title or "",
        "text": _trim_text(cleaned, truncation_length),
    }


def _is_probably_pdf_url(url: str) -> bool:
    if not url:
        return False
    path = (urlparse(url).path or "").lower()
    if path.endswith(".pdf") or path.endswith("pdf"):
        return True
    lowered = url.lower()
    pdf_markers = ["format=pdf", "/pdf", "download=1", "download=true", "file="]
    return any(marker in lowered for marker in pdf_markers)


def _file_type_for_url(url: str) -> str:
    _, file_type = is_file_url(url)
    if file_type:
        return file_type
    if _is_probably_pdf_url(url):
        return "pdf"
    return ""


def _is_supported_aux_file(url: str) -> bool:
    return _file_type_for_url(url) in {"pdf", "excel", "docx"}


def _extract_file_links_from_html(html: str, base_url: str) -> List[str]:
    if not html or not html.strip():
        return []

    try:
        soup = BeautifulSoup(html, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            absolute = urljoin(base_url, a["href"]).split("#")[0]
            if _is_supported_aux_file(absolute):
                links.append(absolute)
        return list(dict.fromkeys(links))
    except Exception as e:
        logger.warning(f"Auxiliary link parsing failed for {base_url}: {e}")
        return []


def _build_deep_crawl_config(
    *,
    max_depth: int = 2,
    max_pages: int = DEEP_CRAWL_MAX_PAGES,
) -> CrawlerRunConfig:
    download_filter = URLPatternFilter(DEEP_CRAWL_DOWNLOAD_PATTERNS, reverse=True)
    utility_filter = URLPatternFilter(DEEP_CRAWL_UTILITY_PATTERNS, reverse=True)
    priority_scorer = KeywordRelevanceScorer(DEEP_CRAWL_PRIORITY_KEYWORDS)
    strategy = BestFirstCrawlingStrategy(
        max_depth=max(0, int(max_depth)),
        include_external=False,
        filter_chain=FilterChain([download_filter, utility_filter]),
        url_scorer=priority_scorer,
        max_pages=max(1, int(max_pages)),
    )
    return CrawlerRunConfig(
        deep_crawl_strategy=strategy,
        scraping_strategy=LXMLWebScrapingStrategy(),
        stream=True,
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


def _extract_file_links_from_result(result, base_url: str) -> List[str]:
    found: List[str] = []
    html = getattr(result, "html", None)
    if html and str(html).strip():
        found.extend(_extract_file_links_from_html(str(html), base_url))

    links = getattr(result, "links", None)
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
        if _is_supported_aux_file(absolute):
            found.append(absolute)

    return list(dict.fromkeys(found))


def _coerce_results(res) -> List:
    if res is None:
        return []
    if isinstance(res, list):
        return res
    return [res]


def _source_from_result(seed_url: str, result, truncation_length: int) -> Optional[dict]:
    success = bool(getattr(result, "success", False))
    status_code = getattr(result, "status_code", 200)
    if not success or status_code != 200:
        return None

    final_url, text = _extract_result_text(result)
    source_url = final_url or seed_url
    result_netloc = urlparse(source_url).netloc
    seed_netloc = urlparse(seed_url).netloc
    if seed_netloc and result_netloc and not _same_site(result_netloc, seed_netloc):
        return None

    metadata = _extract_result_metadata(result)
    parent_url = None if _url_key(source_url) == _url_key(seed_url) else seed_url
    return _make_source(
        url=source_url,
        parent_url=parent_url,
        url_type="pdf" if _is_pdf_result(result) else "web",
        text=text,
        title=metadata.get("title", ""),
        truncation_length=truncation_length,
    )


def _sources_from_results(seed_url: str, results: Iterable, truncation_length: int) -> List[dict]:
    sources = []
    for result in results:
        source = _source_from_result(seed_url, result, truncation_length)
        if source:
            sources.append(source)
    return _dedupe_sources(sources)


def _same_site_url(candidate_url: str, seed_url: str) -> bool:
    candidate_netloc = urlparse(candidate_url).netloc
    seed_netloc = urlparse(seed_url).netloc
    return not candidate_netloc or not seed_netloc or _same_site(candidate_netloc, seed_netloc)


def _collect_file_candidates(seed_url: str, results: Iterable) -> List[str]:
    found: List[str] = []
    for result in results:
        base_url = getattr(result, "url", None) or getattr(result, "final_url", None) or seed_url
        for file_url in _extract_file_links_from_result(result, base_url):
            if _same_site_url(file_url, seed_url):
                found.append(file_url)
    return list(dict.fromkeys(found))


def _fetch_file_source(
    file_url: str,
    *,
    parent_url: str,
    truncation_length: int,
    session: requests.Session,
) -> Optional[dict]:
    file_type = _file_type_for_url(file_url)
    if file_type not in {"pdf", "excel", "docx"}:
        return None

    try:
        response = session.get(file_url, timeout=20)
        if response.status_code != 200:
            return None
        content_length = int(response.headers.get("Content-Length") or 0)
        if content_length and content_length > AUX_MAX_BYTES:
            return None
        raw = response.content
        if len(raw) > AUX_MAX_BYTES:
            return None

        if file_type == "pdf":
            text = extract_pdf_bytes(raw)
        elif file_type == "excel":
            text = extract_excel_bytes(raw)
        else:
            text = extract_docx_bytes(raw)

        return _make_source(
            url=file_url,
            parent_url=parent_url,
            url_type=file_type,
            text=text,
            truncation_length=truncation_length,
        )
    except Exception as e:
        logger.warning(f"Auxiliary download failed for {file_url}: {e}")
        return None


def _fetch_file_sources(
    file_urls: List[str],
    *,
    parent_url: str,
    truncation_length: int,
) -> List[dict]:
    if not file_urls:
        return []

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (compatible; IncentivAI-merge/1.0; "
                "+https://example.invalid)"
            )
        }
    )

    sources = []
    for file_url in file_urls:
        source = _fetch_file_source(
            file_url,
            parent_url=parent_url,
            truncation_length=truncation_length,
            session=session,
        )
        if source:
            sources.append(source)
    return _dedupe_sources(sources)


def _dedupe_sources(sources: List[dict]) -> List[dict]:
    deduped = []
    seen = set()
    for source in sources:
        key = (source.get("url") or "").split("#")[0]
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped


async def _async_deep_scrape(
    seed_url: str,
    *,
    timeout: int = 60,
    max_depth: int = 2,
    max_pages: int = DEEP_CRAWL_MAX_PAGES,
):
    config = _build_deep_crawl_config(max_depth=max_depth, max_pages=max_pages)
    results = []
    async with AsyncWebCrawler() as crawler:
        result_stream = await crawler.arun(url=seed_url, config=config)
        try:
            async with asyncio.timeout(timeout):
                async for result in result_stream:
                    results.append(result)
        except TimeoutError:
            logger.warning(
                "Deep crawl timeout for %s; keeping %s partial result(s)",
                seed_url,
                len(results),
            )
        return results


async def _async_shallow_scrape(seed_url: str, timeout: int = 45):
    config = CrawlerRunConfig(scraping_strategy=LXMLWebScrapingStrategy())
    async with AsyncWebCrawler() as crawler:
        return await asyncio.wait_for(crawler.arun(url=seed_url, config=config), timeout=timeout)


async def _async_pdf_scrape(pdf_url: str, timeout: int = 60):
    config = _build_pdf_run_config()
    async with AsyncWebCrawler(crawler_strategy=PDFCrawlerStrategy()) as crawler:
        return await asyncio.wait_for(crawler.arun(url=pdf_url, config=config), timeout=timeout)


def _scrape_shallow_sources(
    url: str,
    truncation_length: int,
    shallow_timeout: int = 60,
) -> List[dict]:
    shallow = asyncio.run(_async_shallow_scrape(url, timeout=shallow_timeout))
    shallow_results = _coerce_results(shallow)
    sources = _sources_from_results(url, shallow_results, truncation_length)
    file_sources = _fetch_file_sources(
        _collect_file_candidates(url, shallow_results),
        parent_url=url,
        truncation_length=truncation_length,
    )
    return _dedupe_sources(sources + file_sources)


def _direct_file_source(url: str, file_type: str, truncation_length: int) -> Optional[dict]:
    if file_type == "pdf":
        content = extract_pdf_url(url)
    elif file_type == "excel":
        content = extract_excel_url(url)
    elif file_type == "docx":
        content = extract_docx_url(url)
    elif file_type == "image":
        content = extract_image_url(url)
    else:
        content = None

    return _make_source(
        url=url,
        url_type=file_type,
        text=content,
        truncation_length=truncation_length,
    )


def scrape_sources(
    url: str,
    truncation_length: int = 30000,
    *,
    use_deep_crawl: bool = True,
    deep_crawl_timeout_sec: int = 120,
    max_depth: int = 2,
    max_pages: int = DEEP_CRAWL_MAX_PAGES,
) -> List[dict]:
    """
    Return one source record per scraped page or file.
    """
    try:
        bootstrap_crawl4ai_env()

        _, file_type = is_file_url(url)
        if file_type:
            source = _direct_file_source(url, file_type, truncation_length)
            return [source] if source else []

        if _is_probably_pdf_url(url):
            logger.info(f"Direct PDF URL detected: {url}")
            pdf_result = asyncio.run(_async_pdf_scrape(url, timeout=120))
            return _sources_from_results(url, _coerce_results(pdf_result), truncation_length)

        if not use_deep_crawl:
            logger.info(f"Deep crawl disabled; shallow crawl for {url}")
            sources = _scrape_shallow_sources(url, truncation_length)
            if not sources:
                logger.error(f"Shallow crawl produced no content for {url}")
            return sources

        crawl_result = asyncio.run(
            _async_deep_scrape(
                url,
                timeout=deep_crawl_timeout_sec,
                max_depth=max_depth,
                max_pages=max_pages,
            )
        )
        html_results = _coerce_results(crawl_result)
        sources = _sources_from_results(url, html_results, truncation_length)
        file_sources = _fetch_file_sources(
            _collect_file_candidates(url, html_results),
            parent_url=url,
            truncation_length=truncation_length,
        )
        sources = _dedupe_sources(sources + file_sources)
        if not sources:
            logger.warning(f"Deep crawl produced no usable sources for {url}; trying shallow crawl")
            sources = _scrape_shallow_sources(url, truncation_length)
        if not sources:
            logger.error(f"No pages or files successfully crawled for {url}")
        return sources

    except asyncio.TimeoutError:
        logger.error(f"Deep crawl timeout for {url}")
        try:
            sources = _scrape_shallow_sources(url, truncation_length)
            if not sources:
                logger.error(f"Shallow crawl produced no content for {url}")
            return sources
        except Exception as e:
            logger.error(f"Shallow crawl failed for {url}: {e}")
            return []

    except Exception as e:
        logger.error(f"Scrape failed for {url}: {e}")
        return []


def scrape_url(
    url: str,
    truncation_length: int = 30000,
    *,
    use_deep_crawl: bool = True,
    deep_crawl_timeout_sec: int = 120,
    max_depth: int = 2,
    max_pages: int = DEEP_CRAWL_MAX_PAGES,
) -> tuple[Optional[str], str]:
    """
    Backward-compatible wrapper around scrape_sources().
    """
    sources = scrape_sources(
        url,
        truncation_length,
        use_deep_crawl=use_deep_crawl,
        deep_crawl_timeout_sec=deep_crawl_timeout_sec,
        max_depth=max_depth,
        max_pages=max_pages,
    )
    if not sources:
        return None, _file_type_for_url(url) or "web"

    blocks = []
    for source in sources:
        title = source.get("title", "")
        header = source.get("url", url)
        if title:
            header = f"{header} | TITLE: {title}"
        blocks.append(f"--- SOURCE: {header} ---\n{source.get('text', '')}")
    return (
        _trim_text("\n\n".join(blocks), truncation_length),
        sources[0].get("url_type", "web"),
    )
