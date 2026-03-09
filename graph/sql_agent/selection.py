"""
Pairwise selection: compare all pairs of candidates in parallel, pick winner by vote count.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

from refactored.models.llm import get_llm
from refactored.graph.sql_agent.utils.prompts import system_pairwise, user_pairwise


def _compare_pair(
    question: str,
    schema: str,
    sql_a: str,
    sql_b: str,
    idx_a: int,
    idx_b: int,
) -> tuple[int, int]:
    llm = get_llm(role="sql", temperature=0.0)
    raw = llm.chat(
        system_prompt=system_pairwise(),
        user_prompt=user_pairwise(question, schema, sql_a, sql_b),
    )
    choice = (raw or "").strip().upper()
    if choice == "B":
        return idx_b, idx_a
    return idx_a, idx_b


def pairwise_select(
    candidates: list[str],
    question: str,
    schema: str,
    max_workers: int = 4,
) -> int:
    n = len(candidates)
    if n <= 1:
        return 0
    scores = [0] * n
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(
                _compare_pair,
                question,
                schema,
                candidates[i],
                candidates[j],
                i,
                j,
            ): (i, j)
            for i, j in pairs
        }
        for fut in as_completed(futures):
            try:
                winner, _ = fut.result()
                scores[winner] += 1
            except Exception:
                pass
    best = 0
    for i in range(1, n):
        if scores[i] > scores[best]:
            best = i
    return best
