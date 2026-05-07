import asyncio
import contextlib
import io
import os
import zipfile
from datetime import datetime
from urllib.parse import urlparse

import pandas as pd
import streamlit as st


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_VERSION = "compat-2026-05-07-1"
DEFAULT_URL_COLUMN_NAMES = ("url", "urls", "link", "links", "website", "websites")


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


def _run_pipeline_for_url(url, use_deep_crawl, model_name, truncation_length):
    from test_single_link import (
        analyze_scraped_files,
        filter_analysis_results,
        scrape_single_link,
    )

    scraped_files = asyncio.run(
        scrape_single_link(
            url,
            use_deep_crawl=use_deep_crawl,
            truncation_length=truncation_length,
        )
    )
    analysis_files = analyze_scraped_files(scraped_files, model_name=model_name)
    filter_analysis_results(analysis_files, model_name=model_name)

    final_files = []
    for analysis_file in analysis_files:
        base_name = os.path.basename(analysis_file).replace("_analysis.md", "")
        final_file = os.path.join(
            os.path.dirname(analysis_file),
            f"{base_name}_FINAL_rebates.md",
        )
        if os.path.exists(final_file):
            final_files.append(final_file)

    return scraped_files, analysis_files, final_files, ""


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
_caption("Upload an Excel file of links and run the existing pipeline over each URL.")
_caption(f"App version: {APP_VERSION}")

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

    _divider()
    use_deep_crawl = st.checkbox("Deep crawl", value=True)
    model_name = st.text_input("Ollama model", value="llama3.2")
    truncation_length = st.number_input(
        "Max scrape length",
        min_value=10000,
        max_value=500000,
        value=150000,
        step=10000,
    )

    if urls and st.button("Run Pipeline"):
        progress = st.progress(0)
        status = st.empty()
        rows = []
        final_files = []

        for index, url in enumerate(urls, start=1):
            status.write(f"Running {index} of {len(urls)}: {url}")
            try:
                scraped, analyzed, finals, log_text = _run_pipeline_for_url(
                    url=url,
                    use_deep_crawl=use_deep_crawl,
                    model_name=model_name,
                    truncation_length=int(truncation_length),
                )
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
                log_text = str(exc)
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
            with _expander("Latest pipeline log", expanded=False):
                st.text(log_text[-12000:])

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
else:
    st.info("Upload an Excel workbook to begin.")
