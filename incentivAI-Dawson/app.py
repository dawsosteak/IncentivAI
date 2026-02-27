import streamlit as st
from main import run_pipeline
from config import DEFAULT_TEMPERATURE, DEFAULT_TRUNCATION
#browser tab name 
st.set_page_config(page_title="IncentivAI", layout="wide")
#Title of the app
st.title("IncentivAI – Utility Incentive Extractor")

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
    uploaded_file = st.sidebar.file_uploader("Upload Excel (.xlsx) with column 'URLS'", type=["xlsx"])
else:
    state_input = st.sidebar.text_input("Enter State (e.g., California)")
#variables we can set for scraping or looking forurls and doing
temperature = st.sidebar.number_input("Temperature", value=DEFAULT_TEMPERATURE, step=0.1)
truncation_length = st.sidebar.number_input("Max Scrape Length", value=DEFAULT_TRUNCATION)
#create button to press
run_button = st.sidebar.button("Run Extraction")
#what happens if you press button
if run_button:
    if mode == "Upload Excel" and not uploaded_file:
        st.error("Please upload an Excel file.")
    elif mode == "Auto Search Utilities" and not state_input:
        st.error("Please enter a state.")
    else:
        progress = st.progress(0)#progress bar to show progress of the pipeline
        log_container = st.empty()# container to show logs from the pipeline, we can write to this container to show updates on the progress of the pipeline
        #calling progress for updates
        def progress_callback(current, total, message):
            progress.progress(current / total)
            log_container.write(message)
        # run the pipeline and get the output file, this is where we call the main function that runs the whole pipeline
        output_file = run_pipeline(
            mode=mode,
            uploaded_file=uploaded_file,
            state=state_input,
            temperature=temperature,
            truncation_length=truncation_length,
            progress_callback=progress_callback
        )
        #if complete, show success message and download button for the output csv file
        st.success("Extraction complete.")
        with open(output_file, "rb") as f:
            st.download_button("Download CSV", f, file_name="incentives_output.csv")