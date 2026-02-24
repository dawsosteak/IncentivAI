import streamlit as st
from main import run_pipeline
from config import DEFAULT_TEMPERATURE, DEFAULT_TRUNCATION

st.set_page_config(page_title="IncentivAI", layout="wide")

st.title("IncentivAI – Utility Incentive Extractor")

# Sidebar
st.sidebar.header("Configuration")

mode = st.sidebar.radio(
    "Select URL Source Mode",
    ["Upload Excel", "Auto Search Utilities"]
)

uploaded_file = None
state_input = None

if mode == "Upload Excel":
    uploaded_file = st.sidebar.file_uploader("Upload Excel (.xlsx) with column 'URLS'", type=["xlsx"])
else:
    state_input = st.sidebar.text_input("Enter State (e.g., California)")

temperature = st.sidebar.number_input("Temperature", value=DEFAULT_TEMPERATURE, step=0.1)
truncation_length = st.sidebar.number_input("Max Scrape Length", value=DEFAULT_TRUNCATION)

run_button = st.sidebar.button("Run Extraction")

if run_button:
    if mode == "Upload Excel" and not uploaded_file:
        st.error("Please upload an Excel file.")
    elif mode == "Auto Search Utilities" and not state_input:
        st.error("Please enter a state.")
    else:
        progress = st.progress(0)
        log_container = st.empty()

        def progress_callback(current, total, message):
            progress.progress(current / total)
            log_container.write(message)

        output_file = run_pipeline(
            mode=mode,
            uploaded_file=uploaded_file,
            state=state_input,
            temperature=temperature,
            truncation_length=truncation_length,
            progress_callback=progress_callback
        )

        st.success("Extraction complete.")
        with open(output_file, "rb") as f:
            st.download_button("Download CSV", f, file_name="incentives_output.csv")