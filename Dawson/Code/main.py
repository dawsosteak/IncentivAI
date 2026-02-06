import pandas as pd

from scraper import fetch_page, extract_text_blocks
from Code.transformer import ElmoRAG
from extractor import extract_fields


def run(url: str, output_path: str):
    soup = fetch_page(url)
    blocks = extract_text_blocks(soup)

    rag = ElmoRAG()
    rows = []

    for block in blocks:
        if rag.is_relevant(block):
            fields = extract_fields(block)
            rows.append(fields)

    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    return df


if __name__ == "__main__":
    TARGET_URL = "https://www.energy.gov/eere/solar/federal-solar-tax-credit"
    OUTPUT_FILE = "data/output.csv"

    df = run(TARGET_URL, OUTPUT_FILE)
    print(df.head())
