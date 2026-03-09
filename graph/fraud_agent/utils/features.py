"""
Build feature matrix from a list of transaction dicts (e.g. from SQL agent result).
Matches fraud_detection/01 feature logic: haversine, is_online, effective_distance,
hour_of_day, day_of_week, tx_count_1h/24h, amt_sum_24h, customer_age.
"""
from typing import Any

import numpy as np
import pandas as pd


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    return R * c


def build_feature_df_from_transactions(
    transactions: list[dict[str, Any]],
    feature_cols: list[str],
) -> pd.DataFrame:
    """
    From a list of transaction dicts (e.g. from run_sql_agent result), build a DataFrame
    with columns matching feature_cols (as in feature_config.json). Each row is one transaction.
    Uses the same list to compute 24h/1h velocity within the batch (past-only).
    """
    if not transactions:
        return pd.DataFrame(columns=feature_cols)

    df = pd.DataFrame(transactions)
    # Normalize column names / types
    if "transaction_datetime" in df.columns:
        df["transaction_datetime"] = pd.to_datetime(df["transaction_datetime"], errors="coerce")
    if "customer_dob" in df.columns:
        df["customer_dob"] = pd.to_datetime(df["customer_dob"], errors="coerce")

    # Sort by card + time for rolling stats
    card_col = "customer_id_number"
    if card_col not in df.columns:
        card_col = "cc_num"
    df = df.sort_values([card_col, "transaction_datetime"]).reset_index(drop=True)

    # --- is_online, distance, effective_distance ---
    cat_col = "merchant_category"
    df["is_online"] = (df.get(cat_col, pd.Series(dtype=object)).fillna("").astype(str).str.endswith("_net")).astype(int)

    lat_c = df.get("customer_latitude", pd.Series(dtype=float))
    lon_c = df.get("customer_longitude", pd.Series(dtype=float))
    lat_m = df.get("merchant_latitude", pd.Series(dtype=float))
    lon_m = df.get("merchant_longitude", pd.Series(dtype=float))
    valid = lat_c.notna() & lon_c.notna() & lat_m.notna() & lon_m.notna()
    df["distance_to_merchant"] = np.nan
    df.loc[valid, "distance_to_merchant"] = _haversine_km(
        lat_c[valid].values, lon_c[valid].values,
        lat_m[valid].values, lon_m[valid].values,
    )
    df["effective_distance"] = np.where(df["is_online"] == 1, 0.0, df["distance_to_merchant"])
    df["effective_distance"] = df["effective_distance"].fillna(-1)

    # --- hour, day_of_week ---
    ts = df["transaction_datetime"]
    df["hour_of_day"] = ts.dt.hour
    df["day_of_week"] = ts.dt.dayofweek

    # --- 24h / 1h velocity from same list (past only) ---
    t_sec = ts.astype("datetime64[s]").astype("int64")
    amt = df["transaction_amount"].astype(float)
    n = len(df)
    card_vals = df[card_col].values
    dt = t_sec.values[:, None] - t_sec.values[None, :]
    same_card = (card_vals[:, None] == card_vals[None, :])
    past_only = (dt >= 0) & same_card
    within_1h = (dt <= 3600) & (dt >= 0) & same_card
    within_24h = (dt <= 86400) & (dt >= 0) & same_card
    np.fill_diagonal(within_1h, False)
    np.fill_diagonal(within_24h, False)
    df["tx_count_1h"] = within_1h.sum(axis=1)
    df["tx_count_24h"] = within_24h.sum(axis=1)
    df["amt_sum_24h"] = (within_24h.astype(float) * amt.values).sum(axis=1)

    # --- customer_age ---
    df["customer_age"] = (df["transaction_datetime"] - df["customer_dob"]).dt.days / 365.25
    df["customer_age"] = df["customer_age"].clip(lower=0, upper=120).fillna(-1)

    for c in feature_cols:
        if c not in df.columns:
            df[c] = np.nan
    out = df.reindex(columns=feature_cols)
    return out
