"""
modules/llm_agent.py — Builds the LLM instance and exposes ready-to-use chains.
"""

import os
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_ollama.llms import OllamaLLM

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

from config import EXTRACTION_TEMPLATE, FILTER_TEMPLATE


def build_llm(provider: str, model: str, temperature: float):
    """
    Instantiate and return an LLM based on the selected provider.

    Supported providers: ollama, openai, anthropic, google/gemini
    """
    provider = (provider or "ollama").lower()
    model = model or "llama3.2"

    if provider == "ollama":
        return OllamaLLM(model=model, temperature=temperature)

    if provider == "openai":
        if ChatOpenAI is None:
            raise ImportError("langchain-openai is not installed.")
        return ChatOpenAI(model=model, temperature=temperature)

    if provider == "anthropic":
        if ChatAnthropic is None:
            raise ImportError("langchain-anthropic is not installed.")
        return ChatAnthropic(model=model, temperature=temperature)

    if provider in {"google", "gemini"}:
        if ChatGoogleGenerativeAI is None:
            raise ImportError("langchain-google-genai is not installed.")
        return ChatGoogleGenerativeAI(model=model, temperature=temperature)

    raise ValueError(f"Unsupported provider: {provider}")


def build_extraction_chain(provider: str, model: str, temperature: float):
    """Return a LangChain chain for rebate extraction."""
    llm = build_llm(provider, model, temperature)
    prompt = ChatPromptTemplate.from_template(EXTRACTION_TEMPLATE)
    return prompt | llm | StrOutputParser()


def build_filter_chain(provider: str, model: str, temperature: float):
    """Return a LangChain chain for final filtering / consolidation."""
    llm = build_llm(provider, model, temperature)
    prompt = ChatPromptTemplate.from_template(FILTER_TEMPLATE)
    return prompt | llm | StrOutputParser()
