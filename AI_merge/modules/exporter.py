import csv
import os
import tempfile
from datetime import datetime

import pandas as pd

OUTPUT_COLUMNS = [
    "link_type",
    "parent_url",
    "source_url",
    "url_type",
    "utility_company",
    "program_name",
    "program_type",
    "financial_details",
    "eligibility",
    "application_process",
    "sector",
    "notes",
    "summary_of_page",
    "extraction_timestamp",
]


def _build_rows(results: list) -> list:
    rows = []
    for entry in results:
        utility = entry.get("utility_company")
        source_url = entry.get("source_url")
        parent_url = entry.get("parent_url")
        is_sublink = entry.get("is_sublink", False)
        url_type = entry.get("url_type", "web")
        timestamp = entry.get("extraction_timestamp")
        summary = entry.get("summary_of_page")
        programs = entry.get("programs", [])

        link_type = "Sublink" if is_sublink else "Main Link"

        base = {
            "link_type": link_type,
            "parent_url": parent_url or "",
            "source_url": source_url,
            "url_type": url_type,
            "utility_company": utility,
            "summary_of_page": summary,
            "extraction_timestamp": timestamp,
        }

        if not programs:
            rows.append(
                {
                    **base,
                    "program_name": None,
                    "program_type": None,
                    "financial_details": None,
                    "eligibility": None,
                    "application_process": None,
                    "sector": None,
                    "notes": None,
                }
            )
        else:
            for p in programs:
                rows.append(
                    {
                        **base,
                        "program_name": p.get("program_name"),
                        "program_type": p.get("program_type"),
                        "financial_details": p.get("financial_details"),
                        "eligibility": p.get("eligibility"),
                        "application_process": p.get("application_process"),
                        "sector": p.get("sector"),
                        "notes": p.get("notes"),
                    }
                )
    return rows


def export_to_csv(results: list) -> str:
    rows = _build_rows(results)
    rows.sort(
        key=lambda r: (
            r["parent_url"] or r["source_url"],
            0 if r["link_type"] == "Main Link" else 1,
        )
    )
    df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    df.to_csv(tmp.name, index=False)
    return tmp.name


def append_markdown_entry(entry: dict, markdown_csv: str):
    programs = entry.get("programs", [])
    utility = entry.get("utility_company") or "Unknown Utility"
    source_url = entry.get("source_url", "")
    summary = entry.get("summary_of_page") or ""
    timestamp = entry.get("extraction_timestamp", "")
    link_type = "Sublink" if entry.get("is_sublink") else "Main Link"

    lines = [
        f"## {utility}",
        f"**Source:** {source_url}",
        f"**Type:** {link_type}",
        f"**Summary:** {summary}",
        "",
    ]

    if not programs:
        lines.append("_No programs found on this page._")
    else:
        for p in programs:
            name = p.get("program_name") or "Unnamed Program"
            lines.append(f"### {name}")
            if p.get("program_type"):
                lines.append(f"- **Type:** {p['program_type']}")
            if p.get("financial_details"):
                lines.append(f"- **Financial Details:** {p['financial_details']}")
            if p.get("eligibility"):
                lines.append(f"- **Eligibility:** {p['eligibility']}")
            if p.get("application_process"):
                lines.append(f"- **How to Apply:** {p['application_process']}")
            if p.get("sector"):
                lines.append(f"- **Sector:** {p['sector']}")
            if p.get("notes"):
                lines.append(f"- **Notes:** {p['notes']}")
            lines.append("")

    markdown_block = "\n".join(lines)

    file_exists = os.path.isfile(markdown_csv)
    with open(markdown_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["timestamp", "url", "link_type", "markdown_summary"]
        )
        if not file_exists:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": timestamp,
                "url": source_url,
                "link_type": link_type,
                "markdown_summary": markdown_block,
            }
        )
