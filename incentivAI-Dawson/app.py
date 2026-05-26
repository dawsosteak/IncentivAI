import csv
import io
import os
import datetime
import pandas as pd
import streamlit as st
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from main import run_pipeline
from modules.url_source import (
    get_urls_from_discovery,
    VALID_STATES,
    DISCOVERY_TOPICS,
    _load_existing_domains_from_excel,
    _extract_domain,
    _build_merged_workbook,
)
from config import DEFAULT_TEMPERATURE, DEFAULT_TRUNCATION, ERRORS_CSV, MARKDOWN_CSV

st.set_page_config(page_title="IncentivAI", layout="wide")
st.title("IncentivAI – Utility Incentive Extractor")

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.header("Configuration")

mode = st.sidebar.radio(
    "Select Mode",
    ["Upload Excel", "Auto Search Utilities", "City URL Discovery"]
)

uploaded_file = None
state_input = None

if mode == "Upload Excel":
    uploaded_file = st.sidebar.file_uploader(
        "Upload Excel (.xlsx) with column 'URLs'", type=["xlsx"]
    )
elif mode == "Auto Search Utilities":
    state_input = st.sidebar.text_input("Enter State (e.g., California)")

# Pipeline settings — only shown for extraction modes
if mode in ("Upload Excel", "Auto Search Utilities"):
    temperature = st.sidebar.number_input("Temperature", value=DEFAULT_TEMPERATURE, step=0.1)
    truncation_length = st.sidebar.number_input("Max Scrape Length", value=DEFAULT_TRUNCATION)
    provider = st.sidebar.selectbox(
        "LLM Provider",
        ["ollama", "openai", "uw_ssec", "anthropic", "google"],
        index=0
    )
    model_name = st.sidebar.text_input("Model Name", value="qwen2.5:7b")
    run_button = st.sidebar.button("▶ Run Extraction")
    cancel_button = st.sidebar.button("⏹ Cancel")

# ── Session state ─────────────────────────────────────────────────────────────
if "cancelled" not in st.session_state:
    st.session_state.cancelled = False

if mode in ("Upload Excel", "Auto Search Utilities") and cancel_button:
    st.session_state.cancelled = True
    st.sidebar.warning("Cancellation requested — stopping after current URL.")

# ═══════════════════════════════════════════════════════════════════════════════
# MODE: City URL Discovery
# ═══════════════════════════════════════════════════════════════════════════════
if mode == "City URL Discovery":
    st.subheader("Discover New Utility URLs by State")
    st.caption(
        "Searches OpenSERP for electric utility and cooperative websites by state. "
        "Skips domains already in your existing database."
    )

    col1, col2 = st.columns(2)
    with col1:
        selected_states = st.multiselect("States to search", VALID_STATES, default=["Texas"])
        openserp_url = st.text_input("OpenSERP URL", value="http://localhost:7070")
        engine = st.selectbox("Search engine", ["google", "bing", "duckduckgo"], index=0)
    with col2:
        num_results = st.slider("Results per query", min_value=3, max_value=15, value=8)
        db_file = st.file_uploader(
            "Existing URL database for deduplication (optional)",
            type=["xlsx"],
            key="db_upload"
        )

    with st.expander("Search topics"):
        topics_text = st.text_area(
            "One topic per line",
            value="\n".join(DISCOVERY_TOPICS),
            height=300
        )

    if st.button("▶ Run Discovery", disabled=not selected_states):
        progress_bar = st.progress(0)
        status_text = st.empty()
        log_area = st.empty()
        log_lines = []

        def discovery_progress(current, total, url="", message=""):
            progress_bar.progress(current / total)
            status_text.markdown(f"**{message}**")

        discovered = get_urls_from_discovery(
            states=selected_states,
            openserp_url=openserp_url,
            engine=engine,
            num_results=num_results,
            existing_db=db_file,
            progress_callback=discovery_progress,
        )

        st.success(f"Found **{len(discovered)}** new utility URLs across {len(selected_states)} state(s).")

        if discovered:
            # Show results table
            st.subheader("Discovered URLs")
            df = pd.DataFrame([{
                "State": r["state"],
                "URL": r["url"],
                "Page Title": r["title"],
                "Discovered At": r["discovered_at"],
            } for r in discovered])
            st.dataframe(df, use_container_width=True)

            # Build Excel output
            from openpyxl import Workbook as WB
            from openpyxl.styles import Font as F, PatternFill as PF, Alignment as AL, Border as B, Side as S

            def _thin():
                s = S(style="thin", color="BFBFBF")
                return B(left=s, right=s, top=s, bottom=s)

            wb = WB()
            ws = wb.active
            ws.title = "Discovered URLs"
            for col, w in {"A": 16, "B": 30, "C": 60, "D": 45, "E": 70, "F": 22}.items():
                ws.column_dimensions[col].width = w
            ws.freeze_panes = "A2"
            for c, h in enumerate(["State", "Search Query", "URL", "Page Title", "Description", "Discovered At"], 1):
                cell = ws.cell(row=1, column=c, value=h)
                cell.font = F(name="Arial", bold=True, color="FFFFFF", size=11)
                cell.fill = PF("solid", start_color="1F4E79")
                cell.alignment = AL(horizontal="center", vertical="center")
                cell.border = _thin()

            for r_idx, row in enumerate(discovered, 2):
                for c, val in enumerate([
                    row["state"], row["query"], row["url"],
                    row["title"], row["description"], row["discovered_at"]
                ], 1):
                    cell = ws.cell(row=r_idx, column=c, value=val)
                    cell.font = F(name="Arial", size=10)
                    cell.border = _thin()
                    cell.alignment = AL(vertical="top", wrap_text=(c in (2, 3, 4, 5)))
                    if c == 1:
                        cell.fill = PF("solid", start_color="D6E4F0")
                        cell.font = F(name="Arial", bold=True, size=10, color="1F4E79")

            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)
            st.download_button(
                "⬇️ Download Discovered URLs Excel",
                buf.read(),
                file_name=f"utility_urls_discovered_{datetime.date.today()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # Also offer as plain URL list for immediate pipeline use
            url_list = "\n".join(r["url"] for r in discovered)
            st.download_button(
                "⬇️ Download as plain URL list (.txt)",
                url_list.encode("utf-8"),
                file_name="discovered_urls.txt",
                mime="text/plain"
            )

    # ── Merge sub-section ─────────────────────────────────────────────────────
    st.divider()
    st.subheader("Merge Discovered URLs into Existing Database")
    st.caption("Domain-level deduplication. Merges a discovered file into your existing URL database.")

    col1, col2 = st.columns(2)
    with col1:
        merge_db = st.file_uploader("Existing URL database", type=["xlsx"], key="merge_db")
    with col2:
        merge_disc = st.file_uploader("Discovered URLs file", type=["xlsx"], key="merge_disc")

    if merge_db and merge_disc:
        from openpyxl import load_workbook as lw

        def _load_urls(f) -> list:
            wb = lw(io.BytesIO(f.read()), read_only=True)
            ws = wb.active
            urls = []
            for row in ws.iter_rows(values_only=True):
                for cell in row:
                    if cell and isinstance(cell, str) and cell.startswith("http"):
                        urls.append(cell.strip())
            wb.close()
            return urls

        def _load_disc_rows(f) -> list:
            wb = lw(io.BytesIO(f.read()), read_only=True)
            ws = wb.active
            rows = []
            headers = None
            for row in ws.iter_rows(values_only=True):
                if headers is None:
                    headers = [str(c).strip() if c else "" for c in row]
                    continue
                if not any(row):
                    continue
                record = dict(zip(headers, row))
                url = str(record.get("URL", "") or "").strip()
                if url.startswith("http"):
                    rows.append(record)
            wb.close()
            return rows

        existing_urls = _load_urls(merge_db)
        existing_domains = set(_extract_domain(u) for u in existing_urls if _extract_domain(u))
        discovered_rows = _load_disc_rows(merge_disc)

        seen = set(existing_domains)
        new_rows = []
        skipped = 0
        for row in discovered_rows:
            url = str(row.get("URL", "")).strip()
            domain = _extract_domain(url)
            if not domain:
                continue
            if domain in seen:
                skipped += 1
            else:
                seen.add(domain)
                new_rows.append(row)

        st.write(f"**Existing:** {len(existing_urls)} URLs | **Discovered:** {len(discovered_rows)} rows")
        st.write(f"**After dedup:** {len(new_rows)} new URLs, {skipped} skipped")

        if new_rows and st.button("▶ Merge & Download"):
            wb = _build_merged_workbook(existing_urls, new_rows)
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            st.success(f"Merged: {len(existing_urls)} existing + {len(new_rows)} new = {len(existing_urls)+len(new_rows)} total")
            st.download_button(
                "⬇️ Download Merged Database",
                buf.read(),
                file_name=f"Relevant_URLs_merged_{timestamp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# ═══════════════════════════════════════════════════════════════════════════════
# MODE: Upload Excel / Auto Search — Extraction pipeline
# ═══════════════════════════════════════════════════════════════════════════════
elif mode in ("Upload Excel", "Auto Search Utilities"):
    tab_progress, tab_markdown, tab_errors = st.tabs([
        "📊 Progress", "📝 Live Summaries", "⚠️ Errors"
    ])

    if run_button:
        st.session_state.cancelled = False

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
                    f"✅ Succeeded: `{success_count[0]}` &nbsp;|&nbsp; "
                    f"❌ Failed: `{fail_count[0]}` &nbsp;|&nbsp; "
                    f"🔗 Current: `{url}`"
                )

                # Refresh live markdown tab
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
                cancel_flag=lambda: st.session_state.cancelled,
                provider=provider,
                model=model_name,
            )

            # ── Post-run ──────────────────────────────────────────────────────
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
