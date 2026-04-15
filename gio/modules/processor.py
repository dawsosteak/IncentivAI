import json
import re
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
#Building the structure of what to extract and how to format it, with rules for how to handle missing data and multiple programs
SCHEMA_TEMPLATE = """
Return ONLY valid JSON.

{
"utility_company": "",
"programs": [
{
"program_name": "",
"program_type": "",
"financial_details": "",
"eligibility": "",
"application_process": "",
"sector": "",
"notes": ""
}
],
"summary_of_page": ""
}

Rules:
- If no programs found, programs must be [].
- If information missing, use null.
- No markdown.
- No explanation.
"""
#give the prompt to the agent, this is what we can change and write different prompts to test
def build_prompt(text):
    return f"""
You are a strict utility rebate analyst. Your job is to extract actionable utility rebate programs.

CRITICAL INSTRUCTIONS:
1. If this document is merely a news article, a blog post,
   a glossary, or general advice about energy efficiency,
   do NOT invent programs. Return an empty programs list and a short summary_of_page.
2. Only proceed if the document explicitly outlines a specific, currently active rebate,
   incentive, or grant program offered by a utility company or government entity.
3. Only extract explicitly stated programs. Do not infer. Do not fabricate financial data.
4. If the text includes multiple SOURCE sections, you may combine details, but do not duplicate programs.

{text}

{SCHEMA_TEMPLATE}
"""
# Process the text with retries
def process_text(text, url, temperature):
    if not text or not str(text).strip():
        text = "(No content was scraped for this URL.)"

    prompt = build_prompt(text)

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
                logger.error(
                    f"Ollama returned empty output for {url}, attempt {attempt}"
                )
                raise ValueError("empty model response")
            data = json.loads(blob)
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
