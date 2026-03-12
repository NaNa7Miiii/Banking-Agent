"""
Pipeline uses XGBoost from fraud_detection/ml_model/ (saved by 08_xgboost_benchmark.ipynb).
"""
from pathlib import Path

from src.utils.env import get_project_root

FRAUD_MODELS_DIR = get_project_root() / "fraud_detection" / "models"
ML_MODEL_DIR = get_project_root() / "fraud_detection" / "ml_model"


def get_xgboost_model_path() -> Path:
    return ML_MODEL_DIR / "xgboost_fraud.pkl"


def get_preprocess_config_path() -> Path:
    return ML_MODEL_DIR / "preprocess_and_config.pkl"


def get_feature_config_path() -> Path:
    """Prefer ml_model/feature_config.json if present (same 22 features as training)."""
    cfg_in_ml = ML_MODEL_DIR / "feature_config.json"
    if cfg_in_ml.exists():
        return cfg_in_ml
    return FRAUD_MODELS_DIR / "feature_config.json"
