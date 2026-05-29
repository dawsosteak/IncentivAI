"""
modules/exporter.py — Handles all output: writing results to CSV and appending markdown summaries.
"""

import csv
import os
import tempfile

from config import MARKDOWN_CSV


def export_to_csv(result_files: list) -> str:
    """
    Accept either:
      - list of *_FINAL_rebates.md file paths  (from run_pipeline)
      - list of structured dicts               (from process_text / Upload Markdown mode)
      - a mix of both

    Returns the path to the output CSV.
    """
    rows = []

    for item in result_files:
        if isinstance(item, dict):
            # Direct structured dict from process_text()
            rows.append({
                "program_name":  item.get("program_name",  ""),
                "program_url":   item.get("program_url",   ""),
                "rebate_amounts": item.get("rebate_amounts", ""),
                "eligibility":   item.get("eligibility",   ""),
                "utility_name":  item.get("utility_name",  ""),
                "utility_size":  item.get("utility_size",  ""),
                "source_file":   item.get("source_url",    ""),
            })
        else:
            # File path — derive the _FINAL_rebates.md counterpart
            if item.endswith("_analysis.md"):
                final_path = item.replace("_analysis.md", "_FINAL_rebates.md")
            elif item.endswith("_FINAL_rebates.md"):
                final_path = item
            else:
                final_path = item

            if not os.path.isfile(final_path):
                continue

            try:
                with open(final_path, "r", encoding="utf-8") as f:
                    content = f.read()

                if "NO REBATES FOUND" in content.upper():
                    continue

                rows.extend(_parse_markdown_to_rows(content, final_path))

            except Exception as e:
                print(f"[exporter] Error reading {final_path}: {e}")

    # Write to a named temp file so caller can move/read it
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False,
        encoding="utf-8", newline=""
    )
    fieldnames = [
        "program_name", "program_url", "rebate_amounts",
        "eligibility", "utility_name", "utility_size", "source_file"
    ]
    writer = csv.DictWriter(tmp, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(rows)
    tmp.close()

    print(f"[exporter] Wrote {len(rows)} rows to {tmp.name}")
    return tmp.name


def append_markdown_entry(structured: dict, markdown_csv_path: str = MARKDOWN_CSV) -> None:
    """
    Append a single structured extraction result as a markdown summary row to the CSV.
    """
    summary = structured.get("markdown_summary") or _build_markdown_summary(structured)

    file_exists = os.path.isfile(markdown_csv_path)
    try:
        with open(markdown_csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=["source_url", "markdown_summary"],
                quoting=csv.QUOTE_ALL
            )
            if not file_exists:
                writer.writeheader()
            writer.writerow({
                "source_url":       structured.get("source_url", ""),
                "markdown_summary": summary,
            })
    except Exception as e:
        print(f"[exporter] Failed to append markdown entry: {e}")


# ---------------------------------------------------------
# PRIVATE HELPERS
# ---------------------------------------------------------

def _parse_markdown_to_rows(content: str, source_file: str) -> list:
    """
    Lightweight markdown parser — splits on '# Program Name:' blocks
    and extracts fields into dicts.
    """
    rows   = []
    blocks = content.split("# Program Name:")
    for block in blocks[1:]:
        lines        = block.strip().splitlines()
        program_name = lines[0].strip() if lines else ""

        rows.append({
            "program_name":  program_name,
            "program_url":   _extract_field(block, "#Program URL:"),
            "rebate_amounts": _extract_bullets_under(block, "Concrete Rebate Amounts"),
            "eligibility":   _extract_bullets_under(block, "Eligibility Requirements"),
            "utility_name":  _extract_field(block, "Utility Company Name:"),
            "utility_size":  _extract_field(block, "Utility Company Size:"),
            "source_file":   os.path.basename(source_file),
        })
    return rows


def _extract_field(text: str, label: str) -> str:
    for line in text.splitlines():
        if label.lower() in line.lower():
            parts = line.split(":", 1)
            if len(parts) > 1:
                return parts[1].strip().lstrip("*").strip()
    return ""


def _extract_bullets_under(text: str, section_label: str) -> str:
    lines      = text.splitlines()
    collecting = False
    bullets    = []
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


def _build_markdown_summary(structured: dict) -> str:
    return (
        f"# Program Name: {structured.get('program_name', 'N/A')}\n\n"
        f"**URL:** {structured.get('program_url', 'N/A')}\n\n"
        f"**Utility:** {structured.get('utility_name', 'N/A')}\n\n"
        f"**Rebate Amounts:** {structured.get('rebate_amounts', 'N/A')}\n\n"
        f"**Eligibility:** {structured.get('eligibility', 'N/A')}\n"
    )
