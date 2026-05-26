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
  - [CLI / Terminal](#cli--terminal)
  - [Supercomputer / SLURM](#supercomputer--slurm)
- [Modes](#modes)
  - [Upload Excel](#upload-excel)
  - [Auto Search Utilities](#auto-search-utilities)
  - [City URL Discovery](#city-url-discovery)
- [OpenSERP Setup](#openserp-setup)
- [LLM Providers](#llm-providers)
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

**UW SSEC AI Gateway:**
```bash
export UW_SSEC_AI_GATEWAY_KEY=your_key_here
export UW_SSEC_AI_GATEWAY_BASE_URL=your_base_url_here
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
| `MODEL_NAME` | `qwen2.5:7b` | `qwen2.5:14b` | `gpt-4o` via UW SSEC |
| `DEFAULT_TRUNCATION` | `5000` | `8000` | `15000` |
| `LLM_TIMEOUT` | `180` | `120` | `60` |

---

## Running the App

### Streamlit UI

```bash
streamlit run app.py
```

Opens in your browser at `http://localhost:8501`.

### CLI / Terminal

```bash
# Run on an Excel file with local Ollama
python cli.py --file urls.xlsx --provider ollama --model qwen2.5:7b

# Run with OpenAI
python cli.py --file urls.xlsx --provider openai --model gpt-4o

# Run with UW SSEC Gateway
python cli.py --file urls.xlsx --provider uw_ssec --model gpt-5.4-pro

# Auto search by state
python cli.py --state California --provider openai --model gpt-4o

# Save output to a specific directory
python cli.py --file urls.xlsx --provider uw_ssec --model gpt-5.4-pro --output /results/
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

The script sets `UW_SSEC_AI_GATEWAY_KEY` and `UW_SSEC_AI_GATEWAY_BASE_URL` from your environment — set these before submitting:
```bash
export UW_SSEC_AI_GATEWAY_KEY=your_key
export UW_SSEC_AI_GATEWAY_BASE_URL=your_url
sbatch run_job.sh
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

OpenSERP is a local search API that queries Google, Bing, or DuckDuckGo without rate limits. It is required for **City URL Discovery** mode.

### Install and run via Docker

```bash
docker pull karust/openserp
docker run -p 7070:7070 karust/openserp
```

Verify it's running:
```bash
curl "http://localhost:7070/google/search?text=electric+utility+rebate+Texas&limit=5"
```

You should get back a JSON array of search results.

### In the Streamlit UI

Set the **OpenSERP URL** field to `http://localhost:7070` (default).

### On the supercomputer

Run OpenSERP on a login node or as a background service before submitting your SLURM job:
```bash
docker run -d -p 7070:7070 karust/openserp
```

Or run it on your local machine and tunnel the port:
```bash
ssh -L 7070:localhost:7070 your_netid@klone.hyak.uw.edu
```

### Search topics

Discovery runs 20 search queries per state, targeting utility types from the EIA-861 database:
- Electric cooperatives
- Municipal utilities
- Public utility districts
- Investor-owned utilities
- Program types: solar, heat pump, EV charger, weatherization, net metering, etc.

Results are filtered against a domain blocklist that removes aggregators (DSIRE, EnergySage), news sites, and advocacy organizations — keeping only official utility websites.

---

## LLM Providers

| Provider | Flag | Requires |
|---|---|---|
| Ollama (local) | `ollama` | Ollama installed + model pulled |
| OpenAI | `openai` | `OPENAI_API_KEY` env var |
| UW SSEC Gateway | `uw_ssec` | `UW_SSEC_AI_GATEWAY_KEY` + `UW_SSEC_AI_GATEWAY_BASE_URL` |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` env var |
| Google Gemini | `google` | `GOOGLE_API_KEY` env var |

**Recommended models by use case:**

| Use case | Provider | Model |
|---|---|---|
| Local development | ollama | `qwen2.5:7b` |
| Best local quality | ollama | `qwen2.5:14b` |
| Production / best results | uw_ssec | `gpt-5.4-pro` |
| Fast + cheap | openai | `gpt-4o-mini` |

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
