#!/usr/bin/env python

import requests
import html2text
import os
from urllib.parse import urlparse

def download_and_convert_to_md(url_list):
    """
    Downloads content from a list of URLs and saves each as a Markdown file.
    """
    # Configure html2text
    h = html2text.HTML2Text()
    h.body_width = 0 # Disable wrapping of lines
    h.ignore_links = False # Preserve links
    h.ignore_images = False # Preserve images
    
    for url in url_list:
        try:
            # 1. Fetch the content from the URL
            response = requests.get(url, allow_redirects=True, timeout=10)
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            html_content = response.text
            
            # 2. Convert HTML to Markdown
            # Set the baseurl for resolving relative links
            h.baseurl = url
            markdown_content = h.handle(html_content)
            
            # 3. Determine a filename
            # Use the domain name and path to create a meaningful filename
            parsed_url = urlparse(url)
            # Create a basic filename, clean it to be filesystem-safe
            filename = parsed_url.netloc + parsed_url.path
            if not filename.endswith('.md'):
                filename += '.md'
            # Simplify the filename to avoid deep directory structures for this example
            filename = filename.replace('/', '_').replace(':', '')
            filename = os.path.join("downloads", filename)
            
            # Ensure the directory exists if needed, but for simplicity, save in current dir
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            #print(f"Successfully saved {url} to {filename}")
            print(".", end="")

        except requests.exceptions.RequestException as e:
            #print(f"Error downloading {url}: {e}")
            print("E")
        except Exception as e:
            #print(f"An unexpected error occurred for {url}: {e}")
            print("U")
    print("\ndone");

def main():
    # List of URLs to download
    urls_to_scrape = []
    file_path = 'urls.txt'
    print(f"reading urls from {file_path}")
    with open(file_path, 'r') as file:
        for line in file:
            urls_to_scrape.append(line.strip()) # strip() removes leading/trailing whitespace and newline characters
    print(f"found {len(urls_to_scrape)} urls in file {file_path}")
    download_and_convert_to_md(urls_to_scrape)

if __name__ == "__main__":
    main()
