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

def get_chunk_by_uuid(chunk_uuid: str):
    """
    Retrieve a single chunk by its UUID (column: chunk_uuid).
    Returns dict or None.
    """
    if not chunk_uuid:
        return None

    resp = (
        supabase.table("document_chunks")
        .select("*")
        .eq("chunk_uuid", chunk_uuid)
        .limit(1)
        .execute()
    )

    if resp.data:
        return resp.data[0]
    return None

def get_adjacent_chunk(chunk_uuid: str, direction: str = "next"):
    """
    Given a chunk UUID, load the previous or next chunk
    for the *same document* based on chunk_number.

    direction = "next"  → chunk_number + 1
    direction = "prev"  → chunk_number - 1

    Returns dict or False.
    """
    if not chunk_uuid:
        return False

    # Load current chunk info
    cur_resp = (
        supabase.table("document_chunks")
        .select("metadata, chunk_number")
        .eq("chunk_uuid", chunk_uuid)
        .limit(1)
        .execute()
    )

    if not cur_resp.data:
        return False
    
    current = cur_resp.data[0]
    metadata = current.get("metadata") or {}
    source = metadata.get("source")
    chunk_number = current.get("chunk_number")

    if source is None or chunk_number is None:
        return False

    # Direction math
    try:
        num = int(chunk_number)
    except (TypeError, ValueError):
        return False

    if direction == "next":
        target_num = num + 1
    elif direction == "prev":
        target_num = num - 1
        if target_num < 0:
            return False
    else:
        raise ValueError('direction must be "next" or "prev"')

    # Fetch adjacent chunk
    resp = (
        supabase.table("document_chunks")
        .select("*")
        .filter("metadata->>source", "eq", str(source))
        .eq("chunk_number", target_num)
        .limit(1)
        .execute()
    )

    if resp.data:
        return resp.data[0]

    return False

def count_chunks_in_document(chunk_uuid: str):
    """
    Given a chunk UUID, return the total number of chunks
    in the *same document* (same metadata.source).

    Returns an integer count, or 0 if not found.
    """
    if not chunk_uuid:
        return 0

    # 1) Get source from the current chunk
    cur_resp = (
        supabase.table("document_chunks")
        .select("metadata, chunk_number")
        .eq("chunk_uuid", chunk_uuid)
        .limit(1)
        .execute()
    )

    if not cur_resp.data:
        return 0

    current = cur_resp.data[0]
    metadata = current.get("metadata") or {}
    source = metadata.get("source")

    if not source:
        return 0

    # 2) Count how many chunks share this source
    count_resp = (
        supabase.table("document_chunks")
        .select("count", count="exact")
        .filter("metadata->>source", "eq", str(source))
        .execute()
    )

    # PostgREST returns .count, not in data
    total = getattr(count_resp, "count", None)
    return total or 0
