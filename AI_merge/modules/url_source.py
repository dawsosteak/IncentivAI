import pandas as pd
import requests
from bs4 import BeautifulSoup


def _resolve_url_column(df):
    by_exact = {str(c).strip(): c for c in df.columns}
    for preferred in ("URLs", "URLS", "url", "URL", "Url"):
        if preferred in by_exact:
            return by_exact[preferred]
    lower = {str(c).strip().lower(): c for c in df.columns}
    for key in ("urls", "url"):
        if key in lower:
            return lower[key]
    raise ValueError(
        "Excel must contain a URL column named one of: URLs, URLS, or url "
        "(case-insensitive)."
    )


def get_urls(mode, uploaded_file=None, state=None):
    if mode == "Upload Excel":
        df = pd.read_excel(uploaded_file)
        col = _resolve_url_column(df)
        urls = df[col].dropna().astype(str).tolist()
        return list(dict.fromkeys(urls))
    query = f"electric utility companies in {state}"
    search_url = f"https://duckduckgo.com/html/?q={query}"
    response = requests.get(search_url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    links = [
        a["href"] for a in soup.find_all("a", href=True)
        if a["href"].startswith("http")
    ]
    return list(dict.fromkeys(links[:10]))
