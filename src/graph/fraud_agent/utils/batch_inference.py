"""
Batch risk scoring: load XGBoost + preprocessing from fraud_detection/ml_model,
build features from transaction list, return per-tx scores.
"""
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.graph.fraud_agent.config import (
    get_feature_config_path,
    get_preprocess_config_path,
    get_xgboost_model_path,
)
from src.graph.fraud_agent.utils.features import build_feature_df_from_transactions


def _to_native_scalar(v: Any) -> Any:
    """Convert numpy/pandas types to native Python so no Series/ndarray slips into dicts (avoids unhashable)."""
    if v is None or isinstance(v, (bool, str, int, float)):
        return v
    if isinstance(v, (np.integer, np.int32, np.int64)):
        return int(v)
    if isinstance(v, (np.floating, np.float32, np.float64)):
        return float(v)
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, pd.Series):
        return v.tolist()
    if hasattr(v, "isoformat"):  # datetime-like
        return v.isoformat() if hasattr(v, "isoformat") else str(v)
    return v


def _sanitize_transactions(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure each row is a dict of native Python scalars (no Series/ndarray as values)."""
    return [
        {k: _to_native_scalar(v) for k, v in row.items()}
        for row in transactions
    ]


def _apply_xgb_preprocess(X: pd.DataFrame, preprocess: dict[str, Any]) -> np.ndarray:
    """Apply encoder + numeric median fill; return float matrix in feature_cols order."""
    feature_cols = preprocess["feature_cols"]
    cat_features = preprocess["cat_features"]
    encoder = preprocess["encoder"]
    numeric_median = preprocess["numeric_median"]
    numeric_cols = [c for c in feature_cols if c not in cat_features]

    X_enc = X[feature_cols].copy()
    if cat_features:
        X_enc[cat_features] = encoder.transform(
            X[cat_features].astype(str).fillna("__NA__")
        )
    for c in numeric_cols:
        X_enc[c] = pd.to_numeric(X_enc[c], errors="coerce")
    for c in numeric_cols:
        med = numeric_median.get(c)
        if med is not None:
            X_enc[c] = X_enc[c].fillna(med)
    return X_enc[feature_cols].values.astype(np.float64)


def run_batch_risk_scores(
    transactions: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Run XGBoost (from ml_model) on a batch of transactions.
    Returns dict with "results" (list of {transaction_id, xgboost_prob, risk_level})
    and "summary" (string). Risk levels use best threshold (th_xgb) from 08 notebook for review cutoff.
    """
    if not transactions:
        return {"results": [], "summary": "No transactions to score."}
    transactions = _sanitize_transactions(transactions)

    config_path = get_feature_config_path()
    if not config_path.exists():
        return {
            "results": [],
            "summary": "feature_config.json not found; run fraud_detection 08 and save ml_model first.",
        }
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    feature_cols = config.get("feature_cols", [])

    X = build_feature_df_from_transactions(transactions, feature_cols)
    if X.empty or len(X) != len(transactions):
        return {"results": [], "summary": "Feature build failed or row count mismatch."}

    tx_ids = [
        (t.get("transaction_id") or t.get("trans_num") or str(i))
        for i, t in enumerate(transactions)
    ]

    model_path = get_xgboost_model_path()
    preprocess_path = get_preprocess_config_path()
    if not model_path.exists() or not preprocess_path.exists():
        return {
            "results": [],
            "summary": "XGBoost model or preprocess not found; run fraud_detection/08_xgboost_benchmark.ipynb and run the save cell.",
        }

    xgb_clf = joblib.load(model_path)
    preprocess = joblib.load(preprocess_path)
    best_th = preprocess.get("threshold", 0.5)
    X_final = _apply_xgb_preprocess(X, preprocess)
    probs = xgb_clf.predict_proba(X_final)[:, 1]

    high_count = 0
    out_results = []
    for i in range(len(transactions)):
        prob = float(probs[i])
        level = "high" if prob >= best_th else "low"
        if level == "high":
            high_count += 1
        out_results.append({
            "transaction_id": tx_ids[i],
            "xgboost_prob": round(prob, 4),
            "risk_level": level,
        })

    total = len(transactions)
    summary = f"Total {total} tx: {high_count} high-risk (prob >= {best_th})."
    return {"results": out_results, "summary": summary}


if __name__ == "__main__":
    row_with_series = {
        "transaction_id": 1,
        "amount": np.float64(10.5),
        "bad": pd.Series([1, 2]),
    }
    out = _sanitize_transactions([row_with_series])
    assert isinstance(out[0]["amount"], float)
    assert isinstance(out[0]["bad"], list)
    assert out[0]["bad"] == [1, 2]
    print("_sanitize_transactions: ok (no unhashable Series)")
