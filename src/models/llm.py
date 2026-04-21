"""
Standalone LLM client for this package.
"""
import os
import time
from typing import Literal, Optional

from openai import OpenAI
from openai import RateLimitError, APIError, APIConnectionError, APITimeoutError

from src.utils.env import load_env, get_env

DEFAULT_MODEL_CONFIG = {
    "frequency_penalty": 0,
    "max_tokens": 4096,
    "presence_penalty": 0,
    "top_p": 1,
}

_client: Optional[OpenAI] = None


def _resolve_openai_api_key() -> str:
    """Lazily load .env and read OPENAI_API_KEY. Raises only when the key is actually needed."""
    load_env()
    key = get_env("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set in environment or .env file")
    return key


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=_resolve_openai_api_key(),
            timeout=100,
            max_retries=3,
        )
    return _client


LLMRole = Literal["planner", "generic", "sql", "rag", "aggregation", "summarizer", "fraud"]
ROLE_DEFAULTS = {
    "planner": {"model_name": "gpt-4.1", "temperature": 0.1},
    "generic": {"model_name": "gpt-4.1", "temperature": 0.1},
    "sql": {"model_name": "gpt-4.1", "temperature": 0.0},
    "rag": {"model_name": "gpt-4.1", "temperature": 0.0},
    "aggregation": {"model_name": "gpt-4.1", "temperature": 0.2},
    "summarizer": {"model_name": "gpt-4.1", "temperature": 0.1},
    "fraud": {"model_name": "gpt-4.1", "temperature": 0.0},
}

_llm_cache: dict = {}


class OpenAIChatLLM:
    def __init__(
        self,
        client: OpenAI,
        model_name: str,
        config: Optional[dict] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.client = client
        self.model_name = model_name
        self.config = (config or DEFAULT_MODEL_CONFIG).copy()
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _retry_with_backoff(self, func, *args, **kwargs):
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except (RateLimitError, APIConnectionError, APITimeoutError, APIError) as e:
                last_exception = e
                if attempt == self.max_retries - 1:
                    raise
                delay = self.retry_delay * (2 ** attempt)
                time.sleep(delay)
            except Exception:
                raise
        if last_exception:
            raise last_exception

    def chat(self, system_prompt: str, user_prompt: str):
        kwargs = self.config.copy()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response = self._retry_with_backoff(
            self.client.chat.completions.create,
            model=self.model_name,
            messages=messages,
            **kwargs,
        )
        return response.choices[0].message.content

    def chat_messages(self, system_prompt: str, messages: list[dict]) -> str:
        """Multi-turn: messages is list of {'role': 'user'|'assistant', 'content': str}."""
        kwargs = self.config.copy()
        full = [{"role": "system", "content": system_prompt}] + messages
        response = self._retry_with_backoff(
            self.client.chat.completions.create,
            model=self.model_name,
            messages=full,
            **kwargs,
        )
        return response.choices[0].message.content


def get_llm(
    role: LLMRole = "generic",
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
    **kwargs,
) -> OpenAIChatLLM:
    defaults = ROLE_DEFAULTS.get(role, ROLE_DEFAULTS["generic"])
    final_model_name = model_name or defaults["model_name"]
    final_temperature = temperature if temperature is not None else defaults["temperature"]
    cache_key = f"{role}:{final_model_name}:{final_temperature}"
    if cache_key not in _llm_cache:
        config = DEFAULT_MODEL_CONFIG.copy()
        config["temperature"] = final_temperature
        _llm_cache[cache_key] = OpenAIChatLLM(
            client=get_client(),
            model_name=final_model_name,
            config=config,
            max_retries=kwargs.get("max_retries", 3),
            retry_delay=kwargs.get("retry_delay", 1.0),
        )
    return _llm_cache[cache_key]


def get_model_name(role: LLMRole = "generic") -> str:
    """Return the model name for a role (e.g. for LangChain create_agent model string)."""
    defaults = ROLE_DEFAULTS.get(role, ROLE_DEFAULTS["generic"])
    return defaults["model_name"]


def get_create_agent_model_string(role: LLMRole) -> str:
    """Return the model string expected by LangChain create_agent (e.g. 'openai:gpt-4.1')."""
    return f"openai:{get_model_name(role)}"


def get_langchain_chat_model(role: LLMRole = "generic"):
    """
    Return a LangChain ChatOpenAI instance for the given role.
    Use this when a LangChain BaseChatModel is required (e.g. ConversationSummaryBufferMemory).
    Config is read from ROLE_DEFAULTS; API key from env.
    """
    from langchain_openai import ChatOpenAI
    defaults = ROLE_DEFAULTS.get(role, ROLE_DEFAULTS["generic"])
    api_key = _resolve_openai_api_key()
    return ChatOpenAI(
        model=defaults["model_name"],
        temperature=defaults["temperature"],
        api_key=api_key,
    )
