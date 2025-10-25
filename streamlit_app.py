import streamlit as st

# title
st.title("Terrafusion25: grading model outputs")
st.caption("a.k.a. Geologists' input")

# tabs

tab1, = st.tabs(["Chunks"])

with tab1:
    st.markdown("""
- Chunk size 
  - right
  - too small
  - too big
- Well assignment
  - Correct
  - no wells assigned but chunk refers to the well
  - incorrect well assigned
  - multiple wells assigned including correct and not correct one
- Chunk information 
  - processed correctly 
  - missing information 
  - hallucinated 

Comment 

General observation """)
