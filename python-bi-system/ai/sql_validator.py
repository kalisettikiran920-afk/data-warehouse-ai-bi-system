"""
ai/sql_validator.py
===================
SQL Security & Validation Layer

Ensures that LLM-generated queries are strictly READ-ONLY SELECT queries
and cannot modify or corrupt the DuckDB database.
"""

import re
import logging

log = logging.getLogger(__name__)

# List of dangerous SQL keywords that modify data, structure, or settings
FORBIDDEN_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE",
    "ATTACH", "COPY", "PRAGMA", "EXEC", "EXECUTE", "GRANT", "REVOKE",
    "IMPORT", "EXPORT", "LOAD", "INSTALL", "VACUUM", "CHECKPOINT"
]

ALLOWED_TABLES = {"fact_sales", "dim_customers", "dim_products"}


def validate_sql(sql_query: str) -> tuple[bool, str]:
    """
    Validate an LLM-generated SQL query.

    Returns:
        (is_valid: bool, reason: str)
    """
    if not sql_query or not sql_query.strip():
        return False, "Query is empty."

    # 1. Clean query of comments and surrounding whitespace
    cleaned = re.sub(r"--.*", "", sql_query)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL).strip()

    upper_query = cleaned.upper()

    # 2. Must start with SELECT or WITH
    if not (upper_query.startswith("SELECT") or upper_query.startswith("WITH")):
        return False, "Query must be a SELECT or WITH statement."

    # 3. Check for multiple statements (semicolon check)
    query_body = cleaned.rstrip(";").strip()
    if ";" in query_body:
        return False, "Multiple SQL statements are not allowed."

    # 4. Check for forbidden data-modifying keywords
    # Use word boundary to avoid matching substring inside identifiers
    for kw in FORBIDDEN_KEYWORDS:
        pattern = r"\b" + kw + r"\b"
        if re.search(pattern, upper_query):
            return False, f"Forbidden keyword detected: {kw}"

    # 5. Check table references (simple regex table name check)
    # Ensure query targets allowed tables
    referenced_tables = set(re.findall(r"\bFROM\s+([a-zA-Z0-9_]+)|\bJOIN\s+([a-zA-Z0-9_]+)", cleaned, re.IGNORECASE))
    found_tables = {t for tup in referenced_tables for t in tup if t}

    if found_tables:
        invalid_tables = found_tables - ALLOWED_TABLES
        if invalid_tables:
            # Note: We warn or enforce if user attempts to query internal/bronze/silver tables
            for tbl in invalid_tables:
                if tbl.lower().startswith("bronze_") or tbl.lower().startswith("silver_"):
                    return False, f"Querying internal stage table '{tbl}' is forbidden. Only Gold star schema tables are permitted."

    return True, "OK"
