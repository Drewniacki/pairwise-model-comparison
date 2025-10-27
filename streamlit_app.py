import streamlit as st
from db import get_random_chunk, get_chunk_by_uuid, get_adjacent_chunk, get_similar_chunk, insert_chunk_review
from db import count_chunks_in_document, total_documents, documents_with_at_least_one_review, total_reviews_by_user
from db import total_chunks, total_reviews, chunks_with_at_least_one_review, reviewed_chunks_in_this_document
from form_logic import ChunkForm
from drive import format_document_link

# title
st.title("Terrafusion25: assessing model outputs")

# tabs
tab_chunking, = st.tabs(["Chunking"])

with tab_chunking:
    
    # Chunk loading logic
    if ChunkForm.is_submitted():
        if ChunkForm.is_submitted_correctly():
            chunk = get_similar_chunk(st.session_state.chunk_uuid)
        else:
            chunk = get_chunk_by_uuid(st.session_state.chunk_uuid)
    else:
        chunk = get_random_chunk()


    

    if chunk:
        # check if clean load or submitted
        ChunkForm.set_session(chunk)
        

        # present chunk information
        st.subheader("Chunk", divider="orange")
        
        previous_chunk = get_adjacent_chunk(st.session_state.chunk_uuid, direction = "prev")
        if previous_chunk:
            with st.expander("previous chunk:  *[for info only]*"):
                st.code(previous_chunk["text"], language="text")

        st.markdown("##### Chunk content")
        document_chunk_count = count_chunks_in_document(st.session_state.chunk_uuid)
        chunk_number = chunk["chunk_number"]
        st.write(f"this is chunk no **{chunk_number} of {document_chunk_count}** in this document")
        st.code(chunk["text"], language="text")

        next_chunk = get_adjacent_chunk(st.session_state.chunk_uuid, direction = "next")
        if next_chunk:
            with st.expander("next chunk:  *[for info only]*"):
                st.code(next_chunk["text"], language="text")

        st.markdown("##### Assigned wells")
        if chunk['has_well']:
            for well in chunk['wells']:
                st.markdown('- '+well)
        else:
            st.write('*None*')

        source_title = "##### Document source"
        if ChunkForm.is_submitted_correctly():
            if chunk['source'] == get_chunk_by_uuid(st.session_state.submitted["chunk_uuid"])['source']:
                source_title += " :blue-badge[Same as previously assessed]"
            else:
                source_title += " :red-badge[New document source!]"
        st.markdown(source_title)
        st.write(format_document_link(chunk))

        st.markdown("##### Metadata")
        st.json({k: v for k, v in chunk.items() if k != "text"}, expanded=False)



        # Asessement fields
        st.subheader("User input", divider="blue")

        if ChunkForm.is_submitted() and ChunkForm.has_missing_fields():
            st.error(f"Please fill in all required fields: {', '.join(st.session_state.missing_fields)}")

        # 📋 Create a form
        with st.form("chunk_form"):

            name = st.selectbox("**Assesor**", 
                                options=ChunkForm.NAME_OPTIONS, key="name", index=None)
            chunk_size = st.selectbox("**Chunk Size**\n\nHow does the size of this chunk feel? Does it represent the right portion of the document? Does this chunk capture a natural section of the document, or does it cut off mid-idea?", 
                                      options=ChunkForm.CHUNK_SIZE_OPTIONS, key="chunk_size", index=None)
            well_assignment = st.multiselect("**Well Assignment Accuracy**\n\nDoes the well (or wells) automatically assigned to this chunk match what’s actually referenced in the text?", 
                                           options=ChunkForm.WELL_ASSIGNMENT_OPTIONS, key="well_assignment", default=None)
            chunk_info = st.selectbox("**Chunk Information**\n\nWhen compared to the original document, is the information here complete? Is anything missing or incorrectly included?", 
                                      options=ChunkForm.CHUNK_INFO_OPTIONS, key="chunk_info", index=None)
            has_well_diagram = st.selectbox("**Includes Well Diagram?**\n\nDoes this part of the original document include a well diagram or visual reference that the model should recognize?", 
                                            options=ChunkForm.WELL_DIAGRAM_OPTIONS, key="has_well_diagram", index=None)

            comment = st.text_area("**Comment** (optional)", key="comment")
            observation = st.text_area("**General Observation** (optional)\n\nAny broader insights from reviewing multiple chunks so far? Patterns, recurring issues, improvements noticed, etc.", 
                                       key="observation")
            
            # Submit button inside the form
            submitted = st.form_submit_button("Submit", on_click=ChunkForm.onclick)

            

        # ✅ Process the form data if submitted
        if submitted:
            if ChunkForm.is_submitted_correctly():
                inserted = insert_chunk_review(st.session_state.submitted)
                st.success("Form successfully submitted!")
                st.write("##### Submitted Data")
                st.json(inserted, expanded=False)


        # Stats
        with st.expander("Stats"):
            
            # chunks stat
            no_chunks = total_chunks()
            no_reviewed_chunks = chunks_with_at_least_one_review()
            if no_chunks > 0:
                pct = no_reviewed_chunks / no_chunks * 100
                st.write(f"{no_reviewed_chunks} of {no_chunks} chunks reviewed ({pct:.1f}%)")
            else:
                st.write("No chunks in database.")

            # documents stats
            no_documents = total_documents()
            no_documents_with_reviews = documents_with_at_least_one_review()

            if no_documents > 0:
                pct_docs = no_documents_with_reviews / no_documents * 100
                st.write(f"{no_documents_with_reviews} of {no_documents} documents have at least one review ({pct_docs:.1f}%)")
            else:
                st.write("No documents found.")

            
            # documents chunk stats
            no_document_reviews = reviewed_chunks_in_this_document(st.session_state.chunk_uuid)
            no_chunks_in_doc = count_chunks_in_document(st.session_state.chunk_uuid)
            if no_chunks_in_doc > 0:
                pct_doc = no_document_reviews / no_chunks_in_doc * 100
                st.write(f"{no_document_reviews} of {no_chunks_in_doc} chunks in *current document* reviewed ({pct_doc:.1f}%)")
            else:
                st.write("This document has no chunks (strange universe, but we acknowledge it).")

            # user stats
            if "name" in st.session_state and st.session_state.name:
                no_reviews = total_reviews()
                user_reviews = total_reviews_by_user(st.session_state.name)
                if no_reviews > 0:
                    pct_user = user_reviews / no_reviews * 100
                    st.write(f"{user_reviews} of {no_reviews} were submitted by You (**{st.session_state.name}**) ({pct_user:.1f}%)")
                    # st.write(
                    #     f"You (**{st.session_state.name}**) have submitted "
                    #     f"**{user_reviews}** of **{no_reviews}** reviews "
                    #     f"({pct_user:.1f}%)"
                    # )
                else:
                    st.write("There are no reviews")

    else:
        st.warning("No chunks found in database.")
