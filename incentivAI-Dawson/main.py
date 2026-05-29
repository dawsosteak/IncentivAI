import os
import csv
import datetime
from modules.url_source import get_urls
from modules.scraper import scrape_url, scrape_all_pages, is_file_url
from modules.processor import process_text
from modules.exporter import export_to_csv, append_markdown_entry
from utils.logger import get_logger
from config import ERRORS_CSV, MARKDOWN_CSV, MODEL_NAME, DEFAULT_TEMPERATURE

logger = get_logger()


def log_error(url: str, url_type: str, stage: str, reason: str, detail: str = ""):
    """
    Append a structured error entry to errors.csv.

    Columns:
        timestamp  - when the error occurred
        url        - the URL that failed
        url_type   - web / pdf / excel / image
        stage      - scraping / llm_parsing / llm_timeout / llm_extraction / unknown
        reason     - short human readable reason
        detail     - full error message capped at 500 chars
    """
    file_exists = os.path.isfile(ERRORS_CSV)
    with open(ERRORS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["timestamp", "url", "url_type", "stage", "reason", "detail"],
            quoting=csv.QUOTE_ALL
        )
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "url": url,
            "url_type": url_type,
            "stage": stage,
            "reason": reason,
            "detail": str(detail)[:500]
        })


def _process_page(url, parent, url_type, content, temperature, timestamp,
                  all_results, progress_callback, idx, total,
                  provider="ollama", model=None):
    """
    Run LLM extraction on a single scraped page and append to all_results.
    Shared by both main links and sublinks.
    """
    is_sublink = parent is not None

    if progress_callback:
        label = f"[sublink of {parent}]" if is_sublink else "[main link]"
        progress_callback(
            idx, total,
            url=url,
            message=f"({idx}/{total}) {label} Running LLM on: {url}"
        )

    try:
        structured = process_text(content, url, temperature,
                                  provider=provider, model=model)
        structured["source_url"] = url
        structured["parent_url"] = parent
        structured["is_sublink"] = is_sublink
        structured["url_type"] = url_type
        structured["extraction_timestamp"] = timestamp
        all_results.append(structured)
        append_markdown_entry(structured, MARKDOWN_CSV)

    except Exception as e:
        error_str = str(e)
        if "timed out" in error_str.lower():
            stage, reason = "llm_timeout", "LLM call exceeded time limit"
        elif "valid json" in error_str.lower():
            stage, reason = "llm_parsing", "LLM returned malformed JSON after all retries"
        else:
            stage, reason = "llm_extraction", "LLM extraction failed"

        log_error(url, url_type, stage, reason, error_str)
        all_results.append(_empty_result(url, parent, url_type, timestamp))


def run_pipeline(
    mode,
    uploaded_file,
    state,
    temperature=DEFAULT_TEMPERATURE,
    truncation_length=8000,
    progress_callback=None,
    cancel_flag=None,
    provider="ollama",
    model=None,
):
    """
    Main pipeline: fetch URLs → scrape → LLM extract → export.

    Args:
        mode:               "Upload Excel", "Single URL", or "Upload Markdown"
        uploaded_file:      Excel/Markdown file object or file path string
        state:              unused, kept for API compatibility
        temperature:        LLM temperature
        truncation_length:  max chars of scraped content to send to LLM
        progress_callback:  callable(current, total, url, message)
        cancel_flag:        callable that returns True if user cancelled
        provider:           LLM provider (ollama, openai, uw_ssec, etc.)
        model:              model name override

    Returns:
        path to output CSV file
    """
    model = model or MODEL_NAME
    url_entries = get_urls(mode, uploaded_file, state)
    total_entries = len(url_entries)
    all_results = []
    idx = 0

    for entry in url_entries:
        if cancel_flag and cancel_flag():
            logger.info("Pipeline cancelled by user.")
            break

        main_url = entry["url"]
        excel_parent = entry["parent"]
        # For markdown mode, content is pre-loaded in the entry
        pre_loaded_content = entry.get("content")
        timestamp = datetime.datetime.utcnow().isoformat()
        idx += 1

        if progress_callback:
            progress_callback(
                idx, total_entries,
                url=main_url,
                message=f"({idx}/{total_entries}) [main link] Scraping: {main_url}"
            )

        # ── Markdown mode: content already loaded, skip scraping ─────────
        if pre_loaded_content is not None:
            _process_page(
                url=main_url, parent=excel_parent, url_type="markdown",
                content=pre_loaded_content, temperature=temperature,
                timestamp=timestamp, all_results=all_results,
                progress_callback=progress_callback,
                idx=idx, total=total_entries, provider=provider, model=model
            )
            continue

        # ── File types: scrape directly, process as single page ──────────
        _, file_type = is_file_url(main_url)
        if file_type in ("pdf", "excel", "image"):
            content, url_type = scrape_url(main_url, truncation_length)
            if content is None:
                log_error(main_url, file_type, "scraping",
                          f"No content extracted from {file_type} file",
                          "scrape_url returned None")
                all_results.append(_empty_result(main_url, excel_parent, file_type, timestamp))
                continue

            _process_page(
                url=main_url, parent=excel_parent, url_type=file_type,
                content=content, temperature=temperature, timestamp=timestamp,
                all_results=all_results, progress_callback=progress_callback,
                idx=idx, total=total_entries, provider=provider, model=model
            )
            continue

        # ── Web pages: deep crawl, process every discovered page ─────────
        pages = scrape_all_pages(main_url, truncation_length)

        if not pages:
            log_error(main_url, "web", "scraping",
                      "Deep crawl returned no pages",
                      "scrape_all_pages returned empty list")
            all_results.append(_empty_result(main_url, excel_parent, "web", timestamp))
            continue

        for page in pages:
            if cancel_flag and cancel_flag():
                logger.info("Pipeline cancelled by user.")
                break

            # Original URL keeps excel_parent; discovered sublinks get main_url as parent
            parent = excel_parent if page["url"] == main_url else page["parent"]

            _process_page(
                url=page["url"], parent=parent, url_type="web",
                content=page["content"], temperature=temperature,
                timestamp=datetime.datetime.utcnow().isoformat(),
                all_results=all_results, progress_callback=progress_callback,
                idx=idx, total=total_entries, provider=provider, model=model
            )

    return export_to_csv(all_results)


def _empty_result(url: str, parent, url_type: str, timestamp: str) -> dict:
    """Return a blank result dict for failed URLs."""
    return {
        "utility_company": None,
        "programs": [],
        "summary_of_page": None,
        "source_url": url,
        "parent_url": parent,
        "is_sublink": parent is not None,
        "url_type": url_type,
        "extraction_timestamp": timestamp
    }
