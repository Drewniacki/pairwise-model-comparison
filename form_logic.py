import streamlit as st

class ChunkForm:
    NAME_OPTIONS = ["Eva", "Gosia", "Krzysiek", "Tomek", "Michał", "Damian"]
    CHUNK_SIZE_OPTIONS = ["right", "too small", "too big"]
    WELL_ASSIGNMENT_OPTIONS = [
        "correct well name is assigned",
        "the assigned well name does not include sidetrack",
        "the assigned well is not the well this part of the document refers to",
        "the well this part of the document refers to is not assigned",
        "what was automatically assigned is not an actuall well name"]
    CHUNK_INFO_OPTIONS = [
        "processed correctly", 
        "missing information", 
        "hallucinated"]
    WELL_DIAGRAM_OPTIONS = ["Yes", "No"]

    def has_missing_fields():
        if "missing_fields" in st.session_state:
            return bool(len(st.session_state.missing_fields))
        return False
    
    def is_submitted():
        if "form_submitted" in st.session_state:
            return st.session_state.form_submitted
        return False

    def is_submitted_correctly():
        if ChunkForm.is_submitted():
            if not ChunkForm.has_missing_fields():
                return True
        return False

    def onclick():

        st.session_state.missing_fields = []
        if not st.session_state.name:
            st.session_state.missing_fields.append("Assesor")
        if not st.session_state.chunk_size:
            st.session_state.missing_fields.append("Chunk Size")
        if not st.session_state.well_assignment:
            st.session_state.missing_fields.append("Well Assignment Accuracy")
        if not st.session_state.chunk_info:
            st.session_state.missing_fields.append("Chunk Information")
        if not st.session_state.has_well_diagram:
            st.session_state.missing_fields.append("Includes Well Diagram?")

        st.session_state.form_submitted = True

        # clear form and preserve submitted values
        if ChunkForm.is_submitted_correctly():
            st.session_state.submitted = {}
            st.session_state.submitted["chunk_uuid"] = st.session_state.chunk_uuid
            st.session_state.submitted["name"] = st.session_state.name

            for field in ["chunk_size", "chunk_info", "has_well_diagram", "comment", "observation",]:
                st.session_state.submitted[field] = st.session_state.get(field)
                st.session_state[field] = None
            st.session_state.submitted["well_assignment"] = st.session_state.well_assignment
            st.session_state.well_assignment = []


    def set_session(chunk):
        # form values
        if "form_submitted" not in st.session_state:
            st.session_state.form_submitted = False
        if "missing_fileds" not in st.session_state:
            st.session_state.missing_fileds = []
        
        # chunk info
        st.session_state.chunk_uuid = chunk['chunk_uuid']