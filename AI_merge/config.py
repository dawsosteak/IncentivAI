OLLAMA_URL = "http://127.0.0.1:11434"
# Dawson default; override from Streamlit sidebar or pass model_name into the pipeline.
MODEL_NAME = "qwen2.5:14b"

OLLAMA_MODEL_PRESETS = (
    "qwen2.5:14b",
    "llama3.1:8b",
    "llama3.2",
    "Custom…",
)

DEFAULT_TEMPERATURE = 1.0
DEFAULT_TRUNCATION = 30000
DEFAULT_USE_DEEP_CRAWL = True
DEFAULT_DEEP_CRAWL_TIMEOUT_SEC = 120

MAX_RETRIES = 2
LLM_TIMEOUT = 180

UI_POLL_INTERVAL_SEC = 0.25
CANCEL_BUTTON_LABEL = "Cancel extraction"

ERRORS_CSV = "errors.csv"
MARKDOWN_CSV = "markdown_output.csv"
