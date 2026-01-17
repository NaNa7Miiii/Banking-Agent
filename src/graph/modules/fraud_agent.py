from typing import TypedDict, List, Dict, Any, Optional
from sqlalchemy import text
import json
from pathlib import Path
from src.data.model.predictor import get_fraud_predictor
from src.graph.models.llm import get_llm
from src.graph.prompts.fraud_prompts import FRAUD_LLM_SYSTEM_PROMPT, FRAUD_ANALYSIS_USER_PROMPT
from src.graph.modules.sql_agent import SQLAgent


# Fraud agent state definition
class FraudAgentState(TypedDict):
    question: str  # User's question about fraud detection
    transactions: List[Dict[str, Any]]  # List of transaction dictionaries (can be provided directly or fetched from DB)
    sql_query: str  # SQL query generated to fetch transactions
    sql_result: Any  # Raw SQL query result
    fraud_predictions: List[Dict[str, Any]]  # ML model predictions for each transaction
    flagged_transactions: List[Dict[str, Any]]  # Transactions with fraud_probability >= threshold
    llm_analysis: str  # LLM's final fraud analysis (raw JSON string)
    llm_analysis_json: List[Dict[str, Any]]  # Parsed LLM analysis as JSON
    final_fraud_report: str  # Combined report of fraud analysis
    answer: str  # Formatted answer for router (compatible with router interface)
    time_window_start: str  # Start date of time window
    time_window_end: str  # End date of time window

# This agent performs a two-stage fraud detection:
#    1. First stage: Use XGBoost model to filter transactions (ignore if < threshold)
#    2. Second stage: For transactions >= threshold, use LLM for final determination
# If question is provided, it will use SQLAgent to generate SQL and fetch transactions from DB
def create_fraud_agent_node(
    sql_agent: Optional[SQLAgent] = None,
    llm_model="gpt-4.1",
    temperature=0.1,
    model_dir: Optional[Path] = None
):
    # Load required columns from model info
    if model_dir is None:
        model_dir = Path(__file__).parent.parent.parent.parent / "src" / "data" / "model"
    else:
        model_dir = Path(model_dir)

    model_info_path = model_dir / "model_info.json"
    required_columns = None
    if model_info_path.exists():
        with open(model_info_path, "r") as f:
            model_info = json.load(f)
            # Get base columns needed (excluding derived features that will be computed in predictor)
            feature_cols = model_info.get("feature_cols", [])
            base_columns_needed = set()
            for col in feature_cols:
                # Derived features that need base columns
                if col in ["trans_hour", "trans_dayofweek", "trans_day", "trans_month", "is_night"]:
                    base_columns_needed.add("transaction_datetime")
                elif col == "customer_age":
                    base_columns_needed.add("customer_dob")
                else:
                    # Direct column from DB
                    base_columns_needed.add(col)
            base_columns_needed.add("transaction_id")
            # Explicitly exclude is_fraud - it's a forbidden column that should never be queried
            base_columns_needed.discard("is_fraud")
            required_columns = sorted(list(base_columns_needed))

    predictor = get_fraud_predictor(model_dir)

    # If sql_agent is provided but doesn't have required_columns, create a new one
    if sql_agent and required_columns:
        # Create a new SQLAgent with required_columns to ensure SQL queries include all necessary columns
        sql_agent = SQLAgent(
            db=sql_agent.db,
            table_name=sql_agent.table_name,
            llm_model=llm_model,
            temperature=0.0,  # Use 0.0 for SQL generation
            required_columns=required_columns,
        )

    # Create LLM instance using factory function
    llm = get_llm(
        role="fraud",
        model_name=llm_model,
        temperature=temperature,
    )

    def fraud_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
        # Adapt to router interface: accept state with 'question' key, return state with 'answer' key
        question = state.get("question", "")
        transactions = state.get("transactions", [])
        sql_query = state.get("sql_query", "")
        sql_result = state.get("sql_result", None)

        time_window_start = ""
        time_window_end = ""

        # If question is provided but no transactions, use SQLAgent to fetch transactions
        if question and not transactions and sql_agent:
            try:
                # Generate SQL query from question
                sql_query = sql_agent.generate_sql(question)

                # Execute SQL query and get results as dictionaries
                # Use SQLAlchemy engine directly to get dict results
                with sql_agent.db._engine.connect() as conn:
                    result = conn.execute(text(sql_query))
                    # Convert to list of dictionaries
                    transactions = [dict(row._mapping) for row in result]
                    sql_result = transactions

                if not transactions:
                    return {
                        **state,
                        "sql_query": sql_query,
                        "sql_result": sql_result,
                        "transactions": [],
                        "fraud_predictions": [],
                        "flagged_transactions": [],
                        "llm_analysis": "No transactions found matching the query criteria.",
                        "llm_analysis_json": [],
                        "final_fraud_report": f"No transactions found matching the query criteria.\n\nSQL Query: {sql_query}",
                        "answer": "No transactions found matching the query criteria.",
                        "time_window_start": time_window_start,
                        "time_window_end": time_window_end,
                    }
            except Exception as e:
                return {
                    **state,
                    "sql_query": sql_query,
                    "sql_result": None,
                    "transactions": [],
                    "fraud_predictions": [],
                    "flagged_transactions": [],
                    "llm_analysis": f"Error fetching transactions from database: {str(e)}",
                    "llm_analysis_json": [],
                    "final_fraud_report": f"Error fetching transactions from database: {str(e)}\n\nSQL Query: {sql_query if sql_query else 'N/A'}",
                    "answer": f"Error fetching transactions from database: {str(e)}",
                    "time_window_start": time_window_start,
                    "time_window_end": time_window_end,
                }

        if not transactions:
            return {
                **state,
                "fraud_predictions": [],
                "flagged_transactions": [],
                "llm_analysis": "No transactions provided for fraud detection.",
                "llm_analysis_json": [],
                "final_fraud_report": "No transactions provided for fraud detection.",
                "answer": "No transactions provided for fraud detection.",
                "time_window_start": time_window_start,
                "time_window_end": time_window_end,
            }

        # Extract time window from transactions if available
        if transactions:
            transaction_dates = [t.get("transaction_datetime") for t in transactions if t.get("transaction_datetime")]
            if transaction_dates:
                try:
                    from datetime import datetime
                    dates = [datetime.fromisoformat(str(d).replace("Z", "+00:00")) if isinstance(d, str) else d for d in transaction_dates if d]
                    if dates:
                        time_window_start = min(dates).strftime("%Y-%m-%d") if hasattr(min(dates), 'strftime') else str(min(dates)).split()[0]
                        time_window_end = max(dates).strftime("%Y-%m-%d") if hasattr(max(dates), 'strftime') else str(max(dates)).split()[0]
                except:
                    pass

        # Stage 1: ML model predictions for all transactions
        fraud_predictions = predictor.predict_batch(transactions)

        # Stage 2: Filter transactions with fraud_probability >= threshold
        threshold = predictor.decision_threshold
        flagged_transactions = []

        for transaction, prediction in zip(transactions, fraud_predictions):
            fraud_prob = prediction.get("fraud_probability", 0.0)

            # Only process transactions that exceed threshold
            if fraud_prob >= threshold:
                flagged_transactions.append({
                    "transaction": transaction,
                    "fraud_probability": fraud_prob,
                    "confidence": prediction.get("confidence", "unknown"),
                    "ml_is_fraud": prediction.get("is_fraud", False),
                })

        # Stage 3: LLM analysis for flagged transactions
        if flagged_transactions:
            # Format transactions text for prompt template
            transaction_parts = []
            for idx, item in enumerate(flagged_transactions, 1):
                transaction = item.get("transaction", {})
                fraud_prob = item.get("fraud_probability", 0.0)
                confidence = item.get("confidence", "unknown")

                transaction_parts.append(f"Transaction {idx}:")
                transaction_parts.append(f"  ML Fraud Probability: {fraud_prob:.4f} ({confidence} confidence)")
                transaction_parts.append(f"  Transaction Details:")

                # Format transaction details
                for key, value in transaction.items():
                    if value is not None:
                        transaction_parts.append(f"    {key}: {value}")

                transaction_parts.append("")

            transactions_text = "\n".join(transaction_parts)

            # Format user prompt using template
            user_prompt_messages = FRAUD_ANALYSIS_USER_PROMPT.format_messages(
                transactions_text=transactions_text
            )
            user_prompt = user_prompt_messages[0].content if user_prompt_messages else transactions_text

            # Get LLM analysis (should be JSON)
            llm_analysis_raw = llm.chat(
                system_prompt=FRAUD_LLM_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_format=None,
            )

            # Parse JSON response
            llm_analysis_json = []
            llm_analysis = llm_analysis_raw
            try:
                # Clean up potential markdown code blocks
                cleaned = llm_analysis_raw.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                elif cleaned.startswith("```"):
                    cleaned = cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

                llm_analysis_json = json.loads(cleaned)
                if not isinstance(llm_analysis_json, list):
                    llm_analysis_json = []
            except (json.JSONDecodeError, Exception) as e:
                # If parsing fails, keep empty list
                llm_analysis_json = []
                print(f"Warning: Failed to parse LLM JSON response: {e}")

            # Create final report combining ML predictions and LLM analysis
            report_parts = [
                f"Fraud Detection Analysis Report",
                f"=" * 50,
                f"",
                f"Total transactions analyzed: {len(transactions)}",
                f"Transactions flagged by ML model (probability >= {threshold:.2f}): {len(flagged_transactions)}",
                f"",
                f"LLM Analysis:",
                json.dumps(llm_analysis_json, indent=2) if llm_analysis_json else llm_analysis,
                f"",
                f"Detailed ML Predictions:",
                f"-" * 50,
            ]

            for idx, item in enumerate(flagged_transactions, 1):
                trans = item["transaction"]
                prob = item["fraud_probability"]
                conf = item["confidence"]
                trans_id = trans.get("transaction_id", f"Transaction {idx}")

                report_parts.append(f"Transaction {idx} (ID: {trans_id}):")
                report_parts.append(f"  ML Fraud Probability: {prob:.4f} ({conf} confidence)")
                report_parts.append(f"  Amount: ${trans.get('transaction_amount', 'N/A')}")
                report_parts.append(f"  Merchant: {trans.get('merchant_name', 'N/A')}")
                report_parts.append(f"  Category: {trans.get('merchant_category', 'N/A')}")
                report_parts.append("")

            final_fraud_report = "\n".join(report_parts)

            # Create answer for router (will be formatted in chat_interface)
            answer = final_fraud_report
        else:
            llm_analysis = "No transactions exceeded the fraud probability threshold. All transactions appear legitimate based on the ML model."
            llm_analysis_json = []
            final_fraud_report = (
                f"Fraud Detection Analysis Report\n"
                f"{'=' * 50}\n\n"
                f"Total transactions analyzed: {len(transactions)}\n"
                f"Transactions flagged by ML model (probability >= {threshold:.2f}): 0\n\n"
                f"Result: No suspicious transactions detected.\n"
                f"All transactions have fraud probability below the threshold ({threshold:.2f})."
            )
            answer = final_fraud_report

        return {
            **state,
            "sql_query": sql_query,
            "sql_result": sql_result,
            "transactions": transactions,
            "fraud_predictions": fraud_predictions,
            "flagged_transactions": flagged_transactions,
            "llm_analysis": llm_analysis,
            "llm_analysis_json": llm_analysis_json,
            "final_fraud_report": final_fraud_report,
            "answer": answer,
            "time_window_start": time_window_start,
            "time_window_end": time_window_end,
        }

    return fraud_agent_node


# Creates a fraud agent node for the transactions table (similar to create_transaction_sql_agent_node)
def create_transaction_fraud_agent_node(
    username,
    password,
    host,
    port,
    database,
    table_name="transactions",
    llm_model="gpt-4.1",
    temperature=0.1,
    model_dir: Optional[Path] = None):
    """Create a fraud agent node that can be integrated into the main graph"""
    from src.data.utils import get_sql_db

    db = get_sql_db(
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        echo=False,
    )

    # Create SQL agent for fraud agent to use
    sql_agent = SQLAgent(
        db=db,
        table_name=table_name,
        llm_model=llm_model,
        temperature=0.0,  # Use 0.0 for SQL generation
    )

    return create_fraud_agent_node(
        sql_agent=sql_agent,
        llm_model=llm_model,
        temperature=temperature,
        model_dir=model_dir,
    )

