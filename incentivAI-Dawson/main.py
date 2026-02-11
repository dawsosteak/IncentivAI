from modules.excel_reader import get_urls_from_excel
from modules.url_queue_manager import URLQueueManager
from modules.content_scraper import scrape
from modules.ollama_agent import summarize
from modules.llm_extractor import extract
from modules.database_manager import DatabaseManager

def main():
    excel_path = input("Path to Excel file: ").strip()

    urls = get_urls_from_excel(excel_path)
    queue = URLQueueManager()
    queue.add_urls(urls)

    db = DatabaseManager()

    while True:
        url = queue.get_next_url()
        if not url:
            break

        print(f"Processing {url}")
        text = scrape(url)
        summary = summarize(text)
        record = extract(summary, url)
        db.add(record)

    db.save()
    print("Done")

if __name__ == "__main__":
    main()
