# db.py
"""
Supabase data access for the chunk-review Streamlit app.

Key improvements:
- Centralized run filter for all CHUNKS_TABLE queries (see get_chunking_run_filter()).
- Cleaned structure, consistent pagination, and precise docstrings.
- Review counts intersect with the currently-filtered run's chunks for consistency.
- Bias-aware selection helpers: prefer unreviewed chunks and low-coverage documents.

Assumptions:
- `document_chunks_flat` has columns: chunk_uuid (PK), source, chunk_number, chunking_run_id, ...
- `chunk_reviews` has column: chunk_uuid (FK to flat table).
"""

from __future__ import annotations

from supabase import create_client
import streamlit as st
import random
from typing import Dict, Iterable, List, Optional, Set, Tuple

# ---------- Config ----------

CHUNKS_TABLE = "document_chunks_flat"
REVIEWS_TABLE = "chunk_reviews"
_PAGE = 2000  # Tune to balance round-trips vs payload size

# Supabase client (adjust if you prefer env vars)
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


# ---------- Run filter (global constraint applied to CHUNKS_TABLE) ----------

def get_chunking_run_filter() -> Optional[Dict[str, str]]:
    """
    Return a dict of column->value filters that must be applied to *all*
    queries against the CHUNKS_TABLE. Change here to switch runs globally.

    Examples:
        return {"chunking_run_id": "RUN_2025_10_26"}
        return {"chunking_run_id": st.session_state.get("RUN_ID")}
        return None  # disable filtering

    By default: hard-coded example value; set to None if you don't need it.
    """
    return {"chunking_run_id": "well_chunks_run1.1"}  # <— change or set to None


def _apply_run_filter(q):
    """
    Apply get_chunking_run_filter() to a PostgREST query builder
    (only for CHUNKS_TABLE). No-ops if filter is None.
    """
    rf = get_chunking_run_filter()
    if rf:
        for col, val in rf.items():
            q = q.eq(col, val)
    return q


# ---------- Small utilities ----------

def _boolify(value):
    if value is None or isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    return s in {"yes", "y", "true", "1", "t"}


def _get_total_rows_for_chunks_where(filters: Optional[List[Tuple[str, str]]] = None) -> int:
    """
    Exact count on CHUNKS_TABLE with optional extra filters.
    Respects run filter automatically.
    """
    q = supabase.table(CHUNKS_TABLE).select("count", count="exact")
    q = _apply_run_filter(q)
    if filters:
        for col, val in filters:
            q = q.eq(col, val)
    resp = q.limit(1).execute()
    return getattr(resp, "count", 0) or 0


def _iter_all_chunk_rows(select_cols: str = "*", extra_filters: Optional[List[Tuple[str, str]]] = None):
    """
    Yield rows from CHUNKS_TABLE with pagination, respecting the run filter.
    """
    start = 0
    while True:
        q = supabase.table(CHUNKS_TABLE).select(select_cols)
        q = _apply_run_filter(q)
        if extra_filters:
            for col, val in extra_filters:
                q = q.eq(col, val)
        page = q.range(start, start + _PAGE - 1).execute()
        rows = page.data or []
        if not rows:
            break
        for r in rows:
            yield r
        start += _PAGE


def _iter_all_review_rows(select_cols: str = "chunk_uuid"):
    """
    Yield rows from REVIEWS_TABLE with pagination.
    (No run filter here; we intersect with the current run's chunks when needed.)
    """
    start = 0
    while True:
        page = (
            supabase.table(REVIEWS_TABLE)
            .select(select_cols)
            .range(start, start + _PAGE - 1)
            .execute()
        )
        rows = page.data or []
        if not rows:
            break
        for r in rows:
            yield r
        start += _PAGE


def _fetch_all_chunk_uuids_in_run() -> Set[str]:
    """
    Return the set of all chunk_uuid that belong to the current run filter.
    If run filter is None, this returns all chunk_uuids.
    """
    uuids: Set[str] = set()
    for r in _iter_all_chunk_rows(select_cols="chunk_uuid"):
        cu = r.get("chunk_uuid")
        if cu:
            uuids.add(cu)
    return uuids


# ---------- Coverage helpers ----------

def _fetch_all_reviewed_chunk_uuids() -> Set[str]:
    """
    Return a set of chunk_uuid that have *at least one* review,
    limited to the current run (by intersecting with the run's chunk UUIDs).
    """
    in_run = _fetch_all_chunk_uuids_in_run()
    if not in_run:
        return set()

    reviewed: Set[str] = set()
    for r in _iter_all_review_rows(select_cols="chunk_uuid"):
        cu = r.get("chunk_uuid")
        if cu and cu in in_run:
            reviewed.add(cu)
    return reviewed


def _fetch_all_chunks_source_map() -> Dict[str, List[str]]:
    """
    Map source -> list of chunk_uuids (for the current run).
    """
    source_to_chunks: Dict[str, List[str]] = {}
    for r in _iter_all_chunk_rows(select_cols="chunk_uuid,source"):
        src = r.get("source")
        cu = r.get("chunk_uuid")
        if not src or not cu:
            continue
        source_to_chunks.setdefault(str(src), []).append(cu)
    return source_to_chunks


def _weighted_choice_by_coverage(source_to_chunks: Dict[str, List[str]], reviewed_set: Set[str], epsilon: float = 1e-6) -> Optional[str]:
    """
    Choose a source with weight ~ (1 - reviewed_fraction). Favors low-coverage docs.
    """
    sources: List[str] = []
    weights: List[float] = []
    for src, cu_list in source_to_chunks.items():
        total = len(cu_list)
        if total == 0:
            continue
        reviewed_in_src = sum(1 for cu in cu_list if cu in reviewed_set)
        coverage = reviewed_in_src / total
        weight = max(0.0, 1.0 - coverage) + epsilon
        sources.append(src)
        weights.append(weight)
    if not sources:
        return None
    return random.choices(sources, weights=weights, k=1)[0]


def _fetch_row_by_uuid(chunk_uuid: str) -> Optional[dict]:
    """
    Fetch full row for a chunk_uuid, respecting the run filter.
    """
    q = supabase.table(CHUNKS_TABLE).select("*").eq("chunk_uuid", chunk_uuid).limit(1)
    q = _apply_run_filter(q)
    rr = q.execute()
    return (rr.data or [None])[0]


# ---------- Chunk selection ----------

def get_random_chunk() -> Optional[dict]:
    """
    Prefer:
      - chunks that haven't been reviewed,
      - documents (sources) with low coverage,
    within the current run filter.

    Returns a row dict or None.
    """
    total = _get_total_rows_for_chunks_where()
    if total <= 0:
        return None

    reviewed = _fetch_all_reviewed_chunk_uuids()
    source_to_chunks = _fetch_all_chunks_source_map()
    if not source_to_chunks:
        return None

    chosen_source = _weighted_choice_by_coverage(source_to_chunks, reviewed)
    if not chosen_source:
        # Fallback: uniform random row within run
        idx = random.randint(0, total - 1)
        q = supabase.table(CHUNKS_TABLE).select("*")
        q = _apply_run_filter(q)
        resp = q.range(idx, idx).execute()
        return (resp.data or [None])[0]

    # Prefer unreviewed within chosen source
    cu_list = source_to_chunks[chosen_source]
    unreviewed = [cu for cu in cu_list if cu not in reviewed]
    target_uuid = random.choice(unreviewed) if unreviewed else random.choice(cu_list)
    return _fetch_row_by_uuid(target_uuid)


def get_similar_chunk(chunk_uuid: str) -> Optional[dict]:
    """
    Strong bias toward the same document (same `source`) as `chunk_uuid`,
    but not 100%. Bias decreases with that document's review coverage.
    Prefers unreviewed; never returns the same chunk.
    Respects the current run filter.

    Returns a row dict or None.
    """
    if not chunk_uuid:
        return None

    # Current chunk's source (must match run)
    q = supabase.table(CHUNKS_TABLE).select("source").eq("chunk_uuid", chunk_uuid).limit(1)
    q = _apply_run_filter(q)
    cur = q.execute()
    if not cur.data:
        return None
    current_source = cur.data[0].get("source")
    if not current_source:
        return None
    current_source = str(current_source)

    reviewed = _fetch_all_reviewed_chunk_uuids()
    source_to_chunks = _fetch_all_chunks_source_map()
    cu_list = source_to_chunks.get(current_source, [])
    if not cu_list:
        return None

    total_in_src = len(cu_list)
    reviewed_in_src = sum(1 for cu in cu_list if cu in reviewed)
    coverage = reviewed_in_src / total_in_src

    # 0% coverage → ~0.95 stay; 100% → ~0.05
    min_p, max_p = 0.05, 0.95
    p_same = min_p + (max_p - min_p) * (1.0 - coverage)

    # Try same document first (probabilistically)
    if random.random() < p_same:
        unreviewed_other = [cu for cu in cu_list if cu not in reviewed and cu != chunk_uuid]
        pool = unreviewed_other or [cu for cu in cu_list if cu != chunk_uuid]
        if pool:
            return _fetch_row_by_uuid(random.choice(pool))

    # Else choose other documents by low-coverage weighting
    other_sources = {s: lst for s, lst in source_to_chunks.items() if s != current_source and lst}
    if not other_sources:
        # Fallback: only current doc available
        pool = [cu for cu in cu_list if cu != chunk_uuid]
        if not pool:
            return None
        unreviewed_other = [cu for cu in pool if cu not in reviewed]
        pool = unreviewed_other or pool
        return _fetch_row_by_uuid(random.choice(pool))

    chosen_other = _weighted_choice_by_coverage(other_sources, reviewed)
    if not chosen_other:
        # Uniform over all other chunks (prefer unreviewed)
        flat_pool = [cu for lst in other_sources.values() for cu in lst]
        if not flat_pool:
            return None
        unreviewed_pool = [cu for cu in flat_pool if cu not in reviewed]
        flat_pool = unreviewed_pool or flat_pool
        return _fetch_row_by_uuid(random.choice(flat_pool))

    other_cu_list = other_sources[chosen_other]
    unreviewed_other = [cu for cu in other_cu_list if cu not in reviewed]
    target_uuid = random.choice(unreviewed_other) if unreviewed_other else random.choice(other_cu_list)
    return _fetch_row_by_uuid(target_uuid)


def get_chunk_by_uuid(chunk_uuid: str) -> Optional[dict]:
    """
    Retrieve a single chunk by its UUID from the flat table.
    Respects the run filter.
    """
    if not chunk_uuid:
        return None
    return _fetch_row_by_uuid(chunk_uuid)


def get_adjacent_chunk(chunk_uuid: str, direction: str = "next") -> dict | bool:
    """
    Load the previous/next chunk for the *same document* (same `source`) based on `chunk_number`.
    direction: "next" | "prev"

    Returns: row dict or False.
    """
    if not chunk_uuid:
        return False

    q = supabase.table(CHUNKS_TABLE).select("source, chunk_number").eq("chunk_uuid", chunk_uuid).limit(1)
    q = _apply_run_filter(q)
    cur_resp = q.execute()
    if not cur_resp.data:
        return False

    source = cur_resp.data[0].get("source")
    chunk_number = cur_resp.data[0].get("chunk_number")
    if source is None or chunk_number is None:
        return False

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

    q2 = supabase.table(CHUNKS_TABLE).select("*").eq("source", str(source)).eq("chunk_number", target_num).limit(1)
    q2 = _apply_run_filter(q2)
    resp = q2.execute()
    if resp.data:
        return resp.data[0]
    return False


def count_chunks_in_document(chunk_uuid: str) -> int:
    """
    Given a chunk UUID, return the total number of chunks in the *same document* (same `source`).
    Respects the run filter.
    """
    if not chunk_uuid:
        return 0

    q = supabase.table(CHUNKS_TABLE).select("source").eq("chunk_uuid", chunk_uuid).limit(1)
    q = _apply_run_filter(q)
    cur = q.execute()
    if not cur.data:
        return 0

    source = cur.data[0].get("source")
    if not source:
        return 0

    q2 = supabase.table(CHUNKS_TABLE).select("count", count="exact").eq("source", str(source))
    q2 = _apply_run_filter(q2)
    resp = q2.execute()
    return getattr(resp, "count", 0) or 0


# ---------- Reviews ----------

def insert_chunk_review(form_payload: dict) -> dict:
    """
    Insert a review row from the Streamlit form payload.

    Expected:
    {
      "chunk_uuid": "...",
      "name": "...",
      "chunk_size": "...",
      "chunk_info": "...",
      "has_well_diagram": "Yes"/True/False/None,
      "comment": "...",
      "observation": "...",
      "well_assignment": [ ... ]  # list of strings
    }

    Returns inserted row dict.
    """
    if not form_payload or "chunk_uuid" not in form_payload:
        raise ValueError("chunk_uuid is required")

    row = {
        "chunk_uuid": form_payload.get("chunk_uuid"),
        "name": form_payload.get("name"),
        "chunk_size": form_payload.get("chunk_size"),
        "chunk_info": form_payload.get("chunk_info"),
        "has_well_diagram": _boolify(form_payload.get("has_well_diagram")),
        "comment": form_payload.get("comment"),
        "observation": form_payload.get("observation"),
        "well_assignment": form_payload.get("well_assignment") or [],
        # inserted_at handled by DB default
    }
    resp = supabase.table(REVIEWS_TABLE).insert(row).execute()
    if not resp.data:
        raise RuntimeError("Insert failed with no data returned")
    return resp.data[0]


# ---------- Counts & Stats (scoped to current run) ----------

def total_chunks() -> int:
    """Count all rows in CHUNKS_TABLE for the current run."""
    return _get_total_rows_for_chunks_where()


def total_reviews() -> int:
    """
    Count reviews for chunks that belong to the current run.
    (Intersect REVIEWS_TABLE with the run's chunk_uuids.)
    """

    # get function params
    function_params = {"table_name": CHUNKS_TABLE}
    run_filter = get_chunking_run_filter()
    if run_filter:
            function_params |= run_filter

    # call function
    resp = supabase.rpc("count_reviewed_chunks_for_run",function_params).execute()

    # return the count
    return resp.data


def _distinct_chunk_count_in_reviews_for_run() -> int:
    """
    Count DISTINCT reviewed chunk_uuid that belong to the current run.
    """
    in_run = _fetch_all_chunk_uuids_in_run()
    if not in_run:
        return 0

    # If server supports distinct, we could try it —
    # but we still must intersect with in_run, so client-side set is fine.
    seen: Set[str] = set()
    for r in _iter_all_review_rows(select_cols="chunk_uuid"):
        cu = r.get("chunk_uuid")
        if cu and cu in in_run:
            seen.add(cu)
    return len(seen)


def chunks_with_at_least_one_review() -> int:
    """
    Number of CHUNKS (in current run) that have at least one review.
    """
    return _distinct_chunk_count_in_reviews_for_run()


def reviewed_chunks_in_this_document(chunk_uuid: str) -> int:
    """
    For a given chunk_uuid, count how many chunks from the SAME document (same `source`)
    have at least one review, restricted to the current run.
    """
    if not chunk_uuid:
        return 0

    # 1) Source of this chunk (scoped to run)
    q = supabase.table(CHUNKS_TABLE).select("source").eq("chunk_uuid", chunk_uuid).limit(1)
    q = _apply_run_filter(q)
    cur = q.execute()
    if not cur.data:
        return 0
    source = cur.data[0].get("source")
    if not source:
        return 0
    source = str(source)

    # 2) All chunk_uuids in this doc (scoped to run)
    doc_chunk_uuids: List[str] = []
    for r in _iter_all_chunk_rows(select_cols="chunk_uuid", extra_filters=[("source", source)]):
        cu = r.get("chunk_uuid")
        if cu:
            doc_chunk_uuids.append(cu)
    if not doc_chunk_uuids:
        return 0

    # 3) DISTINCT chunk_uuid in reviews among those in this document
    distinct_reviewed: Set[str] = set()
    for i in range(0, len(doc_chunk_uuids), _PAGE):
        batch = doc_chunk_uuids[i : i + _PAGE]
        rev = supabase.table(REVIEWS_TABLE).select("chunk_uuid").in_("chunk_uuid", batch).execute()
        for r in (rev.data or []):
            cu = r.get("chunk_uuid")
            if cu:
                distinct_reviewed.add(cu)
    return len(distinct_reviewed)


def total_documents() -> int:
    """
    Count distinct `source` values in CHUNKS_TABLE for the current run.
    """
    # get function params
    function_params = {"table_name": CHUNKS_TABLE}
    run_filter = get_chunking_run_filter()
    if run_filter:
            function_params |= run_filter

    # call function
    resp = supabase.rpc("count_distinct_sources",function_params).execute()

    # return the count
    return resp.data


def documents_with_at_least_one_review() -> int:
    """
    Number of distinct documents (by `source`) in the current run that have
    at least one reviewed chunk.
    """
    # Collect all run-scoped chunk UUIDs -> source
    uuid_to_source: Dict[str, str] = {}
    for r in _iter_all_chunk_rows(select_cols="chunk_uuid,source"):
        cu = r.get("chunk_uuid")
        src = r.get("source")
        if cu and src:
            uuid_to_source[cu] = str(src)

    if not uuid_to_source:
        return 0

    reviewed_sources: Set[str] = set()
    for r in _iter_all_review_rows(select_cols="chunk_uuid"):
        cu = r.get("chunk_uuid")
        if cu in uuid_to_source:
            reviewed_sources.add(uuid_to_source[cu])

    return len(reviewed_sources)


def total_reviews_by_user(name: str) -> int:
    """
    Count reviews by user, restricted to the current run's chunks.
    """
    if not name:
        return 0

    # get function params
    function_params = {"table_name": CHUNKS_TABLE, "name": name}
    run_filter = get_chunking_run_filter()
    if run_filter:
            function_params |= run_filter

    # call function
    resp = supabase.rpc("count_reviewed_chunks_for_user",function_params).execute()

    # return the count
    return resp.data

