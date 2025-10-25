import streamlit as st

# title
st.title("Terrafusion25\ngrading model outputs")
st.subheader(a.k.a. Geologists' input")
st.divider()

# tabs

tab1, tab2 = st.tabs(["Hello", "Chunks"])

with tab1:
    st.write(
        "Let's start building! For help and inspiration, head over to [docs.streamlit.io](https://docs.streamlit.io/)."
    )

with tab2:
    st.write(
        "Grading chunking process here."
    )
