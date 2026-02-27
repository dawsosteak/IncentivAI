1. Install Python 3.11+ and check it works: `python --version`  
2. Install uv: Open PowerShell and run `iwr https://astral.sh/uv/install.ps1 -useb | iex`, then `uv --version`  
3. Download this repo and navigate to it in PowerShell: `cd C:\Path\To\IncentivAI`  
4. Initialize uv project: `uv init incentivai`  
5. do uv sync
6. 
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
7. install ollama and do ollama pull llama3.1:8b
8. start ollama server: ollama serve
9. playwright install 
then do 
playwright install chromium
uv run streamlit run app.py