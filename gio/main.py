import datetime
from modules.url_source import get_urls
from modules.scraper import scrape_url
from modules.processor import process_text
from modules.exporter import export_to_csv
from utils.logger import get_logger
#get logger for logging errors and info throughout the pipeline
logger = get_logger()
## entire piopelien function that does everything
def run_pipeline(mode, uploaded_file, state, temperature, truncation_length, progress_callback=None):
    #gets list of urls 
    urls = get_urls(mode, uploaded_file, state)
    total = len(urls)
    #list to hold all the results we get from processing each url
    all_results = []
    timestamp = datetime.datetime.utcnow().isoformat()
    #loop through urls and process each one, updating progress 
    for idx, url in enumerate(urls, start=1):
        if progress_callback:
            progress_callback(idx, total, f"Processing {url}")
        # for each url, we scrape the content, process it to extract structured info, and add it to our results list
        try:
            scraped_text = scrape_url(url, truncation_length)
            structured = process_text(scraped_text, url, temperature)
            structured["source_url"] = url
            structured["extraction_timestamp"] = timestamp
            all_results.append(structured)
        #error messaging
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            all_results.append({
                "utility_company": None,
                "programs": [],
                "summary_of_page": None,
                "source_url": url,
                "extraction_timestamp": timestamp
            })

    return export_to_csv(all_results)
