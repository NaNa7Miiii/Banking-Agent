"""
Fraud agent tools: get_transactions_via_sql (calls SQL agent), analyze_risk_scores_batch, query_customer_profile.
"""
import json
from typing import Any

from langchain_core.tools import tool

from src.graph.sql_agent.pipeline import run_sql_agent
from src.graph.fraud_agent.utils.batch_inference import run_batch_risk_scores
from src.graph.fraud_agent.utils.profile import get_customer_profile


def make_fraud_tools(current_user_id: str) -> tuple[list, dict[str, Any]]:
    """
    Returns (list of LangChain tools, collector dict).
    Collector holds: sql_result, sql_answer, risk_scores, profile.
    """
    collector: dict[str, Any] = {
        "sql_result": None,
        "sql_answer": None,
        "risk_scores": None,
        "profile": None,
    }

    @tool
    def get_transactions_via_sql(question: str) -> str:
        """Fetch the current user's transaction list via an internal SQL agent. Pass a natural-language question describing the time range or conditions (e.g. my transactions in the past two months, return transaction_id, transaction_datetime, transaction_amount, merchant_name, merchant_category, customer_latitude, customer_longitude, merchant_latitude, merchant_longitude, customer_dob, customer_id_number, customer_gender, customer_city, customer_state, customer_zip, customer_city_population, customer_job_title). Returns the result rows."""
        # When transaction data was pre-loaded from a previous graph step, do not overwrite
        if collector.get("preloaded_from_graph") and collector.get("sql_result"):
            rows = collector["sql_result"]
            if not rows:
                return "Transaction list from the previous step is empty. You can still call analyze_risk_scores_batch with 'use last result' to score it."
            summary = json.dumps(rows[:50], ensure_ascii=False, default=str)
            if len(rows) > 50:
                summary += f"\n... {len(rows)} rows total; use analyze_risk_scores_batch with input 'use last result' to score."
            return f"Transaction data from the previous step is already loaded ({len(rows)} rows). Call analyze_risk_scores_batch with input 'use last result' to score it.\nSummary:\n{summary[:4000]}"
        out = run_sql_agent(question=question, current_user_id=current_user_id)
        collector["sql_answer"] = out.get("answer", "")
        collector["sql_result"] = out.get("result")
        if out.get("error"):
            return f"SQL error: {out['error']}\n{out.get('answer', '')}"
        rows = out.get("result") or []
        if not rows:
            return "Query succeeded but no matching transactions."
        summary = json.dumps(rows[:50], ensure_ascii=False, default=str)
        if len(rows) > 50:
            summary += f"\n... {len(rows)} rows total; showing first 50. Pass full result to analyze_risk_scores_batch."
        return f"{len(rows)} transaction(s).\nSummary for next tool:\n{summary[:4000]}"

    @tool
    def analyze_risk_scores_batch(transactions_json: str) -> str:
        """Run batch risk scoring (XGBoost) on a list of transactions. Input: (1) full JSON array from get_transactions_via_sql, or (2) a trigger phrase (e.g. 'use last result') to reuse the last query result. Each row should include transaction_id, transaction_datetime, transaction_amount, merchant_name, merchant_category, customer_latitude, customer_longitude, merchant_latitude, merchant_longitude, customer_dob, customer_id_number, etc. Returns per-tx xgboost_prob, risk_level and a summary."""
        data = None
        s = (transactions_json or "").strip()
        if not s or s.lower() == "use last result":
            data = collector.get("sql_result")
        if data is None and s:
            try:
                if isinstance(transactions_json, str):
                    if s.startswith("["):
                        data = json.loads(s)
                    else:
                        start = s.find("[")
                        if start >= 0:
                            end = s.rfind("]") + 1
                            if end > start:
                                data = json.loads(s[start:end])
                        if data is None:
                            data = []
                else:
                    data = list(transactions_json)
            except json.JSONDecodeError:
                collector["risk_scores"] = {"results": [], "summary": "Input is not a valid JSON array."}
                return "Could not parse transaction list JSON; pass the trigger phrase to reuse the last get_transactions_via_sql result."
        if data is None:
            data = []
        if not data:
            collector["risk_scores"] = {"results": [], "summary": "Transaction list is empty."}
            return "Transaction list is empty. Call get_transactions_via_sql first, then score."
        result = run_batch_risk_scores(data)
        collector["risk_scores"] = result
        return json.dumps(result, ensure_ascii=False, indent=2)

    @tool
    def query_customer_profile(cc_num: str) -> str:
        """Look up the customer profile for the given card number: home city, age, average ticket size, common categories. Input is the card number (e.g. current user's)."""
        profile = get_customer_profile(cc_num)
        collector["profile"] = profile
        return json.dumps(profile, ensure_ascii=False)

    return [get_transactions_via_sql, analyze_risk_scores_batch, query_customer_profile], collector
