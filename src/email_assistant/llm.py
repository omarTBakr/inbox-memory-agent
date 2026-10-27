"""Chat and embedding models from the `model` / `embeddings` config sections.

Providers: Ollama (local) or an API (Anthropic, OpenAI, OpenAI-compatible, Google Gemini).
Pass a config to build a model that is not saved yet (e.g. the UI's probe).
"""

from langchain.chat_models import init_chat_model
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from email_assistant import config_store
from email_assistant.config_models import EmbeddingsConfig, ModelConfig

# config provider -> langchain init_chat_model provider
_LANGCHAIN_PROVIDER = {
    "anthropic": "anthropic",
    "openai": "openai",
    "openai_compatible": "openai",
    "google_genai": "google_genai",
}


def model_config() -> ModelConfig:
    return config_store.section("model")


def get_chat_model(cfg: ModelConfig | None = None, api_key: str | None = None, **overrides) -> BaseChatModel:
    cfg = cfg or model_config()
    if cfg.provider == "ollama":
        from langchain_ollama import ChatOllama

        params = {
            "model": cfg.model,
            "base_url": cfg.resolved_base_url(),
            "temperature": cfg.temperature,
            "num_ctx": cfg.num_ctx,
            "reasoning": cfg.reasoning,
        }
        return ChatOllama(**(params | overrides))
    params = {
        "model_provider": _LANGCHAIN_PROVIDER[cfg.provider],
        "temperature": cfg.temperature,
        "api_key": api_key if api_key is not None else config_store.secret("model", "api_key"),
    }
    if cfg.provider in ("openai", "openai_compatible"):
        params["base_url"] = cfg.resolved_base_url()
    return init_chat_model(cfg.model, **(params | overrides))


def structured_output_method(cfg: ModelConfig | None = None) -> str:
    return (cfg or model_config()).resolved_structured_output()


def embeddings_config() -> EmbeddingsConfig:
    return config_store.section("embeddings")


def get_embeddings(cfg: EmbeddingsConfig | None = None, api_key: str | None = None) -> Embeddings:
    cfg = cfg or embeddings_config()
    key = api_key if api_key is not None else config_store.secret("embeddings", "api_key")
    if cfg.provider == "ollama":
        from langchain_ollama import OllamaEmbeddings

        return OllamaEmbeddings(model=cfg.model, base_url=cfg.resolved_base_url())
    if cfg.provider in ("openai", "openai_compatible"):
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=cfg.model, api_key=key, base_url=cfg.resolved_base_url(), dimensions=cfg.dims)
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(model=cfg.model, google_api_key=key)
