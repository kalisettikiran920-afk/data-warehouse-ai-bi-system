"""
config.py
=========
Central configuration for the Python BI System.

All file paths, constants, and shared settings are defined here.
Every other module imports from this file — never hardcode paths elsewhere.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Root directories
# ---------------------------------------------------------------------------
BASE_DIR     = Path(__file__).parent                   # Python BI System/
DATASETS_DIR = BASE_DIR.parent / "SQL DataWarehouse" / "datasets"
DB_PATH      = BASE_DIR / "data" / "warehouse.duckdb"

# ---------------------------------------------------------------------------
# Source CSV files  (same files used by the SQL Server Data Warehouse)
# ---------------------------------------------------------------------------
# CRM source files
CRM_CUST_INFO    = DATASETS_DIR / "source_crm" / "cust_info.csv"
CRM_PRD_INFO     = DATASETS_DIR / "source_crm" / "prd_info.csv"
CRM_SALES        = DATASETS_DIR / "source_crm" / "sales_details.csv"

# ERP source files
ERP_CUST_AZ12    = DATASETS_DIR / "source_erp" / "CUST_AZ12.csv"
ERP_LOC_A101     = DATASETS_DIR / "source_erp" / "LOC_A101.csv"
ERP_PX_CAT_G1V2  = DATASETS_DIR / "source_erp" / "PX_CAT_G1V2.csv"

# ---------------------------------------------------------------------------
# All source files as a registry for easy iteration / validation
# ---------------------------------------------------------------------------
SOURCE_FILES = {
    "crm_cust_info"    : CRM_CUST_INFO,
    "crm_prd_info"     : CRM_PRD_INFO,
    "crm_sales_details": CRM_SALES,
    "erp_cust_az12"    : ERP_CUST_AZ12,
    "erp_loc_a101"     : ERP_LOC_A101,
    "erp_px_cat_g1v2"  : ERP_PX_CAT_G1V2,
}

# ---------------------------------------------------------------------------
# DuckDB layer prefixes
# ---------------------------------------------------------------------------
BRONZE_PREFIX = "bronze_"
SILVER_PREFIX = "silver_"
