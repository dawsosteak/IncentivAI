import asyncio
import contextlib
import io
import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime
from urllib.parse import urlparse

import pandas as pd
import streamlit as st


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_VERSION = "compat-2026-05-07-1"
DEFAULT_URL_COLUMN_NAMES = ("url", "urls", "link", "links", "website", "websites")
DEFAULT_MODEL_OPTIONS = {
    "ollama": ["llama3.2", "qwen2.5:14b-instruct", "mistral"],
    "openai": ["gpt-4.1", "gpt-4.1-mini", "gpt-4o-mini"],
    "uw_ssec": ['gemma-4-31b', 'olmo-3.1-32b', 'gpt-5.4-pro', 'gpt-oss-120b', 'gpt-5.3-codex', 'devstral-small', 'gpt-5.4-mini'],
    "anthropic": ["claude-sonnet-4-0", "claude-3-5-sonnet-latest"],
    "google": ["gemini-2.5-pro", "gemini-2.5-flash"],
}


class StreamlitPrintTee(io.TextIOBase):
    def __init__(self, stream, on_write):
        self.stream = stream
        self.on_write = on_write

    @property
    def encoding(self):
        return getattr(self.stream, "encoding", "utf-8")

    def writable(self):
        return True

    def write(self, text):
        self.stream.write(text)
        self.stream.flush()
        if text:
            self.on_write(text)
        return len(text)

    def flush(self):
        self.stream.flush()


class PipelineRunError(Exception):
    def __init__(self, message, log_text):
        super().__init__(message)
        self.log_text = log_text


def _find_default_url_column(columns):
    normalized = {str(col).strip().lower(): col for col in columns}
    for name in DEFAULT_URL_COLUMN_NAMES:
        if name in normalized:
            return normalized[name]
    for col in columns:
        lowered = str(col).strip().lower()
        if "url" in lowered or "link" in lowered:
            return col
    return columns[0] if len(columns) else None


def _normalize_url(value):
    if pd.isna(value):
        return ""
    url = str(value).strip()
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return url
    if parsed.netloc:
        return f"https:{url}"
    if "." in url and " " not in url:
        return f"https://{url}"
    return ""


def _default_models_for_provider(provider):
    return DEFAULT_MODEL_OPTIONS.get((provider or "").lower(), ["llama3.2"])


@st.cache_data(show_spinner=False)
def _get_ollama_models():
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=True)
    except Exception:
        return []

    models = []
    lines = result.stdout.splitlines()
    for line in lines[1:]:
        parts = line.split()
        if parts:
            models.append(parts[0])
    return models


def _run_pipeline_for_url(
    url,
    use_deep_crawl,
    provider,
    model_name,
    truncation_length,
    log_placeholder=None,
):
    from test_single_link import (
        analyze_scraped_files,
        filter_analysis_results,
        scrape_single_link,
    )

    log_chunks = []

    def append_log(text):
        log_chunks.append(text)
        if log_placeholder is not None:
            log_placeholder.text("".join(log_chunks)[-12000:])

    stdout_tee = StreamlitPrintTee(sys.stdout, append_log)
    stderr_tee = StreamlitPrintTee(sys.stderr, append_log)

    try:
        with contextlib.redirect_stdout(stdout_tee), contextlib.redirect_stderr(stderr_tee):
            scraped_files = asyncio.run(
                scrape_single_link(
                    url,
                    use_deep_crawl=use_deep_crawl,
                    truncation_length=truncation_length,
                )
            )
            analysis_files = analyze_scraped_files(scraped_files, provider=provider, model_name=model_name)
            filter_analysis_results(analysis_files, provider=provider, model_name=model_name)
    except Exception as exc:
        log_text = "".join(log_chunks)
        raise PipelineRunError(str(exc), log_text) from exc

    final_files = []
    for analysis_file in analysis_files:
        base_name = os.path.basename(analysis_file).replace("_analysis.md", "")
        final_file = os.path.join(
            os.path.dirname(analysis_file),
            f"{base_name}_FINAL_rebates.md",
        )
        if os.path.exists(final_file):
            final_files.append(final_file)

    return scraped_files, analysis_files, final_files, "".join(log_chunks)


def _build_zip(filepaths):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in filepaths:
            zf.write(path, arcname=os.path.basename(path))
    buffer.seek(0)
    return buffer


def _markdown_table(rows, columns):
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        values = []
        for column in columns:
            value = str(row.get(column, ""))
            value = value.replace("|", "\\|").replace("\n", " ")
            values.append(value)
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _caption(text):
    caption = getattr(st, "caption", None)
    if callable(caption):
        caption(text)
    else:
        st.write(text)


def _divider():
    divider = getattr(st, "divider", None)
    if callable(divider):
        divider()
    else:
        st.markdown("---")


def _expander(label, expanded=False):
    expander = getattr(st, "expander", None)
    if callable(expander):
        return expander(label, expanded=expanded)
    st.write(f"**{label}**")
    return contextlib.nullcontext()


def _download_button(label, data, file_name, mime):
    download_button = getattr(st, "download_button", None)
    if callable(download_button):
        download_button(label, data, file_name=file_name, mime=mime)
    else:
        st.info(f"Download buttons are not available in this Streamlit version: {file_name}")


try:
    st.set_page_config(page_title="Single Link Tester", layout="wide")
except TypeError:
    st.set_page_config(page_title="Single Link Tester")

st.title("Single Link Tester")
_caption("Run the existing pipeline for one URL or an Excel file of links.")
_caption(f"App version: {APP_VERSION}")

input_mode = st.radio("Input method", ["Excel upload", "Single URL", "Scraped markdown directory"], horizontal=True)
urls = []
scraped_files_dict = {}  # Maps URL to scraped files for directory mode

if input_mode == "Excel upload":
    uploaded_file = st.file_uploader("Excel file", type=["xlsx"])

    if uploaded_file:
        workbook = pd.ExcelFile(uploaded_file)
        sheet_name = st.selectbox("Sheet", workbook.sheet_names)
        df = pd.read_excel(workbook, sheet_name=sheet_name)

        if df.empty:
            st.warning("This sheet is empty.")
            st.stop()

        default_column = _find_default_url_column(df.columns)
        column_options = list(df.columns)
        default_index = column_options.index(default_column) if default_column in column_options else 0
        url_column = st.selectbox("URL column", column_options, index=default_index)

        urls = [_normalize_url(value) for value in df[url_column]]
        urls = [url for url in urls if url]
        urls = list(dict.fromkeys(urls))

        st.write(f"Found {len(urls)} valid unique URL(s).")
        with _expander("Preview URLs"):
            preview_rows = [{"url": url} for url in urls[:50]]
            st.markdown(_markdown_table(preview_rows, ["url"]))
            if len(urls) > 50:
                _caption(f"Showing the first 50 of {len(urls)} URLs.")
    else:
        st.info("Upload an Excel workbook to begin.")
elif input_mode == "Single URL":
    single_url = st.text_input("URL", placeholder="https://www.example.com/rebates")
    normalized_url = _normalize_url(single_url)

    if single_url and normalized_url:
        urls = [normalized_url]
        st.write(f"Ready to run: {normalized_url}")
    elif single_url:
        st.warning("Enter a valid URL, such as https://www.example.com/rebates.")
    else:
        st.info("Enter a URL to begin.")

elif input_mode == "Scraped markdown directory":
    directory = st.text_input("Directory path", placeholder=os.path.join(BASE_DIR, "scraped_markdown"))
    if directory and os.path.isdir(directory):
        md_files = [
            os.path.join(directory, f)
            for f in os.listdir(directory)
            if f.endswith(".md")
        ]
        if md_files:
            for md_file in md_files:
                filename = os.path.basename(md_file)
                url_part = filename.split("_scraped.md")[0]
                url = url_part.replace("_", "/").replace("~", ":")
                scraped_files_dict[url] = [md_file]
            urls = list(scraped_files_dict.keys())
            st.write(f"Found {len(urls)} URLs with scraped markdown files in the directory.")
        else:
            st.warning("No scraped markdown files found in the directory.")
    elif directory:
        st.warning("Enter a valid directory path that contains scraped markdown files.")
    else:
        st.info("Enter a directory path to begin.")

if urls:
    _divider()
    use_deep_crawl = st.checkbox("Deep crawl", value=True)
    provider = st.selectbox("LLM provider", ["ollama", "uw_ssec", "openai", "anthropic", "google"], index=0)
    model_choices = _get_ollama_models() if provider == "ollama" else _default_models_for_provider(provider)
    if provider == "ollama" and not model_choices:
        model_choices = _default_models_for_provider(provider)
    model_name = st.selectbox("Model", model_choices, index=0)
    custom_model = st.text_input("Custom model name (optional)", value="")
    model_name = custom_model.strip() or model_name
    truncation_length = st.number_input(
        "Max scrape length",
        min_value=10000,
        max_value=500000,
        value=150000,
        step=10000,
    )

    if st.button("Run Pipeline"):
        progress = st.progress(0)
        status = st.empty()
        with _expander("Live pipeline log", expanded=True):
            log_placeholder = st.empty()
        rows = []
        final_files = []
        log_text = ""

        for index, url in enumerate(urls, start=1):
            status.write(f"Running {index} of {len(urls)}: {url}")
            try:
                # Skip scraping if using directory mode
                if input_mode == "Scraped markdown directory":
                    scraped = scraped_files_dict.get(url, [])
                    log_text = f"Using pre-scraped files from directory: {scraped}"
                else:
                    scraped, _, _, _ = _run_pipeline_for_url(
                        url=url,
                        use_deep_crawl=use_deep_crawl,
                        provider=provider,
                        model_name=model_name,
                        truncation_length=int(truncation_length),
                        log_placeholder=log_placeholder,
                    )
                
                from test_single_link import analyze_scraped_files, filter_analysis_results
                
                analyzed = analyze_scraped_files(scraped, provider=provider, model_name=model_name)
                filter_analysis_results(analyzed, provider=provider, model_name=model_name)
                
                finals = []
                for analysis_file in analyzed:
                    base_name = os.path.basename(analysis_file).replace("_analysis.md", "")
                    final_file = os.path.join(
                        os.path.dirname(analysis_file),
                        f"{base_name}_FINAL_rebates.md",
                    )
                    if os.path.exists(final_file):
                        finals.append(final_file)
                
                final_files.extend(finals)
                rows.append(
                    {
                        "url": url,
                        "status": "done",
                        "scraped_files": len(scraped),
                        "analysis_files": len(analyzed),
                        "final_files": len(finals),
                        "error": "",
                    }
                )
            except Exception as exc:
                log_text = getattr(exc, "log_text", "")
                log_text = f"{log_text}\nERROR: {exc}" if log_text else str(exc)
                rows.append(
                    {
                        "url": url,
                        "status": "error",
                        "scraped_files": 0,
                        "analysis_files": 0,
                        "final_files": 0,
                        "error": str(exc),
                    }
                )

            progress.progress(int(index / len(urls) * 100))
            log_placeholder.text(log_text[-12000:] or "No log output yet.")

        status.write("Run complete.")
        results_df = pd.DataFrame(rows)
        st.subheader("Run Summary")
        st.markdown(_markdown_table(rows, list(results_df.columns)))

        csv_bytes = results_df.to_csv(index=False).encode("utf-8")
        _download_button(
            "Download run summary CSV",
            csv_bytes,
            file_name="single_link_tester_run_summary.csv",
            mime="text/csv",
        )

        unique_final_files = list(dict.fromkeys(final_files))
        if unique_final_files:
            zip_buffer = _build_zip(unique_final_files)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            _download_button(
                "Download final rebate markdown zip",
                zip_buffer,
                file_name=f"final_rebates_{stamp}.zip",
                mime="application/zip",
            )

            st.subheader("Final Results")
            for path in unique_final_files:
                with _expander(os.path.basename(path)):
                    with open(path, "r", encoding="utf-8") as f:
                        st.markdown(f.read())
        else:
            st.info("No final rebate markdown files were produced.")
