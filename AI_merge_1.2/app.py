import csv
import io
import os
import sys
import threading
import time
import zipfile

import pandas as pd
import streamlit as st

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from main import run_pipeline
from config import (
    DEFAULT_TEMPERATURE,
    DEFAULT_TRUNCATION,
    DEFAULT_USE_DEEP_CRAWL,
    DEFAULT_DEEP_CRAWL_TIMEOUT_SEC,
    UI_POLL_INTERVAL_SEC,
    CANCEL_BUTTON_LABEL,
    ERRORS_CSV,
    MARKDOWN_CSV,
    MODEL_NAME,
    OLLAMA_MODEL_PRESETS,
    DEFAULT_MAX_DEPTH
)


def _streamlit_rerun():
    rerun = getattr(st, "rerun", None)
    if callable(rerun):
        rerun()
        return
    experimental = getattr(st, "experimental_rerun", None)
    if callable(experimental):
        experimental()
        return
    raise RuntimeError("Upgrade Streamlit to at least 1.11 for rerun support.")


st.set_page_config(page_title="IncentivAI", layout="wide")
st.title("IncentivAI – Utility Incentive Extractor")

if "pipeline_running" not in st.session_state:
    st.session_state.pipeline_running = False
if "pipeline_done" not in st.session_state:
    st.session_state.pipeline_done = False
if "pipeline_csv_path" not in st.session_state:
    st.session_state.pipeline_csv_path = None
if "pipeline_done_error" not in st.session_state:
    st.session_state.pipeline_done_error = None
if "pipeline_done_cancelled" not in st.session_state:
    st.session_state.pipeline_done_cancelled = False
if "last_run_markdown_enabled" not in st.session_state:
    st.session_state.last_run_markdown_enabled = True
if "last_run_raw_scrape_enabled" not in st.session_state:
    st.session_state.last_run_raw_scrape_enabled = False
if "last_run_raw_scrape_zip_path" not in st.session_state:
    st.session_state.last_run_raw_scrape_zip_path = None

if st.session_state.pipeline_done:
    err = st.session_state.pipeline_done_error
    path = st.session_state.pipeline_csv_path
    cancelled = st.session_state.pipeline_done_cancelled
    if err is not None:
        st.error(f"Extraction failed: {err}")
    elif path:
        if cancelled:
            st.warning("Extraction cancelled. Download contains partial results.")
        else:
            st.success("Extraction complete.")
        with open(path, "rb") as f:
            st.download_button(
                "Download CSV",
                f,
                file_name="incentives_output.csv",
                key="download_csv_completed",
            )
    st.markdown("---")

st.sidebar.header("Configuration")
mode = st.sidebar.radio(
    "Select URL Source Mode",
    ["Upload Excel", "Auto Search Utilities"],
)

uploaded_file = None
state_input = None
if mode == "Upload Excel":
    uploaded_file = st.sidebar.file_uploader(
        "Upload Excel (.xlsx) with column 'URLs' or 'URLS' (or 'url')",
        type=["xlsx"],
    )
else:
    state_input = st.sidebar.text_input("Enter State (e.g., California)")

st.sidebar.subheader("LLM")
_presets = list(OLLAMA_MODEL_PRESETS)
_default_model_idx = (
    _presets.index(MODEL_NAME) if MODEL_NAME in _presets else 0
)
model_preset = st.sidebar.selectbox(
    "Ollama model",
    options=_presets,
    index=_default_model_idx,
    help="Default matches Dawson (qwen2.5:14b). Pick Custom to type any tag from `ollama list`.",
)
custom_model_name = ""
if model_preset == "Custom…":
    custom_model_name = st.sidebar.text_input(
        "Custom model name",
        value="",
        placeholder="e.g. mistral-small:22b",
    )

temperature = st.sidebar.number_input("Temperature", value=DEFAULT_TEMPERATURE, step=0.1)
truncation_length = st.sidebar.number_input("Max Scrape Length", value=DEFAULT_TRUNCATION)
use_deep_crawl = st.sidebar.checkbox(
    "Deep crawl (multi-page)",
    value=DEFAULT_USE_DEEP_CRAWL,
    help="When off, only the seed page is fetched (faster; may miss linked detail pages).",
)
max_depth = st.sidebar.number_input(
    "Max depth",
    min_value=0,
    max_value=5,
    value=DEFAULT_MAX_DEPTH,
    step=1,
    disabled=not use_deep_crawl,
    help="Best-first crawl depth. Higher can find more detail pages but is slower/noisier.",
)
deep_crawl_timeout_sec = st.sidebar.number_input(
    "Deep crawl timeout (seconds)",
    min_value=30,
    max_value=600,
    value=DEFAULT_DEEP_CRAWL_TIMEOUT_SEC,
    step=30,
    disabled=not use_deep_crawl,
    help="Max time for the full multi-page crawl before falling back to a single page.",
)

generate_markdown = st.sidebar.checkbox(
    "Generate markdown summaries",
    value=True,
    help="When enabled, writes markdown_output.csv after each URL and fills the Live Summaries tab.",
)

write_raw_scrapes = st.sidebar.checkbox(
    "Save raw scraped markdown (pre-LLM)",
    value=False,
    help="Writes raw scraped text to AI_merge/raw_scrapes/ as .md files for troubleshooting.",
)

run_button = st.sidebar.button(
    "Run Extraction",
    disabled=st.session_state.pipeline_running,
)

tab_progress, tab_markdown, tab_errors = st.tabs(["Progress", "Live Summaries", "Errors"])

if st.session_state.pipeline_done and not st.session_state.pipeline_running:
    with tab_progress:
        st.info("Last run finished. Use the download button above or review summaries and errors in the other tabs.")
        if st.session_state.last_run_raw_scrape_enabled:
            raw_dir = os.path.join(_BASE_DIR, "raw_scrapes")
            st.caption(f"Raw scrapes directory: `{raw_dir}`")
            zip_path = st.session_state.last_run_raw_scrape_zip_path
            if zip_path and os.path.isfile(zip_path):
                with open(zip_path, "rb") as f:
                    st.download_button(
                        "Download Raw Scrapes (zip)",
                        f,
                        file_name="raw_scrapes.zip",
                        key="dl_raw_scrapes_zip_last",
                    )

    with tab_markdown:
        st.subheader("Markdown summaries (last run)")
        if not st.session_state.last_run_markdown_enabled:
            st.info(
                "Markdown was turned off for the last run. Enable **Generate markdown summaries** "
                "in the sidebar before the next extraction to populate this tab."
            )
        elif os.path.isfile(MARKDOWN_CSV):
            try:
                md_df = pd.read_csv(
                    MARKDOWN_CSV,
                    quoting=csv.QUOTE_ALL,
                    on_bad_lines="skip",
                )
                for _, row in md_df.iterrows():
                    st.markdown(row["markdown_summary"])
                    st.divider()
                with open(MARKDOWN_CSV, "rb") as f:
                    st.download_button(
                        "Download Markdown CSV",
                        f,
                        file_name="markdown_summaries.csv",
                        key="dl_md_hist",
                    )
            except Exception as e:
                st.error(f"Could not load markdown summaries: {e}")
        elif st.session_state.last_run_markdown_enabled:
            st.info("No markdown summaries file yet.")

    with tab_errors:
        st.subheader("Error log (last run)")
        if os.path.isfile(ERRORS_CSV):
            try:
                err_df = pd.read_csv(
                    ERRORS_CSV,
                    quoting=csv.QUOTE_ALL,
                    on_bad_lines="skip",
                )
                st.dataframe(err_df, width="stretch")
                with open(ERRORS_CSV, "rb") as f:
                    st.download_button(
                        "Download Error Log",
                        f,
                        file_name="errors.csv",
                        key="dl_err_hist",
                    )
            except Exception as e:
                st.error(f"Could not load error log: {e}")
        else:
            st.info("No errors logged.")

if run_button:
    if mode == "Upload Excel" and not uploaded_file:
        st.error("Please upload an Excel file.")
    elif mode == "Auto Search Utilities" and not state_input:
        st.error("Please enter a state.")
    else:
        resolved_model = (
            (custom_model_name or "").strip()
            if model_preset == "Custom…"
            else model_preset
        )
        if model_preset == "Custom…" and not resolved_model:
            st.error("Enter a custom Ollama model name, or choose a preset.")
        else:
            st.session_state.last_run_markdown_enabled = generate_markdown
            st.session_state.last_run_raw_scrape_enabled = write_raw_scrapes
            st.session_state.last_run_raw_scrape_zip_path = None

            st.session_state.pipeline_done = False
            st.session_state.pipeline_csv_path = None
            st.session_state.pipeline_done_error = None
            st.session_state.pipeline_done_cancelled = False

            excel_payload = None
            if mode == "Upload Excel":
                excel_payload = io.BytesIO(uploaded_file.getvalue())

            progress_state = {"current": 0, "total": 1, "message": "Starting…", "url": ""}
            progress_lock = threading.Lock()
            cancel_event = threading.Event()
            result_holder = {"path": None, "cancelled": False, "error": None}

            def progress_callback(current, total, message, url=""):
                with progress_lock:
                    progress_state["current"] = current
                    progress_state["total"] = max(total, 1)
                    progress_state["message"] = message
                    progress_state["url"] = url or ""

            def worker():
                try:
                    path, cancelled = run_pipeline(
                        mode=mode,
                        uploaded_file=excel_payload if mode == "Upload Excel" else None,
                        state=state_input,
                        temperature=temperature,
                        truncation_length=int(truncation_length),
                        max_depth=int(max_depth),
                        progress_callback=progress_callback,
                        cancel_flag=cancel_event.is_set,
                        use_deep_crawl=use_deep_crawl,
                        deep_crawl_timeout_sec=int(deep_crawl_timeout_sec),
                        model_name=resolved_model,
                        write_markdown=generate_markdown,
                        write_raw_scrape_markdown_files=write_raw_scrapes,
                        raw_scrape_markdown_dir=os.path.join(_BASE_DIR, "raw_scrapes"),
                    )
                    result_holder["path"] = path
                    result_holder["cancelled"] = cancelled
                except Exception as e:
                    result_holder["error"] = e

            worker_thread = threading.Thread(target=worker, daemon=True)
            st.session_state.job_ctx = {
                "progress_state": progress_state,
                "progress_lock": progress_lock,
                "cancel_event": cancel_event,
                "result_holder": result_holder,
                "write_markdown": generate_markdown,
                "write_raw_scrapes": write_raw_scrapes,
            }
            st.session_state.worker_thread = worker_thread
            worker_thread.start()
            st.session_state.pipeline_running = True

if st.session_state.pipeline_running and st.session_state.get("job_ctx"):
    ctx = st.session_state.job_ctx
    with ctx["progress_lock"]:
        snap = {
            "current": ctx["progress_state"]["current"],
            "total": max(ctx["progress_state"]["total"], 1),
            "message": ctx["progress_state"]["message"],
            "url": ctx["progress_state"]["url"],
        }

    with tab_progress:
        st.progress(snap["current"] / snap["total"])
        st.markdown(f"**{snap['message']}**")
        st.markdown(f"Current URL: `{snap['url']}`")
        if ctx.get("write_raw_scrapes", False):
            st.caption("Saving raw scraped markdown files to `AI_merge/raw_scrapes/` (pre-LLM).")

    with tab_markdown:
        if not ctx.get("write_markdown", True):
            st.info(
                "Markdown summaries are disabled for this run. "
                "Turn on **Generate markdown summaries** in the sidebar for the next run."
            )
        elif os.path.isfile(MARKDOWN_CSV):
            try:
                md_df = pd.read_csv(
                    MARKDOWN_CSV,
                    quoting=csv.QUOTE_ALL,
                    on_bad_lines="skip",
                )
                for _, row in md_df.tail(5).iterrows():
                    st.markdown(row["markdown_summary"])
                    st.divider()
            except Exception:
                pass

    with tab_errors:
        if os.path.isfile(ERRORS_CSV):
            try:
                err_df = pd.read_csv(
                    ERRORS_CSV,
                    quoting=csv.QUOTE_ALL,
                    on_bad_lines="skip",
                )
                st.dataframe(err_df, width="stretch")
            except Exception:
                pass

    st.sidebar.button(
        CANCEL_BUTTON_LABEL,
        key="cancel_pipeline",
        type="secondary",
        on_click=lambda: ctx["cancel_event"].set(),
    )

    worker_thread = st.session_state.worker_thread
    if not worker_thread.is_alive():
        err = ctx["result_holder"]["error"]
        output_file = ctx["result_holder"]["path"]
        cancelled = ctx["result_holder"]["cancelled"]
        st.session_state.pipeline_running = False
        del st.session_state.job_ctx
        del st.session_state.worker_thread

        st.session_state.pipeline_done = True
        st.session_state.pipeline_csv_path = output_file
        st.session_state.pipeline_done_error = err
        st.session_state.pipeline_done_cancelled = cancelled

        with tab_progress:
            if cancelled:
                st.warning("Pipeline was cancelled. Partial results saved.")
            elif err is None:
                st.success("Extraction complete.")
            if output_file and err is None:
                with open(output_file, "rb") as f:
                    st.download_button(
                        "Download Results CSV",
                        f,
                        file_name="incentives_output.csv",
                    )
            if ctx.get("write_raw_scrapes", False):
                raw_dir = os.path.join(_BASE_DIR, "raw_scrapes")
                if os.path.isdir(raw_dir):
                    zip_path = os.path.join(_BASE_DIR, "raw_scrapes.zip")
                    try:
                        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
                            for root, _, files in os.walk(raw_dir):
                                for name in files:
                                    fp = os.path.join(root, name)
                                    arc = os.path.relpath(fp, _BASE_DIR)
                                    z.write(fp, arcname=arc)
                        st.session_state.last_run_raw_scrape_zip_path = zip_path
                        with open(zip_path, "rb") as f:
                            st.download_button(
                                "Download Raw Scrapes (zip)",
                                f,
                                file_name="raw_scrapes.zip",
                                key="dl_raw_scrapes_zip",
                            )
                    except Exception as e:
                        st.warning(f"Could not zip raw scrapes: {e}")

        with tab_markdown:
            st.subheader("Full Markdown Summaries")
            if not ctx.get("write_markdown", True):
                st.info("Markdown summaries were disabled for this run.")
            elif os.path.isfile(MARKDOWN_CSV):
                try:
                    md_df = pd.read_csv(
                        MARKDOWN_CSV,
                        quoting=csv.QUOTE_ALL,
                        on_bad_lines="skip",
                    )
                    for _, row in md_df.iterrows():
                        st.markdown(row["markdown_summary"])
                        st.divider()
                    with open(MARKDOWN_CSV, "rb") as f:
                        st.download_button(
                            "Download Markdown CSV",
                            f,
                            file_name="markdown_summaries.csv",
                        )
                except Exception as e:
                    st.error(f"Could not load markdown summaries: {e}")
            else:
                st.info("No summaries generated yet.")

        with tab_errors:
            st.subheader("Error Log")
            if os.path.isfile(ERRORS_CSV):
                try:
                    err_df = pd.read_csv(
                        ERRORS_CSV,
                        quoting=csv.QUOTE_ALL,
                        on_bad_lines="skip",
                    )
                    st.dataframe(err_df, width="stretch")
                    with open(ERRORS_CSV, "rb") as f:
                        st.download_button(
                            "Download Error Log",
                            f,
                            file_name="errors.csv",
                        )
                except Exception as e:
                    st.error(f"Could not load error log: {e}")
            else:
                st.info("No errors logged.")

        _streamlit_rerun()
    else:
        time.sleep(UI_POLL_INTERVAL_SEC)
        _streamlit_rerun()

elif not st.session_state.pipeline_done:
    with tab_progress:
        st.info("Configure the sidebar and press **Run Extraction** to start.")
