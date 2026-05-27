# IncentivAI

A pipeline for discovering and extracting structured data from utility company energy incentive programs.
Supports three modes: **URL Discovery** (find new utility websites), **Incentive Extraction** (scrape and extract program data), and **Database Merging** (consolidate discovered URLs).

---

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Setup](#setup)
- [Configuration](#configuration)
- [Running the App](#running-the-app)
  - [Streamlit UI](#streamlit-ui)
  - [Running the Pipeline Directly (Terminal)](#running-the-pipeline-directly-terminal)
  - [CLI / Terminal](#cli--terminal)
  - [Supercomputer / SLURM](#supercomputer--slurm)
- [Modes](#modes)
  - [Upload Excel](#upload-excel)
  - [Auto Search Utilities](#auto-search-utilities)
  - [City URL Discovery](#city-url-discovery)
- [OpenSERP Setup](#openserp-setup)
- [LLM Providers & Model Selection](#llm-providers--model-selection)
- [Output Files](#output-files)
- [Dependencies](#dependencies)

---

## Overview

IncentivAI scrapes utility company websites and uses an LLM to extract structured incentive program data including program names, financial details, eligibility requirements, application processes, and more.

The pipeline has three stages:
1. **Discover** — find utility website URLs by state using OpenSERP
2. **Extract** — scrape each URL and run LLM extraction
3. **Export** — output structured CSV with one row per program found

---

## Project Structure

```
IncentivAI/
├── app.py                  ← Streamlit UI entry point
├── cli.py                  ← Terminal / supercomputer entry point
├── main.py                 ← Shared pipeline logic
├── config.py               ← All configuration constants
├── modules/
│   ├── url_source.py       ← URL loading, discovery, and merging
│   ├── scraper.py          ← Web, PDF, Excel, and image scraping
│   ├── processor.py        ← LLM prompt building and extraction
│   ├── llm_agent.py        ← Multi-provider LLM client
│   └── exporter.py         ← CSV and markdown output
├── utils/
│   └── logger.py           ← Shared logger
├── slurm/
│   └── run_job.sh          ← SLURM batch job script
└── logs/                   ← Runtime logs (gitignored)
```

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/your-org/IncentivAI.git
cd IncentivAI
```

### 2. Install dependencies

This project uses `uv` for package management:

```bash
pip install uv
uv sync
```

### 3. Install Playwright browsers

crawl4ai requires Playwright for JavaScript rendering:

```bash
uv run playwright install chromium
```

### 4. Install Tesseract (for image OCR)

**Windows:**
Download and install from [github.com/UB-Mannheim/tesseract/wiki](https://github.com/UB-Mannheim/tesseract/wiki) and add to PATH.

**Linux / supercomputer:**
```bash
sudo apt install tesseract-ocr
# or via module system:
module load tesseract
```

### 5. Set up your LLM

**Local Ollama:**
```bash
# Install Ollama from https://ollama.com
ollama pull qwen2.5:7b
```

**OpenAI / Anthropic / Google:**
Set the relevant API key as an environment variable:
```bash
export OPENAI_API_KEY=your_key_here
export ANTHROPIC_API_KEY=your_key_here
export GOOGLE_API_KEY=your_key_here
```

---

## Configuration

All settings are in `config.py`:

```python
MODEL_NAME          = "qwen2.5:7b"   # LLM model to use
DEFAULT_TEMPERATURE = 0.0             # 0.0 = most deterministic
DEFAULT_TRUNCATION  = 8000            # max chars of scraped content sent to LLM
MAX_RETRIES         = 2               # LLM retry attempts on JSON parse failure
LLM_TIMEOUT         = 120             # seconds before LLM call is killed
ERRORS_CSV          = "errors.csv"
MARKDOWN_CSV        = "markdown_output.csv"
```

**Tuning for your machine:**

| Setting | Small laptop | Gaming laptop | Supercomputer |
|---|---|---|---|
| `MODEL_NAME` | `qwen2.5:7b` | `qwen2.5:14b` | `gpt-4o` |
| `DEFAULT_TRUNCATION` | `5000` | `8000` | `32000+` |
| `LLM_TIMEOUT` | `180` | `120` | `60` |

---

## Running the App

### Streamlit UI

```bash
streamlit run app.py
```

Opens in your browser at `http://localhost:8501`.

---

### Running the Pipeline Directly (Terminal)

If you don't need the UI, you can run the pipeline straight from the terminal using `main.py`. This is useful for automation, testing, or running on a server without a browser.

**Activate your venv first:**
```bash
# Windows
.\.venv\Scripts\activate

# Mac / Linux
source .venv/bin/activate
```

**Basic usage — Excel file with Ollama:**
```bash
python -c "
from main import run_pipeline
run_pipeline(
    mode='Upload Excel',
    uploaded_file='urls.xlsx',
    provider='ollama',
    model='qwen2.5:7b',
    temperature=0.0,
    truncation_length=8000,
)
"
```

**With OpenAI (GPT-4o):**
```bash
python -c "
from main import run_pipeline
run_pipeline(
    mode='Upload Excel',
    uploaded_file='urls.xlsx',
    provider='openai',
    model='gpt-4o',
    temperature=0.0,
    truncation_length=32000,
)
"
```

**Quick one-liner for a single URL:**
```bash
python -c "
import pandas as pd, io
from main import run_pipeline

df = pd.DataFrame({'URLs': ['https://www.pge.com/rebates']})
buf = io.BytesIO()
df.to_excel(buf, index=False)
buf.seek(0)

run_pipeline(
    mode='Upload Excel',
    uploaded_file=buf,
    provider='ollama',
    model='qwen2.5:7b',
    temperature=0.0,
    truncation_length=8000,
)
"
```

Output files (`incentives_output.csv`, `errors.csv`, `markdown_output.csv`) will be written to your current working directory.

---

### CLI / Terminal

```bash
# Run on an Excel file with local Ollama
python cli.py --file urls.xlsx --provider ollama --model qwen2.5:7b

# Run with OpenAI
python cli.py --file urls.xlsx --provider openai --model gpt-4o

# Auto search by state
python cli.py --state California --provider openai --model gpt-4o

# Save output to a specific directory
python cli.py --file urls.xlsx --provider openai --model gpt-4o --output /results/
```

**All CLI options:**

| Flag | Description | Default |
|---|---|---|
| `--file` | Path to Excel file with URLs column | — |
| `--state` | State name for auto search mode | — |
| `--provider` | LLM provider | `ollama` |
| `--model` | Model name | from `config.py` |
| `--temperature` | LLM temperature | `0.0` |
| `--truncation` | Max scrape length | `8000` |
| `--output` | Output directory | current directory |
| `--output-name` | Output CSV filename | `incentives_output.csv` |

### Supercomputer / SLURM

Edit `slurm/run_job.sh` to set your Excel file path and model, then submit:

```bash
cd slurm
sbatch run_job.sh
```

Monitor your job:
```bash
squeue -u $USER
tail -f logs/incentivai_<job_id>.out
```

---

## Modes

### Upload Excel

Upload an `.xlsx` file with a column named `URLs`. Optionally include a `parent_url` column to pre-define parent/child relationships.

| URLs | parent_url |
|---|---|
| https://www.pge.com/rebates | |
| https://www.pge.com/rebates/solar | https://www.pge.com/rebates |

Leave `parent_url` blank for main links.

### Auto Search Utilities

Enter a U.S. state name and the pipeline will search DuckDuckGo for utility company pages in that state and run extraction on the top results.

### City URL Discovery

Discovers new utility website URLs by state using OpenSERP. This mode does **not** run extraction — it outputs a list of URLs that can then be fed into the extraction pipeline.

Requires OpenSERP running locally — see [OpenSERP Setup](#openserp-setup).

**Workflow:**
1. Run **City URL Discovery** to find new utility URLs → downloads Excel file
2. Use **Merge Database** to deduplicate and merge into your existing URL database
3. Upload the merged database to **Upload Excel** mode to run extraction

---

## OpenSERP Setup

OpenSERP is a local search API that lets you query Google, Bing, or DuckDuckGo programmatically without hitting rate limits or needing API keys. It runs as a local server on your machine and IncentivAI talks to it over `http://localhost:7070`.

### What it does

When City URL Discovery runs, it sends search queries like `"electric utility rebate programs Texas"` to OpenSERP, which performs the actual web search and returns structured JSON results. IncentivAI then filters those results down to real utility websites, strips out aggregators and news sites, and saves the URLs for extraction.

Without OpenSERP running, City URL Discovery will not work.

---

### Option 1 — OpenSERP executable (recommended for Windows)

One of the project contributors built and tested a working OpenSERP executable that runs directly without Docker or Go installation. This is the easiest option on Windows.

**To run it:**
```bash
# Navigate to wherever openserp.exe is located, then:
python openserp.exe
```

> **Note:** The exact command may vary depending on how the executable was built.
> The server should start up in your terminal with a blue output indicating it's running.
> Once you see it listening, leave that terminal open and start IncentivAI in a separate terminal.

When it's running you should see something like:
```
Starting OpenSERP server on :7070
Listening...
```

Set the **OpenSERP URL** field in the Streamlit UI to `http://localhost:7070` (this is the default).

> **TODO:** Update this section with the exact run command once confirmed.

---

### Option 2 — Docker

If you have Docker installed, this is the most reliable cross-platform option:

```bash
docker pull karust/openserp
docker run -p 7070:7070 karust/openserp
```

Verify it's running:
```bash
curl "http://localhost:7070/google/search?text=electric+utility+rebate+Texas&limit=5"
```

You should get back a JSON array of search results.

---

### Option 3 — Build from source

If you have Go installed:
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

Or run it on your local machine and tunnel the port:
```bash
ssh -L 7070:localhost:7070 your_netid@klone.hyak.uw.edu
```

---

### Search topics

Discovery runs search queries per state targeting utility types from the EIA-861 database:
- Electric cooperatives
- Municipal utilities
- Public utility districts
- Investor-owned utilities
- Program types: solar, heat pump, EV charger, weatherization, net metering, etc.

Results are filtered against a domain blocklist that removes aggregators (DSIRE, EnergySage), news sites, and advocacy organizations — keeping only official utility websites.

---

## LLM Providers & Model Selection

The model you choose has a **direct impact on extraction quality**, and the `DEFAULT_TRUNCATION` setting in `config.py` should be matched to what your model can actually handle. Sending more text than a small model can process doesn't improve results — it actively makes them worse. Larger models genuinely benefit from more context.

---

### Tier 1 — Small local models (sub-10B parameters)

Examples: `qwen2.5:7b`, `llama3.2:3b`, `mistral:7b`

These run on most laptops with 8–16GB RAM via Ollama. They work, but have real limitations:

- **Stay at or below `8000` truncation.** These models have limited context windows and degrade noticeably when given more text than they can handle — you'll get hallucinated values, missed fields, and malformed JSON. More text is not better here.
- Financial details and eligibility fields are the hardest for small models — expect some misses.
- Best used for development, testing, and running the pipeline when no internet or API access is available.

```python
# config.py for small models
MODEL_NAME         = "qwen2.5:7b"
DEFAULT_TRUNCATION = 8000
LLM_TIMEOUT        = 180   # small models are slower, give them more time
```

---

### Tier 2 — Medium local models (10B–30B parameters)

Examples: `qwen2.5:14b`, `qwen2.5:32b`, `mixtral:8x7b`

Require a gaming laptop or workstation with 16–32GB RAM. Noticeably better extraction quality:

- **Push truncation to `12000`–`16000`.** These models handle longer context well and will catch financial details that smaller models miss.
- Field extraction is significantly more reliable, especially for eligibility and application process.
- Still slower than cloud models but fully local and free to run.

```python
# config.py for medium models
MODEL_NAME         = "qwen2.5:14b"
DEFAULT_TRUNCATION = 16000
LLM_TIMEOUT        = 120
```

---

### Tier 3 — Large cloud models (GPT-4o, Claude, Gemini)

Examples: `gpt-4o`, `gpt-4o-mini`, `claude-3-5-sonnet`, `gemini-1.5-pro`

This is where the pipeline really performs. Confirmed working end-to-end with GPT-4o.

- **Push truncation as high as you want** — GPT-4o has a 128k token context window. Set `DEFAULT_TRUNCATION` to `32000`, `64000`, or higher. More page content = better extraction, especially for complex multi-program pages.
- Extraction quality is dramatically better across all fields, especially financial details.
- Requires an API key and costs money per run — budget accordingly for large batches.
- Fastest wall-clock time despite being remote, since inference is done on powerful hardware.

```python
# config.py for cloud models
MODEL_NAME         = "gpt-4o"
DEFAULT_TRUNCATION = 32000   # or higher — GPT-4o can handle it
LLM_TIMEOUT        = 60
```

---

### Provider setup

| Provider | Flag | Requires |
|---|---|---|
| Ollama (local) | `ollama` | Ollama installed + model pulled via `ollama pull <model>` |
| OpenAI | `openai` | `OPENAI_API_KEY` environment variable |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` environment variable |
| Google Gemini | `google` | `GOOGLE_API_KEY` environment variable |

**Any model available in Ollama works** — just run `ollama pull <model-name>` and use that exact name (including the tag) in `config.py` or the model name field in the UI. Run `ollama list` to see what you have installed.

---

### Recommended models by use case

| Use case | Provider | Model | Truncation |
|---|---|---|---|
| Local dev / no internet | ollama | `qwen2.5:7b` | `8000` |
| Best local quality | ollama | `qwen2.5:14b` | `16000` |
| Fast + cheap cloud | openai | `gpt-4o-mini` | `16000` |
| Best results / production | openai | `gpt-4o` | `32000+` |

---

## Output Files

| File | Description |
|---|---|
| `incentives_output.csv` | Main extraction results, one row per program |
| `errors.csv` | All failed URLs with stage, reason, and error detail |
| `markdown_output.csv` | Human-readable markdown summaries per URL |
| `utility_urls_discovered.xlsx` | URLs found by City URL Discovery |

### Output CSV columns

| Column | Description |
|---|---|
| `link_type` | `Main Link` or `Sublink` |
| `parent_url` | Parent URL if sublink |
| `source_url` | URL that was scraped |
| `url_type` | `web`, `pdf`, `excel`, or `image` |
| `utility_company` | Name of the utility |
| `program_name` | Full program name |
| `program_type` | Rebate, grant, tax credit, loan, etc. |
| `financial_details` | Dollar amounts, percentages, caps |
| `eligibility` | Who qualifies |
| `application_process` | How to apply |
| `sector` | Residential, Commercial, Industrial, Agricultural |
| `notes` | Expiration dates, caveats, stacking rules |
| `summary_of_page` | One-sentence page summary |
| `extraction_timestamp` | When this URL was processed |

### Error CSV columns

| Column | Description |
|---|---|
| `timestamp` | When the error occurred |
| `url` | URL that failed |
| `url_type` | web / pdf / excel / image |
| `stage` | scraping / llm_parsing / llm_timeout / llm_extraction |
| `reason` | Short human-readable reason |
| `detail` | Full error message |

---

## Dependencies

All managed via `pyproject.toml` and installed with `uv sync`.

Key packages:
- `streamlit` — web UI
- `crawl4ai` — web scraping with JS rendering
- `ollama` — local LLM client
- `langchain-openai`, `langchain-anthropic`, `langchain-google-genai` — cloud LLM providers
- `pdfplumber` — PDF text extraction
- `openpyxl` — Excel read/write
- `pillow` + `pytesseract` — image OCR
- `aiohttp` — async HTTP for auxiliary file fetching
- `beautifulsoup4` — HTML parsing
- `playwright` — browser automation for JS-heavy pages

---

## Gitignore

The following are generated at runtime and should not be committed:

```
logs/
*.csv
*.log
.env
__pycache__/
.venv/
scraped_data/
analysis_results/
```
