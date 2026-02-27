import pandas as pd
import requests
from bs4 import BeautifulSoup
#Function to get URLs either from an uploaded Excel file or by performing a web search based on the selected state
def get_urls(mode, uploaded_file=None, state=None):
    if mode == "Upload Excel":
        df = pd.read_excel(uploaded_file)
        if "URLs" not in df.columns:
            raise ValueError("Excel must contain column named 'URLs'")
        urls = df["URLs"].dropna().astype(str).tolist()
        return list(set(urls))
    #Need to add a web search option to get urls based on the state selected, this is a simple implementation using duckduckgo search, can be improved with more sophisticated scraping or APIs
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