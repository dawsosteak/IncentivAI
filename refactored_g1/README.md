# IncentivAI

A modular pipeline for discovering and extracting structured data from utility company energy incentive programs. Supports four modes: **Upload Excel** (batch scrape from a URL list), **Single URL** (test one URL), **Upload Markdown** (run the LLM on pre-scraped text), and **City URL Discovery** (find new utility websites by state using OpenSERP).

---

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Setup](#setup)
  - [1. Clone the repo](#1-clone-the-repo)
  - [2. Install uv](#2-install-uv)
  - [3. Create the environment](#3-create-the-environment)
  - [4. Install Playwright browsers](#4-install-playwright-browsers)
  - [5. Install Tesseract (image OCR)](#5-install-tesseract-image-ocr)
  - [6. Set up your LLM](#6-set-up-your-llm)
- [Running the App](#running-the-app)
  - [Streamlit UI](#streamlit-ui)
  - [CLI / Terminal](#cli--terminal)
  - [Running run_pipeline() directly from Python](#running-run_pipeline-directly-from-python)
  - [Supercomputer / SLURM](#supercomputer--slurm)
- [Modes](#modes)
  - [Upload Excel](#upload-excel)
  - [Single URL](#single-url)
  - [Upload Markdown](#upload-markdown)
  - [City URL Discovery](#city-url-discovery)
- [OpenSERP Setup](#openserp-setup)
- [LLM Providers & Model Selection](#llm-providers--model-selection)
- [Configuration](#configuration)
- [Output Files](#output-files)
- [Common Issues](#common-issues)
- [Dependencies](#dependencies)
- [Gitignore](#gitignore)

---

## Overview

IncentivAI scrapes utility company websites and uses an LLM to extract structured incentive program data — program names, rebate amounts, eligibility requirements, and more.

The pipeline has three stages:

1. **Discover** — find utility website URLs by state using OpenSERP, or supply your own Excel file
2. **Extract** — scrape each URL (including linked PDFs and Excel files) and run LLM extraction
3. **Export** — output a structured CSV with one row per program found, plus markdown summaries

Switching between modes in the UI does **not** erase your previous results — each mode tracks its own progress independently.

---

## Project Structure

```
IncentivAI/
├── app.py                          ← Streamlit UI entry point
├── cli.py                          ← Terminal / supercomputer entry point
├── main.py                         ← Shared run_pipeline() logic + CLI fallback
├── config.py                       ← All constants, prompts, and defaults
├── pyproject.toml                  ← uv dependency manifest
├── runjob.sh                       ← SLURM batch job script
│
└── modules/
    ├── __init__.py                 ← Re-exports top-level callables
    ├── scraper.py                  ← Web, PDF, and Excel scraping
    ├── llm_agent.py                ← LLM client (ollama, openai, anthropic, google)
    ├── processor.py                ← LLM extraction, filtering, process_text()
    ├── exporter.py                 ← CSV and markdown output
    ├── url_source.py               ← URL loading, discovery, dedup, merge
    │
    └── searching/
        ├── __init__.py
        ├── energy_search.py        ← OpenSERP query builder
        ├── merge_urls.py           ← Domain-level deduplication helpers
        └── openserp.exe            ← Local search server — do not modify
```

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/your-org/IncentivAI.git
cd IncentivAI
```

---

### 2. Install uv

`uv` is a fast Python package manager that replaces pip + venv. Install it once on your machine:

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Mac / Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Close and reopen your terminal after installing.

---

### 3. Create the environment

From inside the project folder:

```powershell
uv sync
```

This reads `pyproject.toml`, creates a `.venv` folder, and installs every dependency. You never need to manually activate the environment — just prefix all commands with `uv run`.

If you add a new package later:
```powershell
uv add package-name
```

---

### 4. Install Playwright browsers

`crawl4ai` uses Playwright for JavaScript-rendered pages. Install the browser after `uv sync`:

```powershell
uv run playwright install chromium
```

---

### 5. Install Tesseract (image OCR)

Tesseract is used for extracting text from image-based PDFs. It must be installed separately — it is not a Python package.

**Windows:**
Download and install from [github.com/UB-Mannheim/tesseract/wiki](https://github.com/UB-Mannheim/tesseract/wiki).
After installing, add it to your PATH — the default install location is:
```
C:\Program Files\Tesseract-OCR
```

Verify it works:
```powershell
tesseract --version
```

**Linux / supercomputer:**
```bash
sudo apt install tesseract-ocr
# or on a module-based HPC system:
module load tesseract
```

If you skip Tesseract, image OCR will be silently skipped — the rest of the pipeline will still work.

---

### 6. Set up your LLM

**Local Ollama (free, no internet required):**
```powershell
# Install Ollama from https://ollama.com, then pull a model:
ollama pull qwen2.5:7b
```

Run `ollama list` to see what you have installed. Any model name from that list can be pasted into the Model Name field in the UI or passed via `--model` in the CLI.

**Cloud providers (set the API key as an environment variable):**

```powershell
# Windows PowerShell
$env:OPENAI_API_KEY    = "sk-..."
$env:ANTHROPIC_API_KEY = "sk-ant-..."
$env:GOOGLE_API_KEY    = "AIza..."
```

```bash
# Mac / Linux
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_API_KEY="AIza..."
```

---

## Running the App

### Streamlit UI

```powershell
uv run streamlit run app.py
```

Opens in your browser at `http://localhost:8501`. The sidebar lets you switch between all four modes. **Switching modes does not erase your previous results** — each mode saves its progress independently.

---

### CLI / Terminal

Use `cli.py` when you want to run the pipeline without a browser, on a server, or as part of a script.

```powershell
# Excel file with local Ollama
uv run python cli.py --file urls.xlsx --provider ollama --model qwen2.5:7b

# Excel file with OpenAI
uv run python cli.py --file urls.xlsx --provider openai --model gpt-4o

# Auto search by state (uses DuckDuckGo)
uv run python cli.py --state California --provider openai --model gpt-4o

# Save to a specific folder
uv run python cli.py --file urls.xlsx --provider openai --model gpt-4o --output results/

# Custom output filename
uv run python cli.py --file urls.xlsx --provider anthropic --model claude-opus-4-5 --output-name run_june.csv
```

**All CLI flags:**

| Flag | Description | Default |
|---|---|---|
| `--file` | Path to `.xlsx` file with a URLs column | — |
| `--state` | U.S. state name for auto search mode | — |
| `--provider` | LLM provider (`ollama`, `openai`, `anthropic`, `google`) | `ollama` |
| `--model` | Model name (exact string passed to provider) | from `config.py` |
| `--temperature` | LLM temperature — `0.0` is most deterministic | `0.1` |
| `--truncation` | Max characters of scraped content sent to LLM | `150000` |
| `--output` | Directory to save output CSV | current directory |
| `--output-name` | Output CSV filename | `incentives_output.csv` |

`--file` and `--state` are mutually exclusive — you must provide exactly one.

---

### Running run_pipeline() directly from Python

For automation or testing without the UI or CLI:

```python
from main import run_pipeline

# From an Excel file
output_csv = run_pipeline(
    mode="Upload Excel",
    uploaded_file="urls.xlsx",
    provider="ollama",
    model="qwen2.5:7b",
    temperature=0.0,
    truncation_length=8000,
)
print(f"Results saved to: {output_csv}")
```

```python
# Single URL — wrap it in a one-row DataFrame
import pandas as pd, io
from main import run_pipeline

df = pd.DataFrame({"URLs": ["https://www.pge.com/rebates"]})
buf = io.BytesIO()
df.to_excel(buf, index=False)
buf.seek(0)

output_csv = run_pipeline(
    mode="Upload Excel",
    uploaded_file=buf,
    provider="openai",
    model="gpt-4o",
    temperature=0.0,
    truncation_length=32000,
)
```

Output files (`incentives_output.csv`, `errors.csv`, `markdown_output.csv`) are written to your current working directory. The function also returns the path to the output CSV.

---

### Supercomputer / SLURM

`runjob.sh` is a pre-configured SLURM script. Edit the `--file` path and provider/model settings, then submit:

```bash
sbatch runjob.sh
```

Override the provider and model at submission time without editing the script:
```bash
INCENTIVAI_PROVIDER=anthropic INCENTIVAI_MODEL=claude-opus-4-5 sbatch runjob.sh
```

Monitor your job:
```bash
squeue -u $USER
tail -f logs/incentivai_<job_id>.out
```

The script uses `uv run python cli.py` so it does not need the venv to be activated separately.

---

## Modes

### Upload Excel

Upload a `.xlsx` file containing a column of URLs. The column can be named any of the following (case-insensitive): `url`, `urls`, `link`, `links`, `website`, `websites`.

After uploading, a column picker appears — you can select which column is the URL column and optionally select a `parent_url` column. You don't need to rename your columns beforehand.

**Example file format:**

| URLs | parent_url |
|---|---|
| https://www.pge.com/rebates | |
| https://www.pge.com/rebates/solar | https://www.pge.com/rebates |
| https://www.sce.com/incentives | |

Leave `parent_url` blank for top-level links. The pipeline will deep-crawl each URL within its own domain (up to 3 levels deep), scrape linked PDFs and Excel files, and run LLM extraction on everything it finds.

**After the run completes:**
- Download the results CSV
- Download markdown summaries as a single `.md` file
- Download the markdown summaries as a CSV
- View the error log

Results persist if you switch to another mode and come back.

---

### Single URL

Enter a single URL in the sidebar and click Run. The pipeline scrapes that URL with deep crawling enabled and runs the full extraction.

This mode is primarily for **testing** — checking that a specific utility website scrapes correctly, verifying your LLM settings, or quickly inspecting one result before running a large batch.

The URL is internally converted to a one-row Excel DataFrame and passed to the same `run_pipeline()` function as Upload Excel — so behavior is identical.

**Good uses for Single URL mode:**
- Testing a new model or temperature setting
- Checking whether a specific utility site is scrapeable
- Debugging extraction issues on a known URL
- Quick demos

---

### Upload Markdown

Upload a `.md` or `.txt` file containing pre-scraped page content and run the LLM extraction directly on it — no web scraping step.

This is useful when:
- You've already scraped a page and saved the content
- You want to test the LLM prompt on specific text
- The target site blocks automated scrapers but you can copy-paste the content manually
- You're running the extractor on content from a source that isn't a public URL

**What you get back:**
- Extracted program data as a CSV (download button)
- The extracted content as a `.md` summary file (download button)
- The original uploaded file back as a download
- A live preview of your uploaded content before running

The extracted markdown summary follows the same structure as all other modes:
```
# Program Name: ...
#Program URL: ...
## Program Details
## Eligibility
## Utility Information
```

---

### City URL Discovery

Discovers new utility website URLs across one or more U.S. states using OpenSERP. This mode does **not** run LLM extraction — it outputs a list of candidate URLs that you can then feed into Upload Excel mode.

**Requires OpenSERP running locally — see [OpenSERP Setup](#openserp-setup) before using this mode.**

**Workflow:**

```
1. Run City URL Discovery  →  downloads utility_urls_discovered_YYYY-MM-DD.xlsx
2. Use the Merge section   →  deduplicates against your existing URL database
3. Upload to Excel mode    →  run extraction on the merged list
```

**Settings:**

| Setting | Description |
|---|---|
| States | One or more U.S. states to search |
| OpenSERP URL | Where your OpenSERP server is running (default: `http://localhost:7070`) |
| Search engine | `google`, `bing`, or `duckduckgo` |
| Results per query | How many search results to pull per query (3–15) |
| Existing URL database | Optional — upload your current URL Excel to skip already-known domains |
| Search topics | Editable list of search queries — defaults cover all major utility types from the EIA-861 database |

**What gets filtered out automatically:**
Discovery results are filtered against a domain blocklist that removes aggregators (DSIRE, EnergySage, Energystar), news outlets (Reuters, Bloomberg, Forbes), government databases (EIA, NREL, EPA), and URL shorteners. Only official utility websites are kept.

**Merge section:**
After discovery, scroll down to the Merge section. Upload your existing URL database and the newly discovered file — the tool deduplicates at the domain level (not just exact URL) and produces a merged Excel with two sheets: all URLs combined, and just the new additions with full metadata.

---

## OpenSERP Setup

OpenSERP is a local search API that queries Google, Bing, or DuckDuckGo programmatically without hitting rate limits or requiring API keys. It runs as a local server on your machine and IncentivAI talks to it over `http://localhost:7070`.

City URL Discovery will not work without OpenSERP running.

---

### Option 1 — OpenSERP executable (Windows, recommended)

The project includes a pre-built `openserp.exe` in `modules/searching/`. Open a **separate terminal**, navigate to that folder, and run:

```powershell
cd modules\searching
.\openserp.exe serve
```

You should see output like:
```
Starting OpenSERP server on :7070
Listening...
```

Leave that terminal open. Start IncentivAI in a second terminal. The **OpenSERP URL** field in the UI defaults to `http://localhost:7070` — leave it as-is unless you changed the port.

You can verify it's working using the **"Check OpenSERP connection"** button in the City URL Discovery panel, or test it manually:
```powershell
curl "http://localhost:7070/google/search?text=electric+utility+rebate+Texas&limit=5"
```

You should get back a JSON array of search results.

---

### Option 2 — Docker

If you have Docker installed:

```bash
docker pull karust/openserp
docker run -p 7070:7070 karust/openserp
```

---

### Option 3 — Build from source (requires Go)

```bash
git clone https://github.com/karust/openserp.git
cd openserp
go build -o openserp
./openserp serve --port 7070
```

---

### On the supercomputer

Run OpenSERP on a login node before submitting your SLURM job:
```bash
docker run -d -p 7070:7070 karust/openserp
```

Or run it locally and forward the port over SSH:
```bash
ssh -L 7070:localhost:7070 your_netid@klone.hyak.uw.edu
```

---

## LLM Providers & Model Selection

The model you choose has a direct impact on extraction quality. The `DEFAULT_TRUNCATION_LENGTH` in `config.py` should be matched to what your model can handle — sending more text than a small model can process makes results **worse**, not better.

---

### Tier 1 — Small local models (≤10B parameters)

Examples: `qwen2.5:7b`, `llama3.2:3b`, `mistral:7b`

Runs on most laptops with 8–16GB RAM via Ollama. Good for development and testing.

- Keep truncation at or below `8000`. These models have limited context and degrade badly with more input.
- Financial details and eligibility fields are the hardest — expect some misses.
- Slower inference — give them more time by raising `LLM_TIMEOUT` in `config.py`.

```python
DEFAULT_MODEL            = "qwen2.5:7b"
DEFAULT_TRUNCATION_LENGTH = 8000
```

---

### Tier 2 — Medium local models (10B–30B parameters)

Examples: `qwen2.5:14b`, `qwen2.5:32b`, `mixtral:8x7b`

Requires 16–32GB RAM. Noticeably better extraction quality than Tier 1.

- Truncation can go up to `16000`. These models handle longer context well.
- Eligibility and financial details are much more reliable.
- Still fully local and free to run.

```python
DEFAULT_MODEL            = "qwen2.5:14b"
DEFAULT_TRUNCATION_LENGTH = 16000
```

---

### Tier 3 — Cloud models

Examples: `gpt-4o`, `gpt-4o-mini`, `claude-opus-4-5`, `gemini-1.5-pro`

Best extraction quality across the board. Confirmed working end-to-end with `gpt-4o`.

- Truncation can be set to `32000`, `64000`, or higher — GPT-4o has a 128k token context window. More context genuinely improves results here.
- Dramatically better on complex multi-program pages.
- Requires an API key and costs money per run.

```python
DEFAULT_MODEL            = "gpt-4o"
DEFAULT_TRUNCATION_LENGTH = 32000
```

---

### Provider setup

| Provider | `--provider` flag | Requires |
|---|---|---|
| Ollama (local) | `ollama` | Ollama installed + model pulled via `ollama pull <model>` |
| OpenAI | `openai` | `OPENAI_API_KEY` environment variable |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` environment variable |
| Google Gemini | `google` | `GOOGLE_API_KEY` environment variable |

---

### Recommended models by use case

| Use case | Provider | Model | Truncation |
|---|---|---|---|
| Local dev / no internet | `ollama` | `qwen2.5:7b` | `8000` |
| Best local quality | `ollama` | `qwen2.5:14b` | `16000` |
| Fast + cheap cloud | `openai` | `gpt-4o-mini` | `16000` |
| Best results / production | `openai` | `gpt-4o` | `32000+` |
| Best results / Anthropic | `anthropic` | `claude-opus-4-5` | `32000+` |

---

## Configuration

All settings live in `config.py`. You should not need to touch any other file for basic tuning.

```python
# LLM defaults
DEFAULT_PROVIDER          = "ollama"
DEFAULT_MODEL             = "llama3.2"
DEFAULT_TEMPERATURE       = 0.1
DEFAULT_TRUNCATION_LENGTH = 150000
DEFAULT_TRUNCATION        = DEFAULT_TRUNCATION_LENGTH   # alias used by app.py

# Output file names
ERRORS_CSV   = "errors.csv"
MARKDOWN_CSV = "markdown_output.csv"

# Scraper limits
MAX_RANKED_PDFS      = 3         # max PDFs to scrape per page
MAX_EXCEL_FILES      = 2         # max Excel files to download per page
MAX_EXCEL_SIZE_BYTES = 10485760  # 10 MB — skip larger Excel files
PDF_SCRAPE_TIMEOUT   = 120       # seconds before PDF scrape is abandoned

# Directories
SCRAPED_DATA_DIR    = "scraped_data"
ANALYSIS_RESULTS_DIR = "analysis_results"
```

The LLM prompts (`EXTRACTION_TEMPLATE` and `FILTER_TEMPLATE`) are also in `config.py`. Edit them there if you want to change what the LLM looks for or how it formats output — changes apply everywhere automatically.

---

## Output Files

| File | Description |
|---|---|
| `incentives_output.csv` | Main extraction results — one row per program found |
| `errors.csv` | All failed URLs with error details |
| `markdown_output.csv` | Human-readable markdown summaries per URL |
| `scraped_data/` | Raw scraped markdown files (one per crawled page) |
| `analysis_results/` | Per-domain analysis files and final filtered results |
| `utility_urls_discovered_YYYY-MM-DD.xlsx` | URLs found by City URL Discovery |

### Output CSV columns

| Column | Description |
|---|---|
| `program_name` | Full program name extracted by LLM |
| `program_url` | URL of the specific program page |
| `rebate_amounts` | Dollar amounts, percentages, and caps |
| `eligibility` | Who qualifies — customer type, equipment, geography |
| `utility_name` | Name of the utility company |
| `utility_size` | Size or type of utility (coop, municipal, IOU, etc.) |
| `source_file` | Scraped file or URL the data came from |

### Error CSV columns

| Column | Description |
|---|---|
| `url` | URL that failed |
| `error` | Full error message |

---

## Common Issues

### `ModuleNotFoundError: No module named 'modules.X'`
You're running from the wrong directory. Always run from the project root (the folder containing `app.py`):
```powershell
cd path\to\IncentivAI
uv run streamlit run app.py
```

---

### `ImportError: cannot import name 'X' from 'config'`
A name used in an import doesn't exist in `config.py`. Check that `config.py` contains `DEFAULT_TRUNCATION` (the alias), `ERRORS_CSV`, and `MARKDOWN_CSV`. These are all present in the version in this repo — if you edited `config.py` manually, compare against the original.

---

### `RequestsDependencyWarning: urllib3 does not match a supported version`
Harmless warning from the `requests<2.32.3` pin conflicting with a newer `urllib3`. The pipeline still runs correctly. To silence it:
```powershell
uv add "requests>=2.31.0"
```

---

### Streamlit crashes with `This event loop is already running`
This is a Windows-specific asyncio issue. `main.py` handles it by running all async scraping in a dedicated thread with a fresh event loop. If you're seeing this error, make sure you're using the latest `main.py` from this repo (the one with `_run_async()`).

---

### OpenSERP returns no results / connection refused
1. Make sure OpenSERP is running in a **separate** terminal before starting IncentivAI
2. Use the correct command: `.\openserp.exe serve` (not just `.\openserp.exe`)
3. Check the OpenSERP URL in the UI matches where it's actually listening (default: `http://localhost:7070`)
4. Use the **"Check OpenSERP connection"** button in the City URL Discovery panel
5. Try the manual test: `curl "http://localhost:7070/google/search?text=test&limit=3"`

---

### Ollama model not found
Make sure the model is pulled before running:
```powershell
ollama pull qwen2.5:7b
ollama list   # verify it appears
```
The model name in the UI or `--model` flag must exactly match what `ollama list` shows, including the tag (e.g. `qwen2.5:7b`, not just `qwen2.5`).

---

### PDF scraping is slow or times out
This is expected — PDFs go through Playwright's browser engine. The timeout is set to 120 seconds per PDF in `config.py` (`PDF_SCRAPE_TIMEOUT`). If PDFs are consistently failing, raise the timeout or reduce `MAX_RANKED_PDFS` to scrape fewer per page.

---

### `uv sync` fails with hatchling wheel error
Hatchling can't find a package folder named `incentivai`. Make sure `pyproject.toml` contains:
```toml
[tool.hatch.build.targets.wheel]
packages = ["."]
```

---

### No results in output CSV despite no errors
The LLM decided the scraped pages were not relevant (no concrete rebate programs found). This can mean:
- The pages are news articles, blog posts, or general info pages — correct behavior, nothing to extract
- The model is too small and hallucinating `NOT RELEVANT` — try a larger model
- `DEFAULT_TRUNCATION_LENGTH` is too low and the relevant content is being cut off — raise it
- The prompt needs tuning for your specific utility type — edit `EXTRACTION_TEMPLATE` in `config.py`

---

### Playwright browser not installed
Run this once after `uv sync`:
```powershell
uv run playwright install chromium
```

---

## Dependencies

All managed via `pyproject.toml` and installed with `uv sync`.

| Package | Purpose |
|---|---|
| `streamlit` | Web UI |
| `crawl4ai` | Web scraping with JS rendering via Playwright |
| `langchain-core` | LLM chain building |
| `langchain-ollama` | Ollama provider |
| `langchain-openai` | OpenAI provider |
| `langchain-anthropic` | Anthropic provider |
| `langchain-google-genai` | Google Gemini provider |
| `ollama` | Ollama Python client |
| `pdfplumber` | PDF text extraction |
| `pillow` + `pytesseract` | Image OCR |
| `openpyxl` | Excel read/write |
| `pandas` | DataFrame operations |
| `aiohttp` | Async HTTP for auxiliary file fetching |
| `beautifulsoup4` | HTML parsing |
| `playwright` | Browser automation for JS-heavy pages |
| `requests` | Synchronous HTTP (OpenSERP, DuckDuckGo search) |
| `lxml` | Fast HTML parsing backend |
| `tabulate` | Markdown table formatting for Excel content |

---

## Gitignore

The following are generated at runtime and should not be committed:

```
.venv/
__pycache__/
*.pyc
*.log
*.csv
.env
scraped_data/
analysis_results/
logs/
results/
```
