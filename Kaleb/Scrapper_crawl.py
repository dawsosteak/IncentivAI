import asyncio
import os
import pandas as pd
from urllib.parse import urlparse
import json
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
from crawl4ai.deep_crawling.filters import FilterChain, SEOFilter, ContentRelevanceFilter, URLPatternFilter
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
import aiohttp
import io
import pypdf
from urllib.parse import urljoin
from bs4 import BeautifulSoup

async def process_auxiliary_files(html, base_url):
    extracted_content = {}
    try:
        soup = BeautifulSoup(html, 'html.parser')
        links = [a.get('href') for a in soup.find_all('a', href=True)]
        
        # Filter for PDF and Excel files, deduplicate
        target_links = set()
        for link in links:
            url = urljoin(base_url, link).split('#')[0]
            if url.lower().endswith(('.pdf', '.xls', '.xlsx')):
                target_links.add(url)
                
        # Limit to 5 files to prevent overwhelming the scraper/analyzer
        target_links = list(target_links)[:5]
        
        if not target_links:
            return extracted_content

        async with aiohttp.ClientSession() as session:
            for url in target_links:
                try:
                    async with session.get(url, timeout=15) as resp:
                        if resp.status == 200:
                            # Restrict to 10MB to prevent memory issues
                            if int(resp.headers.get('Content-Length', 0)) > 10 * 1024 * 1024:
                                continue
                            
                            content = await resp.read()
                            
                            if url.lower().endswith('.pdf'):
                                pdf = pypdf.PdfReader(io.BytesIO(content))
                                text = "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())
                                if text.strip():
                                    extracted_content[url] = text
                                    
                            elif url.lower().endswith(('.xls', '.xlsx')):
                                dfs = pd.read_excel(io.BytesIO(content), sheet_name=None)
                                text = ""
                                for sheet, df in dfs.items():
                                    try:
                                        # Limit rows to 100 per table to avoid massive LLM fatigue
                                        text += f"\n### Sheet: {sheet}\n{df.head(100).to_markdown(index=False)}\n"
                                    except ImportError:
                                        # Fallback if tabulate is not installed
                                        text += f"\n### Sheet: {sheet}\n{df.head(100).to_csv(index=False)}\n"
                                if text.strip():
                                    extracted_content[url] = text
                except Exception as e:
                    print(f"Failed to extract {url}: {e}")
                    
    except Exception as e:
        print(f"Error processing auxiliary links: {e}")
        
    return extracted_content

# load URLs from Excel file
base_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(base_dir, "..", "Relevant URLs.xlsx")
url_list = pd.read_excel(file_path, header=None)[0].dropna().astype(str).tolist()
url_list = [url for url in url_list if url.startswith('http')]
url_test = url_list

async def main():
    #Define the Scorer
    grant_scorer = KeywordRelevanceScorer(
        keywords=["incentive", "grant", "funding", "assistance", "opportunity", "application", "eligibility", "rebate"], 
        weight=0.8
    )
    #Define the Filters
    seo_filter = SEOFilter(threshold=0.3, 
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
        cache_mode=CacheMode.BYPASS,
    )
    # from Analyzer_crawl import analyze_document
    results = []
    base_dir = os.path.dirname(os.path.abspath(__file__))
    progress_file = os.path.join(base_dir, "crawled_urls.txt")
    crawled_urls = set()
    if os.path.exists(progress_file):
        with open(progress_file, "r") as f:
            crawled_urls = set(line.strip() for line in f if line.strip())

    urls_to_crawl = [url for url in url_test if url not in crawled_urls]
    print(f"\nTotal URLs to process: {len(url_test)} | Already crawled: {len(crawled_urls)} | Remaining: {len(urls_to_crawl)}\n")

    async with AsyncWebCrawler() as crawler:
        for url in urls_to_crawl:
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
                        output_dir = os.path.join(base_dir, "scraped_data")
                        if not os.path.exists(output_dir):
                            os.makedirs(output_dir)
                            
                        # Create a unique filename for each URL to avoid massive files and duplication
                        import hashlib
                        url_hash = hashlib.md5(url_r.encode('utf-8')).hexdigest()[:8]
                        
                        # Extract the filename or domain to keep filenames clean
                        if url_r.startswith("file://"):
                            safe_domain = os.path.basename(urlparse(url_r).path).replace(".html", "").replace(".htm", "")
                        else:
                            domain = urlparse(url_r).netloc
                            safe_domain = domain.replace(".", "_")
                            
                        # Format: domain_hash.md
                        filename = f"{safe_domain}_{url_hash}.md"
                        file_path_out = os.path.join(output_dir, filename)
                        
                        # Extract auxiliary files (PDFs, Excels) found on the page
                        aux_content = await process_auxiliary_files(getattr(r, 'html', ''), url_r)
                        for aux_url, aux_text in aux_content.items():
                            scraped_text += f"\n\n--- EMBEDDED FILE CONTENT: {aux_url} ---\n\n{aux_text}\n"
                        
                        # Use write mode ("w") instead of append ("a") to prevent duplication on multiple runs
                        with open(file_path_out, "w", encoding="utf-8") as f:
                            f.write(f"--- SOURCE: {url_r} ---\n\n")
                            f.write(scraped_text)
                        print(f"Saved content to: {file_path_out}")
                        
                        # IMMEDIATELY ANALYZE (Commented out to run scraper separately)
                        #if scraped_text.strip():
                            #analyze_document(url_r, scraped_text)
            except Exception as e:
                print(f"Error crawling {url}: {e}")
            
            # --- SAVE PROGRESS ---
            # Mark this URL as completed in the progress file
            with open(progress_file, "a", encoding="utf-8") as f:
                f.write(url + "\n")
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
