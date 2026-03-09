"""
Batch risk scoring: load calibrated CatBoost + IF, build features from transaction list, return per-tx scores.
"""
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.graph.fraud_agent.config import (
    get_calibrated_model_path,
    get_feature_config_path,
    get_if_model_path,
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


def run_batch_risk_scores(
    transactions: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Run CatBoost (calibrated) + Isolation Forest on a batch of transactions.
    Returns dict with "results" (list of {transaction_id, catboost_prob, isolation_forest_score, risk_level})
    and "summary" (string).
    """
    if not transactions:
        return {"results": [], "summary": "No transactions to score."}
    transactions = _sanitize_transactions(transactions)

    config_path = get_feature_config_path()
    if not config_path.exists():
        return {
            "results": [],
            "summary": "feature_config.json not found; run fraud_detection steps 02/03/04 first.",
        }
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    feature_cols = config.get("feature_cols", [])
    cat_features = config.get("cat_features", [])
    numeric_cols_no_zip = [c for c in feature_cols if c not in cat_features and c != "customer_zip"]

    X = build_feature_df_from_transactions(transactions, feature_cols)
    if X.empty or len(X) != len(transactions):
        return {"results": [], "summary": "Feature build failed or row count mismatch."}

    # Transaction IDs for output (keep order)
    tx_ids = [
        (t.get("transaction_id") or t.get("trans_num") or str(i))
        for i, t in enumerate(transactions)
    ]

    out_results = []
    catboost_probs = None
    if_scores = None

    calibrated_path = get_calibrated_model_path()
    if calibrated_path.exists():
        calibrated = joblib.load(calibrated_path)
        catboost_probs = calibrated.predict_proba(X)[:, 1]
    else:
        catboost_probs = [0.0] * len(transactions)

    if_path = get_if_model_path()
    if if_path.exists():
        if_payload = joblib.load(if_path)
        scaler = if_payload.get("scaler")
        iforest = if_payload.get("iforest")
        num_cols = if_payload.get("numeric_cols", numeric_cols_no_zip)
        num_cols = [c for c in num_cols if c in X.columns]
        if scaler is not None and iforest is not None and num_cols:
            X_num = X[num_cols].fillna(-999).astype(float)
            X_scaled = scaler.transform(X_num)
            if_scores = iforest.decision_function(X_scaled)
        else:
            if_scores = [0.0] * len(transactions)
    else:
        if_scores = [0.0] * len(transactions)

    # Risk level: high (prob >= 0.7 or if very low), review (prob >= 0.5), low
    high_count = 0
    review_count = 0
    for i in range(len(transactions)):
        prob = float(catboost_probs[i])
        if_sc = float(if_scores[i])
        if prob >= 0.7 or if_sc <= -0.05:
            level = "high"
            high_count += 1
        elif prob >= 0.5:
            level = "review"
            review_count += 1
        else:
            level = "low"
        out_results.append({
            "transaction_id": tx_ids[i],
            "catboost_prob": round(prob, 4),
            "isolation_forest_score": round(if_sc, 4),
            "risk_level": level,
        })

    total = len(transactions)
    summary = f"Total {total} tx: {high_count} high-risk, {review_count} recommend review."
    return {"results": out_results, "summary": summary}


if __name__ == "__main__":
    # Quick sanity check: rows with Series/numpy must become native (avoids unhashable type: 'Series')
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
