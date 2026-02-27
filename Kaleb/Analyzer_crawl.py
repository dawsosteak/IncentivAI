import os
import glob
from urllib.parse import urlparse
from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate


# Change to qwen2.5 if you prefer!
model = OllamaLLM(model="llama3.2")

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

# Utility Rebate Program Analysis

## Program Details
- **Program Name:** [Extract Program Name]
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

Document URL/Source: {source}
Document Text:
{document_text}
'''


prompt = ChatPromptTemplate.from_template(template)
chain = prompt | model

def analyze_document(url_source=None, content=None):
    # Resolve the directories relative to the script's location
    base_dir = os.path.dirname(os.path.abspath(__file__))
    results_dir = os.path.join(base_dir, "analysis_results")
    
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)

    # 1. Provide a specific URL and content to analyze (e.g., from Scrapper_crawl.py)
    if url_source and content:
        domain = urlparse(url_source).netloc
        safe_domain = domain.replace(".", "_")
        if not safe_domain:
            safe_domain = "unknown_domain"
            
        result_filename = f"{safe_domain}_analysis.txt"
        result_filepath = os.path.join(results_dir, result_filename)
        
        print(f"\n{'='*60}")
        print(f"Analyzing {url_source}...")
        print(f"{'='*60}")
        
        try:
            results = chain.invoke({
                "source": url_source,
                "document_text": content
            })
            
            print(f"Results for {url_source}:\n")
            print(results)
            print("-" * 60)
            
            with open(result_filepath, "a", encoding="utf-8") as f:
                f.write(f"\n\n--- SOURCE: {url_source} ---\n\n")
                f.write(results)
                f.write("\n")
            print(f"Saved analysis to: {result_filepath}")
            
        except Exception as e:
            print(f"Error processing {url_source}: {e}")
            
        return

    # 2. Bulk analyze markdown files from 'scraped_data' (Standalone mode)
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
        safe_domain = filename.replace(".md", "")
        result_filename = f"{safe_domain}_analysis.txt"
        result_filepath = os.path.join(results_dir, result_filename)
        
        print(f"\n{'='*60}")
        print(f"Analyzing {filename}...")
        print(f"{'='*60}")
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                file_content = f.read()
            
            # Since some files can be very large, we might want to truncate or handle them carefully.
            # For now, we will pass the whole file_content, but if you hit context limits, 
            # you might need to chunk it (e.g., file_content[:10000]).
            
            results = chain.invoke({
                "source": filename,
                "document_text": file_content
            })
            
            print(f"Results for {filename}:\n")
            print(results)
            print("-" * 60)
            
            with open(result_filepath, "a", encoding="utf-8") as f:
                f.write(f"\n\n--- SOURCE: {filename} ---\n\n")
                f.write(results)
                f.write("\n")
            print(f"Saved analysis to: {result_filepath}")
            
            # Optional: Ask to continue or move to the next
            user_input = input("Press Enter to analyze the next file (or type 'exit' to quit): ")
            if user_input.lower() == 'exit':
                break
                
        except Exception as e:
            print(f"Error processing {filename}: {e}")

if __name__ == "__main__":
    analyze_document()