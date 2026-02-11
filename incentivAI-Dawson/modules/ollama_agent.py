import ollama
from config import OLLAMA_PROCESSOR_MODEL

def summarize(text):
    response = ollama.chat(
        model=OLLAMA_PROCESSOR_MODEL,
        messages=[{"role": "user", "content": text}]
    )
    return response["message"]["content"]
