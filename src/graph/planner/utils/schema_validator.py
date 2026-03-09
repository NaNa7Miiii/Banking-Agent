"""
Validate JSON against a JSON Schema. Used by planner to validate LLM output.
"""
from typing import Any, Dict

from src.utils.prompt_loader import get_prompts_dir


def load_schema(module: str, schema_filename: str = "output_schema.json") -> Dict[str, Any]:
    """Load JSON schema from prompts/<module>/<schema_filename>."""
    path = get_prompts_dir() / module / schema_filename
    if not path.exists():
        raise FileNotFoundError(f"Schema file not found: {path}")
    import json
    return json.loads(path.read_text(encoding="utf-8"))


def validate_plan(plan: Dict[str, Any], schema: Dict[str, Any] | None = None) -> None:
    """
    Validate plan against Planner output_schema. Raises ValueError with details on failure.
    If schema is None, loads prompts/planner/output_schema.json.
    """
    try:
        import jsonschema
    except ImportError:
        raise RuntimeError("jsonschema is required for plan validation. Install with: pip install jsonschema")

    if schema is None:
        schema = load_schema("planner")
    jsonschema.validate(instance=plan, schema=schema)
