"""
modules/processor.py — LLM-driven analysis of scraped files and final filtering pass.
"""

import glob
import os

from config import ANALYSIS_RESULTS_DIR, ERROR_LOG_FILENAME
from modules.llm_agent import build_extraction_chain, build_filter_chain


# ---------------------------------------------------------
# STEP 2 — ANALYZE SCRAPED FILES
# ---------------------------------------------------------

def analyze_scraped_files(
    filepaths: list,
    provider: str = "ollama",
    model_name: str = "llama3.2",
    temperature: float = 0.1,
) -> list[str]:
    """
    Run the extraction LLM over each scraped markdown file.
    Results are appended to per-domain analysis files in analysis_results/.
    Returns the list of result file paths that were written.
    """
    base_dir = _project_root()
    results_dir = os.path.join(base_dir, ANALYSIS_RESULTS_DIR)
    error_log_path = os.path.join(base_dir, ERROR_LOG_FILENAME)
    os.makedirs(results_dir, exist_ok=True)

    if not filepaths:
        print("No files to analyze.")
        return []

    chain = build_extraction_chain(provider, model_name, temperature)
    modified_files: set[str] = set()

    print(f"\n{'='*60}\nAnalyzing {len(filepaths)} files...\n{'='*60}")

    for filepath in filepaths:
        filename = os.path.basename(filepath)
        base_name = filename.replace(".md", "")

        parts = base_name.rsplit("_", 1)
        safe_domain = parts[0] if (len(parts) == 2 and len(parts[1]) == 8) else base_name

        result_filepath = os.path.join(results_dir, f"{safe_domain}_analysis.md")

        if _already_analyzed(result_filepath, filename):
            print(f"Skipping {filename}: already in {os.path.basename(result_filepath)}")
            modified_files.add(result_filepath)
            continue

        print(f"\nAnalyzing {filename}...")
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                file_content = f.read()

            result = chain.invoke({"source": filename, "document_text": file_content})
            print(f"Result:\n{result}\n{'-'*60}")

            if _is_valid_extraction(result):
                with open(result_filepath, "a", encoding="utf-8") as f:
                    f.write(f"\n\n--- SOURCE: {filename} ---\n\n")
                    f.write(result)
                    f.write("\n")
                print(f"Appended to: {result_filepath}")
                modified_files.add(result_filepath)
            else:
                print(f"Skipping append for {filename}: no concrete rebate found.")

        except Exception as e:
            _log_error(error_log_path, f"Error processing {filename}: {e}")

    return list(modified_files)


# ---------------------------------------------------------
# STEP 3 — FILTER ANALYSIS RESULTS
# ---------------------------------------------------------

def filter_analysis_results(
    result_filepaths: list,
    provider: str = "ollama",
    model_name: str = "llama3.2",
    temperature: float = 0.1,
) -> None:
    """
    Run a final LLM pass over each domain analysis file to produce
    a clean *_FINAL_rebates.md with only confirmed rebate programs.
    """
    if not result_filepaths:
        return

    chain = build_filter_chain(provider, model_name, temperature)
    print(f"\n{'='*60}\nFiltering {len(result_filepaths)} domain files...\n{'='*60}")

    for filepath in result_filepaths:
        if not os.path.exists(filepath):
            continue

        base_name = os.path.basename(filepath).replace("_analysis.md", "")
        final_filepath = os.path.join(os.path.dirname(filepath), f"{base_name}_FINAL_rebates.md")

        print(f"\nFiltering {os.path.basename(filepath)}...")
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                raw_report = f.read()

            filtered = chain.invoke({"raw_report": raw_report})
            print(f"Filtered:\n{filtered}\n{'-'*60}")

            with open(final_filepath, "w", encoding="utf-8") as f:
                f.write(f"# FINAL REBATE EXTRACTION FOR: {base_name}\n\n")
                f.write(filtered)
                f.write("\n")
            print(f"Saved: {final_filepath}")

        except Exception as e:
            print(f"Error filtering {filepath}: {e}")


# ---------------------------------------------------------
# PROCESS RAW TEXT — used by app.py Upload Markdown mode
# ---------------------------------------------------------

def process_text(
    text: str,
    source_name: str = "uploaded_text",
    temperature: float = 0.1,
    provider: str = "ollama",
    model_name: str = "llama3.2",
) -> dict:
    """
    Run extraction directly on a raw text string (no file I/O).
    Returns a structured dict with extracted fields.
    Used by app.py's 'Upload Markdown' mode.
    """
    chain = build_extraction_chain(provider, model_name, temperature)
    result = chain.invoke({"source": source_name, "document_text": text})

    return {
        "markdown_summary": result,
        "program_name":     _extract_field(result, "# Program Name:"),
        "program_url":      _extract_field(result, "#Program URL:"),
        "utility_name":     _extract_field(result, "Utility Company Name:"),
        "utility_size":     _extract_field(result, "Utility Company Size:"),
        "rebate_amounts":   _extract_bullets_under(result, "Concrete Rebate Amounts"),
        "eligibility":      _extract_bullets_under(result, "Eligibility Requirements"),
    }


# ---------------------------------------------------------
# CONVENIENCE — find existing files for --analyze-only / --filter-only
# ---------------------------------------------------------

def get_scraped_files(scraped_dir: str) -> list[str]:
    return glob.glob(os.path.join(scraped_dir, "*.md"))


def get_analysis_files(results_dir: str) -> list[str]:
    return [
        f for f in glob.glob(os.path.join(results_dir, "*_analysis.md"))
        if not f.endswith("_FINAL_rebates.md")
    ]


# ---------------------------------------------------------
# PRIVATE HELPERS
# ---------------------------------------------------------

def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _already_analyzed(result_filepath: str, source_filename: str) -> bool:
    if not os.path.exists(result_filepath):
        return False
    try:
        with open(result_filepath, "r", encoding="utf-8") as f:
            return f"--- SOURCE: {source_filename} ---" in f.read()
    except Exception:
        return False


def _is_valid_extraction(result: str) -> bool:
    upper = result.upper()
    is_irrelevant = (
        "NOT RELEVANT" in upper
        or "PROGRAM NAME: NONE" in upper
        or "PROGRAM NAME: NOT RELEVANT" in upper
    )
    has_structure = "## PROGRAM DETAILS" in upper or "## ELIGIBILITY" in upper
    return not is_irrelevant and has_structure


def _extract_field(text: str, label: str) -> str:
    for line in text.splitlines():
        if label.lower() in line.lower():
            parts = line.split(":", 1)
            if len(parts) > 1:
                return parts[1].strip().lstrip("*").strip()
    return ""


def _extract_bullets_under(text: str, section_label: str) -> str:
    lines = text.splitlines()
    collecting = False
    bullets = []
    for line in lines:
        if section_label.lower() in line.lower():
            collecting = True
            continue
        if collecting:
            stripped = line.strip()
            if stripped.startswith("-") or stripped.startswith("*"):
                bullets.append(stripped.lstrip("-*").strip())
            elif stripped.startswith("#") or stripped.startswith("##"):
                break
    return " | ".join(bullets)


def _log_error(log_path: str, msg: str) -> None:
    print(msg)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
