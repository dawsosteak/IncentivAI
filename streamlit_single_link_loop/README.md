# Single Link Tester

This is a standalone testing environment for the IncentivAI scraping and analysis pipeline. It is designed to test the extraction of utility rebates and incentives from a single URL using the exact workflow utilized in Kaleb's dual-script setup (`Scrapper_crawl.py` and `Analyzer_crawl.py`), but consolidated into a single convenient script.

## Prerequisites

1. **Python 3.10+**
2. **Ollama**: Must be installed and running locally to handle the LLM analysis.
   - You need the model pulled locally. The default is `llama3.2`.
   - Run `ollama pull llama3.2` if you don't have it.

## Installation

Ensure you have the required dependencies installed. You can install them via pip:

```bash
pip install -U crawl4ai pandas openpyxl beautifulsoup4 aiohttp langchain-ollama streamlit
```

*Note: Depending on your exact system, `crawl4ai` might require Playwright browser binaries to be installed (`playwright install`).*

---

## Testing Different Models on Pre-Scraped Data

If you already have scraped `.md` files in the `scraped_data/` folder and just want to test how different models perform on the same data, use the `--analyze-only` flag. This skips crawling entirely and runs only the analysis + filtering steps.

**Step 1 — Pull the model you want to test (if you haven't already):**
```bash
ollama pull <model-name>
```

**Step 2 — Run analysis with that model:**
```bash
python test_single_link.py --analyze-only --model "<model-name>"
```

**That's it.** Results will be written to `analysis_results/`.

### Model Swap Examples

| Model | Command |
|---|---|
| llama3.2 (default) | `python test_single_link.py --analyze-only --model "llama3.2"` |
| Qwen 2.5 14B | `python test_single_link.py --analyze-only --model "qwen2.5:14b-instruct"` |
| Mistral | `python test_single_link.py --analyze-only --model "mistral"` |

> **Tip:** If you only want to re-run the final cleanup/filtering pass on already-analyzed files (skipping even the first analysis pass), use `--filter-only` instead:
> ```bash
> python test_single_link.py --filter-only --model "<model-name>"
> ```

---

## Usage

### Streamlit App (Batch Excel Upload)

Run the simple frontend from this folder:

```bash
streamlit run app.py
```

Upload an Excel file, select the sheet and URL column, then click **Run Pipeline**. The app loops through each valid link using the existing `test_single_link.py` pipeline and offers the final rebate markdown files as a zip download.

### Basic Run (Scrape + Analyze)
```bash
python test_single_link.py --url "http://cpuc.ca.gov/energyefficiency/"
```

### All Options

| Flag | Description | Default |
|---|---|---|
| `--url` | URL to scrape and analyze | `http://cpuc.ca.gov/energyefficiency/` |
| `--no-deep-crawl` | Only crawl the main page, don't follow links | off |
| `--model` | Ollama model to use for analysis | `llama3.2` |
| `--analyze-only` | Skip crawling; analyze pre-scraped files in `scraped_data/` | off |
| `--filter-only` | Skip crawling + analysis; only re-run the final filter pass on `analysis_results/` | off |

### More Examples

**Shallow crawl with a specific model:**
```bash
python test_single_link.py --url "https://www.example.com/rebates" --no-deep-crawl --model "qwen2.5:14b-instruct"
```

**Analyze pre-scraped data (most common for model testing — see section above):**
```bash
python test_single_link.py --analyze-only --model "llama3.2"
```

**Re-run only the final filter pass:**
```bash
python test_single_link.py --filter-only --model "llama3.2"
```

---

## How It Works

1. **Scraping**: The script uses `crawl4ai` to fetch the HTML, PDFs, or Excel files. Deep crawling will follow relevant embedded links and dump truncated markdown chunks for each page into the `scraped_data/` folder.
2. **Analysis Pass 1**: The script iterates through all `.md` files in `scraped_data/`, interfacing with your local Ollama instance to extract structured markdown regarding program names, rebate amounts, eligibility, and utility details. It appends these findings (including "NOT RELEVANT" blocks) into a single raw markdown file per domain located in the `analysis_results/` folder (e.g., `cpuc_ca_gov_analysis.md`).
3. **Analysis Pass 2 (Filtering)**: A second LLM pass reads the raw `_analysis.md` file, discards all conversational filler and empty/irrelevant blocks, and produces a final, clean file containing strictly actionable rebates (e.g., `cpuc_ca_gov_FINAL_rebates.md`).
