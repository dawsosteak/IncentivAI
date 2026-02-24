import pandas as pd
import requests
from bs4 import BeautifulSoup

def get_urls(mode, uploaded_file=None, state=None):
    if mode == "Upload Excel":
        df = pd.read_excel(uploaded_file)
        if "URLs" not in df.columns:
            raise ValueError("Excel must contain column named 'URLs'")
        urls = df["URLs"].dropna().astype(str).tolist()
        return list(set(urls))

    else:
        query = f"electric utility companies in {state}"
        search_url = f"https://duckduckgo.com/html/?q={query}"
        response = requests.get(search_url)
        soup = BeautifulSoup(response.text, "html.parser")
        links = [
            a["href"] for a in soup.find_all("a", href=True)
            if a["href"].startswith("http")
        ]
        return list(set(links[:10]))