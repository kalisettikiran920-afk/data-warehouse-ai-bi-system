"""
ai/assistant.py
===============
Natural Language Question -> DuckDB SQL -> Execution -> Explanation Pipeline
"""

import os
import logging
from pathlib import Path

import duckdb
import pandas as pd
from dotenv import load_dotenv

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DB_PATH
from ai.sql_validator import validate_sql

# Load environment variables (.env file)
load_dotenv()

log = logging.getLogger(__name__)

# System schema prompt explaining Gold Layer Star Schema
SCHEMA_PROMPT = """
You are a SQL expert for a Business Intelligence system running on DuckDB.
Your task is to generate a single valid READ-ONLY DuckDB SQL query to answer the user's business question.

DATABASE SCHEMA:

1. Table: fact_sales
   - order_number (VARCHAR): Unique sales order identifier (e.g. 'SO54496')
   - product_key (INT): Foreign key linking to dim_products.product_key
   - customer_key (INT): Foreign key linking to dim_customers.customer_key
   - order_date (DATE): Date order was placed
   - shipping_date (DATE): Date order was shipped
   - due_date (DATE): Payment due date
   - sales_amount (DOUBLE): Total revenue for line item ($)
   - quantity (INT): Number of units ordered
   - price (DOUBLE): Price per unit ($)

2. Table: dim_customers
   - customer_key (INT): Surrogate Primary Key
   - customer_id (INT): Source CRM customer ID
   - customer_number (VARCHAR): Alphanumeric customer code
   - first_name (VARCHAR): Customer first name
   - last_name (VARCHAR): Customer last name
   - country (VARCHAR): Country of residence (e.g. 'Australia', 'United States', 'Germany')
   - marital_status (VARCHAR): 'Single', 'Married', 'n/a'
   - gender (VARCHAR): 'Female', 'Male', 'n/a'
   - birthdate (DATE): Date of birth
   - create_date (DATE): Account creation date

3. Table: dim_products
   - product_key (INT): Surrogate Primary Key
   - product_id (INT): Source CRM product ID
   - product_number (VARCHAR): Alphanumeric product key
   - product_name (VARCHAR): Descriptive product name
   - category_id (VARCHAR): Category ID code
   - category (VARCHAR): High-level category (e.g. 'Bikes', 'Components', 'Clothing', 'Accessories')
   - subcategory (VARCHAR): Detailed product subcategory
   - maintenance (VARCHAR): Maintenance required ('Yes'/'No')
   - cost (INT): Product cost ($)
   - product_line (VARCHAR): 'Mountain', 'Road', 'Touring', 'Other Sales'
   - start_date (DATE): Product release start date

RULES FOR SQL GENERATION:
1. Return ONLY the raw SQL query. Do NOT use markdown backticks (e.g. no ```sql).
2. Write a single SELECT or WITH statement. No data modifications.
3. Use aliases: 'f' for fact_sales, 'c' for dim_customers, 'p' for dim_products.
4. For date filtering/grouping, use DuckDB functions: YEAR(order_date), MONTH(order_date), DATE_TRUNC('month', order_date).
5. If user asks for top items, use ORDER BY ... DESC LIMIT N (default LIMIT 10 if not specified).
6. Join fact_sales with dim_customers or dim_products using customer_key and product_key respectively.
"""


def _get_groq_client():
    """Returns a Groq API client instance."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set in environment or .env file.")
    
    from groq import Groq
    return Groq(api_key=api_key)


MODEL_PRIORITY_LIST = [
    "groq/compound",
    "groq/compound-mini",
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "qwen/qwen3.8-27b",
]


def _call_groq_with_fallback(messages: list, temperature: float = 0.0, max_tokens: int = 400):
    """Calls Groq API trying a prioritized list of model candidates to handle model deprecations / 404 errors."""
    client = _get_groq_client()
    last_exception = None

    for model_name in MODEL_PRIORITY_LIST:
        try:
            log.info(f"Attempting Groq API completion with model: {model_name}")
            return client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            err_msg = str(exc).lower()
            if "model_not_found" in err_msg or "does not exist" in err_msg or "404" in err_msg or "access" in err_msg:
                log.warning(f"Groq model '{model_name}' unavailable ({exc}). Trying next fallback...")
                last_exception = exc
                continue
            raise exc

    if last_exception:
        raise last_exception
    raise RuntimeError("No working Groq model available.")


def generate_sql_query(user_question: str) -> str:
    """Generate SQL query from natural language question using Groq LLM with model fallback."""
    response = _call_groq_with_fallback(
        messages=[
            {"role": "system", "content": SCHEMA_PROMPT},
            {"role": "user", "content": user_question},
        ],
        temperature=0.0,
        max_tokens=400,
    )
    
    raw_sql = response.choices[0].message.content.strip()
    # Strip any stray markdown syntax
    cleaned_sql = raw_sql.replace("```sql", "").replace("```", "").strip()
    return cleaned_sql


def explain_query_result(user_question: str, sql_query: str, df_result: pd.DataFrame) -> str:
    """Generate a short business summary explanation of the query result."""
    summary_data = df_result.head(10).to_string(index=False)
    
    explanation_prompt = f"""
    The user asked: "{user_question}"
    SQL Query executed:
    {sql_query}
    
    Query Result Data:
    {summary_data}
    
    Provide a concise 2-sentence business summary of this answer. Focus on key numbers and facts. Do not mention SQL or technical database details.
    """
    
    response = _call_groq_with_fallback(
        messages=[
            {"role": "user", "content": explanation_prompt},
        ],
        temperature=0.3,
        max_tokens=200,
    )
    
    return response.choices[0].message.content.strip()


def process_user_question(user_question: str) -> dict:
    """
    Complete end-to-end pipeline:
      Question -> SQL Generation -> Security Validation -> Execution -> Business Summary

    Returns a dict with keys:
        - success (bool)
        - sql (str)
        - dataframe (pd.DataFrame or None)
        - explanation (str)
        - error (str or None)
    """
    try:
        # Step 1: Generate SQL
        sql = generate_sql_query(user_question)
        
        # Step 2: Validate SQL safety
        is_valid, reason = validate_sql(sql)
        if not is_valid:
            return {
                "success": False,
                "sql": sql,
                "dataframe": None,
                "explanation": None,
                "error": f"SQL Safety Validation Failed: {reason}",
            }
        
        # Step 3: Execute query against DuckDB
        con = duckdb.connect(str(DB_PATH), read_only=True)
        df = con.execute(sql).df()
        con.close()
        
        if df.empty:
            return {
                "success": True,
                "sql": sql,
                "dataframe": df,
                "explanation": "The query executed successfully but returned 0 records for the requested criteria.",
                "error": None,
            }
        
        # Step 4: Generate business explanation
        explanation = explain_query_result(user_question, sql, df)
        
        return {
            "success": True,
            "sql": sql,
            "dataframe": df,
            "explanation": explanation,
            "error": None,
        }
        
    except Exception as exc:
        log.exception("Error processing question: %s", user_question)
        return {
            "success": False,
            "sql": None,
            "dataframe": None,
            "explanation": None,
            "error": str(exc),
        }
