import asyncio
import re
import sys
import pdfplumber
import openpyxl
import requests
from io import BytesIO
from PIL import Image
import pytesseract
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from utils.logger import get_logger

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

logger = get_logger()


def clean_html(html: str) -> str:
    """Strip scripts, styles, and collapse whitespace from raw HTML."""
    html = re.sub(r"<script.*?>.*?</script>", "", html, flags=re.DOTALL)
    html = re.sub(r"<style.*?>.*?</style>", "", html, flags=re.DOTALL)
    text = re.sub(r"\s+", " ", html)
    return text.strip()


def is_file_url(url: str) -> tuple[bool, str]:
    """
    Check if a URL points directly to a file we can extract.
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
        logger.info(f"Extracted PDF content from {url} ({len(text)} chars)")
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
            logger.warning(f"Excel file had no extractable content: {url}")
            return None
        logger.info(f"Extracted Excel content from {url} ({len(text)} chars)")
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
        logger.info(f"Extracted image OCR content from {url} ({len(text)} chars)")
        return text
    except Exception as e:
        logger.error(f"Image OCR extraction failed for {url}: {e}")
        return None


async def async_scrape(url: str, timeout: int = 120) -> str | None:
    """
    Scrape a single URL with JavaScript enabled.
    No filtering, no scoring — grab everything and return it.
    """
    browser_config = BrowserConfig(
        headless=True,
        java_script_enabled=True,
    )

    config = CrawlerRunConfig(
        scraping_strategy=LXMLWebScrapingStrategy(),
        page_timeout=30000,
    )

    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await asyncio.wait_for(
                crawler.arun(url=url, config=config), timeout
            )

            results = result if isinstance(result, list) else [result]
            successful = [r for r in results if getattr(r, "success", False)]

            if not successful:
                raise Exception("No pages crawled successfully.")

            # Just take the first result — no scoring, no filtering
            page = successful[0]

            if hasattr(page, "markdown") and page.markdown:
                return str(page.markdown)
            elif hasattr(page, "html") and page.html:
                return page.html

    except asyncio.TimeoutError:
        logger.error(f"Timeout reached for {url}")
    except Exception as e:
        logger.error(f"Scraping failed for {url}: {e}")

    return None


def scrape_url(url: str, truncation_length: int = 8000) -> tuple[str | None, str]:
    """
    Main entry point for scraping a single URL.
    Detects file types (PDF, Excel, image) and routes accordingly.
    Falls back to a full JS-enabled web scrape for standard pages.

    Returns:
        (content, url_type) where url_type is one of:
        "web", "pdf", "excel", "image"
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

    # Standard web page — full scrape, no filtering
    try:
        content = asyncio.run(async_scrape(url))
        if content is None:
            return None, "web"
        if content.lstrip().startswith("<"):
            content = clean_html(content)
        return content[:truncation_length], "web"
    except Exception as e:
        logger.error(f"Scraping failed for {url}: {e}")
        return None, "web"