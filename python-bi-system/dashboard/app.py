"""
dashboard/app.py
================
Main Streamlit application entry point.

Run using:
    streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

import duckdb
import streamlit as st

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import DB_PATH

# ---------------------------------------------------------------------------
# Page Config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Data Warehouse & AI BI System",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS for Premium Theme
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    /* Metric Card Styling */
    .metric-card {
        background-color: #1E222D;
        border: 1px solid #2A2E3D;
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    .metric-label {
        font-size: 14px;
        color: #8E96A0;
        font-weight: 500;
        margin-bottom: 5px;
    }
    .metric-value {
        font-size: 26px;
        color: #00E699;
        font-weight: 700;
    }
    .metric-sub {
        font-size: 12px;
        color: #B0B7C0;
        margin-top: 5px;
    }
    /* Section Headers */
    .section-header {
        font-size: 22px;
        font-weight: 700;
        color: #FFFFFF;
        margin-top: 15px;
        margin-bottom: 15px;
        border-left: 4px solid #00E699;
        padding-left: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Cached DuckDB Connection
# ---------------------------------------------------------------------------
@st.cache_resource
def get_db_connection() -> duckdb.DuckDBPyConnection:
    """Read-only DuckDB connection for Streamlit app."""
    return duckdb.connect(str(DB_PATH), read_only=True)


def query_db(query: str, params=None):
    """Execute query and return DataFrame."""
    con = get_db_connection()
    if params:
        return con.execute(query, params).df()
    return con.execute(query).df()


# ---------------------------------------------------------------------------
# Main Multipage Setup
# ---------------------------------------------------------------------------
pages = {
    "Analytics Dashboards": [
        st.Page("pages/01_overview.py", title="Executive Overview", icon="📈", default=True),
        st.Page("pages/02_customers.py", title="Customer Analytics", icon="👥"),
        st.Page("pages/03_products.py", title="Product Analytics", icon="📦"),
        st.Page("pages/04_sales.py", title="Sales Analytics", icon="💰"),
    ],
    "AI Business Assistant": [
        st.Page("pages/05_ai_assistant.py", title="AI Chat & Query", icon="🤖"),
    ],
}

pg = st.navigation(pages)
pg.run()
