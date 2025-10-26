# db.py
from supabase import create_client
import streamlit as st
import os
import random

# ---- Config ----
CHUNKS_TABLE = "document_chunks_flat"
REVIEWS_TABLE = "chunk_reviews"
_PAGE = 1000  # paging window for large tables

# You can load these however you prefer:
supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)

# ---------- Chunks ----------

CHUNKS_TABLE = "document_chunks_flat"
REVIEWS_TABLE = "chunk_reviews"
_PAGE = 2000  # tune for your data size / Supabase row limits


def _fetch_all_reviewed_chunk_uuids():
    """Return a set of chunk_uuid that appear in chunk_reviews."""
    reviewed = set()
    start = 0
    while True:
        page = (
            supabase.table(REVIEWS_TABLE)
            .select("chunk_uuid")
            .range(start, start + _PAGE - 1)
            .execute()
        )
        rows = page.data or []
        if not rows:
            break
        for r in rows:
            cu = r.get("chunk_uuid")
            if cu:
                reviewed.add(cu)
        start += _PAGE
    return reviewed


def _fetch_all_chunks_source_map():
    """
    Return:
      - source_to_chunks: dict[source] = [chunk_uuid, ...]
      - any_chunk_by_uuid: dict[chunk_uuid] = row (minimal fields to fetch full row later if needed)
    We only need chunk_uuid and source here.
    """
    source_to_chunks = {}
    start = 0
    while True:
        page = (
            supabase.table(CHUNKS_TABLE)
            .select("chunk_uuid,source")
            .range(start, start + _PAGE - 1)
            .execute()
        )
        rows = page.data or []
        if not rows:
            break
        for r in rows:
            src = r.get("source")
            cu = r.get("chunk_uuid")
            if not src or not cu:
                continue
            source_to_chunks.setdefault(src, []).append(cu)
        start += _PAGE
    return source_to_chunks


def _weighted_choice_by_coverage(source_to_chunks, reviewed_set, epsilon=1e-6):
    """
    Build weights per source = (1 - coverage + epsilon),
    where coverage = reviewed_chunks_in_source / total_chunks_in_source.
    Return one chosen source (or None if empty).
    """
    sources = []
    weights = []
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
    # random.choices handles weights
    return random.choices(sources, weights=weights, k=1)[0]


def get_random_chunk():
    """
    Prefer:
      - chunks that haven't been reviewed,
      - documents with low coverage.
    Fallbacks to any chunk if needed.
    Returns a row dict or None.
    """
    # Nothing to do if there are no chunks at all
    count_resp = supabase.table(CHUNKS_TABLE).select("count", count="exact").limit(1).execute()
    total = getattr(count_resp, "count", 0) or 0
    if total <= 0:
        return None

    # 1) Build reviewed set
    reviewed = _fetch_all_reviewed_chunk_uuids()

    # 2) Build map of source -> chunk_uuids
    source_to_chunks = _fetch_all_chunks_source_map()
    if not source_to_chunks:
        return None

    # 3) Pick a source with weight ~ (1 - coverage)
    chosen_source = _weighted_choice_by_coverage(source_to_chunks, reviewed)
    if not chosen_source:
        # Fallback to pure random chunk if somehow empty
        idx = random.randint(0, total - 1)
        resp = supabase.table(CHUNKS_TABLE).select("*").range(idx, idx).execute()
        return (resp.data or [None])[0]

    # 4) Inside chosen source, prefer an unreviewed chunk
    cu_list = source_to_chunks[chosen_source]
    unreviewed = [cu for cu in cu_list if cu not in reviewed]
    target_uuid = random.choice(unreviewed) if unreviewed else random.choice(cu_list)

    # 5) Fetch and return the full row
    row_resp = (
        supabase.table(CHUNKS_TABLE)
        .select("*")
        .eq("chunk_uuid", target_uuid)
        .limit(1)
        .execute()
    )
    return (row_resp.data or [None])[0]

def get_similar_chunk(chunk_uuid: str):
    """
    Pick a 'similar' chunk with a strong bias toward the same document (same `source`),
    but not 100%. The bias decreases as the current document's review coverage increases.
    Preference inside a document: unreviewed chunks first; avoid returning the same chunk.

    Returns a row dict or None.
    """
    if not chunk_uuid:
        return None

    # 0) Fetch current chunk to get its source
    cur = (
        supabase.table(CHUNKS_TABLE)
        .select("source")
        .eq("chunk_uuid", chunk_uuid)
        .limit(1)
        .execute()
    )
    if not cur.data:
        return None

    current_source = cur.data[0].get("source")
    if not current_source:
        return None

    # 1) Reviewed set (for coverage & unreviewed preference)
    reviewed = _fetch_all_reviewed_chunk_uuids()

    # 2) Map of source -> chunk_uuids
    source_to_chunks = _fetch_all_chunks_source_map()
    if not source_to_chunks:
        return None

    # 3) Coverage for current source
    cu_list = source_to_chunks.get(current_source, [])
    if not cu_list:
        return None

    total_in_src = len(cu_list)
    reviewed_in_src = sum(1 for cu in cu_list if cu in reviewed)
    coverage = reviewed_in_src / total_in_src  # 0.0 .. 1.0

    # 4) Compute probability to stick to same doc.
    #    - At 0% coverage → ~0.95 (very strong)
    #    - At 100% coverage → ~0.05 (still possible, but weak)
    min_p, max_p = 0.05, 0.95
    p_same = min_p + (max_p - min_p) * (1.0 - coverage)

    def _fetch_row_by_uuid(cu: str):
        rr = (
            supabase.table(CHUNKS_TABLE)
            .select("*")
            .eq("chunk_uuid", cu)
            .limit(1)
            .execute()
        )
        return (rr.data or [None])[0]

    # 5) Try same document with probability p_same
    if random.random() < p_same:
        # Prefer unreviewed, exclude the current chunk
        unreviewed_other = [cu for cu in cu_list if cu not in reviewed and cu != chunk_uuid]
        pool = unreviewed_other or [cu for cu in cu_list if cu != chunk_uuid]
        if pool:
            return _fetch_row_by_uuid(random.choice(pool))

    # 6) Else pick from other documents, biased to lower coverage (reuse our weighting helper)
    #    Build a temporary dict excluding the current source
    other_sources = {s: lst for s, lst in source_to_chunks.items() if s != current_source and lst}
    if not other_sources:
        # No other sources? fall back to same doc (excluding current)
        pool = [cu for cu in cu_list if cu != chunk_uuid]
        if not pool:
            return None
        # Prefer unreviewed if any
        unreviewed_other = [cu for cu in pool if cu not in reviewed]
        pool = unreviewed_other or pool
        return _fetch_row_by_uuid(random.choice(pool))

    chosen_source = _weighted_choice_by_coverage(other_sources, reviewed)
    if not chosen_source:
        # Fallback: uniform over all other chunks
        flat_pool = [cu for s, lst in other_sources.items() for cu in lst]
        if not flat_pool:
            return None
        # Prefer unreviewed
        unreviewed_pool = [cu for cu in flat_pool if cu not in reviewed]
        flat_pool = unreviewed_pool or flat_pool
        return _fetch_row_by_uuid(random.choice(flat_pool))

    # Inside chosen other source, prefer unreviewed
    other_cu_list = other_sources[chosen_source]
    unreviewed_other = [cu for cu in other_cu_list if cu not in reviewed]
    target_uuid = random.choice(unreviewed_other) if unreviewed_other else random.choice(other_cu_list)
    return _fetch_row_by_uuid(target_uuid)


def get_chunk_by_uuid(chunk_uuid: str):
    """
    Retrieve a single chunk by its UUID (column: chunk_uuid) from the flat table.
    Returns dict or None.
    """
    if not chunk_uuid:
        return None

    resp = (
        supabase.table(CHUNKS_TABLE)
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
    for the *same document* (same `source`) based on `chunk_number`.

    direction = "next"  → chunk_number + 1
    direction = "prev"  → chunk_number - 1

    Returns dict or False.
    """
    if not chunk_uuid:
        return False

    # Load current chunk info (flat columns, no JSON)
    cur_resp = (
        supabase.table(CHUNKS_TABLE)
        .select("source, chunk_number")
        .eq("chunk_uuid", chunk_uuid)
        .limit(1)
        .execute()
    )
    if not cur_resp.data:
        return False

    current = cur_resp.data[0]
    source = current.get("source")
    chunk_number = current.get("chunk_number")

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

    # Fetch adjacent chunk within the same source
    resp = (
        supabase.table(CHUNKS_TABLE)
        .select("*")
        .eq("source", str(source))
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
    in the *same document* (same `source` column).

    Returns an integer count, or 0 if not found.
    """
    if not chunk_uuid:
        return 0

    # 1) Get source from the current chunk (flat column)
    cur_resp = (
        supabase.table(CHUNKS_TABLE)
        .select("source")
        .eq("chunk_uuid", chunk_uuid)
        .limit(1)
        .execute()
    )
    if not cur_resp.data:
        return 0

    source = cur_resp.data[0].get("source")
    if not source:
        return 0

    # 2) Count how many chunks share this source
    count_resp = (
        supabase.table(CHUNKS_TABLE)
        .select("count", count="exact")
        .eq("source", str(source))
        .execute()
    )
    return getattr(count_resp, "count", 0) or 0


# ---------- Reviews ----------

def _to_bool(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    return s in {"yes", "y", "true", "1", "t"}


def insert_chunk_review(form_payload: dict):
    """
    Insert a review row from the Streamlit form payload.
    Expected payload shape:
    {
      "chunk_uuid": "uuid-string",
      "name": "Krzysiek",
      "chunk_size": "too big",
      "chunk_info": "missing information",
      "has_well_diagram": "No",
      "comment": "asdsad",
      "observation": "dfghsfgh",
      "well_assignment": ["the assigned well is not mentioned in the text"]
    }
    Returns inserted row dict (or raises on error).
    """
    if not form_payload or "chunk_uuid" not in form_payload:
        raise ValueError("chunk_uuid is required")

    row = {
        "chunk_uuid": form_payload.get("chunk_uuid"),
        "name": form_payload.get("name"),
        "chunk_size": form_payload.get("chunk_size"),
        "chunk_info": form_payload.get("chunk_info"),
        "has_well_diagram": _to_bool(form_payload.get("has_well_diagram")),
        "comment": form_payload.get("comment"),
        "observation": form_payload.get("observation"),
        "well_assignment": form_payload.get("well_assignment") or [],
        # inserted_at is server-side default (now()), no need to send
    }

    resp = supabase.table(REVIEWS_TABLE).insert(row).execute()
    if not resp.data:
        raise RuntimeError("Insert failed with no data returned")
    return resp.data[0]


# ---------- Counts & Stats ----------

def total_chunks() -> int:
    """
    Count all rows in document_chunks_flat.
    Uses PostgREST exact count (efficient; no full fetch).
    """
    resp = supabase.table(CHUNKS_TABLE).select("count", count="exact").limit(1).execute()
    return getattr(resp, "count", 0) or 0


def total_reviews() -> int:
    """
    Count all rows in chunk_reviews.
    Uses PostgREST exact count (efficient; no full fetch).
    """
    resp = supabase.table(REVIEWS_TABLE).select("count", count="exact").limit(1).execute()
    return getattr(resp, "count", 0) or 0


def _distinct_chunk_count_in_reviews() -> int:
    """
    Count how many DISTINCT chunk_uuid values appear in chunk_reviews.
    """
    try:
        resp = supabase.table(REVIEWS_TABLE).select("chunk_uuid", count="exact", distinct=True).execute()  # type: ignore
        return getattr(resp, "count", None) or len({row["chunk_uuid"] for row in (resp.data or [])})
    except Exception:
        pass

    # Fallback: paginate and dedupe client-side
    seen = set()
    start = 0
    while True:
        page = supabase.table(REVIEWS_TABLE).select("chunk_uuid").range(start, start + _PAGE - 1).execute()
        rows = page.data or []
        if not rows:
            break
        for r in rows:
            cu = r.get("chunk_uuid")
            if cu:
                seen.add(cu)
        start += _PAGE
    return len(seen)


def chunks_with_at_least_one_review() -> int:
    """How many chunks have at least one review (distinct chunk_uuid in chunk_reviews)."""
    return _distinct_chunk_count_in_reviews()


def reviewed_chunks_in_this_document(chunk_uuid: str) -> int:
    """
    Given a chunk UUID, return how many chunks from the SAME document (same `source`)
    have at least one review.

    Strategy:
      1) Find the `source` for the given chunk (from document_chunks_flat).
      2) Get all chunk_uuids for that source from document_chunks_flat.
      3) Query chunk_reviews for those chunk_uuids and count DISTINCT chunk_uuid.
    """
    if not chunk_uuid:
        return 0

    # Step 1: get source for this chunk
    cur = (
        supabase.table(CHUNKS_TABLE)
        .select("source")
        .eq("chunk_uuid", chunk_uuid)
        .limit(1)
        .execute()
    )
    if not cur.data:
        return 0
    source = cur.data[0].get("source")
    if not source:
        return 0

    # Step 2: collect all chunk_uuids in this document
    doc_chunk_uuids = []
    start = 0
    while True:
        page = (
            supabase.table(CHUNKS_TABLE)
            .select("chunk_uuid")
            .eq("source", str(source))
            .range(start, start + _PAGE - 1)
            .execute()
        )
        rows = page.data or []
        if not rows:
            break
        doc_chunk_uuids.extend([r["chunk_uuid"] for r in rows if r.get("chunk_uuid")])
        start += _PAGE

    if not doc_chunk_uuids:
        return 0

    # Step 3: fetch reviews for these chunk_uuids and count DISTINCT
    distinct_reviewed = set()
    for i in range(0, len(doc_chunk_uuids), _PAGE):
        batch = doc_chunk_uuids[i : i + _PAGE]
        rev = (
            supabase.table(REVIEWS_TABLE)
            .select("chunk_uuid")
            .in_("chunk_uuid", batch)
            .execute()
        )
        for r in (rev.data or []):
            cu = r.get("chunk_uuid")
            if cu:
                distinct_reviewed.add(cu)

    return len(distinct_reviewed)


def total_documents() -> int:
    """
    Count how many distinct documents there are.
    A document is defined by the `source` column in document_chunks_flat.
    """
    try:
        resp = (
            supabase
            .table(CHUNKS_TABLE)
            .select("source", count="exact", distinct=True)  # type: ignore
            .execute()
        )
        return getattr(resp, "count", None) or len({row["source"] for row in (resp.data or [])})
    except Exception:
        pass

    # Fallback: fetch, dedupe
    seen = set()
    start = 0
    while True:
        page = (
            supabase
            .table(CHUNKS_TABLE)
            .select("source")
            .range(start, start + _PAGE - 1)
            .execute()
        )
        rows = page.data or []
        if not rows:
            break
        for r in rows:
            val = r.get("source")
            if val:
                seen.add(val)
        start += _PAGE
    return len(seen)


def documents_with_at_least_one_review() -> int:
    """
    Return the number of distinct documents that have at least one reviewed chunk.
    A document is identified by the `source` column (via document_chunks_flat).
    """
    reviewed_sources = set()
    start = 0

    while True:
        # Get chunk_uuids that have reviews in batches
        page = (
            supabase.table(REVIEWS_TABLE)
            .select("chunk_uuid")
            .range(start, start + _PAGE - 1)
            .execute()
        )
        rows = page.data or []
        if not rows:
            break

        chunk_uuids = [r["chunk_uuid"] for r in rows if r.get("chunk_uuid")]

        # Fetch their sources in batches from the flat table
        for i in range(0, len(chunk_uuids), _PAGE):
            batch = chunk_uuids[i : i + _PAGE]
            docs = (
                supabase.table(CHUNKS_TABLE)
                .select("source")
                .in_("chunk_uuid", batch)
                .execute()
            )
            for d in (docs.data or []):
                src = d.get("source")
                if src:
                    reviewed_sources.add(src)

        start += _PAGE

    return len(reviewed_sources)

def total_reviews_by_user(name: str) -> int:
    """
    Count how many reviews a specific user has submitted.
    """
    if not name:
        return 0

    resp = (
        supabase.table(REVIEWS_TABLE)
        .select("count", count="exact")
        .eq("name", name)
        .execute()
    )
    return getattr(resp, "count", 0) or 0