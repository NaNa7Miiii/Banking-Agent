"""Load fraud agent prompts from prompts/fraud_agent."""
from src.utils.prompt_loader import load_system_prompt

FRAUD_AGENT_MODULE = "fraud_agent"


def agent_system() -> str:
    return load_system_prompt(FRAUD_AGENT_MODULE, "agent_system.md")
