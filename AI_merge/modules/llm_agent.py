import time

import requests
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import RequestException

from config import OLLAMA_URL, MODEL_NAME as DEFAULT_MODEL_NAME, LLM_TIMEOUT


class OllamaNotRunningError(RuntimeError):
    def __init__(self, message=None):
        super().__init__(
            message
            or (
                f"Ollama is not running or not reachable at {OLLAMA_URL}. "
                "Start the server (e.g. run `ollama serve`), then try again."
            )
        )


def ensure_ollama_running(timeout=5):
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=timeout)
        r.raise_for_status()
    except RequestsConnectionError as e:
        raise OllamaNotRunningError() from e
    except RequestException as e:
        raise OllamaNotRunningError(
            f"Ollama at {OLLAMA_URL} did not respond correctly: {e}"
        ) from e


def call_ollama(prompt, temperature, model_name: str | None = None):
    model = (model_name or "").strip() or DEFAULT_MODEL_NAME
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
            timeout=LLM_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()["response"]
    except RequestsConnectionError as e:
        raise OllamaNotRunningError() from e
