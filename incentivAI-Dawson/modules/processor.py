import re
import json
from config import MAX_RETRIES, DEFAULT_TRUNCATION
from modules.llm_agent import call_llm
from utils.logger import get_logger

logger = get_logger()

SCHEMA_TEMPLATE = """
Return ONLY valid JSON. No markdown. No explanation. No text before or after the JSON.

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
- If a field is not found, use null. Never leave a field blank.
- Do not infer or fabricate any information.
- Only extract explicitly stated programs.
- For financial_details: any number, dollar sign, percentage, or rate near a program
  description counts — capture it verbatim from the source text.
- For program_type: be specific (e.g. "rebate", "grant", "tax credit", "low-interest loan",
  "on-bill financing", "weatherization assistance") rather than generic.
- For sector: use one or more of Residential, Commercial, Industrial, Agricultural.
  If the page applies to multiple sectors, list all that apply.
- If multiple programs exist on the page, every single one must be included as a separate
  object in the programs array. Do not merge or summarize multiple programs into one.
- For utility_company: never leave this null if any organization name appears anywhere
  in the text. Use the domain name as a last resort.
"""


def build_prompt(text: str, url: str = "") -> str:
    """
    Build the LLM extraction prompt.
    Truncates input, includes source URL as context hint,
    and provides detailed field-by-field extraction instructions.
    """
    truncated = text[:DEFAULT_TRUNCATION]
    source_hint = f"Source URL: {url}\n\n" if url else ""

    return f"""
You are an expert data extraction assistant specializing in energy efficiency programs,
utility rebates, government incentives, and financial assistance programs.

Your task is to carefully analyze the text below and extract every energy-related program,
rebate, incentive, grant, or financial assistance opportunity that is explicitly mentioned.

EXTRACTION INSTRUCTIONS:

1. FINANCIAL DETAILS — This is the most important field. Search aggressively for any of:
   - Dollar amounts (e.g. "$500", "$1,200", "$50,000")
   - Percentage discounts or coverage (e.g. "50% of project cost", "up to 75%")
   - Ranges (e.g. "$100 to $500", "between $200 and $2,000")
   - Per-unit rates (e.g. "$0.10 per kWh", "$50 per ton")
   - Annual or lifetime caps (e.g. "up to $3,000 per year", "$10,000 lifetime maximum")
   - Funding pool sizes (e.g. "program has $2 million in available funding")
   - Any numeric value appearing near or within a program description
   Capture these values VERBATIM as they appear in the source text. Do not paraphrase.

   Examples:
   "Rebate of $500 for qualifying heat pumps"        → "$500"
   "Covers up to 50% of installation costs"          → "up to 50% of installation costs"
   "Annual incentive not to exceed $2,000"           → "not to exceed $2,000 annually"
   "$0.10 per kWh saved"                             → "$0.10 per kWh"
   If you see ANY dollar sign, percentage, or per-unit rate — capture it.

2. PROGRAM NAME — Use the full official name as written. If no formal name exists,
   construct a descriptive name from the context (e.g. "Residential Heat Pump Rebate").

3. PROGRAM TYPE — Be as specific as possible:
   Rebate, Grant, Tax Credit, Low-Interest Loan, On-Bill Financing,
   Weatherization Assistance, Energy Audit, Free Equipment, Buy-Down Program,
   Performance Incentive, or any other specific type mentioned.

4. ELIGIBILITY — Extract all qualifying conditions including:
   - Customer type (residential, commercial, industrial, agricultural)
   - Income limits or low-income designations
   - Equipment or technology requirements (e.g. "must be ENERGY STAR certified")
   - Geographic restrictions (e.g. "available only in service territory")
   - Utility account requirements (e.g. "must be an active customer")
   - Any other stated conditions for qualification

   Examples of what to look for:
   "Must be a residential customer in our service territory"
   "Income at or below 80% of Area Median Income"
   "Equipment must be ENERGY STAR certified"
   "Available to small commercial customers under 200kW demand"
   Capture ALL conditions stated — do not summarize.

5. APPLICATION PROCESS — Extract any information about:
   - How to apply (online portal, mail-in form, contractor submission)
   - Required documentation
   - Deadlines or application windows
   - Contact information or where to submit
   - Pre-approval requirements

6. SECTOR — Identify all applicable sectors:
   Residential, Commercial, Industrial, Agricultural.
   If the program serves multiple sectors, list all of them.

7. NOTES — Capture any additional context including:
   - Program expiration dates or funding exhaustion warnings
   - Waitlists or limited availability notices
   - Stacking rules (e.g. "cannot be combined with federal tax credit")
   - Important disclaimers or conditions not captured elsewhere
   - Links or references to additional program details

8. UTILITY COMPANY — Search aggressively for the organization name by looking at:
   - The page header, logo text, or site title
   - Any "About Us", "Contact", or copyright footer mentions
   - The domain name itself (e.g. "pge.com" → "Pacific Gas & Electric")
   - Any "offered by", "provided by", "administered by" phrases in the text
   - Organization names near program descriptions
   Never leave this null if any organization name appears anywhere in the text.

IMPORTANT REMINDERS:
- Extract EVERY program mentioned, no matter how briefly.
- Do NOT merge separate programs into one entry.
- Do NOT fabricate or infer any data not explicitly present in the text.
- If a field truly cannot be found, use null — never guess.
- Financial amounts are critical — look for any number near a program description.
- Company name is critical — look everywhere in the text for any organization name.
- If this page is a news article, blog post, or general advice with no concrete program, 
  return programs as [] and note it in summary_of_page.

TEXT:
\"\"\"
{source_hint}{truncated}
\"\"\"

{SCHEMA_TEMPLATE}
"""


def process_text(text: str, url: str, temperature: float,
                 provider: str = "ollama", model: str = None) -> dict:
    """
    Run LLM extraction on scraped text.
    Retries up to MAX_RETRIES times on JSON parse failure.
    Strips markdown fences before parsing.

    Args:
        text:        scraped page content
        url:         source URL (used in prompt and error logging)
        temperature: LLM temperature
        provider:    LLM provider (ollama, openai, uw_ssec, etc.)
        model:       model name override (uses config default if None)

    Returns:
        dict matching the JSON schema
    """
    from config import MODEL_NAME
    model = model or MODEL_NAME

    if not text or len(text) < 50:
        logger.warning(f"Content too short to process for {url}")
        return {
            "utility_company": None,
            "programs": [],
            "summary_of_page": "Scraped content was empty or too short."
        }

    prompt = build_prompt(text, url=url)

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = call_llm(prompt, provider=provider, model=model, temperature=temperature)

            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
                cleaned = re.sub(r"\n?```$", "", cleaned)

            data = json.loads(cleaned)
            return data

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed for {url}, attempt {attempt + 1}: {e}")
        except Exception as e:
            logger.error(f"LLM call failed for {url}, attempt {attempt + 1}: {e}")

    raise Exception(f"LLM failed to return valid JSON after {MAX_RETRIES + 1} attempts for {url}.")
