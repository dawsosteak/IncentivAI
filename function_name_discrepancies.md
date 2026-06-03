# Function Name Discrepancies — Memo vs Actual Codebase

## Table 1 — Full Discrepancy Table

| Name in Memo | Actual Name in Code | File | Notes |
|---|---|---|---|
| `scrape_single_link` | `scrape_all_pages()` | `scraper.py` | Top-level web scrape entry point |
| `search_topics` | `DISCOVERY_TOPICS` | `url_source.py` | Module-level constant, not a variable |
| `load_existing_domains` | `_load_existing_domains_from_excel()` | `url_source.py` | Underscore prefix, longer name |
| `run_state` | `get_urls_from_discovery()` | `url_source.py` | Handles all states, not just one |
| `load_existing_urls` | Inline in `app.py` | `app.py` | No standalone function exists |
| `load_discovered` | Inline in `app.py` | `app.py` | No standalone function exists |
| `extract_domain` | `_extract_domain()` | `url_source.py` | Underscore prefix |
| `build_merged_workbook` | `_build_merged_workbook()` | `url_source.py` | Underscore prefix |
| `TEMPLATE` | `EXTRACTION_TEMPLATE` | `processor.py` | Renamed to clarify two-stage pipeline |
| `llm_agent.py` (initial analyzer) | `processor.py` Stage 1 | `processor.py` | `llm_agent.py` is only the LLM client, not the analyzer |
| `processor.py` (filter only) | `processor.py` (both stages) | `processor.py` | Both extraction and filter live here |
| `PDF_KEYWORDS` | `PDF_SCORE_KEYWORDS` / `INCENTIVE_KEYWORDS` | `scraper.py` | Split into two separate lists |
| `results_filepaths` | In-memory string | `processor.py` | No file paths — Stage 1 output passed directly to Stage 2 in memory |
| `scraped_data/<domain>_<hash>.md` | Never written to disk | `scraper.py` | Current code is fully memory-based, no intermediate files |
| `analysis_results/` folder | Does not exist | — | Output goes to `incentives_output.csv` |
| `energy_search.py` | `url_source.py` | `url_source.py` | Standalone script, not part of the pipeline |
| `MAX_RANKED_PDFS` | Not in `config.py` | `scraper.py` | Hardcoded as `[:3]` slice in `process_auxiliary_files()` |
| `MAX_EXCEL_FILES` | Not in `config.py` | `scraper.py` | Hardcoded as `[:2]` slice |
| `MAX_EXCEL_SIZE_BYTES` | Not in `config.py` | `scraper.py` | Hardcoded as `10 * 1024 * 1024` |
| `PDF_SCRAPE_TIMEOUT` | Not in `config.py` | `scraper.py` | Hardcoded as `timeout=120` in `_scrape_pdf_with_crawl4ai()` |

---

## Table 2 — Summary Table (memo version)

| Previous Name (in memo) | Actual Name (in codebase) |
|---|---|
| `scrape_single_link()` | `scrape_all_pages()` |
| `llm_agent.py` (described as the extraction LLM) | `processor.py` — both LLM stages live here; `llm_agent.py` is only the communication layer |
| `processor.py` (described as the filter LLM only) | `processor.py` — runs **both** extraction and filter stages |
| `load_existing_urls()` | `_load_existing_domains_from_excel()` |
| `load_discovered()` | Handled inline in `app.py`, no standalone function |
| `extract_domain()` | `_extract_domain()` |
| `run_state()` | `get_urls_from_discovery()` |
| Merge module (described as separate file) | Inline in `app.py` — no separate merge file |
| `analysis_results/` folder | Does not exist — no files written to disk, all in-memory |
| `scraped_data/` folder | Does not exist — scraper returns strings, no `.md` files saved |
