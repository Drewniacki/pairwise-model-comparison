import streamlit as st

# title
st.title("Terrafusion25")
st.subheader("grading model outputs")
st.caption("a.k.a. Geologists' input")

# tabs

tab1 = st.tabs(["Chunks"])

with tab1:
    st.write(
        "Grading chunking process here."
    )
