OLLAMA_URL = "http://127.0.0.1:11434"
MODEL_NAME = "llama3.1:8b"

DEFAULT_TEMPERATURE = 0.0
DEFAULT_TRUNCATION = 30000
MAX_RETRIES = 1

# Background pipeline + cancel UI (Streamlit polls while the worker thread runs)
UI_POLL_INTERVAL_SEC = 0.25
CANCEL_BUTTON_LABEL = "Cancel extraction"
