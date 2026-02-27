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
    from Analyzer_crawl import analyze_document
    results = []
    async with AsyncWebCrawler() as crawler:
        for url in url_test:
            print(f"\n" + "="*60)
            print(f"Starting deep crawl for: {url}")
            print("="*60)
            try:
                res = await crawler.arun(url=url, config=config)
                current_results = res if isinstance(res, list) else [res]
                
                for r in current_results:
                    url_r = getattr(r, 'url', 'Unknown URL')
                    metadata = getattr(r, 'metadata', {})
                    
                    # Check for success and HTTP 200 OK
                    status_code = getattr(r, 'status_code', 200) # Default to 200 if missing for some reason
                    if getattr(r, 'success', False) and status_code == 200:
                        results.append(r)
                        score = metadata.get("score", 0)
                        depth = metadata.get("depth", 0)
                        print(f"Depth: {depth} | Score: {score:.2f} | ✅ Crawled: {url_r}")
                        
                        # Output scraped information as requested by the user
                        scraped_text = ""
                        if hasattr(r, 'markdown') and r.markdown:
                            # Try to use fit_markdown (core content) to reduce boilerplate links
                            try:
                                scraped_text = str(r.markdown._markdown_result.fit_markdown)
                                if not scraped_text.strip():
                                    scraped_text = str(r.markdown._markdown_result.raw_markdown)
                            except AttributeError:
                                scraped_text = str(r.markdown)
                        elif hasattr(r, 'html') and r.html:
                            scraped_text = str(r.html)
                        
                        # Define the output directory
                        output_dir = "scraped_data"
                        if not os.path.exists(output_dir):
                            os.makedirs(output_dir)
                        # Extract the domain to keep filenames clean
                        domain = urlparse(url_r).netloc
                        safe_domain = domain.replace(".", "_")
                        filename = f"{safe_domain}.md"
                        file_path_out = os.path.join(output_dir, filename)
                        # Use append mode ("a") to add to the existing file
                        with open(file_path_out, "a", encoding="utf-8") as f:
                            f.write(f"\n\n--- SOURCE: {url_r} ---\n\n")
                            f.write(scraped_text)
                        print(f"Saved content to: {file_path_out}")
                        
                        # IMMEDIATELY ANALYZE
                        if scraped_text.strip():
                            analyze_document(url_r, scraped_text)
            except Exception as e:
                print(f"Error crawling {url}: {e}")
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
