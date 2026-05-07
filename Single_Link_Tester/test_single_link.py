import os
import glob
import asyncio
import io
import hashlib
import argparse
from urllib.parse import urlparse, urljoin
import pandas as pd
from bs4 import BeautifulSoup
import aiohttp

# Crawl4AI imports
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
from crawl4ai.deep_crawling.filters import FilterChain, SEOFilter, DomainFilter
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from crawl4ai.processors.pdf import PDFCrawlerStrategy, PDFContentScrapingStrategy

# Langchain imports
from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# ---------------------------------------------------------
# CONSTANTS & CONFIGURATION
# ---------------------------------------------------------

#Model Name
model_name = "llama3.2"

PDF_KEYWORDS = [
    "incentive", "rebate", "grant", "funding", "assistance", 
    "opportunity", "application", "eligibility", "program", 
    "efficiency", "solar", "ev", "charger"
]

TEMPLATE = '''
You are a strict utility rebate analyst. Your job is to extract actionable utility rebate programs.

CRITICAL INSTRUCTIONS:
1. If this document is merely a news article, a blog post,
a glossary, or general advice about energy efficiency,
YOU MUST ABORT and output EXACTLY: "NOT RELEVANT: No concrete rebate program found."
2. Only proceed if the document explicitly outlines a specific, currently active rebate,
incentive, or grant program offered by a utility company or government entity.

OUTPUT FORMATTING:
You MUST format your output STRICTLY in Markdown. Use exact headers and bullet points as follows:

# Program Name:[Extract Program Name]

#Program URL: [Extract Program URL]

## Program Details
- **Concrete Rebate Amounts:**
- [Amount 1]
- [Amount 2]
- [...list ALL applicable amounts]

## Eligibility
- **Eligibility Requirements:**
- [Requirement 1]
- [Requirement 2]
- [...list ALL applicable requirements]

## Utility Information
- **Utility Company Name:** [Extract Utility Name]
- **Utility Company Size:** [Extract Utility Size]

Do not include any other conversational text or preamble. Output ONLY the strict markdown structure.
If information DOES NOT have rebate information, DON'T append to results.
DO NOT INCLUDE ANY OTHER TEXT OR EXPLANATION. ONLY THE MARKDOWN STRUCTURE WITH THE RELEVANT INFORMATION.

Document URL/Source: {source}
Document Text:
{document_text}
'''

FILTER_TEMPLATE = '''
You are a final-stage quality control analyst. 
Below is a raw markdown report containing extracted utility rebate programs from various pages. 
Some sections might say "NOT RELEVANT: No concrete rebate program found", or contain empty fields, or have unrelated data.

Your job is to read the raw report and output a CLEAN, CONSOLIDATED markdown report that ONLY includes the valid, concrete rebate programs. 
- Discard any section that says "NOT RELEVANT".
- Discard any conversational filler.
- Keep the exact markdown structure for valid programs: 
  # Program Name, #Program URL, ## Program Details, ## Eligibility, ## Utility Information.
- Make sure to keep program details and eligibility requirements as bullet points under their respective headers.

If there are NO valid programs in the entire raw report, output EXACTLY: "NO REBATES FOUND."

Raw Report:
{raw_report}
'''

# ---------------------------------------------------------
# SCRAPER MODULE
# ---------------------------------------------------------
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
        
        base_netloc = urlparse(base_url).netloc
        
        for link in links:
            url = urljoin(base_url, link).split('#')[0]
            link_netloc = urlparse(url).netloc
            
            # Skip if it leaves the parent site
            if base_netloc and link_netloc and not link_netloc.endswith(base_netloc):
                continue
                
            lowered = url.lower()
            if lowered.endswith('.pdf'):
                pdf_links.add(url)
            elif lowered.endswith(('.xls', '.xlsx')):
                excel_links.add(url)
                
        ranked_pdfs = sorted(list(pdf_links), key=_score_pdf_url, reverse=True)[:3]
        target_excels = list(excel_links)[:2]

        for pdf_url in ranked_pdfs:
            pdf_text = await _scrape_pdf_with_crawl4ai(pdf_url)
            if pdf_text and pdf_text.strip():
                extracted_content[pdf_url] = pdf_text

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

async def scrape_single_link(url: str, use_deep_crawl: bool, truncation_length: int = 150000):
    print(f"\n" + "="*60)
    print(f"Starting crawl for single link: {url}")
    print("="*60)
    
    seed_netloc = urlparse(url).netloc
    
    if use_deep_crawl:
        grant_scorer = KeywordRelevanceScorer(keywords=PDF_KEYWORDS, weight=0.8)
        seo_filter = SEOFilter(threshold=0.3, keywords=PDF_KEYWORDS)
        domain_filter = DomainFilter(allowed_domains=[seed_netloc])
        
        strategy = BestFirstCrawlingStrategy(
            max_depth=3,
            include_external=False,
            url_scorer=grant_scorer,
            filter_chain=FilterChain([domain_filter, seo_filter]),
        )
        config = CrawlerRunConfig(
            deep_crawl_strategy=strategy,
            scraping_strategy=LXMLWebScrapingStrategy(),
            cache_mode=CacheMode.BYPASS,
        )
    else:
        config = CrawlerRunConfig(
            scraping_strategy=LXMLWebScrapingStrategy(),
            cache_mode=CacheMode.BYPASS,
        )

    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(base_dir, "scraped_data")
    os.makedirs(output_dir, exist_ok=True)
    
    generated_files = []

    async with AsyncWebCrawler() as crawler:
        try:
            res = await crawler.arun(url=url, config=config)
            current_results = res if isinstance(res, list) else [res]
            
            for r in current_results:
                url_r = getattr(r, 'url', 'Unknown URL')
                
                # Strict check
                if url_r != 'Unknown URL':
                    r_netloc = urlparse(url_r).netloc
                    if seed_netloc and r_netloc and not r_netloc.endswith(seed_netloc):
                        continue
                        
                metadata = getattr(r, 'metadata', {})
                status_code = getattr(r, 'status_code', 200)
                
                if getattr(r, 'success', False) and status_code == 200:
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
                        
                    aux_content = await process_auxiliary_files(getattr(r, 'html', ''), url_r)
                    for aux_url, aux_text in aux_content.items():
                        scraped_text += f"\n\n--- EMBEDDED FILE CONTENT: {aux_url} ---\n\n{aux_text}\n"
                    
                    if truncation_length and len(scraped_text) > truncation_length:
                        scraped_text = scraped_text[:truncation_length] + "\n\n...[TRUNCATED TO PREVENT OVERWHELMING ANALYZER]"
                        
                    url_hash = hashlib.md5(url_r.encode('utf-8')).hexdigest()[:8]
                    domain = urlparse(url_r).netloc
                    safe_domain = domain.replace(".", "_")
                        
                    filename = f"{safe_domain}_{url_hash}.md"
                    file_path_out = os.path.join(output_dir, filename)
                    
                    with open(file_path_out, "w", encoding="utf-8") as f:
                        f.write(f"--- SOURCE: {url_r} ---\n\n")
                        f.write(scraped_text)
                    print(f"Saved content to: {file_path_out}")
                    generated_files.append(file_path_out)

        except Exception as e:
            print(f"Error crawling {url}: {e}")

    print(f"\nCrawled and saved {len(generated_files)} pages to scraped_data/")
    return generated_files


# ---------------------------------------------------------
# ANALYZER MODULE
# ---------------------------------------------------------
def analyze_scraped_files(filepaths: list, model_name: str = "llama3.2", temperature: float = 0.1):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    results_dir = os.path.join(base_dir, "analysis_results")
    error_log_path = os.path.join(base_dir, "analysis_errors.log")
    os.makedirs(results_dir, exist_ok=True)

    def log_error(msg: str):
        print(msg)
        with open(error_log_path, "a", encoding="utf-8") as ef:
            ef.write(msg + "\n")

    if not filepaths:
        print("No files to analyze.")
        return []
        
    modified_results_files = set()

    model = OllamaLLM(model=model_name, temperature=temperature)
    prompt = ChatPromptTemplate.from_template(TEMPLATE)
    chain = prompt | model | StrOutputParser()

    print(f"\n{'='*60}\nStarting Analysis of {len(filepaths)} files...\n{'='*60}")

    for filepath in filepaths:
        filename = os.path.basename(filepath)
        base_name = filename.replace(".md", "")

        # Replicate Kaleb's grouping logic: domain_hash.md -> domain
        parts = base_name.rsplit("_", 1)
        safe_domain = parts[0] if (len(parts) == 2 and len(parts[1]) == 8) else base_name

        result_filepath = os.path.join(results_dir, f"{safe_domain}_analysis.md")

        # Skip if already analyzed
        if os.path.exists(result_filepath):
            try:
                with open(result_filepath, "r", encoding="utf-8") as check_f:
                    if f"--- SOURCE: {filename} ---" in check_f.read():
                        print(f"\nSkipping {filename}: Analysis already exists in {os.path.basename(result_filepath)}")
                        modified_results_files.add(result_filepath)
                        continue
            except Exception:
                pass

        print(f"\nAnalyzing {filename}...")

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                file_content = f.read()

            results = chain.invoke({"source": filename, "document_text": file_content})

            print(f"Results for {filename}:\n{results}\n" + "-" * 60)

            # Prevent bloating the file by dropping NOT RELEVANT, empty, or incorrectly formatted results
            results_upper = results.upper()
            is_irrelevant = "NOT RELEVANT" in results_upper or "PROGRAM NAME: NONE" in results_upper or "PROGRAM NAME: NOT RELEVANT" in results_upper
            
            # The LLM sometimes drops the "Program Name:" part of the header, so we check for the reliable sub-headers
            has_details = "## PROGRAM DETAILS" in results_upper
            has_eligibility = "## ELIGIBILITY" in results_upper
            missing_structure = not (has_details or has_eligibility)
            
            if is_irrelevant or missing_structure:
                print(f"Skipping append for {filename} because no concrete, formatted rebate was found.")
                continue

            # APPEND to the shared domain analysis file just like Kaleb!
            with open(result_filepath, "a", encoding="utf-8") as f:
                f.write(f"\n\n--- SOURCE: {filename} ---\n\n")
                f.write(results)
                f.write("\n")
            print(f"Appended analysis to: {result_filepath}")
            modified_results_files.add(result_filepath)

        except Exception as e:
            log_error(f"Error processing {filename}: {e}")
            
    return list(modified_results_files)

# ---------------------------------------------------------
# FINAL FILTER MODULE
# ---------------------------------------------------------
def filter_analysis_results(result_filepaths: list, model_name: str = "llama3.2", temperature: float = 0.1):
    if not result_filepaths:
        return
        
    model = OllamaLLM(model=model_name, temperature=temperature)
    prompt = ChatPromptTemplate.from_template(FILTER_TEMPLATE)
    chain = prompt | model | StrOutputParser()
    
    print(f"\n{'='*60}\nStarting Final Filtering Pass on {len(result_filepaths)} domains...\n{'='*60}")
    
    for filepath in result_filepaths:
        if not os.path.exists(filepath):
            continue
            
        base_name = os.path.basename(filepath).replace("_analysis.md", "")
        final_filepath = os.path.join(os.path.dirname(filepath), f"{base_name}_FINAL_rebates.md")
        
        print(f"\nFiltering {os.path.basename(filepath)}...")
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                raw_report = f.read()
                
            filtered_result = chain.invoke({"raw_report": raw_report})
            
            print(f"Filtered Results for {base_name}:\n{filtered_result}\n" + "-" * 60)
            
            with open(final_filepath, "w", encoding="utf-8") as f:
                f.write(f"# FINAL REBATE EXTRACTION FOR: {base_name}\n\n")
                f.write(filtered_result)
                f.write("\n")
                
            print(f"Saved clean rebates to: {final_filepath}")
            
        except Exception as e:
            print(f"Error filtering {filepath}: {e}")

# ---------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Crawling and Analyzing a Single Link exactly like Kaleb.")
    parser.add_argument(
        "--url", 
        type=str, 
        default="http://cpuc.ca.gov/energyefficiency/",
        help="The URL to scrape and analyze"
    )
    parser.add_argument(
        "--no-deep-crawl", 
        action="store_true", 
        help="Disable deep crawling"
    )
    parser.add_argument(
        "--model", 
        type=str, 
        default="llama3.2",
        help="The Ollama model to use"
    )
    parser.add_argument(
        "--analyze-only", 
        action="store_true", 
        help="Skip crawling and analyze all pre-scraped markdown files in scraped_data/"
    )
    parser.add_argument(
        "--filter-only", 
        action="store_true", 
        help="Skip crawling and initial analysis, and ONLY run the final filter pass on files in analysis_results/"
    )
    args = parser.parse_args()
    
    if args.filter_only:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        results_dir = os.path.join(base_dir, "analysis_results")
        result_files = [f for f in glob.glob(os.path.join(results_dir, "*_analysis.md")) if not f.endswith("_FINAL_rebates.md")]
        print(f"Filter-only mode: Found {len(result_files)} pre-analyzed files in '{results_dir}'.")
        
        # 3. Filter the analysis results to extract only actual rebates
        filter_analysis_results(result_files, model_name=args.model)
        
    elif args.analyze_only:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        scraped_dir = os.path.join(base_dir, "scraped_data")
        generated_files = glob.glob(os.path.join(scraped_dir, "*.md"))
        print(f"Analyze-only mode: Found {len(generated_files)} pre-scraped files in '{scraped_dir}'.")
        
        # 2. Analyze the generated files
        result_files = analyze_scraped_files(generated_files, model_name=args.model)
        
        # 3. Filter the analysis results to extract only actual rebates
        filter_analysis_results(result_files, model_name=args.model)
        
    else:
        # 1. Scrape the URL
        generated_files = asyncio.run(scrape_single_link(args.url, not args.no_deep_crawl))
        
        # 2. Analyze the generated files
        result_files = analyze_scraped_files(generated_files, model_name=args.model)
        
        # 3. Filter the analysis results to extract only actual rebates
        filter_analysis_results(result_files, model_name=args.model)
