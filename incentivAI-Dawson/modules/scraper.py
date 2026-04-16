import asyncio
import re
import sys
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from utils.logger import get_logger

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

logger = get_logger()

INCENTIVE_KEYWORDS = [
    "incentive", "grant", "funding", "assistance",
    "opportunity", "application", "eligibility", "rebate","program", "financial", "support", "subsidy", "aid","discount","benefit","credit"
]

def clean_html(html):
    html = re.sub(r"<script.*?>.*?</script>", "", html, flags=re.DOTALL)
    html = re.sub(r"<style.*?>.*?</style>", "", html, flags=re.DOTALL)
    text = re.sub(r"\s+", " ", html)
    return text.strip()

async def async_scrape(url, timeout=120):
    scorer = KeywordRelevanceScorer(keywords=INCENTIVE_KEYWORDS, weight=0.5)

    strategy = BestFirstCrawlingStrategy(
        max_depth=2,
        include_external=False
    )

    browser_config = BrowserConfig(
        headless=True,
        java_script_enabled=True,
    )

    config = CrawlerRunConfig(
        deep_crawl_strategy=strategy,
        scraping_strategy=LXMLWebScrapingStrategy(),
        page_timeout=30000,
    )

    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await asyncio.wait_for(
                crawler.arun(url=url, config=config), timeout
            )

            results = result if isinstance(result, list) else [result]
            successful = [r for r in results if getattr(r, "success", False)]

            if not successful:
                raise Exception("No pages crawled successfully.")

            best = max(
                successful,
                key=lambda r: getattr(r, "metadata", {}).get("score", 0)
            )

            if hasattr(best, "markdown") and best.markdown:
                return str(best.markdown)
            elif hasattr(best, "html") and best.html:
                return best.html

    except asyncio.TimeoutError:
        logger.error(f"Timeout reached for {url}")
    except Exception as e:
        logger.error(f"Scraping failed for {url}: {e}")

    return None

def scrape_url(url, truncation_length=1000):
    try:
        content = asyncio.run(async_scrape(url))
        if content is None:
            return None
        if content.lstrip().startswith("<"):
            content = clean_html(content)
        return content[:truncation_length]
    except Exception as e:
        logger.error(f"Scraping failed for {url}: {e}")
        return None