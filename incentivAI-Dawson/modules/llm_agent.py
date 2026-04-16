import ollama
import threading
from config import MODEL_NAME, LLM_TIMEOUT
from utils.logger import get_logger

logger = get_logger()

def call_ollama(prompt: str, temperature: float = 0.2) -> str:
    result = [None]
    error = [None]

    def _call():
        try:
            response = ollama.chat(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": temperature}
            )
            result[0] = response["message"]["content"]
        except Exception as e:
            error[0] = e

    thread = threading.Thread(target=_call)
    thread.start()
    thread.join(LLM_TIMEOUT)

    if thread.is_alive():
        raise TimeoutError(f"LLM call timed out after {LLM_TIMEOUT}s")
    if error[0]:
        raise error[0]

    return result[0]