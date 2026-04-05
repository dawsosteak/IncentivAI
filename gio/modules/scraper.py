import asyncio
import re
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from utils.logger import get_logger
import sys

# Windows-safe event loop
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
#Grab the logger for logging errors and info throughout the scraping process
logger = get_logger()
# removes html 
def clean_html(html):
    html = re.sub(r"<script.*?>.*?</script>", "", html, flags=re.DOTALL)
    html = re.sub(r"<style.*?>.*?</style>", "", html, flags=re.DOTALL)
    text = re.sub(r"\s+", " ", html)
    return text.strip()
# crawler function that uses crawl4ai to scrape the page
async def async_scrape(url, timeout=30):
    config = CrawlerRunConfig(scraping_strategy=LXMLWebScrapingStrategy())
    try:
        async with AsyncWebCrawler() as crawler:
            # Add a timeout to prevent hangs
            result = await asyncio.wait_for(crawler.arun(url=url, config=config), timeout)
            if not result.success:
                raise Exception(result.error_message)
            return result.html
    except asyncio.TimeoutError:
        logger.error(f"Timeout reached for {url}")
    except Exception as e:
        logger.error(f"Scraping failed for {url}: {e}")
    return None
def scrape_url(url, truncation_length=1000):
    try:
        html = asyncio.run(async_scrape(url))
        if html is None:
            return None
        cleaned = clean_html(html)
        return cleaned[:truncation_length]
    except Exception as e:
        logger.error(f"Scraping failed for {url}: {e}")
        return None
# Example usage
if __name__ == "__main__":
    urls = [
        "https://www.anaheim.net/3312/Public-EV-Charger-Rebate",
        "https://beachesenergy.com/my-account/energy-rebates",
        "https://cpi1.gpfulfillment.com/"
    ]
    #Testing urls
    loop = asyncio.ProactorEventLoop()
    asyncio.set_event_loop(loop)
    results = loop.run_until_complete(scrape_urls(urls))
    for url, content in zip(urls, results):
        print(f"\n--- {url} ---\n{content[:500] if content else 'Failed'}")