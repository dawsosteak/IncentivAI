import pandas as pd
import tempfile

def export_to_csv(results):
    rows = []

    for entry in results:
        utility = entry.get("utility_company")
        source_url = entry.get("source_url")
        timestamp = entry.get("extraction_timestamp")
        programs = entry.get("programs", [])

        if not programs:
            rows.append({
                "utility_company": utility,
                "program_name": None,
                "program_type": None,
                "financial_details": None,
                "eligibility": None,
                "application_process": None,
                "sector": None,
                "notes": None,
                "source_url": source_url,
                "extraction_timestamp": timestamp
            })
        else:
            for p in programs:
                rows.append({
                    "utility_company": utility,
                    "program_name": p.get("program_name"),
                    "program_type": p.get("program_type"),
                    "financial_details": p.get("financial_details"),
                    "eligibility": p.get("eligibility"),
                    "application_process": p.get("application_process"),
                    "sector": p.get("sector"),
                    "notes": p.get("notes"),
                    "source_url": source_url,
                    "extraction_timestamp": timestamp
                })

    df = pd.DataFrame(rows)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    df.to_csv(tmp.name, index=False)
    return tmp.name