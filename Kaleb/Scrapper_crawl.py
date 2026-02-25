import asyncio
import os
import pandas as pd
from urllib.parse import urlparse
import json
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
from crawl4ai.deep_crawling.filters import FilterChain, SEOFilter, ContentRelevanceFilter, URLPatternFilter
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy



# load URLs from Excel file
file_path = os.path.join("..", "Relevant URLs.xlsx")
url_list = pd.read_excel(file_path, header=None)[0].dropna().astype(str).tolist()
url_list = [url for url in url_list if url.startswith('http')]
url_test = url_list[:100]


async def main():
    #Define the Scorer
    grant_scorer = KeywordRelevanceScorer(
        keywords=["incentive", "grant", "funding", "assistance", "opportunity", "application", "eligibility", "rebate"], 
        weight=0.7
    )
    #Define the Filters
    seo_filter = SEOFilter(threshold=0.5, 
                           keywords=["rebate", "incentive", "grant", "funding",
                                      "assistance", "opportunity", "application", "eligibility"]  # Keywords to look for in SEO metadata
    )

    strategy = BestFirstCrawlingStrategy(
        max_depth=2,
        include_external=False,
        #check_robots_txt=False,
        url_scorer=grant_scorer,
        filter_chain=FilterChain([seo_filter]),
    )

    config = CrawlerRunConfig(
        deep_crawl_strategy = strategy,
        scraping_strategy=LXMLWebScrapingStrategy(),
    )


    results = []
    async with AsyncWebCrawler() as crawler:
        batch_result = []
        for url in url_test:
            print(f"Starting deep crawl for: {url}")
            try:
                res = await crawler.arun(url=url, config=config)
                if isinstance(res, list):
                    batch_result.extend(res)
                else:
                    batch_result.append(res)
            except Exception as e:
                print(f"Error crawling {url}: {e}")
        
        print("\n" + "="*60)
        print("CRAWL LOG")
        print("="*60)

        for res in batch_result:
            # res is a CrawlResult object
            url = getattr(res, 'url', 'Unknown URL')
            metadata = getattr(res, 'metadata', {})
            
            # Check for success
            if getattr(res, 'success', False):
                results.append(res)
                score = metadata.get("score", 0)
                depth = metadata.get("depth", 0)
                print(f"Depth: {depth} | Score: {score:.2f} | ✅ {url}")
                
                # Output scraped information as requested by the user
                scraped_text = ""
                if hasattr(res, 'markdown') and res.markdown:
                    scraped_text = str(res.markdown)
                elif hasattr(res, 'html') and res.html:
                    scraped_text = str(res.html)
                
                print(f"--- Scraped Information ---")
                print(scraped_text)
                print("-" * 35)
                
                # Define the output directory
                output_dir = "scraped_data"
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)

                # --- Inside your scraping loop ---

                # 1. Extract the domain (e.g., "https://blog.example.com/post" -> "blog.example.com")
                domain = urlparse(url).netloc
                # Replace dots with underscores to keep filenames clean (optional)
                safe_domain = domain.replace(".", "_")
                filename = f"{safe_domain}.md"
                file_path = os.path.join(output_dir, filename)

                # 2. Use append mode ("a") to add to the existing file instead of overwriting it
                with open(file_path, "a", encoding="utf-8") as f:
                 # Add a header so you know where one page ends and the next begins
                    f.write(f"\n\n--- SOURCE: {url} ---\n\n")
                    f.write(scraped_text)

                print(f"Appended content from {url} to: {file_path}")
                

    # 5. Analyze the results
    if not results:
        print("\nNo high-value pages were successfully crawled.")
        return

    print("\n" + "="*60)
    print(" FINAL SUMMARY")
    print("="*60)
    print(f"Crawled {len(results)} high-value pages total")
    
    avg_score = sum(getattr(r, 'metadata', {}).get('score', 0) for r in results) / len(results)
    print(f"Average relevance score: {avg_score:.2f}")

    # Group by depth
    depth_counts = {}
    for r in results:
        d = getattr(r, 'metadata', {}).get('depth', 0)
        depth_counts[d] = depth_counts.get(d, 0) + 1

    print("\nPages crawled by depth:")
    for depth, count in sorted(depth_counts.items()):
        print(f"  Depth {depth}: {count} pages")

if __name__ == "__main__":
    asyncio.run(main())