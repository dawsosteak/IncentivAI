import os
import glob
import re
from urllib.parse import urlparse

from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


# ----------------------------
# Config
# ----------------------------
MODEL_NAME = "llama3.2"          # consider: "qwen2.5:7b-instruct" for better schema-following
TEMPERATURE = 0.0               # extraction = keep as close to 0 as possible
NOT_RELEVANT = "NOT RELEVANT: No concrete rebate program found."

rebate_terms = [
    "rebate", "rebates", "incentive", "incentives", "grant", "grants",
    "tax credit", "bill credit", "voucher", "refund", "cash back",
    "instant rebate", "rebate amount", "eligible for a rebate",
    "discount", "instant savings", "credit", "buydown", "coupon",
]

money_or_percent_re = re.compile(
    r"(\$[\d,]+(\.\d+)?)|(\b\d+(\.\d+)?\s*%)|\b(free|no cost)\b",
    re.IGNORECASE,
)


# ----------------------------
# LLM + Prompt (your prompt)
# ----------------------------
model = OllamaLLM(model=MODEL_NAME, temperature=TEMPERATURE)

template = '''
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
If information DOES NOT have rebate information, DON'T append to results.
DO NOT INCLUDE ANY OTHER TEXT OR EXPLANATION. ONLY THE MARKDOWN STRUCTURE WITH THE RELEVANT INFORMATION.

Document URL/Source: {source}
Document Text:
{document_text}
'''

prompt = ChatPromptTemplate.from_template(template)
chain = prompt | model | StrOutputParser()


# ----------------------------
# Helpers
# ----------------------------
def looks_like_rebate_doc(text: str) -> str:
    """
    Cheap prefilter:
      - "no"    : no rebate-ish keywords
      - "maybe" : has keywords but no obvious $/%/free/no-cost on the page (could be a hub page)
      - "high"  : has keywords + an amount/%/free/no-cost
    """
    if not text:
        return "no"
    t = text.lower()

    has_keyword = any(k in t for k in rebate_terms)
    if not has_keyword:
        return "no"

    has_amount = money_or_percent_re.search(text) is not None
    return "high" if has_amount else "maybe"


def enforce_format(text: str) -> str:
    """
    Enforce either:
      - exact NOT_RELEVANT line (without quotes), OR
      - strict markdown structure starting with '# Program Name:' and containing '#Program URL:'
    """
    t = (text or "").strip()

    # allow either quoted or unquoted NOT RELEVANT (your prompt uses quotes)
    if 'NOT RELEVANT: No concrete rebate program found.' in t:
        return NOT_RELEVANT

    start_idx = t.find("# Program Name:")
    if start_idx == -1:
        return NOT_RELEVANT

    cleaned = t[start_idx:].strip()

    # Must include the exact header used in your prompt (note: no space after #)
    if "\n#Program URL:" not in cleaned:
        return NOT_RELEVANT

    return cleaned


# ----------------------------
# Main
# ----------------------------
def analyze_document(url_source=None, content=None, interactive=False):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    results_dir = os.path.join(base_dir, "analysis_results")
    error_log_path = os.path.join(base_dir, "analysis_errors.log")
    os.makedirs(results_dir, exist_ok=True)

    def log_error(msg: str):
        print(msg)
        with open(error_log_path, "a", encoding="utf-8") as ef:
            ef.write(msg + "\n")

    # 1) Single document mode
    if url_source and content:
        domain = urlparse(url_source).netloc
        safe_domain = domain.replace(".", "_") or "unknown_domain"
        result_filepath = os.path.join(results_dir, f"{safe_domain}_analysis.md")

        print(f"\n{'='*60}\nAnalyzing {url_source}...\n{'='*60}")

        try:
            status = looks_like_rebate_doc(content)
            if status == "no":
                results = NOT_RELEVANT
            else:
                raw = chain.invoke({"source": url_source, "document_text": content})
                results = enforce_format(raw)

            print(f"Results for {url_source}:\n{results}\n" + "-" * 60)

            with open(result_filepath, "a", encoding="utf-8") as f:
                f.write(f"\n\n--- SOURCE: {url_source} ---\n\n")
                f.write(results)
                f.write("\n")
            print(f"Saved analysis to: {result_filepath}")

        except Exception as e:
            log_error(f"Error processing {url_source}: {e}")
        return

    # 2) Bulk mode
    scraped_dir = os.path.join(base_dir, "scraped_data")
    if not os.path.exists(scraped_dir):
        print(f"Error: Directory '{scraped_dir}' not found.")
        return

    markdown_files = glob.glob(os.path.join(scraped_dir, "*.md"))
    if not markdown_files:
        print(f"No markdown files found in '{scraped_dir}'.")
        return

    print(f"Found {len(markdown_files)} markdown files in '{scraped_dir}'.")

    for filepath in markdown_files:
        filename = os.path.basename(filepath)
        base_name = filename.replace(".md", "")

        # Remove 8-char hash suffix if present: domain_hash.md -> domain
        parts = base_name.rsplit("_", 1)
        safe_domain = parts[0] if (len(parts) == 2 and len(parts[1]) == 8) else base_name

        result_filepath = os.path.join(results_dir, f"{safe_domain}_analysis.md")

        # Skip if already analyzed
        if os.path.exists(result_filepath):
            try:
                with open(result_filepath, "r", encoding="utf-8") as check_f:
                    if f"--- SOURCE: {filename} ---" in check_f.read():
                        print(f"\nSkipping {filename}: Analysis already exists in {os.path.basename(result_filepath)}")
                        continue
            except Exception:
                pass

        print(f"\n{'='*60}\nAnalyzing {filename}...\n{'='*60}")

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                file_content = f.read()

            status = looks_like_rebate_doc(file_content)
            if status == "no":
                results = NOT_RELEVANT
            else:
                raw = chain.invoke({"source": filename, "document_text": file_content})
                results = enforce_format(raw)

            print(f"Results for {filename}:\n{results}\n" + "-" * 60)

            with open(result_filepath, "a", encoding="utf-8") as f:
                f.write(f"\n\n--- SOURCE: {filename} ---\n\n")
                f.write(results)
                f.write("\n")
            print(f"Saved analysis to: {result_filepath}")

        except Exception as e:
            log_error(f"Error processing {filename}: {e}")


if __name__ == "__main__":
    analyze_document(interactive=True)