"""
Fraud agent config: model paths (fraud_detection output), no dependency on src.
"""
from pathlib import Path

from refactored.utils.env import get_project_root

FRAUD_MODELS_DIR = get_project_root() / "fraud_detection" / "models"

def get_calibrated_model_path() -> Path:
    return FRAUD_MODELS_DIR / "catboost_calibrated.pkl"

def get_if_model_path() -> Path:
    return FRAUD_MODELS_DIR / "isolation_forest.pkl"

def get_feature_config_path() -> Path:
    return FRAUD_MODELS_DIR / "feature_config.json"
