import asyncio
import os
import sys

# Ensure the current directory is in the path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from Scrapper_crawl import main as scrape_main

async def run_pipeline():
    print("============================================================")
    print("STEP 1: Starting Scraper and Analyzer Pipeline")
    print("============================================================")
    # Execute the scraping logic which now automatically analyzes each page immediately
    await scrape_main()
    print("\nPipeline finished! All results have been saved to the 'analysis_results' folder.")
    print("============================================================")

if __name__ == "__main__":
    try:
        asyncio.run(run_pipeline())
    except KeyboardInterrupt:
        print("\nPipeline interrupted by user.")
    except Exception as e:
        print(f"\nPipeline failed with error: {e}")
