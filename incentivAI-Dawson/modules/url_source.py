import pandas as pd
import requests
from bs4 import BeautifulSoup


def get_urls(mode: str, uploaded_file=None, state: str = None) -> list:
    """
    Returns a list of dicts: [{"url": str, "parent": str | None}]

    uploaded_file can be:
      - A Streamlit UploadedFile object (app.py)
      - A plain file path string (cli.py)

    parent is None for main links.
    parent is set to the parent URL string for sublinks
    (read from optional 'parent_url' column in Excel).
    """
    if mode == "Upload Excel":
        # Handle both Streamlit UploadedFile and plain file path string
        df = pd.read_excel(uploaded_file)

        # Normalize column names — strip whitespace and lowercase
        df.columns = [c.strip().lower() for c in df.columns]

        if "urls" not in df.columns:
            raise ValueError("Excel file must contain a column named 'URLs'")

        result = []
        for _, row in df.iterrows():
            url = str(row["urls"]).strip()
            if not url or url.lower() == "nan":
                continue

            parent = None
            if "parent_url" in df.columns:
                raw_parent = str(row["parent_url"]).strip()
                if raw_parent and raw_parent.lower() != "nan":
                    parent = raw_parent

            result.append({"url": url, "parent": parent})

        # Deduplicate by URL while preserving parent relationship
        seen = set()
        deduped = []
        for entry in result:
            if entry["url"] not in seen:
                seen.add(entry["url"])
                deduped.append(entry)

        return deduped

    else:
        # Auto search mode — DuckDuckGo search by state
        query = f"electric utility companies in {state}"
        search_url = f"https://duckduckgo.com/html/?q={query}"
        try:
            response = requests.get(search_url, timeout=15)
            soup = BeautifulSoup(response.text, "html.parser")
            links = [
                a["href"] for a in soup.find_all("a", href=True)
                if a["href"].startswith("http")
            ]
        except Exception as e:
            raise RuntimeError(f"Auto search failed for state '{state}': {e}")

        seen = set()
        result = []
        for link in links[:10]:
            if link not in seen:
                seen.add(link)
                result.append({"url": link, "parent": None})
        return result
