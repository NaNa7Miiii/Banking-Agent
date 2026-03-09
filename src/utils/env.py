"""
Load environment from project root .env.
"""
import os
from pathlib import Path

# src/utils/env.py -> src -> project root (repo root)
_SRC_ROOT = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _SRC_ROOT.parent


def get_project_root() -> Path:
    return _PROJECT_ROOT


def get_src_root() -> Path:
    return _SRC_ROOT


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
