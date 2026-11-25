"""
dashboard/pages/01_overview.py
==============================
Executive Overview Dashboard Page
"""

import plotly.express as px
import streamlit as st

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.app import query_db

st.title("📈 Executive Overview Dashboard")
st.markdown("High-level key performance indicators and revenue trends from the Gold Star Schema.")
st.divider()

# ---------------------------------------------------------------------------
# 1. Fetch Top-Level KPIs
# ---------------------------------------------------------------------------
kpi_query = """
SELECT
    SUM(sales_amount)             AS total_revenue,
    COUNT(DISTINCT order_number)  AS total_orders,
    COUNT(DISTINCT customer_key)  AS total_customers,
    AVG(sales_amount)             AS avg_order_value
FROM fact_sales;
"""
kpi_df = query_db(kpi_query)

rev = kpi_df["total_revenue"].iloc[0] or 0
orders = kpi_df["total_orders"].iloc[0] or 0
customers = kpi_df["total_customers"].iloc[0] or 0
aov = kpi_df["avg_order_value"].iloc[0] or 0

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">TOTAL REVENUE</div>
            <div class="metric-value">${rev:,.0f}</div>
            <div class="metric-sub">Across all sales channels</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">TOTAL ORDERS</div>
            <div class="metric-value">{orders:,}</div>
            <div class="metric-sub">Completed transactions</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col3:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">TOTAL CUSTOMERS</div>
            <div class="metric-value">{customers:,}</div>
            <div class="metric-sub">Unique active buyers</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col4:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">AVG ORDER VALUE</div>
            <div class="metric-value">${aov:,.2f}</div>
            <div class="metric-sub">Revenue per transaction</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 2. Monthly Revenue Trend Chart
# ---------------------------------------------------------------------------
st.markdown('<div class="section-header">Monthly Revenue Trend</div>', unsafe_allow_html=True)

trend_query = """
SELECT
    DATE_TRUNC('month', order_date) AS month,
    SUM(sales_amount)               AS monthly_revenue,
    COUNT(DISTINCT order_number)   AS order_count
FROM fact_sales
WHERE order_date IS NOT NULL
GROUP BY 1
ORDER BY 1;
"""
trend_df = query_db(trend_query)

fig_trend = px.line(
    trend_df,
    x="month",
    y="monthly_revenue",
    title="Monthly Revenue Trajectory ($)",
    labels={"month": "Month", "monthly_revenue": "Revenue ($)"},
    template="plotly_dark",
    markers=True,
    color_discrete_sequence=["#00E699"],
)
fig_trend.update_layout(height=400, hovermode="x unified")
st.plotly_chart(fig_trend, use_container_width=True)

# ---------------------------------------------------------------------------
# 3. Top Products & Revenue by Country
# ---------------------------------------------------------------------------
row2_col1, row2_col2 = st.columns(2)

with row2_col1:
    st.markdown('<div class="section-header">Top 5 Products by Revenue</div>', unsafe_allow_html=True)
    top_prd_query = """
    SELECT
        p.product_name,
        SUM(f.sales_amount) AS revenue
    FROM fact_sales f
    JOIN dim_products p ON f.product_key = p.product_key
    GROUP BY 1
    ORDER BY revenue DESC
    LIMIT 5;
    """
    top_prd_df = query_db(top_prd_query)
    fig_top_prd = px.bar(
        top_prd_df,
        x="revenue",
        y="product_name",
        orientation="h",
        template="plotly_dark",
        color="revenue",
        color_continuous_scale="Viridis",
        labels={"revenue": "Revenue ($)", "product_name": "Product"},
    )
    fig_top_prd.update_layout(yaxis={"categoryorder": "total ascending"}, height=350, showlegend=False)
    st.plotly_chart(fig_top_prd, use_container_width=True)

with row2_col2:
    st.markdown('<div class="section-header">Revenue by Country</div>', unsafe_allow_html=True)
    geo_query = """
    SELECT
        c.country,
        SUM(f.sales_amount) AS revenue
    FROM fact_sales f
    JOIN dim_customers c ON f.customer_key = c.customer_key
    WHERE c.country IS NOT NULL AND c.country != 'n/a'
    GROUP BY 1
    ORDER BY revenue DESC;
    """
    geo_df = query_db(geo_query)
    fig_geo = px.bar(
        geo_df,
        x="country",
        y="revenue",
        template="plotly_dark",
        color="revenue",
        color_continuous_scale="Teal",
        labels={"country": "Country", "revenue": "Revenue ($)"},
    )
    fig_geo.update_layout(height=350, showlegend=False)
    st.plotly_chart(fig_geo, use_container_width=True)
