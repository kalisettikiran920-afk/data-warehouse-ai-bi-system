"""
etl/bronze.py
=============
BRONZE LAYER — Raw Ingestion

Purpose:
    Load all 6 source CSV files (CRM + ERP) into DuckDB as-is, with no
    transformation. The Bronze layer preserves the original data exactly
    as it arrived from the source systems.

    This mirrors the role of the SQL Server bronze schema and the
    bronze.load_bronze stored procedure in the existing SQL DWH project.

Design decisions:
    - pandas reads each CSV so we have full control over encoding and
      header handling.
    - duckdb.connect().register() maps a pandas DataFrame to a DuckDB
      view, then CREATE OR REPLACE TABLE materialises it permanently.
    - Every run truncates and reloads — same behaviour as the SQL
      TRUNCATE + BULK INSERT pattern in the original project.
    - A dedicated get_connection() helper is used so the caller always
      gets a consistent connection to the same .duckdb file.
"""

import logging
import time
from datetime import datetime

import duckdb
import pandas as pd

# Import path constants from central config
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    DB_PATH,
    CRM_CUST_INFO,
    CRM_PRD_INFO,
    CRM_SALES,
    ERP_CUST_AZ12,
    ERP_LOC_A101,
    ERP_PX_CAT_G1V2,
)

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DuckDB connection helper
# ---------------------------------------------------------------------------
def get_connection() -> duckdb.DuckDBPyConnection:
    """
    Open and return a connection to the project DuckDB file.
    Creates the data/ directory if it does not exist yet.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH))


# ---------------------------------------------------------------------------
# Internal helper — load one CSV into one DuckDB table
# ---------------------------------------------------------------------------
def _load_csv_to_table(
    con: duckdb.DuckDBPyConnection,
    csv_path: Path,
    table_name: str,
    dtype: dict | None = None,
) -> int:
    """
    Read a CSV file with pandas and write it into DuckDB as a permanent table.

    Parameters
    ----------
    con        : open DuckDB connection
    csv_path   : Path to the source CSV file
    table_name : target DuckDB table name (e.g. 'bronze_crm_cust_info')
    dtype      : optional pandas dtype overrides (used where auto-detection
                 would choose the wrong type, e.g. integer date columns)

    Returns
    -------
    int  number of rows loaded
    """
    t0 = time.time()
    log.info("  >> Loading: %s", csv_path.name)

    # Read the CSV — keep_default_na=False so empty strings stay as ''
    # and don't silently become NaN (important for the ERP country column)
    df = pd.read_csv(
        csv_path,
        dtype=dtype,
        keep_default_na=False,   # preserve empty strings
        na_values=["NULL", "null", "\\N"],
    )

    row_count = len(df)

    # Register the DataFrame as a temporary DuckDB relation, then
    # materialise it as a permanent table (CREATE OR REPLACE drops the
    # old table first, matching the SQL TRUNCATE behaviour)
    con.register("_staging", df)
    con.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM _staging")
    con.unregister("_staging")

    elapsed = time.time() - t0
    log.info("     Rows loaded : %d", row_count)
    log.info("     Duration    : %.2f s", elapsed)
    return row_count


# ---------------------------------------------------------------------------
# Public function — run the full Bronze layer load
# ---------------------------------------------------------------------------
def run(con: duckdb.DuckDBPyConnection | None = None) -> dict[str, int]:
    """
    Load all 6 source CSV files into Bronze DuckDB tables.

    Parameters
    ----------
    con : optional existing DuckDB connection.
          If None, a new connection to DB_PATH is opened.

    Returns
    -------
    dict mapping each table name → row count loaded.
    Raises FileNotFoundError if any source CSV is missing.
    """
    own_connection = con is None
    if own_connection:
        con = get_connection()

    batch_start = time.time()
    log.info("=" * 60)
    log.info("BRONZE LAYER — Loading started at %s",
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 60)

    row_counts: dict[str, int] = {}

    try:
        # ----------------------------------------------------------------
        # Validate that all source files exist before starting any loads.
        # Fail early with a clear message rather than a mid-load crash.
        # ----------------------------------------------------------------
        missing = []
        for path in [CRM_CUST_INFO, CRM_PRD_INFO, CRM_SALES,
                     ERP_CUST_AZ12, ERP_LOC_A101, ERP_PX_CAT_G1V2]:
            if not path.exists():
                missing.append(str(path))
        if missing:
            raise FileNotFoundError(
                "The following source files were not found:\n  "
                + "\n  ".join(missing)
            )

        # ----------------------------------------------------------------
        # CRM Tables
        # ----------------------------------------------------------------
        log.info("-" * 60)
        log.info("CRM Tables")
        log.info("-" * 60)

        # crm_cust_info
        # The SQL bronze table stores: cst_id (INT), cst_key, cst_firstname,
        # cst_lastname, cst_marital_status, cst_gndr, cst_create_date (DATE)
        # We let pandas infer types; cst_id will be int64, dates will be
        # parsed in silver.py where we have full control.
        row_counts["bronze_crm_cust_info"] = _load_csv_to_table(
            con,
            CRM_CUST_INFO,
            "bronze_crm_cust_info",
        )

        # crm_prd_info
        # IMPORTANT: prd_cost in the CSV can be NULL/empty.
        # sls_order_dt / sls_ship_dt / sls_due_dt are stored as plain
        # integers in YYYYMMDD format in the original SQL bronze table.
        # We read them as strings here so we don't lose leading zeros or
        # accidentally convert 0 to NaN. Silver.py will handle parsing.
        row_counts["bronze_crm_prd_info"] = _load_csv_to_table(
            con,
            CRM_PRD_INFO,
            "bronze_crm_prd_info",
        )

        # crm_sales_details
        # Date columns (sls_order_dt, sls_ship_dt, sls_due_dt) are stored
        # as integers in YYYYMMDD format in the CSV (e.g. 20110101).
        # We force them to string/object here to preserve '0' values and
        # avoid pandas auto-converting them to float when nulls are present.
        row_counts["bronze_crm_sales_details"] = _load_csv_to_table(
            con,
            CRM_SALES,
            "bronze_crm_sales_details",
            dtype={
                "sls_order_dt": str,
                "sls_ship_dt":  str,
                "sls_due_dt":   str,
            },
        )

        # ----------------------------------------------------------------
        # ERP Tables
        # ----------------------------------------------------------------
        log.info("-" * 60)
        log.info("ERP Tables")
        log.info("-" * 60)

        # erp_cust_az12  (customer demographics: birthdate, gender)
        row_counts["bronze_erp_cust_az12"] = _load_csv_to_table(
            con,
            ERP_CUST_AZ12,
            "bronze_erp_cust_az12",
        )

        # erp_loc_a101  (customer locations: country codes)
        row_counts["bronze_erp_loc_a101"] = _load_csv_to_table(
            con,
            ERP_LOC_A101,
            "bronze_erp_loc_a101",
        )

        # erp_px_cat_g1v2  (product categories)
        row_counts["bronze_erp_px_cat_g1v2"] = _load_csv_to_table(
            con,
            ERP_PX_CAT_G1V2,
            "bronze_erp_px_cat_g1v2",
        )

        # ----------------------------------------------------------------
        # Summary
        # ----------------------------------------------------------------
        elapsed = time.time() - batch_start
        log.info("=" * 60)
        log.info("BRONZE LAYER — Completed in %.2f s", elapsed)
        log.info("Row counts:")
        for table, count in row_counts.items():
            log.info("  %-35s %d", table, count)
        log.info("=" * 60)

        return row_counts

    except Exception:
        log.exception("BRONZE LAYER — FAILED")
        raise

    finally:
        if own_connection:
            con.close()


# ---------------------------------------------------------------------------
# Verification helper — call this after run() to confirm the load
# ---------------------------------------------------------------------------
def verify(con: duckdb.DuckDBPyConnection | None = None) -> bool:
    """
    Run post-load checks on the Bronze layer.

    Checks:
      1. All 6 tables exist in DuckDB.
      2. Each table has at least 1 row (non-empty).
      3. Prints a per-table column summary for manual inspection.

    Returns True if all checks pass, False otherwise.
    """
    own_connection = con is None
    if own_connection:
        con = get_connection()

    expected_tables = [
        "bronze_crm_cust_info",
        "bronze_crm_prd_info",
        "bronze_crm_sales_details",
        "bronze_erp_cust_az12",
        "bronze_erp_loc_a101",
        "bronze_erp_px_cat_g1v2",
    ]

    log.info("=" * 60)
    log.info("BRONZE VERIFICATION")
    log.info("=" * 60)

    all_passed = True

    for table in expected_tables:
        try:
            count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            cols  = [r[0] for r in con.execute(
                f"SELECT column_name FROM information_schema.columns "
                f"WHERE table_name = '{table}' ORDER BY ordinal_position"
            ).fetchall()]

            if count == 0:
                log.warning("  FAIL  %s — 0 rows (table is empty)", table)
                all_passed = False
            else:
                log.info("  PASS  %-35s  rows=%d  cols=%s",
                         table, count, cols)

        except Exception as exc:
            log.error("  FAIL  %s — table not found or query error: %s",
                      table, exc)
            all_passed = False

    log.info("-" * 60)
    if all_passed:
        log.info("BRONZE VERIFICATION — ALL CHECKS PASSED")
    else:
        log.error("BRONZE VERIFICATION — ONE OR MORE CHECKS FAILED")
    log.info("=" * 60)

    if own_connection:
        con.close()

    return all_passed


# ---------------------------------------------------------------------------
# Allow running this file directly for quick testing:
#   python etl/bronze.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    con = get_connection()
    run(con)
    verify(con)
    con.close()
