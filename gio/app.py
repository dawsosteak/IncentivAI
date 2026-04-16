import io
import threading
import time

import streamlit as st

import os
import sys

# Ensure this folder is on sys.path so `main.py` and `modules/*` imports work
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from main import run_pipeline
from config import (
    DEFAULT_TEMPERATURE,
    DEFAULT_TRUNCATION,
    UI_POLL_INTERVAL_SEC,
    CANCEL_BUTTON_LABEL,
)


def _streamlit_rerun():
    """Streamlit 1.27+ exposes st.rerun(); older releases use experimental_rerun."""
    rerun = getattr(st, "rerun", None)
    if callable(rerun):
        rerun()
        return
    experimental = getattr(st, "experimental_rerun", None)
    if callable(experimental):
        experimental()
        return
    raise RuntimeError(
        "This Streamlit version does not support script reruns; "
        "upgrade to at least streamlit 1.11."
    )


#browser tab name
st.set_page_config(page_title="IncentivAI", layout="wide")

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

#Title of the app
st.title("IncentivAI – Utility Incentive Extractor")

# Persisted result after background worker finishes (reliable across Streamlit reruns)
if st.session_state.pipeline_done:
    err = st.session_state.pipeline_done_error
    path = st.session_state.pipeline_csv_path
    cancelled = st.session_state.pipeline_done_cancelled
    if err is not None:
        st.error(f"Extraction failed: {err}")
    elif path:
        if cancelled:
            st.warning(
                "Extraction cancelled. Download contains partial results processed so far."
            )
        else:
            st.success("Extraction complete.")
        with open(path, "rb") as f:
            st.download_button(
                "Download CSV",
                f,
                file_name="incentives_output.csv",
                key="download_csv_completed",
            )
    st.divider()

# Sidebar
st.sidebar.header("Configuration")
#Sets options of what people can do to get urls, either upload an excel file with urls or have the app automatically search for utility company pages based on the state input
mode = st.sidebar.radio(
    "Select URL Source Mode",
    ["Upload Excel", "Auto Search Utilities"]
)
#create variables
uploaded_file = None
state_input = None
#Get user input based on the selected mode
if mode == "Upload Excel":
    uploaded_file = st.sidebar.file_uploader(
        "Upload Excel (.xlsx) with column 'URLs' or 'URLS' (or 'url')",
        type=["xlsx"],
    )
else:
    state_input = st.sidebar.text_input("Enter State (e.g., California)")
#variables we can set for scraping or looking forurls and doing
temperature = st.sidebar.number_input("Temperature", value=DEFAULT_TEMPERATURE, step=0.1)
truncation_length = st.sidebar.number_input("Max Scrape Length", value=DEFAULT_TRUNCATION)
#create button to press
run_button = st.sidebar.button(
    "Run Extraction",
    disabled=st.session_state.pipeline_running,
)

if run_button:
    if mode == "Upload Excel" and not uploaded_file:
        st.error("Please upload an Excel file.")
    elif mode == "Auto Search Utilities" and not state_input:
        st.error("Please enter a state.")
    else:
        st.session_state.pipeline_done = False
        st.session_state.pipeline_csv_path = None
        st.session_state.pipeline_done_error = None
        st.session_state.pipeline_done_cancelled = False

        excel_payload = None
        if mode == "Upload Excel":
            excel_payload = io.BytesIO(uploaded_file.getvalue())

        progress_state = {"current": 0, "total": 1, "message": "Starting extraction…"}
        progress_lock = threading.Lock()
        cancel_event = threading.Event()
        result_holder = {"path": None, "cancelled": False, "error": None}

        def progress_callback(current, total, message):
            with progress_lock:
                progress_state["current"] = current
                progress_state["total"] = max(total, 1)
                progress_state["message"] = message

        def worker():
            try:
                path, cancelled = run_pipeline(
                    mode=mode,
                    uploaded_file=excel_payload if mode == "Upload Excel" else None,
                    state=state_input,
                    temperature=temperature,
                    truncation_length=truncation_length,
                    progress_callback=progress_callback,
                    should_cancel=cancel_event.is_set,
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
        }
        st.session_state.worker_thread = worker_thread
        worker_thread.start()
        st.session_state.pipeline_running = True

if st.session_state.pipeline_running and st.session_state.get("job_ctx"):
    ctx = st.session_state.job_ctx
    progress = st.progress(0)
    log_container = st.empty()

    with ctx["progress_lock"]:
        snap = {
            "current": ctx["progress_state"]["current"],
            "total": max(ctx["progress_state"]["total"], 1),
            "message": ctx["progress_state"]["message"],
        }
    progress.progress(snap["current"] / snap["total"])
    log_container.write(snap["message"])

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
        _streamlit_rerun()
    else:
        time.sleep(UI_POLL_INTERVAL_SEC)
        _streamlit_rerun()
