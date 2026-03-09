"""
Load prompt templates from refactored/prompts. Reusable; no dependency on src.
"""
from pathlib import Path
from typing import Any

from refactored.utils.env import get_refactored_root


def get_prompts_dir() -> Path:
    return get_refactored_root() / "prompts"


def load_system_prompt(module: str, filename: str = "system.md") -> str:
    """
    Load a system prompt from prompts/<module>/<filename>.
    Example: load_system_prompt("planner") -> content of prompts/planner/system.md
    """
    path = get_prompts_dir() / module / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def load_meta(module: str) -> dict[str, Any]:
    """
    Load meta.yaml from prompts/<module>/meta.yaml.
    Returns a dict; does not require PyYAML if file is simple (we can keep it simple or add pyyaml).
    """
    path = get_prompts_dir() / module / "meta.yaml"
    if not path.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ImportError:
        # No PyYAML: return raw content as single key for minimal support
        return {"_raw": path.read_text(encoding="utf-8")}


def load_output_schema_path(module: str) -> Path | None:
    """
    Resolve output_schema path for a module from its meta.yaml.
    Returns path to the JSON file, or None if not specified or missing.
    """
    meta = load_meta(module)
    name = meta.get("output_schema")
    if not name:
        return None
    path = get_prompts_dir() / module / name
    return path if path.exists() else None
