import os
import threading
from config import MODEL_NAME, LLM_TIMEOUT
from utils.logger import get_logger

logger = get_logger()

# Optional provider imports — fail gracefully if not installed
try:
    import ollama as ollama_client
except ImportError:
    ollama_client = None

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None

try:
    from langchain_anthropic import ChatAnthropic
except ImportError:
    ChatAnthropic = None

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None


def build_llm(provider: str, model: str, temperature: float):
    """
    Build and return an LLM client for the given provider.
    Supports: ollama, openai, uw_ssec, anthropic, google/gemini
    """
    provider = (provider or "ollama").lower()
    model = model or MODEL_NAME

    if provider == "ollama":
        if ollama_client is None:
            raise ImportError("ollama package is not installed. Run: uv pip install ollama")
        return None  # ollama is called directly, not via langchain

    if provider == "openai":
        if ChatOpenAI is None:
            raise ImportError("langchain-openai is not installed.")
        return ChatOpenAI(model=model, temperature=temperature)

    if provider in {"uw_ssec", "uw-ssec", "ssec"}:
        if ChatOpenAI is None:
            raise ImportError("langchain-openai is not installed.")
        api_key = os.environ.get("UW_SSEC_AI_GATEWAY_KEY")
        base_url = os.environ.get("UW_SSEC_AI_GATEWAY_BASE_URL")
        if not api_key:
            raise ValueError("UW_SSEC_AI_GATEWAY_KEY environment variable is not set.")
        if not base_url:
            raise ValueError("UW_SSEC_AI_GATEWAY_BASE_URL environment variable is not set.")
        # gpt-5 series requires temperature=1
        gateway_temperature = 1 if model.startswith("gpt-5") else temperature
        return ChatOpenAI(
            model=model,
            temperature=gateway_temperature,
            api_key=api_key,
            base_url=base_url,
        )

    if provider == "anthropic":
        if ChatAnthropic is None:
            raise ImportError("langchain-anthropic is not installed.")
        return ChatAnthropic(model=model, temperature=temperature)

    if provider in {"google", "gemini"}:
        if ChatGoogleGenerativeAI is None:
            raise ImportError("langchain-google-genai is not installed.")
        return ChatGoogleGenerativeAI(model=model, temperature=temperature)

    raise ValueError(f"Unsupported provider: {provider}. Choose from: ollama, openai, uw_ssec, anthropic, google")


def call_ollama(prompt: str, temperature: float = 0.2) -> str:
    """
    Call local Ollama model with a threading-based timeout.
    Uses LLM_TIMEOUT from config to prevent hanging.
    """
    if ollama_client is None:
        raise ImportError("ollama package is not installed.")

    result = [None]
    error = [None]

    def _call():
        try:
            response = ollama_client.chat(
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


def call_llm(prompt: str, provider: str, model: str, temperature: float) -> str:
    """
    Unified LLM call that routes to the correct provider.
    For Ollama uses the native client with timeout.
    For all other providers uses langchain.
    """
    provider = (provider or "ollama").lower()

    if provider == "ollama":
        return call_ollama(prompt, temperature)

    # All non-Ollama providers go through langchain
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser

    llm = build_llm(provider, model, temperature)
    prompt_template = ChatPromptTemplate.from_template("{input}")
    chain = prompt_template | llm | StrOutputParser()
    return chain.invoke({"input": prompt})
