import json
from config import MAX_RETRIES
from modules.llm_agent import call_ollama
from utils.logger import get_logger

logger = get_logger()
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
Extract energy-related programs and incentives.

Only extract explicitly stated programs.
Do not infer.
Do not fabricate financial data.

{text}

{SCHEMA_TEMPLATE}
"""
# Process the text with retries
def process_text(text, url, temperature):
    prompt = build_prompt(text)

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = call_ollama(prompt, temperature)
            data = json.loads(response)
            return data
        except Exception as e:
            logger.error(f"JSON parsing failed for {url}, attempt {attempt}: {e}")

    raise Exception("LLM failed to return valid JSON.")