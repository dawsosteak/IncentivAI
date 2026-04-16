# IncentivAI (`gio`)

Streamlit app that deep-crawls utility URLs with **crawl4ai**, then extracts structured incentive data with a local **Ollama** model.

---

## First-time setup (once per machine / new clone)

Do these in order.

### 1. Python and uv

- Install **Python 3.11+** (`python --version`).
- Install **[uv](https://docs.astral.sh/uv/)** and confirm `uv --version`.

### 2. Project dependencies

From the **`gio`** directory (this folder):

```bash
cd gio
uv sync
```

This creates `.venv` and installs Streamlit, crawl4ai, Playwright, etc.

### 3. Ollama (model + server binary)

- Install **Ollama** from [ollama.com](https://ollama.com) (app or CLI).
- Pull the model that matches **`gio/config.py`** (`MODEL_NAME`, default **`llama3.1:8b`**):

```bash
ollama pull llama3.1:8b
```

If you change `MODEL_NAME` in `config.py`, pull that tag instead.

### 4. Playwright browsers (Chromium for crawl4ai)

**Once** after `uv sync`, install Chromium using the **same** environment:

```bash
cd gio
uv run playwright install chromium
```

Do **not** point `PLAYWRIGHT_BROWSERS_PATH` at an empty folder; this project relies on Playwright’s default browser cache unless you know what you’re doing.

Re-run this step if you upgrade Playwright major versions or delete the browser cache.

---

## Every time you run the app

Two processes are required: **Ollama** and **Streamlit**. Use **two terminals** (or run Ollama in the background).

### Terminal A — Ollama API (must be running)

```bash
ollama serve
```

Leave this running. It listens on **`http://127.0.0.1:11434`** by default, which matches `OLLAMA_URL` in `gio/config.py`.

**Do not** stop this terminal with Ctrl+C while using the app unless you intend to shut Ollama down.

### Terminal B — Streamlit UI

```bash
cd gio
uv run streamlit run app.py
```

Open the URL Streamlit prints (usually `http://localhost:8501`).

---

## Input files

- **Upload Excel:** use a column named **`URLs`**, **`URLS`**, or **`url`** (case-insensitive) with one URL per row.
- **Auto search:** uses DuckDuckGo HTML; results can be noisy or blocked depending on network.

---

## Configuration (`gio/config.py`)

| Setting | Role |
|--------|------|
| `OLLAMA_URL` | Ollama HTTP API (default `http://127.0.0.1:11434`) |
| `MODEL_NAME` | Model tag for `/api/generate` (must be pulled in Ollama) |
| `DEFAULT_TRUNCATION` | Max characters of crawled text sent to the model |

---

## Troubleshooting (quick)

| Symptom | What to check |
|--------|----------------|
| Connection refused to `127.0.0.1:11434` | Start **`ollama serve`** before running the app. |
| Playwright “Executable doesn’t exist” / Chromium missing | Run **`uv run playwright install chromium`** from **`gio`**. |
| Empty or invalid JSON from the model | Ensure the pulled model matches `MODEL_NAME`; check terminal logs for raw response previews. |
