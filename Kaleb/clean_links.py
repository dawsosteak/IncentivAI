import os
import re
import glob

base_dir = os.path.dirname(os.path.abspath(__file__))
scraped_dir = os.path.join(base_dir, "scraped_data")

files = glob.glob(os.path.join(scraped_dir, "*.md"))

def link_replacer(match):
    text = match.group(1)
    url = match.group(2)
    important_keywords = ['pdf', 'doc', 'form', 'apply', 'application', 'rebate', 'incentive', 'grant', 'program', 'login', 'register']
    if any(k in url.lower() for k in important_keywords) or any(k in text.lower() for k in important_keywords):
        return match.group(0) # Keep full link
    return text # Strip URL, keep text

count = 0
for filepath in files:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
        
    cleaned_content = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', link_replacer, content)
    
    if content != cleaned_content:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(cleaned_content)
        count += 1
        
print(f"Cleaned up {count} markdown files by removing non-essential links.")
