import json
import ollama
from config import OLLAMA_EXTRACTOR_MODEL

def safe_parse_json(text):
    """
    Tries to parse text as JSON.
    If it fails, returns an empty dict and prints debug info.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print("WARNING: Failed to parse JSON from LLM output:")
        print(text[:500])  # print first 500 chars for debugging
        return {}

def extract(summary, url):
    # stricter prompt with explicit JSON requirement and example
    prompt = f"""
You are a helpful assistant. Extract clean energy incentive data from the summary below.

Return ONLY **valid JSON** with keys:
- incentive_name
- financial_incentive
- company_name
- location

Example output:
{{
  "incentive_name": "Solar Rebate",
  "financial_incentive": "$500",
  "company_name": "Brenham Utilities",
  "location": "Brenham, TX"
}}

SUMMARY:
{summary}
"""

    # Create Ollama client
    client = ollama.Client()  # assumes Ollama server is running locally

    response = client.chat(
        model=OLLAMA_EXTRACTOR_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )

    # Safely parse JSON
    data = safe_parse_json(response["message"]["content"])

    # Always add the URL
    data["source_url"] = url

    return data

