"""
config.py — Single source of truth for all constants, prompts, and default settings.
"""

# ---------------------------------------------------------
# LLM DEFAULTS
# ---------------------------------------------------------
DEFAULT_PROVIDER = "ollama"
DEFAULT_MODEL = "llama3.2"
DEFAULT_TEMPERATURE = 0.1
DEFAULT_TRUNCATION_LENGTH = 150000
DEFAULT_TRUNCATION = DEFAULT_TRUNCATION_LENGTH  # alias — imported by app.py

# ---------------------------------------------------------
# SCRAPER CONSTANTS
# ---------------------------------------------------------
PDF_KEYWORDS = [
    "incentive", "rebate", "grant", "funding", "assistance",
    "opportunity", "application", "eligibility", "program",
    "efficiency", "solar", "ev", "charger"
]

PDF_BONUS_TERMS = ["guide", "manual", "form", "terms"]

MAX_RANKED_PDFS = 3
MAX_EXCEL_FILES = 2
MAX_EXCEL_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
PDF_SCRAPE_TIMEOUT = 120

# ---------------------------------------------------------
# OUTPUT DIRECTORIES & FILES
# ---------------------------------------------------------
SCRAPED_DATA_DIR = "scraped_data"
ANALYSIS_RESULTS_DIR = "analysis_results"
ERROR_LOG_FILENAME = "analysis_errors.log"

# CSV output files written during pipeline runs
ERRORS_CSV = "errors.csv"
MARKDOWN_CSV = "markdown_output.csv"

# ---------------------------------------------------------
# LLM PROMPT TEMPLATES
# ---------------------------------------------------------
EXTRACTION_TEMPLATE = '''
You are a strict utility rebate analyst. Your job is to extract actionable utility rebate programs.

CRITICAL INSTRUCTIONS:
1. If this document is merely a news article, a blog post,
a glossary, or general advice about energy efficiency,
YOU MUST ABORT and output EXACTLY: "NOT RELEVANT: No concrete rebate program found."
2. Only proceed if the document explicitly outlines a specific, currently active rebate,
incentive, or grant program offered by a utility company or government entity.

OUTPUT FORMATTING:
You MUST format your output STRICTLY in Markdown. Use exact headers and bullet points as follows:

# Program Name:[Extract Program Name]

#Program URL: [Extract Program URL]

## Program Details
- **Concrete Rebate Amounts:**
- [Amount 1]
- [Amount 2]
- [...list ALL applicable amounts]

## Eligibility
- **Eligibility Requirements:**
- [Requirement 1]
- [Requirement 2]
- [...list ALL applicable requirements]

## Utility Information
- **Utility Company Name:** [Extract Utility Name]
- **Utility Company Size:** [Extract Utility Size]

Do not include any other conversational text or preamble. Output ONLY the strict markdown structure.
If information DOES NOT have rebate information, DON\'T append to results.
DO NOT INCLUDE ANY OTHER TEXT OR EXPLANATION. ONLY THE MARKDOWN STRUCTURE WITH THE RELEVANT INFORMATION.

Document URL/Source: {source}
Document Text:
{document_text}
'''

FILTER_TEMPLATE = '''
You are a final-stage quality control analyst.
Below is a raw markdown report containing extracted utility rebate programs from various pages.
Some sections might say "NOT RELEVANT: No concrete rebate program found", or contain empty fields, or have unrelated data.

Your job is to read the raw report and output a CLEAN, CONSOLIDATED markdown report that ONLY includes the valid, concrete rebate programs.
- Discard any section that says "NOT RELEVANT".
- Discard any conversational filler.
- Keep the exact markdown structure for valid programs:
  # Program Name, #Program URL, ## Program Details, ## Eligibility, ## Utility Information.
- Make sure to keep program details and eligibility requirements as bullet points under their respective headers.

If there are NO valid programs in the entire raw report, output EXACTLY: "NO REBATES FOUND."

Raw Report:
{raw_report}
'''
