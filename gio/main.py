import datetime
import os
import sys

# Ensure this folder is on sys.path so `modules/*` imports work
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from modules.url_source import get_urls
from modules.scraper import scrape_url
from modules.processor import process_text
from modules.exporter import export_to_csv
from modules.llm_agent import OllamaNotRunningError, ensure_ollama_running
from utils.logger import get_logger
#get logger for logging errors and info throughout the pipeline
logger = get_logger()
## entire piopelien function that does everything
def run_pipeline(
    mode,
    uploaded_file,
    state,
    temperature,
    truncation_length,
    progress_callback=None,
    should_cancel=None,
):
    ensure_ollama_running()
    #gets list of urls
    urls = get_urls(mode, uploaded_file, state)
    total = len(urls)
    #list to hold all the results we get from processing each url
    all_results = []
    timestamp = datetime.datetime.utcnow().isoformat()
    cancelled = False
    if total == 0 and progress_callback:
        progress_callback(0, 1, "No URLs to process")
    #loop through urls and process each one, updating progress
    for idx, url in enumerate(urls, start=1):
        if should_cancel and should_cancel():
            cancelled = True
            break
        if progress_callback:
            progress_callback(
                idx,
                total,
                f"[{idx}/{total}] Crawling (may take ~2 min)… {url}",
            )
        print(
            f"[Pipeline] [{idx}/{total}] Starting crawl for {url}",
            flush=True,
        )
        try:
            scraped_text = scrape_url(url, truncation_length)
            if progress_callback:
                progress_callback(
                    idx,
                    total,
                    f"[{idx}/{total}] Ollama extraction… {url}",
                )
            print(
                f"[Pipeline] [{idx}/{total}] Crawl finished, calling Ollama for {url}",
                flush=True,
            )
            structured = process_text(scraped_text, url, temperature)
            structured["source_url"] = url
            structured["extraction_timestamp"] = timestamp
            all_results.append(structured)
            print(
                f"[Pipeline] [{idx}/{total}] Finished URL: {url}",
                flush=True,
            )
            if progress_callback:
                progress_callback(
                    idx,
                    total,
                    f"[{idx}/{total}] Done. {url}",
                )
        except OllamaNotRunningError:
            raise
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            all_results.append({
                "utility_company": None,
                "programs": [],
                "summary_of_page": None,
                "source_url": url,
                "extraction_timestamp": timestamp
            })

    if progress_callback:
        progress_callback(total, total, "Writing CSV…")
    path = export_to_csv(all_results)
    print(f"[Pipeline] Wrote CSV: {path}", flush=True)
    if progress_callback:
        progress_callback(total, total, "Complete — ready to download.")
    return path, cancelled
