"""
main.py — Shared pipeline orchestrator + CLI entry point.

run_pipeline() is imported by both app.py (Streamlit) and cli.py (terminal/HPC).
"""

import argparse
import asyncio
import io
import os
import tempfile
import threading

import pandas as pd

from config import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    DEFAULT_TEMPERATURE,
    DEFAULT_TRUNCATION_LENGTH,
    SCRAPED_DATA_DIR,
    ANALYSIS_RESULTS_DIR,
    ERRORS_CSV,
    MARKDOWN_CSV,
)
from modules.scraper import scrape_single_link
from modules.processor import (
    analyze_scraped_files,
    filter_analysis_results,
    get_scraped_files,
    get_analysis_files,
)
from modules.exporter import export_to_csv


# ─────────────────────────────────────────────────────────────────────────────
# ASYNC HELPER — safe to call from Streamlit or any thread
# ─────────────────────────────────────────────────────────────────────────────

def _run_async(coro):
    """
    Run an async coroutine in a dedicated thread with a fresh event loop.
    Calling asyncio.run() directly inside Streamlit raises
    'This event loop is already running' on Windows — this avoids that.
    """
    result_holder = []
    error_holder  = []

    def _runner():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result_holder.append(loop.run_until_complete(coro))
        except Exception as e:
            error_holder.append(e)
        finally:
            loop.close()

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join()

    if error_holder:
        raise error_holder[0]
    return result_holder[0] if result_holder else None


# ─────────────────────────────────────────────────────────────────────────────
# SHARED PIPELINE — called by app.py AND cli.py
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline(
    mode: str,
    uploaded_file=None,          # file path (CLI) or BytesIO / UploadedFile (Streamlit)
    state: str = None,
    temperature: float = DEFAULT_TEMPERATURE,
    truncation_length: int = DEFAULT_TRUNCATION_LENGTH,
    progress_callback=None,
    cancel_flag=None,            # callable → bool, or None
    provider: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
) -> str:
    """
    Orchestrate the full scrape → analyze → filter → export pipeline.

    Returns the path to the output CSV file.
    """

    def _cancelled():
        return callable(cancel_flag) and cancel_flag()

    def _progress(current, total, url="", message=""):
        if progress_callback:
            progress_callback(current, total, url=url, message=message)

    # ── 1. Resolve URLs from input source ────────────────────────────────────
    urls = []

    if mode == "Upload Excel" and uploaded_file is not None:
        # Accept a file path string (CLI) or a file-like object (Streamlit)
        if isinstance(uploaded_file, (str, os.PathLike)):
            df = pd.read_excel(uploaded_file)
        else:
            uploaded_file.seek(0)
            df = pd.read_excel(io.BytesIO(uploaded_file.read()))

        # Find the URL column (flexible naming)
        url_col = next(
            (c for c in df.columns if str(c).strip().lower() in
             {"url", "urls", "link", "links", "website", "websites"}),
            None
        )
        if url_col is None:
            raise ValueError(
                f"No URL column found. Expected one of: url, urls, links, website. "
                f"Found: {list(df.columns)}"
            )

        parent_col = next(
            (c for c in df.columns if str(c).strip().lower() == "parent_url"),
            None
        )

        for _, row in df.iterrows():
            url = str(row[url_col]).strip()
            if url and url.lower() not in ("nan", "none", ""):
                entry = {"url": url, "parent_url": str(row[parent_col]).strip() if parent_col else None}
                urls.append(entry)

    elif mode == "Auto Search Utilities" and state:
        from modules.url_source import get_urls_from_discovery
        discovered = get_urls_from_discovery(
            states=[state],
            progress_callback=progress_callback,
        )
        urls = [{"url": r["url"], "parent_url": None} for r in discovered]

    else:
        raise ValueError(f"Invalid mode or missing input: mode={mode}, file={uploaded_file}, state={state}")

    if not urls:
        raise ValueError("No URLs found in the provided input.")

    total      = len(urls)
    all_results = []

    # ── 2. Scrape → Analyze → Filter each URL ────────────────────────────────
    for i, entry in enumerate(urls, 1):
        if _cancelled():
            _progress(i, total, message="Cancelled by user.")
            break

        url = entry["url"]
        _progress(i, total, url=url, message=f"Scraping {url}")

        try:
            # _run_async keeps this safe whether called from Streamlit or CLI
            scraped_files = _run_async(
                scrape_single_link(url, use_deep_crawl=True, truncation_length=truncation_length)
            )
        except Exception as e:
            _log_error(url, f"Scrape failed: {e}")
            continue

        if not scraped_files:
            _log_error(url, "No content scraped.")
            continue

        _progress(i, total, url=url, message=f"Analyzing {url}")

        try:
            result_files = analyze_scraped_files(
                scraped_files,
                provider=provider,
                model_name=model,
                temperature=temperature,
            )
            filter_analysis_results(
                result_files,
                provider=provider,
                model_name=model,
                temperature=temperature,
            )
            all_results.extend(result_files)
        except Exception as e:
            _log_error(url, f"Analysis failed: {e}")
            continue

    _progress(total, total, message="Exporting results...")

    # ── 3. Export to CSV ──────────────────────────────────────────────────────
    output_path = export_to_csv(all_results)
    return output_path


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _log_error(url: str, message: str):
    import csv
    print(f"[ERROR] {url}: {message}")
    try:
        file_exists = os.path.isfile(ERRORS_CSV)
        with open(ERRORS_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["url", "error"])
            writer.writerow([url, message])
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# CLI ENTRY POINT  (python main.py --url ... --analyze-only etc.)
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Utility rebate scraper and analyzer.")
    parser.add_argument("--url", type=str, default="http://cpuc.ca.gov/energyefficiency/")
    parser.add_argument("--no-deep-crawl", action="store_true")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument(
        "--provider", type=str, default=DEFAULT_PROVIDER,
        choices=["ollama", "openai", "anthropic", "google", "gemini"],
    )
    parser.add_argument("--analyze-only", action="store_true")
    parser.add_argument("--filter-only", action="store_true")
    return parser.parse_args()


def main():
    args     = parse_args()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    scraped_dir  = os.path.join(base_dir, SCRAPED_DATA_DIR)
    results_dir  = os.path.join(base_dir, ANALYSIS_RESULTS_DIR)
    llm_kwargs   = dict(provider=args.provider, model_name=args.model)

    if args.filter_only:
        result_files = get_analysis_files(results_dir)
        print(f"Filter-only: {len(result_files)} analysis files found.")
        filter_analysis_results(result_files, **llm_kwargs)

    elif args.analyze_only:
        scraped_files = get_scraped_files(scraped_dir)
        print(f"Analyze-only: {len(scraped_files)} scraped files found.")
        result_files  = analyze_scraped_files(scraped_files, **llm_kwargs)
        filter_analysis_results(result_files, **llm_kwargs)

    else:
        # _run_async used here too so `python main.py` works consistently
        generated_files = _run_async(scrape_single_link(args.url, not args.no_deep_crawl))
        result_files    = analyze_scraped_files(generated_files, **llm_kwargs)
        filter_analysis_results(result_files, **llm_kwargs)


if __name__ == "__main__":
    main()
