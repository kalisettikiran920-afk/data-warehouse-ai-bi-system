"""
dashboard/pages/02_customers.py
===============================
Customer Demographics & Analytics Page
"""

import plotly.express as px
import streamlit as st

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.app import query_db

st.title("👥 Customer Analytics Dashboard")
st.markdown("Detailed demographic, geographic, and behavioral breakdown of customers.")
st.divider()

col1, col2 = st.columns(2)

with col1:
    st.markdown('<div class="section-header">Customer Gender Distribution</div>', unsafe_allow_html=True)
    gender_query = """
    SELECT gender, COUNT(*) AS count
    FROM dim_customers
    GROUP BY gender;
    """
    gender_df = query_db(gender_query)
    fig_gender = px.pie(
        gender_df,
        values="count",
        names="gender",
        hole=0.4,
        template="plotly_dark",
        color_discrete_sequence=["#00E699", "#00B8FF", "#8E96A0"],
    )
    fig_gender.update_layout(height=350)
    st.plotly_chart(fig_gender, use_container_width=True)

with col2:
    st.markdown('<div class="section-header">Marital Status Breakdown</div>', unsafe_allow_html=True)
    marital_query = """
    SELECT marital_status, COUNT(*) AS count
    FROM dim_customers
    GROUP BY marital_status;
    """
    marital_df = query_db(marital_query)
    fig_marital = px.pie(
        marital_df,
        values="count",
        names="marital_status",
        hole=0.4,
        template="plotly_dark",
        color_discrete_sequence=["#FF7A00", "#7B2CBF", "#8E96A0"],
    )
    fig_marital.update_layout(height=350)
    st.plotly_chart(fig_marital, use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)
col3, col4 = st.columns(2)

with col3:
    st.markdown('<div class="section-header">Customers by Country</div>', unsafe_allow_html=True)
    geo_query = """
    SELECT country, COUNT(*) AS customer_count
    FROM dim_customers
    WHERE country IS NOT NULL AND country != 'n/a'
    GROUP BY country
    ORDER BY customer_count DESC;
    """
    geo_df = query_db(geo_query)
    fig_geo = px.bar(
        geo_df,
        x="country",
        y="customer_count",
        template="plotly_dark",
        color="customer_count",
        color_continuous_scale="Purples",
        labels={"country": "Country", "customer_count": "Customers"},
    )
    fig_geo.update_layout(height=350, showlegend=False)
    st.plotly_chart(fig_geo, use_container_width=True)

with col4:
    st.markdown('<div class="section-header">Customer Age Distribution</div>', unsafe_allow_html=True)
    age_query = """
    SELECT
        CASE 
            WHEN (2026 - YEAR(birthdate)) < 30 THEN '< 30'
            WHEN (2026 - YEAR(birthdate)) BETWEEN 30 AND 45 THEN '30 - 45'
            WHEN (2026 - YEAR(birthdate)) BETWEEN 46 AND 60 THEN '46 - 60'
            WHEN (2026 - YEAR(birthdate)) > 60 THEN '60+'
            ELSE 'Unknown'
        END AS age_group,
        COUNT(*) AS count
    FROM dim_customers
    GROUP BY 1
    ORDER BY count DESC;
    """
    age_df = query_db(age_query)
    fig_age = px.bar(
        age_df,
        x="age_group",
        y="count",
        template="plotly_dark",
        color="count",
        color_continuous_scale="Blues",
        labels={"age_group": "Age Group", "count": "Customers"},
    )
    fig_age.update_layout(height=350, showlegend=False)
    st.plotly_chart(fig_age, use_container_width=True)
