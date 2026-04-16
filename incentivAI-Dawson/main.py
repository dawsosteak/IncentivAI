import os
import csv
import datetime
from modules.url_source import get_urls
from modules.scraper import scrape_url
from modules.processor import process_text
from modules.exporter import export_to_csv
from utils.logger import get_logger

logger = get_logger()

def log_error(url, reason, error_file="errors.csv"):
    file_exists = os.path.isfile(error_file)
    with open(error_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "url", "reason"])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "url": url,
            "reason": reason
        })

def run_pipeline(mode, uploaded_file, state, temperature, truncation_length, progress_callback=None):
    urls = get_urls(mode, uploaded_file, state)
    total = len(urls)
    all_results = []

    for idx, url in enumerate(urls, start=1):
        timestamp = datetime.datetime.utcnow().isoformat()

        if progress_callback:
            progress_callback(idx, total, f"Processing {url}")

        try:
            scraped_text = scrape_url(url, truncation_length)
            if scraped_text is None:
                logger.error(f"Scraping returned no content for {url}")
                log_error(url, "Scraping returned no content")
                all_results.append({
                    "utility_company": None,
                    "programs": [],
                    "summary_of_page": None,
                    "source_url": url,
                    "extraction_timestamp": timestamp
                })
                continue

            structured = process_text(scraped_text, url, temperature)
            structured["source_url"] = url
            structured["extraction_timestamp"] = timestamp
            all_results.append(structured)

        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            log_error(url, str(e))
            all_results.append({
                "utility_company": None,
                "programs": [],
                "summary_of_page": None,
                "source_url": url,
                "extraction_timestamp": timestamp
            })

    return export_to_csv(all_results)