"""
dashboard/pages/03_products.py
==============================
Product Performance & Catalog Analytics Page
"""

import plotly.express as px
import streamlit as st

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.app import query_db

st.title("📦 Product Analytics Dashboard")
st.markdown("Category performance, subcategory breakdowns, product lines, and cost vs price margins.")
st.divider()

col1, col2 = st.columns(2)

with col1:
    st.markdown('<div class="section-header">Revenue by Category</div>', unsafe_allow_html=True)
    cat_query = """
    SELECT
        p.category,
        SUM(f.sales_amount) AS revenue
    FROM fact_sales f
    JOIN dim_products p ON f.product_key = p.product_key
    WHERE p.category IS NOT NULL AND p.category != 'n/a'
    GROUP BY 1
    ORDER BY revenue DESC;
    """
    cat_df = query_db(cat_query)
    fig_cat = px.bar(
        cat_df,
        x="category",
        y="revenue",
        template="plotly_dark",
        color="revenue",
        color_continuous_scale="Plasma",
        labels={"category": "Category", "revenue": "Revenue ($)"},
    )
    fig_cat.update_layout(height=350, showlegend=False)
    st.plotly_chart(fig_cat, use_container_width=True)

with col2:
    st.markdown('<div class="section-header">Revenue by Product Line</div>', unsafe_allow_html=True)
    line_query = """
    SELECT
        p.product_line,
        SUM(f.sales_amount) AS revenue
    FROM fact_sales f
    JOIN dim_products p ON f.product_key = p.product_key
    WHERE p.product_line IS NOT NULL AND p.product_line != 'n/a'
    GROUP BY 1;
    """
    line_df = query_db(line_query)
    fig_line = px.pie(
        line_df,
        values="revenue",
        names="product_line",
        hole=0.4,
        template="plotly_dark",
        color_discrete_sequence=["#00E699", "#FF007A", "#00B8FF", "#FFB800"],
    )
    fig_line.update_layout(height=350)
    st.plotly_chart(fig_line, use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

st.markdown('<div class="section-header">Category & Subcategory Treemap Hierarchy</div>', unsafe_allow_html=True)
tree_query = """
SELECT
    p.category,
    p.subcategory,
    SUM(f.sales_amount) AS revenue,
    SUM(f.quantity)     AS total_units
FROM fact_sales f
JOIN dim_products p ON f.product_key = p.product_key
WHERE p.category IS NOT NULL AND p.category != 'n/a'
GROUP BY 1, 2;
"""
tree_df = query_db(tree_query)
fig_tree = px.treemap(
    tree_df,
    path=["category", "subcategory"],
    values="revenue",
    color="revenue",
    color_continuous_scale="Viridis",
    template="plotly_dark",
)
fig_tree.update_layout(height=450)
st.plotly_chart(fig_tree, use_container_width=True)
