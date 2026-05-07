import requests
from requests import HTTPError
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
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=timeout)
        response.raise_for_status()
    except RequestsConnectionError as e:
        raise OllamaNotRunningError() from e
    except RequestException as e:
        raise OllamaNotRunningError(
            f"Ollama at {OLLAMA_URL} did not respond correctly: {e}"
        ) from e


def call_ollama(
    prompt,
    temperature,
    model_name: str | None = None,
    *,
    system: str | None = None,
    json_mode: bool = False,
):
    model = (model_name or "").strip() or DEFAULT_MODEL_NAME
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if system:
        payload["system"] = system
    if json_mode:
        payload["format"] = "json"

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
            timeout=LLM_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        return data["response"]
    except HTTPError as e:
        detail = ""
        if e.response is not None and e.response.text:
            detail = (e.response.text[:400] + "...") if len(e.response.text) > 400 else e.response.text
        if e.response is not None and e.response.status_code == 404:
            raise RuntimeError(
                f"Ollama returned 404 for POST /api/generate with model {model!r}. "
                f"Usually the model is not installed - run: ollama pull {model}. "
                f"Response: {detail or '(empty)'}"
            ) from e
        raise RuntimeError(
            f"Ollama HTTP {e.response.status_code if e.response else '?'} for /api/generate: {detail or e}"
        ) from e
    except RequestsConnectionError as e:
        raise OllamaNotRunningError() from e
