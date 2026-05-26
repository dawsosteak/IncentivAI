1. Install Python 3.11+ and check it works: `python --version` (make sure it's within VS code and packages) 
2. Install uv: Open PowerShell and run `iwr https://astral.sh/uv/install.ps1 -useb | iex`, then `uv --version`  
3. Download this repo and navigate to it in PowerShell: `cd C:\Your Path\IncentivAI\incentivAI-Dawson`  
4. Initialize uv project: `uv init incentivai`  
5. do:
 uv sync
6. activate virtual environment
   .venv\Scripts\Activate.ps1 (For Windows PC) source .venv/bin/activate (for Mac/linux PC)
Might need to do:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser 
if running into any errors
7. install ollama from webbrowser and then do 
ollama pull llama3.1:8b
8. start ollama server: 
ollama serve
9. install playwright:
 playwright install 
then do 
playwright install chromium
uv run streamlit run app.py