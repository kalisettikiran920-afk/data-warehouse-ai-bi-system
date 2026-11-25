"""
dashboard/pages/04_sales.py
===========================
Sales Trends & Shipping Performance Page
"""

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.app import query_db

st.title("💰 Sales & Transaction Analytics")
st.markdown("Detailed order analysis, shipping lag, and top customer contributions.")
st.divider()

# ---------------------------------------------------------------------------
# 1. Quarterly Sales Trend
# ---------------------------------------------------------------------------
st.markdown('<div class="section-header">Quarterly Revenue Trend</div>', unsafe_allow_html=True)

q_query = """
SELECT
    DATE_TRUNC('quarter', order_date) AS quarter,
    SUM(sales_amount)                 AS revenue,
    SUM(quantity)                     AS total_units
FROM fact_sales
WHERE order_date IS NOT NULL
GROUP BY 1
ORDER BY 1;
"""
q_df = query_db(q_query)
q_df["quarter_str"] = q_df["quarter"].astype(str).str[:7]

fig_q = go.Figure()
fig_q.add_trace(
    go.Bar(
        x=q_df["quarter_str"],
        y=q_df["revenue"],
        name="Revenue ($)",
        marker_color="#00E699",
    )
)
fig_q.add_trace(
    go.Scatter(
        x=q_df["quarter_str"],
        y=q_df["total_units"],
        name="Units Sold",
        yaxis="y2",
        line=dict(color="#FF007A", width=3),
    )
)
fig_q.update_layout(
    template="plotly_dark",
    height=400,
    yaxis=dict(title="Revenue ($)"),
    yaxis2=dict(title="Units Sold", overlaying="y", side="right"),
    hovermode="x unified",
    legend=dict(x=0.01, y=0.99),
)
st.plotly_chart(fig_q, use_container_width=True)

col1, col2 = st.columns(2)

with col1:
    st.markdown('<div class="section-header">Shipping Duration (Order to Ship Lag)</div>', unsafe_allow_html=True)
    lag_query = """
    SELECT
        DATEDIFF('day', order_date, shipping_date) AS days_to_ship,
        COUNT(*) AS order_count
    FROM fact_sales
    WHERE order_date IS NOT NULL AND shipping_date IS NOT NULL
      AND shipping_date >= order_date
    GROUP BY 1
    ORDER BY days_to_ship;
    """
    lag_df = query_db(lag_query)
    fig_lag = px.bar(
        lag_df,
        x="days_to_ship",
        y="order_count",
        template="plotly_dark",
        color="order_count",
        color_continuous_scale="Cividis",
        labels={"days_to_ship": "Days to Ship", "order_count": "Orders"},
    )
    fig_lag.update_layout(height=350, showlegend=False)
    st.plotly_chart(fig_lag, use_container_width=True)

with col2:
    st.markdown('<div class="section-header">Top 10 Customers by Revenue</div>', unsafe_allow_html=True)
    top_cust_query = """
    SELECT
        c.first_name || ' ' || c.last_name AS customer_name,
        SUM(f.sales_amount)                AS total_spent
    FROM fact_sales f
    JOIN dim_customers c ON f.customer_key = c.customer_key
    GROUP BY 1
    ORDER BY total_spent DESC
    LIMIT 10;
    """
    top_cust_df = query_db(top_cust_query)
    fig_top_cust = px.bar(
        top_cust_df,
        x="total_spent",
        y="customer_name",
        orientation="h",
        template="plotly_dark",
        color="total_spent",
        color_continuous_scale="Viridis",
        labels={"total_spent": "Total Spend ($)", "customer_name": "Customer"},
    )
    fig_top_cust.update_layout(yaxis={"categoryorder": "total ascending"}, height=350, showlegend=False)
    st.plotly_chart(fig_top_cust, use_container_width=True)
