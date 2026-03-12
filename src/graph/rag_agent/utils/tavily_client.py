"""
Tavily search wrapper. Env: TAVILY_API_KEY or TAVILY_SEARCH_KEY.
"""
from typing import Any

from src.utils.env import load_env, get_env

load_env()


def get_tavily_client():
    key = get_env("TAVILY_API_KEY") or get_env("TAVILY_SEARCH_KEY")
    if not key:
        raise RuntimeError("TAVILY_API_KEY or TAVILY_SEARCH_KEY is required")
    from tavily import TavilyClient
    return TavilyClient(api_key=key)


def tavily_search(
    query: str,
    max_results: int = 5,
    search_depth: str = "advanced",
    topic: str | None = "finance",
) -> dict[str, Any]:
    client = get_tavily_client()
    params = {
        "query": query,
        "search_depth": search_depth,
        "include_answer": False,
        "include_images": False,
        "include_raw_content": False,
        "max_results": max_results,
    }
    if topic:
        params["topic"] = topic
    return client.search(**params)


def extract_contexts_from_tavily(
    tavily_result: dict,
    max_contexts: int = 5,
) -> tuple[list[str], list[dict]]:
    contexts = []
    sources = []
    for item in (tavily_result.get("results") or [])[:max_contexts]:
        title = item.get("title") or "No title"
        url = item.get("url") or ""
        content = item.get("content") or item.get("raw_content") or ""
        if not content:
            continue
        sources.append({"title": title, "url": url, "content": content})
        contexts.append(f"Source: {title}\nURL: {url}\n\nContent:\n{content}")
    return contexts, sources
