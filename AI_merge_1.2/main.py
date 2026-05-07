import csv
import datetime
import os

from modules.url_source import get_urls
from modules.scraper import scrape_sources
from modules.processor import process_text
from modules.exporter import export_to_csv, append_markdown_entry
from modules.raw_scrape_exporter import write_raw_scrape_markdown
from modules.llm_agent import OllamaNotRunningError, ensure_ollama_running
from utils.logger import get_logger
from config import ERRORS_CSV, MARKDOWN_CSV

logger = get_logger()


def log_error(url: str, url_type: str, stage: str, reason: str, detail: str = ""):
    file_exists = os.path.isfile(ERRORS_CSV)
    with open(ERRORS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["timestamp", "url", "url_type", "stage", "reason", "detail"],
            quoting=csv.QUOTE_ALL,
        )
        if not file_exists:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "url": url,
                "url_type": url_type,
                "stage": stage,
                "reason": reason,
                "detail": str(detail)[:500],
            }
        )


def _empty_result(
    url: str,
    parent: str | None,
    timestamp: str,
    url_type: str = "unknown",
) -> dict:
    return {
        "utility_company": None,
        "programs": [],
        "summary_of_page": None,
        "source_url": url,
        "parent_url": parent,
        "is_sublink": parent is not None,
        "url_type": url_type,
        "extraction_timestamp": timestamp,
    }


def run_pipeline(
    mode,
    uploaded_file,
    state,
    temperature,
    truncation_length,
    max_depth: int = 2,
    progress_callback=None,
    cancel_flag=None,
    use_deep_crawl: bool = True,
    deep_crawl_timeout_sec: int = 120,
    model_name: str | None = None,
    write_markdown: bool = True,
    write_raw_scrape_markdown_files: bool = False,
    raw_scrape_markdown_dir: str = "raw_scrapes",
):
    ensure_ollama_running()
    urls = get_urls(mode, uploaded_file, state)
    total = len(urls)
    all_results = []

    normalised = []
    for entry in urls:
        if isinstance(entry, dict):
            normalised.append(entry)
        else:
            normalised.append({"url": entry, "parent": None})

    for idx, entry in enumerate(normalised, start=1):
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
                idx,
                total,
                f"({idx}/{total}) {link_label} Scraping: {url}",
                url,
            )

        try:
            sources = scrape_sources(
                url,
                int(truncation_length),
                use_deep_crawl=use_deep_crawl,
                deep_crawl_timeout_sec=int(deep_crawl_timeout_sec),
                max_depth=int(max_depth),
            )
        except Exception as e:
            log_error(url, "unknown", "scraping", "Scraper raised an exception", str(e))
            all_results.append(_empty_result(url, parent, timestamp))
            continue

        if not sources:
            log_error(
                url,
                "unknown",
                "scraping",
                "No source records extracted",
                "scrape_sources returned an empty list",
            )
            all_results.append(_empty_result(url, parent, timestamp))
            continue

        if progress_callback:
            total_chars = sum(len(source.get("text", "")) for source in sources)
            progress_callback(
                idx,
                total,
                f"({idx}/{total}) Scraped {len(sources)} sources / {total_chars} chars.",
                url,
            )

        for source_idx, source in enumerate(sources, start=1):
            if cancel_flag and cancel_flag():
                logger.info("Pipeline cancelled by user.")
                break

            source_url = source.get("url") or url
            source_parent = source.get("parent_url")
            if source_parent is None:
                source_parent = parent
            source_type = source.get("url_type", "web")
            source_text = source.get("text", "")
            source_title = source.get("title", "")
            source_timestamp = datetime.datetime.utcnow().isoformat()

            if write_raw_scrape_markdown_files:
                try:
                    write_raw_scrape_markdown(
                        url=source_url,
                        parent_url=source_parent,
                        url_type=source_type,
                        scraped_text=source_text,
                        out_dir=raw_scrape_markdown_dir,
                    )
                except Exception as e:
                    log_error(
                        source_url,
                        source_type,
                        "raw_scrape_export",
                        "Failed to write raw scrape markdown",
                        str(e),
                    )

            if progress_callback:
                progress_callback(
                    idx,
                    total,
                    (
                        f"({idx}/{total}) Source {source_idx}/{len(sources)} "
                        f"({source_type}) scraped {len(source_text)} chars - running LLM extraction..."
                    ),
                    source_url,
                )

            try:
                structured = process_text(
                    source_text,
                    source_url,
                    temperature,
                    model_name=model_name,
                    source_type=source_type,
                    title=source_title,
                )
                structured["source_url"] = source_url
                structured["parent_url"] = source_parent
                structured["is_sublink"] = source_parent is not None
                structured["url_type"] = source_type
                structured["extraction_timestamp"] = source_timestamp
                all_results.append(structured)
                if write_markdown:
                    append_markdown_entry(structured, MARKDOWN_CSV)

            except OllamaNotRunningError:
                raise
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

                log_error(source_url, source_type, stage, reason, error_str)
                all_results.append(
                    _empty_result(source_url, source_parent, source_timestamp, source_type)
                )

    cancelled = bool(cancel_flag and cancel_flag())
    return export_to_csv(all_results), cancelled
