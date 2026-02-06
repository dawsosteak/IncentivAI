import requests
from bs4 import BeautifulSoup


def fetch_page(url: str) -> BeautifulSoup:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def extract_text_blocks(soup: BeautifulSoup) -> list[str]:
    """
    Extracts reasonably sized text blocks for semantic filtering.
    """
    blocks = []

    for tag in soup.find_all(["p", "li", "div"]):
        text = tag.get_text(strip=True)
        if len(text) > 50:
            blocks.append(text)

    return blocks
