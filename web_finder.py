# sample: pip install requests rapidfuzz tldextract beautifulsoup4
import requests
from rapidfuzz import fuzz
from bs4 import BeautifulSoup
import tldextract
import pandas as pd
import json 

SERP_API_KEY = "9e0b9bcb598c0d6c5a659d921b3452c1165d5b3f6156946db0e7bd378fd972a8"

def serp_search(company_name, num=5):
    params = {"engine": "google", "q": f"{company_name} official website", "api_key": SERP_API_KEY, "num": num}
    r = requests.get("https://serpapi.com/search.json", params=params)
    r.raise_for_status()
    return r.json().get("organic_results", [])

def extract_domain(url):
    ext = tldextract.extract(url)
    return f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain

def score_candidate(company_name, url, title, snippet):
    # Simple multi-signal scoring
    domain = extract_domain(url)
    s_name_title = fuzz.partial_ratio(company_name.lower(), (title or "").lower())
    s_name_snip = fuzz.partial_ratio(company_name.lower(), (snippet or "").lower())
    s_domain = fuzz.partial_ratio(company_name.lower(), domain.lower())
    return max(s_name_title, s_name_snip, s_domain)

def validate_homepage(url, company_name):
    try:
        r = requests.get(url, timeout=8, headers={"User-Agent":"Mozilla/5.0"})
        if r.status_code != 200:
            return False, None
        soup = BeautifulSoup(r.text, "html.parser")
        # Basic checks: title or H1 contains company name
        title = (soup.title.string or "") if soup.title else ""
        h1 = (soup.find("h1").get_text(separator=" ") if soup.find("h1") else "")
        text = " ".join([title, h1]).lower()
        return company_name.lower().split()[0] in text, {"title": title, "h1": h1}
    except Exception as e:
        return False, None

def find_website_for(company_name):
    results = serp_search(company_name)
    candidates = []
    for res in results:
        url = res.get("link") or res.get("displayed_link")
        title = res.get("title")
        snippet = res.get("snippet")
        score = score_candidate(company_name, url, title, snippet)
        candidates.append((score, url, title, snippet))
    candidates.sort(reverse=True)
    for score, url, title, snippet in candidates[:3]:
        ok, meta = validate_homepage(url, company_name)
        if ok:
            return {"company": company_name, "url": url, "score": score, "meta": meta}
    return {"company": company_name, "url": None, "candidates": candidates[:5]}

def main():
    df = pd.read_csv("company_names.csv")
    results = []
    for index, row in df.iterrows():
        company_name = row["company_name"]
        result = find_website_for(company_name)
        results.append(result)
    with open("company_results.json", "w") as f:
        json.dump(results, f)

if __name__ == "__main__":
    main()