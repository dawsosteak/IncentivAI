# IncentivAI Pipeline

This repo contains a Streamlit and terminal wrapper around the IncentivAI URL scraping, rebate analysis, URL discovery, and URL database merge workflow.

The main entrypoint is `app.py`. It can run as:

- A Streamlit app with selectable modes.
- A terminal CLI using labeled arguments such as `--mode`, `--url`, `--provider`, and `--crawl-depth`.

The underlying worker scripts are still available:

- `test_single_link.py`: scrape, analyze, and filter rebate results.
- `Searching/energy_search.py`: discover utility URLs through OpenSERP.
- `Searching/merge_urls.py`: merge discovered URLs into an existing database.

## 1. Prerequisites

Install these first:

- Python 3.11 or newer
- `uv`
- An LLM provider
- Optional: Docker, if you want to use URL Discovery through OpenSERP

Check Python:

```bash
python3 --version
```

Install `uv` if you do not already have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Restart your terminal after installing `uv`, then check:

```bash
uv --version
```

## 2. Create The uv Environment

From the repo root:

```bash
cd /Users/gio/github/IncentivAI/incentivai_g1
uv sync
```

This creates or updates `.venv/` from `pyproject.toml` and `uv.lock`.

If `crawl4ai` or Playwright reports missing browser binaries during a crawl, run:

```bash
uv run python -m playwright install chromium
```

You do not need to manually activate the virtual environment if you use `uv run ...`.

Optional activation:

```bash
source .venv/bin/activate
```

## 3. Configure An LLM Provider

### Ollama

Ollama is the default provider.

Install Ollama separately, start it, then pull the default model:

```bash
ollama pull llama3.2
```

Run a quick model check:

```bash
ollama list
```

### UW SSEC AI Gateway

Set both environment variables in the same terminal where you run Streamlit or CLI commands:

```bash
export UW_SSEC_AI_GATEWAY_KEY="your-api-key"
export UW_SSEC_AI_GATEWAY_BASE_URL="https://your-gateway-base-url"
```

Then use:

```bash
--provider uw_ssec --model-name gpt-5.4-mini
```

### OpenAI

```bash
export OPENAI_API_KEY="your-api-key"
```

Then use:

```bash
--provider openai --model-name gpt-4.1-mini
```

### Anthropic And Google

The code supports these providers if the corresponding LangChain packages and API keys are available in your environment:

```bash
export ANTHROPIC_API_KEY="your-api-key"
export GOOGLE_API_KEY="your-api-key"
```

If you plan to use these providers and the imports are missing, add the optional packages:

```bash
uv add langchain-anthropic langchain-google-genai
```

## 4. Run Through Streamlit

Start the app:

```bash
uv run streamlit run app.py
```

If your shell has an old or broken `streamlit` executable, use:

```bash
uv run python -m streamlit run app.py
```

Then open the local URL printed by Streamlit, usually:

```text
http://localhost:8501
```

### Streamlit Modes

The Streamlit app has five modes:

| Mode | What it does |
|---|---|
| `Excel upload` | Upload an Excel workbook, choose the sheet and URL column, then run the scrape/analyze/filter pipeline on each URL. |
| `Single URL` | Run the pipeline on one URL. |
| `Scraped markdown directory` | Skip scraping and analyze existing `.md` files from a directory. |
| `URL Discovery` | Search OpenSERP for utility URLs by state and write discovered URLs to an Excel workbook. |
| `Merge Database` | Merge discovered URLs into an existing URL database with domain-level deduplication. |

For pipeline modes, set:

- **Deep crawl**: enabled by default.
- **Crawl depth**: default is `3`.
- **LLM provider**: default is `ollama`.
- **Model**: default is `llama3.2`.
- **Max scrape length**: default is `150000`.

For `URL Discovery`, start OpenSERP first. If you use the Docker command in this README, set the Streamlit **OpenSERP URL** field to:

```text
http://localhost:7000
```

## 5. Run Through Terminal

Use `app.py` with `--mode`.

Show all CLI options:

```bash
uv run python app.py --help
```

### Single URL

```bash
uv run python app.py \
  --mode single-url \
  --url "https://www.example.com/rebates" \
  --provider ollama \
  --model-name llama3.2 \
  --crawl-depth 3 \
  --truncation-length 150000 \
  --summary-csv run_summary.csv
```

Use a shallow crawl:

```bash
uv run python app.py \
  --mode single-url \
  --url "https://www.example.com/rebates" \
  --no-deep-crawl
```

### Excel Upload Mode From Terminal

This runs the same batch pipeline as the Streamlit Excel upload mode:

```bash
uv run python app.py \
  --mode excel-upload \
  --excel-file "Searching/Relevant_URLs.xlsx" \
  --sheet "All URLs" \
  --url-column "Program Source URLs" \
  --provider ollama \
  --model-name llama3.2 \
  --crawl-depth 3 \
  --summary-csv excel_run_summary.csv
```

If you omit `--sheet`, the first sheet is used.

If you omit `--url-column`, the app tries to detect a URL/link column.

### Scraped Markdown Directory Mode

Use this when you already have scraped markdown files and only want to run analysis and filtering:

```bash
uv run python app.py \
  --mode scraped-markdown-directory \
  --directory "scraped_data" \
  --provider ollama \
  --model-name llama3.2 \
  --summary-csv markdown_run_summary.csv
```

### URL Discovery Mode

URL Discovery requires an OpenSERP server.

Start OpenSERP with Docker:

```bash
docker run -p 127.0.0.1:7000:7000 -it karust/openserp serve -a 0.0.0.0 -p 7000
```

Leave that running, then in a second terminal run:

```bash
cd /Users/gio/github/IncentivAI/incentivai_g1
uv run python app.py \
  --mode url-discovery \
  --states Texas California \
  --openserp-url "http://localhost:7000" \
  --engine google \
  --results-per-query 8 \
  --database-file "Searching/Relevant_URLs.xlsx" \
  --output-file "Searching/utility_urls_discovered.xlsx"
```

Use custom search topics by repeating `--topic`:

```bash
uv run python app.py \
  --mode url-discovery \
  --states Texas \
  --openserp-url "http://localhost:7000" \
  --topic "electric cooperative rebate incentive program" \
  --topic "municipal electric utility solar rebate"
```

If `--database-file` is provided, discovered domains already present in that workbook are skipped.

### Merge Database Mode

This merges discovered URLs into an existing URL workbook by domain.

It does not overwrite your database unless you explicitly choose the same output path.

```bash
uv run python app.py \
  --mode merge-database \
  --database-file "Searching/Relevant_URLs.xlsx" \
  --discovered-file "Searching/utility_urls_discovered.xlsx" \
  --output-file "Searching/Relevant_URLs_merged.xlsx"
```

The output workbook contains:

- `All URLs`: original URLs plus new URLs.
- `New URLs`: only the newly added URL rows with metadata.

## 6. Direct Worker Script Usage

You can still run the single-link worker directly.

```bash
uv run python test_single_link.py \
  --url "https://www.example.com/rebates" \
  --provider ollama \
  --model llama3.2 \
  --crawl-depth 3
```

Analyze already-scraped files in `scraped_data/`:

```bash
uv run python test_single_link.py \
  --analyze-only \
  --provider ollama \
  --model llama3.2
```

Re-run only the final filter pass on `analysis_results/`:

```bash
uv run python test_single_link.py \
  --filter-only \
  --provider ollama \
  --model llama3.2
```

## 7. Outputs

Pipeline runs write to:

| Path | Description |
|---|---|
| `scraped_data/` | Markdown files produced by crawling. |
| `analysis_results/` | Raw `_analysis.md` files and final `_FINAL_rebates.md` files. |
| `run_summary.csv` or your `--summary-csv` path | Optional terminal run summary. |
| `Searching/utility_urls_discovered.xlsx` | Default URL Discovery output. |
| `Searching/Relevant_URLs_merged.xlsx` | Example merged URL database output. |

## 8. Common Problems

### `ModuleNotFoundError`

Run commands through `uv`:

```bash
uv run python app.py --help
```

If dependencies are missing, sync again:

```bash
uv sync
```

### Missing browser binaries

```bash
uv run python -m playwright install chromium
```

### Streamlit command points to the wrong Python

Use:

```bash
uv run python -m streamlit run app.py
```

### Ollama model not found

Pull the model:

```bash
ollama pull llama3.2
```

### OpenSERP connection errors

Confirm Docker is running and OpenSERP is listening:

```bash
docker run -p 127.0.0.1:7000:7000 -it karust/openserp serve -a 0.0.0.0 -p 7000
```

Then pass the same URL to the app:

```bash
--openserp-url "http://localhost:7000"
```

## 9. Defaults

| Setting | Default |
|---|---|
| LLM provider | `ollama` |
| Model | `llama3.2` |
| Deep crawl | enabled |
| Crawl depth | `3` |
| Max scrape length | `150000` |
| URL Discovery engine | `google` |
| URL Discovery results per query | `8` |
