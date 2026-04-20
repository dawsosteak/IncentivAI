import asyncio
import os
import sys

# Ensure the current directory is in the path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from Scrapper_crawl import main as scrape_main
from Analyzer_crawl import analyze_document

async def run_pipeline():
    print("============================================================")
    print("IncentivAI Pipeline")
    print("============================================================")
    print("Select an operation mode:")
    print("1. Analyze existing scraped data (skip crawling)")
    print("2. Crawl and scrape new URLs ONLY")
    print("3. Crawl, scrape, AND analyze URLs")
    print("============================================================")
    
    choice = input("Enter your choice (1, 2, or 3): ").strip()
    
    if choice == '1':
        print("\n--- Starting Analyzer on Existing Scraped Data ---")
        analyze_document(interactive=False)
    elif choice == '2':
        print("\n--- Starting Scraper ---")
        await scrape_main()
    elif choice == '3':
        print("\n--- Starting Full Pipeline ---")
        await scrape_main()
        print("\n--- Starting Analyzer ---")
        analyze_document(interactive=False)
    else:
        print("Invalid choice. Exiting.")
        return

    print("\nPipeline finished!")
    print("============================================================")

if __name__ == "__main__":
    try:
        asyncio.run(run_pipeline())
    except KeyboardInterrupt:
        print("\nPipeline interrupted by user.")
    except Exception as e:
        print(f"\nPipeline failed with error: {e}")
