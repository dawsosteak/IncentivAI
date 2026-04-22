"""
Clean energy search by U.S. state via local OpenSERP instance.
Results are printed to console and saved to an Excel file.

Usage:
    python energy_search.py                        # interactive
    python energy_search.py Texas                  # single state
    python energy_search.py "New York" California  # multiple states
"""

import sys
import time
import datetime
import requests
from typing import List, Dict, Any

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False
    print("⚠️  openpyxl not found. Install with: pip install openpyxl")

# ── Configuration ─────────────────────────────────────────────────────────────
OPENSERP_URL  = "http://localhost:7070"
SEARCH_ENGINE = "google"
NUM_RESULTS   = 5
COUNTRY       = "us"
LANGUAGE      = "EN"
OUTPUT_FILE   = "clean_energy_results.xlsx"

TOPICS = [
    "solar energy",
    "wind power",
    "energy storage",
    "clean energy policy",
    "renewable energy companies",
]

VALID_STATES = {
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming",
}

# ── Excel helpers ─────────────────────────────────────────────────────────────
HEADER_FILL = PatternFill("solid", start_color="1F4E79") if EXCEL_AVAILABLE else None
STATE_FILL  = PatternFill("solid", start_color="2E75B6") if EXCEL_AVAILABLE else None
TOPIC_FILL  = PatternFill("solid", start_color="D6E4F0") if EXCEL_AVAILABLE else None

COL_WIDTHS = {"A": 18, "B": 22, "C": 5, "D": 45, "E": 55, "F": 70, "G": 22}

def _setup_sheet(ws):
    for col, width in COL_WIDTHS.items():
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"

def _write_header(ws):
    headers = ["State", "Topic", "#", "Title", "URL", "Description", "Searched At"]
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font      = Font(name="Arial", bold=True, color="FFFFFF", size=11)
        cell.fill      = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border    = border
    ws.row_dimensions[1].height = 20

def _append_rows(ws, state, topic, results, searched_at):
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for idx, item in enumerate(results, 1):
        row = [state, topic, idx,
               item.get("title", ""),
               item.get("url", ""),
               item.get("description", ""),
               searched_at]
        r = ws.max_row + 1
        for c, val in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=val)
            cell.border    = border
            cell.alignment = Alignment(vertical="top", wrap_text=(c in (4, 5, 6)))
            if c == 1:
                cell.font = Font(name="Arial", bold=True, size=10, color="1F4E79")
                cell.fill = STATE_FILL
            elif c == 2:
                cell.font = Font(name="Arial", bold=True, size=10)
                cell.fill = TOPIC_FILL
            else:
                cell.font = Font(name="Arial", size=10)
        ws.row_dimensions[r].height = 40

def _get_or_create_workbook(path):
    try:
        wb = load_workbook(path)
        ws = wb.active
    except FileNotFoundError:
        wb = Workbook()
        ws = wb.active
        ws.title = "Results"
        _setup_sheet(ws)
        _write_header(ws)
    return wb, ws

# ── Core search ───────────────────────────────────────────────────────────────
def search_google(query: str, limit: int = NUM_RESULTS) -> List[Dict[str, Any]]:
    url    = f"{OPENSERP_URL}/{SEARCH_ENGINE}/search"
    params = {"text": query, "limit": limit, "gl": COUNTRY, "lang": LANGUAGE}
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"❌ Error searching '{query}': {e}")
        return []

def main(state: str) -> None:
    print(f"\n🌱 Searching clean energy topics for: {state}\n")
    wb, ws = (_get_or_create_workbook(OUTPUT_FILE) if EXCEL_AVAILABLE else (None, None))

    for topic in TOPICS:
        query       = f"clean energy {topic} {state}"
        searched_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n📌 {query}")
        results = search_google(query)

        if not results:
            print("   No results found.")
        else:
            for idx, item in enumerate(results, 1):
                title = item.get("title", "N/A")
                url   = item.get("url", "N/A")
                desc  = item.get("description", "")
                if len(desc) > 120:
                    desc = desc[:117] + "..."
                print(f"   {idx}. {title}\n       URL : {url}\n       Desc: {desc}")
            if EXCEL_AVAILABLE and ws is not None:
                _append_rows(ws, state, topic, results, searched_at)

        time.sleep(1)

    if EXCEL_AVAILABLE and wb is not None:
        wb.save(OUTPUT_FILE)
        print(f"\n📊 Results saved → {OUTPUT_FILE}")

    print("\n✅ Done.")

# ── Entry points ──────────────────────────────────────────────────────────────
def _interactive():
    print(f"🔍 Clean Energy Search\nOpenSERP: {OPENSERP_URL} | Engine: {SEARCH_ENGINE}\n")
    while True:
        state = input("🗺️  Enter a U.S. state: ").strip().title()
        if state in VALID_STATES:
            break
        print(f"   ⚠️  '{state}' not recognized. Try again.")
    main(state)

def _cli(states: list):
    for raw in states:
        state = raw.strip().title()
        if state not in VALID_STATES:
            print(f"⚠️  Skipping '{state}' — not a recognized U.S. state.")
            continue
        print(f"\n{'='*50}\n  🗺️  State: {state}\n{'='*50}")
        main(state)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        _cli(sys.argv[1:])
    else:
        _interactive()
