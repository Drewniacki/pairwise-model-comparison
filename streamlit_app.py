import streamlit as st
from db import get_random_chunk

# title
st.title("Terrafusion25: grading model outputs")
# st.caption("a.k.a. Geologists' input")

# tabs

tab_chunking, = st.tabs(["Chunking"])

with tab_chunking:
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
- Cunk includes well diagram? 
  - Yes/No
        

Comment 

General observation """)

    st.header("🎲 Random Chunk Viewer")

    if st.button("Get random chunk"):
        chunk = get_random_chunk()

        if chunk:
            st.subheader("Chunk Text")
            st.write(chunk["text"])

            st.subheader("Metadata")
            st.json(chunk["metadata"])

            st.caption(f"Chunk UUID: {chunk['chunk_uuid']}")
            st.caption(f"Chunk Number: {chunk['chunk_number']}")
            st.caption(f"Run ID: {chunk['chunking_run_id']}")
        else:
            st.warning("No chunks found in database.")
