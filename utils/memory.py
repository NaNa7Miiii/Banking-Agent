"""
Conversation memory for refactored. Redis-backed chat history with summary buffer.
No dependency on src.

Redis keys:
- Chat messages: message_store:<session_id> (session_id = conversation:{cid}:{sid}).
- Moving summary: conversation_summary:{cid}:{sid} (persisted so summary survives across requests).

Writing a turn to memory:
  Use save_context_and_persist(memory, cid, sid, user_input, output_str) only.
  Do not call memory.save_context(...) or save_summary(...) separately; summary would not be persisted.

Note: ConversationSummaryBufferMemory is deprecated (langchain_classic 0.3.1+). Current
code remains valid until removal in 1.0. To suppress the deprecation warning:
  import warnings
  warnings.filterwarnings("ignore", message=".*ConversationSummaryBufferMemory.*", category=LangChainDeprecationWarning)
Future migration: see https://python.langchain.com/docs/versions/migrating_memory/
"""
from typing import Optional

from langchain_classic.memory.summary_buffer import ConversationSummaryBufferMemory
from langchain_community.chat_message_histories import RedisChatMessageHistory

from refactored.utils.env import load_env, get_env


class RedisTrimmingSummaryBufferMemory(ConversationSummaryBufferMemory):
    """
    ConversationSummaryBufferMemory that after prune() also rewrites Redis to only
    contain the remaining messages, so the chat list does not grow unbounded.
    """

    def prune(self) -> None:
        # Work on a copy so we never mutate whatever chat_memory.messages returns
        buffer = list(self.chat_memory.messages)
        curr_buffer_length = self.llm.get_num_tokens_from_messages(buffer)
        if curr_buffer_length <= self.max_token_limit:
            return
        pruned_memory = []
        while curr_buffer_length > self.max_token_limit:
            pruned_memory.append(buffer.pop(0))
            curr_buffer_length = self.llm.get_num_tokens_from_messages(buffer)
        self.moving_summary_buffer = self.predict_new_summary(
            pruned_memory,
            self.moving_summary_buffer,
        )
        # Rewrite Redis to only hold the remaining buffer (trim old messages).
        # Not atomic: under concurrent requests for same session, consider session lock or Redis transaction.
        self.chat_memory.clear()
        for msg in buffer:
            self.chat_memory.add_message(msg)

    async def aprune(self) -> None:
        buffer = list(await self.chat_memory.aget_messages())
        curr_buffer_length = self.llm.get_num_tokens_from_messages(buffer)
        if curr_buffer_length <= self.max_token_limit:
            return
        pruned_memory = []
        while curr_buffer_length > self.max_token_limit:
            pruned_memory.append(buffer.pop(0))
            curr_buffer_length = self.llm.get_num_tokens_from_messages(buffer)
        self.moving_summary_buffer = await self.apredict_new_summary(
            pruned_memory,
            self.moving_summary_buffer,
        )
        await self.chat_memory.aclear()
        await self.chat_memory.aadd_messages(buffer)

load_env()

REDIS_HOST = get_env("REDIS_HOST") or "localhost"
REDIS_PORT = get_env("REDIS_PORT") or "6379"


def get_memory_key(customer_id_number: str, session_id: str) -> str:
    return f"conversation:{customer_id_number}:{session_id}"


def get_summary_key(customer_id_number: str, session_id: str) -> str:
    """Redis key for moving_summary_buffer (ConversationSummaryBufferMemory)."""
    return f"conversation_summary:{customer_id_number}:{session_id}"


def _get_redis_client():
    """Redis client for summary get/set/delete (same host/port as chat history)."""
    import redis
    return redis.Redis(
        host=REDIS_HOST,
        port=int(REDIS_PORT),
        db=0,
        password=None,
        decode_responses=True,
    )


def _get_redis_url() -> str:
    return f"redis://{REDIS_HOST}:{REDIS_PORT}/0"


def _get_summarizer_llm():
    """LangChain ChatOpenAI for ConversationSummaryBufferMemory (summarization)."""
    from langchain_openai import ChatOpenAI
    api_key = get_env("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return ChatOpenAI(
        model="gpt-4.1",
        temperature=0.1,
        api_key=api_key,
    )


def load_summary(customer_id_number: str, session_id: str) -> str:
    """Load moving_summary_buffer from Redis. Returns "" if not set."""
    r = _get_redis_client()
    key = get_summary_key(customer_id_number, session_id)
    value = r.get(key)
    return value if value is not None else ""


def _save_summary(customer_id_number: str, session_id: str, summary: str) -> None:
    """Internal: persist moving_summary_buffer to Redis. Empty string deletes the key."""
    r = _get_redis_client()
    key = get_summary_key(customer_id_number, session_id)
    if summary:
        r.set(key, summary)
    else:
        r.delete(key)


def save_context_and_persist(
    memory: ConversationSummaryBufferMemory,
    customer_id_number: str,
    session_id: str,
    user_input: str,
    output_str: str,
) -> None:
    """
    Save this turn to chat_memory (and run prune if over limit), then persist
    moving_summary_buffer to Redis. This is the only supported way to write a turn; do not
    call memory.save_context(...) and save_summary(...) separately.
    """
    memory.save_context({"input": user_input}, {"output": output_str})
    _save_summary(customer_id_number, session_id, memory.moving_summary_buffer)


def create_memory(
    customer_id_number: str,
    session_id: str,
    llm: Optional[object] = None,
    max_token_limit: int = 2000,
) -> ConversationSummaryBufferMemory:
    redis_key = get_memory_key(customer_id_number, session_id)
    message_history = RedisChatMessageHistory(
        url=_get_redis_url(),
        session_id=redis_key,
    )
    if llm is None:
        llm = _get_summarizer_llm()
    memory = RedisTrimmingSummaryBufferMemory(
        llm=llm,
        chat_memory=message_history,
        max_token_limit=max_token_limit,
        return_messages=True,
    )
    # Restore moving_summary_buffer from Redis so summary survives across requests
    loaded = load_summary(customer_id_number, session_id)
    if loaded:
        memory.moving_summary_buffer = loaded
    return memory


def clear_memory(customer_id_number: str, session_id: str) -> None:
    """
    Clear conversation and summary for this session from Redis.
    Clears chat messages (via memory.clear()) and deletes the summary key.
    """
    memory = create_memory(customer_id_number, session_id)
    memory.clear()
    _save_summary(customer_id_number, session_id, "")


def _format_message(msg: object) -> tuple[str, str]:
    """Return (role_label, content) for a message."""
    msg_type = getattr(msg, "type", None)
    content = getattr(msg, "content", str(msg))
    if msg_type == "human":
        return "User", content
    if msg_type == "system":
        return "Summary", content
    return "Assistant", content


def format_conversation_history(
    memory: Optional[ConversationSummaryBufferMemory],
    current_query: str,
    max_messages: int = 10,
    prefix: str = "Previous conversation",
) -> str:
    """
    Build planner prompt: summary (if any) + last max_messages of dialogue.
    Keeps the first message when it is a summary/system so it is never cut by [-max_messages].
    """
    if not memory:
        return current_query
    variables = memory.load_memory_variables({})
    history = variables.get(memory.memory_key, [])
    if not history:
        return current_query
    if isinstance(history, str):
        history_text = f"\n\n{prefix}:\n{history.strip()}\n"
        return history_text + f"\nCurrent user input: {current_query}"

    # List path: keep first if summary/system, then take last max_messages of the rest
    head = history[0] if history else None
    rest = history[1:] if history else []
    if head is not None and getattr(head, "type", None) == "system":
        role, content = _format_message(head)
        history_text = f"\n\n{prefix}:\n{role}: {content}\n"
        recent = rest[-max_messages:] if len(rest) > max_messages else rest
    else:
        history_text = f"\n\n{prefix}:\n"
        recent = history[-max_messages:] if len(history) > max_messages else history
    for msg in recent:
        role, content = _format_message(msg)
        history_text += f"{role}: {content}\n"
    return history_text + f"\nCurrent user input: {current_query}"
