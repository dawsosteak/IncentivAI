import time

import requests
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import RequestException

from config import OLLAMA_URL, MODEL_NAME


class OllamaNotRunningError(RuntimeError):
    """Raised when the Ollama HTTP API is unreachable (server not started or wrong host/port)."""

    def __init__(self, message=None):
        super().__init__(
            message
            or (
                f"Ollama is not running or not reachable at {OLLAMA_URL}. "
                "Start the server (e.g. run `ollama serve` in a terminal), then try again."
            )
        )


def ensure_ollama_running(timeout=5):
    """
    Fail fast before scraping if Ollama is not accepting connections.
    Uses GET /api/tags (Ollama HTTP API).
    """
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=timeout)
        r.raise_for_status()
    except RequestsConnectionError as e:
        raise OllamaNotRunningError() from e
    except RequestException as e:
        raise OllamaNotRunningError(
            f"Ollama at {OLLAMA_URL} did not respond correctly: {e}"
        ) from e


def call_ollama(prompt, temperature):
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }

    try:
        n_chars = len(prompt) if prompt else 0
        print(
            f"[Ollama] POST /api/generate model={MODEL_NAME} "
            f"prompt_chars={n_chars} temperature={temperature} …",
            flush=True,
        )
        t0 = time.perf_counter()
        response = requests.post(
            f"{OLLAMA_URL}/api/generate", json=payload, timeout=600
        )
        response.raise_for_status()
        text = response.json()["response"]
        elapsed = time.perf_counter() - t0
        out_len = len(text) if text else 0
        print(
            f"[Ollama] Response received in {elapsed:.1f}s, output_chars={out_len}",
            flush=True,
        )
        return text
    except RequestsConnectionError as e:
        raise OllamaNotRunningError() from e
