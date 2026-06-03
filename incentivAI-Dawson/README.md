# IncentivAI
### Automated Discovery and Extraction of U.S. Electric Utility Energy Incentive Programs

> Capstone project — University of Washington, Chemical Engineering  
> Built with Python, crawl4ai, Streamlit, and large language models.

---

## Table of Contents

- [Project Summary](#project-summary)
- [Key Findings](#key-findings)
- [Data Sources and Caveats](#data-sources-and-caveats)
- [Project Structure](#project-structure)
- [Setup](#setup)
  - [Requirements](#requirements)
  - [Step 1 — Clone the repo](#step-1--clone-the-repo)
  - [Step 2 — Install uv](#step-2--install-uv)
  - [Step 3 — Create virtual environment and install dependencies](#step-3--create-a-virtual-environment-and-install-dependencies)
  - [Step 4 — Activate the virtual environment](#step-4--activate-the-virtual-environment)
  - [Step 5 — Install Playwright browsers](#step-5--install-playwright-browsers)
  - [Step 6 — Install Tesseract OCR](#step-6--install-tesseract-ocr)
  - [Step 7 — Set up your LLM](#step-7--set-up-your-llm)
  - [Step 8 — Configure config.py](#step-8--configure-configpy)
- [Running the App](#running-the-app)
  - [Streamlit UI](#streamlit-ui-recommended)
  - [CLI / Terminal](#cli--terminal)
  - [Running the Pipeline Directly (Python)](#running-the-pipeline-directly-python)
  - [Supercomputer / SLURM](#supercomputer--slurm-hyak)
- [Running Individual Modules](#running-individual-modules)
  - [url_source.py](#urlsourcepy)
  - [scraper.py](#scraperpy)
  - [processor.py](#processorpy)
  - [llm_agent.py](#llmagentpy)
  - [exporter.py](#exporterpy)
  - [main.py](#mainpy-direct)
- [Modes](#modes)
  - [Upload Excel](#1-upload-excel)
  - [Single URL](#2-single-url)
  - [Upload Markdown](#3-upload-markdown)
  - [City URL Discovery](#4-city-url-discovery)
- [Common Workflows](#common-workflows)
  - [Workflow A — Test a single utility site](#workflow-a--test-a-single-utility-site-5-minutes)
  - [Workflow B — Run a full state batch](#workflow-b--run-a-full-state-batch)
  - [Workflow C — Discover URLs then extract](#workflow-c--discover-new-urls-then-extract)
  - [Workflow D — Production run on Hyak](#workflow-d--production-run-on-hyak)
- [OpenSERP Setup](#openserp-setup)
- [LLM Providers & Model Selection](#llm-providers--model-selection)
- [Output Files](#output-files)
- [Troubleshooting](#troubleshooting)
- [Known Limitations](#known-limitations)
- [Dependencies](#dependencies)

---

## Project Summary

The United States has thousands of electric utilities — cooperatives, municipal utilities, public utility districts, and investor-owned companies — many of which offer energy efficiency rebates, solar incentives, heat pump programs, EV charger rebates, and weatherization assistance. These programs are poorly aggregated. Existing databases like DSIRE capture some programs but miss a large share of smaller cooperative and municipal utility offerings that only appear on the utility's own website.

**IncentivAI is a pipeline that automates the discovery and structured extraction of these programs at scale.**

The pipeline has three stages:

1. **Discover** — find utility website URLs by U.S. state using a local OpenSERP search instance (Bing/DuckDuckGo)
2. **Extract** — deep-crawl each URL using a headless browser, extract page content including embedded PDFs and Excel files, and run an LLM extraction pass to pull structured program data
3. **Export** — output a structured CSV with one row per program found, including program name, type, financial details, eligibility, application process, and sector

The goal is to build a comprehensive, machine-readable dataset of utility incentive programs that can inform clean energy policy, consumer outreach, and research into the geographic distribution of energy efficiency incentives.

---

## Key Findings

- **94% extraction accuracy on large utility sites** — manual review of one major utility's incentive page found 61 out of 65 rebate programs correctly extracted with accurate financial details when run with GPT-4o via the UW SSEC AI Gateway.
- **~70% extraction accuracy with local models** — hand examination of qwen2.5:14b output against ground truth showed roughly 70% correct field extraction across program name, financial details, and eligibility. Misses were concentrated in complex tables and multi-program pages.
- **40+ new utility URLs per state** — the City URL Discovery pipeline consistently surfaces over 40 unique utility and cooperative websites per state using Bing via OpenSERP, pulling sites not indexed in DSIRE.
- **Model size is the dominant factor in extraction quality** — the gap between qwen2.5:14b (~70%) and GPT-4o (~94%) is primarily in financial detail verbatim capture and correct program delineation on dense pages. Both models perform well on simple single-program pages.
- **Cooperative and municipal utility sites are systematically under-represented in DSIRE** — a significant share of URLs discovered by IncentivAI returned programs with no corresponding DSIRE entry, confirming the hypothesis that smaller utility websites are the primary coverage gap in existing databases.

---

## Data Sources and Caveats

### Primary Sources
- **Electric utility official websites** — scraped directly. Targets cooperative, municipal, public utility district, and investor-owned utility sites across all 50 U.S. states. Site list built using OpenSERP discovery + manual curation against EIA-861 utility naming patterns.
- **Utility-hosted PDFs and Excel files** — automatically discovered on crawled pages and extracted alongside HTML content.

### Discovery Source
- **OpenSERP** (local instance) — a self-hosted search API that queries Bing, DuckDuckGo, or Google via headless Chrome. Used exclusively to build the URL list, not for content. See [OpenSERP Setup](#openserp-setup).

### Caveats
- **Coverage is not complete.** Some utility sites block headless browsers, time out on deep crawls, or have JavaScript-gated content that crawl4ai cannot render.
- **LLM extraction is not perfect.** Small local models (qwen2.5:14b) miss financial details and misclassify program types at a higher rate than cloud models (GPT-4o). All results should be treated as a starting point for human review, not a ground truth.
- **Programs change.** Utility incentive programs expire, run out of funding, or change eligibility without notice. This dataset represents a point-in-time snapshot.
- **Google searches are unreliable for automation.** The pipeline defaults to Bing via OpenSERP. Google aggressively rate-limits and CAPTCHAs headless browser searches — after 5 consecutive queries it triggers a circuit breaker and returns 0 results for the remainder of the session. Use Bing or DuckDuckGo for all discovery runs.

---

## Project Structure

```
IncentivAI/
├── app.py                  ← Streamlit UI entry point
├── cli.py                  ← Terminal / supercomputer entry point
├── main.py                 ← Shared pipeline orchestration
├── config.py               ← All configuration constants
├── modules/
│   ├── url_source.py       ← URL loading + OpenSERP discovery
│   ├── scraper.py          ← Web / PDF / Excel / image scraping
│   ├── processor.py        ← LLM prompt building and extraction
│   ├── llm_agent.py        ← Multi-provider LLM client
│   ├── exporter.py         ← CSV and markdown output
│   └── openserp.exe        ← Pre-built OpenSERP server binary (Windows)
├── utils/
│   └── logger.py           ← Shared logger
├── slurm/
│   └── run_job.sh          ← SLURM batch job for Hyak supercomputer
└── logs/                   ← Runtime logs (gitignored)
```

---

## Setup

### Requirements
- Python 3.11+
- `uv` package manager
- Tesseract OCR (for image extraction)
- Ollama (for local LLM) OR an API key for OpenAI / Anthropic / Google
- OpenSERP executable (for URL discovery only)

---

### Step 1 — Clone the repo

```bash
git clone https://github.com/your-org/IncentivAI.git
cd IncentivAI
```

---

### Step 2 — Install `uv`

`uv` is a fast Python package manager that replaces pip for this project. Install it once globally:

```bash
pip install uv
```

Verify:
```bash
uv --version
```

---

### Step 3 — Create a virtual environment and install dependencies

```bash
uv sync
```

This does three things in one command:
- Creates a `.venv/` folder inside your project (your isolated Python environment)
- Reads `pyproject.toml` to find all required packages
- Installs all of them into `.venv/`

> ⚠️ **If Streamlit stays at version 1.19 after sync**, check `pyproject.toml` for `altair<5` and change it to `altair>=5`. The old altair pin conflicts with Streamlit 1.28+ and silently caps your Streamlit version. Then re-run `uv sync`.

You only need to run `uv sync` once after cloning, and again any time `pyproject.toml` changes.

---

### Step 4 — Activate the virtual environment

**Windows (PowerShell):**
```powershell
.\.venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
.\.venv\Scripts\activate.bat
```

**Mac / Linux:**
```bash
source .venv/bin/activate
```

When activated, your terminal prompt shows `(.venv)` at the start. To deactivate:
```bash
deactivate
```

> **VS Code tip:** Open the project folder and select the `.venv` interpreter via `Ctrl+Shift+P → Python: Select Interpreter`. VS Code will activate it automatically in every new terminal.

Alternatively, prefix every command with `uv run` instead of activating — both work identically:
```bash
uv run python myscript.py   # same as activating first, then running
```

---

### Step 5 — Install Playwright browsers

```bash
uv run playwright install chromium
```

Downloads a bundled Chromium browser (~170MB) used by crawl4ai for deep crawling. Only needed once.

---

### Step 6 — Install Tesseract OCR

Required for image file extraction. Skip if you don't need image OCR.

**Windows:**
Download from [github.com/UB-Mannheim/tesseract/wiki](https://github.com/UB-Mannheim/tesseract/wiki) and add to PATH.

Verify:
```bash
tesseract --version
```

**Linux / Hyak:**
```bash
sudo apt install tesseract-ocr
```

---

### Step 7 — Set up your LLM

**Option A — Local Ollama:**
```bash
# Install from https://ollama.com, then:
ollama pull qwen2.5:14b    # recommended local model
ollama pull qwen2.5:7b     # if you have less than 12GB RAM

ollama list                # verify models are installed
```

**Option B — Cloud provider (Mac/Linux):**
```bash
export OPENAI_API_KEY=your_key_here
export ANTHROPIC_API_KEY=your_key_here
export GOOGLE_API_KEY=your_key_here
```

**Option B — Cloud provider (Windows PowerShell):**
```powershell
$env:OPENAI_API_KEY="your_key_here"
$env:ANTHROPIC_API_KEY="your_key_here"
$env:GOOGLE_API_KEY="your_key_here"
```

**Option C — UW SSEC AI Gateway (Hyak only):**
```bash
export UW_SSEC_AI_GATEWAY_KEY=your_key_here
export UW_SSEC_AI_GATEWAY_BASE_URL=your_gateway_url_here
```

---

### Step 8 — Configure `config.py`

```python
MODEL_NAME          = "qwen2.5:14b"  # change to match your setup
DEFAULT_TEMPERATURE = 0.1
DEFAULT_TRUNCATION  = 15000          # see LLM section for recommended values
MAX_RETRIES         = 2
LLM_TIMEOUT         = 180
```

---

## Running the App

### Streamlit UI (recommended)

```bash
uv run streamlit run app.py
# or, if venv is activated:
streamlit run app.py
```

Opens at `http://localhost:8501`. Keep the terminal open — closing it kills the app.

---

### CLI / Terminal

```bash
# Excel file with local Ollama
python cli.py --file urls.xlsx --provider ollama --model qwen2.5:14b

# Excel file with OpenAI
python cli.py --file urls.xlsx --provider openai --model gpt-4o

# Save output to a specific directory
python cli.py --file urls.xlsx --provider openai --model gpt-4o --output results/
```

**All CLI flags:**

| Flag | Description | Default |
|---|---|---|
| `--file` | Path to Excel file with URLs column | — |
| `--provider` | LLM provider | `ollama` |
| `--model` | Model name | from `config.py` |
| `--temperature` | LLM temperature | from `config.py` |
| `--truncation` | Max scrape length (chars) | from `config.py` |
| `--output` | Output directory | current directory |
| `--output-name` | Output CSV filename | `incentives_output.csv` |

---

### Running the Pipeline Directly (Python)

For quick tests without UI or CLI:

```python
from main import run_pipeline

run_pipeline(
    mode="Upload Excel",
    uploaded_file="urls.xlsx",
    provider="ollama",
    model="qwen2.5:14b",
    temperature=0.1,
    truncation_length=15000,
)
```

Single URL quick test:
```python
import pandas as pd, io
from main import run_pipeline

df = pd.DataFrame({"URLs": ["https://www.example-utility.com/rebates"]})
buf = io.BytesIO()
df.to_excel(buf, index=False)
buf.seek(0)

run_pipeline(
    mode="Upload Excel",
    uploaded_file=buf,
    provider="ollama",
    model="qwen2.5:14b",
    temperature=0.1,
    truncation_length=15000,
)
```

---

### Supercomputer / SLURM (Hyak)

```bash
cd slurm
sbatch run_job.sh
```

Monitor:
```bash
squeue -u $USER
tail -f logs/incentivai_<job_id>.out
```

> **Recommended for production runs.** GPT-4o via the UW SSEC gateway on Hyak means LLM calls take seconds not minutes, and your local machine is completely free.

---

## Running Individual Modules

Every module can be imported and called directly from a Python script or interactive session. This is useful for debugging a specific stage, testing a single URL, or verifying your setup before running a full batch.

All examples assume your venv is activated or you prefix with `uv run python`.

---

### `url_source.py`

**Load URLs from an Excel file:**
```python
from modules.url_source import get_urls

entries = get_urls(mode="Upload Excel", uploaded_file="urls.xlsx")
for e in entries:
    print(e["url"], e["parent"])
```

**Test a single URL load manually:**
```python
from modules.url_source import _get_urls_from_excel

entries = _get_urls_from_excel("urls.xlsx")
print(f"Loaded {len(entries)} URLs")
print(entries[:3])  # preview first 3
```

**Test OpenSERP is reachable before running discovery:**
```python
from modules.url_source import _search_openserp

results = _search_openserp(
    query="electric cooperative rebate Texas",
    openserp_url="http://localhost:7070",
    engine="bing",
    limit=5
)
print(f"Got {len(results)} results")
for r in results:
    print(r.get("url"), r.get("title"))
```

**Run discovery for a single state:**
```python
from modules.url_source import get_urls_from_discovery

results = get_urls_from_discovery(
    states=["Texas"],
    openserp_url="http://localhost:7070",
    engine="bing",
    num_results=8,
    existing_db=None,
    progress_callback=lambda c, t, url="", message="": print(f"[{c}/{t}] {message}"),
)
print(f"\nFound {len(results)} URLs")
for r in results:
    print(r["url"])
```

**Check if a URL passes the domain blocklist:**
```python
from modules.url_source import is_utility_url

urls = [
    "https://www.texaselectric.coop/rebates",
    "https://www.dsireusa.org/programs",
    "https://www.energysage.com/solar",
]
for url in urls:
    print(url, "→", "KEEP" if is_utility_url(url) else "BLOCKED")
```

**Extract domain from a URL:**
```python
from modules.url_source import _extract_domain

print(_extract_domain("https://www.texaselectric.coop/rebates"))
# → texaselectric.coop
```

---

### `scraper.py`

**Check if a URL points to a file (PDF, Excel, image):**
```python
from modules.scraper import is_file_url

urls = [
    "https://example.com/rebate-guide.pdf",
    "https://example.com/programs.xlsx",
    "https://example.com/rebates",          # web page
    "https://example.com/download?id=123",  # no extension — triggers HEAD request
]
for url in urls:
    is_file, file_type = is_file_url(url)
    print(url, "→", file_type if is_file else "web page")
```

**Scrape a PDF directly:**
```python
from modules.scraper import extract_pdf

text = extract_pdf("https://example.com/rebate-guide.pdf")
if text:
    print(f"Extracted {len(text)} chars")
    print(text[:500])
else:
    print("No text extracted")
```

**Scrape an Excel file directly:**
```python
from modules.scraper import extract_excel

text = extract_excel("https://example.com/programs.xlsx")
print(text[:500] if text else "No content")
```

**Scrape a single web page (no deep crawl):**
```python
from modules.scraper import scrape_all_pages

pages = scrape_all_pages(
    url="https://www.example-utility.com/rebates",
    truncation_length=15000,
    use_deep_crawl=False      # single page only, no sublink following
)
for page in pages:
    print(f"URL: {page['url']}")
    print(f"Content length: {len(page['content'])} chars")
    print(page['content'][:300])
```

**Deep crawl a URL (follows sublinks up to depth 2):**
```python
from modules.scraper import scrape_all_pages

pages = scrape_all_pages(
    url="https://www.example-utility.com/rebates",
    truncation_length=15000,
    use_deep_crawl=True       # follows sublinks — default behavior
)
print(f"Found {len(pages)} pages")
for page in pages:
    print(f"  {page['url']} (parent: {page['parent']})")
```

**Test content preprocessing:**
```python
from modules.scraper import preprocess_content, extract_relevant_sentences, INCENTIVE_KEYWORDS

raw = """
Skip to main content | Cookie Policy | Accept All
Our Residential Solar Rebate offers $500 for qualifying installations.
Contact us at info@utility.com for more details.
"""
cleaned = preprocess_content(raw)
filtered = extract_relevant_sentences(cleaned, INCENTIVE_KEYWORDS)
print(filtered)
```

**Reset seen URLs between test runs** (prevents deduplication carrying over):
```python
from modules.scraper import reset_seen_urls
reset_seen_urls()
```

---

### `processor.py`

**Build and inspect the LLM prompt for any text:**
```python
from modules.processor import build_prompt

text = "Central Texas Electric offers a $500 heat pump rebate for residential customers."
prompt = build_prompt(text, url="https://www.ctec.coop/rebates")
print(prompt)
# Paste this into any LLM chat to see what it would extract
```

**Run LLM extraction on any text:**
```python
from modules.processor import process_text

text = """
Central Texas Electric Cooperative offers the following programs:
- Heat Pump Rebate: $500 for qualifying ENERGY STAR heat pumps
- EV Charger Rebate: $250 for Level 2 chargers installed at residential accounts
- Smart Thermostat Rebate: $75 for ENERGY STAR certified smart thermostats
Eligibility: Must be an active CTEC residential customer.
"""

result = process_text(
    text=text,
    url="https://www.ctec.coop/rebates",
    temperature=0.1,
    provider="ollama",
    model="qwen2.5:14b",
)

print(f"Utility: {result['utility_company']}")
print(f"Programs found: {len(result['programs'])}")
for p in result["programs"]:
    print(f"  - {p['program_name']}: {p['financial_details']}")
```

**Test with a cloud model:**
```python
from modules.processor import process_text

result = process_text(
    text="Your scraped text here",
    url="https://example.com",
    temperature=0.1,
    provider="openai",
    model="gpt-4o",
)
print(result)
```

**Test JSON parsing only (check if LLM output is valid):**
```python
import json

raw_llm_output = '''
```json
{"utility_company": "Test Coop", "programs": [], "summary_of_page": "No programs found."}
```
'''

import re
cleaned = raw_llm_output.strip()
if cleaned.startswith("```"):
    cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
    cleaned = re.sub(r"\n?```$", "", cleaned)

data = json.loads(cleaned)
print(data)
```

---

### `llm_agent.py`

**Test if your LLM provider is working:**
```python
from modules.llm_agent import call_llm

response = call_llm(
    prompt="Return only this JSON: {\"status\": \"ok\"}",
    provider="ollama",
    model="qwen2.5:14b",
    temperature=0.0,
)
print(response)
```

**Test OpenAI connection:**
```python
from modules.llm_agent import call_llm

response = call_llm(
    prompt="Say hello in one word.",
    provider="openai",
    model="gpt-4o-mini",
    temperature=0.0,
)
print(response)
```

**Test UW SSEC gateway:**
```python
import os
os.environ["UW_SSEC_AI_GATEWAY_KEY"] = "your_key"
os.environ["UW_SSEC_AI_GATEWAY_BASE_URL"] = "your_url"

from modules.llm_agent import call_llm

response = call_llm(
    prompt="Say hello.",
    provider="uw_ssec",
    model="gpt-4o",
    temperature=1,   # gpt-5 series requires temperature=1
)
print(response)
```

**Build an LLM client directly (without calling it):**
```python
from modules.llm_agent import build_llm

llm = build_llm(provider="ollama", model="qwen2.5:14b", temperature=0.1)
print(type(llm))  # confirms the client was built without errors
```

---

### `exporter.py`

**Flatten and export results to CSV manually:**
```python
from modules.exporter import export_to_csv

# Simulate what process_text returns
results = [
    {
        "utility_company": "Central Texas Electric",
        "programs": [
            {
                "program_name": "Heat Pump Rebate",
                "program_type": "rebate",
                "financial_details": "$500",
                "eligibility": "Residential CTEC customers",
                "application_process": "Submit online form",
                "sector": "Residential",
                "notes": None,
            }
        ],
        "summary_of_page": "CTEC offers several residential rebates.",
        "source_url": "https://www.ctec.coop/rebates",
        "parent_url": None,
        "is_sublink": False,
        "url_type": "web",
        "extraction_timestamp": "2025-01-01T00:00:00",
    }
]

csv_path = export_to_csv(results)
print(f"Saved to: {csv_path}")

import pandas as pd
print(pd.read_csv(csv_path).to_string())
```

**Append a markdown entry manually:**
```python
from modules.exporter import append_markdown_entry

entry = {
    "utility_company": "Central Texas Electric",
    "programs": [{"program_name": "Heat Pump Rebate", "financial_details": "$500",
                  "program_type": "rebate", "eligibility": "Residential", 
                  "application_process": "Online", "sector": "Residential", "notes": None}],
    "summary_of_page": "Rebate programs for residential customers.",
    "source_url": "https://www.ctec.coop/rebates",
    "is_sublink": False,
    "extraction_timestamp": "2025-01-01T00:00:00",
}

append_markdown_entry(entry, "test_markdown.csv")
print("Written to test_markdown.csv")
```

---

### `main.py` (direct)

**Run the full pipeline on a file path:**
```python
from main import run_pipeline

output_csv = run_pipeline(
    mode="Upload Excel",
    uploaded_file="urls.xlsx",
    state=None,
    temperature=0.1,
    truncation_length=15000,
    progress_callback=lambda c, t, url="", message="": print(f"[{c}/{t}] {message}"),
    cancel_flag=None,
    provider="ollama",
    model="qwen2.5:14b",
)
print(f"Output saved to: {output_csv}")
```

**Run on a single URL without the UI:**
```python
import io, pandas as pd
from main import run_pipeline

df = pd.DataFrame({"URLs": ["https://www.anaheim.net/936/Energy-Rebates-Incentives"]})
buf = io.BytesIO()
df.to_excel(buf, index=False)
buf.seek(0)

output_csv = run_pipeline(
    mode="Upload Excel",
    uploaded_file=buf,
    state=None,
    temperature=0.1,
    truncation_length=40000,
    provider="openai",
    model="gpt-4o",
)

import pandas as pd
df = pd.read_csv(output_csv)
print(df[["utility_company", "program_name", "financial_details"]].to_string())
```

**Test the error logger directly:**
```python
from main import log_error

log_error(
    url="https://example.com/rebates",
    url_type="web",
    stage="scraping",
    reason="Test error",
    detail="This is a test entry to verify errors.csv is working correctly."
)
# Check errors.csv in your project folder
```

---

## Modes

### 1. Upload Excel

Upload an `.xlsx` file with a column named `URLs` (case-insensitive — also accepts `url`, `links`, `website`, etc.). Optionally include a `parent_url` column.

| URLs | parent_url |
|---|---|
| https://www.example-coop.com/rebates | |
| https://www.example-coop.com/rebates/solar | https://www.example-coop.com/rebates |

Leave `parent_url` blank for main links. The pipeline deep-crawls each URL and all discovered subpages.

---

### 2. Single URL

Enter one URL directly in the sidebar. Useful for testing a specific page before running a full batch.

---

### 3. Upload Markdown

Upload a `.md` or `.txt` file containing pre-scraped content. The pipeline runs LLM extraction directly — no scraping. Useful for:
- Pages that block headless browsers
- Content copied manually
- Testing prompt quality on known content

---

### 4. City URL Discovery

Discovers utility website URLs by state using OpenSERP. Does **not** run extraction — outputs a URL list to feed into the extraction pipeline.

**Requires OpenSERP running locally.** See [OpenSERP Setup](#openserp-setup).

**Recommended workflow:**
1. Run **City URL Discovery** → downloads discovered URLs as Excel
2. Use **Merge Database** → deduplicates against your existing URL list → download merged
3. Upload merged file to **Upload Excel** mode → run full extraction pipeline

**Engine recommendation:** Use **Bing**. Google CAPTCHAs after 5 consecutive queries from the same IP and blocks all further results for hours.

---

## Common Workflows

### Workflow A — Test a single utility site (5 minutes)

1. Open Streamlit: `streamlit run app.py`
2. Select **Single URL** in the sidebar
3. Paste a utility rebate page URL (e.g. `https://www.anaheim.net/936/Energy-Rebates-Incentives`)
4. Set provider to `ollama`, model to `qwen2.5:14b`
5. Click **▶ Run Extraction**
6. Check the **📝 Live Summaries** tab for results
7. Download `incentives_output.csv` from the **📊 Progress** tab

---

### Workflow B — Run a full state batch

1. Prepare an Excel file with one URL per row in a column named `URLs`
2. Open Streamlit: `streamlit run app.py`
3. Select **Upload Excel**, upload your file
4. Set provider and model (use `openai` + `gpt-4o` for best results)
5. Click **▶ Run Extraction**
6. Monitor progress in the **📊 Progress** tab
7. Download results when complete — do this before starting another run as CSVs clear on each new run

---

### Workflow C — Discover new URLs then extract

1. Start OpenSERP in a separate terminal: `cd modules && openserp.exe`
2. Open Streamlit in another terminal: `streamlit run app.py`
3. Select **City URL Discovery**
4. Choose states, set engine to **Bing**, set OpenSERP URL to `http://localhost:7070`
5. Click **▶ Run Discovery** → download the discovered URLs Excel
6. Use **Merge Database** to dedup against your existing database → download merged file
7. Switch to **Upload Excel** mode, upload the merged file, run extraction

---

### Workflow D — Production run on Hyak

1. SSH into Hyak: `ssh your_netid@klone.hyak.uw.edu`
2. Set environment variables:
   ```bash
   export UW_SSEC_AI_GATEWAY_KEY=your_key
   export UW_SSEC_AI_GATEWAY_BASE_URL=your_url
   ```
3. Place your Excel file in the project directory
4. Edit `slurm/run_job.sh` — update `--file` path and `--model`
5. Submit: `cd slurm && sbatch run_job.sh`
6. Monitor: `squeue -u $USER` and `tail -f logs/incentivai_<JOBID>.out`
7. Results saved to `results/incentives_<JOBID>.csv`

---

## OpenSERP Setup

OpenSERP is a self-hosted search API that queries Bing, DuckDuckGo, or Google using a real headless Chrome browser. IncentivAI uses it only for URL discovery.

**Without OpenSERP running, City URL Discovery will not work.**

---

### Option 1 — OpenSERP executable (recommended for Windows)

The project includes `openserp.exe` in the `modules/` folder.

```bash
# Open a NEW terminal window (separate from the one running Streamlit)
cd modules
openserp.exe
```

When running correctly:
```
┌───────────────────────────────────────────────────┐
│                   Fiber v2.52.9                   │
│               http://127.0.0.1:7070               │
│                                                   │
│ Handlers ............ 38  Processes ........... 1 │
│ Prefork ....... Disabled  PID ............. XXXXX │
└───────────────────────────────────────────────────┘
```

Set the **OpenSERP URL** in the Streamlit UI to `http://localhost:7070`.

> ⚠️ Do not close this terminal while running discovery. Closing it kills the server and all queries will fail silently returning 0 results.

---

### Option 2 — Docker

```bash
docker pull karust/openserp
docker run -p 7070:7070 karust/openserp
```

Verify:
```bash
curl "http://localhost:7070/bing/search?text=electric+utility+rebate+Texas&limit=5"
```

---

### Option 3 — Build from source (Go required)

```bash
git clone https://github.com/karust/openserp.git
cd openserp
go build -o openserp
./openserp serve --port 7070
```

---

### On Hyak

```bash
docker run -d -p 7070:7070 karust/openserp
# or tunnel from local machine:
ssh -L 7070:localhost:7070 your_netid@klone.hyak.uw.edu
```

---

### Google vs Bing vs DuckDuckGo

| Engine | Reliability | Notes |
|---|---|---|
| **Bing** ✅ | High | Recommended default. Rarely CAPTCHAs automated searches. |
| **DuckDuckGo** ✅ | High | Most permissive. Slightly lower result quality. |
| **Google** ⚠️ | Low | Best quality but CAPTCHAs after 5 consecutive queries. IP bans last hours to days. Use at most once per day, never re-run same state same day. |

---

## LLM Providers & Model Selection

Model choice is the single biggest factor in extraction quality.

> **Note on truncation:** The `DEFAULT_TRUNCATION` setting is in **characters**, not tokens. Roughly 4 characters = 1 token. So `40000` chars ≈ 10,000 tokens, and `100000` chars ≈ 25,000 tokens. GPT-4o's 128k token window is ~500,000 characters — effectively no limit for any real webpage.

---

### Tier 1 — Small local models (≤10B parameters)

Examples: `qwen2.5:7b`, `llama3.2:3b`, `mistral:7b`

```python
MODEL_NAME         = "qwen2.5:7b"
DEFAULT_TRUNCATION = 8000
LLM_TIMEOUT        = 180
```

- Stay around `8000`–`12000` chars — these models degrade on longer context
- ~60–70% field extraction accuracy on complex pages
- Best for development, testing, and offline use

---

### Tier 2 — Medium local models (10B–30B parameters)

Examples: `qwen2.5:14b`, `qwen2.5:32b`, `mixtral:8x7b`

```python
MODEL_NAME         = "qwen2.5:14b"
DEFAULT_TRUNCATION = 40000
LLM_TIMEOUT        = 180
```

- **~70% extraction accuracy** confirmed by manual hand-examination
- `40000` chars (~10k tokens) works well — these models have 128k token windows
- Significantly better than 7B on financial details and multi-program pages
- Fully local and free to run

---

### Tier 3 — Cloud models (GPT-4o, Claude, Gemini)

```python
MODEL_NAME         = "gpt-4o"
DEFAULT_TRUNCATION = 100000   # or higher — effectively no limit
LLM_TIMEOUT        = 60
```

- **~94% extraction accuracy** — 61/65 programs correctly extracted on a major utility site
- Don't truncate — send everything, GPT-4o handles it
- Dramatically better on complex tables and verbatim financial capture
- Requires API key, costs money per run

---

### Provider setup

| Provider | Flag | Requires |
|---|---|---|
| Ollama (local) | `ollama` | Ollama installed + `ollama pull <model>` |
| OpenAI | `openai` | `OPENAI_API_KEY` env var |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` env var |
| Google Gemini | `google` | `GOOGLE_API_KEY` env var |
| UW SSEC Gateway | `uw_ssec` | `UW_SSEC_AI_GATEWAY_KEY` + `UW_SSEC_AI_GATEWAY_BASE_URL` |

---

### Recommended configuration by use case

| Use case | Provider | Model | Truncation |
|---|---|---|---|
| Local dev / testing | ollama | `qwen2.5:7b` | `8000` |
| Best local quality | ollama | `qwen2.5:14b` | `40000` |
| Fast + affordable cloud | openai | `gpt-4o-mini` | `50000` |
| Production / best results | openai or uw_ssec | `gpt-4o` | `100000+` |

---

## Output Files

| File | Description |
|---|---|
| `incentives_output.csv` | Main output — one row per program found |
| `errors.csv` | Failed URLs with stage, reason, and error detail |
| `markdown_output.csv` | Human-readable markdown summaries per URL |
| `utility_urls_discovered.xlsx` | URLs found by City URL Discovery |

> ⚠️ `errors.csv` and `markdown_output.csv` are **cleared at the start of each new run** in the Streamlit UI. Download them before starting another run if you need them.

### Output CSV columns

| Column | Description |
|---|---|
| `link_type` | `Main Link` or `Sublink` |
| `parent_url` | Parent URL if sublink, else blank |
| `source_url` | URL that was scraped |
| `url_type` | `web`, `pdf`, `excel`, or `image` |
| `utility_company` | Name of the utility |
| `program_name` | Full program name |
| `program_type` | Rebate, grant, tax credit, loan, etc. |
| `financial_details` | Dollar amounts, percentages, caps — verbatim from source |
| `eligibility` | Who qualifies and under what conditions |
| `application_process` | How to apply |
| `sector` | Residential, Commercial, Industrial, Agricultural |
| `notes` | Expiration dates, caveats, stacking rules |
| `summary_of_page` | Page summary |
| `extraction_timestamp` | UTC timestamp of processing |

### Error CSV columns

| Column | Description |
|---|---|
| `timestamp` | When the error occurred |
| `url` | URL that failed |
| `url_type` | web / pdf / excel / image |
| `stage` | scraping / llm_parsing / llm_timeout / llm_extraction |
| `reason` | Short human-readable reason |
| `detail` | Full error message (capped at 500 chars) |

---

## Troubleshooting

**Streamlit stays at version 1.19 after `uv sync`**
You have `altair<5` in `pyproject.toml`. Change it to `altair>=5` and re-run `uv sync`. The old altair pin conflicts with Streamlit 1.28+ and silently caps the version.

**`Error: Unrecognized type: LargeUtf8 (20)` in browser**
PyArrow version mismatch with Streamlit's JavaScript Arrow library. The `_safe_dataframe()` wrapper in `app.py` should prevent this. If it reappears, run `uv pip install --upgrade pyarrow streamlit`.

**`TypeError: container() got unexpected keyword argument 'height'`**
Your Streamlit version is below 1.32.0. Run `uv sync` — if it stays at 1.19, see the altair fix above.

**`TypeError: 'NoneType' object is not iterable` during City URL Discovery**
OpenSERP returned a non-list response (null or error object). The `_search_openserp()` function in `url_source.py` should guard against this. Also check that your OpenSERP URL is correct (`http://localhost:7070` not `7000`).

**City URL Discovery returns 0 results**
In order of likelihood:
1. OpenSERP URL in the UI is wrong — should be `http://localhost:7070`
2. `openserp.exe` is not running — open a separate terminal, `cd modules`, run `openserp.exe`
3. You're using Google engine — switch to Bing
4. Google has CAPTCHAd your IP — wait several hours or use a VPN

**`scrape_all_pages returned empty list` for all URLs in an Excel batch**
Playwright browser state is degrading between sequential URLs. Each URL now runs in an isolated thread — make sure you are running the latest `scraper.py` from this repo. Also check `errors.csv` for the specific failure stage.

**LLM timeout errors**
Increase `LLM_TIMEOUT` in `config.py`. For qwen2.5:14b on a mid-range laptop, `300` seconds is safer than `180`. Alternatively reduce `DEFAULT_TRUNCATION` — less content = faster LLM calls.

**`second argument (exceptions) must be a non-empty sequence`**
A crawl4ai internal bug triggered on certain sites. Your code handles it gracefully — the URL is logged to `errors.csv` and the pipeline continues. Update crawl4ai when a new version is available: `uv pip install --upgrade crawl4ai`.

**`Task was destroyed but it is pending`**
A noisy warning from crawl4ai's internal memory monitor. Does not affect results. Suppressed in `app.py` with `warnings.filterwarnings`.

**`use_container_width` deprecation warning**
Your Streamlit version is recent enough to use the new `width='stretch'` API. The `_dataframe()` wrapper in `app.py` handles both APIs automatically.

**Ollama model not found**
Run `ollama list` to see installed models. If your model isn't there, run `ollama pull qwen2.5:14b`. Make sure the model name in `config.py` matches exactly including the tag.

---

## Known Limitations

- **Memory usage is high during extraction runs.** crawl4ai launches real Chromium instances — 200–500MB RAM each. On a 50-URL batch expect 2–6GB RAM consumed during the run. Released after completion.
- **Google is unreliable for automated searching.** Use Bing or DuckDuckGo. See [Google vs Bing vs DuckDuckGo](#google-vs-bing-vs-duckduckgo).
- **Some utility sites block headless browsers.** Sites with Cloudflare, login walls, or aggressive bot detection return empty results. These are logged to `errors.csv`.
- **Results are a point-in-time snapshot.** Programs expire and change without notice.
- **Running extraction and other CPU-intensive tasks simultaneously is not recommended.** The scraper and local LLM together can saturate CPU and RAM on a typical laptop.

---

## Dependencies

All managed via `pyproject.toml` and installed with `uv sync`.

| Package | Purpose |
|---|---|
| `streamlit>=1.33.0` | Web UI |
| `altair>=5` | Required by Streamlit 1.28+ — must NOT be pinned to `<5` |
| `crawl4ai` | Web scraping with JS rendering via Playwright |
| `playwright` | Headless browser automation |
| `langchain-core` | LLM abstraction layer |
| `langchain-ollama` | Ollama provider |
| `langchain-openai` | OpenAI + UW SSEC gateway provider |
| `langchain-anthropic` | Anthropic provider |
| `langchain-google-genai` | Google Gemini provider |
| `pdfplumber` | PDF text extraction |
| `openpyxl` | Excel read/write |
| `pillow` + `pytesseract` | Image OCR |
| `aiohttp` | Async HTTP for auxiliary file fetching |
| `beautifulsoup4` | HTML parsing for auxiliary link discovery |
| `pandas` | Data handling and CSV output |
| `nest_asyncio` | Allows `asyncio.run()` inside Streamlit's event loop |
| `requests` | Synchronous HTTP for file downloads |
| `tabulate` | Markdown table formatting in Excel auxiliary extraction |

---

## Gitignore

```
logs/
*.csv
*.log
.env
__pycache__/
.venv/
scraped_data/
analysis_results/
uv.lock
```
