import os
import csv
import datetime
from modules.url_source import get_urls
from modules.scraper import scrape_url
from modules.processor import process_text
from modules.exporter import export_to_csv, append_markdown_entry
from utils.logger import get_logger
from config import ERRORS_CSV, MARKDOWN_CSV

logger = get_logger()


def log_error(url: str, url_type: str, stage: str, reason: str, detail: str = ""):
    file_exists = os.path.isfile(ERRORS_CSV)
    with open(ERRORS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["timestamp", "url", "url_type", "stage", "reason", "detail"],
            quoting=csv.QUOTE_ALL  # ← force quote every field
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


def run_pipeline(
    mode,
    uploaded_file,
    state,
    temperature,
    truncation_length,
    progress_callback=None,
    cancel_flag=None
):
    """
    Main pipeline: fetch URLs, scrape, extract with LLM, export.

    Args:
        cancel_flag: a callable that returns True if the user has cancelled.
    """
    urls = get_urls(mode, uploaded_file, state)
    total = len(urls)
    all_results = []

    # Track which URLs are sublinks vs main links
    # get_urls should return a list of dicts with "url" and "parent" keys,
    # or plain strings — we normalise both here
    normalised = []
    for entry in urls:
        if isinstance(entry, dict):
            normalised.append(entry)
        else:
            normalised.append({"url": entry, "parent": None})

    for idx, entry in enumerate(normalised, start=1):
        # Check cancel flag before each URL
        if cancel_flag and cancel_flag():
            logger.info("Pipeline cancelled by user.")
            break

        url = entry["url"]
        parent = entry["parent"]
        timestamp = datetime.datetime.utcnow().isoformat()
        is_sublink = parent is not None

        if progress_callback:
            link_label = f"[sublink of {parent}]" if is_sublink else "[main link]"
            progress_callback(
                idx, total,
                url=url,
                message=f"({idx}/{total}) {link_label} Scraping: {url}"
            )

        # --- Scraping ---
        try:
            scraped_text, url_type = scrape_url(url, truncation_length)
        except Exception as e:
            log_error(url, "unknown", "scraping", "Scraper raised an exception", str(e))
            all_results.append(_empty_result(url, parent, timestamp))
            continue

        if scraped_text is None:
            log_error(
                url, url_type, "scraping",
                f"No content extracted from {url_type} resource",
                "scrape_url returned None — page may be behind auth, empty, or unsupported format"
            )
            all_results.append(_empty_result(url, parent, timestamp))
            continue

        if progress_callback:
            progress_callback(
                idx, total,
                url=url,
                message=f"({idx}/{total}) Scraped {len(scraped_text)} chars — running LLM extraction..."
            )

        # --- LLM Extraction ---
        try:
            structured = process_text(scraped_text, url, temperature)
            structured["source_url"] = url
            structured["parent_url"] = parent
            structured["is_sublink"] = is_sublink
            structured["url_type"] = url_type
            structured["extraction_timestamp"] = timestamp
            all_results.append(structured)

            # Write markdown summary live so it appears in Streamlit while running
            append_markdown_entry(structured, MARKDOWN_CSV)

        except Exception as e:
            error_str = str(e)
            if "timed out" in error_str.lower():
                stage = "llm_timeout"
                reason = "LLM call exceeded time limit"
            elif "valid json" in error_str.lower():
                stage = "llm_parsing"
                reason = "LLM returned malformed JSON after all retries"
            else:
                stage = "llm_extraction"
                reason = "LLM extraction failed"

            log_error(url, url_type, stage, reason, error_str)
            all_results.append(_empty_result(url, parent, timestamp))

    return export_to_csv(all_results)


def _empty_result(url: str, parent: str | None, timestamp: str) -> dict:
    """Return a blank result dict for failed URLs."""
    return {
        "utility_company": None,
        "programs": [],
        "summary_of_page": None,
        "source_url": url,
        "parent_url": parent,
        "is_sublink": parent is not None,
        "url_type": "unknown",
        "extraction_timestamp": timestamp
    }