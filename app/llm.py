from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama

from app.config import get_settings


def get_strategist_llm():
    settings = get_settings()
    if settings.llm_provider.lower() == "ollama":
        return ChatOllama(
            model=settings.strategist_model,
            base_url=settings.ollama_base_url,
            temperature=0.2,
        )
    return ChatGoogleGenerativeAI(
        model="gemini-1.5-pro",
        google_api_key=settings.google_api_key,
        temperature=0.2,
        max_tokens=1024,
    )


def get_question_setter_llm():
    settings = get_settings()
    if settings.llm_provider.lower() == "ollama":
        return ChatOllama(
            model=settings.question_setter_model,
            base_url=settings.ollama_base_url,
            temperature=0.6,
        )
    return ChatAnthropic(
        model="claude-3-5-sonnet-20241022",
        api_key=settings.anthropic_api_key,
        temperature=0.6,
        max_tokens=2048,
    )


def get_evaluator_llm():
    settings = get_settings()
    if settings.llm_provider.lower() == "ollama":
        return ChatOllama(
            model=settings.evaluator_model,
            base_url=settings.ollama_base_url,
            temperature=0.1,
        )
    return ChatAnthropic(
        model="claude-3-5-sonnet-20241022",
        api_key=settings.anthropic_api_key,
        temperature=0.1,
        max_tokens=3000,
    )
