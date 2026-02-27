import requests
from config import OLLAMA_URL, MODEL_NAME
#Call ollama server and model with the given prompt and temperature, return the response text
def call_ollama(prompt, temperature):
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature#tempearture is how random/creative the response is, higher is more random, lower is more deterministic
        }
    }

    response = requests.post(f"{OLLAMA_URL}/api/generate", json=payload)
    response.raise_for_status()
    return response.json()["response"]
#Function is basically send prompt, get response, and return response text