"""
Search Google for clean energy topics in a specific U.S. state using a local OpenSERP instance.
No API keys required — just a running Docker container with OpenSERP.
"""

import requests
import time
from typing import List, Dict, Any

# Configuration
OPENSERP_URL = "http://localhost:7000"  # default OpenSERP address
SEARCH_ENGINE = "google"                # can also be "bing", "duckduckgo", or "mega"
NUM_RESULTS = 5                         # results per topic
COUNTRY = "us"                          # geographic bias (gl parameter)
LANGUAGE = "EN"                         # language (hl parameter)

# Clean energy angles to search per state
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
        return resp.json()
    except Exception as e:
        print(f"❌ Error searching for '{query}': {e}")
        return []


def get_state_input() -> str:
    """
    Prompt the user to enter a U.S. state name and validate it.

    Returns:
        A validated, title-cased U.S. state name.
    """
    valid_states = {
        "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
        "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
        "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
        "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
        "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
        "New Hampshire", "New Jersey", "New Mexico", "New York",
        "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
        "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
        "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
        "West Virginia", "Wisconsin", "Wyoming"
    }

    while True:
        state = input("🗺️  Enter a U.S. state to search clean energy info for: ").strip().title()
        if state in valid_states:
            return state
        print(f"   ⚠️  '{state}' is not a recognized U.S. state. Please try again.")


def main():
    print("🔍 Clean Energy Search by U.S. State\n")
    print(f"Target OpenSERP instance: {OPENSERP_URL}")
    print(f"Engine: {SEARCH_ENGINE}, Country: {COUNTRY}, Language: {LANGUAGE}\n")

    # Get the target state from the user
    state = get_state_input()

    print(f"\n🌱 Searching clean energy topics for: {state}\n")

    for topic in TOPICS:
        # Build a state-specific query
        query = f"clean energy {topic} {state}"
        print(f"\n📌 Searching: {query}")
        results = search_google(query, limit=NUM_RESULTS)

        if not results:
            print("   No results found.")
        else:
            for idx, item in enumerate(results, 1):
                title = item.get("title", "N/A")
                url   = item.get("url", "N/A")
                desc  = item.get("description", "")
                if len(desc) > 120:
                    desc = desc[:117] + "..."
                print(f"   {idx}. {title}")
                print(f"       URL: {url}")
                print(f"       Desc: {desc}")

        time.sleep(1)  # polite delay between requests

    print("\n✅ Done.")


if __name__ == "__main__":
    main()