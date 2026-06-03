
import re
from config import MAX_RETRIES, DEFAULT_TRUNCATION
from modules.llm_agent import call_llm
from utils.logger import get_logger

logger = get_logger()

# ── Stage 1: Extraction prompt ────────────────────────────────────────────────
# Extracts rebate programs as structured markdown, or outputs "NOT RELEVANT"
# if the page has no concrete programs.

EXTRACTION_TEMPLATE = """
You are a strict utility rebate analyst. Your job is to extract actionable utility rebate programs.

CRITICAL INSTRUCTIONS:
1. If this document is merely a news article, a blog post,
a glossary, or general advice about energy efficiency,
YOU MUST ABORT and output EXACTLY: "NOT RELEVANT: No concrete rebate program found."
2. Only proceed if the document explicitly outlines a specific, currently active rebate,
incentive, or grant program offered by a utility company or government entity.

OUTPUT FORMATTING:
You MUST format your output STRICTLY in Markdown. Use exact headers and bullet points as follows:

# Program Name: [Extract Program Name]

# Program URL: [Extract Program URL]

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
If information DOES NOT have rebate information, DON'T append to results.
DO NOT INCLUDE ANY OTHER TEXT OR EXPLANATION. ONLY THE MARKDOWN STRUCTURE WITH THE RELEVANT INFORMATION.

Document URL/Source: {source}
Document Text:
{document_text}
"""

# ── Stage 2: Filter/consolidation prompt ─────────────────────────────────────
# Cleans and consolidates the raw markdown from Stage 1.
# Discards NOT RELEVANT sections, filler, and empty fields.

FILTER_TEMPLATE = """
You are a final-stage quality control analyst.
Below is a raw markdown report containing extracted utility rebate programs from various pages.
Some sections might say "NOT RELEVANT: No concrete rebate program found.", or contain empty fields,
or have unrelated data.

Your job is to read the raw report and output a CLEAN, CONSOLIDATED markdown report that ONLY
includes the valid, concrete rebate programs.
- Discard any section that says "NOT RELEVANT".
- Discard any conversational filler.
- Keep the exact markdown structure for valid programs:
  # Program Name, # Program URL, ## Program Details, ## Eligibility, ## Utility Information.
- Make sure to keep program details and eligibility requirements as bullet points under their
  respective headers.

If there are NO valid programs in the entire raw report, output EXACTLY: "NO REBATES FOUND."

Raw Report:
{raw_report}
"""


# ── Prompt builders ───────────────────────────────────────────────────────────

def build_extraction_prompt(text: str, url: str = "") -> str:
    """Build the Stage 1 extraction prompt."""
    truncated = text[:DEFAULT_TRUNCATION]
    return EXTRACTION_TEMPLATE.format(
        source=url or "unknown",
        document_text=truncated
    )


def build_filter_prompt(raw_markdown: str) -> str:
    """Build the Stage 2 filter/consolidation prompt."""
    return FILTER_TEMPLATE.format(raw_report=raw_markdown)


# ── Markdown → JSON schema parser ────────────────────────────────────────────

def _parse_markdown_to_dict(markdown: str, url: str = "") -> dict:
    """
    Parse the filtered markdown output from Stage 2 into the pipeline JSON schema.

    Handles multiple programs on one page by splitting on '# Program Name:' headers.
    Falls back gracefully if markdown is malformed or empty.

    Returns dict matching:
        {
            "utility_company": str | None,
            "programs": [...],
            "summary_of_page": str
        }
    """
    if not markdown or not markdown.strip():
        return {
            "utility_company": None,
            "programs": [],
            "summary_of_page": "Filter stage returned empty output."
        }

    if "NO REBATES FOUND" in markdown.upper():
        return {
            "utility_company": None,
            "programs": [],
            "summary_of_page": "No valid rebate programs found after filtering."
        }

    # Split into individual program blocks on each "# Program Name:" header
    program_blocks = re.split(r'(?=^# Program Name:)', markdown, flags=re.MULTILINE)
    program_blocks = [
        b.strip() for b in program_blocks
        if b.strip() and "# Program Name:" in b
    ]

    # If no blocks found but content exists, treat whole thing as one block
    if not program_blocks and markdown.strip():
        program_blocks = [markdown.strip()]

    programs = []
    utility_company = None

    for block in program_blocks:
        program = {
            "program_name":       None,
            "program_type":       "rebate",
            "financial_details":  None,
            "eligibility":        None,
            "application_process": None,
            "sector":             None,
            "notes":              None,
        }

        # ── Program name ──────────────────────────────────────────────────────
        name_match = re.search(r'# Program Name:\s*(.+)', block)
        if name_match:
            name = name_match.group(1).strip()
            if name.lower() not in ('[extract program name]', 'unknown', ''):
                program["program_name"] = name

        # ── Program URL → goes into notes ─────────────────────────────────────
        url_match = re.search(r'# Program URL:\s*(.+)', block)
        if url_match:
            extracted_url = url_match.group(1).strip()
            if extracted_url.lower() not in ('[extract program url]', 'unknown', ''):
                program["notes"] = f"Program URL: {extracted_url}"

        # ── Financial details (rebate amounts) ────────────────────────────────
        amounts_match = re.search(
            r'## Program Details.*?\*\*Concrete Rebate Amounts:\*\*(.*?)(?=^##|\Z)',
            block, re.DOTALL | re.MULTILINE
        )
        if amounts_match:
            amounts_text = amounts_match.group(1).strip()
            amounts = [
                line.lstrip('- ').strip()
                for line in amounts_text.split('\n')
                if line.strip() and line.strip() not in ('-', '•')
                and '[amount' not in line.lower()
            ]
            if amounts:
                program["financial_details"] = "; ".join(amounts)

        # ── Eligibility ───────────────────────────────────────────────────────
        elig_match = re.search(
            r'## Eligibility.*?\*\*Eligibility Requirements:\*\*(.*?)(?=^##|\Z)',
            block, re.DOTALL | re.MULTILINE
        )
        if elig_match:
            elig_text = elig_match.group(1).strip()
            reqs = [
                line.lstrip('- ').strip()
                for line in elig_text.split('\n')
                if line.strip() and line.strip() not in ('-', '•')
                and '[requirement' not in line.lower()
            ]
            if reqs:
                program["eligibility"] = "; ".join(reqs)

        # ── Utility company ───────────────────────────────────────────────────
        util_match = re.search(r'\*\*Utility Company Name:\*\*\s*(.+)', block)
        if util_match:
            util_name = util_match.group(1).strip()
            if util_name.lower() not in ('[extract utility name]', 'unknown', ''):
                utility_company = util_name

        # ── Utility size → sector if mentioned ───────────────────────────────
        size_match = re.search(r'\*\*Utility Company Size:\*\*\s*(.+)', block)
        if size_match:
            size = size_match.group(1).strip()
            if size.lower() not in ('[extract utility size]', 'unknown', ''):
                existing_notes = program.get("notes") or ""
                program["notes"] = (existing_notes + f" | Utility size: {size}").lstrip(" | ")

        # Only append if we got something meaningful
        if program["program_name"] or program["financial_details"]:
            programs.append(program)

    return {
        "utility_company": utility_company,
        "programs": programs,
        "summary_of_page": (
            f"Extracted {len(programs)} rebate program(s) from {url or 'uploaded content'}."
            if programs else
            "Page processed but no structured programs could be parsed from output."
        )
    }


# ── Main entry point ──────────────────────────────────────────────────────────

def process_text(
    text: str,
    url: str,
    temperature: float,
    provider: str = "ollama",
    model: str = None
) -> dict:
    """
    Two-stage LLM pipeline for extracting utility rebate programs.

    Stage 1 — Extraction LLM:
        Reads raw scraped text, extracts rebate programs as structured markdown.
        Outputs "NOT RELEVANT" if page has no concrete programs — pipeline
        exits early and skips Stage 2, saving time and tokens.

    Stage 2 — Filter LLM:
        Reads the raw markdown from Stage 1, discards NOT RELEVANT sections,
        cleans up filler, and outputs a consolidated report of valid programs only.
        Falls back to raw Stage 1 output if Stage 2 fails after all retries.

    Both stages use the same provider and model. Retries up to MAX_RETRIES
    on failure before raising.

    Args:
        text:        scraped page content
        url:         source URL (used in prompt and logging)
        temperature: LLM temperature
        provider:    LLM provider (ollama, openai, uw_ssec, anthropic, google)
        model:       model name override (uses config MODEL_NAME if None)

    Returns:
        dict matching pipeline JSON schema:
        {
            "utility_company": str | None,
            "programs": [{"program_name", "program_type", "financial_details",
                          "eligibility", "application_process", "sector", "notes"}],
            "summary_of_page": str
        }
    """
    from config import MODEL_NAME
    model = model or MODEL_NAME

    # Guard: skip content that's too short to be useful
    if not text or len(text) < 50:
        logger.warning(f"Content too short to process for {url}")
        return {
            "utility_company": None,
            "programs": [],
            "summary_of_page": "Scraped content was empty or too short."
        }

    # ── Stage 1: Extraction ───────────────────────────────────────────────────
    logger.info(f"Stage 1 — extracting from: {url}")
    extraction_prompt = build_extraction_prompt(text, url)
    raw_markdown = ""

    for attempt in range(MAX_RETRIES + 1):
        try:
            raw_markdown = call_llm(
                extraction_prompt,
                provider=provider,
                model=model,
                temperature=temperature
            )
            break
        except Exception as e:
            logger.error(f"Stage 1 extraction failed for {url}, attempt {attempt + 1}: {e}")
            if attempt == MAX_RETRIES:
                raise Exception(
                    f"Stage 1 LLM extraction failed after {MAX_RETRIES + 1} attempts for {url}."
                )

    # Early exit — Stage 1 flagged this page as not relevant
    if "NOT RELEVANT" in raw_markdown.upper():
        logger.info(f"Stage 1: not relevant — skipping Stage 2 for {url}")
        return {
            "utility_company": None,
            "programs": [],
            "summary_of_page": "Page filtered as not relevant — no concrete rebate programs found."
        }

    # ── Stage 2: Filter ───────────────────────────────────────────────────────
    logger.info(f"Stage 2 — filtering output for: {url}")
    filter_prompt = build_filter_prompt(raw_markdown)
    filtered_markdown = ""

    for attempt in range(MAX_RETRIES + 1):
        try:
            filtered_markdown = call_llm(
                filter_prompt,
                provider=provider,
                model=model,
                temperature=temperature
            )
            break
        except Exception as e:
            logger.error(f"Stage 2 filter failed for {url}, attempt {attempt + 1}: {e}")
            if attempt == MAX_RETRIES:
                # Fallback: use raw Stage 1 output rather than losing data entirely
                logger.warning(
                    f"Stage 2 filter failed after all retries — "
                    f"falling back to raw Stage 1 output for {url}"
                )
                filtered_markdown = raw_markdown

    # ── Parse filtered markdown → JSON schema ────────────────────────────────
    result = _parse_markdown_to_dict(filtered_markdown, url)
    logger.info(
        f"Extracted {len(result.get('programs', []))} program(s) from {url}"
    )
    return result
