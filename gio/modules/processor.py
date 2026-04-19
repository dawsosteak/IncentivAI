import json
import re
from typing import Dict, List, Optional

from config import MAX_RETRIES
from modules.llm_agent import OllamaNotRunningError, call_ollama
from utils.logger import get_logger

logger = get_logger()


def _extract_json_blob(raw: str) -> str:
    """Strip whitespace and optional ```json ... ``` fences from model output."""
    s = (raw or "").strip()
    if not s:
        return ""
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s)
    if fence:
        return fence.group(1).strip()
    return s


SCHEMA_TEMPLATE = """
Return ONLY valid JSON.

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
  "summary_of_page": ""
}

Rules:
- If no explicit incentive programs are found, programs must be [].
- If information is missing, use null.
- Do not infer or guess.
- Do not merge information from different documents.
- No markdown.
- No explanation.
"""


def build_prompt(text: str, url: str) -> str:
    return f"""
You are a strict information extraction system for energy incentives.

You are given ONE source document from the URL below.

SOURCE URL:
{url}

Your task is to extract only incentive programs that are explicitly described in this document.

CRITICAL INSTRUCTIONS:
1. Extract programs only if the document explicitly describes a specific rebate, grant, tax credit, loan, bill credit, or incentive program.
2. If this document is only a navigation page, resource hub, index page, news article, blog post, glossary, FAQ, or general advice page, return "programs": [].
3. Do not infer program details from general context.
4. Do not invent utility companies, administrators, rebate amounts, eligibility rules, or application steps.
5. The utility company and each program must be grounded in the source text itself.
6. If the document links to other pages or PDFs but does not itself state the program details, return "programs": [] and summarize that this page is a resource/link page.
7. Treat this as a single-source extraction task only.

DOCUMENT TEXT:
{text}

{SCHEMA_TEMPLATE}
"""


def _normalize_text(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _appears_in_text(needle: Optional[str], haystack: str) -> bool:
    n = _normalize_text(needle)
    h = _normalize_text(haystack)
    if not n:
        return False
    # require a reasonably meaningful string
    if len(n) < 4:
        return False
    return n in h


def _row_is_grounded(data: Dict, source_text: str, url: str) -> bool:
    """
    Reject obviously hallucinated outputs.
    """
    haystack = _normalize_text(source_text)

    utility_company = data.get("utility_company")
    programs = data.get("programs") or []

    # If utility company is present, it should appear in the text
    if utility_company and not _appears_in_text(utility_company, haystack):
        logger.warning(
            f"Rejecting extraction for {url}: utility_company {utility_company!r} not found in source text"
        )
        return False

    for program in programs:
        program_name = program.get("program_name")
        financial_details = program.get("financial_details")

        # Program name should appear explicitly in the page text
        if program_name and not _appears_in_text(program_name, haystack):
            logger.warning(
                f"Rejecting extraction for {url}: program_name {program_name!r} not found in source text"
            )
            return False

        # If financial details look specific, require at least some numeric grounding
        if financial_details:
            has_number = bool(re.search(r"[$\d]", str(financial_details)))
            if has_number and not any(tok in haystack for tok in re.findall(r"[$\d][\d,\.]*", str(financial_details))):
                logger.warning(
                    f"Rejecting extraction for {url}: financial_details {financial_details!r} not grounded in source text"
                )
                return False

    # Optional hard guard for known bad mismatch pattern
    if ".vermont.gov" in url.lower():
        bad_admins = ["xcel energy"]
        utility_lower = _normalize_text(utility_company)
        if utility_lower in bad_admins:
            logger.warning(
                f"Rejecting extraction for {url}: obviously mismatched utility_company={utility_company!r}"
            )
            return False

    return True


def process_text(text: str, url: str, temperature: float):
    if not text or not str(text).strip():
        text = "(No content was scraped for this URL.)"

    prompt = build_prompt(text, url)

    print(
        f"[Ollama] Starting extraction for {url} (prompt_chars={len(prompt)})",
        flush=True,
    )

    for attempt in range(MAX_RETRIES + 1):
        response = None
        try:
            if attempt > 0:
                print(
                    f"[Ollama] Retry {attempt + 1}/{MAX_RETRIES + 1} for {url}",
                    flush=True,
                )

            response = call_ollama(prompt, temperature)
            blob = _extract_json_blob(response)
            if not blob:
                logger.error(f"Ollama returned empty output for {url}, attempt {attempt}")
                raise ValueError("empty model response")

            data = json.loads(blob)

            if not isinstance(data, dict):
                raise ValueError("model did not return a JSON object")

            if "programs" not in data or not isinstance(data["programs"], list):
                raise ValueError("JSON missing programs list")

            # Reject ungrounded hallucinations
            if not _row_is_grounded(data, text, url):
                logger.warning(f"Ungrounded extraction rejected for {url}; returning empty result")
                return {
                    "utility_company": None,
                    "programs": [],
                    "summary_of_page": "The page did not contain explicitly grounded incentive program details."
                }

            print(f"[Ollama] Parsed JSON OK for {url}", flush=True)
            return data

        except OllamaNotRunningError:
            raise
        except Exception as e:
            r = response if isinstance(response, str) else ""
            preview = (r[:400] + "…") if len(r) > 400 else r
            logger.error(
                f"JSON parsing failed for {url}, attempt {attempt}: {e} "
                f"(response preview: {preview!r})"
            )

    raise RuntimeError("LLM failed to return valid JSON after retries.")