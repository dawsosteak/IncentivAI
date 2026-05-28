# Single Link Tester

This is a standalone testing environment for the IncentivAI scraping and analysis pipeline. It is designed to test the extraction of utility rebates and incentives from a single URL using the exact workflow utilized in Kaleb's dual-script setup (`Scrapper_crawl.py` and `Analyzer_crawl.py`), but consolidated into a single convenient script.

## Prerequisites

1. **Python 3.10+**
2. **LLM Provider**: Ollama is the default, but you can also use OpenAI, Anthropic, or Google Gemini.
   - For Ollama, install and run it locally, then pull the model you want. The default is `llama3.2`.
   - For OpenAI, Anthropic, or Google, set the appropriate API key in your environment.
   - For UW SSEC AI Gateway, set `UW_SSEC_AI_GATEWAY_KEY` and `UW_SSEC_AI_GATEWAY_BASE_URL` in your environment.

## Installation

Ensure you have the required dependencies installed. You can install them via pip:

```bash
pip install -U crawl4ai pandas openpyxl beautifulsoup4 aiohttp langchain-ollama streamlit langchain-openai langchain-anthropic langchain-google-genai
```

*Note: Depending on your exact system, `crawl4ai` might require Playwright browser binaries to be installed (`playwright install`).*

---

## Testing Different Models on Pre-Scraped Data

If you already have scraped `.md` files in the `scraped_data/` folder and just want to test how different models perform on the same data, use the `--analyze-only` flag. This skips crawling entirely and runs only the analysis + filtering steps.

**Step 1 — Pull or configure the model you want to test (if needed):**
```bash
ollama pull <model-name>
```

**Step 2 — Run analysis with that model:**
```bash
python test_single_link.py --analyze-only --provider "ollama" --model "<model-name>"
```

**That's it.** Results will be written to `analysis_results/`.

### Model Swap Examples

| Model | Command |
|---|---|
| llama3.2 (default) | `python test_single_link.py --analyze-only --provider "ollama" --model "llama3.2"` |
| OpenAI GPT-4.1 | `python test_single_link.py --analyze-only --provider "openai" --model "gpt-4.1"` |
| UW SSEC GPT-5 Mini | `python test_single_link.py --analyze-only --provider "uw_ssec" --model "gpt-5-mini"` |
| UW SSEC Kimi K2 Thinking | `python test_single_link.py --analyze-only --provider "uw_ssec" --model "kimi-k2-thinking"` |
| Claude | `python test_single_link.py --analyze-only --provider "anthropic" --model "claude-sonnet-4-0"` |
| Gemini | `python test_single_link.py --analyze-only --provider "google" --model "gemini-2.5-pro"` |

> **Tip:** If you only want to re-run the final cleanup/filtering pass on already-analyzed files (skipping even the first analysis pass), use `--filter-only` instead:
> ```bash
> python test_single_link.py --filter-only --provider "<provider>" --model "<model-name>"
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
| `--provider` | LLM provider to use | `ollama` |
| `--model` | Model name to use for analysis | `llama3.2` |
| `--analyze-only` | Skip crawling; analyze pre-scraped files in `scraped_data/` | off |
| `--filter-only` | Skip crawling + analysis; only re-run the final filter pass on `analysis_results/` | off |

### More Examples

**Shallow crawl with a specific model:**
```bash
python test_single_link.py --url "https://www.example.com/rebates" --no-deep-crawl --provider "ollama" --model "qwen2.5:14b-instruct"
```

**Analyze pre-scraped data (most common for model testing — see section above):**
```bash
python test_single_link.py --analyze-only --provider "ollama" --model "llama3.2"
```

**Analyze pre-scraped data with the UW SSEC AI Gateway:**
```bash
export UW_SSEC_AI_GATEWAY_KEY="your-api-key"
export UW_SSEC_AI_GATEWAY_BASE_URL="https://llmaven-prod-litellm-prod.lemonmoss-19296c81.westus2.azurecontainerapps.io"
python test_single_link.py --analyze-only --provider "uw_ssec" --model "gpt-5-mini"
```

> **Note:** The gateway's `gpt-5` models require `temperature=1`; the pipeline handles this automatically for `gpt-5*` model names.

The `export` commands only apply to the current terminal session. Run them again when you open a new terminal, restart your computer, or launch Streamlit from a different environment. To use the gateway in the Streamlit interface, export the variables first, then start the app from that same terminal:

```bash
export UW_SSEC_AI_GATEWAY_KEY="your-api-key"
export UW_SSEC_AI_GATEWAY_BASE_URL="https://llmaven-prod-litellm-prod.lemonmoss-19296c81.westus2.azurecontainerapps.io"
streamlit run app.py
```

For convenience, you can add these exports to your shell profile, such as `~/.zshrc`, but that stores the key on disk. If you use a `.env` file or any local secrets file, make sure it is listed in `.gitignore` and never committed.

**Re-run only the final filter pass:**
```bash
python test_single_link.py --filter-only --provider "ollama" --model "llama3.2"
```

---

## How It Works

1. **Scraping**: The script uses `crawl4ai` to fetch the HTML, PDFs, or Excel files. Deep crawling will follow relevant embedded links and dump truncated markdown chunks for each page into the `scraped_data/` folder.
2. **Analysis Pass 1**: The script iterates through all `.md` files in `scraped_data/`, interfacing with your local Ollama instance to extract structured markdown regarding program names, rebate amounts, eligibility, and utility details. It appends these findings (including "NOT RELEVANT" blocks) into a single raw markdown file per domain located in the `analysis_results/` folder (e.g., `cpuc_ca_gov_analysis.md`).
3. **Analysis Pass 2 (Filtering)**: A second LLM pass reads the raw `_analysis.md` file, discards all conversational filler and empty/irrelevant blocks, and produces a final, clean file containing strictly actionable rebates (e.g., `cpuc_ca_gov_FINAL_rebates.md`).
