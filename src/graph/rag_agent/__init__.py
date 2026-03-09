def run_rag_agent(*args, **kwargs):
    from src.graph.rag_agent.pipeline import run_rag_agent as _run
    return _run(*args, **kwargs)


__all__ = ["run_rag_agent"]
