import argparse
import pandas as pd

from app import _find_default_url_column, _normalize_url
from test_single_link import (
    scrape_single_link,
    analyze_scraped_files,
    filter_analysis_results,
)

import asyncio


def main():
    parser = argparse.ArgumentParser(description="Run rebate pipeline over URLs in an Excel file.")
    parser.add_argument("--excel", required=True, help="Path to Excel file")
    parser.add_argument("--sheet", default=0, help="Sheet name or sheet index")
    parser.add_argument("--url-column", default=None, help="Column containing URLs. If omitted, auto-detect.")
    parser.add_argument("--provider", default="uw_ssec")
    parser.add_argument("--model", default="gpt-5.4-mini")
    parser.add_argument("--deep-crawl", action="store_true")
    parser.add_argument("--truncation-length", type=int, default=150000)
    args = parser.parse_args()

    try:
        sheet = int(args.sheet)
    except ValueError:
        sheet = args.sheet

    df = pd.read_excel(args.excel, sheet_name=sheet)

    url_column = args.url_column or _find_default_url_column(df.columns)
    if url_column not in df.columns:
        raise ValueError(f"URL column '{url_column}' not found. Available columns: {list(df.columns)}")

    urls = [_normalize_url(value) for value in df[url_column]]
    urls = [url for url in urls if url]
    urls = list(dict.fromkeys(urls))

    print(f"Found {len(urls)} valid unique URL(s). Using column: {url_column}")

    for i, url in enumerate(urls, start=1):
        print(f"\n{'=' * 80}")
        print(f"Running {i}/{len(urls)}: {url}")
        print(f"{'=' * 80}")

        scraped_files = asyncio.run(
            scrape_single_link(
                url,
                use_deep_crawl=args.deep_crawl,
                truncation_length=args.truncation_length,
            )
        )

        analysis_files = analyze_scraped_files(
            scraped_files,
            provider=args.provider,
            model_name=args.model,
        )

        filter_analysis_results(
            analysis_files,
            provider=args.provider,
            model_name=args.model,
        )


if __name__ == "__main__":
    main()
