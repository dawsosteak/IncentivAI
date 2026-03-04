
"""
Search Google for clean energy topics in the United States using a local OpenSERP instance.
No API keys required – just a running Docker container with OpenSERP.
"""

import requests
import time
from typing import List, Dict, Any

# Configuration
OPENSERP_URL = "http://localhost:7000"  # default OpenSERP address
SEARCH_ENGINE = "google"                 # can also be "bing", "duckduckgo", or "mega"
NUM_RESULTS = 5                           # results per topic
COUNTRY = "us"                             # geographic bias (gl parameter)
LANGUAGE = "EN"                             # language (hl parameter)

# Topics to search (clean energy angles)
TOPICS = [
    "solar energy",
    "wind power",
    "energy storage",
    "clean energy policy",
    "renewable energy companies"
]

def search_google(query: str, limit: int = NUM_RESULTS) -> List[Dict[str, Any]]:
    """
    Perform a Google search via OpenSERP.

    Args:
        query: Search query string.
        limit: Maximum number of results to return.

    Returns:
        List of result dictionaries with keys: title, url, description.
    """
    url = f"{OPENSERP_URL}/{SEARCH_ENGINE}/search"
    params = {
        "text": query,
        "limit": limit,
        "gl": COUNTRY,
        "lang": LANGUAGE
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        # OpenSERP returns a list of results directly
        return data
    except Exception as e:
        print(f"❌ Error searching for '{query}': {e}")
        return []

def main():
    print("🔍 Starting clean energy search (U.S. focused)\n")
    print(f"Target OpenSERP instance: {OPENSERP_URL}")
    print(f"Engine: {SEARCH_ENGINE}, Country: {COUNTRY}, Language: {LANGUAGE}\n")

    if not TOPICS:
        print("No topics defined. Exiting.")
        return

    for topic in TOPICS:
        # Build a query that implies U.S. context
        query = f"clean energy {topic} United States"
        print(f"\n📌 Searching: {query}")
        results = search_google(query, limit=NUM_RESULTS)

        if not results:
            print("   No results found.")
        else:
            for idx, item in enumerate(results, 1):
                title = item.get("title", "N/A")
                url = item.get("url", "N/A")
                desc = item.get("description", "")
                # Truncate description for cleaner display
                if len(desc) > 120:
                    desc = desc[:117] + "..."
                print(f"   {idx}. {title}")
                print(f"       URL: {url}")
                print(f"       Desc: {desc}")

        # Be polite – small delay between topics
        time.sleep(1)

    print("\n✅ Done.")

if __name__ == "__main__":
    main()
