"""
dashboard/pages/05_ai_assistant.py
==============================
AI Business Assistant Page (Natural Language Query & Explanation)
"""

import os
import plotly.express as px
import streamlit as st

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import importlib
import ai.assistant
importlib.reload(ai.assistant)
from ai.assistant import process_user_question

st.title("🤖 AI Business Assistant")
st.markdown("Ask business questions in natural language. The AI converts your question into a read-only SQL query, executes it against the Gold Star Schema, and explains the results.")
st.divider()

# Check for GROQ API Key
if not os.getenv("GROQ_API_KEY"):
    st.warning("⚠️ **GROQ_API_KEY** is not set in `.env`. Please add your free Groq API key to `.env` file to enable the AI Assistant.")
    st.info("Example `.env` format:\n`GROQ_API_KEY=gsk_your_key_here`")

# Sample questions selector
st.markdown("### 💡 Sample Business Questions")
sample_questions = [
    "What are the top 5 products by total revenue?",
    "Which country generated the highest total sales?",
    "Show total sales by product category",
    "What is the revenue breakdown by customer gender?",
    "List the top 10 customers who spent the most money",
]

selected_sample = st.selectbox("Select a quick sample question or type your own below:", ["-- Type custom question --"] + sample_questions)

user_question = st.text_input(
    "Ask a Question:",
    value="" if selected_sample == "-- Type custom question --" else selected_sample,
    placeholder="e.g. Which product category brought in the most revenue in 2023?",
)

submit_button = st.button("🚀 Ask Assistant", type="primary")

if submit_button and user_question:
    with st.spinner("🤖 Thinking... Generating SQL query & analyzing database..."):
        res = process_user_question(user_question)

    if not res["success"]:
        st.error(f"❌ Error: {res['error']}")
        if res["sql"]:
            with st.expander("Generated SQL Query (Failed Validation or Execution)"):
                st.code(res["sql"], language="sql")
    else:
        # Success output
        st.success("✅ Query Executed Successfully! (Read-Only SQL Verified)")

        # AI Summary Explanation Box
        if res["explanation"]:
            st.info(f"💡 **AI Business Summary:**\n\n{res['explanation']}")

        # Generated SQL Expander
        with st.expander("🔍 View Generated SQL Query"):
            st.code(res["sql"], language="sql")

        df = res["dataframe"]
        if df is not None and not df.empty:
            st.markdown("### 📊 Data Results")
            st.dataframe(df, use_container_width=True)

            # Auto Chart Generation Logic
            num_cols = df.select_dtypes(include=["number"]).columns.tolist()
            cat_cols = [c for c in df.columns if c not in num_cols]

            if len(num_cols) >= 1 and len(cat_cols) >= 1 and len(df) <= 30:
                st.markdown("### 📈 Auto-Generated Visualization")
                x_col = cat_cols[0]
                y_col = num_cols[0]

                if len(df) <= 8:
                    fig = px.bar(df, x=x_col, y=y_col, color=x_col, template="plotly_dark", title=f"{y_col.replace('_', ' ').title()} by {x_col.replace('_', ' ').title()}")
                else:
                    fig = px.bar(df, x=x_col, y=y_col, template="plotly_dark", title=f"{y_col.replace('_', ' ').title()} by {x_col.replace('_', ' ').title()}")
                
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)

        elif df is not None and df.empty:
            st.warning("Query returned 0 records.")
