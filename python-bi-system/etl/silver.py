"""
etl/silver.py
=============
SILVER LAYER — Data Cleansing, Standardisation & Normalisation

Purpose:
    Transform raw tables from the Bronze layer into cleaned, standardized,
    and normalized Silver layer tables in DuckDB.

    This directly reproduces the exact business logic from the SQL Server Data Warehouse
    stored procedure `silver.load_silver` (proc_load_silver.sql).

Tables Transformed:
    1. silver_crm_cust_info   — Deduplicated customer records, normalized marital status & gender
    2. silver_crm_prd_info    — Extracted category IDs, mapped product lines, calculated product end dates
    3. silver_crm_sales_details — Cleaned & parsed YYYYMMDD dates, validated sales/quantity/price consistency
    4. silver_erp_cust_az12   — Cleaned customer IDs (removed 'NAS' prefix), validated birthdates, normalized gender
    5. silver_erp_loc_a101    — Cleaned customer IDs (removed hyphen), normalized country names ('DE' -> Germany, 'US'/'USA' -> United States)
    6. silver_erp_px_cat_g1v2 — Cleaned product category hierarchy
"""

import logging
import time
from datetime import datetime

import duckdb
import numpy as np
import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DB_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def get_connection() -> duckdb.DuckDBPyConnection:
    """Connect to the DuckDB database file."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH))


def _save_to_duckdb(con: duckdb.DuckDBPyConnection, df: pd.DataFrame, table_name: str) -> int:
    """Helper to save a pandas DataFrame into a DuckDB table."""
    con.register("_staging_silver", df)
    con.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM _staging_silver")
    con.unregister("_staging_silver")
    return len(df)


# ---------------------------------------------------------------------------
# 1. Transform CRM Customer Info
# ---------------------------------------------------------------------------
def _transform_crm_cust_info(con: duckdb.DuckDBPyConnection) -> int:
    """
    SQL Logic Reference (proc_load_silver.sql):
        - Filter out NULL cst_id
        - Select most recent record per cst_id (flag_last = 1 order by cst_create_date desc)
        - Trim cst_firstname, cst_lastname
        - Normalize marital status ('S' -> 'Single', 'M' -> 'Married', else 'n/a')
        - Normalize gender ('F' -> 'Female', 'M' -> 'Male', else 'n/a')
    """
    t0 = time.time()
    log.info("  >> Transforming: silver_crm_cust_info")

    df = con.execute("SELECT * FROM bronze_crm_cust_info").df()
    df.columns = df.columns.str.lower()

    # Safely convert cst_id to numeric, coercing empty strings '' to NaN
    df["cst_id"] = pd.to_numeric(df["cst_id"], errors="coerce")
    # Filter out NULL / NaN cst_id
    df = df[df["cst_id"].notna()].copy()
    df["cst_id"] = df["cst_id"].astype(int)

    # Sort by cst_create_date DESC to keep the most recent record per cst_id
    df["cst_create_date_dt"] = pd.to_datetime(df["cst_create_date"], errors="coerce")
    df = df.sort_values(by=["cst_id", "cst_create_date_dt"], ascending=[True, False])
    df = df.drop_duplicates(subset=["cst_id"], keep="first").copy()
    df = df.drop(columns=["cst_create_date_dt"])

    # String cleaning & normalization
    df["cst_key"] = df["cst_key"].astype(str).str.strip()
    df["cst_firstname"] = df["cst_firstname"].astype(str).str.strip()
    df["cst_lastname"] = df["cst_lastname"].astype(str).str.strip()

    # Marital status normalization
    status_upper = df["cst_marital_status"].astype(str).str.strip().str.upper()
    df["cst_marital_status"] = np.select(
        [status_upper == "S", status_upper == "M"],
        ["Single", "Married"],
        default="n/a",
    )

    # Gender normalization
    gndr_upper = df["cst_gndr"].astype(str).str.strip().str.upper()
    df["cst_gndr"] = np.select(
        [gndr_upper == "F", gndr_upper == "M"],
        ["Female", "Male"],
        default="n/a",
    )

    cols = [
        "cst_id",
        "cst_key",
        "cst_firstname",
        "cst_lastname",
        "cst_marital_status",
        "cst_gndr",
        "cst_create_date",
    ]
    df_clean = df[cols].copy()

    count = _save_to_duckdb(con, df_clean, "silver_crm_cust_info")
    log.info("     Rows transformed: %d (Duration: %.2f s)", count, time.time() - t0)
    return count


# ---------------------------------------------------------------------------
# 2. Transform CRM Product Info
# ---------------------------------------------------------------------------
def _transform_crm_prd_info(con: duckdb.DuckDBPyConnection) -> int:
    """
    SQL Logic Reference (proc_load_silver.sql):
        - cat_id = REPLACE(SUBSTRING(prd_key, 1, 5), '-', '_')
        - prd_key = SUBSTRING(prd_key, 7, LEN(prd_key))
        - prd_cost = ISNULL(prd_cost, 0)
        - prd_line mapping ('M' -> 'Mountain', 'R' -> 'Road', 'S' -> 'Other Sales', 'T' -> 'Touring', else 'n/a')
        - prd_start_dt = CAST(prd_start_dt AS DATE)
        - prd_end_dt = LEAD(prd_start_dt) OVER (PARTITION BY prd_key ORDER BY prd_start_dt) - 1
    """
    t0 = time.time()
    log.info("  >> Transforming: silver_crm_prd_info")

    df = con.execute("SELECT * FROM bronze_crm_prd_info").df()
    df.columns = df.columns.str.lower()

    df["prd_id"] = pd.to_numeric(df["prd_id"], errors="coerce").fillna(0).astype(int)
    prd_key_str = df["prd_key"].astype(str).str.strip()

    # Extract cat_id (chars 1-5, replace '-' with '_') and refined prd_key (char 7+)
    df["cat_id"] = prd_key_str.str[:5].str.replace("-", "_")
    df["prd_key"] = prd_key_str.str[6:]

    df["prd_nm"] = df["prd_nm"].astype(str).str.strip()

    # prd_cost NULL replacement
    df["prd_cost"] = pd.to_numeric(df["prd_cost"], errors="coerce").fillna(0).astype(int)

    # Product line mapping
    line_upper = df["prd_line"].astype(str).str.strip().str.upper()
    df["prd_line"] = np.select(
        [line_upper == "M", line_upper == "R", line_upper == "S", line_upper == "T"],
        ["Mountain", "Road", "Other Sales", "Touring"],
        default="n/a",
    )

    # Convert start date
    df["prd_start_dt"] = pd.to_datetime(df["prd_start_dt"], errors="coerce").dt.date

    # Calculate end date using LEAD window logic per prd_key group ordered by prd_start_dt
    df = df.sort_values(by=["prd_key", "prd_start_dt"]).reset_index(drop=True)
    df["next_start_dt"] = df.groupby("prd_key")["prd_start_dt"].shift(-1)
    
    # prd_end_dt is next_start_dt - 1 day
    df["prd_end_dt"] = pd.to_datetime(df["next_start_dt"]) - pd.Timedelta(days=1)
    df["prd_end_dt"] = df["prd_end_dt"].dt.date
    df = df.drop(columns=["next_start_dt"])

    cols = [
        "prd_id",
        "cat_id",
        "prd_key",
        "prd_nm",
        "prd_cost",
        "prd_line",
        "prd_start_dt",
        "prd_end_dt",
    ]
    df_clean = df[cols].copy()

    count = _save_to_duckdb(con, df_clean, "silver_crm_prd_info")
    log.info("     Rows transformed: %d (Duration: %.2f s)", count, time.time() - t0)
    return count


# ---------------------------------------------------------------------------
# 3. Transform CRM Sales Details
# ---------------------------------------------------------------------------
def _transform_crm_sales_details(con: duckdb.DuckDBPyConnection) -> int:
    """
    SQL Logic Reference (proc_load_silver.sql):
        - Invalid dates (0 or length != 8) set to NULL, else converted to DATE
        - sls_sales recalculated as sls_quantity * ABS(sls_price) if NULL, <= 0, or != quantity * price
        - sls_price derived as sls_sales / sls_quantity if NULL or <= 0
    """
    t0 = time.time()
    log.info("  >> Transforming: silver_crm_sales_details")

    df = con.execute("SELECT * FROM bronze_crm_sales_details").df()
    df.columns = df.columns.str.lower()

    def parse_int_date(series: pd.Series) -> pd.Series:
        """Parses YYYYMMDD integer/string date representations into datetime.date."""
        s_str = series.astype(str).str.split(".").str[0].str.strip()
        valid_mask = (s_str != "0") & (s_str.str.len() == 8) & (s_str != "nan") & (s_str != "None") & (s_str != "")
        result = pd.Series(index=series.index, dtype="object")
        result[valid_mask] = pd.to_datetime(s_str[valid_mask], format="%Y%m%d", errors="coerce").dt.date
        return result

    df["sls_order_dt"] = parse_int_date(df["sls_order_dt"])
    df["sls_ship_dt"] = parse_int_date(df["sls_ship_dt"])
    df["sls_due_dt"] = parse_int_date(df["sls_due_dt"])

    df["sls_quantity"] = pd.to_numeric(df["sls_quantity"], errors="coerce")
    df["sls_price"] = pd.to_numeric(df["sls_price"], errors="coerce")
    df["sls_sales"] = pd.to_numeric(df["sls_sales"], errors="coerce")

    # Derive price when price is missing/invalid but sales and quantity are present
    price_invalid = df["sls_price"].isna() | (df["sls_price"] <= 0)
    has_sales = df["sls_sales"].notna() & (df["sls_sales"] > 0)
    has_qty = df["sls_quantity"].notna() & (df["sls_quantity"] > 0)

    df["sls_price"] = np.where(
        price_invalid & has_sales & has_qty,
        df["sls_sales"] / df["sls_quantity"],
        df["sls_price"]
    )

    # Recalculate sales when sales is missing/invalid or doesn't match qty * price
    calc_sales = df["sls_quantity"] * df["sls_price"].abs()
    has_price = df["sls_price"].notna() & (df["sls_price"] > 0)

    sales_invalid = (
        df["sls_sales"].isna()
        | (df["sls_sales"] <= 0)
        | (has_price & (df["sls_sales"] != calc_sales))
    )

    df["sls_sales"] = np.where(
        sales_invalid & has_price & has_qty,
        calc_sales,
        df["sls_sales"]
    )

    df["sls_ord_num"] = df["sls_ord_num"].astype(str).str.strip()
    df["sls_prd_key"] = df["sls_prd_key"].astype(str).str.strip()
    df["sls_cust_id"] = pd.to_numeric(df["sls_cust_id"], errors="coerce").astype("Int64")

    cols = [
        "sls_ord_num",
        "sls_prd_key",
        "sls_cust_id",
        "sls_order_dt",
        "sls_ship_dt",
        "sls_due_dt",
        "sls_sales",
        "sls_quantity",
        "sls_price",
    ]
    df_clean = df[cols].copy()

    count = _save_to_duckdb(con, df_clean, "silver_crm_sales_details")
    log.info("     Rows transformed: %d (Duration: %.2f s)", count, time.time() - t0)
    return count


# ---------------------------------------------------------------------------
# 4. Transform ERP Customer AZ12
# ---------------------------------------------------------------------------
def _transform_erp_cust_az12(con: duckdb.DuckDBPyConnection) -> int:
    """
    SQL Logic Reference (proc_load_silver.sql):
        - Remove 'NAS' prefix from cid if present
        - bdate > GETDATE() set to NULL
        - gen normalized ('F'/'FEMALE' -> 'Female', 'M'/'MALE' -> 'Male', else 'n/a')
    """
    t0 = time.time()
    log.info("  >> Transforming: silver_erp_cust_az12")

    df = con.execute("SELECT * FROM bronze_erp_cust_az12").df()
    df.columns = df.columns.str.lower()

    cid_str = df["cid"].astype(str).str.strip()
    df["cid"] = np.where(cid_str.str.startswith("NAS"), cid_str.str[3:], cid_str)

    bdate_dt = pd.to_datetime(df["bdate"], errors="coerce")
    today = pd.Timestamp.today().floor("D")
    bdate_valid = np.where(bdate_dt > today, pd.NaT, bdate_dt)
    df["bdate"] = pd.to_datetime(bdate_valid).date

    gen_upper = df["gen"].astype(str).str.strip().str.upper()
    df["gen"] = np.select(
        [gen_upper.isin(["F", "FEMALE"]), gen_upper.isin(["M", "MALE"])],
        ["Female", "Male"],
        default="n/a",
    )

    cols = ["cid", "bdate", "gen"]
    df_clean = df[cols].copy()

    count = _save_to_duckdb(con, df_clean, "silver_erp_cust_az12")
    log.info("     Rows transformed: %d (Duration: %.2f s)", count, time.time() - t0)
    return count


# ---------------------------------------------------------------------------
# 5. Transform ERP Location A101
# ---------------------------------------------------------------------------
def _transform_erp_loc_a101(con: duckdb.DuckDBPyConnection) -> int:
    """
    SQL Logic Reference (proc_load_silver.sql):
        - REPLACE(cid, '-', '')
        - Normalize cntry: 'DE' -> 'Germany', 'US'/'USA' -> 'United States', blank/null -> 'n/a', else TRIM(cntry)
    """
    t0 = time.time()
    log.info("  >> Transforming: silver_erp_loc_a101")

    df = con.execute("SELECT * FROM bronze_erp_loc_a101").df()
    df.columns = df.columns.str.lower()

    df["cid"] = df["cid"].astype(str).str.replace("-", "").str.strip()

    cntry_trim = df["cntry"].astype(str).str.strip()
    is_empty = (cntry_trim == "") | (cntry_trim.isna()) | (cntry_trim == "nan") | (cntry_trim == "None")

    df["cntry"] = np.select(
        [cntry_trim == "DE", cntry_trim.isin(["US", "USA"]), is_empty],
        ["Germany", "United States", "n/a"],
        default=cntry_trim,
    )

    cols = ["cid", "cntry"]
    df_clean = df[cols].copy()

    count = _save_to_duckdb(con, df_clean, "silver_erp_loc_a101")
    log.info("     Rows transformed: %d (Duration: %.2f s)", count, time.time() - t0)
    return count


# ---------------------------------------------------------------------------
# 6. Transform ERP Product Categories
# ---------------------------------------------------------------------------
def _transform_erp_px_cat_g1v2(con: duckdb.DuckDBPyConnection) -> int:
    """
    SQL Logic Reference (proc_load_silver.sql):
        - Clean string fields for product categories, subcategories, maintenance.
    """
    t0 = time.time()
    log.info("  >> Transforming: silver_erp_px_cat_g1v2")

    df = con.execute("SELECT * FROM bronze_erp_px_cat_g1v2").df()
    df.columns = df.columns.str.lower()

    for col in ["id", "cat", "subcat", "maintenance"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    cols = ["id", "cat", "subcat", "maintenance"]
    df_clean = df[cols].copy()

    count = _save_to_duckdb(con, df_clean, "silver_erp_px_cat_g1v2")
    log.info("     Rows transformed: %d (Duration: %.2f s)", count, time.time() - t0)
    return count


# ---------------------------------------------------------------------------
# Public Pipeline Function
# ---------------------------------------------------------------------------
def run(con: duckdb.DuckDBPyConnection | None = None) -> dict[str, int]:
    """Run all Silver layer transformations."""
    own_connection = con is None
    if own_connection:
        con = get_connection()

    batch_start = time.time()
    log.info("=" * 60)
    log.info("SILVER LAYER — Transformations started at %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 60)

    row_counts: dict[str, int] = {}

    try:
        row_counts["silver_crm_cust_info"] = _transform_crm_cust_info(con)
        row_counts["silver_crm_prd_info"] = _transform_crm_prd_info(con)
        row_counts["silver_crm_sales_details"] = _transform_crm_sales_details(con)
        row_counts["silver_erp_cust_az12"] = _transform_erp_cust_az12(con)
        row_counts["silver_erp_loc_a101"] = _transform_erp_loc_a101(con)
        row_counts["silver_erp_px_cat_g1v2"] = _transform_erp_px_cat_g1v2(con)

        elapsed = time.time() - batch_start
        log.info("=" * 60)
        log.info("SILVER LAYER — Completed in %.2f s", elapsed)
        log.info("Row counts:")
        for table, count in row_counts.items():
            log.info("  %-35s %d", table, count)
        log.info("=" * 60)

        return row_counts

    except Exception:
        log.exception("SILVER LAYER — FAILED")
        raise

    finally:
        if own_connection:
            con.close()


# ---------------------------------------------------------------------------
# Verification Function
# ---------------------------------------------------------------------------
def verify(con: duckdb.DuckDBPyConnection | None = None) -> bool:
    """
    Quality checks for Silver Layer matching quality_checks_silver.sql:
      1. Check for duplicate or NULL primary keys in cst_id and prd_id.
      2. Check for unexpected values in marital status and gender.
      3. Check for negative costs in silver_crm_prd_info.
      4. Check that sls_sales == sls_quantity * sls_price in silver_crm_sales_details.
      5. Check for invalid date relationships (e.g. prd_end_dt < prd_start_dt).
    """
    own_connection = con is None
    if own_connection:
        con = get_connection()

    log.info("=" * 60)
    log.info("SILVER VERIFICATION — Running Data Quality Checks")
    log.info("=" * 60)

    all_passed = True

    # 1. Customer PK check
    cust_dup = con.execute("""
        SELECT cst_id, COUNT(*) FROM silver_crm_cust_info
        GROUP BY cst_id HAVING COUNT(*) > 1 OR cst_id IS NULL
    """).fetchall()
    if cust_dup:
        log.error("  FAIL  silver_crm_cust_info — Duplicate or NULL cst_id found: %s", cust_dup)
        all_passed = False
    else:
        log.info("  PASS  silver_crm_cust_info — Primary key cst_id is unique and non-null")

    # 2. Product PK check
    prd_dup = con.execute("""
        SELECT prd_id, COUNT(*) FROM silver_crm_prd_info
        GROUP BY prd_id HAVING COUNT(*) > 1 OR prd_id IS NULL
    """).fetchall()
    if prd_dup:
        log.error("  FAIL  silver_crm_prd_info — Duplicate or NULL prd_id found: %s", prd_dup)
        all_passed = False
    else:
        log.info("  PASS  silver_crm_prd_info — Primary key prd_id is unique and non-null")

    # 3. Product cost check
    neg_cost = con.execute("""
        SELECT COUNT(*) FROM silver_crm_prd_info WHERE prd_cost < 0 OR prd_cost IS NULL
    """).fetchone()[0]
    if neg_cost > 0:
        log.error("  FAIL  silver_crm_prd_info — Invalid costs found: %d", neg_cost)
        all_passed = False
    else:
        log.info("  PASS  silver_crm_prd_info — Costs are valid and non-negative")

    # 4. Product date range check
    inv_prd_dates = con.execute("""
        SELECT COUNT(*) FROM silver_crm_prd_info WHERE prd_end_dt < prd_start_dt
    """).fetchone()[0]
    if inv_prd_dates > 0:
        log.error("  FAIL  silver_crm_prd_info — Invalid date ranges (end < start): %d", inv_prd_dates)
        all_passed = False
    else:
        log.info("  PASS  silver_crm_prd_info — Product date ranges are valid")

    # 5. Sales formula consistency check
    sales_mismatch = con.execute("""
        SELECT COUNT(*) FROM silver_crm_sales_details
        WHERE sls_sales != sls_quantity * sls_price
           OR sls_sales IS NULL OR sls_sales <= 0
    """).fetchone()[0]
    if sales_mismatch > 0:
        log.error("  FAIL  silver_crm_sales_details — Sales calculation mismatch: %d rows", sales_mismatch)
        all_passed = False
    else:
        log.info("  PASS  silver_crm_sales_details — All sales = quantity * price calculations match")

    # 6. Future birthdate check
    fut_bdate = con.execute("""
        SELECT COUNT(*) FROM silver_erp_cust_az12 WHERE bdate > CURRENT_DATE
    """).fetchone()[0]
    if fut_bdate > 0:
        log.error("  FAIL  silver_erp_cust_az12 — Future birthdates found: %d", fut_bdate)
        all_passed = False
    else:
        log.info("  PASS  silver_erp_cust_az12 — Birthdates are valid")

    log.info("-" * 60)
    if all_passed:
        log.info("SILVER VERIFICATION — ALL CHECKS PASSED")
    else:
        log.error("SILVER VERIFICATION — ONE OR MORE CHECKS FAILED")
    log.info("=" * 60)

    if own_connection:
        con.close()

    return all_passed


if __name__ == "__main__":
    con = get_connection()
    run(con)
    verify(con)
    con.close()
