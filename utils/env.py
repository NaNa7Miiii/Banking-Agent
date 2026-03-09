"""
Load environment from project root .env. Refactored module must not depend on src.
"""
import os
from pathlib import Path

# refactored/utils/env.py -> refactored -> project root (agent_bank)
_REFACTORED_ROOT = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _REFACTORED_ROOT.parent


def get_project_root() -> Path:
    return _PROJECT_ROOT


def get_refactored_root() -> Path:
    return _REFACTORED_ROOT


def load_env() -> None:
    """Load .env from project root if present."""
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=_PROJECT_ROOT / ".env")
    except ImportError:
        pass


def get_env(key: str, default: str | None = None) -> str | None:
    """Get env var after load_env() has been called."""
    return os.getenv(key, default)
