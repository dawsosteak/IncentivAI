import csv
import os
import pandas as pd
import streamlit as st
from main import run_pipeline
from config import DEFAULT_TEMPERATURE, DEFAULT_TRUNCATION, ERRORS_CSV, MARKDOWN_CSV

st.set_page_config(page_title="IncentivAI", layout="wide")
st.title("IncentivAI – Utility Incentive Extractor")

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.header("Configuration")

mode = st.sidebar.radio(
    "Select URL Source Mode",
    ["Upload Excel", "Auto Search Utilities"]
)

uploaded_file = None
state_input = None

if mode == "Upload Excel":
    uploaded_file = st.sidebar.file_uploader(
        "Upload Excel (.xlsx) with column 'URLS'", type=["xlsx"]
    )
else:
    state_input = st.sidebar.text_input("Enter State (e.g., California)")

temperature = st.sidebar.number_input("Temperature", value=DEFAULT_TEMPERATURE, step=0.1)
truncation_length = st.sidebar.number_input("Max Scrape Length", value=DEFAULT_TRUNCATION)

run_button = st.sidebar.button("▶ Run Extraction")
cancel_button = st.sidebar.button("⏹ Cancel")

# ── Session state for cancel flag ─────────────────────────────────────────────
if "cancelled" not in st.session_state:
    st.session_state.cancelled = False

if cancel_button:
    st.session_state.cancelled = True
    st.sidebar.warning("Cancellation requested — stopping after current URL.")

# ── Main area tabs ────────────────────────────────────────────────────────────
tab_progress, tab_markdown, tab_errors = st.tabs([
    "📊 Progress", "📝 Live Summaries", "⚠️ Errors"
])

# ── Run pipeline ──────────────────────────────────────────────────────────────
if run_button:
    st.session_state.cancelled = False  # reset on new run

    if mode == "Upload Excel" and not uploaded_file:
        st.error("Please upload an Excel file.")
    elif mode == "Auto Search Utilities" and not state_input:
        st.error("Please enter a state.")
    else:
        with tab_progress:
            progress_bar = st.progress(0)
            status_text = st.empty()
            stats = st.empty()

        success_count = [0]
        fail_count = [0]

        def progress_callback(current, total, url="", message=""):
            pct = current / total
            progress_bar.progress(pct)
            status_text.markdown(f"**{message}**")
            stats.markdown(
                f"✅ Succeeded: `{success_count[0]}`  |  "
                f"❌ Failed: `{fail_count[0]}`  |  "
                f"🔗 Current: `{url}`"
            )

            # Refresh live markdown tab with last 5 entries
            with tab_markdown:
                if os.path.isfile(MARKDOWN_CSV):
                    try:
                        md_df = pd.read_csv(
                            MARKDOWN_CSV,
                            quoting=csv.QUOTE_ALL,
                            on_bad_lines="skip"
                        )
                        for _, row in md_df.tail(5).iterrows():
                            st.markdown(row["markdown_summary"])
                            st.divider()
                    except Exception:
                        pass

            # Refresh errors tab
            with tab_errors:
                if os.path.isfile(ERRORS_CSV):
                    try:
                        err_df = pd.read_csv(
                            ERRORS_CSV,
                            quoting=csv.QUOTE_ALL,
                            on_bad_lines="skip"
                        )
                        st.dataframe(err_df, use_container_width=True)
                    except Exception:
                        pass

        output_file = run_pipeline(
            mode=mode,
            uploaded_file=uploaded_file,
            state=state_input,
            temperature=temperature,
            truncation_length=int(truncation_length),
            progress_callback=progress_callback,
            cancel_flag=lambda: st.session_state.cancelled
        )

        # ── Post-run results ──────────────────────────────────────────────────
        with tab_progress:
            if st.session_state.cancelled:
                st.warning("Pipeline was cancelled. Partial results saved.")
            else:
                st.success("✅ Extraction complete.")

            with open(output_file, "rb") as f:
                st.download_button(
                    "⬇️ Download Results CSV",
                    f,
                    file_name="incentives_output.csv"
                )

        with tab_markdown:
            st.subheader("Full Markdown Summaries")
            if os.path.isfile(MARKDOWN_CSV):
                try:
                    md_df = pd.read_csv(
                        MARKDOWN_CSV,
                        quoting=csv.QUOTE_ALL,
                        on_bad_lines="skip"
                    )
                    for _, row in md_df.iterrows():
                        st.markdown(row["markdown_summary"])
                        st.divider()
                    with open(MARKDOWN_CSV, "rb") as f:
                        st.download_button(
                            "⬇️ Download Markdown CSV",
                            f,
                            file_name="markdown_summaries.csv"
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
                        on_bad_lines="skip"
                    )
                    st.dataframe(err_df, use_container_width=True)
                    with open(ERRORS_CSV, "rb") as f:
                        st.download_button(
                            "⬇️ Download Error Log",
                            f,
                            file_name="errors.csv"
                        )
                except Exception as e:
                    st.error(f"Could not load error log: {e}")
            else:
                st.info("No errors logged.")