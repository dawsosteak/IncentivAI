"""
# Web Finder - Company Website Discovery Tool

This script automatically finds official websites for companies by:
1. Searching Google via SerpAPI
2. Scoring results using fuzzy string matching
3. Validating candidates by checking page content

## Dependencies
Install required packages with:
    pip install requests rapidfuzz tldextract beautifulsoup4 pandas
"""

import requests
from rapidfuzz import fuzz
from bs4 import BeautifulSoup
import tldextract
import pandas as pd
import json 

# ============================================================================
# CONFIGURATION
# ============================================================================
# Your SerpAPI key for Google search queries
# Get one at: https://serpapi.com
SERP_API_KEY = "9e0b9bcb598c0d6c5a659d921b3452c1165d5b3f6156946db0e7bd378fd972a8"


# ============================================================================
# STEP 1: GOOGLE SEARCH
# ============================================================================
def serp_search(company_name, num=5):
    """
    Search Google for the company's official website using SerpAPI.
    
    Args:
        company_name (str): The name of the company to search for
        num (int): Number of search results to return (default: 5)
    
    Returns:
        list: A list of organic search results, each containing:
              - 'link': The URL of the result
              - 'title': The page title
              - 'snippet': A brief description from the search result
    
    How it works:
        - Appends "official website" to the company name for better results
        - Sends a GET request to SerpAPI's Google search endpoint
        - Returns the organic (non-ad) search results
    """
    params = {
        "engine": "google",
        "q": f"{company_name} official website",
        "api_key": SERP_API_KEY,
        "num": num
    }
    r = requests.get("https://serpapi.com/search.json", params=params)
    r.raise_for_status()  # Raises an exception if the request failed
    return r.json().get("organic_results", [])


# ============================================================================
# STEP 2: DOMAIN EXTRACTION
# ============================================================================
def extract_domain(url):
    """
    Extract the clean domain name from a full URL.
    
    Args:
        url (str): A full URL like "https://www.example.com/page"
    
    Returns:
        str: The domain name like "example.com"
    
    How it works:
        - Uses tldextract to parse the URL into components
        - Combines the domain and suffix (e.g., "example" + "com")
        - Handles edge cases where there's no suffix
    
    Example:
        extract_domain("https://www.anaheim.net/123/utilities")
        -> "anaheim.net"
    """
    ext = tldextract.extract(url)
    return f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain


# ============================================================================
# STEP 3: CANDIDATE SCORING
# ============================================================================
def score_candidate(company_name, url, title, snippet):
    """
    Score how likely a search result is the official company website.
    
    Args:
        company_name (str): The company name we're searching for
        url (str): The URL of the search result
        title (str): The page title from the search result
        snippet (str): The description snippet from the search result
    
    Returns:
        int: A score from 0-100 indicating confidence level
             (100 = perfect match, 0 = no match)
    
    How it works:
        Uses fuzzy string matching (partial_ratio) to compare the company 
        name against three different signals:
        
        1. **Title match**: Does the page title contain the company name?
           Example: "City of Anaheim | Official Website" matches well
        
        2. **Snippet match**: Does the description mention the company?
           Example: "Welcome to Anaheim Public Utilities..." matches well
        
        3. **Domain match**: Is the company name in the domain?
           Example: "anaheim.net" partially matches "city of anaheim"
        
        Returns the highest score among all three signals, giving the
        candidate the benefit of the doubt.
    """
    domain = extract_domain(url)
    
    # Compare company name to each signal using fuzzy matching
    s_name_title = fuzz.partial_ratio(company_name.lower(), (title or "").lower())
    s_name_snip = fuzz.partial_ratio(company_name.lower(), (snippet or "").lower())
    s_domain = fuzz.partial_ratio(company_name.lower(), domain.lower())
    
    # Return the best match score
    return max(s_name_title, s_name_snip, s_domain)


# ============================================================================
# STEP 4: HOMEPAGE VALIDATION
# ============================================================================
def validate_homepage(url, company_name):
    """
    Verify that a URL is actually the company's official homepage.
    
    Args:
        url (str): The URL to validate
        company_name (str): The company name to look for on the page
    
    Returns:
        tuple: (is_valid, metadata)
               - is_valid (bool): True if the page appears to be official
               - metadata (dict or None): Contains 'title' and 'h1' if valid
    
    How it works:
        1. Fetches the actual webpage content
        2. Parses the HTML to extract the page title and first H1 heading
        3. Checks if the first word of the company name appears in either
        
        This helps filter out:
        - Directory listings (like Yelp, LinkedIn)
        - News articles about the company
        - Other non-official pages
    
    Example:
        For "city of anaheim public utilities":
        - Checks if "city" appears in the page title or H1
        - Returns True if found, False otherwise
    """
    try:
        # Fetch the page with a browser-like User-Agent to avoid blocks
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        
        if r.status_code != 200:
            return False, None
        
        # Parse the HTML content
        soup = BeautifulSoup(r.text, "html.parser")
        
        # Extract the page title
        title = (soup.title.string or "") if soup.title else ""
        
        # Extract the first H1 heading
        h1 = (soup.find("h1").get_text(separator=" ") if soup.find("h1") else "")
        
        # Combine title and H1 for checking
        text = " ".join([title, h1]).lower()
        
        # Check if the first word of the company name is present
        first_word = company_name.lower().split()[0]
        is_valid = first_word in text
        
        return is_valid, {"title": title, "h1": h1}
        
    except Exception as e:
        # If anything goes wrong (timeout, connection error, etc.), mark as invalid
        return False, None


# ============================================================================
# STEP 5: MAIN SEARCH ORCHESTRATION
# ============================================================================
def find_website_for(company_name):
    """
    Find the official website for a given company name.
    
    Args:
        company_name (str): The company to search for
    
    Returns:
        dict: Result containing:
              - 'company': The input company name
              - 'url': The found website URL (or None if not found)
              - 'score': Confidence score (if found)
              - 'meta': Page metadata (if found)
              - 'candidates': Top 5 candidates (if no match found)
    
    How it works:
        1. **Search**: Query Google for the company + "official website"
        2. **Score**: Calculate confidence scores for each result
        3. **Sort**: Rank candidates by score (highest first)
        4. **Validate**: Check top 3 candidates by visiting the actual page
        5. **Return**: First validated match, or list of candidates if none valid
    
    The multi-step validation helps ensure we return the actual official
    website rather than a directory listing or news article.
    """
    # Step 5a: Get search results from Google
    results = serp_search(company_name)
    
    # Step 5b: Score each candidate
    candidates = []
    for res in results:
        url = res.get("link") or res.get("displayed_link")
        title = res.get("title")
        snippet = res.get("snippet")
        score = score_candidate(company_name, url, title, snippet)
        candidates.append((score, url, title, snippet))
    
    # Step 5c: Sort by score (highest confidence first)
    candidates.sort(reverse=True)
    
    # Step 5d: Validate top 3 candidates
    for score, url, title, snippet in candidates[:3]:
        ok, meta = validate_homepage(url, company_name)
        if ok:
            # Found a validated match!
            return {"company": company_name, "url": url, "score": score, "meta": meta}
    
    # Step 5e: No validated match found, return candidates for manual review
    return {"company": company_name, "url": None, "candidates": candidates[:5]}


# ============================================================================
# STEP 6: BATCH PROCESSING
# ============================================================================
def main():
    """
    Process a batch of companies from a CSV file.
    
    Input file: company_names.csv
        Must contain a column named 'company_name' with one company per row
    
    Output file: company_results.json
        JSON array with results for each company
    
    How it works:
        1. Reads the CSV file using pandas
        2. Iterates through each company name
        3. Calls find_website_for() for each company
        4. Saves all results to a JSON file
    """
    # Load company names from CSV
    df = pd.read_csv("company_names.csv")
    
    results = []
    for index, row in df.iterrows():
        company_name = row["company_name"]
        print(f"Processing: {company_name}...")  # Progress indicator
        result = find_website_for(company_name)
        results.append(result)
    
    # Save results to JSON
    with open("company_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"Done! Results saved to company_results.json")


if __name__ == "__main__":
    main()
