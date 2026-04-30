import json
import re
from typing import Dict, Optional

from config import MAX_RETRIES
from modules.llm_agent import OllamaNotRunningError, call_ollama
from utils.logger import get_logger

logger = get_logger()

SYSTEM_PROMPT = """
You extract structured incentive and rebate data from one provided source at a time.
Use only the supplied source text and metadata. Do not use outside knowledge.
If the source is an application form, flyer, spreadsheet, or PDF, treat it as a valid
program source when it contains concrete incentive, eligibility, or application terms.
Return only JSON that matches the requested schema.
""".strip()


def _extract_json_blob(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s)
    if fence:
        return fence.group(1).strip()

    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        return s[start : end + 1].strip()
    return s


SCHEMA_TEMPLATE = """
Return ONLY valid JSON. No markdown. No explanation. No text before or after the JSON.

{
  "utility_company": null,
  "programs": [
    {
      "program_name": null,
      "program_type": null,
      "financial_details": null,
      "eligibility": null,
      "application_process": null,
      "sector": null,
      "notes": null
    }
  ],
  "summary_of_page": null
}

Rules:
- If no programs found, programs must be [].
- If a field is not found, use null. Never leave a string field as an empty string.
- Do not infer or fabricate any information.
- Only extract explicitly stated programs.
- Preserve source wording for official names, dollar amounts, percentages, caps, rates, and deadlines.
- For financial_details: capture dollar amounts, percentages, caps, and rates verbatim from the source.
- For program_type: be specific (rebate, grant, tax credit, low-interest loan, on-bill financing, etc.).
- For sector: return a concise string such as Residential, Commercial, Industrial, Agricultural, or Mixed.
- If multiple programs exist, each must be a separate object in programs. Do not merge programs.
- If the document is only news, a blog, glossary, generic advice, or navigation with no concrete program rules,
  return "programs": [] and explain briefly in summary_of_page.
"""


def _prepare_source_text(text: str) -> str:
    prepared = (text or "").replace("\x00", " ")
    prepared = prepared.replace("\r\n", "\n").replace("\r", "\n")
    prepared = re.sub(r"[ \t]+", " ", prepared)
    prepared = re.sub(r"\n{3,}", "\n\n", prepared)
    return prepared.strip()


def build_prompt(
    text: str,
    url: str,
    *,
    source_type: str | None = None,
    title: str | None = None,
) -> str:
    prepared_text = _prepare_source_text(text)
    metadata_lines = [f"URL: {url}"]
    if source_type:
        metadata_lines.append(f"Type: {source_type}")
    if title:
        metadata_lines.append(f"Title: {title}")
    metadata = "\n".join(metadata_lines)

    return f"""
You are an expert extraction assistant for energy efficiency programs, utility rebates,
government incentives, and financial assistance programs.

SOURCE METADATA:
{metadata}

Treat this as one independent source. The source may be a web page, PDF, DOCX,
spreadsheet, application form, program flyer, or extracted OCR text.

Your task is to analyze the text and extract every energy-related program, rebate, incentive,
grant, or financial assistance opportunity that is explicitly stated.

EXTRACTION PRIORITIES:

1. FINANCIAL DETAILS - Search for dollar amounts, percentages, ranges, per-unit rates,
   annual/lifetime caps, funding pools. Capture verbatim. Do not paraphrase numbers.

2. PROGRAM NAME - Use the official name as written, or a short descriptive name grounded in the text.

3. PROGRAM TYPE - Be specific (rebate, grant, tax credit, loan, audit, weatherization, etc.).

4. ELIGIBILITY - Customer type, income rules, equipment requirements, geography, account requirements.

5. APPLICATION PROCESS - How to apply, documentation, deadlines, pre-approval, contacts.

6. SECTOR - Residential, Commercial, Industrial, Agricultural, or Mixed.

7. NOTES - Expiration, waitlists, stacking rules, disclaimers, links to more detail.

8. UTILITY COMPANY - Header, footer, copyright, domain, "offered by" lines. Use domain only if no better name appears.

STRICT GROUNDING:
- If the page is only an index, FAQ, or news without concrete program terms, return programs: [].
- Do not invent administrators, amounts, or eligibility not present in the text.
- Do not merge information from different implied sources; stick to this document only.
- If a value is paraphrased by you, keep it clearly grounded in the source text.

TEXT:
---SOURCE TEXT START---
{prepared_text}
---SOURCE TEXT END---

{SCHEMA_TEMPLATE}
"""


def _normalize_text(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _appears_in_text(needle: Optional[str], haystack: str) -> bool:
    n = _normalize_text(needle)
    h = _normalize_text(haystack)
    if not n or len(n) < 4:
        return False
    return n in h


def _row_is_grounded(data: Dict, source_text: str, url: str) -> bool:
    haystack = _normalize_text(source_text)
    utility_company = data.get("utility_company")
    programs = data.get("programs") or []

    if utility_company and not _appears_in_text(utility_company, haystack):
        logger.warning(
            f"Rejecting extraction for {url}: utility_company {utility_company!r} not found in source text"
        )
        return False

    for program in programs:
        program_name = program.get("program_name")
        financial_details = program.get("financial_details")

        if program_name and not _appears_in_text(program_name, haystack):
            logger.warning(
                f"Rejecting extraction for {url}: program_name {program_name!r} not found in source text"
            )
            return False

        if financial_details:
            has_number = bool(re.search(r"[$\d]", str(financial_details)))
            if has_number and not any(
                tok in haystack for tok in re.findall(r"[$\d][\d,\.]*", str(financial_details))
            ):
                logger.warning(
                    f"Rejecting extraction for {url}: financial_details {financial_details!r} "
                    "not grounded in source text"
                )
                return False

    if ".vermont.gov" in url.lower():
        bad_admins = ["xcel energy"]
        utility_lower = _normalize_text(utility_company)
        if utility_lower in bad_admins:
            logger.warning(
                f"Rejecting extraction for {url}: mismatched utility_company={utility_company!r}"
            )
            return False

    return True


def process_text(
    text: str,
    url: str,
    temperature: float,
    model_name: str | None = None,
    *,
    source_type: str | None = None,
    title: str | None = None,
):
    if not text or len(str(text).strip()) < 50:
        logger.warning(f"Content too short to process for {url}")
        return {
            "utility_company": None,
            "programs": [],
            "summary_of_page": "Scraped content was empty or too short.",
        }

    prompt = build_prompt(text, url, source_type=source_type, title=title)

    for attempt in range(MAX_RETRIES + 1):
        response = None
        try:
            response = call_ollama(
                prompt,
                temperature,
                model_name=model_name,
                system=SYSTEM_PROMPT,
                json_mode=True,
            )
            blob = _extract_json_blob(response)
            if not blob:
                raise ValueError("empty model response")

            data = json.loads(blob)
            if not isinstance(data, dict):
                raise ValueError("model did not return a JSON object")
            if "programs" not in data or not isinstance(data["programs"], list):
                raise ValueError("JSON missing programs list")

            if not _row_is_grounded(data, text, url):
                logger.warning(f"Ungrounded extraction rejected for {url}; returning empty result")
                return {
                    "utility_company": data.get("utility_company"),
                    "programs": [],
                    "summary_of_page": data.get("summary_of_page") or "Extraction rejected as ungrounded.",
                }

            return data

        except OllamaNotRunningError:
            raise
        except Exception as e:
            logger.warning(
                f"LLM parse/validation failed for {url} attempt {attempt + 1}/{MAX_RETRIES + 1}: {e}. "
                f"Raw response starts: {str(response)[:300] if response else '(none)'}"
            )
            if attempt >= MAX_RETRIES:
                raise ValueError(f"LLM did not return valid JSON after retries: {e}")
