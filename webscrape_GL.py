import beautifulsoup4 as bs
import requests

url = "https://www.google.com"

response = requests.get(url)

soup = bs(response.text, "html.parser")

print(soup.prettify())