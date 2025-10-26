# db.py
from supabase import create_client
import streamlit as st
import os

# You can load these however you prefer:
supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)

def get_random_chunk():
    """
    Fetch one random chunk from the database.
    Returns a dict or None.
    """
    resp = supabase.rpc("get_random_chunk").execute()

    if resp.data:
        return resp.data[0]
    return None
