import streamlit as st

st.set_page_config(
    page_title="SQL-Refinery",
    page_icon="🛠️",
    layout="wide"
)

st.title("🛠️ SQL-Refinery")
st.subheader("AI-Powered SQL Optimization")

st.success("Streamlit is running successfully!")

st.write(
    "Welcome to SQL-Refinery. "
    "We will connect your existing SQL rewriting, "
    "CSV upload, and query benchmarking functionality next."
)

query = st.text_area(
    "Enter your SQL query",
    placeholder="SELECT * FROM customers;"
)

if st.button("Optimize SQL"):
    if query.strip():
        st.code(query, language="sql")
        st.info("Your SQL query is ready to connect to the optimizer.")
    else:
        st.warning("Please enter a SQL query.")