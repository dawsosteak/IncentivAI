"""
cli.py — Terminal / supercomputer entry point for IncentivAI.

Usage examples:
  # Local Ollama
  python cli.py --file urls.xlsx --provider ollama --model qwen2.5:7b

  # OpenAI
  python cli.py --file urls.xlsx --provider openai --model gpt-4o

  # Auto search by state
  python cli.py --state California --provider openai --model gpt-4o

  # SLURM / supercomputer (called from sbatch script)
  python cli.py --file urls.xlsx --provider uw_ssec --model gpt-5.4-pro --output /results/
"""

import argparse
import os
import sys
import shutil
from main import run_pipeline
from config import (
    DEFAULT_TEMPERATURE,
    DEFAULT_TRUNCATION,
    MODEL_NAME,
)


def progress_callback(current, total, url="", message=""):
    """Print-based progress for terminal use."""
    pct = int((current / total) * 100)
    bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
    print(f"\r[{bar}] {pct}% ({current}/{total}) {message[:80]}", end="", flush=True)
    if current == total:
        print()  # newline on completion


def main():
    parser = argparse.ArgumentParser(
        description="IncentivAI — Utility Incentive Extractor (CLI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Providers:
  ollama     Local Ollama instance (default)
  openai     OpenAI API (requires OPENAI_API_KEY)
  anthropic  Anthropic API (requires ANTHROPIC_API_KEY)
  google     Google Gemini API (requires GOOGLE_API_KEY)
        """
    )

    # Input source — one of --file or --state required
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--file",
        type=str,
        help="Path to Excel file (.xlsx) with a 'URLs' column and optional 'parent_url' column"
    )
    input_group.add_argument(
        "--state",
        type=str,
        help="State name for auto utility search (e.g. 'California')"
    )

    # LLM settings
    parser.add_argument(
        "--provider",
        type=str,
        default="ollama",
        choices=["ollama", "openai", "uw_ssec", "anthropic", "google", "gemini"],
        help=f"LLM provider to use (default: ollama)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=MODEL_NAME,
        help=f"Model name to use (default: {MODEL_NAME})"
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help=f"LLM temperature (default: {DEFAULT_TEMPERATURE})"
    )

    # Scraping settings
    parser.add_argument(
        "--truncation",
        type=int,
        default=DEFAULT_TRUNCATION,
        help=f"Max characters of scraped content to send to LLM (default: {DEFAULT_TRUNCATION})"
    )

    # Output
    parser.add_argument(
        "--output",
        type=str,
        default=".",
        help="Directory to save output CSV (default: current directory)"
    )
    parser.add_argument(
        "--output-name",
        type=str,
        default="incentives_output.csv",
        help="Output CSV filename (default: incentives_output.csv)"
    )

    args = parser.parse_args()

    # ── Validate input file exists ────────────────────────────────────────
    if args.file and not os.path.isfile(args.file):
        print(f"Error: File not found: {args.file}")
        sys.exit(1)

    # ── Validate output directory ─────────────────────────────────────────
    os.makedirs(args.output, exist_ok=True)
    output_path = os.path.join(args.output, args.output_name)

    # ── Print run config ──────────────────────────────────────────────────
    print("=" * 60)
    print("IncentivAI — CLI Mode")
    print("=" * 60)
    print(f"  Input:       {args.file or f'Auto search: {args.state}'}")
    print(f"  Provider:    {args.provider}")
    print(f"  Model:       {args.model}")
    print(f"  Temperature: {args.temperature}")
    print(f"  Truncation:  {args.truncation}")
    print(f"  Output:      {output_path}")
    print("=" * 60)
    print()

    # ── Run pipeline ──────────────────────────────────────────────────────
    mode = "Upload Excel" if args.file else "Auto Search Utilities"

    # For CLI, uploaded_file is a file path string
    # url_source.get_urls handles both Streamlit UploadedFile and plain path strings
    uploaded_file = args.file if args.file else None

    try:
        tmp_csv = run_pipeline(
            mode=mode,
            uploaded_file=uploaded_file,
            state=args.state,
            temperature=args.temperature,
            truncation_length=args.truncation,
            progress_callback=progress_callback,
            cancel_flag=None,
            provider=args.provider,
            model=args.model,
        )

        # Move temp CSV to specified output location
        shutil.move(tmp_csv, output_path)

        print()
        print("=" * 60)
        print(f"✅ Extraction complete.")
        print(f"   Results saved to: {output_path}")
        if os.path.isfile("errors.csv"):
            print(f"   Errors logged to: errors.csv")
        if os.path.isfile("markdown_output.csv"):
            print(f"   Markdown summaries: markdown_output.csv")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n\nCancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\nPipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
