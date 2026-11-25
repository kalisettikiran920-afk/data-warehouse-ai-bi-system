"""
etl/gold.py
===========
GOLD LAYER — Business Analytical Layer (Star Schema)

Purpose:
    Model business-ready dimension and fact tables (Star Schema) from the Silver layer.

    This directly reproduces the exact data modeling logic from the SQL Server Data Warehouse
    script `ddl_gold.sql`.

Tables Created:
    1. dim_customers — Customer dimension table enriched with ERP demographic and location data.
    2. dim_products  — Product dimension table filtered for current active products (prd_end_dt IS NULL)
                        and enriched with ERP category hierarchy.
    3. fact_sales    — Transactional sales fact table linked via surrogate keys (customer_key, product_key)
                        to dimension tables.
"""

import logging
import time
from datetime import datetime

import duckdb
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


# ---------------------------------------------------------------------------
# 1. Build dim_customers
# ---------------------------------------------------------------------------
def _build_dim_customers(con: duckdb.DuckDBPyConnection) -> int:
    """
    SQL Logic Reference (ddl_gold.sql):
        SELECT
            ROW_NUMBER() OVER (ORDER BY cst_id) AS customer_key,
            ci.cst_id                          AS customer_id,
            ci.cst_key                         AS customer_number,
            ci.cst_firstname                   AS first_name,
            ci.cst_lastname                    AS last_name,
            la.cntry                           AS country,
            ci.cst_marital_status              AS marital_status,
            CASE 
                WHEN ci.cst_gndr != 'n/a' THEN ci.cst_gndr
                ELSE COALESCE(ca.gen, 'n/a')
            END                                AS gender,
            ca.bdate                           AS birthdate,
            ci.cst_create_date                 AS create_date
        FROM silver_crm_cust_info ci
        LEFT JOIN silver_erp_cust_az12 ca ON ci.cst_key = ca.cid
        LEFT JOIN silver_erp_loc_a101 la  ON ci.cst_key = la.cid;
    """
    t0 = time.time()
    log.info("  >> Building: dim_customers")

    query = """
    CREATE OR REPLACE TABLE dim_customers AS
    SELECT
        ROW_NUMBER() OVER (ORDER BY ci.cst_id) AS customer_key,
        ci.cst_id                             AS customer_id,
        ci.cst_key                            AS customer_number,
        ci.cst_firstname                      AS first_name,
        ci.cst_lastname                       AS last_name,
        COALESCE(la.cntry, 'n/a')             AS country,
        ci.cst_marital_status                 AS marital_status,
        CASE 
            WHEN ci.cst_gndr != 'n/a' THEN ci.cst_gndr
            ELSE COALESCE(ca.gen, 'n/a')
        END                                   AS gender,
        ca.bdate                              AS birthdate,
        ci.cst_create_date                    AS create_date
    FROM silver_crm_cust_info ci
    LEFT JOIN silver_erp_cust_az12 ca ON ci.cst_key = ca.cid
    LEFT JOIN silver_erp_loc_a101 la  ON ci.cst_key = la.cid;
    """
    con.execute(query)

    count = con.execute("SELECT COUNT(*) FROM dim_customers").fetchone()[0]
    log.info("     Rows built: %d (Duration: %.2f s)", count, time.time() - t0)
    return count


# ---------------------------------------------------------------------------
# 2. Build dim_products
# ---------------------------------------------------------------------------
def _build_dim_products(con: duckdb.DuckDBPyConnection) -> int:
    """
    SQL Logic Reference (ddl_gold.sql):
        SELECT
            ROW_NUMBER() OVER (ORDER BY pn.prd_start_dt, pn.prd_key) AS product_key,
            pn.prd_id       AS product_id,
            pn.prd_key      AS product_number,
            pn.prd_nm       AS product_name,
            pn.cat_id       AS category_id,
            pc.cat          AS category,
            pc.subcat       AS subcategory,
            pc.maintenance  AS maintenance,
            pn.prd_cost     AS cost,
            pn.prd_line     AS product_line,
            pn.prd_start_dt AS start_date
        FROM silver_crm_prd_info pn
        LEFT JOIN silver_erp_px_cat_g1v2 pc ON pn.cat_id = pc.id
        WHERE pn.prd_end_dt IS NULL;
    """
    t0 = time.time()
    log.info("  >> Building: dim_products")

    query = """
    CREATE OR REPLACE TABLE dim_products AS
    SELECT
        ROW_NUMBER() OVER (ORDER BY pn.prd_start_dt, pn.prd_key) AS product_key,
        pn.prd_id                                                AS product_id,
        pn.prd_key                                               AS product_number,
        pn.prd_nm                                                AS product_name,
        pn.cat_id                                                AS category_id,
        COALESCE(pc.cat, 'n/a')                                  AS category,
        COALESCE(pc.subcat, 'n/a')                               AS subcategory,
        COALESCE(pc.maintenance, 'n/a')                          AS maintenance,
        pn.prd_cost                                              AS cost,
        pn.prd_line                                              AS product_line,
        pn.prd_start_dt                                          AS start_date
    FROM silver_crm_prd_info pn
    LEFT JOIN silver_erp_px_cat_g1v2 pc ON pn.cat_id = pc.id
    WHERE pn.prd_end_dt IS NULL;
    """
    con.execute(query)

    count = con.execute("SELECT COUNT(*) FROM dim_products").fetchone()[0]
    log.info("     Rows built: %d (Duration: %.2f s)", count, time.time() - t0)
    return count


# ---------------------------------------------------------------------------
# 3. Build fact_sales
# ---------------------------------------------------------------------------
def _build_fact_sales(con: duckdb.DuckDBPyConnection) -> int:
    """
    SQL Logic Reference (ddl_gold.sql):
        SELECT
            sd.sls_ord_num  AS order_number,
            pr.product_key  AS product_key,
            cu.customer_key AS customer_key,
            sd.sls_order_dt AS order_date,
            sd.sls_ship_dt  AS shipping_date,
            sd.sls_due_dt   AS due_date,
            sd.sls_sales    AS sales_amount,
            sd.sls_quantity AS quantity,
            sd.sls_price    AS price
        FROM silver_crm_sales_details sd
        LEFT JOIN dim_products pr ON sd.sls_prd_key = pr.product_number
        LEFT JOIN dim_customers cu ON sd.sls_cust_id = cu.customer_id;
    """
    t0 = time.time()
    log.info("  >> Building: fact_sales")

    query = """
    CREATE OR REPLACE TABLE fact_sales AS
    SELECT
        sd.sls_ord_num  AS order_number,
        pr.product_key  AS product_key,
        cu.customer_key AS customer_key,
        sd.sls_order_dt AS order_date,
        sd.sls_ship_dt  AS shipping_date,
        sd.sls_due_dt   AS due_date,
        sd.sls_sales    AS sales_amount,
        sd.sls_quantity AS quantity,
        sd.sls_price    AS price
    FROM silver_crm_sales_details sd
    LEFT JOIN dim_products pr ON sd.sls_prd_key = pr.product_number
    LEFT JOIN dim_customers cu ON sd.sls_cust_id = cu.customer_id;
    """
    con.execute(query)

    count = con.execute("SELECT COUNT(*) FROM fact_sales").fetchone()[0]
    log.info("     Rows built: %d (Duration: %.2f s)", count, time.time() - t0)
    return count


# ---------------------------------------------------------------------------
# Public Pipeline Function
# ---------------------------------------------------------------------------
def run(con: duckdb.DuckDBPyConnection | None = None) -> dict[str, int]:
    """Run Gold layer Star Schema creation."""
    own_connection = con is None
    if own_connection:
        con = get_connection()

    batch_start = time.time()
    log.info("=" * 60)
    log.info("GOLD LAYER — Star Schema creation started at %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 60)

    row_counts: dict[str, int] = {}

    try:
        row_counts["dim_customers"] = _build_dim_customers(con)
        row_counts["dim_products"] = _build_dim_products(con)
        row_counts["fact_sales"] = _build_fact_sales(con)

        elapsed = time.time() - batch_start
        log.info("=" * 60)
        log.info("GOLD LAYER — Completed in %.2f s", elapsed)
        log.info("Row counts:")
        for table, count in row_counts.items():
            log.info("  %-35s %d", table, count)
        log.info("=" * 60)

        return row_counts

    except Exception:
        log.exception("GOLD LAYER — FAILED")
        raise

    finally:
        if own_connection:
            con.close()


# ---------------------------------------------------------------------------
# Verification Function
# ---------------------------------------------------------------------------
def verify(con: duckdb.DuckDBPyConnection | None = None) -> bool:
    """
    Quality checks for Gold Layer matching quality_checks_gold.sql:
      1. Surrogate key uniqueness in dim_customers and dim_products.
      2. Referential integrity in fact_sales (check for orphan product_key or customer_key).
      3. Total revenue calculation check.
    """
    own_connection = con is None
    if own_connection:
        con = get_connection()

    log.info("=" * 60)
    log.info("GOLD VERIFICATION — Running Star Schema Quality Checks")
    log.info("=" * 60)

    all_passed = True

    # 1. Customer Key Uniqueness Check
    cust_dup = con.execute("""
        SELECT customer_key, COUNT(*) FROM dim_customers
        GROUP BY customer_key HAVING COUNT(*) > 1
    """).fetchall()
    if cust_dup:
        log.error("  FAIL  dim_customers — Duplicate customer_key found: %s", cust_dup)
        all_passed = False
    else:
        log.info("  PASS  dim_customers — Surrogate key customer_key is 100%% unique")

    # 2. Product Key Uniqueness Check
    prd_dup = con.execute("""
        SELECT product_key, COUNT(*) FROM dim_products
        GROUP BY product_key HAVING COUNT(*) > 1
    """).fetchall()
    if prd_dup:
        log.error("  FAIL  dim_products — Duplicate product_key found: %s", prd_dup)
        all_passed = False
    else:
        log.info("  PASS  dim_products — Surrogate key product_key is 100%% unique")

    # 3. Referential Integrity Check
    orphan_rows = con.execute("""
        SELECT COUNT(*) 
        FROM fact_sales f
        LEFT JOIN dim_customers c ON f.customer_key = c.customer_key
        LEFT JOIN dim_products p   ON f.product_key = p.product_key
        WHERE p.product_key IS NULL OR c.customer_key IS NULL
    """).fetchone()[0]

    if orphan_rows > 0:
        log.error("  FAIL  fact_sales — Orphan records found (unmatched FKs): %d rows", orphan_rows)
        all_passed = False
    else:
        log.info("  PASS  fact_sales — Referential integrity validated (0 orphan foreign keys)")

    # 4. Gold Layer KPI Overview summary
    rev = con.execute("SELECT SUM(sales_amount) FROM fact_sales").fetchone()[0]
    orders = con.execute("SELECT COUNT(DISTINCT order_number) FROM fact_sales").fetchone()[0]
    customers = con.execute("SELECT COUNT(DISTINCT customer_key) FROM dim_customers").fetchone()[0]
    products = con.execute("SELECT COUNT(DISTINCT product_key) FROM dim_products").fetchone()[0]

    log.info("-" * 60)
    log.info("GOLD LAYER SUMMARY METRICS:")
    log.info("  Total Revenue    : $%s", f"{int(rev):,}" if rev else "0")
    log.info("  Total Sales Orders: %s", f"{orders:,}")
    log.info("  Total Customers  : %s", f"{customers:,}")
    log.info("  Active Products  : %s", f"{products:,}")

    log.info("-" * 60)
    if all_passed:
        log.info("GOLD VERIFICATION — ALL CHECKS PASSED")
    else:
        log.error("GOLD VERIFICATION — ONE OR MORE CHECKS FAILED")
    log.info("=" * 60)

    if own_connection:
        con.close()

    return all_passed


if __name__ == "__main__":
    con = get_connection()
    run(con)
    verify(con)
    con.close()
