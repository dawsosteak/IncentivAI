import asyncio
import os
import pandas as pd
from urllib.parse import urlparse, urljoin
import json
from bs4 import BeautifulSoup
import aiohttp
import io
import hashlib

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
from crawl4ai.deep_crawling.filters import FilterChain, SEOFilter
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from crawl4ai.processors.pdf import PDFCrawlerStrategy, PDFContentScrapingStrategy

PDF_KEYWORDS = [
    "incentive", "rebate", "grant", "funding", "assistance", 
    "opportunity", "application", "eligibility", "program", 
    "efficiency", "solar", "ev", "charger"
]

def _score_pdf_url(url: str) -> int:
    lowered = url.lower()
    score = 0
    for kw in PDF_KEYWORDS:
        if kw in lowered:
            score += 2
    bonus_terms = ["guide", "manual", "form", "terms"]
    for kw in bonus_terms:
        if kw in lowered:
            score += 1
    return score

async def _scrape_pdf_with_crawl4ai(pdf_url: str):
    print(f"    -> Scraping PDF gracefully via Crawl4AI: {pdf_url}")
    pdf_scraping_strategy = PDFContentScrapingStrategy(
        extract_images=False,
        save_images_locally=False,
        batch_size=4,
    )
    config = CrawlerRunConfig(scraping_strategy=pdf_scraping_strategy, cache_mode=CacheMode.BYPASS)
    try:
        async with AsyncWebCrawler(crawler_strategy=PDFCrawlerStrategy()) as crawler:
            res = await asyncio.wait_for(crawler.arun(url=pdf_url, config=config), timeout=120)
            
            # Extract Text gracefully focusing on raw_markdown or standard markdown
            md = getattr(res, "markdown", None)
            extracted = ""
            if md:
                try:
                    markdown_result = getattr(md, "_markdown_result", None)
                    if markdown_result is not None:
                        extracted = str(getattr(markdown_result, "fit_markdown", "") or "")
                        if not extracted.strip():
                            extracted = str(getattr(markdown_result, "raw_markdown", "") or "")
                    if not extracted.strip():
                        extracted = str(md)
                except Exception:
                    extracted = str(md)
            if not extracted:
                html = getattr(res, "html", None)
                if html:
                    extracted = str(html)
                    
            return extracted
    except Exception as e:
        print(f"    -> Failed to scrape PDF {pdf_url}: {e}")
        return ""


async def process_auxiliary_files(html, base_url):
    extracted_content = {}
    try:
        soup = BeautifulSoup(html, 'html.parser')
        links = [a.get('href') for a in soup.find_all('a', href=True)]
        
        pdf_links = set()
        excel_links = set()
        
        for link in links:
            url = urljoin(base_url, link).split('#')[0]
            lowered = url.lower()
            if lowered.endswith('.pdf'):
                pdf_links.add(url)
            elif lowered.endswith(('.xls', '.xlsx')):
                excel_links.add(url)
                
        # Top 3 PDFs based on scoring instead of arbitrary 5
        ranked_pdfs = sorted(list(pdf_links), key=_score_pdf_url, reverse=True)[:3]
        
        # Limit excel files strictly to 2 to avoid overwhelming output
        target_excels = list(excel_links)[:2]

        # 1. Scrape PDFs using Crawl4AI Strategy
        for pdf_url in ranked_pdfs:
            pdf_text = await _scrape_pdf_with_crawl4ai(pdf_url)
            if pdf_text and pdf_text.strip():
                extracted_content[pdf_url] = pdf_text

        # 2. Scrape Excels using existing logic (Pandas)
        if target_excels:
            async with aiohttp.ClientSession() as session:
                for url in target_excels:
                    try:
                        async with session.get(url, timeout=15) as resp:
                            if resp.status == 200:
                                if int(resp.headers.get('Content-Length', 0)) > 10 * 1024 * 1024:
                                    continue
                                content = await resp.read()
                                dfs = pd.read_excel(io.BytesIO(content), sheet_name=None)
                                text = ""
                                for sheet, df in dfs.items():
                                    try:
                                        text += f"\n### Sheet: {sheet}\n{df.head(100).to_markdown(index=False)}\n"
                                    except ImportError:
                                        text += f"\n### Sheet: {sheet}\n{df.head(100).to_csv(index=False)}\n"
                                if text.strip():
                                    extracted_content[url] = text
                    except Exception as e:
                        print(f"    -> Failed to extract Excel {url}: {e}")
    except Exception as e:
        print(f"Error processing auxiliary links: {e}")
        
    return extracted_content

# load URLs from Excel file
base_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(base_dir, "..", "Relevant URLs.xlsx")
try:
    url_list = pd.read_excel(file_path, header=None)[0].dropna().astype(str).tolist()
    url_list = [url for url in url_list if url.startswith('http')]
    url_test = url_list
except Exception as e:
    print(f"Could not load URLs from excel: {e}")
    url_test = []

async def main():
    if not url_test:
        return
        
    #Define the Scorer
    grant_scorer = KeywordRelevanceScorer(
        keywords= PDF_KEYWORDS, 
        weight=0.8
    )
    #Define the Filters
    seo_filter = SEOFilter(threshold=0.3, 
                           keywords= PDF_KEYWORDS  # Keywords to look for in SEO metadata
    )
    strategy = BestFirstCrawlingStrategy(
        max_depth=3,
        include_external=False,
        url_scorer=grant_scorer,
        filter_chain=FilterChain([seo_filter]),
    )
    config = CrawlerRunConfig(
        deep_crawl_strategy = strategy,
        scraping_strategy=LXMLWebScrapingStrategy(),
        cache_mode=CacheMode.BYPASS,
    )
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
                    
                    status_code = getattr(r, 'status_code', 200)
                    if getattr(r, 'success', False) and status_code == 200:
                        results.append(r)
                        score = metadata.get("score", 0)
                        depth = metadata.get("depth", 0)
                        print(f"Depth: {depth} | Score: {score:.2f} | ✅ Crawled: {url_r}")
                        
                        scraped_text = ""
                        if hasattr(r, 'markdown') and r.markdown:
                            try:
                                scraped_text = str(r.markdown._markdown_result.fit_markdown)
                                if not scraped_text.strip():
                                    scraped_text = str(r.markdown._markdown_result.raw_markdown)
                            except AttributeError:
                                scraped_text = str(r.markdown)
                        elif hasattr(r, 'html') and r.html:
                            scraped_text = str(r.html)
                        
                        output_dir = os.path.join(base_dir, "scraped_data")
                        if not os.path.exists(output_dir):
                            os.makedirs(output_dir)
                            
                        # Extract auxiliary files (PDFs, Excels) found on the page
                        aux_content = await process_auxiliary_files(getattr(r, 'html', ''), url_r)
                        for aux_url, aux_text in aux_content.items():
                            scraped_text += f"\n\n--- EMBEDDED FILE CONTENT: {aux_url} ---\n\n{aux_text}\n"

                        url_hash = hashlib.md5(url_r.encode('utf-8')).hexdigest()[:8]
                        if url_r.startswith("file://"):
                            safe_domain = os.path.basename(urlparse(url_r).path).replace(".html", "").replace(".htm", "")
                        else:
                            domain = urlparse(url_r).netloc
                            safe_domain = domain.replace(".", "_")
                            
                        filename = f"{safe_domain}_{url_hash}.md"
                        file_path_out = os.path.join(output_dir, filename)
                        
                        with open(file_path_out, "w", encoding="utf-8") as f:
                            f.write(f"--- SOURCE: {url_r} ---\n\n")
                            f.write(scraped_text)
                        print(f"Saved content to: {file_path_out}")
                        
            except Exception as e:
                print(f"Error crawling {url}: {e}")
            
            with open(progress_file, "a", encoding="utf-8") as f:
                f.write(url + "\n")

    if not results:
        print("\nNo high-value pages were successfully crawled.")
        return
    print("\n" + "="*60)
    print(" FINAL SUMMARY")
    print("="*60)
    print(f"Crawled {len(results)} high-value pages total")
    
    avg_score = sum(getattr(r, 'metadata', {}).get('score', 0) for r in results) / len(results)
    print(f"Average relevance score: {avg_score:.2f}")
    depth_counts = {}
    for r in results:
        d = getattr(r, 'metadata', {}).get('depth', 0)
        depth_counts[d] = depth_counts.get(d, 0) + 1
    print("\nPages crawled by depth:")
    for depth, count in sorted(depth_counts.items()):
        print(f"  Depth {depth}: {count} pages")

if __name__ == "__main__":
    asyncio.run(main())
