import logging
import json
import os
import pandas as pd
from typing import List, Dict, Optional
import ollama
from scraper import ContentScraper  # Import the original scraper class

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
OLLAMA_MODEL = "qwen2.5"

def extract_data_with_ollama(text_content: str, model_name: str = OLLAMA_MODEL) -> Dict[str, str]:
    """
    Extracts structured data using a more robust text-parsing approach for smaller models.
    """
    if not text_content or len(text_content) < 50:
        return {
            "utility_name": "No Content",
            "rebate_amount": "N/A",
            "requirements": "N/A",
            "client_size": "N/A",
            "notes": "Scraped content was empty or too short."
        }
        
    # 1. Truncate but keep more context for Qwen (32k context window), leaving room for prompt/response.
    truncated_text = text_content[:25000] 

    # 2. Construct a prompt
    prompt = f"""
    Analyze the text below to find energy rebate/incentive information. 
    If there are multiple incentives, add them all. If a source is not available, leave it blank. 
    If information is not found, use "Not specified".
    
    TEXT:
    \"\"\"
    {truncated_text}
    \"\"\"

    Extract the following 5 fields.
    
    Utility Name: [Name of the utility company]
    Rebate Amount: [Dollar amount or percentage, e.g. $500 or 75%]
    Requirements: [Brief eligibility or equipment requirements]
    Client Size: [Residential, Commercial, Industrial, or size limit]
    Notes: [Any warnings, "Redacted", "See details", or broken page errors]

    RESPONSE FORMAT (Do not use markdown tables):
    Utility Name: ...
    Rebate Amount: ...
    Requirements: ...
    Client Size: ...
    Notes: ...
    """

    # Use the structured prompt below for better extraction results
        
    try:
        response = ollama.chat(model=model_name, messages=[{'role': 'user', 'content': prompt}])
        content = response['message']['content']
        
        # Simple parsing by line with cleanup
        data = {
            "utility_name": "Not specified",
            "rebate_amount": "Not specified", 
            "requirements": "Not specified",
            "client_size": "Not specified",
            "notes": ""
        }
        
        for line in content.split('\n'):
            # Clean up markdown chars
            clean_line = line.strip().strip('|').strip('*').strip()
            
            # Skip table headers or empty lines
            if "---" in clean_line or len(clean_line) < 5 or ":" not in clean_line:
                continue

            # Parse key: value
            parts = clean_line.split(":", 1)
            if len(parts) != 2:
                continue
                
            # Clean key: remove stars, extra spaces, lower case
            key = parts[0].strip().replace('*', '').lower()
            val = parts[1].strip()

            if "utility name" in key:
                data["utility_name"] = val
            elif "rebate amount" in key:
                data["rebate_amount"] = val
            elif "requirements" in key:
                data["requirements"] = val
            elif "client size" in key:
                data["client_size"] = val
            elif "notes" in key:
                data["notes"] = val
                
        # Fallback: if data is mostly empty, put raw response in notes (truncated)
        if data["utility_name"] == "Not specified" and data["rebate_amount"] == "Not specified":
             data["notes"] = f"Raw LLM Output: {content[:100]}..."

        return data

    except Exception as e:
        logger.error(f"Error calling Ollama: {e}")
        return {
            "utility_name": "Extraction Error",
            "rebate_amount": "Error",
            "requirements": "Error",
            "client_size": "Error",
            "notes": f"Ollama failed: {str(e)}"
        }

def main():
    # 1. Setup paths
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    excel_path = os.path.join(base_dir, 'Relevant URLs.xlsx')
    output_path = os.path.join(base_dir, 'Extracted_Incentives.xlsx')
    debug_dir = os.path.join(base_dir, 'debug_scrapes')
    
    if not os.path.exists(debug_dir):
        os.makedirs(debug_dir)

    if not os.path.exists(excel_path):
        excel_path = 'Relevant URLs.xlsx' # Fallback
        if not os.path.exists(excel_path):
             logger.error("Could not find Relevant URLs.xlsx")
             return

    # 2. Load URLs
    try:
        df_urls = pd.read_excel(excel_path, header=None)
        urls = df_urls[0].tolist()
        # Limit to first 30 for testing/demo purposes 
        urls_to_process = urls[10:30] 
        logger.info(f"Processing {len(urls_to_process)} URLs...")
    except Exception as e:
        logger.error(f"Error reading Excel: {e}")
        return

    # 3. Initialize Scraper with better headers
    scraper = ContentScraper()
    # Update headers to avoid 403 blocks
    scraper.session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    })

    results = []

    # 4. Process
    for i, url in enumerate(urls_to_process):
        logger.info(f"Processing ({i+1}/{len(urls)}): {url}")
        
        try:
            raw_content = scraper.fetch_content(url)
            
            # DEBUG: Save content to file (Commented out for production run)
            # safe_name = "".join([c if c.isalnum() else "_" for c in url[-20:]])
            # with open(os.path.join(debug_dir, f"{i}_{safe_name}.txt"), "w", encoding="utf-8") as f:
            #    f.write(raw_content)
            
            # Check for blocking messages in content
            if "Access Denied" in raw_content or "403 Forbidden" in raw_content:
                logger.warning(f"Blocked by {url}")
                results.append({"URL": url, "Notes": "Access Denied / Blocked by website"})
                continue
                
        except Exception as e:
            logger.error(f"Scrape error {url}: {e}")
            results.append({"URL": url, "Notes": f"Scrape Error: {e}"})
            continue

        extracted = extract_data_with_ollama(raw_content)
        extracted["URL"] = url
        results.append(extracted)

    # 5. Save


    # 5. Save to Excel
    try:
        df_results = pd.DataFrame(results)
        df_results.to_excel(output_path, index=False)
        logger.info(f"Successfully saved extracted data to: {output_path}")
    except Exception as e:
        logger.error(f"Failed to save Excel file: {e}")

if __name__ == "__main__":
    main()
